# test_no_cross_tenant_leak.py — 他人のデータが見えないこと
#
# 最終調査で見つけた、いちばん静かな事故:
#
#   各モジュールは「DBを引く → 失敗したらプロセス内のリストを返す」形だった。
#   そのリストはモジュール変数なので、プロセス全体で1つしかない。
#
#   つまり、AさんのDBが一瞬でも読めなかったとき（通信の揺れ、表の欠け、権限）、
#   Aさんの画面に、そのプロセスで前に動いた別の人のデータが出る。
#   例外を握りつぶしているので、黙って出る。誰も気づかない。
#
#   書き込み側は require_storage で塞いだが、読み取り側は素通りだった。
#   人に配る構成では、これは事故になる。
#
# 控えを「そのとき繋いでいる保存先ごと」に分けて塞いだ。

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import memstore


class Works:
    """普通に動くDB。1つの表だけを持つ、最小の偽物。"""

    def __init__(self):
        self.rows = []

    def table(self, name):
        return _Q(self)


class _Q:
    def __init__(self, db):
        self.db, self._op, self._id, self._row = db, "select", None, None

    def select(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def eq(self, col, val): self._id = val; return self
    def insert(self, row): self._op, self._row = "insert", dict(row); return self
    def upsert(self, row): self._op, self._row = "insert", dict(row); return self
    def update(self, row): self._op, self._row = "update", dict(row); return self
    def delete(self): self._op = "delete"; return self

    def execute(self):
        if self._op == "insert":
            self.db.rows.append(self._row)
            return type("R", (), {"data": [self._row]})()
        if self._op == "update":
            for r in self.db.rows:
                if r.get("id") == self._id:
                    r.update(self._row)
            return type("R", (), {"data": []})()
        if self._op == "delete":
            self.db.rows[:] = [r for r in self.db.rows if r.get("id") != self._id]
            return type("R", (), {"data": []})()
        rows = self.db.rows
        if self._id is not None:
            rows = [r for r in rows if r.get("id") == self._id]
        return type("R", (), {"data": list(rows)})()


class Boom:
    """読み取りが必ず失敗するDB。通信の揺れや表の欠けを模す。"""

    def table(self, name):
        return self

    def select(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def insert(self, *a, **k): return self
    def upsert(self, *a, **k): return self
    def execute(self): raise RuntimeError("そのDBは今読めません")


def bind(c):
    return config.bind_request_client(c)


# ── 入れ物そのもの ───────────────────────────────────────────────
def test_a_list_is_separate_per_destination():
    box = memstore.TenantList()
    a, b = object(), object()

    t = bind(a)
    try:
        box.append("Aさんのメモ")
    finally:
        config.reset_request_client(t)

    t = bind(b)
    try:
        assert list(box) == [], "Bさんに Aさんのものが見えている"
        box.append("Bさんのメモ")
        assert list(box) == ["Bさんのメモ"]
    finally:
        config.reset_request_client(t)

    t = bind(a)
    try:
        assert list(box) == ["Aさんのメモ"], "Aさんのものが消えた"
    finally:
        config.reset_request_client(t)


def test_a_dict_is_separate_per_destination():
    box = memstore.TenantDict()
    a, b = object(), object()

    t = bind(a)
    try:
        box["GEMINI_API_KEY"] = "Aさんの鍵"
    finally:
        config.reset_request_client(t)

    t = bind(b)
    try:
        assert box.get("GEMINI_API_KEY") is None, "Bさんに Aさんの鍵が見えている"
    finally:
        config.reset_request_client(t)


def test_the_list_behaves_like_a_list():
    """各モジュールは append / insert / スライス / for / len を使う。
    どれかが動かないと、そのモジュールが静かに壊れる。"""
    box = memstore.TenantList()
    box.append({"id": "1"})
    box.insert(0, {"id": "0"})
    assert len(box) == 2
    assert box[0]["id"] == "0"
    assert [x["id"] for x in box] == ["0", "1"]
    assert list(box[:1]) == [{"id": "0"}]
    box[:] = [x for x in box if x["id"] != "0"]      # その場で削る書き方
    assert [x["id"] for x in box] == ["1"]
    del box[0]
    assert len(box) == 0 and not box


def test_trimming_from_the_end_works():
    """hfhub が del _mem_images[:-N] で古いものを捨てている。"""
    box = memstore.TenantList()
    for i in range(10):
        box.append(i)
    del box[:-3]
    assert list(box) == [7, 8, 9]


# ── 実際のモジュールで確かめる ───────────────────────────────────
@pytest.mark.parametrize("mod_name,write,read", [
    ("tasks", lambda m: m.create_task("Aさんの見積"), lambda m: m.list_tasks()),
    ("agenda", lambda m: m.add_event("Aさんの打ち合わせ", "2026-09-01"),
     lambda m: m.list_events()),
    ("conversations", lambda m: m.save_conversation(
        "", [{"role": "user", "content": "Aさんの相談"}]),
     lambda m: m.list_conversations()),
])
def test_another_persons_data_never_shows_up(mod_name, write, read):
    """ここが本題。Aさんが書いたあと、BさんのDBが読めなくても
    Aさんのものが出てはいけない。"""
    import importlib
    m = importlib.import_module(mod_name)

    a_client, b_client = Works(), Boom()

    t = bind(a_client)
    try:
        write(m)
        assert len(read(m)) >= 1, "Aさん自身の分が読めていない"
    finally:
        config.reset_request_client(t)

    t = bind(b_client)              # BさんのDBは読めない状態
    try:
        got = read(m)
    finally:
        config.reset_request_client(t)

    assert got == [], f"{mod_name}: Bさんに他人のデータが見えた → {got}"


def test_single_user_mode_still_works():
    """1人運用（差し替えなし）は、これまでどおり自分の分が読める。
    ここを壊すと、配る前の使い方が動かなくなる。"""
    import tasks
    tasks.create_task("自分のタスク")
    titles = [t.get("title") for t in tasks.list_tasks()]
    assert "自分のタスク" in titles
