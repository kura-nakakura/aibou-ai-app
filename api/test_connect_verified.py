# test_connect_verified.py — 「接続しました」が、本当に保存できる状態か
#
# 調べて分かった、いちばん静かな事故:
#   Supabaseは繋がっている。でも表（テーブル）が無い。
#   各モジュールは insert の例外を握ってメモリへ退避し、成功として返す。
#   画面には「保存しました」と出て、再起動で消える。
#   SQLを流し忘れた人は必ずここに落ちるが、どこにも警告が出なかった。
#
# 繋いだ時点で、表を作り、実際に1行書いて消して確かめる。
# 書けないなら「接続しました」で終わらせず、何をすればいいかまで返す。

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tenancy


class Boom(Exception):
    pass


def _client(*, insert_error: str = "", delete_error: str = ""):
    """書き込みの成否だけを決められる、最小の偽クライアント。"""
    log = {"inserted": [], "deleted": []}

    class Table:
        def insert(self, row):
            if insert_error:
                raise Boom(insert_error)
            log["inserted"].append(row)
            return self

        def delete(self):
            if delete_error:
                raise Boom(delete_error)
            return self

        def eq(self, col, val):
            log["deleted"].append(val)
            return self

        def execute(self):
            return type("R", (), {"data": []})()

    class Client:
        log = None
        def table(self, name):
            assert name == "tasks"
            return Table()

    c = Client()
    c.log = log
    return c


# ── 書けるかを、実際に書いて確かめる ─────────────────────────────
def test_a_working_database_passes():
    c = _client()
    assert tenancy.verify_writable(c) == {"ok": True}
    assert len(c.log["inserted"]) == 1
    assert c.log["inserted"][0]["title"] == "接続確認"


def test_the_probe_row_is_cleaned_up():
    """確認用の行を残すと、利用者のタスク一覧に見慣れないものが増える。"""
    c = _client()
    tenancy.verify_writable(c)
    assert c.log["deleted"] == [c.log["inserted"][0]["id"]]
    assert c.log["inserted"][0]["id"].startswith("aibou-probe-")


def test_missing_tables_are_reported_as_such():
    """ここが本題。SQLを流し忘れた状態を、繋がったと言わない。"""
    r = tenancy.verify_writable(_client(insert_error='relation "tasks" does not exist'))
    assert r["ok"] is False
    assert r["reason"] == "tables_missing"


@pytest.mark.parametrize("msg", [
    "PGRST205: Could not find the table",
    "42P01 undefined_table",
])
def test_other_ways_supabase_says_the_table_is_missing(msg):
    assert tenancy.verify_writable(_client(insert_error=msg))["reason"] == "tables_missing"


def test_a_read_only_key_is_reported_differently():
    """anonキーで繋いだ人は、表があっても書けない。原因が違うので分けて言う。"""
    r = tenancy.verify_writable(_client(insert_error="new row violates row-level security policy"))
    assert r["ok"] is False
    assert r["reason"] == "write_failed"
    assert "row-level security" in r["detail"]


def test_failing_to_clean_up_does_not_fail_the_check():
    """消せなくても、書けたことは確かめられている。そこで落とさない。"""
    assert tenancy.verify_writable(_client(delete_error="no delete permission"))["ok"] is True


# ── 接続の返事 ───────────────────────────────────────────────────
@pytest.fixture
def clean():
    tenancy._mem_rows.clear()
    tenancy._clients.clear()
    yield
    tenancy._mem_rows.clear()
    tenancy._clients.clear()


def test_connect_says_writable_when_it_is(clean, monkeypatch):
    monkeypatch.setattr(tenancy, "check", lambda u, k: {"ok": True, "tables_ready": True})
    monkeypatch.setattr(tenancy, "client_for", lambda uid: _client())

    r = tenancy.connect("u1", "https://mine.supabase.co", "k" * 50)
    assert r["ok"] is True
    assert r["writable"] is True
    assert "warning" not in r


def test_connect_warns_when_the_tables_are_missing(clean, monkeypatch):
    """繋がっただけで終わらせない。ここを黙ると、保存したのに消える。"""
    monkeypatch.setattr(tenancy, "check", lambda u, k: {"ok": True, "tables_ready": False})
    monkeypatch.setattr(tenancy, "client_for",
                        lambda uid: _client(insert_error='relation "tasks" does not exist'))

    r = tenancy.connect("u1", "https://mine.supabase.co", "k" * 50)
    assert r["writable"] is False
    assert "保存されません" in r["warning"]
    # DB接続URLが無い人には、それを入れれば自動で作れると伝える
    assert "DB接続URL" in r["warning"]


def test_connect_tries_to_create_the_tables_when_it_can(clean, monkeypatch):
    """DB接続URLがあるなら、利用者にSQLを流させず、ここで作る。"""
    monkeypatch.setattr(tenancy, "check", lambda u, k: {"ok": True, "tables_ready": False})
    made = {"ran": False}

    def fake_create(uid):
        made["ran"] = True
        return {"ok": True, "tables": 26}

    monkeypatch.setattr(tenancy, "create_tables", fake_create)
    monkeypatch.setattr(tenancy, "client_for", lambda uid: _client())

    r = tenancy.connect("u1", "https://mine.supabase.co", "k" * 50,
                        db_url="postgresql://postgres:x@db/postgres")
    assert made["ran"] is True
    assert r["writable"] is True
    assert "warning" not in r


def test_a_failed_migration_is_reported_not_hidden(clean, monkeypatch):
    monkeypatch.setattr(tenancy, "check", lambda u, k: {"ok": True, "tables_ready": False})
    monkeypatch.setattr(tenancy, "create_tables",
                        lambda uid: {"error": "could not connect to server"})
    monkeypatch.setattr(tenancy, "client_for",
                        lambda uid: _client(insert_error='relation "tasks" does not exist'))

    r = tenancy.connect("u1", "https://mine.supabase.co", "k" * 50,
                        db_url="postgresql://postgres:x@db/postgres")
    assert r["migrate_error"]
    assert "SQL Editor" in r["warning"]     # 手でやる道も示す


def test_a_bad_connection_is_still_refused_before_all_this(clean, monkeypatch):
    monkeypatch.setattr(tenancy, "check", lambda u, k: {"error": "service key が正しくないようです"})
    r = tenancy.connect("u1", "https://mine.supabase.co", "k" * 50)
    assert "error" in r
    assert "ok" not in r
