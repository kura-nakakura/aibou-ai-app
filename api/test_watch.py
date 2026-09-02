# test_watch.py — 見張り（監視して、変わったときだけ報せる）
#
# ここで守りたいのは、報告が正直であること。とくに次の2つを取り違えないこと:
#   「新着はありません」    … 見に行けて、無かった
#   「見に行けませんでした」 … そもそも確認できていない
# この2つを混ぜると、メールが読めていないのに「新着なし」と言う。
# 見張りとしては、これが一番やってはいけない嘘になる。

import base64
import hashlib
import hmac
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import inbox
import slackread
import watch
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    """毎回まっさらな見張りから始める（前のテストの記憶を持ち越さない）。"""
    watch._mem_state.clear()
    inbox._mem.clear()
    slackread._name_cache.clear()
    yield
    watch._mem_state.clear()
    inbox._mem.clear()


def _only(monkeypatch, key: str, fn):
    """源を1つだけに差し替える（他の源に邪魔されずに挙動を見る）。"""
    monkeypatch.setattr(watch, "SOURCES",
                        [{"key": key, "label": key.upper(), "collect": fn, "min_interval": 0}])


# ── 1. 読めなかった源を、黙って落とさない ───────────────────────────
def test_a_source_that_cannot_be_read_is_reported_not_hidden(monkeypatch):
    """メールが読めないとき「新着なし」と言わせない。理由まで本文に出す。"""
    _only(monkeypatch, "mail",
          lambda: {"ok": False, "error": "ログインを拒否されました"})
    text = watch.report()["text"]
    assert "見に行けなかった" in text
    assert "ログインを拒否されました" in text
    assert "いま気にすべきものはありません。" in text  # 気にすべき品目は確かに無い
    # 「無い」と「見ていない」が同じ文に混ざっていないこと
    assert text.index("いま気にすべきものはありません。") < text.index("見に行けなかった")


def test_a_broken_source_does_not_take_down_the_others(monkeypatch):
    """1つの源が例外で落ちても、他の源の報告は出る。"""
    def boom():
        raise RuntimeError("接続が切れました")

    monkeypatch.setattr(watch, "SOURCES", [
        {"key": "mail", "label": "メール", "collect": boom, "min_interval": 0},
        {"key": "tasks", "label": "タスク", "min_interval": 0,
         "collect": lambda: {"ok": True, "items": [{"key": "t1", "title": "請求書", "detail": "期限切れ"}]}},
    ])
    text = watch.report()["text"]
    assert "請求書" in text                      # 生きている源は出る
    assert "接続が切れました" in text            # 落ちた源も理由つきで出る


def test_unconfigured_is_not_the_same_as_broken(monkeypatch):
    """未設定は「壊れている」ではない。設定すれば見張れる、として別枠に出す。"""
    _only(monkeypatch, "slack",
          lambda: {"ok": False, "skipped": True, "error": "Slackの読み取りが未設定です"})
    text = watch.report()["text"]
    assert "未設定" in text
    assert "見に行けなかった" not in text


# ── 2. 増えたぶんだけを報せる ────────────────────────────────────────
def test_first_run_is_silent_then_only_new_items_are_notified(monkeypatch):
    """初回は黙って覚える。2回目以降、増えたぶんだけ鳴らす。"""
    items = [{"key": "m1", "title": "見積の件", "detail": ""}]
    _only(monkeypatch, "mail", lambda: {"ok": True, "items": list(items)})
    sent = []
    monkeypatch.setattr(watch, "notify_all_for_test", None, raising=False)

    import notify
    monkeypatch.setattr(notify, "notify_all", lambda t: (sent.append(t), {"ok": True})[1])

    # 1回目：見張りを始めた瞬間。全部が「初めて見る」なので、そのまま出すと大量に飛ぶ
    first = watch.tick(force=True)
    assert first["notified"] is False, "見張りを始めた1回目から通知が飛んでいる"
    assert sent == []

    # 2回目：何も増えていない
    assert watch.tick(force=True)["notified"] is False
    assert sent == []

    # 3回目：1件増えた
    items.append({"key": "m2", "title": "請求書が届きました", "detail": "経理より"})
    third = watch.tick(force=True)
    assert third["notified"] is True and third["new"] == 1
    assert len(sent) == 1
    assert "請求書が届きました" in sent[0]
    assert "見積の件" not in sent[0], "前に報せたものをもう一度送っている"


def test_the_same_failure_is_not_announced_every_time(monkeypatch):
    """メールのパスワードが違えば毎回同じ失敗が出る。毎回鳴らすのは嫌がらせ。"""
    state = {"error": "ログインを拒否されました"}
    _only(monkeypatch, "mail", lambda: {"ok": False, "error": state["error"]})
    sent = []
    import notify
    monkeypatch.setattr(notify, "notify_all", lambda t: (sent.append(t), {"ok": True})[1])

    assert watch.tick(force=True)["notified"] is True     # 1回目は報せる
    assert watch.tick(force=True)["notified"] is False    # 2回目は黙る
    assert watch.tick(force=True)["notified"] is False
    assert len(sent) == 1

    # 直ったら、直ったことを報せる
    _only(monkeypatch, "mail", lambda: {"ok": True, "items": []})
    res = watch.tick(force=True)
    assert res["notified"] is True
    assert "読めるようになりました" in sent[-1]


def test_disabled_source_is_not_collected(monkeypatch):
    calls = {"n": 0}

    def counted():
        calls["n"] += 1
        return {"ok": True, "items": []}

    _only(monkeypatch, "mail", counted)
    watch.set_enabled("mail", False)
    watch.report()
    assert calls["n"] == 0, "止めた対象を見に行っている"


def test_min_interval_keeps_us_off_the_network(monkeypatch):
    """毎分IMAPやSlackに繋ぎに行かない。画面からの「今すぐ」だけは通す。"""
    calls = {"n": 0}

    def counted():
        calls["n"] += 1
        return {"ok": True, "items": []}

    monkeypatch.setattr(watch, "SOURCES",
                        [{"key": "mail", "label": "メール", "collect": counted,
                          "min_interval": 3600}])
    watch.tick(force=False)
    assert calls["n"] == 1
    watch.tick(force=False)
    assert calls["n"] == 1, "間隔を空けずに見に行っている"
    watch.tick(force=True)
    assert calls["n"] == 2, "「今すぐ確認」が間隔で止められている"


# ── 3. 「気にすべきもの」だけを品目にする ────────────────────────────
def test_only_due_tasks_become_items(monkeypatch):
    """自分で足したタスクが即座に通知で返ってくるのは、うるさいだけ。

    期限が来ているものだけを拾う。
    """
    import tasks as tasks_mod
    today = watch._today()
    monkeypatch.setattr(tasks_mod, "list_tasks", lambda status=None, limit=100: [
        {"id": "a", "title": "期限なし", "due": ""},
        {"id": "b", "title": "まだ先", "due": "2099-12-31"},
        {"id": "c", "title": "今日が期限", "due": today},
        {"id": "d", "title": "とっくに過ぎている", "due": "2020-01-01"},
    ])
    res = watch._src_tasks()
    titles = [i["title"] for i in res["items"]]
    assert titles == ["今日が期限", "とっくに過ぎている"]
    assert res["items"][1]["urgent"] is True          # 期限切れは強調する


def test_a_task_becoming_due_counts_as_new(monkeypatch):
    """明日期限のタスクが今日になったら、それは新しい動きとして報せる。"""
    import tasks as tasks_mod
    today = watch._today()
    rows = [{"id": "a", "title": "請求書を出す", "due": "2099-01-01"}]
    monkeypatch.setattr(tasks_mod, "list_tasks", lambda status=None, limit=100: rows)
    monkeypatch.setattr(watch, "SOURCES",
                        [{"key": "tasks", "label": "タスク", "collect": watch._src_tasks,
                          "min_interval": 0}])
    import notify
    sent = []
    monkeypatch.setattr(notify, "notify_all", lambda t: (sent.append(t), {"ok": True})[1])

    watch.tick(force=True)                 # 初回：まだ期限は先なので品目ゼロ
    assert sent == []
    rows[0]["due"] = today                 # 期限が今日になった
    res = watch.tick(force=True)
    assert res["notified"] is True and "請求書を出す" in sent[-1]


# ── 4. Slack ─────────────────────────────────────────────────────────
def test_slack_webhook_alone_cannot_read(monkeypatch):
    """通知用のWebhookだけ入れても読めない。そこを正直に言う。"""
    import keychain
    monkeypatch.setattr(keychain, "get_key",
                        lambda n: "https://hooks.slack.com/x" if n == "SLACK_WEBHOOK" else "")
    res = watch._src_slack()
    assert res["ok"] is False and res["skipped"] is True
    assert "SLACK_BOT_TOKEN" in res["hint"]
    assert "送信専用" in res["hint"]


def test_slack_missing_scope_is_explained_in_japanese(monkeypatch):
    import keychain
    monkeypatch.setattr(keychain, "get_key",
                        lambda n: "xoxb-test" if n == "SLACK_BOT_TOKEN" else "")

    class R:
        content = b"{}"
        status_code = 200
        def json(self):
            return {"ok": False, "error": "missing_scope", "needed": "channels:history"}

    monkeypatch.setattr(slackread.requests, "get", lambda *a, **k: R())
    res = slackread.recent()
    assert res["ok"] is False
    assert "権限" in res["error"] and "channels:history" in res["error"]


def test_slack_reads_messages(monkeypatch):
    import keychain
    monkeypatch.setattr(keychain, "get_key",
                        lambda n: "xoxb-test" if n == "SLACK_BOT_TOKEN" else "")

    class R:
        content = b"{}"
        status_code = 200
        def __init__(self, d):
            self._d = d
        def json(self):
            return self._d

    def fake_get(url, params=None, **k):
        if url.endswith("users.conversations"):
            return R({"ok": True, "channels": [{"id": "C1", "name": "general"}]})
        if url.endswith("conversations.history"):
            return R({"ok": True, "messages": [
                {"ts": "1700000002.0", "user": "U1", "text": "見積の件どうなりました？"},
                {"ts": "1700000001.0", "user": "U1", "text": "参加しました", "subtype": "channel_join"},
            ]})
        if url.endswith("users.info"):
            return R({"ok": True, "user": {"profile": {"display_name": "田中"}}})
        return R({"ok": False, "error": "unknown_method"})

    monkeypatch.setattr(slackread.requests, "get", fake_get)
    res = slackread.recent()
    assert res["ok"] is True and len(res["items"]) == 1     # 入退室は数えない
    m = res["items"][0]
    assert m["text"] == "見積の件どうなりました？"
    assert m["channel"] == "general" and m["who"] == "田中"
    assert m["key"] == "C1:1700000002.0"


def test_slack_one_bad_channel_does_not_hide_the_others(monkeypatch):
    import keychain
    monkeypatch.setattr(keychain, "get_key",
                        lambda n: "xoxb-test" if n == "SLACK_BOT_TOKEN" else "")

    class R:
        content = b"{}"
        status_code = 200
        def __init__(self, d):
            self._d = d
        def json(self):
            return self._d

    def fake_get(url, params=None, **k):
        if url.endswith("users.conversations"):
            return R({"ok": True, "channels": [{"id": "C1", "name": "ok"},
                                               {"id": "C2", "name": "ng"}]})
        if url.endswith("conversations.history"):
            if (params or {}).get("channel") == "C2":
                return R({"ok": False, "error": "not_in_channel"})
            return R({"ok": True, "messages": [{"ts": "1.0", "user": "U1", "text": "こんにちは"}]})
        return R({"ok": True, "user": {"profile": {"display_name": "誰か"}}})

    monkeypatch.setattr(slackread.requests, "get", fake_get)
    res = slackread.recent()
    assert res["ok"] is True and len(res["items"]) == 1
    assert "not_in_channel" not in res.get("warning", "")
    assert "入っていません" in res.get("warning", ""), "読めなかったチャンネルが黙殺されている"


# ── 5. LINE の受信口 ─────────────────────────────────────────────────
_SECRET = "line-channel-secret"


def _sign(body: bytes, secret: str = _SECRET) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


def _line_body(text: str = "会議を30分ずらせますか", mid: str = "msg1") -> bytes:
    return json.dumps({"events": [{
        "type": "message", "timestamp": 1700000000000,
        "source": {"userId": "U123"},
        "message": {"id": mid, "type": "text", "text": text},
    }]}).encode()


def test_line_webhook_rejects_a_forged_body(monkeypatch):
    """URLを知っただけの相手に書き込ませない。ここが無いと誰でも偽メッセージを流せる。"""
    import keychain
    monkeypatch.setattr(keychain, "get_key",
                        lambda n: _SECRET if n == "LINE_CHANNEL_SECRET" else "")
    body = _line_body()
    r = client.post("/line/webhook", content=body,
                    headers={"X-Line-Signature": _sign(body, "まちがった秘密")})
    assert r.status_code == 403
    assert inbox.list_messages(channel="line") == []


def test_line_webhook_refuses_when_it_cannot_verify(monkeypatch):
    """シークレット未設定なら受け取らない。検証できないものを保存しない。"""
    import keychain
    monkeypatch.setattr(keychain, "get_key", lambda n: "")
    body = _line_body()
    r = client.post("/line/webhook", content=body,
                    headers={"X-Line-Signature": _sign(body)})
    assert r.status_code == 503
    assert inbox.list_messages(channel="line") == []


def test_line_webhook_accepts_a_genuine_message(monkeypatch):
    import keychain
    monkeypatch.setattr(keychain, "get_key",
                        lambda n: _SECRET if n == "LINE_CHANNEL_SECRET" else "")
    body = _line_body()
    r = client.post("/line/webhook", content=body,
                    headers={"X-Line-Signature": _sign(body)})
    assert r.status_code == 200 and r.json()["saved"] == 1
    rows = inbox.list_messages(channel="line")
    assert len(rows) == 1 and rows[0]["text"] == "会議を30分ずらせますか"


def test_line_redelivery_is_not_counted_twice(monkeypatch):
    """LINEは同じイベントを2回送ることがある。そのまま入れると新着の数が嘘になる。"""
    import keychain
    monkeypatch.setattr(keychain, "get_key",
                        lambda n: _SECRET if n == "LINE_CHANNEL_SECRET" else "")
    body = _line_body(mid="same-id")
    head = {"X-Line-Signature": _sign(body)}
    client.post("/line/webhook", content=body, headers=head)
    second = client.post("/line/webhook", content=body, headers=head)
    assert second.json()["saved"] == 0 and second.json()["skipped"] == 1
    assert len(inbox.list_messages(channel="line")) == 1


def test_line_ignores_non_text_events(monkeypatch):
    payload = {"events": [
        {"type": "follow", "source": {"userId": "U1"}},
        {"type": "message", "message": {"id": "s1", "type": "sticker"}, "source": {"userId": "U1"}},
    ]}
    res = inbox.ingest_line(payload)
    assert res["saved"] == 0 and res["skipped"] == 2


def test_webhook_token_is_not_guessable_from_the_user_id(monkeypatch):
    import config
    monkeypatch.setattr(config, "KEYCHAIN_SECRET", "server-side-secret", raising=False)
    a = inbox.webhook_token("user-a")
    b = inbox.webhook_token("user-b")
    assert a and b and a != b
    assert "user-a" not in a
    assert inbox.webhook_token("user-a") == a, "同じ人なら毎回同じURLになること"


def test_signature_check_uses_the_raw_body():
    """整形し直した本文で検証すると必ず食い違う。生のバイト列で確かめる。"""
    body = b'{"events":[]}'
    assert inbox.verify_line_signature(body, _sign(body), _SECRET) is True
    assert inbox.verify_line_signature(b'{"events": []}', _sign(body), _SECRET) is False
    assert inbox.verify_line_signature(body, "", _SECRET) is False
    assert inbox.verify_line_signature(body, _sign(body), "") is False


# ── 6. 入口（HTTP） ──────────────────────────────────────────────────
def test_watch_endpoint_returns_each_source_state():
    r = client.get("/watch")
    assert r.status_code == 200
    d = r.json()
    assert {s["key"] for s in d["sources"]} == set(watch.source_keys())
    for s in d["sources"]:
        assert "ok" in s and "label" in s
        assert "_state" not in s, "内部の持ち回りが外に出ている"


def test_watch_check_endpoint_runs_now():
    r = client.post("/watch/check")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_watch_source_endpoint_rejects_unknown_source():
    r = client.post("/watch/source", json={"source": "でたらめ", "enabled": False})
    assert r.status_code == 400


def test_watch_inbox_endpoint_exposes_the_webhook_path():
    r = client.get("/watch/inbox")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True and "path" in d and "unread" in d


# ── 7. 朝の報告に、監視の中身が入っていること ────────────────────────
def test_briefing_includes_watched_material(monkeypatch):
    """挨拶と日付だけの報告に戻らないこと（元の穴がここだった）。"""
    import proactive
    monkeypatch.setattr(watch, "SOURCES", [
        {"key": "tasks", "label": "タスク", "min_interval": 0,
         "collect": lambda: {"ok": True, "items": [{"key": "t1", "title": "請求書を出す",
                                                    "detail": "期限切れ"}]}},
    ])
    import config
    monkeypatch.setattr(config, "get_gemini_model", lambda: None)
    text = proactive.build_briefing()
    assert "請求書を出す" in text


def test_briefing_says_what_it_could_not_check(monkeypatch):
    """AIにまとめさせても「確認できていません」が消えないこと。"""
    import proactive
    import config
    monkeypatch.setattr(watch, "SOURCES", [
        {"key": "mail", "label": "メール", "min_interval": 0,
         "collect": lambda: {"ok": False, "error": "ログインを拒否されました"}},
    ])

    class Model:
        def generate_content(self, p):
            class R:
                text = "おはようございます。特に問題ありません。"
            return R()

    monkeypatch.setattr(config, "get_gemini_model", lambda: Model())
    text = proactive.build_briefing()
    assert "確認できていません" in text
    assert "ログインを拒否されました" in text


# ── 8. 会話から呼べる道具 ────────────────────────────────────────────
def test_watch_report_tool(monkeypatch):
    import tools
    monkeypatch.setattr(watch, "SOURCES", [
        {"key": "mail", "label": "メール", "min_interval": 0,
         "collect": lambda: {"ok": False, "error": "ログインを拒否されました"}},
    ])
    out = tools.execute_tool("watch_report", {})
    assert "ログインを拒否されました" in out
