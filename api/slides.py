# slides.py — スライド資料（プレゼン）の生成＋デザイン
# =====================================================================
# トピックから「デザインされたスライド構成」を JSON で生成する。
#   deck = {
#     "title": "...", "theme": "midnight",
#     "slides": [{"layout": "title", "title": "...", "subtitle": "...", "image": "url"}, ...]
#   }
# レイアウト: title / section / bullets / two_col / stat / quote / image
# theme はフロントの配色プリセット名。image は英語プロンプト→Pollinations URL に変換。
# 設定が欠けても crash せず、フォールバックのデッキを返す。
# =====================================================================

import json
import re

import llm

THEMES = ["midnight", "aurora", "sunset", "forge", "mono"]
LAYOUTS = ["title", "section", "bullets", "two_col", "stat", "quote", "image"]
MAX_IMAGES = 5  # 1デッキあたりの自動画像枚数の上限


def _extract_json(text: str):
    text = text or ""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    raw = m.group(1) if m else None
    if raw is None:
        s = text.find("{")
        e = text.rfind("}")
        raw = text[s:e + 1] if s != -1 and e > s else None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _norm_slide(s) -> dict:
    """1枚のスライドを正規化する（旧形式=bulletsのみ、にも対応）。"""
    if isinstance(s, str):
        return {"layout": "bullets", "title": s[:120], "bullets": []}
    if not isinstance(s, dict):
        return {"layout": "bullets", "title": "", "bullets": []}

    layout = str(s.get("layout") or "").strip().lower()
    if layout not in LAYOUTS:
        layout = "bullets"

    bullets = s.get("bullets") or s.get("points") or []
    if isinstance(bullets, str):
        bullets = [bullets]
    bullets = [str(b)[:200] for b in bullets if str(b).strip()][:8]

    out = {
        "layout": layout,
        "title": str(s.get("title") or "")[:150],
        "bullets": bullets,
        "notes": str(s.get("notes") or "")[:500],
    }
    for k in ("subtitle", "stat", "quote", "author", "image"):
        v = s.get(k)
        if v:
            out[k] = str(v)[:400]
    return out


def _normalize(deck, fallback_title: str = "スライド") -> dict:
    if not isinstance(deck, dict):
        deck = {}
    title = str(deck.get("title") or fallback_title)[:120]
    theme = str(deck.get("theme") or "midnight").strip().lower()
    if theme not in THEMES:
        theme = "midnight"
    slides = [_norm_slide(s) for s in (deck.get("slides") or [])[:30]]
    slides = [s for s in slides if s.get("title") or s.get("bullets") or s.get("quote") or s.get("stat") or s.get("image")]
    if not slides:
        slides = [{"layout": "title", "title": title, "subtitle": "", "bullets": []}]
    return {"title": title, "theme": theme, "slides": slides}


def _apply_images(deck: dict) -> dict:
    """image フィールドが英語プロンプトなら Pollinations URL に変換する（上限あり）。"""
    try:
        import imagegen
    except Exception:
        return deck
    used = 0
    for s in deck.get("slides", []):
        img = s.get("image")
        if not img:
            continue
        if str(img).startswith("http"):
            continue
        if used >= MAX_IMAGES:
            s.pop("image", None)
            continue
        res = imagegen.generate(str(img), 1280, 720)
        if res.get("ok"):
            s["image"] = res["url"]
            used += 1
        else:
            s.pop("image", None)
    return deck


def generate_deck(topic: str, n: int = 6, theme: str = "", with_images: bool = True) -> dict:
    """トピックからデザイン付きのスライド構成を生成する。"""
    topic = (topic or "").strip()
    if not topic:
        return {"error": "topic is empty"}
    try:
        n = max(3, min(int(n or 6), 15))
    except Exception:
        n = 6
    theme = (theme or "").strip().lower()
    theme_hint = theme if theme in THEMES else "内容に合うものを選ぶ"

    prompt = (
        f"あなたはプロのプレゼンデザイナーです。テーマ「{topic}」について、"
        f"{n}枚程度の「デザインされた」スライド構成を作ってください。\n"
        "各スライドに最適な layout を割り当てます：\n"
        "- title: 表紙（title, subtitle, image=表紙背景の英語画像プロンプト）\n"
        "- section: 章の区切り（title）\n"
        "- bullets: 見出し+箇条書き（title, bullets 2〜5個）\n"
        "- two_col: 箇条書きが6個前後と多い時（title, bullets）\n"
        "- stat: 重要な数字を大きく見せる（stat 例\"+30%\", title=その説明）\n"
        "- quote: 引用・キーメッセージ（quote, author）\n"
        "- image: 画像で見せる（title, image=英語画像プロンプト, bullets任意）\n"
        "1枚目は必ず title、最後は section か bullets の『まとめ』。"
        "image は表紙と image レイアウトのみ、短い英語プロンプトにする（多用しない）。\n"
        f"theme は次から1つ選ぶ: {', '.join(THEMES)}（{theme_hint}）。\n"
        "必ず次の形式のJSONだけを ```json ``` の中に出力：\n"
        '```json\n'
        '{"title":"タイトル","theme":"midnight","slides":['
        '{"layout":"title","title":"...","subtitle":"...","image":"..."},'
        '{"layout":"bullets","title":"...","bullets":["..."]}]}\n'
        '```'
    )
    try:
        text = llm.generate_text(prompt, max_tokens=2200)
    except Exception as e:
        return {"error": f"generation failed: {e}"}
    deck = _extract_json(text)
    if not deck:
        deck = {"title": topic, "theme": theme or "midnight", "slides": [
            {"layout": "title", "title": topic, "subtitle": "自動生成の簡易版"},
        ]}
    deck = _normalize(deck, topic)
    if theme in THEMES:
        deck["theme"] = theme
    if with_images:
        deck = _apply_images(deck)
    return deck


# 各レイアウトが使うフィールド（フロントの編集フォームと共有する定義）
LAYOUT_FIELDS = {
    "title": ["title", "subtitle", "image"],
    "section": ["title", "subtitle"],
    "bullets": ["title", "bullets"],
    "two_col": ["title", "bullets"],
    "stat": ["stat", "title", "subtitle"],
    "quote": ["quote", "author"],
    "image": ["title", "image", "bullets"],
}

LAYOUT_LABELS = {
    "title": "表紙",
    "section": "章の区切り",
    "bullets": "箇条書き",
    "two_col": "2段組み",
    "stat": "数字を大きく",
    "quote": "引用",
    "image": "画像で見せる",
}


def revise_slide(slide: dict, instruction: str, deck_title: str = "",
                 layout: str = "", context: str = "") -> dict:
    """1枚だけをAIで書き直す（Genspark のようなスライド単位の編集）。

    デッキ全体を作り直すと他の枚が変わってしまうので、対象の1枚と
    前後の文脈だけを渡して、その枚だけを返させる。
    {"ok": True, "slide": {...}} / {"error": ...}
    """
    instruction = (instruction or "").strip()
    if not instruction:
        return {"error": "修正指示が空です"}
    if not isinstance(slide, dict):
        slide = {}

    want = layout.strip().lower() if layout else ""
    if want and want not in LAYOUTS:
        want = ""
    layout_note = (
        f"レイアウトは必ず \"{want}\"（{LAYOUT_LABELS.get(want, want)}）にする。"
        f"使うフィールド: {', '.join(LAYOUT_FIELDS.get(want, []))}"
        if want else
        "レイアウトは内容に最も合うものを選ぶ（変えなくてよければそのまま）。"
    )

    prompt = (
        "あなたはプロのプレゼンデザイナーです。スライド1枚だけを修正してください。\n"
        + (f"【資料のタイトル】{deck_title}\n" if deck_title else "")
        + (f"【前後のスライド】{context}\n" if context else "")
        + "【いまのスライド】\n" + json.dumps(slide, ensure_ascii=False) + "\n"
        + "【修正指示】\n" + instruction + "\n\n"
        + f"{layout_note}\n"
        f"使えるレイアウト: {', '.join(LAYOUTS)}\n"
        "・箇条書きは1項目を短く（長い文章にしない）\n"
        "・事実として断定できないことは書かない\n"
        "・image は短い英語の画像プロンプト（不要なら入れない）\n"
        "修正後のスライド1枚のJSONだけを ```json ``` の中に出力してください。\n"
        '```json\n{"layout":"bullets","title":"...","bullets":["..."]}\n```'
    )
    try:
        text = llm.generate_text(prompt, max_tokens=1200)
    except Exception as e:
        return {"error": f"修正に失敗しました: {e}"}

    data = _extract_json(text)
    if not isinstance(data, dict):
        return {"error": "修正結果を読み取れませんでした。もう一度お試しください。"}
    # デッキ全体が返ってきた場合は先頭の1枚を採用する
    if "slides" in data and isinstance(data.get("slides"), list) and data["slides"]:
        data = data["slides"][0]

    out = _norm_slide(data)
    if want:
        out["layout"] = want
    if not (out.get("title") or out.get("bullets") or out.get("quote")
            or out.get("stat") or out.get("image")):
        return {"error": "修正結果が空でした。もう一度お試しください。"}
    return {"ok": True, "slide": out}


def to_markdown(deck: dict) -> str:
    """デッキを Markdown 化する（ドキュメントとして扱いたい時用）。"""
    deck = _normalize(deck)
    lines = [f"# {deck['title']}", ""]
    for i, s in enumerate(deck["slides"], start=1):
        head = s.get("title") or s.get("quote") or s.get("stat") or "(無題)"
        lines.append(f"## {i}. {head}")
        if s.get("subtitle"):
            lines.append(f"*{s['subtitle']}*")
        for b in s.get("bullets", []):
            lines.append(f"- {b}")
        if s.get("author"):
            lines.append(f"— {s['author']}")
        if s.get("notes"):
            lines.append(f"\n> {s['notes']}")
        lines.append("")
    return "\n".join(lines)
