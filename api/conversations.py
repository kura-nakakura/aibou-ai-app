"""
api/conversations.py — CHATの会話履歴を、その人のDBに残す。

調べて分かったこと: 会話履歴はブラウザの localStorage にしか無かった。
だから端末を変えると全部消えるし、ブラウザのデータを消しても消える。
規約には「会話…はあなたのSupabaseに保存されます」と書いてあったので、
そこだけ実装が追いついていなかった。

方針:
  ・保存先はその人のDB（config.get_supabase() が返すもの）。
  ・端末側の localStorage は「手元の控え」として残す。オフラインでも読めるし、
    保存先が無い人でも会話自体はできたほうがよい。
  ・本文は jsonb に丸ごと入れる。会話は1件ずつ読み書きするので、
    行を分ける利点が薄く、読み書きが単純なほうが壊れにくい。
  ・大きくなりすぎないよう、1会話あたりの上限を決めて古い発言から捨てる
    （画像を含む会話は、放っておくと数MBになる）。
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

import config
import memstore

TABLE = "conversations"

# 1会話に残す発言数と、1発言の長さの上限。
# 上限が無いと、画像付きの長い会話がDBの行サイズを押し上げ、
# ある日から突然保存が失敗するようになる（原因が分かりにくい）。
MAX_MESSAGES = 200
MAX_CHARS_PER_MESSAGE = 8000
MAX_CONVERSATIONS = 200

# 保存先が無いときの控え（1人運用・オフライン）。プロセスが死ぬと消える。
_mem = memstore.TenantList()
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trim(messages) -> List[dict]:
    """保存する形に整える。長すぎるものは切る。

    切るのは末尾ではなく先頭（古いほう）。直近のやり取りのほうが役に立つ。
    """
    out: List[dict] = []
    for m in (messages or [])[-MAX_MESSAGES:]:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "user")
        if role not in ("user", "assistant"):
            role = "user"
        text = str(m.get("content") or m.get("text") or "")
        out.append({"role": role, "content": text[:MAX_CHARS_PER_MESSAGE]})
    return out


def _title_of(messages, fallback: str = "") -> str:
    """一覧に出す見出し。最初の発言から作る。"""
    if fallback.strip():
        return fallback.strip()[:60]
    for m in messages or []:
        if isinstance(m, dict) and (m.get("role") or "user") == "user":
            t = str(m.get("content") or m.get("text") or "").strip()
            if t:
                return t.replace("\n", " ")[:60]
    return "新しいチャット"


def list_conversations(limit: int = 50) -> List[dict]:
    """一覧。本文は返さない（重いので、開いたときに取りに行く）。"""
    c = config.get_supabase()
    if c:
        try:
            rows = (c.table(TABLE).select("id,title,updated_at,created_at")
                    .order("updated_at", desc=True).limit(limit).execute().data) or []
            return rows
        except Exception:
            pass
    return [{k: v for k, v in row.items() if k != "messages"}
            for row in sorted(_mem, key=lambda r: r.get("updated_at") or "", reverse=True)[:limit]]


def get_conversation(conv_id: str) -> Optional[dict]:
    """1件を本文つきで返す。無ければ None。"""
    cid = (conv_id or "").strip()
    if not cid:
        return None
    c = config.get_supabase()
    if c:
        try:
            rows = (c.table(TABLE).select("*").eq("id", cid).limit(1).execute().data) or []
            if rows:
                return rows[0]
        except Exception:
            pass
    for row in _mem:
        if row.get("id") == cid:
            return row
    return None


def save_conversation(conv_id: str, messages, title: str = "") -> dict:
    """作成または上書き。idを渡せば上書き、空なら新規。

    会話は同じidに何度も書き戻る（発言のたびに更新される）ので、
    upsert で1行を持ち回る。行が増え続けると一覧が壊れる。
    """
    msgs = _trim(messages)
    if not msgs:
        return {"error": "保存する会話がありません"}

    cid = (conv_id or "").strip() or str(uuid.uuid4())
    row = {
        "id": cid,
        "title": _title_of(msgs, title),
        "messages": msgs,
        "updated_at": _now(),
    }

    c = config.get_supabase()
    if c:
        try:
            existing = (c.table(TABLE).select("id").eq("id", cid).limit(1).execute().data) or []
            if existing:
                c.table(TABLE).update(row).eq("id", cid).execute()
            else:
                row["created_at"] = _now()
                c.table(TABLE).insert(row).execute()
            return {"ok": True, "id": cid, "title": row["title"]}
        except Exception as e:
            # 握りつぶさない。保存できていないのに成功を返すと、
            # 端末を変えたときに初めて消えたと気づくことになる。
            return {"error": f"会話を保存できませんでした: {str(e)[:180]}"}

    row.setdefault("created_at", _now())
    for i, r in enumerate(_mem):
        if r.get("id") == cid:
            _mem[i] = row
            break
    else:
        _mem.insert(0, row)
        del _mem[MAX_CONVERSATIONS:]
    return {"ok": True, "id": cid, "title": row["title"]}


def delete_conversation(conv_id: str) -> dict:
    cid = (conv_id or "").strip()
    if not cid:
        return {"error": "idが空です"}
    c = config.get_supabase()
    if c:
        try:
            c.table(TABLE).delete().eq("id", cid).execute()
            return {"ok": True}
        except Exception as e:
            return {"error": f"削除できませんでした: {str(e)[:180]}"}
    before = len(_mem)
    _mem[:] = [r for r in _mem if r.get("id") != cid]
    return {"ok": True, "removed": before - len(_mem)}
