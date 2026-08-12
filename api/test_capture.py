# test_capture.py — CAPTURE：文字起こし・ナレーション台本・吹き込みの検証
#
# 実際の音声認識は Gemini 依存なのでモックする。ここで確かめたいのは
#   ・ブラウザのWebMをそのままAIに渡さず、必ず音声へ変換していること
#   ・鍵やffmpegが無い環境で、黙って失敗せず理由を返すこと
#   ・長い録画を途中まで処理したことを隠さないこと
#   ・録画にナレーションを重ねた動画が本当に作られること（ffmpegがある環境）

import os
import shutil
import subprocess
import tempfile

from fastapi.testclient import TestClient

import transcribe as tr
from main import app

client = TestClient(app)

HAS_FFMPEG = shutil.which("ffmpeg") is not None


def _make_webm(seconds: int = 2, silent: bool = False) -> bytes:
    """テスト用の小さなWebM（映像＋音声）を作る。"""
    if not HAS_FFMPEG:
        return b""
    work = tempfile.mkdtemp(prefix="t_")
    try:
        out = os.path.join(work, "a.webm")
        audio = "anullsrc=r=44100:cl=mono" if silent else "sine=frequency=440"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc2=s=320x240:d={seconds}",
             "-f", "lavfi", "-i", f"{audio}:duration={seconds}",
             "-c:v", "libvpx", "-b:v", "200k", "-c:a", "libopus", "-t", str(seconds), out],
            capture_output=True, timeout=180)
        with open(out, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ── 状態 ─────────────────────────────────────────────────────────────
def test_status_reports_what_is_possible():
    s = tr.status()
    assert set(s) >= {"ffmpeg", "transcribe", "narrate", "voiceover", "styles", "max_mb"}
    assert s["narrate"] is True                     # 台本はテキストだけなので常に可
    assert s["voiceover"] == tr.ffmpeg_available()   # 合成はffmpeg依存
    assert any(x["key"] == "explain" for x in s["styles"])


def test_status_endpoint():
    r = client.get("/capture/status")
    assert r.status_code == 200 and "ffmpeg" in r.json()


# ── 音声抽出（WebMをそのままAIに渡さない） ───────────────────────────
def test_extracts_audio_from_a_webm_recording():
    if not HAS_FFMPEG:
        return
    data = _make_webm(2)
    audio, total, truncated, err = tr.extract_audio(data, "rec.webm")
    assert err is None
    assert audio and audio[:2] in (b"\xff\xfb", b"\xff\xf3", b"ID") or len(audio) > 100
    assert total and 1.0 < total < 4.0
    assert truncated is False


def test_long_recording_is_cut_and_says_so():
    if not HAS_FFMPEG:
        return
    data = _make_webm(4)
    audio, total, truncated, err = tr.extract_audio(data, "rec.webm", seconds=1)
    assert err is None and audio
    assert truncated is True          # 全部処理したと誤解させない


def test_extract_reports_a_broken_file():
    if not HAS_FFMPEG:
        return
    audio, _total, _t, err = tr.extract_audio(b"not a media file", "x.webm")
    assert audio is None and err


# ── 文字起こし ───────────────────────────────────────────────────────
def test_transcribe_requires_a_key(monkeypatch):
    if not HAS_FFMPEG:
        return
    import config
    monkeypatch.setattr(config, "get_gemini_model", lambda: None)
    res = tr.transcribe(_make_webm(1), "rec.webm")
    assert res.get("error") and "Gemini" in res["error"]


def test_transcribe_sends_converted_audio_not_the_webm(monkeypatch):
    """AIに渡すのは mp3。WebMのバイト列をそのまま渡していないこと。"""
    if not HAS_FFMPEG:
        return
    webm = _make_webm(2)
    seen = {}

    class FakeModel:
        def generate_content(self, parts):
            seen["parts"] = parts
            class R:
                text = "こんにちは、テストです。"
            return R()

    import config
    monkeypatch.setattr(config, "gemini_configured", lambda: True)
    monkeypatch.setattr(config, "get_gemini_model", lambda: FakeModel())
    res = tr.transcribe(webm, "rec.webm")
    assert res["ok"] and "こんにちは" in res["text"]
    blob = seen["parts"][1]
    assert blob["mime_type"] == "audio/mp3"
    assert blob["data"] != webm                 # 変換されている
    assert not blob["data"].startswith(b"\x1aE\xdf\xa3")   # WebMのマジックではない
    # 書き起こしだけを求める指示になっている（要約させない）
    assert "要約" in seen["parts"][0] and "文字起こし" in seen["parts"][0]


def test_transcribe_validates_input():
    assert tr.transcribe(b"").get("error")
    big = b"x" * (tr.MAX_UPLOAD_BYTES + 1)
    assert "大きすぎます" in tr.transcribe(big).get("error", "")


def test_transcribe_empty_result_is_reported(monkeypatch):
    if not HAS_FFMPEG:
        return

    class FakeModel:
        def generate_content(self, parts):
            class R:
                text = "   "
            return R()

    import config
    monkeypatch.setattr(config, "gemini_configured", lambda: True)
    monkeypatch.setattr(config, "get_gemini_model", lambda: FakeModel())
    res = tr.transcribe(_make_webm(1), "rec.webm")
    assert res.get("error") and "無音" in res["error"]


# ── ナレーション台本 ─────────────────────────────────────────────────
def test_narration_script_uses_style_and_length(monkeypatch):
    seen = {}
    import llm
    monkeypatch.setattr(llm, "generate_text",
                        lambda p, **k: (seen.update(p=p), "まず画面を開きます。\n次に設定を押します。")[1])
    res = tr.narration_script("画面を開いて設定を押す", style="formal", seconds=30)
    assert res["ok"] and "設定" in res["script"]
    assert "です・ます調" in seen["p"]
    assert "30秒" in seen["p"] and "字程度" in seen["p"]     # 尺に収める指示
    # 素材に無いことを足させない
    assert "素材に無い事実を足さない" in seen["p"]


def test_narration_script_without_length_has_no_char_limit(monkeypatch):
    seen = {}
    import llm
    monkeypatch.setattr(llm, "generate_text", lambda p, **k: (seen.update(p=p), "台本")[1])
    tr.narration_script("メモ")
    assert "字程度に収める" not in seen["p"]


def test_narration_script_validation(monkeypatch):
    assert tr.narration_script("").get("error")
    import llm
    monkeypatch.setattr(llm, "generate_text", lambda p, **k: "")
    assert tr.narration_script("素材").get("error")


def test_narrate_endpoint(monkeypatch):
    import llm
    monkeypatch.setattr(llm, "generate_text", lambda p, **k: "読み上げ台本です。")
    r = client.post("/capture/narrate", json={"source": "手順のメモ", "style": "friendly"})
    assert r.status_code == 200 and "読み上げ台本" in r.json()["script"]
    assert client.post("/capture/narrate", json={"source": ""}).status_code == 400


# ── ナレーションの吹き込み ───────────────────────────────────────────
def _make_mp3(seconds: int = 2) -> bytes:
    if not HAS_FFMPEG:
        return b""
    work = tempfile.mkdtemp(prefix="t_")
    try:
        out = os.path.join(work, "n.mp3")
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}",
                        "-c:a", "libmp3lame", out], capture_output=True, timeout=120)
        with open(out, "rb") as f:
            return f.read()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_voiceover_replaces_the_audio_track():
    if not HAS_FFMPEG:
        return
    res = tr.voiceover(_make_webm(3), _make_mp3(2), keep_original=False)
    assert res.get("ok"), res
    assert res["data"][4:8] == b"ftyp"          # mp4 になっている
    assert res["seconds"] and res["seconds"] > 0
    assert res["mixed"] is False


def test_voiceover_can_keep_the_original_audio():
    if not HAS_FFMPEG:
        return
    res = tr.voiceover(_make_webm(3), _make_mp3(2), keep_original=True)
    assert res.get("ok"), res
    assert res["mixed"] is True


def test_voiceover_falls_back_when_there_is_no_original_audio():
    """元に音声トラックが無い録画でも、混ぜる指定なら差し替えに落として成功させる。"""
    if not HAS_FFMPEG:
        return
    work = tempfile.mkdtemp(prefix="t_")
    try:
        silent = os.path.join(work, "v.webm")
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=s=320x240:d=2",
                        "-an", "-c:v", "libvpx", "-b:v", "200k", silent],
                       capture_output=True, timeout=180)
        with open(silent, "rb") as f:
            video = f.read()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    res = tr.voiceover(video, _make_mp3(2), keep_original=True)
    assert res.get("ok"), res
    assert res["mixed"] is False        # 混ぜられないので差し替えた


def test_voiceover_validation():
    assert tr.voiceover(b"", b"x").get("error")
    assert tr.voiceover(b"x", b"").get("error")


def test_voiceover_endpoint_requires_a_script():
    files = {"file": ("rec.webm", b"x", "video/webm")}
    r = client.post("/capture/voiceover", data={"script": "  "}, files=files)
    assert r.status_code == 400


def test_voiceover_endpoint_returns_a_real_mp4(monkeypatch):
    """台本 → 読み上げ → 録画に重ねる、のHTTP経路が本物のMP4を返すこと。

    読み上げ（edge-tts）は外部サービスなのでここでは差し替え、
    合成とレスポンスの形だけを確かめる。
    """
    if not HAS_FFMPEG:
        return
    import base64
    import main

    narr = _make_mp3(2)

    async def fake_tts(text, voice, rate):
        assert text.strip()          # 台本が渡っている
        return narr

    monkeypatch.setattr(main, "_synthesize_tts", fake_tts)
    files = {"file": ("rec.webm", _make_webm(3), "video/webm")}
    r = client.post("/capture/voiceover",
                    data={"script": "これはナレーションです。", "keep_original": "1"},
                    files=files)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    raw = base64.b64decode(d["video_base64"])
    assert raw[4:8] == b"ftyp"       # MP4として返っている
    assert d["seconds"] and d["seconds"] > 0


def test_voiceover_endpoint_reports_tts_failure(monkeypatch):
    """読み上げに失敗したら、黙って空を返さず理由を伝える。"""
    if not HAS_FFMPEG:
        return
    import main

    async def broken_tts(text, voice, rate):
        raise RuntimeError("ネットワークに到達できません")

    monkeypatch.setattr(main, "_synthesize_tts", broken_tts)
    files = {"file": ("rec.webm", _make_webm(1), "video/webm")}
    r = client.post("/capture/voiceover", data={"script": "台本"}, files=files)
    assert r.status_code == 503 and "読み上げに失敗" in r.json()["error"]


def test_transcribe_endpoint(monkeypatch):
    if not HAS_FFMPEG:
        return

    class FakeModel:
        def generate_content(self, parts):
            class R:
                text = "テストの音声です。"
            return R()

    import config
    monkeypatch.setattr(config, "gemini_configured", lambda: True)
    monkeypatch.setattr(config, "get_gemini_model", lambda: FakeModel())
    files = {"file": ("rec.webm", _make_webm(2), "video/webm")}
    r = client.post("/capture/transcribe", files=files)
    assert r.status_code == 200 and "テストの音声" in r.json()["text"]
    # 空ファイルは弾く
    assert client.post("/capture/transcribe",
                       files={"file": ("e.webm", b"", "video/webm")}).status_code == 400
