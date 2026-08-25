"""
api/keychain.py — APIキー保管庫（認証コード付きの「鍵束」のサーバー側）。

各種APIキー（Gemini / LINE Notify / 画像生成 / YouTube 等）をサーバーに保管する。
Supabase テーブル `api_keys` を使い、未設定ならプロセス内メモリにフォールバックする
（外部サービスが無くても絶対に crash しない）。

セキュリティ方針:
  * フルの値は決して API から返さない（list は必ずマスクして返す）。
  * Supabase に保存する値は **サーバー側で Fernet(AES128-CBC + HMAC) 暗号化**してから
    書き込む。DB には暗号文（`enc:v1:...`）だけが残り、平文は保存されない。
  * 復号はサーバー内部（利用時）でのみ行う。
  * **鍵はその人のもの**。保存も読み出しも、その人のDBとその人のクライアント
    の中で完結させる。利用者の操作でプロセス共有の場所（os.environ など）を
    書き換えない。書き換えると、その鍵が他の利用者のリクエストでも使われる。
  * サーバー側だけが決めてよい設定（SERVER_ONLY）は、利用者のDBの値では
    上書きさせない。暗号鍵や管理用DBの差し替えに繋がるため。
  * 旧データ（平文で保存済み）も読めるよう後方互換。次回保存時に暗号化へ移行する。
"""

import base64
import hashlib
import os
import time
from typing import Dict, List, Optional

import config
import memstore

# ── 暗号化（Fernet, マスターシークレットから鍵導出） ──────────────
_ENC_PREFIX = "enc:v1:"
_fernet_cache = None
_fernet_tried = False


def _get_fernet():
    """Fernet インスタンスを返す（1度だけ生成）。シークレットが無ければ None。"""
    global _fernet_cache, _fernet_tried
    if _fernet_cache is not None or _fernet_tried:
        return _fernet_cache
    _fernet_tried = True
    secret = (
        getattr(config, "KEYCHAIN_SECRET", "")
        or config.SUPABASE_SERVICE_KEY
        or config.APP_TOKEN
    )
    if not secret:
        return None
    try:
        from cryptography.fernet import Fernet
        # 任意長のシークレット → SHA-256 → base64url でFernet鍵(32byte)に整形
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
        _fernet_cache = Fernet(key)
    except Exception:
        _fernet_cache = None
    return _fernet_cache


def _encrypt(value: str) -> str:
    """保存用に暗号化する。暗号化不能な環境では平文のまま返す（メモリ運用想定）。"""
    if not value:
        return value
    f = _get_fernet()
    if not f:
        return value
    try:
        return _ENC_PREFIX + f.encrypt(value.encode("utf-8")).decode("ascii")
    except Exception:
        return value


def _decrypt(stored: Optional[str]) -> str:
    """保存値を復号する。平文（旧データ）はそのまま返す。復号失敗時は空。"""
    s = (stored or "").strip()
    if not s:
        return ""
    if not s.startswith(_ENC_PREFIX):
        return s  # 後方互換：平文で保存された旧データ
    f = _get_fernet()
    if not f:
        return ""
    try:
        return f.decrypt(s[len(_ENC_PREFIX):].encode("ascii")).decode("utf-8")
    except Exception:
        return ""

# UI にプリセット表示する「よく使うキー」。任意の名前も保存できる。
KNOWN_KEYS: List[Dict[str, str]] = [
    {"name": "GEMINI_API_KEY", "label": "Gemini API Key", "hint": "チャット・生成の頭脳（必須）"},
    {"name": "GITHUB_TOKEN", "label": "GitHub Token", "hint": "CODEモードのリポジトリ連携（Fine-grained PAT）"},
    {"name": "HUGGINGFACE_TOKEN", "label": "HuggingFace Token", "hint": "無料の代替AI（学習されない相談向け）。hf_で始まるトークン"},
    {"name": "X_API_KEY", "label": "X API Key", "hint": "Xへの投稿（OAuth 1.0a）"},
    {"name": "X_API_SECRET", "label": "X API Secret", "hint": "Xへの投稿（OAuth 1.0a）"},
    {"name": "X_ACCESS_TOKEN", "label": "X Access Token", "hint": "Xへの投稿（OAuth 1.0a）"},
    {"name": "X_ACCESS_SECRET", "label": "X Access Token Secret", "hint": "Xへの投稿（OAuth 1.0a）"},
    {"name": "X_ALLOW_AUTOPOST", "label": "Xへの自動投稿を許可",
     "hint": "1で有効。既定OFF（自動実行からの投稿を止める）"},
    {"name": "LINE_CHANNEL_TOKEN", "label": "LINE チャネルアクセストークン",
     "hint": "LINE公式アカウントから通知を送る（Messaging API）"},
    {"name": "LINE_TO_USER_ID", "label": "LINE 宛先ユーザーID",
     "hint": "空なら友だち全員へ。1人で使うなら空でよい"},
    {"name": "LINE_NOTIFY_TOKEN", "label": "LINE Notify Token（終了済み）",
     "hint": "2025年3月末でサービス終了。LINE_CHANNEL_TOKEN に移行してください"},
    {"name": "DISCORD_WEBHOOK", "label": "Discord Webhook", "hint": "ジョブ結果の通知"},
    {"name": "SLACK_WEBHOOK", "label": "Slack Webhook", "hint": "ジョブ結果の通知"},
    {"name": "OPENAI_API_KEY", "label": "OpenAI API Key", "hint": "代替の生成エンジン（任意）"},
    {"name": "NOTION_TOKEN", "label": "Notion Token", "hint": "エージェントがメモを追記（内部インテグレーション）"},
    {"name": "NOTION_PARENT_ID", "label": "Notion 追記先ID", "hint": "メモを追加するページ or データベースのID"},
    {"name": "LEONARDO_API_KEY", "label": "Leonardo.ai Key", "hint": "高品質画像生成（任意）"},
    {"name": "YOUTUBE_API_KEY", "label": "YouTube Data API", "hint": "動画自動投稿（任意）"},
    {"name": "NOTE_TOKEN", "label": "note Token", "hint": "記事自動下書き（任意）"},
    {"name": "SHUTTERSTOCK_FTP", "label": "Shutterstock FTP", "hint": "素材自動アップロード（任意）"},
    {"name": "SUPABASE_URL", "label": "Supabase URL", "hint": "永続ストレージ（任意）"},
    {"name": "SUPABASE_SERVICE_KEY", "label": "Supabase Service Key", "hint": "永続ストレージ（任意）"},
    {"name": "SUPABASE_DB_URL", "label": "Supabase DB接続URL", "hint": "テーブル自動作成に使う postgresql://… 接続文字列"},
    {"name": "ALLOW_AI_STOCK_UPLOAD", "label": "AI画像のストック送信を許可", "hint": "1で有効。規約確認は利用者責任（既定OFF）"},
    {"name": "ALLOW_NOTE_AUTOPOST", "label": "noteへの自動投稿を許可", "hint": "1で有効。非公式APIのため規約リスクは利用者責任（既定OFF）"},
    {"name": "GOOGLE_CLIENT_ID", "label": "Google Client ID", "hint": "Google連携（スプレッドシート/ドキュメント/カレンダー）"},
    {"name": "GOOGLE_CLIENT_SECRET", "label": "Google Client Secret", "hint": "Google連携（OAuth）"},
    {"name": "EMAIL_ADDRESS", "label": "メールアドレス", "hint": "エージェントのメール送受信（Gmail等）"},
    {"name": "EMAIL_PASSWORD", "label": "メール アプリパスワード", "hint": "Gmailは2段階認証→アプリパスワード"},
]

# ── 鍵は「その人のもの」であること ────────────────────────────────────
# 利用者ごとに自分のSupabaseを繋ぐ方式にしたので、鍵もその人のDBに入る。
# ところが読み出し側がプロセス共有の辞書と os.environ を先に見ていたため、
# 先に誰かが使った鍵が、そのまま次の人にも使われてしまう状態だった
# （Aさんのキーの請求でBさんが動く／Aさんのメール・Notionに繋がる）。
#
# 直し方:
#   ・その人のDBから読んだ値は、その人のクライアントにだけぶら下げる
#   ・利用者の保存で os.environ を書き換えない（サーバー全体に漏れるため）
#   ・os.environ / プロセス内辞書は「管理者がサーバーに入れた共通の鍵」
#     としてだけ読む。自分の鍵があればそちらが優先。
#
# 誰のDBにも繋いでいないとき（自分用に立てた1人運用）は、これまで通り
# プロセス内辞書と環境変数で動く。
_mem_keys = memstore.TenantDict()   # その人のクライアントにぶら下げる、復号済みの鍵
_KEYS_NOTE = "_aibou_keys"

# サーバー側だけが決めてよい設定（利用者のDBの値で上書きさせない）。
# ここを上書きできると、暗号鍵の差し替えや管理用DBの乗っ取りに繋がる。
SERVER_ONLY = {
    "KEYCHAIN_SECRET", "SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SUPABASE_ANON_KEY",
    "SUPABASE_JWT_SECRET", "APP_TOKEN", "REQUIRE_AUTH", "OWNER_EMAIL", "OWNER_USER_ID",
}


def _tenant():
    """いま処理している利用者のDBクライアント。1人運用なら None 相当。"""
    try:
        return config.get_supabase()
    except Exception:
        return None


def _tenant_keys(client) -> Optional[Dict[str, str]]:
    """そのクライアントにぶら下がっている鍵の入れ物（無ければ作る）。"""
    if client is None:
        return None
    notes = getattr(client, _KEYS_NOTE, None)
    if notes is None:
        notes = {}
        try:
            setattr(client, _KEYS_NOTE, notes)
        except Exception:
            return None          # 付けられない実装なら覚えない（毎回DBを見る）
    return notes

# ── 「入っていない鍵」を覚えておくための短期メモ ──────────────────────
# 会話を1回始めるたびに llm.providers_in_order() が HUGGINGFACE_TOKEN と
# LLM_PROVIDER を見に来る。未設定だと毎回 Supabase まで問い合わせに行って
# 「無い」と分かるだけで終わり、その往復ぶん返事が遅れていた（しかも
# providers_in_order は1リクエストで2回呼ばれる）。
# 無かったことを短時間だけ覚えて、その間は問い合わせない。
#
# メモはクライアント自身にぶら下げる。共通の辞書にすると、鍵を入れている
# 人と入れていない人の判定が混ざる恐れがあるため。
_MISS_NOTE = "_aibou_key_misses"
_MISS_TTL = 30.0          # 秒。鍵を入れてから効くまでの待ち時間の上限


def _missing_recently(client, name: str) -> bool:
    notes = getattr(client, _MISS_NOTE, None)
    if not notes:
        return False
    until = notes.get(name)
    return bool(until and time.monotonic() < until)


def _note_missing(client, name: str) -> None:
    try:
        notes = getattr(client, _MISS_NOTE, None)
        if notes is None:
            notes = {}
            setattr(client, _MISS_NOTE, notes)
        notes[name] = time.monotonic() + _MISS_TTL
    except Exception:
        pass


def _clear_missing(name: str) -> None:
    """鍵を書き換えたら「無い」の記憶は捨てる（すぐ効くように）。"""
    try:
        c = config.get_supabase()
        notes = getattr(c, _MISS_NOTE, None) if c is not None else None
        if notes:
            notes.pop(name, None)
    except Exception:
        pass


def _mask(value: str) -> str:
    """値をマスクする（先頭2 + ●… + 末尾2）。空なら空文字。"""
    v = (value or "").strip()
    if not v:
        return ""
    if len(v) <= 4:
        return "•" * len(v)
    return v[:2] + "•" * min(8, max(4, len(v) - 4)) + v[-2:]


def set_key(name: str, value: str) -> dict:
    """鍵を保存する。保存先はその人のDB（繋いでいなければプロセス内）。

    重要: 利用者の保存で os.environ を書き換えない。書き換えると、その鍵が
    サーバー全体の既定値になり、他の利用者のリクエストでも使われてしまう。
    """
    name = (name or "").strip()
    value = (value or "").strip()
    if not name:
        return {"error": "name is required"}

    c = _tenant()
    notes = _tenant_keys(c)

    if notes is not None:
        # その人のDBに繋がっている → その人の場所にだけ入れる
        notes[name] = value
        _clear_missing(name)
        try:
            c.table("api_keys").upsert({"name": name, "value": _encrypt(value)}).execute()
        except Exception:
            pass
    else:
        # 誰のDBにも繋いでいない（1人運用）→ これまで通りプロセス内に持つ
        _mem_keys[name] = value
        os.environ[name] = value
        if name == "GEMINI_API_KEY":
            try:
                config.reconfigure_gemini(value)
            except Exception:
                pass

    return {"ok": True, "name": name, "masked": _mask(value), "set": bool(value), "encrypted": bool(_get_fernet())}


def get_key(name: str) -> str:
    """フルのキー値を返す（サーバー内部利用専用 / API では返さない）。

    探す順番:
      1. その人が保存した鍵（その人のDB）      ← 自分の鍵が最優先
      2. 管理者がサーバーに入れた共通の鍵（環境変数）
    1人運用（誰のDBにも繋いでいない）ときだけ、プロセス内の保存分も見る。
    """
    name = (name or "").strip()
    if not name:
        return ""

    # サーバーが決める設定は、利用者の値で上書きさせない
    if name in SERVER_ONLY:
        return os.environ.get(name, "").strip()

    c = _tenant()
    notes = _tenant_keys(c)

    if notes is not None:
        if name in notes:
            return notes[name]
        if not _missing_recently(c, name):
            try:
                rows = (c.table("api_keys").select("value").eq("name", name)
                        .limit(1).execute().data) or []
                if rows:
                    v = _decrypt(rows[0].get("value"))  # DBは暗号文 → ここで復号
                    if v:
                        notes[name] = v
                        return v
                _note_missing(c, name)
            except Exception:
                pass
    else:
        # 1人運用：プロセス内に保存した分
        if name in _mem_keys:
            return _mem_keys[name]

    # 管理者がサーバーに入れた共通の鍵（自分の鍵が無いときだけ使われる）
    return os.environ.get(name, "").strip()


def list_keys() -> List[dict]:
    """既知キー + 保存済みキーを「マスク値 + 設定有無」で返す（フル値は返さない）。"""
    labels = {k["name"]: k for k in KNOWN_KEYS}
    names: List[str] = [k["name"] for k in KNOWN_KEYS]

    c = _tenant()
    notes = _tenant_keys(c)

    # その人が保存した分（1人運用ならプロセス内の分）を追加
    for n in (notes if notes is not None else _mem_keys):
        if n not in names:
            names.append(n)

    # その人のDBに保存されている分を追加
    if c:
        try:
            rows = (c.table("api_keys").select("name").limit(1000).execute().data) or []
            for r in rows:
                n = (r.get("name") or "").strip()
                if n and n not in names:
                    names.append(n)
        except Exception:
            pass

    out: List[dict] = []
    for n in names:
        v = get_key(n)
        meta = labels.get(n, {})
        out.append({
            "name": n,
            "label": meta.get("label", n),
            "hint": meta.get("hint", ""),
            "masked": _mask(v),
            "set": bool(v),
        })
    return out


def delete_key(name: str) -> dict:
    """鍵を削除する。消せるのは自分の鍵だけ。

    管理者がサーバーに入れた共通の鍵（環境変数）は、利用者の操作では消さない。
    消してしまうと他の利用者ごと動かなくなるため。
    """
    name = (name or "").strip()
    if not name:
        return {"error": "name is required"}

    c = _tenant()
    notes = _tenant_keys(c)
    _clear_missing(name)

    if notes is not None:
        notes.pop(name, None)
        try:
            c.table("api_keys").delete().eq("name", name).execute()
        except Exception:
            pass
    else:
        # 1人運用：プロセス内と環境変数から消す
        _mem_keys.pop(name, None)
        try:
            if name in os.environ:
                del os.environ[name]
        except Exception:
            pass
        if name == "GEMINI_API_KEY":
            try:
                config.reconfigure_gemini("")
            except Exception:
                pass
    return {"ok": True}


# config は keychain を import できない（こちらが config を import しているため）。
# 起動時にここから登録して、config 側から「いまの人の鍵」を引けるようにする。
config.set_key_resolver(get_key)
