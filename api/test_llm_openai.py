# test_llm_openai.py — OpenAI をプロバイダとして使えるかの検証
#
# 拡張機能の画面に「OpenAI を繋ぐと GPT系が使えます」と書く以上、本当に
# 使えなければならない。これまでは鍵の入力欄があるだけで、llm.py は
# gemini と huggingface しか見ていなかった（＝入れても何も起きない）。
#
# あわせて、従量課金のプロバイダを勝手に使い始めないことも見る。
# 鍵を入れただけで請求が発生したら、それは事故。

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import llm


@pytest.fixture
def keys(monkeypatch):
    store = {}
    monkeypatch.setattr(llm, "_kc", lambda n: store.get(n, ""))
    monkeypatch.setattr(config, "gemini_configured", lambda: bool(store.get("_GEMINI")))
    return store


def test_openai_key_alone_is_enough_to_generate(keys):
    keys["OPENAI_API_KEY"] = "sk-test"
    assert llm.providers_in_order() == ["openai"]
    assert llm.active_provider() == "openai"


def test_no_keys_means_no_provider(keys):
    assert llm.providers_in_order() == []
    assert llm.active_provider() == "none"


def test_openai_is_not_used_first_by_accident(keys):
    """従量課金なので、明示的に選ばない限り先頭に来てはいけない。"""
    keys["_GEMINI"] = "1"
    keys["OPENAI_API_KEY"] = "sk-test"
    order = llm.providers_in_order()
    assert order[0] == "gemini"
    assert "openai" in order          # 最後の受け皿には残す


def test_choosing_openai_puts_it_first(keys):
    keys["_GEMINI"] = "1"
    keys["OPENAI_API_KEY"] = "sk-test"
    keys["LLM_PROVIDER"] = "openai"
    assert llm.providers_in_order()[0] == "openai"


def test_model_can_be_overridden(keys):
    assert llm.openai_model() == llm.DEFAULT_OPENAI_MODEL
    keys["OPENAI_MODEL"] = "gpt-4o"
    assert llm.openai_model() == "gpt-4o"


def test_generate_actually_calls_openai(keys, monkeypatch):
    """振り分けが openai に届くこと。ネットワークには出ない。"""
    keys["OPENAI_API_KEY"] = "sk-test"
    seen = {}

    class R:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": "こんにちは"}}]}

    def fake_post(url, headers=None, json=None, **kw):
        seen["url"] = url
        seen["auth"] = headers["Authorization"]
        seen["model"] = json["model"]
        return R()

    monkeypatch.setattr(llm.requests, "post", fake_post)
    assert llm.generate_text("やあ") == "こんにちは"
    assert seen["url"] == llm.OPENAI_URL
    assert seen["auth"] == "Bearer sk-test"
    assert seen["model"] == llm.DEFAULT_OPENAI_MODEL


def test_openai_failure_falls_back_to_gemini(keys, monkeypatch):
    """1つ落ちても止まらない。これがプロバイダを増やす理由でもある。"""
    keys["_GEMINI"] = "1"
    keys["OPENAI_API_KEY"] = "sk-test"
    keys["LLM_PROVIDER"] = "openai"

    def boom(*a, **k):
        raise RuntimeError("OpenAIが落ちている")

    monkeypatch.setattr(llm.requests, "post", boom)
    monkeypatch.setattr(llm, "_gen_gemini", lambda p: "Geminiが答えました")
    assert llm.generate_text("やあ") == "Geminiが答えました"


def test_error_message_names_every_accepted_key(keys):
    """「どれを入れればいいのか」が分かる文言であること。"""
    with pytest.raises(RuntimeError) as e:
        llm.generate_text("やあ")
    for name in ["GEMINI_API_KEY", "HUGGINGFACE_TOKEN", "OPENAI_API_KEY"]:
        assert name in str(e.value)


def test_streaming_reads_openai_deltas(keys, monkeypatch):
    keys["OPENAI_API_KEY"] = "sk-test"

    class R:
        status_code = 200
        def iter_lines(self):
            yield b'data: {"choices":[{"delta":{"content":"\xe3\x81\x93"}}]}'
            yield b'data: {"choices":[{"delta":{"content":"\xe3\x82\x93"}}]}'
            yield b"data: [DONE]"

    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: R())
    assert "".join(llm.stream_text("やあ")) == "こん"
