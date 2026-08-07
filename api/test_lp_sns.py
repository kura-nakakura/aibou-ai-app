# test_lp_sns.py — LP/HP生成 と SNS投稿サポート のテスト

from fastapi.testclient import TestClient

import compliance
import lp
import sns
from main import app

client = TestClient(app)

_HTML = ("<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'>"
         "<title>テストLP</title><style>body{margin:0}</style></head>"
         "<body><h1>見出し</h1>" + "<p>本文</p>" * 40 + "</body></html>")


# ── LP: 出力の取り出し ───────────────────────────────────────────────
def test_extract_html_from_fence():
    out = lp._extract_html(f"説明文です\n```html\n{_HTML}\n```\nおわり")
    assert out.startswith("<!DOCTYPE html>") and out.endswith("</html>")


def test_extract_html_strips_preamble_and_trailer():
    out = lp._extract_html("これが作ったページです:\n" + _HTML + "\n以上です。")
    assert out.startswith("<!DOCTYPE html>") and out.endswith("</html>")


def test_looks_like_html_rejects_prose():
    assert lp._looks_like_html(_HTML) is True
    assert lp._looks_like_html("ページを作りました。") is False


def test_generate_returns_html_and_title(monkeypatch):
    monkeypatch.setattr(lp.llm, "generate_text", lambda p, **k: _HTML)
    res = lp.generate("カフェのLPを作って", style="warm")
    assert res["ok"] and res["title"] == "テストLP"
    assert res["html"].startswith("<!DOCTYPE html>")


def test_generate_forbids_external_deps_in_prompt(monkeypatch):
    """外部CDN/フォント/画像を使わせない指示が必ず入る（iframeプレビューとCSP対策）。"""
    seen = {}
    monkeypatch.setattr(lp.llm, "generate_text", lambda p, **k: (seen.update(p=p), _HTML)[1])
    lp.generate("何か")
    assert "外部CSS/JS/フォント/画像URLは一切使わない" in seen["p"]
    assert "レスポンシブ" in seen["p"]


def test_generate_refine_mode_includes_current(monkeypatch):
    seen = {}
    monkeypatch.setattr(lp.llm, "generate_text", lambda p, **k: (seen.update(p=p), _HTML)[1])
    lp.generate("色を暖色に変えて", current=_HTML)
    assert "【既存のHTML】" in seen["p"] and "【修正指示】" in seen["p"]
    assert "差分ではなく全文" in seen["p"]


def test_generate_requires_brief():
    assert lp.generate("").get("error")


def test_generate_rejects_non_html_output(monkeypatch):
    monkeypatch.setattr(lp.llm, "generate_text", lambda p, **k: "すみません、作れません")
    assert lp.generate("LP作って").get("error")


def test_style_presets_exist():
    assert set(lp.STYLES) >= {"modern", "bold", "warm", "dark", "minimal"}


def test_lp_endpoints(monkeypatch):
    monkeypatch.setattr(lp.llm, "generate_text", lambda p, **k: _HTML)
    assert client.get("/lp/styles").status_code == 200
    r = client.post("/lp/generate", json={"brief": "パン屋のLP", "style": "warm"})
    assert r.status_code == 200 and r.json()["ok"]
    assert client.post("/lp/generate", json={"brief": ""}).status_code == 400


def test_lp_save_as_artifact(monkeypatch):
    monkeypatch.setattr(lp.llm, "generate_text", lambda p, **k: _HTML)
    import artifacts
    before = len(artifacts.list_artifacts())
    r = client.post("/lp/generate", json={"brief": "花屋のLP", "save": True}).json()
    assert r["artifact"]["kind"] == "site"
    assert len(artifacts.list_artifacts()) == before + 1


# ── SNS: 投稿案 ──────────────────────────────────────────────────────
_POSTS = ('```json\n{"posts":[{"text":"朝の散歩が集中力を上げます。","hashtags":["朝活","習慣"],'
          '"image_prompt":"morning walk"},{"text":"2案目の本文","hashtags":["#朝活"]}]}\n```')


def test_generate_posts_x(monkeypatch):
    monkeypatch.setattr(sns.llm, "generate_text", lambda p, **k: _POSTS)
    res = sns.generate_posts("x", "朝活", n=2)
    assert res["ok"] and res["platform"] == "x" and res["limit"] == 280
    assert len(res["posts"]) == 2
    # ハッシュタグに # が自動で付く／重複しない
    assert res["posts"][0]["hashtags"] == ["#朝活", "#習慣"]
    assert res["posts"][0]["length"] > 0 and res["posts"][0]["over_limit"] is False
    assert res["auto_post"] is False   # 自動投稿しない


def test_generate_posts_instagram_limit(monkeypatch):
    monkeypatch.setattr(sns.llm, "generate_text", lambda p, **k: _POSTS)
    res = sns.generate_posts("instagram", "朝活", n=1)
    assert res["limit"] == 2200 and res["label"] == "Instagram"


def test_over_limit_flag(monkeypatch):
    long_text = "あ" * 300
    monkeypatch.setattr(sns.llm, "generate_text",
                        lambda p, **k: '{"posts":[{"text":"' + long_text + '","hashtags":[]}]}')
    res = sns.generate_posts("x", "テーマ", n=1)
    assert res["posts"][0]["over_limit"] is True   # X の280字超過を可視化


def test_promo_adds_pr_disclosure(monkeypatch):
    """PR案件はステマ規制対応で #PR を必ず付ける。"""
    monkeypatch.setattr(sns.llm, "generate_text", lambda p, **k: _POSTS)
    res = sns.generate_posts("instagram", "新商品", n=1, promo=True)
    assert sns.PR_TAG in res["posts"][0]["hashtags"]


def test_promo_instruction_in_prompt(monkeypatch):
    seen = {}
    monkeypatch.setattr(sns.llm, "generate_text", lambda p, **k: (seen.update(p=p), _POSTS)[1])
    sns.generate_posts("x", "案件", n=1, promo=True)
    assert "景品表示法" in seen["p"]


def test_thread_only_for_x(monkeypatch):
    seen = {}
    monkeypatch.setattr(sns.llm, "generate_text", lambda p, **k: (seen.update(p=p), _POSTS)[1])
    sns.generate_posts("instagram", "話題", thread=True)
    assert "スレッド案" not in seen["p"]
    sns.generate_posts("x", "話題", thread=True)
    assert "スレッド案" in seen["p"]


def test_generate_posts_validation():
    assert sns.generate_posts("tiktok", "x").get("error")
    assert sns.generate_posts("x", "").get("error")


def test_generate_posts_bad_output(monkeypatch):
    monkeypatch.setattr(sns.llm, "generate_text", lambda p, **k: "JSONではない")
    assert sns.generate_posts("x", "テーマ").get("error")


def test_with_image_attaches_url():
    post = sns.with_image({"text": "t", "image_prompt": "a cat"})
    assert post["image_url"].startswith("https://image.pollinations")
    # image_prompt が無ければ何もしない
    assert "image_url" not in sns.with_image({"text": "t"})


def test_sns_endpoints(monkeypatch):
    monkeypatch.setattr(sns.llm, "generate_text", lambda p, **k: _POSTS)
    assert client.get("/sns/platforms").status_code == 200
    r = client.post("/sns/generate", json={"platform": "x", "topic": "朝活", "n": 2})
    assert r.status_code == 200 and len(r.json()["posts"]) == 2
    assert client.post("/sns/generate", json={"platform": "x", "topic": ""}).status_code == 400


def test_sns_with_images_endpoint(monkeypatch):
    monkeypatch.setattr(sns.llm, "generate_text", lambda p, **k: _POSTS)
    r = client.post("/sns/generate", json={"platform": "instagram", "topic": "朝活", "n": 1, "with_images": True})
    assert r.status_code == 200
    assert r.json()["posts"][0].get("image_url", "").startswith("https://image.pollinations")


def test_disclosure_helper_shared():
    """SNSもLPも同じコンプライアンス基盤を使う。"""
    assert compliance.has_disclosure(compliance.with_disclosure("x"))
