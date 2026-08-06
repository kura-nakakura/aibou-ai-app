# keepalive.py — Supabase 無料枠の「7日間アクセスなしで自動一時停止」を防ぐ
# =====================================================================
# 定期的に DB を軽く触って「活動あり」と認識させる。
#   1) keepalive テーブルへ upsert（確実な書き込み活動）
#   2) 失敗したら既知テーブルへ SELECT（読み取りでも活動になる）
#   3) SUPABASE_DB_URL があれば Postgres 直結でも SELECT 1
#
# 呼び出し口は3系統（どれでも良い・冗長化）:
#   * アプリ内の常駐ループ（1日1回・サーバーが起きている間）
#   * GET /keepalive （外部cron / GitHub Actions から。認証不要）
#   * Settings の「今すぐ実行」ボタン
# 設計方針は他モジュールと統一：設定が欠けても絶対に crash しない。
# =====================================================================

from datetime import datetime, timezone
from typing import Optional

import config

# 読み取りフォールバックに使う既知テーブル（存在するものが1つあれば十分）。
_FALLBACK_TABLES = ("keepalive", "api_keys", "tasks", "agent_memory", "vault_data")

_last: dict = {"at": "", "ok": False, "detail": "まだ実行されていません"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _touch_via_rest() -> Optional[str]:
    """Supabase(PostgREST)経由でDBを触る。成功したら手段の説明を返す。"""
    c = config.get_supabase()
    if not c:
        return None
    # 1) 書き込み（最も確実な「活動」）
    try:
        c.table("keepalive").upsert({"id": 1, "last_ping": _now_iso()}).execute()
        return "keepalive テーブルへ upsert"
    except Exception:
        pass
    # 2) 読み取りフォールバック
    for t in _FALLBACK_TABLES:
        try:
            c.table(t).select("*").limit(1).execute()
            return f"{t} テーブルへ SELECT"
        except Exception:
            continue
    return None


def _touch_via_postgres() -> Optional[str]:
    """SUPABASE_DB_URL があれば Postgres 直結で SELECT 1（冗長化）。"""
    try:
        import migrate
        url = migrate.db_url()
    except Exception:
        return None
    if not url:
        return None
    try:
        import psycopg2
        conn = psycopg2.connect(url, connect_timeout=15)
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        conn.close()
        return "Postgres 直結で SELECT 1"
    except Exception:
        return None


def ping() -> dict:
    """DBを1回触る。{ok, at, detail, methods}。絶対に raise しない。"""
    methods = []
    rest = _touch_via_rest()
    if rest:
        methods.append(rest)
    pg = _touch_via_postgres()
    if pg:
        methods.append(pg)

    ok = bool(methods)
    detail = ("・".join(methods) if ok
              else "Supabase未設定のため何もしていません（SUPABASE_URL / SUPABASE_SERVICE_KEY を設定してください）")
    _last.update({"at": _now_iso(), "ok": ok, "detail": detail})
    return {"ok": ok, "at": _last["at"], "detail": detail, "methods": methods}


def status() -> dict:
    """最後の実行結果と設定状況を返す（UI表示用）。"""
    configured = False
    try:
        configured = config.get_supabase() is not None
    except Exception:
        configured = False
    db_url_set = False
    try:
        import migrate
        db_url_set = bool(migrate.db_url())
    except Exception:
        pass
    return {
        "supabase_configured": configured,
        "db_url_set": db_url_set,
        "last_at": _last["at"],
        "last_ok": _last["ok"],
        "last_detail": _last["detail"],
    }
