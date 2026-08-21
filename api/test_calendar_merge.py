# test_calendar_merge.py — アプリ内の予定とGoogleカレンダーを1枚にまとめる入口の検証
#
# 予定が2か所にあると「どっちを見ればいいのか」になる。画面には1枚の
# カレンダーとして出すので、まとめる側が壊れると予定が消えたように見える。
#
# 特に大事なのは、片方が落ちても、もう片方は必ず出ること。
# Googleが繋がらない日にアプリ内の予定まで消えたら、ただの障害に見える。

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agenda
import config
import gservice
from main import app

client = TestClient(app)


@pytest.fixture
def open_app(monkeypatch):
    """認証は別のテストで見ているので、ここは通す。"""
    monkeypatch.setattr(config, "APP_TOKEN", "")
    monkeypatch.setattr(config, "REQUIRE_AUTH", False)
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", "")


def _cal(days=30):
    r = client.get(f"/agenda/calendar?days={days}")
    assert r.status_code == 200, r.text
    return r.json()


def test_app_events_are_returned(open_app, monkeypatch):
    monkeypatch.setattr(agenda, "list_events", lambda *a, **k: [
        {"id": "1", "title": "歯医者", "date": "2026-08-21", "time": "15:00", "note": ""},
    ])
    monkeypatch.setattr(gservice, "connected", lambda: False)

    body = _cal()
    assert body["google_connected"] is False
    assert body["items"][0]["title"] == "歯医者"
    assert body["items"][0]["source"] == "app"


def test_google_events_are_merged_and_marked(open_app, monkeypatch):
    monkeypatch.setattr(agenda, "list_events", lambda *a, **k: [
        {"id": "1", "title": "アプリの予定", "date": "2026-08-22", "time": "10:00", "note": ""},
    ])
    monkeypatch.setattr(gservice, "connected", lambda: True)
    monkeypatch.setattr(gservice, "list_events", lambda d, m: {"ok": True, "items": [
        {"title": "Googleの予定", "start": "2026-08-21T15:00:00+09:00", "url": "https://cal/1"},
    ]})

    body = _cal()
    assert body["google_connected"] is True
    titles = [i["title"] for i in body["items"]]
    assert titles == ["Googleの予定", "アプリの予定"]      # 日付順
    g = body["items"][0]
    assert g["source"] == "google"
    assert g["date"] == "2026-08-21"                      # 日付だけ切り出す
    assert g["time"] == "15:00"                           # 時刻も取り出す
    assert g["url"] == "https://cal/1"


def test_all_day_google_events_have_no_time(open_app, monkeypatch):
    """終日の予定は start が "2026-08-21" だけ。時刻をでっち上げない。"""
    monkeypatch.setattr(agenda, "list_events", lambda *a, **k: [])
    monkeypatch.setattr(gservice, "connected", lambda: True)
    monkeypatch.setattr(gservice, "list_events", lambda d, m: {"ok": True, "items": [
        {"title": "夏休み", "start": "2026-08-21", "url": ""},
    ]})

    item = _cal()["items"][0]
    assert item["date"] == "2026-08-21"
    assert item["time"] == ""


def test_google_failing_never_hides_app_events(open_app, monkeypatch):
    """ここが本題。片方の失敗で予定が全部消えたら、障害にしか見えない。"""
    monkeypatch.setattr(agenda, "list_events", lambda *a, **k: [
        {"id": "1", "title": "残るはずの予定", "date": "2026-08-21", "time": "", "note": ""},
    ])
    monkeypatch.setattr(gservice, "connected", lambda: True)

    def boom(*a, **k):
        raise RuntimeError("Googleが落ちている")

    monkeypatch.setattr(gservice, "list_events", boom)

    body = _cal()
    assert [i["title"] for i in body["items"]] == ["残るはずの予定"]


def test_app_store_failing_still_returns_google(open_app, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("保存先が読めない")

    monkeypatch.setattr(agenda, "list_events", boom)
    monkeypatch.setattr(gservice, "connected", lambda: True)
    monkeypatch.setattr(gservice, "list_events", lambda d, m: {"ok": True, "items": [
        {"title": "Googleだけ", "start": "2026-08-21T09:00:00+09:00", "url": ""},
    ]})

    assert [i["title"] for i in _cal()["items"]] == ["Googleだけ"]


def test_nothing_configured_returns_an_empty_list_not_an_error(open_app, monkeypatch):
    monkeypatch.setattr(agenda, "list_events", lambda *a, **k: [])
    monkeypatch.setattr(gservice, "connected", lambda: False)

    body = _cal()
    assert body["items"] == []
    assert body["google_connected"] is False


def test_untitled_events_still_show_up(open_app, monkeypatch):
    """タイトルが空でも行を消さない。消すと「予定が減った」と見える。"""
    monkeypatch.setattr(agenda, "list_events", lambda *a, **k: [
        {"id": "1", "title": "", "date": "2026-08-21", "time": "", "note": ""},
    ])
    monkeypatch.setattr(gservice, "connected", lambda: False)

    assert _cal()["items"][0]["title"] == "(無題)"
