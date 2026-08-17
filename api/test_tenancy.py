# test_tenancy.py — 利用者ごとの「自分のSupabase」接続の検証
#
# ここが壊れると、他人のデータが見える／自分のデータが消えるという一番重い
# 事故になる。確かめたいのは
#   ・リクエストごとに保存先が正しく差し替わること
#   ・未接続の人のデータが、管理者の共有DBへ黙って書かれないこと
#   ・service key が API から出ていかないこと（マスクのみ）
#   ・繋がらない接続を保存してしまわないこと

import jwt as pyjwt
from fastapi.testclient import TestClient

import config
import tenancy
from main import app

client = TestClient(app)
SECRET = "test-jwt-secret-for-tenancy"


def _token(sub: str) -> str:
    return pyjwt.encode({"sub": sub, "aud": "authenticated"}, SECRET, algorithm="HS256")


def _auth(sub: str) -> dict:
    return {"Authorization": f"Bearer {_token(sub)}"}


def _reset():
    tenancy._mem_rows.clear()
    tenancy._clients.clear()


# ── 保存先の差し替え ───────────────────────────────────────────────
def test_binding_swaps_where_everything_is_stored():
    """全モジュールが get_supabase() 越しなので、ここが差し替われば全部変わる。"""
    class FakeClient:
        pass

    mine = FakeClient()
    token = config.bind_request_client(mine)
    try:
        assert config.get_supabase() is mine
    finally:
        config.reset_request_client(token)


def test_unconnected_user_writes_nowhere_not_to_the_shared_db(monkeypatch):
    """未接続なら None を束縛する。共有DBへ黙って書かないことが要件。"""
    # 管理者のSupabaseが有るように見せかけても、未接続の人には渡さない
    monkeypatch.setattr(config, "_supabase_client", object(), raising=False)
    token = config.bind_request_client(None)
    try:
        assert config.get_supabase() is None
    finally:
        config.reset_request_client(token)


def test_binding_is_undone_after_the_request():
    before = config.get_supabase()
    token = config.bind_request_client(object())
    config.reset_request_client(token)
    assert config.get_supabase() is before


# ── 接続の検証 ─────────────────────────────────────────────────────
def test_check_rejects_obviously_wrong_input():
    assert tenancy.check("", "k").get("error")
    assert tenancy.check("https://x.supabase.co", "").get("error")
    assert "形式" in tenancy.check("ftp://nope", "k" * 50).get("error", "")
    assert "短すぎ" in tenancy.check("https://abc.supabase.co", "short").get("error", "")


def test_check_reports_a_reachable_project_without_tables(monkeypatch):
    """テーブルがまだ無いのは「失敗」ではなく「次の手順がある」状態。"""
    class T:
        def select(self, *_a, **_k): return self
        def limit(self, *_a, **_k): return self
        def execute(self): raise Exception('relation "api_keys" does not exist')

    class C:
        def table(self, *_a, **_k): return T()

    monkeypatch.setattr(tenancy, "create_client", lambda *a, **k: C(), raising=False)
    import supabase as sb
    monkeypatch.setattr(sb, "create_client", lambda *a, **k: C())
    res = tenancy.check("https://abc.supabase.co", "k" * 60)
    assert res["ok"] is True and res["tables_ready"] is False


def test_check_explains_a_bad_service_key(monkeypatch):
    class T:
        def select(self, *_a, **_k): return self
        def limit(self, *_a, **_k): return self
        def execute(self): raise Exception("Invalid API key")

    class C:
        def table(self, *_a, **_k): return T()

    import supabase as sb
    monkeypatch.setattr(sb, "create_client", lambda *a, **k: C())
    assert "service key" in tenancy.check("https://abc.supabase.co", "k" * 60).get("error", "")


# ── 台帳 ───────────────────────────────────────────────────────────
def test_connect_stores_and_status_never_leaks_the_key(monkeypatch):
    _reset()
    monkeypatch.setattr(tenancy, "check", lambda u, k: {"ok": True, "tables_ready": True})
    secret = "service-role-key-" + "x" * 50
    res = tenancy.connect("user-1", "https://abc.supabase.co", secret, "postgresql://db", "私のDB")
    assert res["ok"]

    st = tenancy.status("user-1")
    assert st["connected"] is True
    assert st["url"] == "https://abc.supabase.co"
    assert st["db_url_set"] is True
    assert st["label"] == "私のDB"
    # 生の鍵が状態に混ざっていないこと
    assert secret not in repr(st)
    assert st["masked_key"] and "•" in st["masked_key"]


def test_stored_key_is_encrypted_at_rest(monkeypatch):
    _reset()
    monkeypatch.setattr(tenancy, "check", lambda u, k: {"ok": True})
    monkeypatch.setattr(config, "KEYCHAIN_SECRET", "unit-test-secret", raising=False)
    secret = "service-role-" + "y" * 50
    tenancy.connect("user-2", "https://abc.supabase.co", secret)
    row = tenancy._mem_rows["user-2"]
    assert row["service_key"].startswith("enc:v1:")
    assert secret not in row["service_key"]
    # 復号すると元に戻る
    assert tenancy.credentials("user-2")[1] == secret


def test_a_failing_connection_is_not_saved(monkeypatch):
    _reset()
    monkeypatch.setattr(tenancy, "check", lambda u, k: {"error": "接続できませんでした"})
    assert tenancy.connect("user-3", "https://abc.supabase.co", "k" * 60).get("error")
    assert tenancy.status("user-3")["connected"] is False


def test_users_do_not_see_each_others_connection(monkeypatch):
    _reset()
    monkeypatch.setattr(tenancy, "check", lambda u, k: {"ok": True})
    tenancy.connect("alice", "https://alice.supabase.co", "a" * 60)
    tenancy.connect("bob", "https://bob.supabase.co", "b" * 60)
    assert tenancy.status("alice")["url"] == "https://alice.supabase.co"
    assert tenancy.status("bob")["url"] == "https://bob.supabase.co"
    assert tenancy.credentials("alice")[1] != tenancy.credentials("bob")[1]


def test_disconnect_stops_using_that_database(monkeypatch):
    _reset()
    monkeypatch.setattr(tenancy, "check", lambda u, k: {"ok": True})
    tenancy.connect("user-4", "https://abc.supabase.co", "k" * 60)
    tenancy.disconnect("user-4")
    assert tenancy.status("user-4")["connected"] is False
    assert tenancy.client_for("user-4") is None


def test_create_tables_needs_the_db_url(monkeypatch):
    _reset()
    monkeypatch.setattr(tenancy, "check", lambda u, k: {"ok": True})
    tenancy.connect("user-5", "https://abc.supabase.co", "k" * 60)     # db_url なし
    assert "DB接続URL" in tenancy.create_tables("user-5").get("error", "")


def test_create_tables_does_not_leak_the_db_url_into_the_environment(monkeypatch):
    """一時的に環境変数へ差し込むが、終わったら必ず元に戻すこと。"""
    _reset()
    monkeypatch.setattr(tenancy, "check", lambda u, k: {"ok": True})
    tenancy.connect("user-6", "https://abc.supabase.co", "k" * 60, "postgresql://secret-db")
    import migrate
    monkeypatch.setattr(migrate, "run_migrations", lambda: {"ok": True})
    import os
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    tenancy.create_tables("user-6")
    assert os.environ.get("SUPABASE_DB_URL") is None


# ── HTTP経路 ───────────────────────────────────────────────────────
def test_endpoint_requires_login(monkeypatch):
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", "", raising=False)
    r = client.get("/account/database")
    assert r.status_code == 200 and r.json()["available"] is False


def test_endpoints_work_for_a_logged_in_user(monkeypatch):
    _reset()
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", SECRET, raising=False)
    monkeypatch.setattr(tenancy, "check", lambda u, k: {"ok": True, "tables_ready": False})

    st = client.get("/account/database", headers=_auth("u-http")).json()
    assert st["available"] is True and st["connected"] is False

    body = {"url": "https://mine.supabase.co", "service_key": "k" * 60, "db_url": "", "label": "自分"}
    r = client.post("/account/database", json=body, headers=_auth("u-http"))
    assert r.status_code == 200 and r.json()["connected"] is True
    assert "k" * 60 not in r.text          # 鍵が応答に出ていない

    st = client.get("/account/database", headers=_auth("u-http")).json()
    assert st["url"] == "https://mine.supabase.co"

    assert client.request("DELETE", "/account/database", headers=_auth("u-http")).status_code == 200
    assert client.get("/account/database", headers=_auth("u-http")).json()["connected"] is False


def test_connect_endpoint_rejects_a_bad_connection(monkeypatch):
    _reset()
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", SECRET, raising=False)
    monkeypatch.setattr(tenancy, "check", lambda u, k: {"error": "service key が正しくないようです"})
    r = client.post("/account/database",
                    json={"url": "https://mine.supabase.co", "service_key": "k" * 60},
                    headers=_auth("u-bad"))
    assert r.status_code == 400 and "service key" in r.json()["error"]
