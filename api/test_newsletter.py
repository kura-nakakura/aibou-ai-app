# test_newsletter.py — ⑤ニュースレター（ダブルオプトイン/配信）と note 自動投稿

import config
import newsletter
import note_client
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def _clear(monkeypatch=None):
    newsletter._mem_subs.clear()
    newsletter._mem_issues.clear()


# ── メール検証 ───────────────────────────────────────────────────────
def test_valid_email():
    assert newsletter.valid_email("a@b.co")
    for bad in ("", "a@b", "a b@c.com", "no-at.com", "a@@b.com"):
        assert not newsletter.valid_email(bad)


# ── ダブルオプトイン ─────────────────────────────────────────────────
def test_subscribe_starts_pending_and_needs_confirmation(monkeypatch):
    monkeypatch.setattr(config, "get_supabase", lambda: None)
    monkeypatch.setattr(newsletter, "_send_confirmation", lambda e, t: True)
    _clear()
    res = newsletter.subscribe("Foo@Example.com", source="/g/test")
    assert res["ok"] and res["status"] == "pending"
    sub = newsletter.get_subscriber("foo@example.com")   # 小文字で正規化
    assert sub["status"] == "pending" and sub["source"] == "/g/test"
    # 未確認は配信対象に入らない
    assert newsletter.list_subscribers("confirmed") == []
    _clear()


def test_confirm_then_unsubscribe(monkeypatch):
    monkeypatch.setattr(config, "get_supabase", lambda: None)
    monkeypatch.setattr(newsletter, "_send_confirmation", lambda e, t: True)
    _clear()
    newsletter.subscribe("x@example.com")
    token = newsletter.get_subscriber("x@example.com")["token"]
    assert newsletter.confirm(token)["status"] == "confirmed"
    assert [s["email"] for s in newsletter.list_subscribers("confirmed")] == ["x@example.com"]
    assert newsletter.unsubscribe(token)["status"] == "unsubscribed"
    assert newsletter.list_subscribers("confirmed") == []
    _clear()


def test_bad_token_rejected(monkeypatch):
    monkeypatch.setattr(config, "get_supabase", lambda: None)
    _clear()
    assert newsletter.confirm("nope").get("error")
    assert newsletter.unsubscribe("").get("error")


def test_subscribe_invalid_email():
    assert newsletter.subscribe("bad").get("error")


def test_stats(monkeypatch):
    monkeypatch.setattr(config, "get_supabase", lambda: None)
    monkeypatch.setattr(newsletter, "_send_confirmation", lambda e, t: True)
    _clear()
    newsletter.subscribe("a@example.com")
    newsletter.subscribe("b@example.com")
    newsletter.confirm(newsletter.get_subscriber("a@example.com")["token"])
    st = newsletter.stats()
    assert st["total"] == 2 and st["confirmed"] == 1 and st["pending"] == 1
    _clear()


# ── 配信（下書き→送信・停止リンク必須） ──────────────────────────────
def test_draft_issue_requires_content(monkeypatch):
    monkeypatch.setattr(config, "get_supabase", lambda: None)
    assert newsletter.draft_issue("", "").get("error")


def test_draft_issue_with_ai_topic(monkeypatch):
    monkeypatch.setattr(config, "get_supabase", lambda: None)
    import llm
    monkeypatch.setattr(llm, "generate_text", lambda p, **k: "AIが書いた本文です")
    _clear()
    issue = newsletter.draft_issue("今週のまとめ", topic="AIの使い方")
    assert issue["status"] == "draft" and "AIが書いた" in issue["body"]
    _clear()


def test_send_includes_unsubscribe_link(monkeypatch):
    monkeypatch.setattr(config, "get_supabase", lambda: None)
    monkeypatch.setattr(newsletter, "_send_confirmation", lambda e, t: True)
    monkeypatch.setenv("PUBLIC_SITE_URL", "https://example.com")
    import compliance, email_svc
    monkeypatch.setattr(compliance, "polite_delay", lambda *a, **k: 0)
    sent = []
    monkeypatch.setattr(email_svc, "configured", lambda: True)
    monkeypatch.setattr(email_svc, "send", lambda to, sub, body: sent.append((to, sub, body)) or {"ok": True})
    _clear()
    newsletter.subscribe("c@example.com")
    newsletter.confirm(newsletter.get_subscriber("c@example.com")["token"])
    issue = newsletter.draft_issue("件名", "本文")
    res = newsletter.send_issue(issue["id"])
    assert res["ok"] and res["sent"] == 1
    # 全配信メールに配信停止リンクが入る（特定電子メール法の要件）
    assert "newsletter/unsubscribe?token=" in sent[0][2]
    assert newsletter.get_issue(issue["id"])["status"] == "sent"
    _clear()


def test_send_skips_unconfirmed(monkeypatch):
    monkeypatch.setattr(config, "get_supabase", lambda: None)
    monkeypatch.setattr(newsletter, "_send_confirmation", lambda e, t: True)
    import email_svc
    monkeypatch.setattr(email_svc, "configured", lambda: True)
    monkeypatch.setattr(email_svc, "send", lambda *a: {"ok": True})
    _clear()
    newsletter.subscribe("p@example.com")   # pending のまま
    issue = newsletter.draft_issue("件名", "本文")
    assert newsletter.send_issue(issue["id"]).get("error")   # 送る相手がいない
    _clear()


def test_send_without_email_configured(monkeypatch):
    monkeypatch.setattr(config, "get_supabase", lambda: None)
    import email_svc
    monkeypatch.setattr(email_svc, "configured", lambda: False)
    _clear()
    issue = newsletter.draft_issue("件名", "本文")
    assert "未設定" in newsletter.send_issue(issue["id"])["error"]
    _clear()


# ── エンドポイント ───────────────────────────────────────────────────
def test_subscribe_and_confirm_endpoints(monkeypatch):
    monkeypatch.setattr(config, "get_supabase", lambda: None)
    monkeypatch.setattr(newsletter, "_send_confirmation", lambda e, t: True)
    _clear()
    r = client.post("/newsletter/subscribe", json={"email": "ep@example.com", "source": "/g/x"})
    assert r.status_code == 200 and r.json()["status"] == "pending"
    assert client.post("/newsletter/subscribe", json={"email": "bad"}).status_code == 400
    token = newsletter.get_subscriber("ep@example.com")["token"]
    ok = client.get(f"/newsletter/confirm?token={token}")
    assert ok.status_code == 200 and "登録完了" in ok.text
    bad = client.get("/newsletter/confirm?token=zzz")
    assert bad.status_code == 400
    out = client.get(f"/newsletter/unsubscribe?token={token}")
    assert out.status_code == 200 and "配信停止" in out.text
    _clear()


def test_subscribers_endpoint_returns_stats(monkeypatch):
    monkeypatch.setattr(config, "get_supabase", lambda: None)
    _clear()
    r = client.get("/newsletter/subscribers")
    assert r.status_code == 200 and "stats" in r.json()


# ── note 自動投稿（既定OFF） ─────────────────────────────────────────
def test_note_disabled_by_default(monkeypatch):
    import keychain
    monkeypatch.setattr(keychain, "get_key", lambda n: "")
    monkeypatch.delenv("ALLOW_NOTE_AUTOPOST", raising=False)
    assert note_client.enabled() is False
    res = note_client.create_draft("題", "本文")
    assert res["status"] == "skipped" and "ALLOW_NOTE_AUTOPOST" in res["reason"]


def test_note_requires_credentials_even_when_opted_in(monkeypatch):
    import keychain
    monkeypatch.setattr(keychain, "get_key", lambda n: "1" if n == "ALLOW_NOTE_AUTOPOST" else "")
    res = note_client.create_draft("題", "本文")
    assert res["status"] == "skipped" and "NOTE_EMAIL" in res["reason"]


def test_note_empty_input():
    assert note_client.create_draft("", "")["status"] == "skipped"


def test_note_draft_adds_disclosure(monkeypatch):
    """投稿本文にもPR表記が必ず入る。"""
    import keychain, compliance
    creds = {"ALLOW_NOTE_AUTOPOST": "1", "NOTE_EMAIL": "a@b.com", "NOTE_PASSWORD": "pw"}
    monkeypatch.setattr(keychain, "get_key", lambda n: creds.get(n, ""))
    monkeypatch.setattr(compliance, "polite_delay", lambda *a, **k: 0)
    posted = {}

    class FakeSession:
        cookies = {"x": "1"}
        headers: dict = {}
        def post(self, url, json=None, timeout=None):
            posted["url"] = url
            posted["json"] = json
            class R:
                status_code = 200
                content = b"{}"
                def json(self_inner):
                    return {"data": {"key": "abc123"}}
            return R()

    monkeypatch.setattr(note_client, "_login", lambda: (FakeSession(), ""))
    res = note_client.create_draft("タイトル", "本文です")
    assert res["status"] == "draft_created" and "abc123" in res["url"]
    assert posted["json"]["status"] == "draft"          # 公開はしない
    assert compliance.has_disclosure(posted["json"]["body"])


def test_note_status_hides_credentials(monkeypatch):
    import keychain
    monkeypatch.setattr(keychain, "get_key", lambda n: "secret" if n == "NOTE_PASSWORD" else "")
    st = note_client.status()
    assert set(st) == {"opted_in", "credentials", "enabled", "reason"}
    assert "secret" not in str(st)


def test_note_endpoints(monkeypatch):
    import keychain
    monkeypatch.setattr(keychain, "get_key", lambda n: "")
    assert client.get("/note/status").status_code == 200
    r = client.post("/note/draft", json={"title": "t", "markdown": "b"})
    assert r.status_code == 200 and r.json()["status"] == "skipped"
