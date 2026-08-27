# test_drive_truth.py — 「Googleドライブに作成しました」が本当であること
#
# 報告:
#   相棒にGoogleドライブへのファイル作成を頼んだら「作成しました」と返ってきたが、
#   実際にドライブを見ると無い。
#
# 調べて分かったこと（3つ重なっていた）:
#
#   1. 「ドライブにファイルを作る」に当たるツールが無かった。
#      あるのは Docs / Sheets / Slides だけ。「ファイルを作って」と言われると、
#      AIbouの中に保存するだけの create_document が選ばれ、
#      「ドキュメント『X』を作成しました」と返っていた。嘘ではないが、
#      ドライブを頼んだ人には嘘として届く。
#
#   2. 本文の書き込みの失敗を握りつぶしていた。
#      Docs も Sheets も「入れ物を作る」と「中身を書く」が別のリクエストで、
#      後者の応答を一切見ていなかった。中身が空のまま「作成しました」になる。
#
#   3. どのGoogleアカウントに繋いでいるかが、どこにも出ていなかった。
#      別のアカウントに繋がっていれば、作られていても本人のドライブには無い。
#
# 直したので、戻らないように固定する。

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gservice
import tools


class Resp:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._data = data if data is not None else {}
        self.content = b"x"

    def json(self):
        return self._data


class FakeGoogle:
    """Google APIの偽物。呼ばれた先を記録する。"""

    def __init__(self, *, create_ok=True, write_ok=True, exists=True, trashed=False):
        self.create_ok, self.write_ok = create_ok, write_ok
        self.exists, self.trashed = exists, trashed
        self.calls = []

    def post(self, url, **kw):
        self.calls.append(("POST", url))
        if "batchUpdate" in url:
            return Resp(200 if self.write_ok else 403,
                        {} if self.write_ok else {"error": {"message": "権限がありません"}})
        if "upload/drive" in url:
            return Resp(200, {"id": "F1", "name": "メモ.txt"} if self.create_ok
                        else {"error": {"message": "作れません"}})
        if "documents" in url:
            return Resp(200, {"documentId": "D1"} if self.create_ok
                        else {"error": {"message": "作れません"}})
        if "spreadsheets" in url:
            return Resp(200, {"spreadsheetId": "S1"} if self.create_ok
                        else {"error": {"message": "作れません"}})
        if "oauth2" in url or "token" in url:
            return Resp(200, {"access_token": "tok"})
        return Resp(200, {})

    def put(self, url, **kw):
        self.calls.append(("PUT", url))
        return Resp(200 if self.write_ok else 403,
                    {} if self.write_ok else {"error": {"message": "権限がありません"}})

    def get(self, url, **kw):
        self.calls.append(("GET", url))
        if "/drive/v3/about" in url:
            return Resp(200, {"user": {"emailAddress": "me@example.com"}})
        if "/drive/v3/files/" in url:
            if not self.exists:
                return Resp(404, {"error": {"message": "見つかりません"}})
            return Resp(200, {"id": "F1", "name": "メモ.txt", "trashed": self.trashed,
                              "webViewLink": "https://drive.google.com/file/d/F1/view",
                              "owners": [{"emailAddress": "me@example.com"}]})
        return Resp(200, {})


@pytest.fixture
def google(monkeypatch):
    def _make(**kw):
        fake = FakeGoogle(**kw)
        monkeypatch.setattr(gservice, "requests", fake)
        monkeypatch.setattr(gservice, "_access_token", lambda: "tok")
        return fake
    return _make


# ── 1. 「ドライブに作って」に当たるツールがあること ────────────────

def test_there_is_a_tool_for_making_a_file_in_drive():
    assert "drive_upload" in tools._DISPATCH
    assert "drive_upload" in tools.TOOLS_DOC


def test_drive_upload_creates_and_then_confirms_it_exists(google):
    fake = google()
    out = tools.execute_tool("drive_upload", {"name": "メモ.txt", "content": "やること"})
    assert "作成し" in out and "確認しました" in out
    assert "me@example.com" in out, "どのアカウントに作ったかが出ていない"
    # 作りっぱなしにせず、必ず見に行っていること
    assert any(m == "GET" and "/drive/v3/files/" in u for m, u in fake.calls), \
        "作成の確認をしていない"


def test_drive_upload_admits_it_when_the_file_is_not_there(google):
    """作成のAPIが200でも、実際に見て無ければ「作成しました」と言わない。"""
    google(exists=False)
    out = tools.execute_tool("drive_upload", {"name": "メモ.txt", "content": "やること"})
    assert "作成できませんでした" in out
    assert "確認が取れませんでした" in out


def test_drive_upload_admits_it_when_the_file_went_to_the_trash(google):
    google(trashed=True)
    out = tools.execute_tool("drive_upload", {"name": "メモ.txt", "content": "やること"})
    assert "作成できませんでした" in out


# ── 2. AIbou内の保存を、ドライブと誤解させないこと ────────────────

def test_saving_inside_aibou_says_so_plainly(monkeypatch):
    """ここが「作成しました」だけだったので、ドライブを頼んだ人が騙された。"""
    monkeypatch.setattr(gservice, "connected", lambda: False)
    out = tools.execute_tool("create_document", {"title": "メモ", "content": "本文"})
    assert "AIbou内に保存" in out
    assert "Googleドライブではありません" in out


def test_it_points_at_the_right_tool_when_google_is_connected(monkeypatch):
    monkeypatch.setattr(gservice, "connected", lambda: True)
    out = tools.execute_tool("create_document", {"title": "メモ", "content": "本文"})
    assert "drive_upload" in out, "正しい行き先が案内されていない"


def test_the_tool_docs_warn_the_agent_away_from_the_wrong_one():
    """AIbouが選ぶ時点で間違えないよう、説明にも書いておく。"""
    doc = tools.TOOLS_DOC
    i = doc.index("- create_document:")
    j = doc.index("- create_spreadsheet:")
    assert "Googleドライブには入らない" in doc[i:j]
    assert "drive_upload" in doc[i:j]


# ── 3. 中身が入っていないのに「作成しました」と言わないこと ────────

def test_a_document_with_no_body_is_reported_as_such(google):
    google(write_ok=False)
    out = tools.execute_tool("google_doc", {"title": "議事録", "content": "本文"})
    assert "本文が入っていません" in out, out
    assert "作成しました" not in out


def test_a_sheet_with_no_rows_is_reported_as_such(google):
    google(write_ok=False)
    out = tools.execute_tool("google_sheet", {"title": "家計簿", "rows": [["費目", "金額"]]})
    assert "中身が入っていません" in out, out


def test_a_document_that_really_worked_says_so_with_the_account(google):
    google()
    out = tools.execute_tool("google_doc", {"title": "議事録", "content": "本文"})
    assert "実在を確認しました" in out
    assert "me@example.com" in out


# ── 4. どのアカウントに繋いでいるかが分かること ────────────────────

def test_status_tells_which_google_account_is_connected(google, monkeypatch):
    google()
    monkeypatch.setattr(gservice, "connected", lambda: True)
    monkeypatch.setattr(gservice, "configured", lambda: True)
    assert gservice.status().get("account") == "me@example.com"


def test_status_stays_quiet_when_not_connected(monkeypatch):
    monkeypatch.setattr(gservice, "connected", lambda: False)
    monkeypatch.setattr(gservice, "configured", lambda: True)
    st = gservice.status()
    assert st["connected"] is False
    assert "account" not in st


# ── 5. 未接続なら、はっきり断ること ───────────────────────────────

def test_drive_upload_says_it_is_not_connected(monkeypatch):
    monkeypatch.setattr(gservice, "_access_token", lambda: None)
    monkeypatch.setattr(gservice, "configured", lambda: True)
    out = tools.execute_tool("drive_upload", {"name": "a.txt", "content": "x"})
    assert "作成できませんでした" in out
    assert "未接続" in out
