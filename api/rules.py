"""
api/rules.py — AIbouに守らせる「ルール」をGitHubのメモから読む。

やりたいこと:
  Obsidianで書いたメモを、そのままAIbouの行動指針にする。
  「Xに投稿するときは絵文字を使わない」のような約束を、人が読める形で置いておき、
  AIbouがそれに従う。人がメモを直せば、AIbouの振る舞いが変わる。

なぜGitHubを毎回読まないか:
  返事が始まる前にGitHubへ問い合わせると、その往復がそのまま待ち時間になる。
  1メッセージあたり1秒近く増えることもある。ルールは毎日変わるものではないので、
  取りに行くのは「同期したとき」だけにして、ふだんは保存済みから読む。

  さらに、保存済みを読むのも1リクエストに1回で済むよう、そのときのクライアントに
  短時間ぶら下げる（keychain と同じやり方）。結果として、会話のたびに増える
  往復はゼロになる。

ルールの書き方（メモの先頭に置く）:

    ---
    適用: ツール
    対象: x_post, notify
    ---
    - 絵文字は使わない
    - 140字を超えたら、分割せずに削る

  適用は4種類:
    常時   … いつでも読む（指示文に入る）
    ツール … そのツールを使う直前に読む   ← 一番確実
    モード … そのモードのときだけ
    話題   … 本文に対象の言葉が出たときだけ（当たり外れがある）

  書き忘れた場合は「常時」になる。ただし常時ぶんは合計文字数に上限を設ける
  （全部を常に入れると、肝心の質問が薄まるため）。

安全のうえでの決めごと:
  ・AIbouはこのメモを書き換えない。読むだけ。
    書き換えられると、AIが自分の都合のいいルールを作れてしまう。
  ・取り込むのはテキストのメモだけ。実行はしない。
"""

import time
import uuid
from typing import Dict, List, Optional

import config
import memstore

TABLE = "agent_rules"

# 常時ぶんの合計上限。ここを超えたぶんは切り、切ったことを報告する。
ALWAYS_BUDGET = 4_000
# 1つのルールの上限（長すぎるルールは部分的に無視される）。
MAX_RULE_CHARS = 2_000
# 取り込む最大件数。
MAX_RULES = 200

APPLIES = ("always", "tool", "mode", "topic")

# 日本語で書けるようにする（メモは人が読むものなので）。
_APPLIES_JA = {
    "常時": "always", "いつでも": "always", "always": "always",
    "ツール": "tool", "tool": "tool",
    "モード": "mode", "mode": "mode",
    "話題": "topic", "キーワード": "topic", "topic": "topic",
}
_KEY_APPLIES = ("適用", "applies", "apply")
_KEY_TARGETS = ("対象", "targets", "target", "globs")
_KEY_TITLE = ("題名", "title", "name")

_mem_rules = memstore.TenantList()

# 1リクエスト中に何度も読み直さないための覚え書き（クライアントにぶら下げる）。
_CACHE_NOTE = "_aibou_rules_cache"
_CACHE_TTL = 60.0


# ── メモの読み取り ────────────────────────────────────────────────
def parse(path: str, text: str) -> Optional[dict]:
    """1枚のメモを、ルール1件に変換する。中身が無ければ None。"""
    text = (text or "").replace("\r\n", "\n")
    meta, body = _split_front_matter(text)

    body = body.strip()[:MAX_RULE_CHARS]
    if not body:
        return None

    applies = _APPLIES_JA.get(_pick(meta, _KEY_APPLIES).lower(), "always")
    targets = [t.strip() for t in _pick(meta, _KEY_TARGETS).replace("、", ",").split(",")]
    targets = [t for t in targets if t]

    # 対象を書かずに「ツール」等にしても、誰にも当たらない。常時として扱う。
    if applies != "always" and not targets:
        applies = "always"

    title = _pick(meta, _KEY_TITLE) or _title_from_path(path)
    return {
        "id": str(uuid.uuid4()),
        "path": path,
        "title": title,
        "applies": applies,
        "targets": ",".join(targets),
        "body": body,
    }


def _split_front_matter(text: str):
    """先頭の --- ブロックを見出しとして切り出す。無ければ空の見出し。"""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    head = text[3:end]
    rest = text[end + 4:]
    meta: Dict[str, str] = {}
    for line in head.split("\n"):
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        meta[k.strip().lower()] = v.strip().strip("\"'").strip("[]")
    return meta, rest


def _pick(meta: dict, keys) -> str:
    for k in keys:
        v = meta.get(k)
        if v:
            return str(v)
    return ""


def _title_from_path(path: str) -> str:
    name = (path or "").rsplit("/", 1)[-1]
    return name[:-3] if name.lower().endswith(".md") else name


# ── 保存 ──────────────────────────────────────────────────────────
def _forget_cache() -> None:
    try:
        c = config.get_supabase()
        if c is not None:
            setattr(c, _CACHE_NOTE, None)
    except Exception:
        pass


def _all() -> List[dict]:
    """保存済みのルール全部。1リクエスト中は覚えておく。"""
    c = config.get_supabase()
    if c is None:
        return list(_mem_rules)

    note = getattr(c, _CACHE_NOTE, None)
    if note and (time.monotonic() - note[0]) < _CACHE_TTL:
        return note[1]

    try:
        rows = (c.table(TABLE).select("*").limit(MAX_RULES).execute().data) or []
    except Exception:
        rows = list(_mem_rules)
    try:
        setattr(c, _CACHE_NOTE, (time.monotonic(), rows))
    except Exception:
        pass
    return rows


def replace_all(items: List[dict]) -> dict:
    """取り込んだ内容で丸ごと置き換える（消したメモが残らないように）。"""
    items = list(items)[:MAX_RULES]

    # メモリ側は、入れ物ごと差し替えず中身を入れ替える
    # （保存先ごとに分けている意味が消えるため）。
    for _i in range(len(_mem_rules) - 1, -1, -1):
        del _mem_rules[_i]
    for it in items:
        _mem_rules.append(it)

    c = config.get_supabase()
    if c is None:
        _forget_cache()
        return {"ok": True, "count": len(items), "persisted": False}

    try:
        c.table(TABLE).delete().neq("id", "").execute()
    except Exception:
        pass
    try:
        if items:
            c.table(TABLE).insert(items).execute()
        _forget_cache()
        return {"ok": True, "count": len(items), "persisted": True}
    except Exception as e:
        _forget_cache()
        return {"ok": True, "count": len(items), "persisted": False,
                "warning": f"保存先に書けませんでした（{str(e)[:140]}）。"
                           "サーバーが更新されるとルールは消えます。"}


# ── 取り込み ──────────────────────────────────────────────────────
def sync(repo: str = "", path: str = "") -> dict:
    """GitHubのリポジトリからメモを取り込む。ここでだけGitHubに触る。"""
    import gh
    import keychain

    repo = (repo or keychain.get_key("RULES_REPO") or "").strip()
    if not repo:
        return {"error": "ルールの置き場（owner/name）が設定されていません"}
    path = (path if path is not None else "").strip() or keychain.get_key("RULES_PATH") or ""

    res = gh.import_repo(repo, path=path)
    if res.get("error"):
        return res

    items: List[dict] = []
    for f in res.get("files") or []:
        p = f.get("path") or ""
        if not p.lower().endswith(".md"):
            continue
        rule = parse(p, f.get("content") or "")
        if rule:
            items.append(rule)

    saved = replace_all(items)
    out = {
        "ok": True,
        "repo": res.get("repo"),
        "count": len(items),
        "persisted": saved.get("persisted", False),
        "by_applies": {a: sum(1 for i in items if i["applies"] == a) for a in APPLIES},
    }
    if saved.get("warning"):
        out["warning"] = saved["warning"]
    if not items:
        out["warning"] = ("読めるメモが1枚もありませんでした。"
                          ".md のファイルがあるか、フォルダの指定が合っているか確認してください。")
    return out


# ── 読み出し（ここは毎回呼ばれる。GitHubには触らない） ──────────────
def _block(items: List[dict], heading: str, budget: int = 0) -> str:
    """ルールを指示文に入れる形にまとめる。"""
    if not items:
        return ""
    out = [heading]
    used = 0
    for it in items:
        piece = f"\n■ {it.get('title') or it.get('path')}\n{it.get('body') or ''}"
        if budget and used + len(piece) > budget:
            out.append(f"\n（ここまで。残り{len(items) - len(out) + 1}件は長さの都合で省略）")
            break
        out.append(piece)
        used += len(piece)
    return "".join(out)


def always_block() -> str:
    """いつでも読むルール。指示文の先頭に入れる。"""
    items = [r for r in _all() if (r.get("applies") or "always") == "always"]
    return _block(items, "【守ること（あなたの決まりごと）】", budget=ALWAYS_BUDGET)


def for_tool(tool: str) -> str:
    """そのツールを使う直前に読ませるルール。無ければ空。"""
    tool = (tool or "").strip()
    if not tool:
        return ""
    items = [r for r in _all()
             if r.get("applies") == "tool" and tool in _targets(r)]
    return _block(items, f"【{tool} を使うときのルール】")


def for_mode(mode: str) -> str:
    mode = (mode or "").strip().lower()
    if not mode:
        return ""
    items = [r for r in _all()
             if r.get("applies") == "mode" and mode in [t.lower() for t in _targets(r)]]
    return _block(items, "【この画面でのルール】")


def for_topic(text: str) -> str:
    """本文に対象の言葉が出たときだけ読むルール。

    当たり外れがある方法なので、外せない約束をここに置いてはいけない。
    確実に効かせたいものは「ツール」か「モード」で指定すること。
    """
    text = (text or "")
    if not text:
        return ""
    items = [r for r in _all()
             if r.get("applies") == "topic" and any(t and t in text for t in _targets(r))]
    return _block(items, "【この話題でのルール】")


def _targets(rule: dict) -> List[str]:
    return [t.strip() for t in str(rule.get("targets") or "").split(",") if t.strip()]


def status() -> dict:
    """UI用。ルールの一覧（本文は短く切る）。"""
    import keychain
    items = _all()
    return {
        "repo": keychain.get_key("RULES_REPO"),
        "path": keychain.get_key("RULES_PATH"),
        "count": len(items),
        "items": [{
            "path": r.get("path"),
            "title": r.get("title"),
            "applies": r.get("applies") or "always",
            "targets": _targets(r),
            "preview": (r.get("body") or "")[:120],
        } for r in items],
    }
