# test_hooks.py — 外から AIbou を動かす入口の検証
#
# なぜ作ったか:
#   無料プランのサーバーは寝るので、内側のループだけでは定期実行が飛ぶ。
#   外から叩いてもらうのが確実で、しかも「外から叩ける」こと自体が拡張性になる。
#   iOSショートカット・スプレッドシートのスクリプト・IFTTT・各自のSupabase
#   （pg_cron）から、自分の自動化を起こせる。どれも無料。
#
# ここで確かめたいのは、ほぼ全部が安全側の話:
#   ・URLを1つ知られただけで何でもできる、になっていないこと
#   ・合言葉を偽造できないこと
#   ・他人の自動化を動かせないこと
#   ・叩かれたとき、その人の保存先と鍵で動くこと

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import hooks as hooks_mod
import tenancy
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean():
    hooks_mod._mem.clear()
    tenancy._mem_rows.clear()
    tenancy._clients.clear()
    yield
    hooks_mod._mem.clear()
    tenancy._mem_rows.clear()
    tenancy._clients.clear()


# ── 合言葉 ───────────────────────────────────────────────────────
def test_a_token_round_trips():
    h = hooks_mod.create("u-1", "auto-1", "毎朝の要約")
    assert h["ok"] is True
    assert hooks_mod.parse_token(h["token"])


def test_a_token_cannot_be_forged():
    """署名が無いと、適当なidを名乗って他人の自動化を動かせてしまう。"""
    assert hooks_mod.parse_token("someone-elses-id.0000000000000000") == ""
    assert hooks_mod.parse_token("someone-elses-id") == ""
    assert hooks_mod.parse_token("") == ""


def test_a_tampered_token_is_rejected():
    h = hooks_mod.create("u-1", "auto-1")
    t = h["token"]
    assert hooks_mod.parse_token(t[:-1] + ("0" if t[-1] != "0" else "1")) == ""


def test_tokens_are_long_enough_to_not_guess():
    h = hooks_mod.create("u-1", "auto-1")
    token_id = h["token"].split(".")[0]
    assert len(token_id) >= 20


def test_two_hooks_never_share_a_token():
    a = hooks_mod.create("u-1", "auto-1")
    b = hooks_mod.create("u-1", "auto-2")
    assert a["token"] != b["token"]


# ── できることを最初から絞る ─────────────────────────────────────
def test_a_hook_must_name_an_automation():
    """任意の命令を実行できる作りにすると、URLが漏れた瞬間に乗っ取られる。"""
    assert "error" in hooks_mod.create("u-1", "")


def test_the_hook_only_knows_one_automation():
    h = hooks_mod.create("u-1", "auto-1", "毎朝")
    row = hooks_mod.find_by_token(h["token"])
    assert row["automation_id"] == "auto-1"
    # 起動側が別の自動化を指定する余地は無い（引数を受け取らない）
    assert "instruction" not in row


# ── 実際に叩く ───────────────────────────────────────────────────
def test_firing_runs_that_automation(monkeypatch):
    ran = []
    import automations
    monkeypatch.setattr(automations, "run_flow",
                        lambda fid: ran.append(fid) or {"name": "毎朝", "ran": 1})

    h = hooks_mod.create("", "auto-1", "毎朝")
    r = client.post(f"/hook/{h['token']}")
    assert r.status_code == 200, r.text
    assert ran == ["auto-1"]


def test_an_unknown_token_is_a_plain_404(monkeypatch):
    """存在しないのか合言葉が違うのかを区別すると、総当たりの手掛かりになる。"""
    r = client.post("/hook/bogus.0000000000000000")
    assert r.status_code == 404
    assert "見つかりませんでした" in r.json()["detail"]


def test_firing_uses_that_persons_database(monkeypatch):
    """外から叩かれるので文脈が無い。ここで差し替えないと、
    自動化がサーバー既定のDBで動き、他人の設定で走る。"""
    seen = []
    import automations

    def fake_run(fid):
        seen.append(config.get_supabase())
        return {"name": "x", "ran": 1}

    monkeypatch.setattr(automations, "run_flow", fake_run)

    mine = object()
    monkeypatch.setattr(tenancy, "client_for", lambda uid: mine if uid == "u-1" else None)

    h = hooks_mod.create("u-1", "auto-1")
    client.post(f"/hook/{h['token']}")
    assert seen == [mine]


def test_the_binding_is_released_after_firing(monkeypatch):
    import automations
    monkeypatch.setattr(automations, "run_flow", lambda fid: {"ran": 1})
    monkeypatch.setattr(tenancy, "client_for", lambda uid: object())

    before = config.storage_is_bound()
    h = hooks_mod.create("u-1", "auto-1")
    client.post(f"/hook/{h['token']}")
    assert config.storage_is_bound() is before


def test_use_is_recorded(monkeypatch):
    """動いていないトリガーに気づけるように、使われた記録を残す。"""
    import automations
    monkeypatch.setattr(automations, "run_flow", lambda fid: {"ran": 1})

    h = hooks_mod.create("", "auto-1")
    client.post(f"/hook/{h['token']}")
    row = hooks_mod.find_by_token(h["token"])
    assert row["uses"] == 1
    assert row["last_used_at"]


def test_a_failing_automation_is_reported(monkeypatch):
    import automations
    monkeypatch.setattr(automations, "run_flow", lambda fid: {"error": "その自動化はありません"})

    h = hooks_mod.create("", "auto-missing")
    r = client.post(f"/hook/{h['token']}")
    assert r.status_code == 400
    assert "ありません" in r.json()["error"]


# ── 一覧と削除 ───────────────────────────────────────────────────
def test_the_list_shows_the_url_again():
    """URLを控え忘れた人が詰まないように、毎回出す。漏れたら作り直せばよい。"""
    h = hooks_mod.create("u-1", "auto-1", "毎朝")
    items = hooks_mod.list_hooks()
    assert items[0]["token"] == h["token"]
    assert items[0]["label"] == "毎朝"


def test_deleting_stops_it(monkeypatch):
    import automations
    monkeypatch.setattr(automations, "run_flow", lambda fid: {"ran": 1})

    h = hooks_mod.create("", "auto-1")
    hooks_mod.delete(h["id"])
    assert client.post(f"/hook/{h['token']}").status_code == 404


# ── 連打よけ ─────────────────────────────────────────────────────
def test_hammering_is_refused(monkeypatch):
    """外に開いた入口なので、URLを知っている人が連打できてしまう。
    1回ごとにAIが動くため、無料枠が一気に削られる。"""
    import automations
    ran = []
    monkeypatch.setattr(automations, "run_flow", lambda fid: ran.append(fid) or {"ran": 1})
    hooks_mod._last_fired.clear()

    h = hooks_mod.create("", "auto-1")
    assert client.post(f"/hook/{h['token']}").status_code == 200
    r2 = client.post(f"/hook/{h['token']}")
    assert r2.status_code == 429
    assert "空けて" in r2.json()["detail"]
    assert len(ran) == 1          # 2回目は本当に動いていない


def test_the_limit_is_per_hook(monkeypatch):
    """1つが連打されても、別のトリガーまで止めない。"""
    import automations
    monkeypatch.setattr(automations, "run_flow", lambda fid: {"ran": 1})
    hooks_mod._last_fired.clear()

    a = hooks_mod.create("", "auto-1")
    b = hooks_mod.create("", "auto-2")
    assert client.post(f"/hook/{a['token']}").status_code == 200
    assert client.post(f"/hook/{b['token']}").status_code == 200


def test_the_limit_is_short_enough_for_real_use(monkeypatch):
    """時報や定期実行の用途を邪魔しない長さであること。
    長くしすぎると、5分ごとのcronすら弾いてしまう。"""
    assert hooks_mod.MIN_INTERVAL_SEC <= 60


def test_after_the_interval_it_runs_again(monkeypatch):
    import automations
    monkeypatch.setattr(automations, "run_flow", lambda fid: {"ran": 1})
    hooks_mod._last_fired.clear()

    h = hooks_mod.create("", "auto-1")
    client.post(f"/hook/{h['token']}")
    # 時間を進める代わりに、記録を消す（時計を待たない）
    hooks_mod._last_fired.clear()
    assert client.post(f"/hook/{h['token']}").status_code == 200
