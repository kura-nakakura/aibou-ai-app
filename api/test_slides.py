# test_slides.py — スライド生成 / Googleスライド / ツール のテスト

import json

from fastapi.testclient import TestClient

import artifacts
import gservice
import slides
import tools
from main import app

client = TestClient(app)


# ── slides.py ────────────────────────────────────────────────────────
def test_normalize_various_shapes():
    d = slides._normalize({"title": "T", "slides": ["見出しだけ", {"title": "A", "bullets": "単一"}]})
    assert d["title"] == "T"
    assert d["theme"] == "midnight"  # 既定テーマ
    assert d["slides"][0]["title"] == "見出しだけ"
    assert d["slides"][0]["layout"] == "bullets"  # 旧形式→bullets
    assert d["slides"][1]["bullets"] == ["単一"]


def test_normalize_layouts_and_theme():
    d = slides._normalize({
        "title": "P", "theme": "sunset",
        "slides": [
            {"layout": "title", "title": "表紙", "subtitle": "副題", "image": "http://x/y.png"},
            {"layout": "stat", "stat": "+30%", "title": "成長"},
            {"layout": "quote", "quote": "名言", "author": "誰か"},
            {"layout": "bogus", "title": "不明レイアウト"},
        ],
    })
    assert d["theme"] == "sunset"
    assert d["slides"][0]["layout"] == "title" and d["slides"][0]["subtitle"] == "副題"
    assert d["slides"][1]["stat"] == "+30%"
    assert d["slides"][2]["quote"] == "名言" and d["slides"][2]["author"] == "誰か"
    assert d["slides"][3]["layout"] == "bullets"  # 不正レイアウト→bullets


def test_normalize_invalid_theme_defaults():
    assert slides._normalize({"title": "T", "theme": "neon", "slides": [{"title": "a"}]})["theme"] == "midnight"


def test_apply_images_converts_prompt_to_url():
    deck = {"title": "T", "theme": "midnight", "slides": [
        {"layout": "title", "title": "cover", "image": "a calm mountain lake"},
        {"layout": "image", "title": "x", "image": "http://already/url.png"},
    ]}
    out = slides._apply_images(deck)
    assert out["slides"][0]["image"].startswith("https://image.pollinations")
    assert out["slides"][1]["image"] == "http://already/url.png"  # URLはそのまま


def test_normalize_empty_gives_placeholder():
    d = slides._normalize({}, "フォールバック")
    assert d["title"] == "フォールバック" and len(d["slides"]) == 1


def test_extract_json_from_fence():
    text = 'ここに説明\n```json\n{"title":"X","slides":[{"title":"a","bullets":["b"]}]}\n```\n終わり'
    d = slides._extract_json(text)
    assert d and d["title"] == "X"


def test_generate_deck_mocked(monkeypatch):
    monkeypatch.setattr(slides.llm, "generate_text",
                        lambda p, **k: '```json\n{"title":"提案","theme":"aurora","slides":[{"layout":"title","title":"背景","image":"city skyline"}]}\n```')
    deck = slides.generate_deck("新規事業", 5, "", with_images=False)
    assert deck["title"] == "提案" and deck["theme"] == "aurora"
    assert deck["slides"][0]["layout"] == "title"


def test_generate_deck_theme_override(monkeypatch):
    monkeypatch.setattr(slides.llm, "generate_text",
                        lambda p, **k: '{"title":"X","theme":"aurora","slides":[{"title":"a","bullets":["b"]}]}')
    deck = slides.generate_deck("topic", 4, "sunset", with_images=False)
    assert deck["theme"] == "sunset"  # 明示指定が優先


def test_generate_deck_bad_output_degrades(monkeypatch):
    monkeypatch.setattr(slides.llm, "generate_text", lambda p, **k: "JSONではない普通の文章")
    deck = slides.generate_deck("テーマ")
    assert deck["title"] == "テーマ" and len(deck["slides"]) >= 1


def test_generate_deck_requires_topic():
    assert slides.generate_deck("").get("error")


def test_to_markdown():
    md = slides.to_markdown({"title": "T", "slides": [{"title": "A", "bullets": ["x", "y"]}]})
    assert "# T" in md and "## 1. A" in md and "- x" in md


# ── create_slides tool → artifact ────────────────────────────────────
def test_create_slides_tool_from_slides_array():
    before = len(artifacts.list_artifacts())
    r = tools.execute_tool("create_slides", {"title": "四半期報告", "slides": [{"title": "売上", "bullets": ["前年比+20%"]}]})
    assert "四半期報告" in r and "スライド" in r
    items = artifacts.list_artifacts()
    assert len(items) == before + 1 and items[0]["kind"] == "slides"
    full = artifacts.get(items[0]["id"])
    deck = json.loads(full["content"])
    assert deck["slides"][0]["title"] == "売上"


def test_create_slides_tool_requires_input():
    assert "必要" in tools.execute_tool("create_slides", {})


# ── Google Slides ────────────────────────────────────────────────────
def test_google_slides_tool_not_connected():
    r = tools.execute_tool("create_google_slides", {"slides": [{"title": "x", "bullets": ["y"]}]})
    assert "Google" in r and ("未接続" in r or "未設定" in r)


def test_gservice_create_presentation_mocked(monkeypatch):
    monkeypatch.setattr(gservice, "_access_token", lambda: "tok")

    class FakeResp:
        content = b"{}"
        def __init__(self, d):
            self._d = d
        def json(self):
            return self._d

    calls = {"batch": 0}

    def fake_post(url, **k):
        if url.endswith("/presentations"):
            return FakeResp({"presentationId": "pid1", "slides": [{"objectId": "p0"}]})
        calls["batch"] += 1
        return FakeResp({})

    monkeypatch.setattr(gservice.requests, "post", fake_post)
    res = gservice.create_presentation("提案", [{"title": "背景", "bullets": ["a", "b"]}])
    assert res["ok"] is True and "pid1" in res["url"] and calls["batch"] == 1


# ── ④ スライド1枚ごとの編集（Genspark相当） ──────────────────────────
_ONE = '```json\n{"layout":"bullets","title":"直した見出し","bullets":["短く1","短く2"]}\n```'


def test_revise_slide_returns_single_slide(monkeypatch):
    monkeypatch.setattr(slides.llm, "generate_text", lambda p, **k: _ONE)
    res = slides.revise_slide({"layout": "bullets", "title": "元", "bullets": ["長い文章"]},
                              "もっと短く力強く")
    assert res["ok"] and res["slide"]["title"] == "直した見出し"
    assert res["slide"]["bullets"] == ["短く1", "短く2"]


def test_revise_slide_prompt_scopes_to_one_slide(monkeypatch):
    """デッキ全体ではなく1枚だけを直す指示になっている（他の枚を壊さない）。"""
    seen = {}
    monkeypatch.setattr(slides.llm, "generate_text", lambda p, **k: (seen.update(p=p), _ONE)[1])
    slides.revise_slide({"layout": "stat", "stat": "+30%"}, "数字を強調",
                        deck_title="事業計画", context="前: 課題 / 次: まとめ")
    p = seen["p"]
    assert "スライド1枚だけを修正" in p
    assert "事業計画" in p and "前: 課題 / 次: まとめ" in p
    assert '"stat": "+30%"' in p or '"stat":"+30%"' in p     # いまの内容を渡している


def test_revise_slide_can_force_layout(monkeypatch):
    """レイアウトを指定したらAIの出力より指定が優先される。"""
    seen = {}
    monkeypatch.setattr(slides.llm, "generate_text", lambda p, **k: (seen.update(p=p), _ONE)[1])
    res = slides.revise_slide({"title": "x"}, "引用にして", layout="quote")
    assert 'レイアウトは必ず "quote"' in seen["p"]
    assert res["slide"]["layout"] == "quote"      # AIがbulletsを返しても指定を守る


def test_revise_slide_unwraps_a_whole_deck(monkeypatch):
    """デッキ形式で返ってきても先頭1枚を取り出す（モデルの揺れに耐える）。"""
    whole = '{"title":"deck","slides":[{"layout":"quote","quote":"引用文","author":"著者"}]}'
    monkeypatch.setattr(slides.llm, "generate_text", lambda p, **k: whole)
    res = slides.revise_slide({"title": "x"}, "引用に")
    assert res["ok"] and res["slide"]["layout"] == "quote" and res["slide"]["quote"] == "引用文"


def test_revise_slide_validation(monkeypatch):
    assert slides.revise_slide({"title": "x"}, "").get("error")
    monkeypatch.setattr(slides.llm, "generate_text", lambda p, **k: "JSONではない")
    assert slides.revise_slide({"title": "x"}, "直して").get("error")
    monkeypatch.setattr(slides.llm, "generate_text", lambda p, **k: '{"layout":"bullets"}')
    assert slides.revise_slide({"title": "x"}, "直して").get("error")   # 中身が空


def test_revise_slide_rejects_invalid_layout_request(monkeypatch):
    seen = {}
    monkeypatch.setattr(slides.llm, "generate_text", lambda p, **k: (seen.update(p=p), _ONE)[1])
    res = slides.revise_slide({"title": "x"}, "直して", layout="carousel")
    assert "レイアウトは必ず" not in seen["p"]      # 未知のレイアウトは無視
    assert res["slide"]["layout"] in slides.LAYOUTS


def test_layout_fields_cover_every_layout():
    """編集フォームの定義が全レイアウトに存在すること（UIが空にならない）。"""
    for key in slides.LAYOUTS:
        assert slides.LAYOUT_FIELDS.get(key), f"{key} のフィールド定義がない"
        assert slides.LAYOUT_LABELS.get(key), f"{key} の表示名がない"


def test_slides_layouts_endpoint():
    r = client.get("/slides/layouts")
    assert r.status_code == 200
    d = r.json()
    assert {x["key"] for x in d["layouts"]} == set(slides.LAYOUTS)
    assert d["themes"] == slides.THEMES
    stat = next(x for x in d["layouts"] if x["key"] == "stat")
    assert "stat" in stat["fields"] and stat["label"] == "数字を大きく"


def test_slides_revise_endpoint(monkeypatch):
    monkeypatch.setattr(slides.llm, "generate_text", lambda p, **k: _ONE)
    r = client.post("/slides/revise", json={"slide": {"title": "元"}, "instruction": "短く"})
    assert r.status_code == 200 and r.json()["slide"]["title"] == "直した見出し"
    assert client.post("/slides/revise", json={"slide": {}, "instruction": ""}).status_code == 400
