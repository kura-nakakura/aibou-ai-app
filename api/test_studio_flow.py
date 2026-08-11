# test_studio_flow.py — ⑤ AI STUDIO / ⑥ 共通フローエンジン
#
# 実行部分は flow_engine に1本化してあり、AI STUDIO のワークフローと
# BOARD の自動化の両方がこれを使う。
#
# ワークフローのステップが
#   ・担当のカスタムAIの人格/ルールを実際に使うか
#   ・VAULTのノートブックを根拠資料にできるか（RAG）
#   ・条件で分岐（スキップ）できるか
#   ・{input}/{original}/{stepN} を差し込めるか
# を検証する。LLMはモックするので鍵なしで通る。

from fastapi.testclient import TestClient

import automations
import flow_engine
import studio
from main import app

client = TestClient(app)


def _reset():
    studio._mem_ais.clear()
    studio._mem_workflows.clear()


def _capture(monkeypatch, answers=None):
    """llm.generate_text を差し替えて、渡されたプロンプトを記録する。

    answers を渡すと呼ばれた順に返す（条件判定の YES/NO を仕込むため）。
    """
    seen = []
    seq = list(answers or [])

    def fake(prompt, **kw):
        seen.append(prompt)
        return seq.pop(0) if seq else f"OUT{len(seen)}"

    monkeypatch.setattr(flow_engine.llm, "generate_text", fake)
    return seen


# ── プレースホルダー ─────────────────────────────────────────────────
def test_fill_supports_input_original_and_step_refs():
    out = flow_engine.fill("A={input} B={original} C={step1} D={step2}",
                       "最初", "直前", ["一番目", "二番目"])
    assert out == "A=直前 B=最初 C=一番目 D=二番目"


def test_fill_ignores_out_of_range_step_refs():
    assert flow_engine.fill("x={step9}", "o", "c", ["a"]) == "x="


# ── カスタムAIの適用 ─────────────────────────────────────────────────
def test_step_applies_custom_ai_persona_and_rules(monkeypatch):
    _reset()
    ai = studio.create_ai("校閲さん", persona="厳しい校閲者です。", rules="敬体で書く")
    wf = studio.create_workflow("w", [{"name": "校閲", "prompt": "直して: {input}", "ai_id": ai["id"]}])
    seen = _capture(monkeypatch)
    res = studio.run_workflow(wf["id"], "本文")
    p = seen[0]
    assert "あなたは「校閲さん」です。厳しい校閲者です。" in p
    assert "【必ず守るルール】" in p and "敬体で書く" in p
    assert res["results"][0]["ai"] == "校閲さん"


def test_step_without_ai_has_no_persona_prefix(monkeypatch):
    _reset()
    wf = studio.create_workflow("w", [{"prompt": "やって: {input}"}])
    seen = _capture(monkeypatch)
    res = studio.run_workflow(wf["id"], "入力")
    assert seen[0] == "やって: 入力"
    assert "ai" not in res["results"][0]


def test_unknown_ai_id_is_ignored(monkeypatch):
    _reset()
    wf = studio.create_workflow("w", [{"prompt": "x", "ai_id": "no-such-ai"}])
    _capture(monkeypatch)
    res = studio.run_workflow(wf["id"], "")
    assert res["results"][0].get("skipped") is False and "ai" not in res["results"][0]


# ── ナレッジ（RAG） ──────────────────────────────────────────────────
def test_step_grounds_on_vault_notebook(monkeypatch):
    _reset()
    import vault
    monkeypatch.setattr(vault, "_load_docs", lambda nb: ({"就業規則": "年次有給は20日"}, None))
    wf = studio.create_workflow("w", [{"prompt": "質問: {input}", "notebook_id": "nb1"}])
    seen = _capture(monkeypatch)
    res = studio.run_workflow(wf["id"], "有給は何日?")
    p = seen[0]
    assert "【資料】" in p and "年次有給は20日" in p
    assert "資料には記載がありません" in p          # 資料外を推測させない
    assert res["results"][0]["knowledge"] == "nb1"


def test_missing_knowledge_warns_but_still_runs(monkeypatch):
    """資料が読めなくても止めない（ただし警告を残して黙って通さない）。"""
    _reset()
    import vault
    monkeypatch.setattr(vault, "_load_docs", lambda nb: (None, {"error": "notebook not found"}))
    wf = studio.create_workflow("w", [{"prompt": "やって", "notebook_id": "bad"}])
    _capture(monkeypatch)
    res = studio.run_workflow(wf["id"], "")
    row = res["results"][0]
    assert row["skipped"] is False and row["output"]
    assert "notebook not found" in row["warning"]


def test_empty_notebook_warns(monkeypatch):
    _reset()
    import vault
    monkeypatch.setattr(vault, "_load_docs", lambda nb: ({}, None))
    wf = studio.create_workflow("w", [{"prompt": "やって", "notebook_id": "nb"}])
    _capture(monkeypatch)
    res = studio.run_workflow(wf["id"], "")
    assert "資料がありません" in res["results"][0]["warning"]


# ── 分岐 ─────────────────────────────────────────────────────────────
def test_condition_skips_step(monkeypatch):
    _reset()
    wf = studio.create_workflow("w", [
        {"name": "判定元", "prompt": "分類して: {input}"},
        {"name": "苦情対応", "prompt": "謝罪文を書く", "when": "苦情である"},
        {"name": "まとめ", "prompt": "まとめる: {input}"},
    ])
    # 1) step1本体, 2) step2の条件判定=NO, 3) step3本体
    seen = _capture(monkeypatch, ["分類結果", "NO", "最終"])
    res = studio.run_workflow(wf["id"], "問い合わせ本文")
    rows = res["results"]
    assert rows[0]["skipped"] is False
    assert rows[1]["skipped"] is True and "苦情である" in rows[1]["reason"]
    assert rows[2]["skipped"] is False
    assert res["ran"] == 2 and res["skipped"] == 1
    # スキップされたステップの出力は後続に渡らない（step1の出力が引き継がれる）
    assert "分類結果" in seen[2]
    assert res["final_output"] == "最終"


def test_condition_runs_step_on_yes(monkeypatch):
    _reset()
    wf = studio.create_workflow("w", [{"prompt": "対応する", "when": "苦情である"}])
    _capture(monkeypatch, ["YES", "対応文"])
    res = studio.run_workflow(wf["id"], "怒っています")
    assert res["results"][0]["skipped"] is False and res["final_output"] == "対応文"


def test_ambiguous_condition_runs_and_records_why(monkeypatch):
    """判定が曖昧なら黙って飛ばさず実行する（作った人の意図に近いほう）。"""
    _reset()
    wf = studio.create_workflow("w", [{"prompt": "やる", "when": "条件"}])
    _capture(monkeypatch, ["たぶん？", "出力"])
    res = studio.run_workflow(wf["id"], "")
    row = res["results"][0]
    assert row["skipped"] is False and "曖昧" in row["reason"]


def test_condition_error_runs_step(monkeypatch):
    _reset()
    wf = studio.create_workflow("w", [{"prompt": "やる", "when": "条件"}])
    calls = {"n": 0}

    def flaky(prompt, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return "出力"

    monkeypatch.setattr(flow_engine.llm, "generate_text", flaky)
    res = studio.run_workflow(wf["id"], "")
    assert res["results"][0]["skipped"] is False
    assert "判定できなかった" in res["results"][0]["reason"]


def test_skipped_step_keeps_step_numbering(monkeypatch):
    """飛ばしても {stepN} の番号がずれない。"""
    _reset()
    wf = studio.create_workflow("w", [
        {"prompt": "一番目"},
        {"prompt": "二番目", "when": "満たさない条件"},
        {"prompt": "1番目の出力={step1} 2番目の出力={step2}"},
    ])
    seen = _capture(monkeypatch, ["A", "NO", "C"])
    studio.run_workflow(wf["id"], "")
    assert seen[2] == "1番目の出力=A 2番目の出力="


# ── 全体のふるまい ───────────────────────────────────────────────────
def test_empty_prompt_step_is_skipped_not_crashing(monkeypatch):
    _reset()
    wf = studio.create_workflow("w", [{"prompt": ""}, {"prompt": "本体"}])
    _capture(monkeypatch, ["出力"])
    res = studio.run_workflow(wf["id"], "")
    assert res["results"][0]["skipped"] is True and res["ran"] == 1


def test_run_validation():
    _reset()
    assert studio.run_workflow("no-such-id").get("error") == "workflow not found"
    wf = studio.create_workflow("空", [])
    assert studio.run_workflow(wf["id"]).get("error") == "no steps defined"


def test_generation_failure_stops_the_flow(monkeypatch):
    """生成が失敗したら以降は続けない。

    エラー文字列を {input} として次に渡すと、意味のない出力を作りながら
    APIを消費してしまう。失敗した行に error を残して止めるほうが分かりやすい。
    """
    _reset()
    wf = studio.create_workflow("w", [{"prompt": "壊れる"}, {"prompt": "続く: {input}"}])
    calls = {"n": 0}

    def flaky(prompt, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("model down")
        return "2番目は動いた"

    monkeypatch.setattr(flow_engine.llm, "generate_text", flaky)
    res = studio.run_workflow(wf["id"], "")
    assert res["results"][0]["ok"] is False
    assert "model down" in res["results"][0]["error"]
    assert len(res["results"]) == 1      # 2番目は実行しない
    assert calls["n"] == 1


def test_steps_are_capped(monkeypatch):
    _reset()
    wf = studio.create_workflow("w", [{"prompt": f"s{i}"} for i in range(40)])
    _capture(monkeypatch)
    res = studio.run_workflow(wf["id"], "")
    assert len(res["results"]) == flow_engine.MAX_STEPS


# ── エンドポイント ───────────────────────────────────────────────────
def test_workflow_endpoint_round_trip(monkeypatch):
    _reset()
    ai = client.post("/studio/ais", json={"name": "要約AI", "persona": "簡潔に書く"}).json()
    wf = client.post("/studio/workflows", json={"name": "調査", "steps": [
        {"name": "要約", "prompt": "要約: {input}", "ai_id": ai["id"], "notebook_id": "", "when": ""},
    ]}).json()
    # 追加フィールドが保存されて返ってくる
    assert wf["steps"][0]["ai_id"] == ai["id"]
    _capture(monkeypatch)
    r = client.post(f"/studio/workflows/{wf['id']}/run", json={"input": "長い文章"})
    assert r.status_code == 200
    d = r.json()
    assert d["ran"] == 1 and d["results"][0]["ai"] == "要約AI"


# ── ⑥ 自動化とワークフローが同じエンジンを使う ───────────────────────
def test_automation_steps_can_use_ai_knowledge_and_conditions(monkeypatch):
    """BOARDの自動化でも担当AI・根拠資料・実行条件が効く（同じ実装だから）。"""
    _reset()
    automations._mem_flows.clear()
    import vault
    monkeypatch.setattr(vault, "_load_docs", lambda nb: ({"規則": "有給は20日"}, None))
    ai = studio.create_ai("窓口さん", persona="丁寧に案内します。", rules="敬体で書く")
    flow = automations.create_flow("問い合わせ自動化", steps=[
        {"type": "ai_generate", "name": "回答", "params": {"prompt": "答えて: {input}"},
         "ai_id": ai["id"], "notebook_id": "nb1"},
        {"type": "ai_generate", "name": "苦情対応", "params": {"prompt": "謝罪"},
         "when": "苦情である"},
    ])
    # 拡張フィールドが保存されている
    assert flow["steps"][0]["ai_id"] == ai["id"]
    assert flow["steps"][0]["notebook_id"] == "nb1"
    assert flow["steps"][1]["when"] == "苦情である"

    seen = _capture(monkeypatch, ["案内文", "NO"])
    res = automations.run_flow(flow["id"], "有給は何日?")
    p = seen[0]
    assert "あなたは「窓口さん」です。丁寧に案内します。" in p
    assert "有給は20日" in p
    rows = res["results"]
    assert rows[0]["ai"] == "窓口さん" and rows[0]["knowledge"] == "nb1"
    assert rows[1]["skipped"] is True and res["ran"] == 1 and res["skipped"] == 1


def test_plain_automation_still_works_without_the_new_fields(monkeypatch):
    """従来の単純な自動化（params だけ）がそのまま動く。"""
    _reset()
    automations._mem_flows.clear()
    sent = {}
    made = {}
    monkeypatch.setattr(flow_engine, "_act_notify",
                        lambda text: (sent.update(text=text), {"ok": True})[1])
    monkeypatch.setattr(flow_engine, "_act_create_task",
                        lambda t, c: (made.update(title=t), {"ok": True})[1])
    flow = automations.create_flow("朝の要約", steps=[
        {"type": "ai_generate", "name": "要約", "params": {"prompt": "要約: {input}"}},
        {"type": "notify", "name": "通知", "params": {"message": "できました: {input}"}},
        {"type": "create_task", "name": "タスク", "params": {"title": "確認: {input}"}},
    ])
    _capture(monkeypatch, ["きょうの要約"])
    res = automations.run_flow(flow["id"], "元ネタ")
    assert [r["type"] for r in res["results"]] == ["ai_generate", "notify", "create_task"]
    assert all(r["ok"] for r in res["results"])
    # 通知とタスクにも生成結果が差し込まれる
    assert sent["text"] == "できました: きょうの要約"
    assert made["title"] == "確認: きょうの要約"
    # 通知やタスクは流れを変えない（最終出力は生成結果のまま）
    assert res["final_output"] == "きょうの要約"


def test_action_step_failure_does_not_stop_the_flow(monkeypatch):
    """通知が失敗しても後続は続ける（生成と違い、流れは壊れない）。"""
    _reset()
    automations._mem_flows.clear()
    monkeypatch.setattr(flow_engine, "_act_notify",
                        lambda text: {"ok": False, "error": "LINE未設定"})
    flow = automations.create_flow("f", steps=[
        {"type": "notify", "params": {"message": "しらせる"}},
        {"type": "ai_generate", "params": {"prompt": "つづき"}},
    ])
    _capture(monkeypatch, ["生成できた"])
    res = automations.run_flow(flow["id"], "")
    assert res["results"][0]["ok"] is False and "LINE未設定" in res["results"][0]["error"]
    assert res["results"][1]["ok"] is True and res["final_output"] == "生成できた"


def test_unknown_step_type_is_rejected_at_creation():
    automations._mem_flows.clear()
    flow = automations.create_flow("f", steps=[
        {"type": "launch_missiles", "params": {}},
        {"type": "notify", "params": {"message": "ok"}},
    ])
    assert [s["type"] for s in flow["steps"]] == ["notify"]


def test_step_types_are_shared_between_modules():
    """種別定義が1か所に集まっていること（片方だけ増えてずれないように）。"""
    assert automations.STEP_TYPES == list(flow_engine.STEP_TYPES)
    assert studio.MAX_STEPS == flow_engine.MAX_STEPS


def test_knowledge_reaches_an_answer_buried_in_a_large_notebook(monkeypatch):
    """資料が上限を超える量でも、指示に関係する箇所が渡る。

    以前は先頭から12,000字で切っていたため、後ろに答えがある資料では
    永久に届かなかった。
    """
    _reset()
    import vault
    filler = "\n\n".join(f"無関係な段落 {i} です。社内の一般的な説明。" * 8 for i in range(300))
    docs = {"大きな規程": filler + "\n\n特別休暇は年に3日付与されます。"}
    assert len(docs["大きな規程"]) > flow_engine.KNOWLEDGE_CHARS
    monkeypatch.setattr(vault, "_load_docs", lambda nb: (docs, None))
    wf = studio.create_workflow("w", [{"prompt": "特別休暇は何日ですか？", "notebook_id": "nb1"}])
    seen = _capture(monkeypatch)
    res = studio.run_workflow(wf["id"], "")
    assert "特別休暇は年に3日" in seen[0]
    assert len(seen[0]) < len(docs["大きな規程"])      # 全文は渡していない
    assert "warning" not in res["results"][0]          # 関連が見つかったので警告なし


def test_knowledge_warns_when_nothing_relevant_is_found(monkeypatch):
    """関連が見つからないときは黙って先頭を渡さず、その旨を残す。"""
    _reset()
    import vault
    monkeypatch.setattr(vault, "_load_docs",
                        lambda nb: ({"献立": "月曜はカレー。火曜は魚。"}, None))
    wf = studio.create_workflow("w", [{"prompt": "半導体の製造装置について", "notebook_id": "nb"}])
    _capture(monkeypatch)
    res = studio.run_workflow(wf["id"], "")
    assert "見つかりませんでした" in res["results"][0]["warning"]
