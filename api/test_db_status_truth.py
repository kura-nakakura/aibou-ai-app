# test_db_status_truth.py — 「どこに保存されているか」の表示が、実際の保存先と一致するか
#
# 画面は /account/database の返事をそのまま信じて文言を出す。だから、この
# 返事が保存の実装（use_own_database）とズレると、そのままユーザーへの嘘になる。
#
# 実際に踏んだ: 持ち主は個人接続が無くてもサーバーの既定DBに保存され続けるのに、
# この入口だけ connected=False としか返さず、画面が
# 「どこにも保存されていません。アプリを再起動すると消えます」と表示した。
# データは無事だったのに、消えたと思わせた。

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import tenancy
from main import app

client = TestClient(app)
SECRET = "test-jwt-secret-for-db-status"


def token_for(sub: str, email: str) -> str:
    import jwt as pyjwt
    return pyjwt.encode(
        {"sub": sub, "email": email, "aud": "authenticated", "exp": 9999999999},
        SECRET, algorithm="HS256",
    )


@pytest.fixture
def configured(monkeypatch):
    """人に配るときの構成。持ち主が決まっていて、既定DBがある。"""
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(config, "OWNER_EMAIL", "boss@example.com")
    monkeypatch.setattr(config, "OWNER_USER_ID", "")
    monkeypatch.setattr(config, "SUPABASE_URL", "https://server.supabase.co")
    monkeypatch.setattr(config, "REQUIRE_AUTH", False)
    monkeypatch.setattr(config, "APP_TOKEN", "")
    tenancy._mem_rows.clear()
    tenancy._clients.clear()
    yield
    tenancy._mem_rows.clear()
    tenancy._clients.clear()


def _status(token: str) -> dict:
    r = client.get("/account/database", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    return r.json()


def test_owner_without_a_personal_db_is_told_their_data_is_stored(configured):
    """持ち主は既定DBに保存されている。「保存されていない」と言ってはいけない。"""
    body = _status(token_for("owner-1", "boss@example.com"))
    assert body["available"] is True
    assert body["connected"] is False          # 個人接続はしていない（事実）
    assert body["using_server_db"] is True     # でも保存はされている（事実）


def test_other_users_without_a_personal_db_are_not_told_that(configured):
    """他の人は本当にどこにも保存されない。ここで True を返すと逆の嘘になる。"""
    body = _status(token_for("member-1", "member@example.com"))
    assert body["connected"] is False
    assert body["using_server_db"] is False


def test_status_matches_where_writes_actually_go(configured):
    """表示と実装のズレそのものを見張る。

    use_own_database は「持ち主 かつ 個人接続なし」のときだけ既定DBに残す。
    /account/database の using_server_db は、それと同じ条件でなければならない。
    """
    import main

    for sub, email in [("owner-1", "boss@example.com"), ("member-1", "member@example.com")]:
        claims = {"sub": sub, "email": email}
        stays_on_server_db = (
            tenancy.client_for(sub) is None and main.is_owner_claims(claims)
        )
        assert _status(token_for(sub, email))["using_server_db"] is stays_on_server_db


def test_owner_with_their_own_db_is_connected_not_fallback(configured, monkeypatch):
    """自分のDBを繋いだ持ち主は「接続済み」。既定DBの話は出さない。"""
    monkeypatch.setattr(tenancy, "check", lambda u, k: {"ok": True, "tables_ready": True})
    tenancy.connect("owner-1", "https://mine.supabase.co", "k" * 50)

    body = _status(token_for("owner-1", "boss@example.com"))
    assert body["connected"] is True
    assert body["using_server_db"] is False
    assert body["url"] == "https://mine.supabase.co"


def test_the_service_key_never_comes_back(configured, monkeypatch):
    """文言を直したついでに鍵が漏れていないか（この入口の本来の約束）。"""
    monkeypatch.setattr(tenancy, "check", lambda u, k: {"ok": True, "tables_ready": True})
    secret = "s" * 50
    tenancy.connect("owner-1", "https://mine.supabase.co", secret)

    raw = client.get("/account/database",
                     headers={"Authorization": f"Bearer {token_for('owner-1', 'boss@example.com')}"}).text
    assert secret not in raw


def test_no_default_db_means_no_false_reassurance(configured, monkeypatch):
    """既定DBが無い構成なら、持ち主にも「保存されている」と言わない。"""
    monkeypatch.setattr(config, "SUPABASE_URL", "")
    body = _status(token_for("owner-1", "boss@example.com"))
    assert body["using_server_db"] is False
