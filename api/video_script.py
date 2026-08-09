# video_script.py — 動画の絵コンテ（ストーリーボード）をAIに書かせる
# =====================================================================
# 「テーマを1行書いたら台本ができる」ようにするのが目的。DeeVid のように
# テーマ→シーン分割→ナレーション→画のプロンプト までを一気に用意する。
#
#   storyboard("朝の散歩の効果", n=5, aspect="9:16")
#     → {"ok": True, "scenes": [{"narration": 日本語, "visual": 英語}, ...], "title": ...}
#
# ナレーションは日本語（gTTSで読ませる／字幕に焼く）、visual は英語
# （画像生成モデルは英語プロンプトのほうが安定する）。
# =====================================================================

import json
import re

import llm

MAX_SCENES = 10

# 縦型（Shorts/Reels）は1シーンを短く畳む。横型は少し長めに語れる。
_LENGTH_HINT = {
    "9:16": "1シーン20〜45文字。テンポよく、最初の1シーンで惹きつける。",
    "1:1": "1シーン25〜50文字。",
    "16:9": "1シーン30〜70文字。落ち着いた語り口。",
}

_TONES = {
    "friendly": "親しみやすく、やさしい語り口",
    "calm": "落ち着いた、静かな語り口",
    "energetic": "テンポが速く、元気な語り口",
    "documentary": "ドキュメンタリー風の、事実を淡々と伝える語り口",
}


def _system(n: int, aspect: str, tone: str, style: str) -> str:
    length = _LENGTH_HINT.get(aspect, _LENGTH_HINT["16:9"])
    tone_note = _TONES.get(tone, _TONES["friendly"])
    return (
        "あなたは動画の構成作家です。与えられたテーマから、ナレーション付きの短い動画の"
        f"絵コンテを{n}シーンで作ってください。\n"
        "【出力形式】次のJSONのみを出力（説明文やコードフェンスは書かない）\n"
        '{"title":"動画のタイトル","scenes":[{"narration":"日本語のナレーション",'
        '"visual":"english image prompt"}]}\n'
        "【ナレーション（narration）】\n"
        f"・日本語。{length}\n"
        f"・{tone_note}\n"
        "・そのまま読み上げる文章にする（「シーン1」などの見出しや記号は入れない）\n"
        "・全シーンを通して話が繋がり、最後は締めの一文で終える\n"
        "・事実として断定できないことは書かない（誇張・断定を避ける）\n"
        "【画のプロンプト（visual）】\n"
        "・英語。被写体・構図・光・雰囲気を具体的に書く（例: quiet lake at dawn, "
        "mist over water, soft morning light, wide shot）\n"
        "・文字やロゴを画面に入れる指示はしない（字幕は別で焼き込む）\n"
        + (f"・全シーン共通の画の方向性: {style}\n" if style else "")
    )


def _extract_json(text: str) -> dict:
    """モデル出力からJSONを取り出す（```フェンスや前後の説明を許容）。"""
    t = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        t = m.group(1).strip()
    i, j = t.find("{"), t.rfind("}")
    if i != -1 and j > i:
        t = t[i: j + 1]
    try:
        return json.loads(t)
    except Exception:
        return {}


def storyboard(topic: str, n: int = 5, aspect: str = "16:9",
               tone: str = "friendly", style: str = "") -> dict:
    """テーマから絵コンテを作る。{ok, title, scenes:[{narration,visual}]} / {error}。"""
    topic = (topic or "").strip()
    if not topic:
        return {"error": "動画のテーマが空です"}
    try:
        n = max(2, min(int(n or 5), MAX_SCENES))
    except Exception:
        n = 5

    prompt = _system(n, aspect, tone, style) + "\n【テーマ】\n" + topic
    try:
        text = llm.generate_text(prompt, max_tokens=2000)
    except Exception as e:
        return {"error": f"絵コンテの生成に失敗しました: {e}"}

    data = _extract_json(text)
    raw = data.get("scenes")
    if not isinstance(raw, list) or not raw:
        return {"error": "絵コンテを読み取れませんでした。もう一度お試しください。"}

    scenes = []
    for sc in raw[:n]:
        if not isinstance(sc, dict):
            continue
        narration = str(sc.get("narration") or "").strip()
        visual = str(sc.get("visual") or "").strip()
        if not narration and not visual:
            continue
        scenes.append({"narration": narration[:300], "visual": visual[:300]})
    if not scenes:
        return {"error": "絵コンテを読み取れませんでした。もう一度お試しください。"}

    title = str(data.get("title") or topic[:40]).strip()[:120]
    return {"ok": True, "title": title, "scenes": scenes}
