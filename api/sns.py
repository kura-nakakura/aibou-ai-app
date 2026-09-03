# sns.py — SNS投稿サポート（まずは Instagram / X）
# =====================================================================
# テーマから各SNSの「作法」に合わせた投稿案を複数出す。
#   X (旧Twitter): 280字制限、1〜3個のハッシュタグ、スレッド案も可
#   Instagram    : キャプション（最大2200字）＋ハッシュタグ多め＋画像プロンプト
#
# 自動投稿はしない：X APIは有料枠、Instagramはビジネスアカウント＋Graph API審査が
# 必要で、規約と費用の判断は利用者に属する。ここは「下書きを作ってコピーする」
# までを担い、投稿は人が行う（セミオート原則）。
# PR案件の場合は景品表示法対応の表記を必ず入れる。
# =====================================================================

import jsonout

import json
import re

import compliance
import llm

PLATFORMS = {
    "x": {
        "label": "X (旧Twitter)",
        "limit": 280,
        "tags": "1〜3個",
        "guide": ("1投稿280字以内。冒頭1行で内容が分かるように書く。"
                  "絵文字は控えめ、改行で読みやすく。ハッシュタグは1〜3個まで。"),
    },
    "instagram": {
        "label": "Instagram",
        "limit": 2200,
        "tags": "10〜15個",
        "guide": ("キャプションは冒頭2行が命（続きが折りたたまれる）。"
                  "共感→本題→行動喚起の流れ。改行を多めに。"
                  "ハッシュタグは10〜15個、大中小の規模を混ぜる。"),
    },
}
MAX_VARIANTS = 5
PR_TAG = "#PR"


def _extract_json(text: str):
    """AIの出力からJSONを取り出す。読めなければ None。

    中身は jsonout に1本化してある（同じ関数が10か所にあり、崩れ方への
    強さがばらついていたため）。
    """
    return jsonout.extract(text)


def _norm_tags(tags) -> list:
    if isinstance(tags, str):
        tags = re.split(r"[\s,、]+", tags)
    out = []
    for t in (tags or []):
        t = str(t).strip()
        if not t:
            continue
        if not t.startswith("#"):
            t = "#" + t
        t = re.sub(r"\s+", "", t)
        if t not in out:
            out.append(t)
    return out[:20]


def _norm_post(p, platform: str, promo: bool) -> dict:
    if isinstance(p, str):
        p = {"text": p}
    if not isinstance(p, dict):
        p = {}
    text = str(p.get("text") or p.get("caption") or "").strip()
    tags = _norm_tags(p.get("hashtags") or p.get("tags"))
    if promo and PR_TAG not in tags:
        tags.insert(0, PR_TAG)
    thread = [str(t).strip() for t in (p.get("thread") or []) if str(t).strip()][:5]
    out = {
        "text": text,
        "hashtags": tags,
        "image_prompt": str(p.get("image_prompt") or "")[:300],
        "thread": thread,
    }
    # 文字数（ハッシュタグ込み）を返してUIで超過を可視化する
    joined = text + ("\n\n" + " ".join(tags) if tags else "")
    out["length"] = len(joined)
    out["over_limit"] = out["length"] > PLATFORMS.get(platform, {}).get("limit", 280)
    return out


def generate_posts(platform: str, topic: str, n: int = 3, tone: str = "",
                   promo: bool = False, thread: bool = False) -> dict:
    """投稿案を n 個生成する。{ok, platform, posts:[...]} / {error}。"""
    platform = (platform or "x").strip().lower()
    if platform not in PLATFORMS:
        return {"error": f"未対応のSNSです: {platform}"}
    topic = (topic or "").strip()
    if not topic:
        return {"error": "投稿のテーマ(topic)が空です"}
    try:
        n = max(1, min(int(n or 3), MAX_VARIANTS))
    except Exception:
        n = 3

    meta = PLATFORMS[platform]
    tone_note = f"トーン: {tone}。" if tone.strip() else "トーン: 自然で押し付けない。"
    promo_note = ("これはPR/宣伝投稿です。景品表示法（ステマ規制）に従い、"
                  "本文の冒頭に「PR」であることが分かる記載を入れ、ハッシュタグにも #PR を入れる。"
                  if promo else "宣伝色は出さず、読み手の役に立つ内容にする。")
    thread_note = ("あわせて続きのスレッド案を2〜4個 thread に入れる。" if (thread and platform == "x") else "")

    prompt = (
        f"あなたは{meta['label']}運用のプロです。テーマ「{topic}」について、"
        f"投稿案を{n}個、それぞれ切り口を変えて作ってください。\n"
        f"【{meta['label']}の作法】{meta['guide']}\n"
        f"{tone_note}{promo_note}{thread_note}\n"
        "誇張・断定・根拠のない数値は書かない。実在の他者を騙るような内容は書かない。\n"
        f"ハッシュタグは{meta['tags']}。画像に添えるなら image_prompt に英語の画像プロンプトも。\n"
        "必ず次の形式のJSONだけを ```json ``` の中に出力：\n"
        '```json\n'
        '{"posts":[{"text":"投稿本文","hashtags":["#タグ"],"image_prompt":"english prompt","thread":[]}]}\n'
        '```'
    )
    try:
        text = llm.generate_text(prompt, max_tokens=2200)
    except Exception as e:
        return {"error": f"生成に失敗しました: {e}"}

    data = _extract_json(text) or {}
    raw_posts = data.get("posts") or []
    posts = [_norm_post(p, platform, promo) for p in raw_posts[:n]]
    posts = [p for p in posts if p["text"]]
    if not posts:
        return {"error": "投稿案を生成できませんでした。もう一度お試しください。"}

    return {
        "ok": True,
        "platform": platform,
        "label": meta["label"],
        "limit": meta["limit"],
        "posts": posts,
        "auto_post": False,
        "note": compliance.platform_policy("note").get("note", "") and "投稿は手動で行ってください（自動投稿はしません）。",
    }


def with_image(post: dict) -> dict:
    """image_prompt から画像を生成してURLを添える（任意・無料のimagegenを使用）。"""
    prompt = (post or {}).get("image_prompt") or ""
    if not prompt:
        return post
    try:
        import imagegen
        res = imagegen.generate(prompt, 1080, 1080)
        if res.get("ok"):
            post = dict(post)
            post["image_url"] = res["url"]
    except Exception:
        pass
    return post
