# transcribe.py — 録画/録音の文字起こしと、ナレーションの吹き込み
# =====================================================================
# CAPTUREモードで録ったものを素材として使えるようにする。
#
#   transcribe(data, name, mime)      … 音声を文字起こし（Geminiのマルチモーダル）
#   narration_script(text, ...)       … 文字起こし/構成メモから読み上げ台本を作る
#   voiceover(video, audio, keep_original) … 録画にナレーション音声を重ねる（ffmpeg）
#
# 設計上の注意
#   ・ブラウザの録画は WebM/Opus。Gemini が受け付ける形式ではないので、
#     ffmpeg で mp3 に変換してから渡す（動画からは音声だけ抜く）。
#     ffmpeg が無い環境では、その旨をはっきり返して縮退する。
#   ・長い録画は丸ごと送れないため、上限を設けて「どこまで処理したか」を返す。
#     黙って前半だけ書き起こすと、全部できたと誤解される。
#   ・絶対に raise しない（他のモジュールと同じ方針）。
# =====================================================================

import os
import shutil
import subprocess
import tempfile

MAX_UPLOAD_BYTES = 80_000_000     # 受け取る録画/録音の上限（約80MB）
MAX_AUDIO_SECONDS = 1800          # 文字起こしに回す音声の上限（30分）
MAX_SCRIPT_CHARS = 6000

NARRATION_STYLES = {
    "explain": "落ち着いた解説口調。手順を順に説明する",
    "friendly": "親しみやすく、やさしい語り口",
    "energetic": "テンポが速く、元気な語り口",
    "formal": "です・ます調の丁寧な業務説明",
}


def _ffmpeg():
    return shutil.which("ffmpeg")


def ffmpeg_available() -> bool:
    return _ffmpeg() is not None


def status() -> dict:
    """UIが「何ができるか」を判断するための状態。鍵の値は返さない。"""
    ok_key = False
    try:
        import config
        ok_key = config.gemini_configured()
    except Exception:
        pass
    return {
        "ffmpeg": ffmpeg_available(),
        "transcribe": bool(ok_key and ffmpeg_available()),
        "narrate": True,                    # 台本生成はテキストだけなので常に可
        "voiceover": ffmpeg_available(),
        "styles": [{"key": k, "label": v} for k, v in NARRATION_STYLES.items()],
        "max_mb": MAX_UPLOAD_BYTES // 1_000_000,
    }


def _duration(path: str):
    """メディアの長さ（秒）。分からなければ None。"""
    probe = shutil.which("ffprobe")
    if not probe:
        return None
    try:
        r = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, timeout=60)
        return float(r.stdout.decode().strip())
    except Exception:
        return None


def extract_audio(data: bytes, name: str = "rec", seconds: int = MAX_AUDIO_SECONDS):
    """録画/録音から mp3 の音声を取り出す。(bytes, duration, truncated, error)。

    ブラウザのWebMをそのままAIに渡せないので、ここで必ず変換する。
    """
    ff = _ffmpeg()
    if not ff:
        return None, None, False, "サーバーに ffmpeg が無いため音声を取り出せません"
    work = tempfile.mkdtemp(prefix="cap_")
    try:
        src = os.path.join(work, "in" + (os.path.splitext(name or "")[1] or ".webm"))
        with open(src, "wb") as f:
            f.write(data)
        total = _duration(src)
        out = os.path.join(work, "audio.mp3")
        cmd = [ff, "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000",
               "-b:a", "64k", "-t", str(int(seconds)), out]
        r = subprocess.run(cmd, capture_output=True, timeout=900)
        if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) == 0:
            tail = r.stderr.decode("utf-8", "replace")[-300:]
            return None, total, False, f"音声を取り出せませんでした（{tail.strip()}）"
        with open(out, "rb") as f:
            audio = f.read()
        truncated = bool(total and total > seconds + 1)
        return audio, total, truncated, None
    except Exception as e:
        return None, None, False, f"音声の抽出に失敗しました: {e}"
    finally:
        shutil.rmtree(work, ignore_errors=True)


def transcribe(data: bytes, name: str = "rec.webm", mime: str = "") -> dict:
    """録画/録音を文字起こしする。{ok, text, seconds, truncated} / {error}。"""
    if not data:
        return {"error": "ファイルが空です"}
    if len(data) > MAX_UPLOAD_BYTES:
        return {"error": f"ファイルが大きすぎます（上限 {MAX_UPLOAD_BYTES // 1_000_000}MB）"}

    audio, total, truncated, err = extract_audio(data, name)
    if err:
        return {"error": err}

    try:
        import config
        model = config.get_gemini_model()
    except Exception:
        model = None
    if model is None:
        return {"error": "文字起こしには Gemini のキーが必要です（設定 → KEYCHAIN）"}

    prompt = (
        "この音声を日本語で文字起こししてください。\n"
        "・聞こえたことだけを書き、内容の要約や補足はしない\n"
        "・話者が変わったら改行する\n"
        "・聞き取れない部分は （聞き取れず） と書く\n"
        "・相槌や言い直しは自然に整えてよい\n"
        "文字起こしのみを出力してください。"
    )
    try:
        resp = model.generate_content([prompt, {"mime_type": "audio/mp3", "data": audio}])
        text = (getattr(resp, "text", "") or "").strip()
    except Exception as e:
        return {"error": f"文字起こしに失敗しました: {e}"}
    if not text:
        return {"error": "音声から文字を取り出せませんでした（無音の可能性があります）"}
    return {
        "ok": True,
        "text": text,
        "seconds": round(total, 1) if total else None,
        "truncated": truncated,
        "limit_seconds": MAX_AUDIO_SECONDS,
    }


def narration_script(source: str, style: str = "explain", seconds: int = 0,
                     instruction: str = "") -> dict:
    """文字起こし（または構成メモ）から読み上げ台本を作る。{ok, script} / {error}。"""
    source = (source or "").strip()
    if not source:
        return {"error": "元になる文字起こしか構成メモを入れてください"}
    tone = NARRATION_STYLES.get(style, NARRATION_STYLES["explain"])

    # 読み上げの速さから、尺に収まる目安の文字数を出す（日本語は約6字/秒）
    limit = ""
    if seconds and seconds > 0:
        chars = max(80, int(seconds * 5.5))
        limit = f"・動画の長さは約{int(seconds)}秒なので、全体で{chars}字程度に収める\n"

    prompt = (
        "あなたは動画のナレーション作家です。次の素材から、そのまま読み上げられる"
        "ナレーション台本を書いてください。\n"
        f"・{tone}\n"
        "・話し言葉にする。記号や見出し、「ナレーション：」などのラベルは書かない\n"
        "・素材に無い事実を足さない\n"
        "・一文を短くし、息継ぎしやすい区切りで改行する\n"
        + limit
        + (f"・追加の指示: {instruction}\n" if instruction.strip() else "")
        + "\n【素材】\n" + source[:12_000] + "\n\n【ナレーション台本】\n"
    )
    try:
        import llm
        script = (llm.generate_text(prompt, max_tokens=2000) or "").strip()
    except Exception as e:
        return {"error": f"台本の生成に失敗しました: {e}"}
    if not script:
        return {"error": "台本を生成できませんでした"}
    return {"ok": True, "script": script[:MAX_SCRIPT_CHARS],
            "chars": len(script[:MAX_SCRIPT_CHARS])}


def voiceover(video: bytes, narration: bytes, keep_original: bool = False,
              original_volume: float = 0.25) -> dict:
    """録画にナレーション音声を重ねた mp4 を作る。{ok, data, seconds} / {error}。

    keep_original=True なら元の音（操作音や環境音）を小さく残して混ぜる。
    """
    ff = _ffmpeg()
    if not ff:
        return {"error": "サーバーに ffmpeg が無いためナレーションを重ねられません"}
    if not video:
        return {"error": "録画データが空です"}
    if not narration:
        return {"error": "ナレーション音声が空です"}
    if len(video) > MAX_UPLOAD_BYTES:
        return {"error": f"録画が大きすぎます（上限 {MAX_UPLOAD_BYTES // 1_000_000}MB）"}

    work = tempfile.mkdtemp(prefix="capvo_")
    try:
        vin = os.path.join(work, "in.webm")
        ain = os.path.join(work, "narr.mp3")
        out = os.path.join(work, "out.mp4")
        with open(vin, "wb") as f:
            f.write(video)
        with open(ain, "wb") as f:
            f.write(narration)

        if keep_original:
            # 元の音を小さくしてナレーションと混ぜる。元に音声トラックが無い場合も
            # あるので、失敗したらナレーションだけに切り替える。
            vol = max(0.0, min(float(original_volume or 0.25), 1.0))
            cmd = [ff, "-y", "-i", vin, "-i", ain,
                   "-filter_complex",
                   f"[0:a]volume={vol:.2f}[a0];[a0][1:a]amix=inputs=2:duration=first:dropout_transition=0[a]",
                   "-map", "0:v:0", "-map", "[a]",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                   "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out]
            r = subprocess.run(cmd, capture_output=True, timeout=1800)
            if r.returncode != 0:
                keep_original = False       # 音声トラック無しなどで失敗 → 差し替えへ

        if not keep_original:
            cmd = [ff, "-y", "-i", vin, "-i", ain,
                   "-map", "0:v:0", "-map", "1:a:0", "-shortest",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                   "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out]
            r = subprocess.run(cmd, capture_output=True, timeout=1800)

        if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) == 0:
            tail = r.stderr.decode("utf-8", "replace")[-300:]
            return {"error": f"合成に失敗しました（{tail.strip()}）"}
        with open(out, "rb") as f:
            data = f.read()
        return {"ok": True, "data": data, "seconds": _duration(out),
                "mixed": bool(keep_original)}
    except Exception as e:
        return {"error": f"合成に失敗しました: {e}"}
    finally:
        shutil.rmtree(work, ignore_errors=True)
