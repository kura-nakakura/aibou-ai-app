# test_auth_matrix.py — 設定のどの段階でも動くことの検証
#
# ログインを足したとき、フロントが Authorization を JWT で上書きしたせいで、
# それまで通っていた共通トークンが失われ「ログインした瞬間に全部401」に
# なった。動いていたアプリを壊す最悪の壊れ方だったので、設定の組み合わせを
# 総当たりで見張る。
#
# 考え方: 通行証（通してよいか）と本人確認（誰か）は別物。
#   Authorization  … 確実に通る資格情報
#   X-Supabase-Token … 誰かを伝える（利用者ごとの分離・オーナー判定に使う）

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import main
from main import app

client = TestClient(app)
SECRET = "matrix-test-jwt-secret"
APP = "legacy-app-token"


def jwt_for(sub="u1", email="a@example.com"):
    import jwt as pyjwt
    return pyjwt.encode({"sub": sub, "email": email, "aud": "authenticated",
                         "exp": 9999999999}, SECRET, algorithm="HS256")


def setup_server(monkeypatch, app_token="", jwt_secret="", require=False):
    monkeypatch.setattr(config, "APP_TOKEN", app_token)
    monkeypatch.setattr(config, "SUPABASE_JWT_SECRET", jwt_secret)
    monkeypatch.setattr(config, "REQUIRE_AUTH", require)
    monkeypatch.setattr(config, "OWNER_EMAIL", "")
    monkeypatch.setattr(config, "OWNER_USER_ID", "")


def frontend_headers(api_token="", signed_in=False):
    """webapp/src/lib/api.ts の authHeaders と同じ組み立て。"""
    h = {}
    token = jwt_for() if signed_in else ""
    if api_token:
        h["Authorization"] = f"Bearer {api_token}"
        if token:
            h["X-Supabase-Token"] = token
    elif token:
        h["Authorization"] = f"Bearer {token}"
    return h


def can_use(headers) -> bool:
    return client.get("/tasks", headers=headers).status_code != 401


# ── 動いていた構成が、ログインしても動き続けること（本題）──────────
def test_legacy_setup_keeps_working_after_signing_in(monkeypatch):
    """APP_TOKEN だけの構成。ログインで壊れないこと。"""
    setup_server(monkeypatch, app_token=APP, jwt_secret="", require=True)

    assert can_use(frontend_headers(api_token=APP, signed_in=False)), "ログイン前から使えない"
    assert can_use(frontend_headers(api_token=APP, signed_in=True)), \
        "ログインした瞬間に使えなくなっている（これが起きた不具合）"


def test_signing_in_does_not_lose_the_working_credential(monkeypatch):
    """Authorization が JWT で上書きされていないこと。"""
    setup_server(monkeypatch, app_token=APP, jwt_secret="", require=True)
    h = frontend_headers(api_token=APP, signed_in=True)
    assert h["Authorization"] == f"Bearer {APP}", "通行証をJWTで置き換えている"
    assert "X-Supabase-Token" in h, "本人確認が送られていない"


# ── 設定の各段階 ──────────────────────────────────────────────────
@pytest.mark.parametrize("api_token,signed_in", [
    ("", False), ("", True), (APP, False), (APP, True),
])
def test_open_server_lets_everyone_through(monkeypatch, api_token, signed_in):
    """何も設定していない（1人運用）ならオープンのまま。"""
    setup_server(monkeypatch)
    assert can_use(frontend_headers(api_token, signed_in))


@pytest.mark.parametrize("api_token,signed_in,ok", [
    (APP, False, True),    # 共通トークンで通る
    (APP, True, True),     # ログインしても通る
    ("", True, True),      # JWTだけでも通る
    ("", False, False),    # 何も無ければ通さない
])
def test_full_setup(monkeypatch, api_token, signed_in, ok):
    """JWT も APP_TOKEN も設定済み（移行中）。"""
    setup_server(monkeypatch, app_token=APP, jwt_secret=SECRET, require=True)
    assert can_use(frontend_headers(api_token, signed_in)) is ok


@pytest.mark.parametrize("signed_in,ok", [(True, True), (False, False)])
def test_final_setup_jwt_only(monkeypatch, signed_in, ok):
    """配布時の構成（APP_TOKEN を外し、ログイン必須）。"""
    setup_server(monkeypatch, app_token="", jwt_secret=SECRET, require=True)
    assert can_use(frontend_headers(api_token="", signed_in=signed_in)) is ok


def test_app_token_alone_does_not_pass_once_it_is_removed(monkeypatch):
    """APP_TOKEN を外したら、古いトークンでは通れないこと。"""
    setup_server(monkeypatch, app_token="", jwt_secret=SECRET, require=True)
    assert not can_use({"Authorization": f"Bearer {APP}"})
    assert not can_use({"X-App-Token": APP})


# ── 本人確認が、通行証と別に効いていること ────────────────────────
def test_identity_is_read_from_its_own_header(monkeypatch):
    """Authorization が共通トークンでも、誰かは分かること。

    ここが効かないと、利用者ごとのDB分離もオーナー判定も働かない。
    """
    setup_server(monkeypatch, app_token=APP, jwt_secret=SECRET, require=True)
    h = frontend_headers(api_token=APP, signed_in=True)
    prof = client.get("/account/profile", headers=h).json()
    assert prof["signed_in"] is True
    assert prof["user_id"] == "u1"


def test_owner_check_uses_the_identity_header(monkeypatch):
    """共通トークン構成でも、持ち主判定が正しく効くこと。"""
    setup_server(monkeypatch, app_token=APP, jwt_secret=SECRET, require=True)
    monkeypatch.setattr(config, "OWNER_EMAIL", "boss@example.com")

    import jwt as pyjwt
    def tok(email):
        return pyjwt.encode({"sub": "x", "email": email, "aud": "authenticated",
                             "exp": 9999999999}, SECRET, algorithm="HS256")

    boss = {"Authorization": f"Bearer {APP}", "X-Supabase-Token": tok("boss@example.com")}
    emp = {"Authorization": f"Bearer {APP}", "X-Supabase-Token": tok("emp@example.com")}
    assert client.get("/income/jobs", headers=boss).status_code != 403
    assert client.get("/income/jobs", headers=emp).status_code == 403


def test_a_forged_identity_is_ignored(monkeypatch):
    """署名の合わない本人確認は通さないこと。"""
    setup_server(monkeypatch, app_token=APP, jwt_secret=SECRET, require=True)
    import jwt as pyjwt
    forged = pyjwt.encode({"sub": "attacker", "email": "boss@example.com",
                           "aud": "authenticated", "exp": 9999999999},
                          "wrong-secret", algorithm="HS256")
    prof = client.get("/account/profile",
                      headers={"Authorization": f"Bearer {APP}",
                               "X-Supabase-Token": forged}).json()
    assert prof["signed_in"] is False
    assert prof["user_id"] == ""
