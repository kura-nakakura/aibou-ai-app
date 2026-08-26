# test_keys_persist.py — 「入れたはずの鍵が、更新したら未設定に戻る」
#
# 報告: GITHUBのトークンを入れたのに、アップデートを重ねたら入っていないことになった。
#
# 追いかけて分かった原因は2つ。どちらも「保存できていないのに保存したと言う」形。
#
#   1. set_key は Supabase への upsert を except: pass で握りつぶしていた。
#      表が無くても鍵が違っても {"ok": True} が返る。DBがまったく無い構成では
#      プロセス内のメモリと os.environ にしか書かないので、Renderが再起動する
#      たび（＝アプリを更新するたび）に消える。画面にはずっと「保存しました」。
#
#   2. 利用者ごとにDBを分ける前、鍵はサーバー既定のDBに入っていた。あとから
#      自分のDBを繋ぐと、読む先がそちらに変わるので、前に入れた鍵が見えなくなる。
#      消えたのではなく、前の場所に取り残されている。
#
# ついでに見つけた漏れも、ここで固定する。
#
#   3. 保存先が無い利用者の set_key が os.environ[name] = value を実行していた。
#      その鍵はサーバー全体の既定値になり、保存先を持たない別の利用者の
#      get_key のフォールバックで使われてしまう。

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import keychain


class FakeDB:
    """api_keys の表を1つ持つ、最小の偽Supabase。"""

    def __init__(self, writable=True, rows=None):
        self.rows = list(rows or [])
        self.writable = writable

    def table(self, name):
        assert name == "api_keys"
        return _Q(self)


class NoTable(FakeDB):
    """繋がってはいるが、表がまだ無いDB（SQLを流し忘れた人が落ちる場所）。"""

    def __init__(self):
        super().__init__(writable=False)


class _Q:
    def __init__(self, db):
        self.db, self._op, self._name, self._row = db, "select", None, None

    def select(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def eq(self, col, val): self._name = val; return self
    def upsert(self, row): self._op, self._row = "upsert", dict(row); return self
    def delete(self): self._op = "delete"; return self

    def execute(self):
        if not self.db.writable:
            raise RuntimeError('relation "public.api_keys" does not exist')
        if self._op == "upsert":
            for r in self.db.rows:
                if r.get("name") == self._row.get("name"):
                    r.update(self._row)
                    break
            else:
                self.db.rows.append(self._row)
            return type("R", (), {"data": [self._row]})()
        if self._op == "delete":
            self.db.rows = [r for r in self.db.rows if r.get("name") != self._name]
            return type("R", (), {"data": []})()
        rows = self.db.rows
        if self._name is not None:
            rows = [r for r in rows if r.get("name") == self._name]
        return type("R", (), {"data": [dict(r) for r in rows]})()


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    """毎回まっさらから。鍵は環境変数にもプロセスにも残さない。

    暗号化のシークレットも入れる。素の環境では暗号化なし（平文）に縮退する
    仕様なので、そのままだと「DBに平文が残らないこと」を確かめられない。
    """
    monkeypatch.setattr(config, "KEYCHAIN_SECRET", "test-secret-for-keychain")
    monkeypatch.setattr(keychain, "_fernet_cache", None)
    monkeypatch.setattr(keychain, "_fernet_tried", False)

    keychain._mem_keys.clear()
    for n in ("GITHUB_TOKEN", "DEMO_KEY", "OTHER_KEY"):
        os.environ.pop(n, None)
    yield
    keychain._mem_keys.clear()
    for n in ("GITHUB_TOKEN", "DEMO_KEY", "OTHER_KEY"):
        os.environ.pop(n, None)
    keychain._fernet_cache = None
    keychain._fernet_tried = False


def _bound(client):
    """このリクエストの保存先を差し替えるコンテキスト。"""
    class _C:
        def __enter__(self_): self_.t = config.bind_request_client(client); return client
        def __exit__(self_, *a): config.reset_request_client(self_.t)
    return _C()


# ── 1. 書けなかったのに「保存しました」と言わない ────────────────────

def test_set_key_reports_failure_when_table_missing():
    with _bound(NoTable()):
        res = keychain.set_key("GITHUB_TOKEN", "ghp_example_value_123456")

    assert res.get("persisted") is False, "表が無いのに保存できたことになっている"
    assert res.get("where") == "memory"
    assert "消え" in (res.get("warning") or ""), "消えることが伝わらない"


def test_set_key_reports_success_when_it_really_saved():
    db = FakeDB()
    with _bound(db):
        res = keychain.set_key("GITHUB_TOKEN", "ghp_example_value_123456")

    assert res.get("persisted") is True
    assert res.get("where") == "db"
    assert res.get("warning") is None
    assert [r["name"] for r in db.rows] == ["GITHUB_TOKEN"]
    assert db.rows[0]["value"] != "ghp_example_value_123456", "平文で保存されている"


def test_unsaved_key_is_not_shown_as_saved():
    """書けなかった鍵は、一覧でも「一時」と出る。"""
    with _bound(NoTable()) as db:
        keychain.set_key("GITHUB_TOKEN", "ghp_example_value_123456")
        # 同じクライアントのまま読み直す（実際のリクエストと同じ流れ）
        assert keychain.get_key("GITHUB_TOKEN") == "ghp_example_value_123456"
        assert keychain.resolve_key("GITHUB_TOKEN")[1] == "memory"
        item = next(k for k in keychain.list_keys() if k["name"] == "GITHUB_TOKEN")
    assert item["set"] is True
    assert item["persisted"] is False, "消える鍵が「保存済み」に見えている"


def test_saved_key_survives_a_new_client_on_the_same_database():
    """更新でプロセスが入れ替わっても、DBに書けていれば読み直せる。"""
    store = [{"name": "GITHUB_TOKEN", "value": keychain._encrypt("ghp_example_value_123456")}]
    with _bound(FakeDB(rows=store)):
        assert keychain.get_key("GITHUB_TOKEN") == "ghp_example_value_123456"
    # 再起動を模す: クライアントを作り直しても、同じ中身から読める
    with _bound(FakeDB(rows=store)):
        v, where = keychain.resolve_key("GITHUB_TOKEN")
    assert v == "ghp_example_value_123456"
    assert where == "db"


# ── 2. 前の保存先に取り残された鍵 ────────────────────────────────────

def test_orphaned_keys_finds_what_the_old_location_still_holds(monkeypatch):
    old = FakeDB(rows=[
        {"name": "GITHUB_TOKEN", "value": keychain._encrypt("ghp_old_value_1234")},
        {"name": "DEMO_KEY", "value": keychain._encrypt("demo-1234")},
    ])
    monkeypatch.setattr(config, "default_supabase", lambda: old)

    mine = FakeDB(rows=[{"name": "DEMO_KEY", "value": keychain._encrypt("demo-mine")}])
    with _bound(mine):
        found = keychain.orphaned_keys()

    names = [i["name"] for i in found["items"]]
    assert found["available"] is True
    assert names == ["GITHUB_TOKEN"], "自分のDBに既にある鍵まで移そうとしている"
    assert "ghp_old_value_1234" not in str(found), "値そのものを返している"


def test_rescue_copies_the_key_into_the_current_database(monkeypatch):
    old = FakeDB(rows=[{"name": "GITHUB_TOKEN", "value": keychain._encrypt("ghp_old_value_1234")}])
    monkeypatch.setattr(config, "default_supabase", lambda: old)

    mine = FakeDB()
    with _bound(mine):
        res = keychain.rescue_keys(["GITHUB_TOKEN"])
        assert keychain.get_key("GITHUB_TOKEN") == "ghp_old_value_1234"

    assert res["moved"] == ["GITHUB_TOKEN"]
    assert [r["name"] for r in mine.rows] == ["GITHUB_TOKEN"]
    assert [r["name"] for r in old.rows] == ["GITHUB_TOKEN"], "元から消してしまっている"

    # 移したあとは、取り残しとして出てこない
    with _bound(mine):
        assert keychain.orphaned_keys()["available"] is False


def test_rescue_never_moves_server_only_settings(monkeypatch):
    """暗号鍵や管理用DBの設定は移さない（差し替えられると乗っ取りになる）。"""
    old = FakeDB(rows=[
        {"name": "SUPABASE_SERVICE_KEY", "value": keychain._encrypt("service-secret")},
        {"name": "GITHUB_TOKEN", "value": keychain._encrypt("ghp_old_value_1234")},
    ])
    monkeypatch.setattr(config, "default_supabase", lambda: old)

    mine = FakeDB()
    with _bound(mine):
        res = keychain.rescue_keys()
        found = keychain.orphaned_keys()

    assert res["moved"] == ["GITHUB_TOKEN"]
    assert [i["name"] for i in found["items"]] == []
    assert "SUPABASE_SERVICE_KEY" not in [r["name"] for r in mine.rows]


def test_no_orphans_when_the_current_database_is_the_old_one(monkeypatch):
    """持ち主がサーバー既定のまま使っているときは、移す話が出ない。"""
    same = FakeDB(rows=[{"name": "GITHUB_TOKEN", "value": keychain._encrypt("ghp_x")}])
    monkeypatch.setattr(config, "default_supabase", lambda: same)
    with _bound(same):
        assert keychain.orphaned_keys()["available"] is False


# ── 3. 未接続の人の鍵が、サーバー全体に漏れない ──────────────────────

def test_key_from_a_user_without_storage_never_becomes_the_server_default():
    """保存先が無い利用者の鍵は、受け付けずに理由を返す。

    ここで os.environ に書くと、その鍵がサーバー共通の既定値になり、
    保存先を持たない別の利用者のリクエストでも使われてしまう。
    """
    with _bound(None):                      # 本人は分かるが、保存先が無い
        res = keychain.set_key("GITHUB_TOKEN", "ghp_employee_secret")

    assert res.get("error"), "保存先が無いのに受け付けている"
    assert res.get("needs_storage") is True
    assert "GITHUB_TOKEN" not in os.environ, "他の利用者にも効く場所に書かれた"
    assert keychain.get_key("GITHUB_TOKEN") == ""


def test_single_user_setup_still_works_but_says_it_is_temporary():
    """1人運用（利用者を特定していない構成）は、これまで通り動く。"""
    res = keychain.set_key("DEMO_KEY", "demo-1234")
    assert res.get("ok") is True
    assert keychain.get_key("DEMO_KEY") == "demo-1234"
    assert res.get("persisted") is False
    assert res.get("where") == "memory"
    assert "更新" in (res.get("warning") or "")


def test_server_env_key_is_reported_as_server_not_as_saved():
    """管理者が環境変数で入れた鍵は「サーバー設定」と出る（利用者は消せない）。"""
    os.environ["DEMO_KEY"] = "from-render-env"
    with _bound(FakeDB()):
        v, where = keychain.resolve_key("DEMO_KEY")
    assert v == "from-render-env"
    assert where == "server"
