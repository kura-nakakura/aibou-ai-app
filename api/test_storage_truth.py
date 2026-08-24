# test_storage_truth.py — 「保存しました」が本当かどうか
#
# 利用者からの報告: 「ノートブック作ったのに消える」。
#
# 原因は、保存先が無い人の書き込みを各モジュールがプロセスのメモリへ
# 退避していたこと。画面には成功と出るのに、Renderが再起動すれば消える。
# 消えたことにも気づけないし、気づいても理由が分からない。
#
# 保存先が無いなら、その場で断って理由を出す。消えるより誠実。
# 読み取りには付けない（空で表示されるだけで害がない）。

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import tenancy
from main import app

client = TestClient(app)
SECRET = "test-jwt-secret-for-storage-truth"


def token_for(sub: str, email: str = "member@example.com") -> str:
    import jwt as pyjwt
    return pyjwt.encode(
        {"sub": sub, "email": email, "aud": "authenticated", "exp": 9999999999},
        SECRET, algorithm="HS256",
    )


def auth(sub: str, email: str = "member@example.com") -> dict:
    return {"Authorization": f"Bearer {token_for(sub, email)}"}


@pytest.fixture
def member_without_a_database(monkeypatch):
    """人に配ったときの、いちばん普通の状態。ログイン済み・自分のDBは未接続。"""
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", SECRET)
    monkeypatch.setattr(config, "OWNER_EMAIL", "boss@example.com")
    monkeypatch.setattr(config, "OWNER_USER_ID", "")
    monkeypatch.setattr(config, "APP_TOKEN", "")
    monkeypatch.setattr(config, "REQUIRE_AUTH", False)
    tenancy._mem_rows.clear()
    tenancy._clients.clear()
    yield
    tenancy._mem_rows.clear()
    tenancy._clients.clear()


# ── 保存できないなら、受け付けない ───────────────────────────────
WRITES = [
    ("post", "/vault/create", {"name": "社内規程"}),
    ("post", "/tasks", {"title": "見積を出す"}),
    ("post", "/agenda", {"title": "打ち合わせ", "date": "2026-09-01"}),
    ("post", "/life/entries", {"category": "work", "content": "転職した"}),
    ("post", "/automations", {"name": "毎朝の要約", "steps": []}),
    ("post", "/autopilot/missions", {"goal": "資料を作る"}),
    ("post", "/memory/add", {"text": "誕生日は5月"}),
]


@pytest.mark.parametrize("method,path,body", WRITES)
def test_saving_without_a_database_is_refused_not_faked(
    member_without_a_database, method, path, body,
):
    r = getattr(client, method)(path, json=body, headers=auth("member-1"))
    assert r.status_code == 409, f"{path} が {r.status_code} で通ってしまった"
    detail = r.json().get("detail", "")
    # 数字やコード名ではなく、次にやることが分かる日本語であること
    assert "保存先" in detail
    assert "Supabase" in detail
    assert "残りません" in detail


def test_owner_only_screens_are_refused_before_the_storage_check(member_without_a_database):
    """副業・自己進化は持ち主だけのもの。保存先の有無より先に、権限で断る。
    ここが409（保存先が無い）になると、繋げば使えると誤解させる。"""
    r = client.post("/studio/ais", json={"name": "営業メール係"}, headers=auth("member-1"))
    assert r.status_code == 403, r.status_code


def test_reading_still_works_and_returns_empty(member_without_a_database):
    """読み取りまで止めない。空で出るだけなら害がないし、
    画面が丸ごとエラーになるほうが分かりにくい。"""
    for path in ["/tasks", "/agenda", "/vault/notebooks", "/life/entries"]:
        r = client.get(path, headers=auth("member-1"))
        assert r.status_code == 200, f"{path} が {r.status_code}"


def test_a_member_with_their_own_database_can_save(member_without_a_database, monkeypatch):
    """自分のDBを繋いだ人は、当然そのまま保存できる。"""
    monkeypatch.setattr(tenancy, "check", lambda u, k: {"ok": True, "tables_ready": True})

    class FakeTable:
        def insert(self, row): self._row = row; return self
        def select(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def order(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def execute(self): return type("R", (), {"data": [{"id": "nb-1", "name": "社内規程"}]})()

    class FakeClient:
        def table(self, name): return FakeTable()

    tenancy.connect("member-1", "https://mine.supabase.co", "k" * 50)
    monkeypatch.setattr(tenancy, "client_for", lambda uid: FakeClient() if uid == "member-1" else None)

    r = client.post("/vault/create", json={"name": "社内規程"}, headers=auth("member-1"))
    assert r.status_code == 200, r.text


def test_the_owner_can_still_save_on_the_server_database(member_without_a_database, monkeypatch):
    """持ち主はサーバー既定のDBを使い続ける。ここを塞ぐと自分が閉め出される。"""
    monkeypatch.setattr(config, "_supabase_client", object(), raising=False)
    monkeypatch.setattr(config, "_supabase_tried", True, raising=False)

    # 保存先の判定だけを見る（実際の書き込みは他のテストの領分）
    r = client.post("/tasks", json={"title": "見積を出す"},
                    headers=auth("owner-1", "boss@example.com"))
    assert r.status_code != 409, "持ち主が保存先なし扱いになっている"


def test_single_user_setup_is_not_blocked(monkeypatch):
    """1人で使っている構成（ログイン無し）は、これまで通り動く。
    ここを塞ぐと、配る前の使い方まで壊れる。"""
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", "")
    monkeypatch.setattr(config, "APP_TOKEN", "")
    monkeypatch.setattr(config, "REQUIRE_AUTH", False)
    monkeypatch.setattr(config, "OWNER_EMAIL", "")
    monkeypatch.setattr(config, "OWNER_USER_ID", "")

    r = client.post("/tasks", json={"title": "見積を出す"})
    assert r.status_code != 409, "1人運用が保存先なしで止められている"


# ── 保存先の呼び名 ───────────────────────────────────────────────
def test_storage_state_names_where_things_go(monkeypatch):
    monkeypatch.setattr(config, "_supabase_client", None, raising=False)
    monkeypatch.setattr(config, "_supabase_tried", True, raising=False)
    assert config.storage_state() == "memory"

    token = config.bind_request_client(object())
    try:
        assert config.storage_state() == "personal"
    finally:
        config.reset_request_client(token)

    token = config.bind_request_client(None)
    try:
        assert config.storage_state() == "memory"   # 差し替え済みで中身なし
    finally:
        config.reset_request_client(token)

    monkeypatch.setattr(config, "_supabase_client", object(), raising=False)
    assert config.storage_state() == "server"
