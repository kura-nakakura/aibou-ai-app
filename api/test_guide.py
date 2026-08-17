# test_guide.py — 使い方ガイドの検証
#
# ここが壊れると「説明と実物が食い違うアプリ」になる。特に確かめたいのは
#   ・画面のガイドとCHATの説明が同じ出どころから来ていること
#   ・ベータの注意（データが利用者ごとに分かれていない）が確実に載ること
#   ・実装に無い機能を説明していないこと

from fastapi.testclient import TestClient

import guide
import main
from main import app

client = TestClient(app)


def test_sections_have_the_shape_the_ui_expects():
    for s in guide.sections():
        assert set(s) >= {"id", "title", "summary", "steps", "notes"}
        assert s["title"] and s["summary"]
        assert isinstance(s["steps"], list) and isinstance(s["notes"], list)


def test_ids_are_unique():
    ids = [s["id"] for s in guide.sections()]
    assert len(ids) == len(set(ids))


def test_sections_are_a_copy_so_callers_cannot_corrupt_the_source():
    got = guide.sections()
    got[0]["title"] = "書き換え"
    assert guide.sections()[0]["title"] != "書き換え"


def test_beta_warning_is_present_and_explicit():
    """共有環境であることは、隠すと事故になる。必ず載っていること。"""
    beta = next(s for s in guide.sections() if s["id"] == "beta")
    joined = beta["summary"] + " ".join(beta["notes"])
    assert "ベータ" in joined
    assert "全員が同じ" in joined or "分かれておらず" in joined
    assert "APIキー" in joined


def test_chat_prompt_carries_the_same_warning():
    """CHATが「個人利用として安全です」と嘘をつかないよう、事実を渡す。"""
    block = guide.prompt_block()
    assert "ベータ" in block
    assert "共有" in block
    assert "でっち上げ" in block or "あるかのように答えない" in block


def test_chat_system_prompt_includes_the_guide():
    p = main.build_system_prompt("AIbou", "", "")
    assert "このアプリについて" in p
    assert "ベータ" in p


def test_guide_endpoint():
    r = client.get("/guide")
    assert r.status_code == 200
    d = r.json()
    assert d["app"] and d["beta"] is True and d["shared_data"] is True
    assert len(d["sections"]) == d["section_count"] >= 4
    # 件数キーが本体を上書きしていないこと（実際に踏んだ不具合）
    assert isinstance(d["sections"], list)


def test_guide_does_not_promise_features_that_do_not_exist():
    """説明にあるモード名は、実際に画面がある名前だけにする。"""
    text = " ".join(s["summary"] + " ".join(s["steps"]) for s in guide.sections())
    modes = ["HOME", "CHAT", "ME", "TASKS", "BOARD", "VAULT", "CODE",
             "STUDIO", "CAPTURE", "SNS", "INCOME", "AUTO", "ARCHIVE"]
    settings_tabs = ["CORE", "PERSONA", "KEYCHAIN", "DIAGNOSTICS"]   # 設定のタブ名
    # 画面名ではない語（サービス名・略語）
    other = ["PDF", "AI", "LP", "LINE", "ZIP", "CSV", "URL", "PAT"]
    import re
    for word in re.findall(r"\b[A-Z]{3,}\b", text):
        assert word in modes + settings_tabs + other, \
            f"実在しない画面名が説明に出ている: {word}"
