# test_image_delivery.py — 作った画像が読めるか
#
# 利用者からの報告: 「画像など作成したときに読み込めない問題がある」。
#
# 原因: 画像を配る入口は <img src> のためにヘッダを使えず、認証を通していない。
# 認証が無いということは「誰の保存先を見ればいいか」も分からないということ。
# 各自が自分のSupabaseに保存する構成では、書いた先と読む先が食い違い、
# 自分で作った画像が自分で読めなかった。
#
# URLに署名つきの手形（持ち主のID）を載せて解決する。
# 手形は偽造できず、中身は利用者IDだけ。

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import hfhub


# ── 手形そのもの ─────────────────────────────────────────────────
def test_a_token_round_trips():
    t = hfhub.sign_owner("user-123")
    assert t and "." in t
    assert hfhub.verify_owner(t) == "user-123"


def test_someone_elses_id_cannot_be_forged():
    """署名が無ければ、他人のIDを名乗って他人の画像を引けてしまう。"""
    import base64
    body = base64.urlsafe_b64encode(b"someone-else").decode().rstrip("=")
    assert hfhub.verify_owner(f"{body}.0000000000000000") == ""
    assert hfhub.verify_owner(f"{body}") == ""


def test_a_tampered_token_is_rejected():
    t = hfhub.sign_owner("user-123")
    assert hfhub.verify_owner(t[:-1] + ("0" if t[-1] != "0" else "1")) == ""


def test_no_token_means_the_default_database():
    """1人運用や持ち主は手形なしで動く。空を「拒否」にしない。"""
    assert hfhub.verify_owner("") == ""
    assert hfhub.sign_owner("") == ""


def test_the_token_does_not_leak_a_secret():
    t = hfhub.sign_owner("user-123")
    secret = os.environ.get("KEYCHAIN_SECRET", "")
    if secret:
        assert secret not in t


# ── 実際に読み書きが噛み合うか ───────────────────────────────────
class FakeTable:
    def __init__(self, store): self.store = store
    def insert(self, row): self.store.append(row); return self
    def select(self, *a, **k): return self
    def eq(self, col, val): self._id = val; return self
    def limit(self, *a, **k): return self
    def execute(self):
        rows = [r for r in self.store if r.get("id") == getattr(self, "_id", None)]
        return type("R", (), {"data": rows})()


class FakeClient:
    def __init__(self): self.rows = []
    def table(self, name): return FakeTable(self.rows)


@pytest.fixture
def two_separate_databases(monkeypatch):
    """AさんのDBとBさんのDB。メモリ退避は使わせない（本番では消えるため）。"""
    hfhub._mem_images.clear()
    a, b = FakeClient(), FakeClient()
    monkeypatch.setattr(config, "_supabase_client", None, raising=False)
    monkeypatch.setattr(config, "_supabase_tried", True, raising=False)
    yield a, b
    hfhub._mem_images.clear()


def test_an_image_saved_in_my_database_is_read_from_my_database(two_separate_databases):
    mine, theirs = two_separate_databases

    token = config.bind_request_client(mine)
    try:
        img_id = hfhub.save_image(b"\x89PNG-mine", "image/png", "私の画像")
    finally:
        config.reset_request_client(token)

    # 保存はAさんのDBに入り、Bさんのには入っていない
    assert any(r["id"] == img_id for r in mine.rows)
    assert not theirs.rows

    # メモリ退避を消しても、Aさんの保存先からなら読める
    hfhub._mem_images.clear()
    token = config.bind_request_client(mine)
    try:
        data, mime = hfhub.get_image(img_id)
    finally:
        config.reset_request_client(token)
    assert data == b"\x89PNG-mine"
    assert mime == "image/png"


def test_reading_from_the_wrong_database_finds_nothing(two_separate_databases):
    """ここが「画像が読み込めない」の正体だった。取り違えたら空で返る。"""
    mine, theirs = two_separate_databases

    token = config.bind_request_client(mine)
    try:
        img_id = hfhub.save_image(b"\x89PNG-mine", "image/png", "私の画像")
    finally:
        config.reset_request_client(token)

    hfhub._mem_images.clear()
    token = config.bind_request_client(theirs)
    try:
        data, _ = hfhub.get_image(img_id)
    finally:
        config.reset_request_client(token)
    assert data is None


def test_the_delivery_url_carries_the_owner():
    """URLに手形が載っていないと、配る側は持ち主を割り出せない。"""
    import main
    from fastapi import Request

    scope = {"type": "http", "scheme": "https", "server": ("api.example.com", 443),
             "path": "/", "headers": [], "query_string": b""}
    req = Request(scope)

    url = main._media_url(req, "/hf/image/abc123", "user-123")
    assert "/hf/image/abc123" in url
    assert "u=" in url
    token = url.split("u=", 1)[1]
    assert hfhub.verify_owner(token) == "user-123"


def test_the_url_is_unchanged_when_there_is_no_owner():
    """1人運用では手形を付けない（意味が無いうえに、URLが読みにくくなる）。"""
    import main
    from fastapi import Request

    scope = {"type": "http", "scheme": "https", "server": ("api.example.com", 443),
             "path": "/", "headers": [], "query_string": b""}
    url = main._media_url(Request(scope), "/hf/image/abc123", "")
    assert "u=" not in url


def test_non_image_urls_are_left_alone():
    """音声や外部URLに手形を足さない（余計なクエリで壊れることがある）。"""
    import main
    from fastapi import Request

    scope = {"type": "http", "scheme": "https", "server": ("api.example.com", 443),
             "path": "/", "headers": [], "query_string": b""}
    url = main._media_url(Request(scope), "https://example.com/a.png", "user-123")
    assert url == "https://example.com/a.png"
