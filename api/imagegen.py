# imagegen.py — 画像生成（キー不要・無料）
# =====================================================================
# 既定は Pollinations（APIキー不要）。プロンプトから決定的なURLを組み立てて返す
# （同じプロンプト＋seedなら同じ画像）。生成物は artifacts に image として保存し、
# HOMEの「生成物」でサムネイル表示・オープンできる。
# =====================================================================

import hashlib
import urllib.parse

# 用途別のアスペクト比プリセット（SNSや印刷でよく使う比率）
ASPECTS = {
    "1:1": (1024, 1024, "正方形（Instagram）"),
    "4:5": (1024, 1280, "縦長（Instagramフィード）"),
    "9:16": (1080, 1920, "縦全画面（ストーリー/Reels）"),
    "16:9": (1280, 720, "横長（YouTube/スライド）"),
    "3:2": (1200, 800, "写真（ブログ挿絵）"),
}

MAX_VARIANTS = 4


def generate_variants(prompt: str, n: int = 2, aspect: str = "1:1", offset: int = 0) -> dict:
    """同じ指示で複数のバリエーションを作る。{ok, images:[{url,seed}], aspect}。

    Pollinations は seed で絵柄が変わるため、seed を振り分けることで
    「同じ指示の別案」を並べて選べるようにする（ChatGPTの複数枚生成に相当）。
    offset をずらすと、同じ指示のまま“さらに別の案”を出せる（リロール）。
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return {"error": "画像の指示(prompt)が空です"}
    if aspect not in ASPECTS:
        aspect = "1:1"
    try:
        n = max(1, min(int(n or 2), MAX_VARIANTS))
    except Exception:
        n = 2
    try:
        offset = max(0, int(offset or 0))
    except Exception:
        offset = 0
    w, h, _ = ASPECTS[aspect]

    images = []
    for i in range(n):
        res = generate(prompt, w, h, variant=offset + i)
        if res.get("ok"):
            images.append({"url": res["url"], "seed": res["seed"]})
    if not images:
        return {"error": "画像を生成できませんでした"}
    return {"ok": True, "images": images, "aspect": aspect, "width": w, "height": h,
            "prompt": prompt, "offset": offset}


def generate(prompt: str, width: int = 1024, height: int = 1024, variant: int = 0) -> dict:
    """プロンプトから画像URLを作る。{ok, url, provider} / {ok:False, error}。"""
    prompt = (prompt or "").strip()
    if not prompt:
        return {"ok": False, "error": "画像の指示(prompt)が空です"}
    try:
        w = max(256, min(int(width or 1024), 1536))
        h = max(256, min(int(height or 1024), 1536))
    except Exception:
        w, h = 1024, 1024
    # 同じプロンプトなら同じ絵（再現性）。variant を変えると別案になる。
    base = int(hashlib.md5(prompt.encode("utf-8")).hexdigest()[:8], 16)
    seed = (base + int(variant or 0) * 7919) % 100000
    enc = urllib.parse.quote(prompt[:400], safe="")
    url = (f"https://image.pollinations.ai/prompt/{enc}"
           f"?width={w}&height={h}&nologo=true&seed={seed}")
    return {"ok": True, "url": url, "provider": "pollinations", "seed": seed}
