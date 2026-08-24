# test_conversations.py — 会話履歴が、その人のDBに残るか
#
# 調べて分かったこと: CHATの履歴はブラウザの localStorage にしか無かった。
# 端末を変えると全部消えるし、ブラウザのデータを消しても消える。
# 規約には「会話…はあなたのSupabaseに保存されます」と書いてあったので、
# そこだけ実装が追いついていなかった。
#
# いちばん使う画面の履歴が残らないのは、機能が半分しかないのと同じ。

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import conversations


@pytest.fixture(autouse=True)
def clean():
    conversations._mem.clear()
    yield
    conversations._mem.clear()


class FakeDB:
    """1テーブルぶんの、最小の偽Supabase。"""

    def __init__(self, fail: str = ""):
        self.rows = []
        self.fail = fail

    def table(self, name):
        assert name == "conversations"
        return _Q(self)


class _Q:
    def __init__(self, db):
        self.db, self._id, self._cols = db, None, None

    def select(self, cols="*"): self._cols = cols; return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def eq(self, col, val): self._id = val; return self

    def insert(self, row):
        if self.db.fail: raise RuntimeError(self.db.fail)
        self.db.rows.append(dict(row)); self._op = "insert"; return self

    def update(self, row):
        if self.db.fail: raise RuntimeError(self.db.fail)
        self._row = row; self._op = "update"; return self

    def delete(self): self._op = "delete"; return self

    def execute(self):
        op = getattr(self, "_op", "select")
        if op == "update":
            for r in self.db.rows:
                if r["id"] == self._id:
                    r.update(self._row)
            return type("R", (), {"data": []})()
        if op == "delete":
            self.db.rows[:] = [r for r in self.db.rows if r["id"] != self._id]
            return type("R", (), {"data": []})()
        rows = self.db.rows
        if self._id is not None:
            rows = [r for r in rows if r["id"] == self._id]
        if self._cols and self._cols != "*":
            keep = [c.strip() for c in self._cols.split(",")]
            rows = [{k: v for k, v in r.items() if k in keep} for r in rows]
        return type("R", (), {"data": list(rows)})()


def bind(db):
    return config.bind_request_client(db)


MSGS = [
    {"role": "user", "content": "来週の予定を教えて"},
    {"role": "assistant", "content": "月曜に打ち合わせがあります"},
]


# ── 保存して、読み戻せるか ───────────────────────────────────────
def test_a_conversation_survives_and_can_be_read_back():
    db = FakeDB()
    t = bind(db)
    try:
        r = conversations.save_conversation("", MSGS)
        assert r["ok"] is True
        got = conversations.get_conversation(r["id"])
        assert got["messages"] == MSGS
    finally:
        config.reset_request_client(t)


def test_saving_again_updates_instead_of_piling_up():
    """発言のたびに書き戻る。行が増え続けると一覧が壊れる。"""
    db = FakeDB()
    t = bind(db)
    try:
        r = conversations.save_conversation("", MSGS)
        conversations.save_conversation(r["id"], MSGS + [{"role": "user", "content": "ありがとう"}])
        assert len(db.rows) == 1
        assert len(conversations.get_conversation(r["id"])["messages"]) == 3
    finally:
        config.reset_request_client(t)


def test_the_list_does_not_carry_the_bodies():
    """一覧で本文まで返すと、会話が増えるほど開くのが遅くなる。"""
    db = FakeDB()
    t = bind(db)
    try:
        conversations.save_conversation("", MSGS)
        items = conversations.list_conversations()
        assert items and "messages" not in items[0]
        assert items[0]["title"] == "来週の予定を教えて"
    finally:
        config.reset_request_client(t)


def test_delete_removes_it():
    db = FakeDB()
    t = bind(db)
    try:
        r = conversations.save_conversation("", MSGS)
        assert conversations.delete_conversation(r["id"])["ok"] is True
        assert conversations.get_conversation(r["id"]) is None
    finally:
        config.reset_request_client(t)


# ── 失敗を握りつぶさない ─────────────────────────────────────────
def test_a_failed_save_is_reported_not_swallowed():
    """ここを握りつぶすと、端末を変えたときに初めて消えたと気づくことになる。
    表が無いDBに繋いだ人が、まさにこれに落ちる。"""
    t = bind(FakeDB(fail='relation "conversations" does not exist'))
    try:
        r = conversations.save_conversation("", MSGS)
        assert "error" in r
        assert "保存できませんでした" in r["error"]
        assert "ok" not in r
    finally:
        config.reset_request_client(t)


# ── 大きくなりすぎない ───────────────────────────────────────────
def test_long_conversations_keep_the_recent_part():
    """上限が無いと、画像付きの長い会話が行サイズを押し上げ、
    ある日から突然保存が失敗する。切るのは古いほう。"""
    many = [{"role": "user", "content": f"発言{i}"} for i in range(400)]
    trimmed = conversations._trim(many)
    assert len(trimmed) == conversations.MAX_MESSAGES
    assert trimmed[-1]["content"] == "発言399"      # 直近が残る


def test_a_huge_message_is_cut():
    trimmed = conversations._trim([{"role": "user", "content": "あ" * 50_000}])
    assert len(trimmed[0]["content"]) == conversations.MAX_CHARS_PER_MESSAGE


def test_broken_rows_do_not_break_the_save():
    trimmed = conversations._trim([None, "文字列", {"role": "system", "content": "x"}, {}])
    assert all(m["role"] in ("user", "assistant") for m in trimmed)


# ── 見出し ───────────────────────────────────────────────────────
def test_the_title_comes_from_the_first_question():
    assert conversations._title_of(MSGS) == "来週の予定を教えて"


def test_an_explicit_title_wins():
    assert conversations._title_of(MSGS, "見積の相談") == "見積の相談"


def test_an_empty_conversation_still_gets_a_name():
    assert conversations._title_of([]) == "新しいチャット"


def test_newlines_do_not_break_the_list():
    msgs = [{"role": "user", "content": "1行目\n2行目"}]
    assert "\n" not in conversations._title_of(msgs)


def test_empty_messages_are_refused():
    assert "error" in conversations.save_conversation("", [])
