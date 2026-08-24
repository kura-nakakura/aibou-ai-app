# test_agent_truth.py — エージェントが「やった」と言うとき、本当にやったのか
#
# HOMEのエージェントは、指示を受けてタスク追加・予定登録・記憶などを実際に行う。
# だからこそ、やっていないのに「やりました」と言うのが一番きつい。
#
# 調べて分かった穴が2つ:
#   1. ツールはHTTPを通らずモジュールを直接呼ぶので、保存先が無くても
#      メモリに書いて「タスクを追加しました」と返していた。
#      （HTTPの入口は require_storage で塞いだが、ここは素通りだった）
#   2. 生成が使えないときの最終報告が、全部失敗していても
#      「実行しました（add_task）」と書いていた。

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agent
import config
import tools


# ── 1. 保存先が無いのに「追加しました」と言わない ────────────────
@pytest.fixture
def no_storage():
    """ログイン済みで、保存先が無い状態（人に配ったときのいちばん普通の状態）。"""
    token = config.bind_request_client(None)
    yield
    config.reset_request_client(token)


PERSISTING = [
    ("add_task", {"title": "見積を出す"}),
    ("add_agenda", {"title": "打ち合わせ", "date": "2026-09-01"}),
    ("remember", {"text": "誕生日は5月"}),
    ("save_note", {"text": "メモ"}),
    ("board_add_note", {"text": "付箋"}),
    ("create_automation", {"name": "毎朝", "steps": []}),
    ("create_mission", {"goal": "資料を作る"}),
]


@pytest.mark.parametrize("name,params", PERSISTING)
def test_the_agent_refuses_instead_of_pretending(no_storage, name, params):
    out = tools.execute_tool(name, params)
    assert "保存先" in out, f"{name} が「{out}」と返した"
    assert "Supabase" in out
    # 成功したように読める言い方をしていないこと
    assert "しました" not in out.replace("できませんでした", "")


def test_tools_that_do_not_persist_still_run(no_storage, monkeypatch):
    """外部に書くものや読むものまで止めない。止めると使えなくなるだけ。"""
    called = {}
    def fake(_p):
        called["hit"] = True
        return "結果"

    monkeypatch.setitem(tools._DISPATCH, "web_search", fake)
    assert tools.execute_tool("web_search", {"query": "天気"}) == "結果"
    assert called.get("hit") is True


def test_nothing_is_blocked_when_storage_exists(monkeypatch):
    """保存先があるときは、当然そのまま動く。"""
    token = config.bind_request_client(object())
    try:
        monkeypatch.setitem(tools._DISPATCH, "add_task", lambda p: "タスクを追加しました：x")
        assert "追加しました" in tools.execute_tool("add_task", {"title": "x"})
    finally:
        config.reset_request_client(token)


def test_single_user_setup_is_not_blocked(monkeypatch):
    """1人運用（差し替えが入っていない）は、これまで通り。"""
    monkeypatch.setitem(tools._DISPATCH, "add_task", lambda p: "タスクを追加しました：x")
    assert "追加しました" in tools.execute_tool("add_task", {"title": "x"})


# ── 2. 失敗を成功のように報告しない ──────────────────────────────
def test_failure_marks_are_recognised():
    assert agent._looks_failed("タスクの作成に失敗しました：x") is True
    assert agent._looks_failed("ツール実行エラー（add_task）：x") is True
    assert agent._looks_failed("保存先がつながっていないため、保存できませんでした。") is True
    assert agent._looks_failed("メールを送れませんでした") is True
    assert agent._looks_failed("不明なツールです：foo") is True


def test_success_is_not_mistaken_for_failure():
    """成功まで失敗扱いにすると、うまくいったのに謝ることになる。"""
    for ok in ["タスクを追加しました：見積を出す",
               "予定を登録しました：2026-09-01 打ち合わせ",
               "覚えました。",
               "検索結果を3件見つけました"]:
        assert agent._looks_failed(ok) is False, ok


def test_the_fallback_report_does_not_claim_success():
    """生成が文章を返さなかったときの受け皿。ここで一律に「完了しました」と
    書くと、全部失敗していても成功したように読める。"""
    failed = [("add_task", "タスクの作成に失敗しました：保存先なし")]
    out = agent._fallback_report(["add_task"], failed)
    assert "うまくいかなかった" in out
    assert "add_task" in out
    assert not out.startswith("実行しました")
    assert not out.startswith("完了しました")


def test_the_fallback_report_says_what_ran_when_it_worked():
    out = agent._fallback_report(["add_task", "add_agenda"], [])
    assert out.startswith("実行しました")
    assert "add_task" in out and "add_agenda" in out


def test_the_fallback_report_with_nothing_done():
    assert agent._fallback_report([], []) == "完了しました。"


def test_many_failures_are_summarised_not_dumped():
    """全部並べると読めない。件数で足りる。"""
    failed = [(f"tool{i}", "失敗しました") for i in range(6)]
    out = agent._fallback_report([f"tool{i}" for i in range(6)], failed)
    assert "ほか3件" in out
