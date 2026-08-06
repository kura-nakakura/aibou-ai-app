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


# 既定はブロックだが、アカウント所有者の判断で解除できるフラグ（KEYCHAIN/環境変数）。
# 各プラットフォームの規約に同意・確認するのは利用者本人なので、こちらで恒久的に
# 禁止はしない。既定OFF＋明示的なオプトインという形にして、事故を防ぐ。
_OVERRIDE_FLAGS = {
    "shutterstock": "ALLOW_AI_STOCK_UPLOAD",   # AI生成画像をストックへ送るか
    "note": "ALLOW_NOTE_AUTOPOST",             # note へ自動投稿するか（非公式API）
}


def _flag(name: str) -> bool:
    """KEYCHAIN → 環境変数の順に真偽フラグを読む。"""
    val = ""
    try:
        import keychain
        val = (keychain.get_key(name) or "").strip()
    except Exception:
        val = ""
    if not val:
        import os
        val = (os.environ.get(name, "") or "").strip()
    return val.lower() in ("1", "true", "yes", "on")


def platform_policy(platform: str) -> dict:
    """送信先のポリシーを返す。未知の送信先は保守的に allowed=False。
    オプトインフラグが立っている送信先は allowed/generative_ok を解除する。"""
    key = (platform or "").strip().lower()
    base = _PLATFORM_POLICY.get(key)
    if base is None:
        return {
            "allowed": False, "generative_ok": False, "auto_post": False, "overridden": False,
            "note": f"未登録の送信先（{platform}）のため、安全側に倒して送信しません。",
        }
    p = dict(base)
    flag = _OVERRIDE_FLAGS.get(key)
    if flag and _flag(flag):
        p["allowed"] = True
        p["generative_ok"] = True
        p["overridden"] = True
        p["note"] = (f"{flag}=1 により利用者の判断で有効化されています。"
                     f"規約の確認と結果の責任は利用者に帰属します（元の注意: {base['note']}）")
    else:
        p["overridden"] = False
        if flag and not base["allowed"]:
            p["note"] = f"{base['note']} 送る場合は {flag}=1 を設定してください（自己責任）。"
    return p


def gate(platform: str, ai_generated: bool = True) -> dict:
    """配信可否の判定。{ok, reason}。既定でブロックされる送信先は
    オプトインフラグ（例 ALLOW_AI_STOCK_UPLOAD=1）で解除できる。"""
    p = platform_policy(platform)
    if not p["allowed"]:
        return {"ok": False, "reason": p["note"]}
    if ai_generated and not p["generative_ok"]:
        return {"ok": False, "reason": f"AI生成コンテンツは許容されていません：{p['note']}"}
    return {"ok": True, "reason": p["note"], "overridden": p.get("overridden", False)}


def policy_report() -> dict:
    """全送信先の現在のポリシー（UI表示用）。"""
    return {k: platform_policy(k) for k in _PLATFORM_POLICY}


def polite_delay(lo: float = 2.0, hi: float = 6.0, sleep: bool = True) -> float:
    """外部APIへの連打を避けるためのランダム待機（礼儀・レート制御）。
    検知回避のためではなく、相手先に負荷をかけないための素直な間隔調整。"""
    d = random.uniform(lo, hi)
    if sleep:
        time.sleep(d)
    return d
