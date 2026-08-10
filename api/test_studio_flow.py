# test_studio_flow.py — ⑤ AI STUDIO（ナレッジ連携・分岐・カスタムAI適用）
#
# ワークフローのステップが
#   ・担当のカスタムAIの人格/ルールを実際に使うか
#   ・VAULTのノートブックを根拠資料にできるか（RAG）
#   ・条件で分岐（スキップ）できるか
#   ・{input}/{original}/{stepN} を差し込めるか
# を検証する。LLMはモックするので鍵なしで通る。

from fastapi.testclient import TestClient

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

    monkeypatch.setattr(studio.llm, "generate_text", fake)
    return seen


# ── プレースホルダー ─────────────────────────────────────────────────
def test_fill_supports_input_original_and_step_refs():
    out = studio._fill("A={input} B={original} C={step1} D={step2}",
                       "最初", "直前", ["一番目", "二番目"])
    assert out == "A=直前 B=最初 C=一番目 D=二番目"


def test_fill_ignores_out_of_range_step_refs():
    assert studio._fill("x={step9}", "o", "c", ["a"]) == "x="


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
    monkeypatch.setattr(vault, "_load_context", lambda nb: ("## 就業規則\n年次有給は20日", None))
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
    monkeypatch.setattr(vault, "_load_context", lambda nb: (None, {"error": "notebook not found"}))
    wf = studio.create_workflow("w", [{"prompt": "やって", "notebook_id": "bad"}])
    _capture(monkeypatch)
    res = studio.run_workflow(wf["id"], "")
    row = res["results"][0]
    assert row["skipped"] is False and row["output"]
    assert "notebook not found" in row["warning"]


def test_empty_notebook_warns(monkeypatch):
    _reset()
    import vault
    monkeypatch.setattr(vault, "_load_context", lambda nb: ("", None))
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

    monkeypatch.setattr(studio.llm, "generate_text", flaky)
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


def test_step_failure_does_not_stop_the_workflow(monkeypatch):
    _reset()
    wf = studio.create_workflow("w", [{"prompt": "壊れる"}, {"prompt": "続く: {input}"}])
    calls = {"n": 0}

    def flaky(prompt, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("model down")
        return "2番目は動いた"

    monkeypatch.setattr(studio.llm, "generate_text", flaky)
    res = studio.run_workflow(wf["id"], "")
    assert "[error:" in res["results"][0]["output"]
    assert res["results"][1]["output"] == "2番目は動いた"


def test_steps_are_capped(monkeypatch):
    _reset()
    wf = studio.create_workflow("w", [{"prompt": f"s{i}"} for i in range(40)])
    _capture(monkeypatch)
    res = studio.run_workflow(wf["id"], "")
    assert len(res["results"]) == studio.MAX_STEPS


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
