# test_memory_speed.py — 返答が始まるまでの往復を数える
#
# 記憶の想起は「返事を書き始める前」に終わらせる必要があるので、ここでの
# 往復はそのまま利用者の待ち時間になる。速さは環境で揺れて測れないが、
# 「何回ネットワークへ出るか」は数えられる。数が増えたら遅くなったと分かる。
#
# 併せて、速くするための覚え書きが利用者どうしで混ざらないことも見る。
# ここが壊れると、他人の記憶で答える事故になる。

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import memory_store


class FakeQuery:
    """table(...).select(...)... の連鎖を受け止めて、最後に行を返す。"""

    def __init__(self, client):
        self._c = client

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self

    def execute(self):
        self._c.calls.append("select")
        return type("R", (), {"data": list(self._c.rows)})()

    def insert(self, row):
        self._c.rows.insert(0, row)
        self._c.calls.append("insert")
        return type("Ins", (), {"execute": lambda _s: None})()


class FakeClient:
    """Supabase クライアントの代わり。出ていった回数を数える。"""

    def __init__(self, rpc_works=True, rows=None):
        self.calls = []
        self.rows = rows if rows is not None else [
            {"role": "user", "content": "牛乳を買う", "importance": 0},
            {"role": "fact", "content": "毎朝7時に起きる", "importance": 1},
        ]
        self.rpc_works = rpc_works

    def table(self, _name):
        return FakeQuery(self)

    def rpc(self, _name, _params):
        self.calls.append("rpc")
        if not self.rpc_works:
            raise RuntimeError('function "match_memories" does not exist')
        rows = list(self.rows)      # そのDBの中身を返す（取り違えを検出するため）
        return type("R", (), {"execute": lambda _s: type("E", (), {"data": rows})()})()


@pytest.fixture
def embeds(monkeypatch):
    """埋め込み（Gemini往復）の回数を数える。"""
    n = {"count": 0}

    def fake_embed(text):
        n["count"] += 1
        return [0.1] * 8

    monkeypatch.setattr(memory_store, "embed", fake_embed)
    return n


def _bind(monkeypatch, client):
    monkeypatch.setattr(memory_store, "get_supabase", lambda: client)


# ── RPC が無い環境（多くの人がこれ）──────────────────────────────
def test_missing_rpc_is_only_probed_once(monkeypatch, embeds):
    """match_memories が無いと分かったら、以降は埋め込みもRPCも呼ばない。

    直す前は毎メッセージごとに「Gemini往復 + 落ちるRPC」を払っていた。
    """
    c = FakeClient(rpc_works=False)
    _bind(monkeypatch, c)

    memory_store.mem_recall("牛乳", limit=4)
    assert embeds["count"] == 1                    # 1回目は試す
    assert c.calls.count("rpc") == 1

    for _ in range(5):
        memory_store.mem_recall("牛乳", limit=4)
    assert embeds["count"] == 1, "RPCが無いのに毎回ベクトル化している"
    assert c.calls.count("rpc") == 1, "無いと分かったRPCを呼び続けている"


def test_rows_are_not_refetched_for_every_message(monkeypatch, embeds):
    """会話が続く間、同じ行を毎回取りに行かない。"""
    c = FakeClient(rpc_works=False)
    _bind(monkeypatch, c)

    for _ in range(5):
        memory_store.mem_recall("牛乳", limit=4)
    assert c.calls.count("select") == 1, "毎メッセージで記憶を取り直している"


def test_answers_still_contain_the_memories(monkeypatch, embeds):
    """速くしても、思い出す中身は変わらないこと。"""
    c = FakeClient(rpc_works=False)
    _bind(monkeypatch, c)
    out = memory_store.mem_recall("牛乳", limit=4)
    assert "牛乳を買う" in out and "毎朝7時に起きる" in out


def test_no_embeddings_are_written_when_nothing_can_read_them(monkeypatch, embeds):
    """RPCが無い間は、読む相手のいないベクトルを毎ターン作らない。

    1ターンにつき2回（発言＋返答）のGemini往復ぶん、無料枠と時間を使っていた。
    """
    c = FakeClient(rpc_works=False)
    _bind(monkeypatch, c)
    memory_store.mem_recall("牛乳", limit=4)     # ここでRPCが無いと分かる
    before = embeds["count"]

    memory_store.mem_add("user", "明日15時に歯医者")
    memory_store.mem_add("assistant", "登録しました")
    assert embeds["count"] == before, "使われないベクトルを作り続けている"
    # 保存自体は行われていること
    assert c.calls.count("insert") == 2


def test_embeddings_are_written_while_semantic_search_works(monkeypatch, embeds):
    c = FakeClient(rpc_works=True)
    _bind(monkeypatch, c)
    memory_store.mem_recall("牛乳", limit=4)
    before = embeds["count"]
    memory_store.mem_add("user", "明日15時に歯医者")
    assert embeds["count"] == before + 1
    assert "embedding" in c.rows[0]


def test_writing_a_memory_drops_the_cache(monkeypatch, embeds):
    """書いた直後に、古い一覧のまま答えないこと。"""
    c = FakeClient(rpc_works=False)
    _bind(monkeypatch, c)
    memory_store.mem_recall("牛乳", limit=4)
    assert "歯医者" not in memory_store.mem_recall("牛乳", limit=4)

    memory_store.mem_add("user", "明日15時に歯医者")
    assert "歯医者" in memory_store.mem_recall("歯医者", limit=4)


# ── RPC がある環境 ────────────────────────────────────────────────
def test_semantic_search_is_used_when_available(monkeypatch, embeds):
    c = FakeClient(rpc_works=True)
    _bind(monkeypatch, c)
    out = memory_store.mem_recall("牛乳", limit=4)
    assert "牛乳を買う" in out
    assert c.calls.count("rpc") == 1
    assert c.calls.count("select") == 0, "意味検索で足りているのに全件も取っている"


# ── 利用者どうしで混ざらないこと（ここが壊れると事故）──────────────
def test_notes_do_not_leak_between_users(monkeypatch, embeds):
    """速くするための覚え書きは、その人のDBだけに紐づくこと。"""
    a = FakeClient(rpc_works=False, rows=[{"role": "user", "content": "Aさんの秘密", "importance": 0}])
    b = FakeClient(rpc_works=True, rows=[{"role": "user", "content": "Bさんの秘密", "importance": 0}])

    _bind(monkeypatch, a)
    out_a = memory_store.mem_recall("秘密", limit=4)
    assert "Aさんの秘密" in out_a

    _bind(monkeypatch, b)
    out_b = memory_store.mem_recall("秘密", limit=4)
    assert "Bさんの秘密" in out_b
    assert "Aさんの秘密" not in out_b, "他人の記憶が混ざっている"
    # AでRPCが無かったことをBに持ち込まない（BのRPCは呼ばれるはず）
    assert b.calls.count("rpc") == 1

    _bind(monkeypatch, a)
    assert "Bさんの秘密" not in memory_store.mem_recall("秘密", limit=4)


def test_no_supabase_is_still_free_and_safe(monkeypatch, embeds):
    _bind(monkeypatch, None)
    assert memory_store.mem_recall("なにか") == ""
    assert embeds["count"] == 0, "DBが無いのにベクトル化している"


# ── 「入っていない鍵」を毎回DBまで見に行かないこと ────────────────
def test_absent_keys_are_not_looked_up_every_time(monkeypatch):
    """未設定の鍵のために毎回Supabaseへ問い合わせない。

    会話を始めるたびに HUGGINGFACE_TOKEN と LLM_PROVIDER を見に行くので、
    未設定だと「無いと分かるだけの往復」が返事の前に何度も入っていた。
    """
    import keychain

    c = FakeClient()
    c.rows = []                                   # api_keys は空＝鍵は無い
    monkeypatch.setattr(keychain.config, "get_supabase", lambda: c)
    monkeypatch.delenv("HUGGINGFACE_TOKEN", raising=False)
    keychain._mem_keys.pop("HUGGINGFACE_TOKEN", None)

    for _ in range(6):
        assert keychain.get_key("HUGGINGFACE_TOKEN") == ""
    assert c.calls.count("select") == 1, "無い鍵を毎回DBまで見に行っている"


def test_saving_a_key_takes_effect_immediately(monkeypatch):
    """速くするための記憶が、鍵を入れた直後の反映を邪魔しないこと。"""
    import keychain

    c = FakeClient()
    c.rows = []
    monkeypatch.setattr(keychain.config, "get_supabase", lambda: c)
    monkeypatch.delenv("HUGGINGFACE_TOKEN", raising=False)
    keychain._mem_keys.pop("HUGGINGFACE_TOKEN", None)

    assert keychain.get_key("HUGGINGFACE_TOKEN") == ""      # 無いと覚える
    keychain.set_key("HUGGINGFACE_TOKEN", "hf_test123")
    assert keychain.get_key("HUGGINGFACE_TOKEN") == "hf_test123"
    keychain.delete_key("HUGGINGFACE_TOKEN")
    keychain._mem_keys.pop("HUGGINGFACE_TOKEN", None)


def test_key_notes_do_not_leak_between_users(monkeypatch):
    """「鍵が無い」の記憶を他の人へ持ち込まないこと。"""
    import keychain

    a, b = FakeClient(), FakeClient()
    a.rows, b.rows = [], []
    monkeypatch.delenv("SOME_KEY", raising=False)
    keychain._mem_keys.pop("SOME_KEY", None)

    monkeypatch.setattr(keychain.config, "get_supabase", lambda: a)
    keychain.get_key("SOME_KEY")
    assert a.calls.count("select") == 1

    monkeypatch.setattr(keychain.config, "get_supabase", lambda: b)
    keychain.get_key("SOME_KEY")
    assert b.calls.count("select") == 1, "他の人の『無い』を鵜呑みにしている"


# ── 途中のプロキシに溜め込まれないこと ────────────────────────────
def test_streaming_replies_are_not_buffered_by_proxies():
    """SSE に素通し指示が付いていること。

    これが無いと、nginx系のプロキシが応答を貯めてから流すことがあり、
    「しばらく無反応 → 突然まとめて出る」という遅さになる。
    """
    from fastapi.testclient import TestClient

    import main as main_mod

    client = TestClient(main_mod.app)
    with client.stream("POST", "/chat", json={"message": "こんにちは", "history": []}) as r:
        assert r.status_code == 200
        assert r.headers.get("x-accel-buffering") == "no"
        assert "no-transform" in (r.headers.get("cache-control") or "")
        assert r.headers["content-type"].startswith("text/event-stream")


# ── ログインした瞬間に全部401、を防ぐ ──────────────────────────────
# フロントはログインすると Authorization に Supabase の JWT を載せる。
# サーバーが SUPABASE_JWT_SECRET を持たない構成だと検証できず、
# APP_TOKEN 時代から動いていたアプリが「ログインした途端に壊れる」。
# 移行中でも動くよう、共通トークンを別ヘッダでも受け取る。
def test_logging_in_does_not_break_a_server_that_only_knows_app_token(monkeypatch):
    from fastapi.testclient import TestClient

    import config as cfg
    import main as main_mod

    monkeypatch.setattr(cfg, "APP_TOKEN", "legacy-shared-token")
    monkeypatch.setattr(cfg, "SUPABASE_JWT_SECRET", "")     # まだ設定していない
    monkeypatch.setattr(cfg, "REQUIRE_AUTH", True)
    c = TestClient(main_mod.app)

    # ログイン後: Authorization は JWT（このサーバーには検証できない）
    only_jwt = c.get("/tasks", headers={"Authorization": "Bearer some.supabase.jwt"})
    assert only_jwt.status_code == 401           # これだけだと通らない（従来どおり）

    # フロントは共通トークンも別ヘッダで添えるので、通る
    both = c.get("/tasks", headers={
        "Authorization": "Bearer some.supabase.jwt",
        "X-App-Token": "legacy-shared-token",
    })
    assert both.status_code == 200, "ログインすると使えなくなってしまう"

    # 間違ったトークンは通さない
    wrong = c.get("/tasks", headers={
        "Authorization": "Bearer some.supabase.jwt",
        "X-App-Token": "not-the-token",
    })
    assert wrong.status_code == 401


def test_app_token_header_is_ignored_when_no_app_token_is_configured(monkeypatch):
    """APP_TOKEN を外したら、このヘッダでは通れないこと。"""
    from fastapi.testclient import TestClient

    import config as cfg
    import main as main_mod

    monkeypatch.setattr(cfg, "APP_TOKEN", "")
    monkeypatch.setattr(cfg, "SUPABASE_JWT_SECRET", "secret")
    monkeypatch.setattr(cfg, "REQUIRE_AUTH", True)
    c = TestClient(main_mod.app)
    assert c.get("/tasks", headers={"X-App-Token": "anything"}).status_code == 401


# ── 「使えない理由」を取り違えないこと ────────────────────────────
def test_database_reason_distinguishes_signed_out_from_unverifiable(monkeypatch):
    """ログイン済みの人に「ログインしていません」と言わないこと。"""
    from fastapi.testclient import TestClient

    import config as cfg
    import main as main_mod

    monkeypatch.setattr(cfg, "APP_TOKEN", "")
    monkeypatch.setattr(cfg, "REQUIRE_AUTH", False)
    monkeypatch.setattr(cfg, "SUPABASE_JWT_SECRET", "")
    c = TestClient(main_mod.app)

    out = c.get("/account/database").json()
    assert "ログインしていない" in out["reason"]

    # ログインしているのにサーバーが確認できない場合は、そう言う
    signed = c.get("/account/database",
                   headers={"Authorization": "Bearer some.jwt"}).json()
    assert "ログインしていない" not in signed["reason"]
    assert "SUPABASE_JWT_SECRET" in signed["reason"]
