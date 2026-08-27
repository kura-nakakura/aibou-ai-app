# test_agent_trace.py — 「いま何をしているか」と「どこで待ったか」が分かること
#
# きっかけ:
#   ルールをGitHubから読む機能を足すと、返事が遅くなるのではないか、という心配。
#
#   もっともな心配で、実際そうなりうる。問題は、これまで画面に
#   「考えています…」としか出ていなかったことだった。遅いと感じても、
#   準備が重いのか、生成が重いのか、ツールが重いのかが分からない。
#   原因が分からなければ、直しようがない。
#
# そこで、
#   ・全部のイベントに ms（その工程にかかった時間）と total_ms を付ける
#   ・返事が始まる前の準備を prepare として1つの工程にする
# を入れた。ここが崩れると、また「なんとなく遅い」に戻る。

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agent
import llm
import tools


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    """生成は呼ばない。ツールを1回使って報告する筋書きを固定で返す。"""
    calls = {"n": 0}

    def _gen(prompt, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return tools.TOOL_CALL_MARKER + '{"tool":"list_state","params":{}}\n現状を見ます'
        return "確認しました。"

    monkeypatch.setattr(llm, "generate_text", _gen)
    monkeypatch.setattr(tools, "execute_tool", lambda name, params: "タスクは3件です")
    return calls


def _run(instruction="今の状況を教えて", **kw):
    return list(agent.run_stream(instruction, **kw))


def test_every_event_carries_its_own_duration():
    evs = _run()
    assert evs, "イベントが1つも出ていない"
    for ev in evs:
        assert "ms" in ev, f"{ev.get('phase')} に ms が無い"
        assert "total_ms" in ev, f"{ev.get('phase')} に total_ms が無い"
        assert ev["ms"] >= 0 and ev["total_ms"] >= 0, "時間が負になっている"


def test_total_never_goes_backwards():
    """合計は必ず増える一方（時計合わせで巻き戻らないこと）。"""
    totals = [ev["total_ms"] for ev in _run()]
    assert totals == sorted(totals), f"合計が巻き戻っている: {totals}"


def test_preparation_is_reported_as_its_own_step():
    """返事が始まる前の工程が、画面に出せる形で流れてくること。

    ここが無いと、記憶やルールの読み込みが重くなったとき、
    利用者からは「ただ遅い」としか見えない。
    """
    evs = _run()
    prep = [e for e in evs if e["phase"] == "prepare"]
    assert prep, "準備の工程が出ていない"
    assert prep[0].get("what"), "何の準備なのかが書かれていない"
    # 準備は「考えます」より先に出ないと、順番として意味が通らない
    assert evs.index(prep[0]) < next(i for i, e in enumerate(evs) if e["phase"] == "thinking")


def test_the_phases_still_come_in_the_expected_order():
    """時間を足したせいで、流れそのものが変わっていないこと。"""
    phases = [e["phase"] for e in _run()]
    assert phases[0] == "start"
    assert phases[-1] == "done"
    assert "tool" in phases and "observation" in phases and "final" in phases
    assert phases.index("tool") < phases.index("observation")


def test_empty_instruction_also_gets_stamped():
    """指示が空で即答するときも、形は同じであること（画面が分岐せずに済む）。"""
    evs = _run("")
    assert [e["phase"] for e in evs] == ["start", "final", "done"]
    for ev in evs:
        assert "ms" in ev and "total_ms" in ev


def test_error_path_is_stamped_too(monkeypatch):
    """生成が失敗したときも、そこまでに何秒かかったかは残る。"""
    def _boom(prompt, **kw):
        raise RuntimeError("生成に失敗しました")

    monkeypatch.setattr(llm, "generate_text", _boom)
    evs = _run()
    phases = [e["phase"] for e in evs]
    assert "error" in phases
    assert phases[-1] == "done", "error のあとに done が来ていない"
    for ev in evs:
        assert "ms" in ev and "total_ms" in ev


def test_approval_pause_is_stamped_too():
    """承認待ちで止まるときも同じ。止まるまでに何秒かかったかが分かる。"""
    def _gen(prompt, **kw):
        return tools.TOOL_CALL_MARKER + '{"tool":"notify","params":{"message":"テスト"}}\n送ります'

    import llm as _llm
    orig = _llm.generate_text
    _llm.generate_text = _gen
    try:
        evs = _run("通知して", approval=True)
    finally:
        _llm.generate_text = orig

    approval = [e for e in evs if e["phase"] == "approval"]
    assert approval, "承認待ちのイベントが出ていない"
    assert "ms" in approval[0] and "total_ms" in approval[0]
