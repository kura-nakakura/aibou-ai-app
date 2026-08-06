# compliance.py — 収益コンテンツの法令・規約遵守を「コード側で」担保する
# =====================================================================
# 企画書の §7 リスクヘッジをシステム化する共通モジュール。
#   1) ステマ規制（景品表示法）: 生成物へ PR表記を必ず埋め込む
#   2) プラットフォーム規約: 送信先ごとの可否をゲートで判定（AI生成物の可否など）
#   3) 礼儀としてのレート制御: API連打を避けるランダム遅延
#   4) セミオート原則: 生成物は draft/pending 止まりで、公開は人間の承認が必要
#
# 方針として「検知回避（スパム判定を潜り抜ける加工）」は実装しない。
# 規約に沿って“出せるものを出す”ためのゲートとして機能させる。
# =====================================================================

import random
import time

# 景品表示法（ステマ規制）対応の固定文。記事・動画概要の先頭に必ず入れる。
DISCLOSURE = "※本記事にはプロモーションが含まれています"
DISCLOSURE_VIDEO = "※本動画にはプロモーションが含まれています"

# 送信先ごとのポリシー。allowed=False の送信先へは配信させない（警告を返す）。
#   generative_ok: AI生成コンテンツの投稿が許容されるか
_PLATFORM_POLICY = {
    "note": {
        "allowed": True, "generative_ok": True, "auto_post": False,
        "note": "公式APIが無いため自動投稿はしない。下書きファイルを出力し、人が貼り付けて公開する。",
    },
    "youtube": {
        "allowed": True, "generative_ok": True, "auto_post": False,
        "note": "公式APIで非公開(private)アップロードのみ。公開は人が行う。",
    },
    "pseo": {
        "allowed": True, "generative_ok": True, "auto_post": False,
        "note": "自社サイトなので配信可。ただし承認済みページのみ公開する。",
    },
    "shutterstock": {
        "allowed": False, "generative_ok": False, "auto_post": False,
        "note": "Shutterstockの投稿者規約はAI生成画像の投稿を認めていない。AI生成物の送信は行わない。",
    },
}


def disclosure(kind: str = "article") -> str:
    """PR表記を返す（article / video）。"""
    return DISCLOSURE_VIDEO if kind == "video" else DISCLOSURE


def with_disclosure(text: str, kind: str = "article") -> str:
    """本文の先頭にPR表記を付ける（既に入っていれば二重に付けない）。"""
    body = (text or "").strip()
    mark = disclosure(kind)
    if "プロモーションが含まれています" in body[:200]:
        return body
    prefix = f"> {mark}" if kind == "article" else mark
    return f"{prefix}\n\n{body}" if body else prefix


def has_disclosure(text: str) -> bool:
    return "プロモーションが含まれています" in (text or "")


def platform_policy(platform: str) -> dict:
    """送信先のポリシーを返す。未知の送信先は保守的に allowed=False。"""
    key = (platform or "").strip().lower()
    return _PLATFORM_POLICY.get(key, {
        "allowed": False, "generative_ok": False, "auto_post": False,
        "note": f"未登録の送信先（{platform}）のため、安全側に倒して送信しません。",
    })


def gate(platform: str, ai_generated: bool = True) -> dict:
    """配信可否の判定。{ok, reason}。AI生成物を認めない送信先はここで止める。"""
    p = platform_policy(platform)
    if not p["allowed"]:
        return {"ok": False, "reason": p["note"]}
    if ai_generated and not p["generative_ok"]:
        return {"ok": False, "reason": f"AI生成コンテンツは許容されていません：{p['note']}"}
    return {"ok": True, "reason": p["note"]}


def polite_delay(lo: float = 2.0, hi: float = 6.0, sleep: bool = True) -> float:
    """外部APIへの連打を避けるためのランダム待機（礼儀・レート制御）。
    検知回避のためではなく、相手先に負荷をかけないための素直な間隔調整。"""
    d = random.uniform(lo, hi)
    if sleep:
        time.sleep(d)
    return d
