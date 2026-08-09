# test_video.py — ③ 動画作成（絵コンテ自動生成／比率／字幕）のテスト
#
# 実レンダリングは ffmpeg 依存なので、ここではフィルタ組み立てと
# 絵コンテ生成・エンドポイントの契約を検証する（ffmpeg が無い環境でも通る）。

import os
import sys

from fastapi.testclient import TestClient

import video_script
from main import app

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import renderer  # noqa: E402  リポジトリrootの renderer.py

client = TestClient(app)

_SB = ('```json\n{"title":"朝の散歩のすすめ","scenes":['
       '{"narration":"朝の光を浴びると体内時計が整います。","visual":"quiet street at dawn, soft light"},'
       '{"narration":"まずは15分から始めましょう。","visual":"person walking, wide shot"}]}\n```')


# ── 絵コンテ生成 ─────────────────────────────────────────────────────
def test_storyboard_parses_scenes(monkeypatch):
    monkeypatch.setattr(video_script.llm, "generate_text", lambda p, **k: _SB)
    res = video_script.storyboard("朝の散歩", n=2)
    assert res["ok"] and res["title"] == "朝の散歩のすすめ"
    assert len(res["scenes"]) == 2
    assert res["scenes"][0]["narration"].startswith("朝の光")
    assert res["scenes"][0]["visual"] == "quiet street at dawn, soft light"


def test_storyboard_prompt_adapts_to_vertical(monkeypatch):
    """縦型は1シーンを短く畳む指示にする（Shorts向け）。"""
    seen = {}
    monkeypatch.setattr(video_script.llm, "generate_text",
                        lambda p, **k: (seen.update(p=p), _SB)[1])
    video_script.storyboard("話題", n=3, aspect="9:16")
    assert "20〜45文字" in seen["p"]
    video_script.storyboard("話題", n=3, aspect="16:9")
    assert "30〜70文字" in seen["p"]


def test_storyboard_prompt_asks_for_english_visuals(monkeypatch):
    seen = {}
    monkeypatch.setattr(video_script.llm, "generate_text",
                        lambda p, **k: (seen.update(p=p), _SB)[1])
    video_script.storyboard("話題", tone="calm", style="film photography")
    assert "english image prompt" in seen["p"]
    assert "落ち着いた" in seen["p"]          # tone が効く
    assert "film photography" in seen["p"]    # style が効く
    # 字幕は別で焼くので、画に文字を入れさせない
    assert "文字やロゴを画面に入れる指示はしない" in seen["p"]


def test_storyboard_clamps_scene_count(monkeypatch):
    many = '{"scenes":[' + ",".join(['{"narration":"n","visual":"v"}'] * 30) + ']}'
    monkeypatch.setattr(video_script.llm, "generate_text", lambda p, **k: many)
    assert len(video_script.storyboard("x", n=99)["scenes"]) == video_script.MAX_SCENES
    assert len(video_script.storyboard("x", n=1)["scenes"]) == 2      # 最低2シーン
    assert len(video_script.storyboard("x", n="bad")["scenes"]) == 5  # 不正値は既定


def test_storyboard_validation(monkeypatch):
    assert video_script.storyboard("").get("error")
    monkeypatch.setattr(video_script.llm, "generate_text", lambda p, **k: "JSONではない")
    assert video_script.storyboard("テーマ").get("error")
    monkeypatch.setattr(video_script.llm, "generate_text", lambda p, **k: '{"scenes":[]}')
    assert video_script.storyboard("テーマ").get("error")


def test_storyboard_skips_empty_scenes(monkeypatch):
    mixed = '{"scenes":[{"narration":"あり","visual":"v"},{"narration":"","visual":""},"ゴミ"]}'
    monkeypatch.setattr(video_script.llm, "generate_text", lambda p, **k: mixed)
    assert len(video_script.storyboard("x", n=5)["scenes"]) == 1


# ── 字幕のレイアウト ─────────────────────────────────────────────────
def test_subtitle_metrics_fit_inside_the_frame():
    """縦型でも字幕が横にはみ出さないこと（フォントを高さだけで決めると溢れる）。"""
    for _key, (w, h, _label) in renderer.VIDEO_ASPECTS.items():
        fontsize, per_line, margin = renderer.subtitle_metrics(w, h)
        # 全角＝送り幅≒フォントサイズなので、行の想定幅が画面幅を超えないこと
        assert per_line * fontsize <= w, f"{w}x{h} で字幕がはみ出す"
        assert fontsize >= 18 and per_line >= 8 and 0 < margin < h


def test_vertical_wraps_more_than_landscape():
    _, pl_v, _ = renderer.subtitle_metrics(720, 1280)
    _, pl_h, _ = renderer.subtitle_metrics(1280, 720)
    assert pl_v < pl_h    # 縦型のほうが1行が短い


def test_wrap_ja_breaks_without_spaces():
    t = "日光を浴びると体内時計が整い、夜の眠りが深くなることが知られています。"
    out = renderer.wrap_ja(t, per_line=20)
    lines = out.split("\n")
    assert len(lines) >= 2
    assert all(len(ln) <= 24 for ln in lines)     # 句読点で少し伸びる余地を許容
    assert renderer.wrap_ja("", per_line=20) == ""


def test_wrap_ja_caps_lines_and_marks_truncation():
    long = "あ" * 300
    out = renderer.wrap_ja(long, per_line=20, max_lines=3)
    assert len(out.split("\n")) == 3
    assert out.endswith("…")     # 入り切らなかったことが分かる


# ── シーンのフィルタグラフ ───────────────────────────────────────────
def test_scene_vf_has_motion_fade_and_subtitles():
    vf = renderer._scene_vf(1280, 720, 4.0, 24, 0, "/tmp/s.txt", "/f.ttf", motion=True)
    assert "zoompan" in vf and "fade=t=in" in vf and "fade=t=out" in vf
    assert "drawtext" in vf and "textfile='/tmp/s.txt'" in vf
    assert vf.endswith("format=yuv420p")
    # ズームは出力フレーム番号 on 基準（ループ入力で zoom+inc はリセットされる）
    assert "on/96" in vf      # 4.0s * 24fps


def test_scene_vf_without_motion_pads_instead():
    vf = renderer._scene_vf(720, 1280, 3.0, 24, 1, None, None, motion=False)
    assert "zoompan" not in vf and "pad=720:1280" in vf
    assert "drawtext" not in vf      # 字幕なし指定なら焼かない


def test_scene_vf_zoom_direction_varies_by_seed():
    a = renderer._scene_vf(1280, 720, 4.0, 24, 0, None, None, motion=True)
    b = renderer._scene_vf(1280, 720, 4.0, 24, 1, None, None, motion=True)
    assert a != b     # シーンごとに動きが変わる（同じ動きの連続を避ける）


def test_video_aspects_include_vertical():
    assert set(renderer.VIDEO_ASPECTS) >= {"16:9", "9:16", "1:1"}
    w, h, _ = renderer.VIDEO_ASPECTS["9:16"]
    assert h > w


# ── エンドポイント ───────────────────────────────────────────────────
def test_storyboard_endpoint(monkeypatch):
    monkeypatch.setattr(video_script.llm, "generate_text", lambda p, **k: _SB)
    r = client.post("/video/storyboard", json={"topic": "朝の散歩", "n": 2, "aspect": "9:16"})
    assert r.status_code == 200 and len(r.json()["scenes"]) == 2
    assert client.post("/video/storyboard", json={"topic": ""}).status_code == 400


def test_video_aspects_endpoint():
    r = client.get("/video/aspects")
    assert r.status_code == 200
    d = r.json()
    assert {a["key"] for a in d["aspects"]} >= {"16:9", "9:16", "1:1"}
    # ffmpeg / フォントの有無を正直に返す（UIが字幕トグルを出す判断に使う）
    assert isinstance(d["available"], bool) and isinstance(d["subtitles_available"], bool)


def test_video_endpoint_passes_aspect_and_subtitles(monkeypatch):
    """UIで選んだ比率と字幕設定が renderer に渡ること。"""
    seen = {}

    class FakeRenderer:
        @staticmethod
        def is_available():
            return True

        @staticmethod
        def render_forge_video(scenes, image_prompt, aspect="16:9", subtitles=True):
            seen.update(scenes=scenes, aspect=aspect, subtitles=subtitles)
            return None      # 実レンダリングはしない → 503 になる

    import main
    monkeypatch.setattr(main, "_load_renderer", lambda: FakeRenderer)
    r = client.post("/video", json={
        "scenes": [{"narration": "テスト", "visual": "a lake"}],
        "aspect": "9:16", "subtitles": False,
    })
    assert r.status_code == 503                  # 生成できなければ素直に縮退
    assert seen["aspect"] == "9:16" and seen["subtitles"] is False
    assert seen["scenes"][0]["narration"] == "テスト"


def test_video_endpoint_degrades_without_ffmpeg(monkeypatch):
    import main
    monkeypatch.setattr(main, "_load_renderer", lambda: None)
    r = client.post("/video", json={"scenes": [{"narration": "x", "visual": "y"}]})
    assert r.status_code == 503 and "unavailable" in r.json()["error"]
