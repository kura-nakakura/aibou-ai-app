# test_app_image.py — ① アプリ生成（kind="app"）と ② 画像スタジオ のテスト

from fastapi.testclient import TestClient

import imagegen
import lp
from main import app

client = TestClient(app)

_HTML = ("<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'><title>家計簿</title>"
         "<style>body{margin:0}</style></head><body><h1>家計簿</h1>"
         + "<p>x</p>" * 40 + "<script>localStorage.getItem('k')</script></body></html>")


# ── ① アプリ生成 ─────────────────────────────────────────────────────
def test_app_prompt_demands_working_app(monkeypatch):
    """base44のように「実際に動く」ことを要求する（保存・削除まで動く）。"""
    seen = {}
    monkeypatch.setattr(lp.llm, "generate_text", lambda p, **k: (seen.update(p=p), _HTML)[1])
    lp.generate("家計簿アプリ", kind="app")
    p = seen["p"]
    assert "実際に操作できること" in p and "localStorage" in p
    assert "バックエンド無しで動作する" in p
    # フレームワークは読み込めないので使わせない
    assert "素のJavaScript" in p and "Reactなど" in p
    # 1ファイル完結の要件は共通で入る（iframeプレビューの前提）
    assert "外部CSS/JS/フォント/画像URL・CDNは一切使わない" in p


def test_lp_prompt_stays_page_oriented(monkeypatch):
    seen = {}
    monkeypatch.setattr(lp.llm, "generate_text", lambda p, **k: (seen.update(p=p), _HTML)[1])
    lp.generate("カフェのLP", kind="lp")
    assert "ランディングページ" in seen["p"]
    assert "localStorage" not in seen["p"]


def test_app_default_spec_used(monkeypatch):
    seen = {}
    monkeypatch.setattr(lp.llm, "generate_text", lambda p, **k: (seen.update(p=p), _HTML)[1])
    lp.generate("メモ帳", kind="app")
    assert lp.APP_DEFAULT_SPEC in seen["p"]


def test_app_kind_returned(monkeypatch):
    monkeypatch.setattr(lp.llm, "generate_text", lambda p, **k: _HTML)
    res = lp.generate("家計簿", kind="app")
    assert res["ok"] and res["kind"] == "app" and res["title"] == "家計簿"


def test_invalid_kind_falls_back_to_lp(monkeypatch):
    monkeypatch.setattr(lp.llm, "generate_text", lambda p, **k: _HTML)
    assert lp.generate("何か", kind="game")["kind"] == "lp"


def test_app_refine_preserves_features(monkeypatch):
    seen = {}
    monkeypatch.setattr(lp.llm, "generate_text", lambda p, **k: (seen.update(p=p), _HTML)[1])
    lp.generate("削除ボタンを追加して", current=_HTML, kind="app")
    assert "【既存のHTML】" in seen["p"] and "既にある機能を壊さないこと" in seen["p"]


def test_app_endpoint(monkeypatch):
    monkeypatch.setattr(lp.llm, "generate_text", lambda p, **k: _HTML)
    r = client.post("/lp/generate", json={"brief": "家計簿アプリ", "kind": "app"})
    assert r.status_code == 200 and r.json()["kind"] == "app"


# ── ② 画像スタジオ ───────────────────────────────────────────────────
def test_aspect_presets():
    assert set(imagegen.ASPECTS) >= {"1:1", "4:5", "9:16", "16:9", "3:2"}
    w, h, _ = imagegen.ASPECTS["9:16"]
    assert h > w   # 縦長


def test_variants_differ_but_are_reproducible():
    a = imagegen.generate_variants("a calm lake", n=3, aspect="16:9")
    assert a["ok"] and len(a["images"]) == 3
    seeds = [i["seed"] for i in a["images"]]
    assert len(set(seeds)) == 3            # 別案になる
    b = imagegen.generate_variants("a calm lake", n=3, aspect="16:9")
    assert [i["seed"] for i in b["images"]] == seeds   # 同じ指示なら同じ結果
    assert "width=1280" in a["images"][0]["url"] and "height=720" in a["images"][0]["url"]


def test_variants_clamped_and_validated():
    # 上限でクランプ（作りすぎない）
    assert len(imagegen.generate_variants("x", n=99)["images"]) == imagegen.MAX_VARIANTS
    # 0 や None は「未指定」として既定枚数(2)にする
    assert len(imagegen.generate_variants("x", n=0)["images"]) == 2
    assert len(imagegen.generate_variants("x", n=None)["images"]) == 2
    # 文字列が来ても落ちない
    assert len(imagegen.generate_variants("x", n="bad")["images"]) == 2
    assert imagegen.generate_variants("", n=2).get("error")
    # 未知の比率は 1:1 に落とす
    assert imagegen.generate_variants("x", aspect="7:3")["aspect"] == "1:1"


def test_offset_yields_new_alternatives():
    """「別案を見る」= seed をずらす。前の案と重複しない。"""
    first = imagegen.generate_variants("a fox", n=2, offset=0)
    more = imagegen.generate_variants("a fox", n=2, offset=2)
    a = {i["seed"] for i in first["images"]}
    b = {i["seed"] for i in more["images"]}
    assert not (a & b) and more["offset"] == 2
    # 同じ offset なら再現する
    assert [i["seed"] for i in imagegen.generate_variants("a fox", n=2, offset=2)["images"]] == \
           [i["seed"] for i in more["images"]]
    # 負値・不正値は 0 に丸める（落ちない）
    assert imagegen.generate_variants("a fox", n=1, offset=-5)["offset"] == 0
    assert imagegen.generate_variants("a fox", n=1, offset="x")["offset"] == 0


def test_offset_endpoint():
    r = client.post("/image/generate", json={"prompt": "a fox", "n": 2, "offset": 2})
    assert r.status_code == 200 and r.json()["offset"] == 2


def test_single_generate_still_works_and_has_seed():
    res = imagegen.generate("one image")
    assert res["ok"] and "seed" in res and res["url"].startswith("https://image.pollinations")


def test_image_endpoints():
    assert client.get("/image/aspects").status_code == 200
    r = client.post("/image/generate", json={"prompt": "sunset over hills", "n": 2, "aspect": "4:5"})
    assert r.status_code == 200 and len(r.json()["images"]) == 2
    assert client.post("/image/generate", json={"prompt": ""}).status_code == 400


def test_image_save_creates_artifacts():
    import artifacts
    before = len(artifacts.list_artifacts())
    r = client.post("/image/generate", json={"prompt": "a red bicycle", "n": 2, "save": True})
    assert r.status_code == 200 and len(r.json()["artifacts"]) == 2
    items = artifacts.list_artifacts()
    assert len(items) == before + 2 and items[0]["kind"] == "image"
