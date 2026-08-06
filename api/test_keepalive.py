# test_keepalive.py — Supabase 自動一時停止の防止（keep-alive）のテスト

from fastapi.testclient import TestClient

import config
import keepalive
from main import app

client = TestClient(app)


class FakeTable:
    """upsert/select を記録する最小のフェイク（成否を切り替えられる）。"""

    def __init__(self, log, fail_upsert=False, fail_tables=()):
        self.log = log
        self.fail_upsert = fail_upsert
        self.fail_tables = fail_tables
        self.name = ""

    def __call__(self, name):
        self.name = name
        return self

    def upsert(self, row):
        if self.fail_upsert or self.name in self.fail_tables:
            raise RuntimeError("no such table")
        self.log.append(("upsert", self.name, row))
        return self

    def select(self, *_a, **_k):
        if self.name in self.fail_tables:
            raise RuntimeError("no such table")
        return self

    def limit(self, _n):
        return self

    def execute(self):
        self.log.append(("execute", self.name))
        return type("R", (), {"data": []})()


class FakeClient:
    def __init__(self, log, fail_upsert=False, fail_tables=()):
        self._t = FakeTable(log, fail_upsert, fail_tables)

    def table(self, name):
        return self._t(name)


def test_ping_upserts_keepalive_row(monkeypatch):
    log = []
    monkeypatch.setattr(config, "get_supabase", lambda: FakeClient(log))
    monkeypatch.setattr(keepalive, "_touch_via_postgres", lambda: None)
    res = keepalive.ping()
    assert res["ok"] is True
    assert "keepalive" in res["detail"]
    assert any(op == "upsert" and t == "keepalive" for op, t, *_ in log)


def test_ping_falls_back_to_select(monkeypatch):
    """keepalive テーブルが無い環境でも SELECT で活動を作れる。"""
    log = []
    monkeypatch.setattr(config, "get_supabase",
                        lambda: FakeClient(log, fail_upsert=True, fail_tables=("keepalive",)))
    monkeypatch.setattr(keepalive, "_touch_via_postgres", lambda: None)
    res = keepalive.ping()
    assert res["ok"] is True and "SELECT" in res["detail"]
    assert any(op == "execute" for op, *_ in log)


def test_ping_without_supabase_is_graceful(monkeypatch):
    monkeypatch.setattr(config, "get_supabase", lambda: None)
    monkeypatch.setattr(keepalive, "_touch_via_postgres", lambda: None)
    res = keepalive.ping()
    assert res["ok"] is False and "Supabase未設定" in res["detail"]


def test_ping_includes_postgres_method(monkeypatch):
    monkeypatch.setattr(config, "get_supabase", lambda: None)
    monkeypatch.setattr(keepalive, "_touch_via_postgres", lambda: "Postgres 直結で SELECT 1")
    res = keepalive.ping()
    assert res["ok"] is True and "Postgres" in res["detail"]


def test_status_reports_last_run(monkeypatch):
    monkeypatch.setattr(config, "get_supabase", lambda: None)
    monkeypatch.setattr(keepalive, "_touch_via_postgres", lambda: "Postgres 直結で SELECT 1")
    keepalive.ping()
    st = keepalive.status()
    assert st["last_ok"] is True and st["last_at"]
    assert "supabase_configured" in st and "db_url_set" in st


def test_keepalive_endpoint_is_open(monkeypatch):
    """外部cronから叩けるよう認証不要で、常に200を返す。"""
    monkeypatch.setattr(config, "get_supabase", lambda: None)
    monkeypatch.setattr(keepalive, "_touch_via_postgres", lambda: None)
    r = client.get("/keepalive")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body and "detail" in body


def test_keepalive_status_endpoint():
    r = client.get("/keepalive/status")
    assert r.status_code == 200 and "last_ok" in r.json()
