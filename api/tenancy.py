# tenancy.py — 利用者ごとの「自分のSupabase」接続
# =====================================================================
# 役割の分け方
#   ・認証（ログイン）      … 管理者のSupabase（1つ）。誰がログインしたかだけを扱う
#   ・そのの人のデータ      … その人自身のSupabase。タスク・予定・ノート等はここへ
#
# 接続情報（URL / service key / DB接続文字列）は管理者のSupabaseの
# `user_connections` に、service key と DB接続文字列を Fernet で暗号化して
# 置く。復号はサーバー内部（利用時）だけで行い、APIは必ずマスクして返す。
#
# 未接続の人はどうなるか
#   保存しない（プロセス内メモリのみ）。管理者の共有DBへ黙って書き込むと、
#   利用者ごとに分ける目的そのものが壊れるため、そこは繋がない。
#   UI側で「自分のDBを接続してください」と出す。
#
# 方針（他モジュールと同じ）
#   ・絶対に raise しない。失敗は {"error": 日本語} で返す。
#   ・鍵の値は返さない（set かどうか＋マスクだけ）。
# =====================================================================

import base64
import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

import config

TABLE = "user_connections"
_ENC_PREFIX = "enc:v1:"

# 接続を作れた利用者のクライアントを使い回す（毎リクエスト作ると遅い）。
_clients: dict = {}
# 管理者DBが無い環境向けのメモリ台帳（開発・テスト用）。
_mem_rows: dict = {}

URL_RE = re.compile(r"^https://[A-Za-z0-9-]+\.supabase\.co/?$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fernet():
    """keychain と同じ導出（KEYCHAIN_SECRET → SHA256 → Fernet鍵）。"""
    secret = (getattr(config, "KEYCHAIN_SECRET", "") or config.SUPABASE_SERVICE_KEY
              or config.APP_TOKEN)
    if not secret:
        return None
    try:
        from cryptography.fernet import Fernet
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))
    except Exception:
        return None


def _encrypt(value: str) -> str:
    if not value:
        return ""
    f = _fernet()
    if not f:
        return value            # 暗号化できない環境（メモリ運用）はそのまま
    try:
        return _ENC_PREFIX + f.encrypt(value.encode()).decode("ascii")
    except Exception:
        return value


def _decrypt(stored: Optional[str]) -> str:
    s = (stored or "").strip()
    if not s:
        return ""
    if not s.startswith(_ENC_PREFIX):
        return s
    f = _fernet()
    if not f:
        return ""
    try:
        return f.decrypt(s[len(_ENC_PREFIX):].encode("ascii")).decode()
    except Exception:
        return ""


def mask(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    return v[:4] + "•" * min(10, max(4, len(v) - 8)) + v[-4:] if len(v) > 8 else "•" * len(v)


# ── 管理者DB（台帳の置き場） ───────────────────────────────────────
def _admin_client():
    """台帳を読む先。ここだけは必ず管理者のSupabaseを使う。

    get_supabase() はリクエスト中に差し替わるので、それを使うと
    「その人のDBの中に台帳を探す」ことになってしまう。素で作り直す。
    """
    if not (config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY):
        return None
    try:
        from supabase import create_client
        return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
    except Exception:
        return None


def _read_row(user_id: str) -> Optional[dict]:
    c = _admin_client()
    if c:
        try:
            rows = (c.table(TABLE).select("*").eq("user_id", user_id)
                    .limit(1).execute().data) or []
            if rows:
                return rows[0]
        except Exception:
            pass
    return _mem_rows.get(user_id)


def _write_row(row: dict) -> None:
    _mem_rows[row["user_id"]] = row
    c = _admin_client()
    if c:
        try:
            c.table(TABLE).upsert(row, on_conflict="user_id").execute()
        except Exception:
            pass


# ── 接続の検証 ─────────────────────────────────────────────────────
def check(url: str, service_key: str) -> dict:
    """本当に繋がるかを1回叩いて確かめる。{"ok":True} / {"error": 理由}。"""
    url = (url or "").strip().rstrip("/")
    key = (service_key or "").strip()
    if not url or not key:
        return {"error": "URL と service key の両方を入れてください"}
    if not URL_RE.match(url + "/"):
        return {"error": "URLの形式が違います（https://xxxx.supabase.co の形で入れてください）"}
    if len(key) < 40:
        return {"error": "service key が短すぎます。値を貼り間違えていないか確認してください"}
    try:
        from supabase import create_client
        c = create_client(url, key)
    except Exception as e:
        return {"error": f"接続を作れませんでした: {e}"}
    # 存在しなくてもよいテーブルを引いて、鍵とURLが有効かだけを見る。
    try:
        c.table("api_keys").select("name").limit(1).execute()
        return {"ok": True, "tables_ready": True}
    except Exception as e:
        msg = str(e)
        if "does not exist" in msg or "PGRST205" in msg or "42P01" in msg:
            # 繋がってはいるが、まだテーブルが無い状態（次の手順が案内できる）
            return {"ok": True, "tables_ready": False}
        if "Invalid API key" in msg or "JWT" in msg or "401" in msg:
            return {"error": "service key が正しくないようです（Settings → API → service_role）"}
        return {"error": f"接続できませんでした: {msg[:180]}"}


# ── 台帳の読み書き ─────────────────────────────────────────────────
def verify_writable(client) -> dict:
    """本当に書けるかを、実際に1行入れて消して確かめる。

    「繋がった」だけでは足りない。テーブルが無いDBに書くと、各モジュールは
    例外を握ってメモリへ退避し、成功として返してしまう。画面には保存できた
    ように見えて、再起動で消える。SQLを流し忘れた人が必ずここに落ちる。

    読めるかだけを見ても分からない（読めても書けないことがある）ので、
    実際に書いて、消す。
    """
    probe_id = f"aibou-probe-{uuid.uuid4()}"
    try:
        client.table("tasks").insert({
            "id": probe_id, "title": "接続確認", "content": "",
            "status": "pending", "created_at": _now(), "updated_at": _now(),
        }).execute()
    except Exception as e:
        msg = str(e)
        if "does not exist" in msg or "PGRST205" in msg or "42P01" in msg:
            return {"ok": False, "reason": "tables_missing"}
        return {"ok": False, "reason": "write_failed", "detail": msg[:180]}
    try:
        client.table("tasks").delete().eq("id", probe_id).execute()
    except Exception:
        pass          # 消せなくても書けたことは確かめられた
    return {"ok": True}


def connect(user_id: str, url: str, service_key: str, db_url: str = "", label: str = "") -> dict:
    """接続を確かめてから保存する。"""
    user_id = (user_id or "").strip()
    if not user_id:
        return {"error": "ログインしていないため保存できません"}
    res = check(url, service_key)
    if res.get("error"):
        return res
    row = {
        "user_id": user_id,
        "url": url.strip().rstrip("/"),
        "service_key": _encrypt(service_key.strip()),
        "db_url": _encrypt((db_url or "").strip()),
        "label": (label or "").strip()[:60],
        "verified_at": _now(),
        "created_at": _now(),
    }
    _write_row(row)
    _clients.pop(user_id, None)     # 作り直させる

    # ここから先が本題。繋がっただけでは保存できるとは限らない。
    # テーブルが無ければ作り、そのうえで本当に書けるかを確かめる。
    # ここを省くと、SQLを流し忘れた人が「保存したのに消える」に落ちる。
    made = None
    if not res.get("tables_ready") and db_url:
        try:
            made = create_tables(user_id)
        except Exception as e:
            made = {"error": str(e)[:180]}

    client = client_for(user_id)
    check_write = verify_writable(client) if client is not None else {"ok": False, "reason": "no_client"}

    out = {"ok": True, "tables_ready": bool(check_write.get("ok")), "writable": bool(check_write.get("ok"))}
    if made and made.get("error"):
        out["migrate_error"] = made["error"]
    if check_write.get("ok"):
        return out

    # 書けないまま「接続しました」で終わらせない。何をすればいいかまで返す。
    if check_write.get("reason") == "tables_missing":
        out["warning"] = (
            "接続はできましたが、まだ表（テーブル）がありません。このままでは保存されません。"
            + ("DB接続URL（postgresql://…）を入れると、ここで自動的に作れます。"
               if not db_url else
               "自動作成に失敗しました。Supabaseの SQL Editor で supabase_schema.sql を実行してください。")
        )
    elif check_write.get("reason") == "write_failed":
        out["warning"] = ("接続はできましたが、書き込みが拒否されました。"
                          f"service_role キーで繋いでいるか確認してください（{check_write.get('detail', '')}）")
    else:
        out["warning"] = "接続はできましたが、書き込みを確かめられませんでした。"
    return out


def disconnect(user_id: str) -> dict:
    """接続を外す（以後その人のデータは保存されない）。"""
    _mem_rows.pop(user_id, None)
    _clients.pop(user_id, None)
    c = _admin_client()
    if c:
        try:
            c.table(TABLE).delete().eq("user_id", user_id).execute()
        except Exception:
            pass
    return {"ok": True}


def all_connected_users() -> list:
    """自分のDBを繋いでいる人のIDを全部返す。

    定期実行のように「リクエストが無いところで動くもの」に要る。
    常駐ループはリクエスト文脈を持たないので、そのままだとサーバー既定のDBしか
    見えない。各自の予約は各自のDBにあるので、誰がいるかを知る必要がある。
    """
    c = _admin_client()
    if c:
        try:
            rows = (c.table(TABLE).select("user_id").execute().data) or []
            ids = [str(r.get("user_id") or "") for r in rows]
            return [i for i in ids if i]
        except Exception:
            pass
    return [k for k in _mem_rows.keys() if k]


def credentials(user_id: str) -> Tuple[str, str, str]:
    """(url, service_key, db_url) を復号して返す。サーバー内部専用。"""
    row = _read_row(user_id)
    if not row:
        return "", "", ""
    return (row.get("url") or "",
            _decrypt(row.get("service_key")),
            _decrypt(row.get("db_url")))


def client_for(user_id: str):
    """その人のSupabaseクライアント。未接続なら None。"""
    if not user_id:
        return None
    if user_id in _clients:
        return _clients[user_id]
    url, key, _db = credentials(user_id)
    if not (url and key):
        return None
    try:
        from supabase import create_client
        c = create_client(url, key)
    except Exception:
        c = None
    _clients[user_id] = c
    return c


def status(user_id: str) -> dict:
    """UI用の状態。鍵の値は返さない。"""
    row = _read_row(user_id)
    if not row:
        return {"connected": False, "url": "", "masked_key": "", "db_url_set": False,
                "label": "", "verified_at": None}
    key = _decrypt(row.get("service_key"))
    return {
        "connected": bool(row.get("url") and key),
        "url": row.get("url") or "",
        "masked_key": mask(key),
        "db_url_set": bool(_decrypt(row.get("db_url"))),
        "label": row.get("label") or "",
        "verified_at": row.get("verified_at"),
    }


def create_tables(user_id: str) -> dict:
    """その人のDBに必要なテーブルを作る（DB接続文字列が要る）。"""
    _url, _key, db_url = credentials(user_id)
    if not db_url:
        return {"error": "テーブル作成には DB接続URL（postgresql://…）が必要です。"
                         "Supabaseの Connect → Session pooler の文字列を入れてください"}
    import migrate
    # 誰のDBかを引数で渡す。
    # 以前は os.environ["SUPABASE_DB_URL"] を一時的に書き換えて渡していたが、
    # 環境変数はプロセス全体で1つしかない。ここは実行スレッドの上で動くので、
    # 差し替えている最中に別の人の要求が同じ変数を読むと、その人のテーブル作成が
    # こちらのDBに対して走る。渡す先を引数にすれば、そもそも混ざらない。
    return migrate.run_migrations(db_url)
