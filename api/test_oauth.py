# test_oauth.py — 「押すだけ」の連携が、正しい人のものになること
#
# 元の不具合:
#   提供元からの戻り（コールバック）は、提供元のサーバーがブラウザを飛ばして
#   くるだけなのでログイン情報が付かない。利用者を特定できないまま鍵を保存して
#   いたため、keychain が「1人運用」とみなして os.environ に書いていた。
#   os.environ はサーバー全体の既定値なので、
#     誰か1人がGoogleを繋ぐ → 自分で繋いでいない他の利用者が全員その人の
#     Googleアカウントで動く（カレンダーを読み、ドライブに書く）
#   という漏れになっていた。
#
# 直し方: 送り出すときに「誰が始めたか」を署名して state に載せ、戻りで検証して
# その人の保管庫にだけ入れる。署名があるので、他人が state を作って別の
# アカウントを差し込むこともできない。

import json
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import keychain
import oauth
from main import app

client = TestClient(app)


class _FakeDB:
    """自分のSupabaseを繋いでいる利用者（読み書きは何も返さない）。"""
    def __init__(self):
        self.written = {}

    def table(self, _name):
        outer = self

        class Q:
            _payload = None

            def select(self, *a, **k): return self
            def eq(self, *a, **k): return self
            def limit(self, *a, **k): return self
            def order(self, *a, **k): return self
            def delete(self, *a, **k): return self

            def upsert(self, payload, *a, **k):
                outer.written[payload.get("name")] = payload.get("value")
                return self

            def insert(self, *a, **k): return self
            def update(self, *a, **k): return self

            def execute(self):
                class R:
                    data: list = []
                return R()
        return Q()


@pytest.fixture(autouse=True)
def clean():
    for k in ("OAUTH_GOOGLE", "OAUTH_SLACK", "GOOGLE_REFRESH_TOKEN",
              "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"):
        os.environ.pop(k, None)
    keychain._mem_keys.clear()
    yield
    for k in ("OAUTH_GOOGLE", "OAUTH_SLACK", "GOOGLE_REFRESH_TOKEN",
              "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"):
        os.environ.pop(k, None)
    keychain._mem_keys.clear()


# ── 1. 連携が、始めた本人のものになること ────────────────────────────
def test_a_connection_never_becomes_the_server_wide_default(monkeypatch):
    """利用者Aの連携が、繋いでいない利用者Bにも使われないこと。"""
    monkeypatch.setattr(oauth, "_app_credentials", lambda p: ("cid", "sec"))
    monkeypatch.setattr(oauth, "_whoami", lambda p, t: "a@example.com")

    class Resp:
        content = b"{}"
        def json(self):
            return {"refresh_token": "rt-A", "access_token": "at-A", "expires_in": 3600}

    monkeypatch.setattr(oauth.requests, "post", lambda *a, **k: Resp())

    # 利用者Aの保存先に束ねてから受け取る（本番のコールバックと同じ形）
    db_a = _FakeDB()
    token = config.bind_request_client(db_a)
    try:
        res = oauth.finish("google", "code-A", "https://x/cb")
        assert res["ok"] is True
    finally:
        config.reset_request_client(token)

    # サーバー全体の既定になっていないこと（ここが元の漏れ）
    assert os.environ.get("OAUTH_GOOGLE") is None, "連携がサーバー全体の既定になっている"
    assert os.environ.get("GOOGLE_REFRESH_TOKEN") is None

    # Aの保存先には入っている
    assert "OAUTH_GOOGLE" in db_a.written
    assert "rt-A" in db_a.written["OAUTH_GOOGLE"]

    # 別の利用者Bからは見えないこと
    token = config.bind_request_client(_FakeDB())
    try:
        assert oauth.connected("google") is False, "他人の連携が見えている"
        assert oauth.access_token("google") == ""
    finally:
        config.reset_request_client(token)


def test_a_user_without_storage_is_told_rather_than_leaking(monkeypatch):
    """保存先が無い利用者の連携を、プロセスへ書いて済ませないこと。"""
    monkeypatch.setattr(oauth, "_app_credentials", lambda p: ("cid", "sec"))
    monkeypatch.setattr(oauth, "_whoami", lambda p, t: "")

    class Resp:
        content = b"{}"
        def json(self):
            return {"refresh_token": "rt-X", "access_token": "at-X", "expires_in": 3600}

    monkeypatch.setattr(oauth.requests, "post", lambda *a, **k: Resp())

    token = config.bind_request_client(None)      # ログイン済み・保存先なし
    try:
        res = oauth.finish("google", "code", "https://x/cb")
        assert res.get("error") and "保存先" in res["error"]
    finally:
        config.reset_request_client(token)
    assert os.environ.get("OAUTH_GOOGLE") is None


# ── 2. state（誰が始めたか）の署名 ───────────────────────────────────
def test_state_carries_the_owner_and_cannot_be_forged(monkeypatch):
    monkeypatch.setattr(config, "KEYCHAIN_SECRET", "server-secret", raising=False)
    st = oauth.sign_state("user-A", "google")

    ok = oauth.verify_state(st, "google")
    assert ok["ok"] is True and ok["user_id"] == "user-A"

    # 中身を書き換えたら通らない（他人のAIbouに別アカウントを差し込ませない）
    body, _, sig = st.partition(".")
    import base64
    forged = base64.urlsafe_b64encode(
        json.dumps({"u": "user-B", "p": "google", "t": 9999999999}).encode()
    ).decode().rstrip("=") + "." + sig
    assert oauth.verify_state(forged, "google").get("error")

    # 提供元をすり替えても通らない
    assert oauth.verify_state(st, "slack").get("error")
    # 署名が無ければ通らない
    assert oauth.verify_state(body, "google").get("error")


def test_state_expires(monkeypatch):
    monkeypatch.setattr(config, "KEYCHAIN_SECRET", "server-secret", raising=False)
    st = oauth.sign_state("user-A", "google")
    monkeypatch.setattr(oauth.time, "time", lambda: 10 ** 10)
    assert "時間" in oauth.verify_state(st, "google").get("error", "")


def test_callback_refuses_a_missing_state():
    r = client.get("/connect/google/callback", params={"code": "abc"})
    assert r.status_code == 400 and "state" in r.text


# ── 3. アプリ登録はサーバー側（利用者は鍵を入れない） ────────────────
def test_the_owner_registers_the_app_once_and_nobody_types_keys(monkeypatch):
    """持ち主が環境変数に置けば、利用者は誰も client_id を入力しなくてよい。"""
    assert oauth.configured("google") is False
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "server-cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "server-sec")
    assert oauth.configured("google") is True

    res = oauth.start_url("google", "https://x/cb", "user-A")
    assert res["ok"] and "server-cid" in res["url"]
    assert "state=" in res["url"]
    assert "gmail.readonly" in res["url"], "メールを読む権限が要求されていない"


def test_start_explains_what_the_owner_must_do():
    res = oauth.start_url("google", "https://x/cb", "user-A")
    assert "GOOGLE_CLIENT_ID" in res["error"]
    assert "持ち主が1回だけ" in res["error"]


def test_unknown_provider_is_refused():
    assert oauth.start_url("dropbox", "https://x/cb").get("error")
    assert oauth.status("dropbox").get("error")


# ── 4. 以前の形からの持ち越し ────────────────────────────────────────
def test_an_old_connection_is_still_recognised():
    """GOOGLE_REFRESH_TOKEN だけで繋いである人が、繋ぎ直さずに済むこと。"""
    keychain.set_key("GOOGLE_REFRESH_TOKEN", "rt-old")
    try:
        assert oauth.connected("google") is True
        assert oauth._load("google")["refresh_token"] == "rt-old"
    finally:
        keychain.delete_key("GOOGLE_REFRESH_TOKEN")


def test_disconnect_removes_both_the_new_and_the_old_form():
    keychain.set_key("GOOGLE_REFRESH_TOKEN", "rt-old")
    keychain.set_key("OAUTH_GOOGLE", json.dumps({"refresh_token": "rt-new"}))
    oauth.disconnect("google")
    assert oauth.connected("google") is False


# ── 5. 画面に出す状態 ────────────────────────────────────────────────
def test_status_separates_app_registration_from_the_users_consent():
    """「持ち主の登録がまだ」と「この人がまだ許可していない」を混ぜないこと。

    混ぜると、利用者が自分では直せないことを直そうとして詰まる。
    """
    st = oauth.status("google")
    assert st["configured"] is False and st["connected"] is False
    assert st["unlocks"] and st["label"] == "Google"


def test_connect_endpoint_lists_providers_and_what_cannot_be_oauthed():
    r = client.get("/connect")
    assert r.status_code == 200
    d = r.json()
    keys = {p["key"] for p in d["providers"]}
    assert {"google", "slack", "notion", "github"} <= keys
    # AIの鍵はOAuthにできない。理由を画面に出せるように返す。
    assert "GEMINI_API_KEY" in d["no_oauth"]
    assert "請求先" in d["no_oauth"]["GEMINI_API_KEY"]


def test_no_provider_leaks_its_secret():
    r = client.get("/connect")
    body = r.text
    assert "client_secret" not in body and "refresh_token" not in body


# ── 6. 入口（HTTP）を通したときも、漏れないこと ──────────────────────
def _signed_state(user_id: str, provider: str, owner: bool = False) -> str:
    return oauth.sign_state(user_id, provider, owner)


def test_the_callback_refuses_a_user_who_has_nowhere_to_save(monkeypatch):
    """保存先を繋いでいない利用者の連携を、プロセスへ書いて済ませないこと。

    ここを素通りさせると keychain が「1人運用」とみなしてプロセスへ書き、
    その鍵がサーバー全体の既定になる。元の漏れはこの経路だった。
    """
    import tenancy
    monkeypatch.setattr(config, "KEYCHAIN_SECRET", "server-secret", raising=False)
    monkeypatch.setattr(oauth, "_app_credentials", lambda p: ("cid", "sec"))
    monkeypatch.setattr(oauth, "_whoami", lambda p, t: "")
    monkeypatch.setattr(tenancy, "client_for", lambda uid: None)   # 保存先なし

    class Resp:
        content = b"{}"
        def json(self):
            # Slack は成功時に ok:true を返す（これが無いと交換の段階で落ちる）
            return {"ok": True, "access_token": "xoxb-X", "team": {"name": "どこかの職場"}}

    monkeypatch.setattr(oauth.requests, "post", lambda *a, **k: Resp())

    r = client.get("/connect/slack/callback", params={
        "code": "abc", "state": _signed_state("user-no-db", "slack", owner=False)})
    assert r.status_code >= 400
    assert "保存先" in r.text
    assert os.environ.get("OAUTH_SLACK") is None, "連携がサーバー全体の既定になっている"


def test_the_owner_without_a_personal_db_still_connects(monkeypatch):
    """持ち主は保存先を繋いでいなくても繋げること（既定のDBが自分の物）。"""
    import tenancy
    monkeypatch.setattr(config, "KEYCHAIN_SECRET", "server-secret", raising=False)
    monkeypatch.setattr(oauth, "_app_credentials", lambda p: ("cid", "sec"))
    monkeypatch.setattr(oauth, "_whoami", lambda p, t: "team")
    monkeypatch.setattr(tenancy, "client_for", lambda uid: None)

    class Resp:
        content = b"{}"
        def json(self):
            return {"ok": True, "access_token": "xoxb-1", "team": {"name": "みんなの職場"}}

    monkeypatch.setattr(oauth.requests, "post", lambda *a, **k: Resp())

    r = client.get("/connect/slack/callback", params={
        "code": "abc", "state": _signed_state("owner-1", "slack", owner=True)})
    assert r.status_code == 200
    assert "みんなの職場" in r.text
    oauth.disconnect("slack")


# ── 7. メールが、アプリパスワード無しで読めること ────────────────────
def test_mail_works_without_an_app_password_once_google_is_connected(monkeypatch):
    """設定の中でいちばん脱落する手順（2段階認証→アプリパスワード→16文字）を
    通らなくても、Googleを繋いであれば読めること。"""
    import email_svc
    assert email_svc.configured() is False        # 何も無ければ、当然できない

    keychain.set_key("OAUTH_GOOGLE", json.dumps(
        {"refresh_token": "rt", "access_token": "at", "obtained_at": 10 ** 10,
         "expires_in": 3600, "account": "me@example.com"}))
    try:
        assert email_svc.configured() is True
        st = email_svc.status()
        assert st["via"] == "google" and st["address"] == "me@example.com"

        class Resp:
            content = b"{}"
            def __init__(self, d): self._d = d
            def json(self): return self._d

        def fake_get(url, headers=None, params=None, timeout=None):
            if url.endswith("/messages"):
                return Resp({"messages": [{"id": "m1"}]})
            return Resp({"id": "m1", "snippet": "見積の件です",
                         "payload": {"headers": [
                             {"name": "From", "value": "取引先 <a@example.com>"},
                             {"name": "Subject", "value": "見積のご確認"},
                             {"name": "Date", "value": "Tue, 2 Sep 2026 10:00:00 +0900"}]}})

        monkeypatch.setattr(email_svc.requests, "get", fake_get)
        res = email_svc.inbox(limit=1)
        assert res["ok"] is True
        m = res["items"][0]
        assert m["subject"] == "見積のご確認" and m["from"] == "a@example.com"
        assert m["id"] == "m1", "見張りが同じメールを見分けるための名札が無い"
    finally:
        keychain.delete_key("OAUTH_GOOGLE")


def test_mail_says_what_to_do_when_nothing_is_set_up():
    """「未設定」で終わらせず、いちばん楽な道を案内すること。"""
    import email_svc
    res = email_svc.inbox()
    assert res["ok"] is False and "Google" in res["error"]
