# slackread.py — Slack を「読む」（notify.send_slack は送るだけ）
# =====================================================================
# これまで Slack は Incoming Webhook 経由の送信専用だった。Webhook は
# 投稿しかできない仕組みなので、いくらトークンを増やしても読めない。
# 読むには Bot トークン（xoxb-…）と Web API が要る。
#
# 認証情報（KEYCHAIN）:
#   SLACK_BOT_TOKEN … xoxb- で始まる Bot User OAuth Token
#   SLACK_CHANNELS  … 任意。カンマ区切りのチャンネルID。空なら
#                     「Botが入っている全部」を見る
#
# 必要なスコープ（Slack App の OAuth & Permissions で付ける）:
#   channels:history / groups:history / im:history / mpim:history
#   channels:read    / groups:read    / im:read    / mpim:read
#   users:read（発言者の名前を出すため。無くても動く）
#
# 設計方針は他モジュールと同じ。設定が欠けても crash せず、
# 「なぜ読めないのか」を日本語で返す（黙って空を返さない）。
# =====================================================================

from typing import Dict, List

import keychain

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

API = "https://slack.com/api/"
_TIMEOUT = 15

# 発言者IDから表示名への対応。毎回 users.info を叩くと遅いので覚えておく。
_name_cache: Dict[str, str] = {}

# Slack が返すエラー語を、人が読める日本語にする。
# 「ok:false」だけ見せられても何をすればいいか分からない。
_ERRORS = {
    "not_authed": "トークンが送られていません",
    "invalid_auth": "トークンが正しくありません（xoxb- で始まる Bot トークンを入れてください）",
    "account_inactive": "このトークンのアカウントが無効になっています",
    "token_revoked": "トークンが取り消されています。Slack Appで作り直してください",
    "missing_scope": "権限（スコープ）が足りません",
    "not_in_channel": "Botがそのチャンネルに入っていません（チャンネルで /invite してください）",
    "channel_not_found": "チャンネルが見つかりません",
    "ratelimited": "Slack側で回数制限にかかりました。しばらく待ってください",
}


def _token() -> str:
    return (keychain.get_key("SLACK_BOT_TOKEN") or "").strip()


def configured() -> bool:
    return bool(_token())


def _explain(d: dict) -> str:
    """Slack のエラー応答を日本語1行にする。"""
    err = str(d.get("error") or "unknown")
    msg = _ERRORS.get(err, f"Slackがエラーを返しました（{err}）")
    needed = d.get("needed")
    if err == "missing_scope" and needed:
        msg += f"。Slack Appに {needed} を追加して、入れ直してください"
    return msg


def _api(method: str, params: dict | None = None) -> dict:
    """Slack Web API を1回叩く。{"ok":True, ...} / {"ok":False,"error":日本語}。"""
    tok = _token()
    if not tok:
        return {"ok": False, "error": "Slackのトークンが未設定です", "skipped": True}
    if requests is None:  # pragma: no cover
        return {"ok": False, "error": "requests が利用できません"}
    try:
        r = requests.get(API + method, params=params or {},
                         headers={"Authorization": f"Bearer {tok}"}, timeout=_TIMEOUT)
        d = r.json() if r.content else {}
    except Exception as e:
        return {"ok": False, "error": f"Slackに繋がりませんでした（{str(e)[:120]}）"}
    if not d.get("ok"):
        return {"ok": False, "error": _explain(d)}
    return d


def status() -> dict:
    """繋がっているかを実際に1回叩いて確かめる。設定だけ見て「接続済み」と言わない。"""
    if not configured():
        return {"configured": False, "connected": False}
    d = _api("auth.test")
    if not d.get("ok"):
        return {"configured": True, "connected": False, "error": d.get("error", "")}
    return {"configured": True, "connected": True,
            "team": d.get("team", ""), "bot": d.get("user", "")}


def _display_name(user_id: str) -> str:
    """発言者の表示名。取れなければIDのまま返す（名前が無くても本文は読める）。"""
    uid = (user_id or "").strip()
    if not uid:
        return ""
    if uid in _name_cache:
        return _name_cache[uid]
    d = _api("users.info", {"user": uid})
    prof = (d.get("user") or {}).get("profile") or {} if d.get("ok") else {}
    name = (prof.get("display_name") or prof.get("real_name")
            or (d.get("user") or {}).get("name") or uid)
    _name_cache[uid] = name
    return name


def _channels() -> dict:
    """見に行くチャンネルの一覧。SLACK_CHANNELS があればそれだけ。"""
    picked = [c.strip() for c in (keychain.get_key("SLACK_CHANNELS") or "").split(",") if c.strip()]
    if picked:
        return {"ok": True, "items": [{"id": c, "name": c} for c in picked]}
    d = _api("users.conversations",
             {"types": "public_channel,private_channel,im,mpim", "limit": 50,
              "exclude_archived": "true"})
    if not d.get("ok"):
        return d
    items = [{"id": c.get("id", ""), "name": c.get("name") or ("DM" if c.get("is_im") else "")}
             for c in (d.get("channels") or []) if c.get("id")]
    return {"ok": True, "items": items}


def recent(limit: int = 20, per_channel: int = 5) -> dict:
    """Botが見えている範囲の新しい発言を返す。

    {"ok":True, "items":[{key,channel,who,text,ts,url}]} /
    {"ok":False, "error": 日本語}
    """
    if not configured():
        return {"ok": False, "skipped": True,
                "error": "Slackのトークン（SLACK_BOT_TOKEN）が未設定です"}

    chans = _channels()
    if not chans.get("ok"):
        return {"ok": False, "error": chans.get("error", "チャンネル一覧を取得できませんでした")}

    channels = chans.get("items") or []
    if not channels:
        return {"ok": True, "items": [],
                "note": "Botがどのチャンネルにも入っていません。読みたいチャンネルで /invite してください"}

    items: List[dict] = []
    errors: List[str] = []
    for ch in channels[:20]:
        d = _api("conversations.history",
                 {"channel": ch["id"], "limit": max(1, min(int(per_channel or 5), 20))})
        if not d.get("ok"):
            # 1つのチャンネルで失敗しても、他のチャンネルは読む
            errors.append(f"#{ch.get('name') or ch['id']}: {d.get('error', '')}")
            continue
        for m in d.get("messages") or []:
            text = (m.get("text") or "").strip()
            if not text or m.get("subtype") == "channel_join":
                continue
            ts = str(m.get("ts") or "")
            items.append({
                "key": f"{ch['id']}:{ts}",
                "channel": ch.get("name") or ch["id"],
                "who": _display_name(m.get("user") or m.get("bot_id") or ""),
                "text": text[:300],
                "ts": ts,
                "url": "",
            })

    items.sort(key=lambda x: x["ts"], reverse=True)
    out = {"ok": True, "items": items[:max(1, int(limit or 20))]}
    if errors and not items:
        # 全滅したときは、握りつぶさず理由を返す
        return {"ok": False, "error": " / ".join(errors[:3])}
    if errors:
        out["warning"] = " / ".join(errors[:3])
    return out
