# test_board_auto.py — ⑨ BOARD：自動化を時刻で回せるようにした分の検証
#
# これまで BOARD の自動化は手動実行しかできず、UIに「毎朝〜する」と
# 書いてあるのに発火する仕組みが無かった。scheduler から automations を
# 回せるようにしたので、その繋ぎを確かめる。

from fastapi.testclient import TestClient

import automations
import flow_engine
import scheduler
from main import app

client = TestClient(app)


def _reset():
    scheduler._mem.clear()
    automations._mem_flows.clear()


# ── 登録 ─────────────────────────────────────────────────────────────
def test_schedule_can_reference_an_automation():
    _reset()
    flow = automations.create_flow("朝の要約", steps=[
        {"type": "ai_generate", "params": {"prompt": "要約"}},
    ])
    s = scheduler.add("", time="07:30", days="mon,wed", automation_id=flow["id"])
    assert s["automation_id"] == flow["id"]
    assert s["time"] == "07:30" and s["days"] == "mon,wed"
    # 指示が空でも、一覧に出る名前は自動で埋める
    assert s["instruction"]


def test_schedule_still_requires_something_to_run():
    _reset()
    assert scheduler.add("", time="08:00").get("error") == "instruction is empty"


def test_plain_instruction_schedule_has_no_automation_id():
    _reset()
    s = scheduler.add("今日の予定を教えて")
    assert "automation_id" not in s


# ── 実行（tick） ─────────────────────────────────────────────────────
def test_tick_runs_the_referenced_automation(monkeypatch):
    _reset()
    flow = automations.create_flow("夜のまとめ", steps=[
        {"type": "ai_generate", "name": "まとめ", "params": {"prompt": "まとめて"}},
    ])
    s = scheduler.add("", time="00:00", automation_id=flow["id"])
    s["last_run"] = ""      # 本日未実行にする

    monkeypatch.setattr(flow_engine.llm, "generate_text", lambda p, **k: "まとめました")
    sent = {}
    import notify
    monkeypatch.setattr(notify, "notify_all", lambda msg: (sent.update(msg=msg), {"ok": True})[1])
    # エージェント経路が呼ばれないことも確かめる
    import agent
    monkeypatch.setattr(agent, "run_stream",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("agentを呼んではいけない")))

    res = scheduler.tick()
    assert res["count"] == 1
    assert "まとめました" in res["ran"][0]["result"]
    # 実行件数の要約が入る（何が動いたか分かるように）
    assert "実行 1" in res["ran"][0]["result"]
    assert "まとめました" in sent["msg"]


def test_tick_reports_automation_errors_without_crashing(monkeypatch):
    _reset()
    s = scheduler.add("", time="00:00", automation_id="no-such-automation")
    s["last_run"] = ""
    import notify
    monkeypatch.setattr(notify, "notify_all", lambda msg: {"ok": True})
    res = scheduler.tick()
    assert res["count"] == 1
    assert "not found" in res["ran"][0]["result"]


def test_tick_still_runs_plain_instructions(monkeypatch):
    _reset()
    s = scheduler.add("今日の天気", time="00:00")
    s["last_run"] = ""
    import agent
    monkeypatch.setattr(agent, "run_stream",
                        lambda *a, **k: iter([{"phase": "final", "text": "晴れです"}]))
    import notify
    monkeypatch.setattr(notify, "notify_all", lambda msg: {"ok": True})
    res = scheduler.tick()
    assert res["ran"][0]["result"] == "晴れです"


def test_scheduled_automation_uses_ai_and_knowledge(monkeypatch):
    """時刻実行でも、ステップの担当AIと根拠資料がちゃんと効く。"""
    _reset()
    import studio
    import vault
    studio._mem_ais.clear()
    ai = studio.create_ai("窓口さん", persona="丁寧に案内します。")
    monkeypatch.setattr(vault, "_load_docs", lambda nb: ({"規則": "有給は20日"}, None))
    flow = automations.create_flow("定時案内", steps=[
        {"type": "ai_generate", "params": {"prompt": "案内文を書く"},
         "ai_id": ai["id"], "notebook_id": "nb1"},
    ])
    s = scheduler.add("", time="00:00", automation_id=flow["id"])
    s["last_run"] = ""
    seen = {}
    monkeypatch.setattr(flow_engine.llm, "generate_text",
                        lambda p, **k: (seen.update(p=p), "案内文")[1])
    import notify
    monkeypatch.setattr(notify, "notify_all", lambda msg: {"ok": True})
    scheduler.tick()
    assert "窓口さん" in seen["p"] and "有給は20日" in seen["p"]


# ── エンドポイント ───────────────────────────────────────────────────
def test_scheduler_endpoint_accepts_automation_id():
    _reset()
    flow = automations.create_flow("f", steps=[{"type": "notify", "params": {"message": "x"}}])
    r = client.post("/scheduler", json={"instruction": "", "time": "09:00",
                                        "days": "daily", "automation_id": flow["id"]})
    assert r.status_code == 200 and r.json()["automation_id"] == flow["id"]
    items = client.get("/scheduler").json()["items"]
    assert any(i.get("automation_id") == flow["id"] for i in items)
