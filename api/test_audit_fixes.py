# test_audit_fixes.py — 全体調査で見つかった不具合を、戻らないように留める
#
# どれも「画面には問題なく見えるが、実際は違うことが起きている」型。
# 目で見ても気づけないので、テストで押さえる。

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import main as main_mod
import migrate
import watch
from main import app

client = TestClient(app)


class _FakeClient:
    """自分のSupabaseを繋いでいる利用者（中身は空でよい）。"""
    def table(self, _name):
        class Q:
            def select(self, *a, **k): return self
            def eq(self, *a, **k): return self
            def limit(self, *a, **k): return self
            def order(self, *a, **k): return self
            def insert(self, *a, **k): return self
            def upsert(self, *a, **k): return self
            def update(self, *a, **k): return self
            def delete(self, *a, **k): return self
            def execute(self):
                class R:
                    data: list = []
                return R()
        return Q()


# ── 1. 他人のDBを、自分のDBとして見せない ────────────────────────────
def test_a_tenant_never_gets_the_servers_database_url(monkeypatch):
    """SUPABASE_DB_URL は「鍵」ではなく「保存先そのもの」。

    自分のDBを繋いでいる人が自分の接続文字列を入れていないとき、サーバー
    （＝持ち主）の接続文字列へ落ちると、2つのことが同時に起きる:
      ・持ち主のDBの表の状況を、自分のDBの状況として見てしまう
        （自分のDBが空でも「テーブルは揃っています」と出る）
      ・「テーブルを作る」で、持ち主のDBに対してDDLが走る
    """
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://owner-db/postgres")

    # 誰にも繋いでいない（1人運用・持ち主）ときは、これまで通りサーバーの値を使う
    assert migrate.db_url() == "postgresql://owner-db/postgres"

    token = config.bind_request_client(_FakeClient())
    try:
        assert config.storage_state() == "personal"
        assert migrate.db_url() == "", "利用者にサーバーのDB接続文字列が渡っている"
    finally:
        config.reset_request_client(token)


def test_a_tenant_with_their_own_db_url_still_gets_it(monkeypatch):
    """自分で入れた接続文字列は、当然そのまま使えること。"""
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://owner-db/postgres")
    import keychain
    monkeypatch.setattr(keychain, "resolve_key",
                        lambda name: ("postgresql://mine/postgres", "db"))
    token = config.bind_request_client(_FakeClient())
    try:
        assert migrate.db_url() == "postgresql://mine/postgres"
    finally:
        config.reset_request_client(token)


def test_migrations_are_skipped_rather_than_run_against_someone_else(monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://owner-db/postgres")
    token = config.bind_request_client(_FakeClient())
    try:
        res = migrate.run_migrations()
        assert res.get("skipped") is True, "他人のDBに対してマイグレーションが走った"
    finally:
        config.reset_request_client(token)


# ── 2. 保存先が無いのに「保存した」と言わない ────────────────────────
@pytest.fixture
def logged_in_without_storage():
    """ログイン済みだが保存先が無い人（人に配ったときの、いちばん普通の状態）。"""
    async def _user(): return "user-A"
    async def _claims(): return {"sub": "user-A", "email": "a@example.com"}
    app.dependency_overrides[main_mod.current_user] = _user
    app.dependency_overrides[main_mod.current_claims] = _claims
    token = config.bind_request_client(None)
    yield
    config.reset_request_client(token)
    app.dependency_overrides.clear()


@pytest.mark.parametrize("label,path,body", [
    ("タスク", "/tasks", {"title": "x"}),
    ("予定", "/agenda", {"title": "x", "date": "2026-09-05"}),
    # ここから下が今回の抜け。会話から頼むと断るのに、画面からは通っていた。
    ("ボード作成", "/boards", {"name": "x"}),
    ("ボード保存", "/board",
     {"nodes": [{"id": "n1", "type": "note", "x": 0, "y": 0, "text": "メモ"}], "edges": []}),
    ("定期実行", "/scheduler", {"instruction": "毎朝ニュースを送って", "time": "07:00"}),
])
def test_writes_are_refused_when_there_is_nowhere_to_save(
        logged_in_without_storage, label, path, body):
    r = client.post(path, json=body)
    assert r.status_code == 409, f"{label}が、消えるのに受け入れられている"
    assert "保存先" in r.text


def test_the_screen_and_the_agent_agree(logged_in_without_storage):
    """同じことを頼んで、片方は断り片方は受け入れる、が起きないこと。

    「毎朝7時に送って」を会話から頼むと断られるのに、定期実行の画面から
    登録すると通る——という食い違いが実際にあった。
    """
    import tools
    from_agent = tools.execute_tool("schedule_add", {"instruction": "毎朝ニュース", "time": "07:00"})
    from_screen = client.post("/scheduler", json={"instruction": "毎朝ニュース", "time": "07:00"})
    assert "保存先" in from_agent
    assert from_screen.status_code == 409


# ── 3. 画面を開くだけで、外へ繋ぎに行かない ──────────────────────────
@pytest.fixture(autouse=True)
def clean_watch():
    watch._mem_state.clear()
    yield
    watch._mem_state.clear()


def test_opening_the_screen_does_not_reach_out_every_time(monkeypatch):
    """HOMEを開くたびにメール（IMAPログイン）やSlackへ繋ぐと、開くだけで待たされる。"""
    hits = {"n": 0}

    def counted():
        hits["n"] += 1
        return {"ok": True, "items": [{"key": "m1", "title": "見積の件", "detail": ""}]}

    monkeypatch.setattr(watch, "SOURCES",
                        [{"key": "mail", "label": "メール", "collect": counted,
                          "min_interval": 300}])

    first = watch.report()
    assert hits["n"] == 1
    assert first["sources"][0]["items"], "1回目で中身が取れていない"

    second = watch.report()
    assert hits["n"] == 1, "画面を開くたびに外へ繋ぎに行っている"
    assert [i["title"] for i in second["sources"][0]["items"]] == ["見積の件"], \
        "繋がなかったぶん、画面が空になっている"
    assert second["sources"][0]["fresh"] is False       # 今回は見に行っていない印

    # 「今すぐ確認」は、間隔に関係なく本当に見に行く
    watch.report(force=True)
    assert hits["n"] == 2


def test_a_new_item_found_while_viewing_is_still_notified(monkeypatch):
    """画面を開いて拾えた新着が、そのあとの見回りで握りつぶされないこと。

    控えから出すときに一律「新着ではない」としてしまうと、画面を開いた人だけが
    気づけて、通知は永久に来ない、という抜けができる。
    """
    monkeypatch.setattr(watch, "SOURCES", [{
        "key": "mail", "label": "メール", "min_interval": 3600,
        "collect": lambda: {"ok": True, "items": [{"key": "m1", "title": "請求書", "detail": ""}]},
    }])
    sent = []
    import notify
    monkeypatch.setattr(notify, "notify_all", lambda t: (sent.append(t), {"ok": True})[1])

    watch.tick(force=True)          # 見張りを始める（初回は黙る）
    sent.clear()

    # 画面を開いた（ここでは間隔内なので控えを使う）
    watch.report()

    # そのあとの見回り。控えから出した品目でも、新着なら報せること
    monkeypatch.setattr(watch, "SOURCES", [{
        "key": "mail", "label": "メール", "min_interval": 3600,
        "collect": lambda: {"ok": True, "items": [
            {"key": "m1", "title": "請求書", "detail": ""},
            {"key": "m2", "title": "新しいメール", "detail": ""}]},
    }])
    res = watch.tick(force=True)
    assert res["notified"] is True and "新しいメール" in sent[-1]


def test_viewing_does_not_mark_things_as_already_seen(monkeypatch):
    """画面をちらっと開いただけで新着が消えないこと。"""
    monkeypatch.setattr(watch, "SOURCES", [{
        "key": "mail", "label": "メール", "min_interval": 0,
        "collect": lambda: {"ok": True, "items": [{"key": "m1", "title": "請求書", "detail": ""}]},
    }])
    watch.report()
    watch.report()
    st = watch._load("mail")
    assert st["seen"] == [], "画面に出しただけで「見たこと」にされている"
    assert st["started"] is False


def test_an_unconfigured_source_stays_unconfigured_from_the_cache(monkeypatch):
    """未設定を控えから出すとき、「読めている」に化けないこと。"""
    monkeypatch.setattr(watch, "SOURCES", [{
        "key": "slack", "label": "Slack", "min_interval": 3600,
        "collect": lambda: {"ok": False, "skipped": True, "error": "Slackの読み取りが未設定です"},
    }])
    watch.report()
    again = watch.report()["sources"][0]
    assert again["setup_needed"] is True and again["ok"] is False
    assert "未設定" in again["error"]


def test_a_failing_source_stays_failing_from_the_cache(monkeypatch):
    """読めなかったことも控えから正しく出ること（「異常なし」に化けない）。"""
    monkeypatch.setattr(watch, "SOURCES", [{
        "key": "mail", "label": "メール", "min_interval": 3600,
        "collect": lambda: {"ok": False, "error": "ログインを拒否されました"},
    }])
    watch.report()
    again = watch.report()
    assert again["sources"][0]["ok"] is False
    assert "ログインを拒否されました" in again["text"]
    assert "見に行けなかった" in again["text"]


# ── 4. AIの出力崩れへの強さを、モード間で揃える ──────────────────────
# 同じ役目の _extract_json が10モジュールにあり、実装が7種類に分かれていた。
# 実際に崩れたJSONを食わせると、末尾カンマ（AIがよく出す）で6モジュールが
# 失敗し、3モジュールだけが復帰できた。「予定登録は失敗しやすいがスライドは
# 成功しやすい」という差が、機能ではなく写し間違いから出ていた。
import jsonout

_WOBBLE = [
    ("フェンス", '```json\n{"a":1}\n```', {"a": 1}),
    ("フェンスなし・前置き付き", 'はい、作りました。\n{"a":1}', {"a": 1}),
    ("後書き付き", '{"a":1}\nご確認ください。', {"a": 1}),
    ("末尾カンマ", '{"a":1,}', {"a": 1}),
    ("入れ子の末尾カンマ", '```json\n{"a":[1,2,],"b":{"c":1,},}\n```', {"a": [1, 2], "b": {"c": 1}}),
    ("本文に波括弧が入る", '{"code":"function f(){ return {x:1}; }"}',
     {"code": "function f(){ return {x:1}; }"}),
    ("本文の波括弧＋後書き", '{"code":"if (a) { b(); }"}\nこれで動きます。{参考}',
     {"code": "if (a) { b(); }"}),
    ("フェンスの中に前置き", '```json\nこれです\n{"a":1}\n```', {"a": 1}),
]


@pytest.mark.parametrize("label,text,want", _WOBBLE)
def test_json_extraction_survives_the_usual_wobble(label, text, want):
    assert jsonout.extract(text) == want, label


def test_json_extraction_gives_up_rather_than_inventing():
    """読めないものを、それらしい形にでっち上げないこと。"""
    for text in ("すみません、できません", "", "   ", "{壊れている"):
        assert jsonout.extract(text) is None


def test_json_extraction_respects_strings_when_matching_braces():
    """文字列の中の括弧で切らないこと（CODEモードの本文で実際に起きる）。"""
    src = '{"file":"a.js","code":"const o = {\\"k\\": \\"}\\"};"}'
    got = jsonout.extract(src)
    assert got and got["file"] == "a.js" and got["code"].endswith(';')


@pytest.mark.parametrize("module_name", [
    "agenda", "code_agent", "evolve", "income", "life", "pseo", "slides", "sns", "video_script",
])
def test_every_mode_uses_the_same_extractor(module_name):
    """どのモードでも同じだけ粘ること（片方だけ失敗する、を作らない）。"""
    import importlib
    fn = getattr(importlib.import_module(module_name), "_extract_json")
    assert fn('{"a":1,}'), f"{module_name} が末尾カンマで落ちている"
    assert fn('はい。\n{"a":1}\n以上です。'), f"{module_name} が前後の説明で落ちている"
    assert not fn("すみません、できません"), f"{module_name} が読めないものを受け入れている"
