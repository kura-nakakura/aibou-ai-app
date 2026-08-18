# test_key_isolation.py — 鍵が利用者どうしで混ざらないことの検証
#
# ここが壊れると、AさんのAPIキーでBさんが動く。請求も利用履歴もAさんに乗り、
# Aさんのメール・Notion・GitHubに繋がってしまう。人に渡すアプリとして最悪の
# 事故なので、実際に踏んだ形（プロセス共有の辞書と os.environ）を含めて
# しつこく確かめる。

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import keychain


class FakeTable:
    def __init__(self, store, calls):
        self._s = store
        self._c = calls
        self._name = None

    def select(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def delete(self, *a, **k): self._del = True; return self

    def eq(self, _col, val):
        self._name = val
        return self

    def upsert(self, row):
        self._s[row["name"]] = row["value"]
        self._c.append(("upsert", row["name"]))
        return type("E", (), {"execute": lambda _s2: None})()

    def execute(self):
        if getattr(self, "_del", False):
            self._s.pop(self._name, None)
            return type("R", (), {"data": []})()
        self._c.append(("select", self._name))
        if self._name is None:                      # 一覧
            return type("R", (), {"data": [{"name": n} for n in self._s]})()
        v = self._s.get(self._name)
        return type("R", (), {"data": ([{"value": v}] if v is not None else [])})()


class FakeClient:
    """ある利用者のSupabase。中身はその人だけのもの。"""

    def __init__(self, name):
        self.name = name
        self.store = {}
        self.calls = []

    def table(self, _n):
        return FakeTable(self.store, self.calls)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """サーバー共通の鍵が無い状態から始める。"""
    for n in ("NOTION_TOKEN", "GITHUB_TOKEN", "GEMINI_API_KEY", "EMAIL_PASSWORD"):
        monkeypatch.delenv(n, raising=False)
    keychain._mem_keys.clear()
    yield
    keychain._mem_keys.clear()


def use(monkeypatch, client):
    """そのリクエストを、この利用者として処理する。"""
    monkeypatch.setattr(config, "get_supabase", lambda: client)


# ── いちばん大事なところ ──────────────────────────────────────────
def test_one_users_key_never_reaches_another(monkeypatch):
    a, b = FakeClient("A"), FakeClient("B")

    use(monkeypatch, a)
    keychain.set_key("NOTION_TOKEN", "secret_A_notion")
    assert keychain.get_key("NOTION_TOKEN") == "secret_A_notion"

    use(monkeypatch, b)
    assert keychain.get_key("NOTION_TOKEN") == "", "Aさんの鍵がBさんに渡っている"

    keychain.set_key("NOTION_TOKEN", "secret_B_notion")
    assert keychain.get_key("NOTION_TOKEN") == "secret_B_notion"

    use(monkeypatch, a)
    assert keychain.get_key("NOTION_TOKEN") == "secret_A_notion", "Bさんの保存でAさんが上書きされた"


def test_saving_a_key_does_not_change_the_server_environment(monkeypatch):
    """利用者の保存が os.environ に漏れないこと（漏れると全員に効く）。"""
    a = FakeClient("A")
    use(monkeypatch, a)
    keychain.set_key("GITHUB_TOKEN", "ghp_A")
    assert os.environ.get("GITHUB_TOKEN", "") == "", "利用者の鍵がサーバー全体に漏れている"


def test_every_integration_key_is_separated(monkeypatch):
    """連携ごとに個別ではなく、仕組みとして分かれていること。"""
    names = ["NOTION_TOKEN", "GITHUB_TOKEN", "EMAIL_PASSWORD", "LINE_NOTIFY_TOKEN",
             "DISCORD_WEBHOOK", "SLACK_WEBHOOK", "HUGGINGFACE_TOKEN", "GEMINI_API_KEY"]
    a, b = FakeClient("A"), FakeClient("B")

    use(monkeypatch, a)
    for n in names:
        keychain.set_key(n, f"A_{n}")

    use(monkeypatch, b)
    for n in names:
        assert keychain.get_key(n) == "", f"{n} がBさんに漏れている"


def test_deleting_your_key_does_not_touch_anyone_else(monkeypatch):
    a, b = FakeClient("A"), FakeClient("B")
    use(monkeypatch, a)
    keychain.set_key("NOTION_TOKEN", "A_token")
    use(monkeypatch, b)
    keychain.set_key("NOTION_TOKEN", "B_token")

    keychain.delete_key("NOTION_TOKEN")
    assert keychain.get_key("NOTION_TOKEN") == ""

    use(monkeypatch, a)
    assert keychain.get_key("NOTION_TOKEN") == "A_token", "他人の削除で自分の鍵が消えた"


# ── 管理者がサーバーに入れた共通の鍵 ──────────────────────────────
def test_server_key_is_used_only_when_you_have_none(monkeypatch):
    """共通の鍵は「自分の鍵が無いときだけ」効く。"""
    monkeypatch.setenv("GEMINI_API_KEY", "server_shared_key")
    a = FakeClient("A")
    use(monkeypatch, a)
    assert keychain.get_key("GEMINI_API_KEY") == "server_shared_key"

    keychain.set_key("GEMINI_API_KEY", "A_own_key")
    assert keychain.get_key("GEMINI_API_KEY") == "A_own_key", "自分の鍵より共通鍵が優先されている"


def test_user_cannot_delete_the_shared_server_key(monkeypatch):
    """自分の操作で、他の人ごと止めてしまわないこと。"""
    monkeypatch.setenv("GEMINI_API_KEY", "server_shared_key")
    a = FakeClient("A")
    use(monkeypatch, a)
    keychain.delete_key("GEMINI_API_KEY")
    assert os.environ.get("GEMINI_API_KEY") == "server_shared_key"


def test_server_only_settings_cannot_be_overridden_by_a_user(monkeypatch):
    """暗号鍵や管理用DBの設定を、利用者のDBの値で乗っ取れないこと。"""
    monkeypatch.setenv("KEYCHAIN_SECRET", "real_server_secret")
    a = FakeClient("A")
    use(monkeypatch, a)
    a.store["KEYCHAIN_SECRET"] = "attacker_value"       # DBに直接仕込まれた想定
    assert keychain.get_key("KEYCHAIN_SECRET") == "real_server_secret"

    for n in sorted(keychain.SERVER_ONLY):
        a.store[n] = "attacker_value"
        assert keychain.get_key(n) != "attacker_value", f"{n} を利用者側から上書きできる"


# ── 一覧（設定画面）も自分のものだけ ──────────────────────────────
def test_listing_shows_only_your_own_keys(monkeypatch):
    a, b = FakeClient("A"), FakeClient("B")
    use(monkeypatch, a)
    keychain.set_key("MY_SECRET_A", "value_A")

    use(monkeypatch, b)
    listed = {k["name"]: k for k in keychain.list_keys()}
    assert "MY_SECRET_A" not in listed, "他人の鍵の名前が一覧に出ている"
    for k in listed.values():
        assert "value_A" not in (k.get("masked") or "")


def test_listing_never_returns_full_values(monkeypatch):
    a = FakeClient("A")
    use(monkeypatch, a)
    keychain.set_key("NOTION_TOKEN", "secret_A_notion_full_value")
    for k in keychain.list_keys():
        assert "secret_A_notion_full_value" not in str(k), "フルの鍵が一覧から漏れている"


# ── 1人運用（誰のDBにも繋いでいない）は今まで通り ──────────────────
def test_single_user_mode_still_works(monkeypatch):
    use(monkeypatch, None)
    keychain.set_key("NOTION_TOKEN", "solo_token")
    assert keychain.get_key("NOTION_TOKEN") == "solo_token"
    keychain.delete_key("NOTION_TOKEN")
    assert keychain.get_key("NOTION_TOKEN") == ""


# ── AIの鍵（Gemini）も人ごとであること ────────────────────────────
def test_gemini_uses_the_current_users_key(monkeypatch):
    """Aさんの生成がBさんの鍵で走らないこと。

    google-generativeai はプロセス全体に1つの鍵しか持てないので、
    「いま処理している人の鍵」を毎回入れ直しているかを見る。
    """
    a, b = FakeClient("A"), FakeClient("B")
    use(monkeypatch, a)
    keychain.set_key("GEMINI_API_KEY", "key_of_A")
    assert config.current_gemini_key() == "key_of_A"

    use(monkeypatch, b)
    keychain.set_key("GEMINI_API_KEY", "key_of_B")
    assert config.current_gemini_key() == "key_of_B"

    use(monkeypatch, a)
    assert config.current_gemini_key() == "key_of_A", "Bさんの鍵がAさんに使われている"


def test_gemini_generation_is_run_with_the_callers_key(monkeypatch):
    """実際に生成を呼んだとき、その人の鍵が genai に入っていること。"""
    seen = []

    class FakeModel:
        def __init__(self, name): self.model_name = name
        def generate_content(self, prompt, stream=False):
            seen.append(config._configured_key)      # 呼んだ瞬間の鍵
            return "ok"

    import types
    fake = types.ModuleType("google.generativeai")
    fake.configure = lambda api_key=None, **k: None
    fake.GenerativeModel = FakeModel
    monkeypatch.setitem(sys.modules, "google.generativeai", fake)
    monkeypatch.setattr(config, "_resolve_model", lambda key="": "gemini-flash-latest")
    monkeypatch.setattr(config, "_configured_key", None)

    a, b = FakeClient("A"), FakeClient("B")
    use(monkeypatch, a)
    keychain.set_key("GEMINI_API_KEY", "key_of_A")
    config.generate_resilient("こんにちは")

    use(monkeypatch, b)
    keychain.set_key("GEMINI_API_KEY", "key_of_B")
    config.generate_resilient("こんにちは")

    assert seen == ["key_of_A", "key_of_B"], f"別の人の鍵で生成している: {seen}"


def test_model_choice_is_remembered_per_key(monkeypatch):
    """鍵ごとに使えるモデルは違う。片方の判定を他方に流用しないこと。"""
    config._resolved_model.clear()
    monkeypatch.setattr(config, "_list_available_models", lambda: {"gemini-2.5-flash"})
    m1 = config._resolve_model("key_of_A")
    monkeypatch.setattr(config, "_list_available_models", lambda: {"gemini-2.0-flash"})
    m2 = config._resolve_model("key_of_B")
    assert m1 != m2, "別の鍵なのに同じモデル判定を使い回している"
