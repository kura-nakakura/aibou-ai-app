# renderer.py — 動画/音声レンダリング（スケルトン / 後で実装）
# =================================================================
# 環境音(asset_engine.generate_ambient_wav)＋静止画(generate_thumbnail/画像)から、
# YouTube投稿用の動画ファイル等を合成する工程。実合成(FFmpeg等)は後で実装する。
#
# いまは“枠だけ”：未実装の関数は None を返す（絶対にraiseしない）。これにより
# publisher / run_publisher 側は「アセット未提供 → 公式アップロードはskip」と
# 安全に振る舞い、ここを実装すれば自動的に実投入できるようになる。
# =================================================================

import os
import shutil
import subprocess


def _ffmpeg():
    return shutil.which("ffmpeg")


def is_available():
    """FFmpeg が使えるか（headless環境にインストールされているか）。"""
    return _ffmpeg() is not None


def _safe_name(text, fallback="asset"):
    s = "".join(c for c in (text or "") if c.isalnum() or c in " -_").strip()[:40]
    return s or fallback


def _ken_burns_vf(seconds, fps, seed=0, amp=0.12):
    """ケン・バーンズ効果（ゆっくりズーム＋パン）のフィルタグラフを組む。

    静止画をそのまま流すと“紙芝居”になり視聴体験が悪いので、映像編集の定番である
    緩やかなズーム/パンを入れて「見られる動画」にする（作品としての品質向上）。

    実装メモ:
      * 先に 2倍解像度へ拡大しておくと、ズームしても解像が落ちない。
      * zoompan の z は出力フレーム番号 `on` から算出する。ループ入力では
        `zoom+inc` 方式だと毎フレーム状態がリセットされ得るため、`on` 基準にする。
      * seed で「寄り/引き」とパン方向を決め、動画ごとに動きが変わるようにする。
    """
    total = max(1, int(seconds) * int(fps))
    zoom_in = (seed % 2) == 0
    # 寄り: 1.0 → 1+amp / 引き: 1+amp → 1.0
    z = (f"1+{amp:.4f}*on/{total}" if zoom_in else f"{1 + amp:.4f}-{amp:.4f}*on/{total}")
    # パン先（中央 / やや左上 / やや右下）を seed で選ぶ
    pan = seed % 3
    if pan == 0:
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif pan == 1:
        x, y = f"iw/2-(iw/zoom/2)-(iw*0.04*on/{total})", f"ih/2-(ih/zoom/2)-(ih*0.03*on/{total})"
    else:
        x, y = f"iw/2-(iw/zoom/2)+(iw*0.04*on/{total})", f"ih/2-(ih/zoom/2)+(ih*0.03*on/{total})"

    return (
        "scale=2560:1440:force_original_aspect_ratio=increase,"
        "crop=2560:1440,"
        f"zoompan=z='{z}':d=1:x='{x}':y='{y}':s=1280x720:fps={fps},"
        "format=yuv420p"
    )


def _build_ffmpeg_cmd(ff, image_path, audio_path, out_path, seconds, fps=24, seed=0, motion=True):
    """静止画＋環境音(ループ)を seconds 秒の mp4 にする ffmpeg コマンドを組む。

    motion=True ならケン・バーンズ効果で滑らかに動かす（既定・fps=24）。
    motion=False は従来の静止画スライド（軽量・fpsは呼び出し側で下げる想定）。
    """
    if motion:
        vf = _ken_burns_vf(seconds, fps, seed)
        vcodec_opts = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "24"]
    else:
        vf = ("scale=1280:720:force_original_aspect_ratio=decrease,"
              "pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p")
        vcodec_opts = ["-c:v", "libx264", "-tune", "stillimage"]

    return [
        ff, "-y",
        "-loop", "1", "-framerate", str(fps), "-i", image_path,
        "-stream_loop", "-1", "-i", audio_path,
        "-t", str(int(seconds)),
        "-vf", vf,
        *vcodec_opts,
        "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        out_path,
    ]


def render_video(job, audio_path=None, image_path=None, out_dir="rendered", minutes=None):
    """静止画(image)＋環境音(audio)をループして mp4 を合成する。
    ffmpeg または入力ファイルが無ければ None を返す（絶対にraiseしない）。
    尺は minutes（既定: 環境変数 RENDER_MINUTES または 10分）。"""
    ff = _ffmpeg()
    if not ff:
        return None
    if not (audio_path and os.path.exists(audio_path)) or not (image_path and os.path.exists(image_path)):
        return None
    try:
        mins = float(minutes if minutes is not None else (os.environ.get("RENDER_MINUTES") or 10))
        seconds = max(5, int(mins * 60))
        os.makedirs(out_dir, exist_ok=True)
        jid = str(job.get("id", "x"))[:8]
        out_path = os.path.join(out_dir, f"{jid}_{_safe_name(job.get('theme'))}.mp4")
        # テーマ/IDから決まる seed で、動画ごとにズーム方向とパンを変える
        # （同じ入力なら同じ結果＝再現性あり）。
        seed = abs(hash(f"{jid}{job.get('theme', '')}")) % 6
        motion = (os.environ.get("RENDER_MOTION", "1") != "0")
        fps = int(os.environ.get("RENDER_FPS") or (24 if motion else 2))
        cmd = _build_ffmpeg_cmd(ff, image_path, audio_path, out_path, seconds,
                                fps=fps, seed=seed, motion=motion)
        timeout = int(os.environ.get("RENDER_TIMEOUT_SEC") or 1800)
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return out_path
        return None
    except Exception:
        return None


def build_assets(job):
    """1ジョブから配信用アセット {"images":[png], "video": mp4} を生成する。
    画像は asset_image キーで生成。ffmpeg があれば環境音＋画像から mp4 も合成する。
    publish_shutterstock には画像、publish_youtube には動画が渡る（認証情報がある場合のみ実投入）。"""
    assets = {}
    try:
        import asset_engine
        import key_manager
        payload = job.get("payload", {}) or {}
        theme = job.get("theme", "")
        prompt = (payload.get("shutterstock", {}) or {}).get("title_en") or theme
        os.makedirs("rendered", exist_ok=True)
        jid = str(job.get("id", "x"))[:8]
        safe = _safe_name(theme)

        # 画像（asset_image 用途キー：env の用途別→共通）
        _, key = key_manager.resolve_key("asset_image")
        img, _src = asset_engine.generate_image(prompt, gemini_key=key)
        img_path = None
        if img:
            img_path = os.path.join("rendered", f"{jid}_{safe}.png")
            with open(img_path, "wb") as f:
                f.write(img)
            assets["images"] = [img_path]

        # 動画（ffmpeg があるときだけ：環境音ベースクリップ→ループmp4）
        if img_path and is_available():
            sec = int(os.environ.get("RENDER_AUDIO_SEC") or 60)
            wav, _kind = asset_engine.generate_ambient_wav(theme, duration_sec=sec)
            if wav:
                aud_path = os.path.join("rendered", f"{jid}_{safe}.wav")
                with open(aud_path, "wb") as f:
                    f.write(wav)
                vid = render_video(job, audio_path=aud_path, image_path=img_path)
                if vid:
                    assets["video"] = vid
    except Exception:
        pass
    return assets


# =================================================================
# Forge Lab 用：絵コンテ（複数シーン）から画像＋ナレーション＋字幕のMP4を合成
# =================================================================

# 出力比率のプリセット。縦型（Shorts / Reels / TikTok）に対応するのが要点。
VIDEO_ASPECTS = {
    "16:9": (1280, 720, "横長（YouTube）"),
    "9:16": (720, 1280, "縦型（Shorts / Reels / TikTok）"),
    "1:1": (1080, 1080, "正方形（Instagramフィード）"),
}

MAX_SCENES = 10

# 日本語字幕を焼き込むためのフォント候補（Dockerfileで fonts-ipafont-gothic を入れる）
_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",   # 最後の砦（日本語は出ない）
)


def font_path():
    """字幕に使える日本語フォントのパス。見つからなければ None（字幕なしで続行）。"""
    for p in _FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def has_filter(name):
    """ffmpeg にそのフィルタが組み込まれているか（drawtext は libfreetype 依存）。"""
    ff = _ffmpeg()
    if not ff:
        return False
    try:
        r = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, timeout=20)
        return f" {name} " in r.stdout.decode("utf-8", "ignore")
    except Exception:
        return False


def wrap_ja(text, per_line=22, max_lines=3):
    """日本語は単語区切りが無いので、文字数で折り返す（句読点の直後で優先的に折る）。

    ffmpeg の drawtext は自動改行しないため、こちらで改行を入れておく必要がある。
    """
    t = " ".join((text or "").split())
    if not t:
        return ""
    lines, cur = [], ""
    for ch in t:
        cur += ch
        # 句読点で区切れるならそこで折り返す（読みやすさ優先）
        if len(cur) >= per_line or (ch in "。！？" and len(cur) >= per_line * 0.6):
            lines.append(cur)
            cur = ""
            if len(lines) >= max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    out = [ln.strip() for ln in lines if ln.strip()]
    # 入り切らなかった分は最後の行に「…」を付けて示す
    used = sum(len(ln) for ln in lines)
    if used < len(t) and out:
        out[-1] = out[-1][: max(1, per_line - 1)] + "…"
    return "\n".join(out)


def subtitle_metrics(width, height):
    """字幕の (フォントサイズ, 1行の文字数, 下マージン) を実際の画面寸法から決める。

    文字サイズを height だけで決めると、縦型（720x1280）では横にはみ出す。
    日本語は全角＝送り幅がほぼフォントサイズなので、短辺基準でサイズを決め、
    1行の文字数は「使える横幅 ÷ フォントサイズ」で求める。
    """
    fontsize = max(18, int(round(min(width, height) * 0.045)))
    side = max(int(width * 0.05), int(fontsize * 0.8))     # 左右の余白
    per_line = max(8, int((width - side * 2) // fontsize))
    return fontsize, per_line, int(height * 0.06)


def _subtitle_vf(textfile, font, width, height):
    """字幕（下寄せ・半透明の座布団つき）の drawtext フィルタを組む。

    テキストは textfile 経由で渡す。フィルタ文字列に本文を直接埋めると
    `:` や `'` のエスケープ地獄になるうえ、日本語の記号で壊れやすい。
    """
    fontsize, _per_line, margin = subtitle_metrics(width, height)
    return (
        f"drawtext=fontfile='{font}':textfile='{textfile}'"
        f":fontcolor=white:fontsize={fontsize}:line_spacing={int(fontsize * 0.35)}"
        f":box=1:boxcolor=black@0.55:boxborderw={int(fontsize * 0.5)}"
        f":x=(w-text_w)/2:y=h-text_h-{margin}"
    )


def _scene_vf(width, height, seconds, fps, seed, subtitle_file=None, font=None, motion=True):
    """1シーン分の映像フィルタ（ケン・バーンズ＋フェード＋字幕）を組む。"""
    parts = []
    if motion:
        # 一度大きめに整えてから zoompan で寄る/引く（解像を落とさない）
        big_w, big_h = width * 2, height * 2
        total = max(1, int(round(seconds * fps)))
        zoom_in = (seed % 2) == 0
        amp = 0.12
        z = (f"1+{amp:.4f}*on/{total}" if zoom_in else f"{1 + amp:.4f}-{amp:.4f}*on/{total}")
        pan = seed % 3
        if pan == 0:
            x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        elif pan == 1:
            x, y = f"iw/2-(iw/zoom/2)-(iw*0.04*on/{total})", f"ih/2-(ih/zoom/2)-(ih*0.03*on/{total})"
        else:
            x, y = f"iw/2-(iw/zoom/2)+(iw*0.04*on/{total})", f"ih/2-(ih/zoom/2)+(ih*0.03*on/{total})"
        parts.append(f"scale={big_w}:{big_h}:force_original_aspect_ratio=increase")
        parts.append(f"crop={big_w}:{big_h}")
        parts.append(f"zoompan=z='{z}':d=1:x='{x}':y='{y}':s={width}x{height}:fps={fps}")
    else:
        parts.append(f"scale={width}:{height}:force_original_aspect_ratio=decrease")
        parts.append(f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2")

    # シーンの切り替わりを滑らかにする（黒からのフェードイン／黒へのフェードアウト）
    fade = min(0.4, max(0.15, seconds * 0.12))
    parts.append(f"fade=t=in:st=0:d={fade:.2f}")
    parts.append(f"fade=t=out:st={max(0.0, seconds - fade):.2f}:d={fade:.2f}")

    if subtitle_file and font:
        parts.append(_subtitle_vf(subtitle_file, font, width, height))
    parts.append("format=yuv420p")
    return ",".join(parts)


def _fetch_image_bytes(prompt, width=1280, height=720, timeout=60):
    """Pollinations（無料・キー不要）から画像を取得する。失敗時は None。"""
    try:
        import requests, urllib.parse
        url = (f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt or 'cinematic scene')}"
               f"?width={width}&height={height}&nologo=true")
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200 and r.content:
            return r.content
    except Exception:
        return None
    return None


def _audio_seconds(ff, path):
    """音声の長さ（秒）。取れなければ None。ケン・バーンズの尺算出に使う。"""
    probe = shutil.which("ffprobe") or (ff.replace("ffmpeg", "ffprobe") if ff else None)
    if not probe or not os.path.exists(probe):
        return None
    try:
        r = subprocess.run(
            [probe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, timeout=30,
        )
        return float(r.stdout.decode().strip())
    except Exception:
        return None


def _clip_from_image_audio(ff, image_path, audio_path, out_path, width=1280, height=720,
                           subtitle_file=None, font=None, seed=0, motion=True, fps=24):
    """1枚画像＋ナレーション音声から、音声長に合わせたMP4クリップを作る。

    ケン・バーンズで動かすには尺が必要なので ffprobe で音声長を測る。
    測れないときは静止画スライドに落として、必ず何かを返せるようにする。
    """
    seconds = _audio_seconds(ff, audio_path)
    if seconds is None or seconds <= 0:
        seconds, motion = 5.0, False
    vf = _scene_vf(width, height, seconds, fps, seed, subtitle_file, font, motion)
    cmd = [
        ff, "-y",
        "-loop", "1", "-framerate", str(fps), "-i", image_path,
        "-i", audio_path,
        "-t", f"{seconds:.2f}",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p",
        "-r", str(fps),
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-shortest", "-movflags", "+faststart",
        out_path,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=600)
        if r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return out_path
        # 動きや字幕でフィルタが通らなかった場合は、静止画スライドで作り直す
        if motion or subtitle_file:
            return _clip_from_image_audio(ff, image_path, audio_path, out_path, width, height,
                                          subtitle_file=None, font=None, seed=seed,
                                          motion=False, fps=fps)
    except Exception:
        return None
    return None


def render_forge_video(scenes, image_prompt="", out_dir="rendered", lang="ja",
                       aspect="16:9", subtitles=True):
    """複数シーン [{"narration": 日本語, "visual": 英語(任意)}] から動画を合成する。

    各シーンで Pollinations の画像＋gTTSのナレーションを作り、ケン・バーンズで
    動かし、字幕（narration）を焼き込んでから連結する。
    aspect で縦型（Shorts/Reels）にもできる。
    FFmpeg/ネットワークが無ければ None（絶対にraiseしない）。
    """
    ff = _ffmpeg()
    if not ff or not scenes:
        return None
    width, height, _ = VIDEO_ASPECTS.get(aspect) or VIDEO_ASPECTS["16:9"]
    try:
        from gtts import gTTS
        import tempfile, uuid
        work = tempfile.mkdtemp(prefix="forgevid_")
        # 字幕はフォントと drawtext の両方が揃って初めて焼ける（無ければ字幕なしで続行）
        font = font_path() if subtitles else None
        if font and not has_filter("drawtext"):
            font = None
        # 1行の文字数は画面寸法から決める（縦型は横幅が狭いので自動的に少なくなる）
        _fs, per_line, _mg = subtitle_metrics(width, height)
        motion = (os.environ.get("RENDER_MOTION", "1") != "0")

        clips = []
        for i, sc in enumerate(scenes[:MAX_SCENES]):
            narration = (sc.get("narration") or "").strip()
            visual = (sc.get("visual") or image_prompt or narration or "cinematic scene").strip()
            if not narration:
                narration = visual
            img = _fetch_image_bytes(f"{image_prompt}, {visual}" if image_prompt else visual,
                                     width=width, height=height)
            if not img:
                continue
            img_path = os.path.join(work, f"img_{i}.png")
            with open(img_path, "wb") as f:
                f.write(img)
            try:
                aud_path = os.path.join(work, f"aud_{i}.mp3")
                gTTS(text=narration[:500], lang=lang).save(aud_path)
            except Exception:
                continue

            sub_file = None
            if font:
                wrapped = wrap_ja(narration, per_line=per_line)
                if wrapped:
                    sub_file = os.path.join(work, f"sub_{i}.txt")
                    with open(sub_file, "w", encoding="utf-8") as f:
                        f.write(wrapped)

            clip = _clip_from_image_audio(
                ff, img_path, aud_path, os.path.join(work, f"clip_{i}.mp4"),
                width=width, height=height, subtitle_file=sub_file, font=font,
                seed=i, motion=motion,
            )
            if clip:
                clips.append(clip)
        if not clips:
            return None
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"forge_{uuid.uuid4().hex[:8]}.mp4")
        if len(clips) == 1:
            shutil.copy(clips[0], out_path)
            return out_path
        list_file = os.path.join(work, "list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for c in clips:
                f.write(f"file '{c}'\n")
        r = subprocess.run(
            [ff, "-y", "-f", "concat", "-safe", "0", "-i", list_file,
             "-c", "copy", "-movflags", "+faststart", out_path],
            capture_output=True, timeout=600,
        )
        if r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return out_path
        shutil.copy(clips[0], out_path)  # 連結失敗時は先頭クリップを返す
        return out_path
    except Exception:
        return None
