"""
api/inbox.py — 外から届いたメッセージの受け皿（いまは LINE）。

これまで LINE は送るだけだった（notify.send_line）。Messaging API は
「送る」と「受け取る」が別の口で、受け取るには LINE 側からこちらへ
POST してもらう窓口（Webhook）が要る。その窓口と保管がここ。

安全の要点:
  ・LINE以外からの投稿を受け付けない。届いた本文そのものを
    LINE_CHANNEL_SECRET で署名検証し、合わないものは捨てる。
    ここを省くと、URLを知った誰でも偽のメッセージを流し込める。
  ・利用者ごとに窓口を分ける。URLの中の合言葉から持ち主を割り出し、
    その人の保存先に入れる。合言葉は user_id から鍵付きで導出するので、
    他人のIDを知っていても作れない。

保存先は Supabase `inbox_messages`、無ければメモリ（他と同じ縮退）。
"""

import base64
import hashlib
import hmac
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import config
import memstore

TABLE = "inbox_messages"

# 保存先が無いときの控え（保存先ごとに分かれる）
_mem = memstore.TenantList()

# 1回の受信で保存する上限。大量に投げ込まれても膨らませない。
MAX_PER_REQUEST = 20
MAX_TEXT = 2000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── 窓口の合言葉（利用者ごとにURLを分ける） ──────────────────────────
def _secret() -> str:
    return (getattr(config, "KEYCHAIN_SECRET", "") or config.SUPABASE_SERVICE_KEY
            or config.APP_TOKEN or "")


def webhook_token(user_id: str) -> str:
    """その人専用の窓口の合言葉。user_id からは辿れるが、逆は作れない。"""
    uid = (user_id or "").strip()
    secret = _secret()
    if not (uid and secret):
        return ""
    return hmac.new(secret.encode(), f"line-webhook:{uid}".encode(),
                    hashlib.sha256).hexdigest()[:24]


def resolve_token(token: str) -> str:
    """合言葉から持ち主のIDを割り出す。分からなければ空文字。"""
    tok = (token or "").strip()
    if not tok or not _secret():
        return ""
    try:
        import tenancy
        users = tenancy.all_connected_users()
    except Exception:
        return ""
    for uid in users:
        # 総当たりで当てられないよう、比較は定数時間で行う
        if hmac.compare_digest(webhook_token(uid), tok):
            return uid
    return ""


# ── 署名検証（LINEから来たものかを確かめる） ─────────────────────────
def verify_line_signature(body: bytes, signature: str, channel_secret: str) -> bool:
    """LINEの X-Line-Signature を検証する。合わなければ False。

    LINEは本文そのもの（バイト列）をチャネルシークレットでHMAC-SHA256し、
    base64にしたものを送ってくる。整形し直した本文で作ると必ず食い違うため、
    受け取った生のバイト列をそのまま使うこと。
    """
    if not (body and signature and channel_secret):
        return False
    try:
        want = base64.b64encode(
            hmac.new(channel_secret.encode(), body, hashlib.sha256).digest()
        ).decode("ascii")
    except Exception:
        return False
    return hmac.compare_digest(want, signature.strip())


# ── 保管 ─────────────────────────────────────────────────────────────
def add(channel: str, text: str, sender: str = "", ts: str = "",
        external_id: str = "") -> dict:
    """1件保存する。同じ external_id が既にあれば入れ直さない。"""
    text = (text or "").strip()[:MAX_TEXT]
    if not text:
        return {"error": "text is empty"}

    ext = (external_id or "").strip()
    if ext and _exists(ext):
        return {"skipped": True, "external_id": ext}

    row = {
        "id": str(uuid.uuid4()),
        "channel": (channel or "line").strip(),
        "sender": (sender or "").strip()[:120],
        "text": text,
        "external_id": ext,
        "ts": (ts or "").strip(),
        "read": False,
        "created_at": _now(),
    }
    c = config.get_supabase()
    if c:
        try:
            res = c.table(TABLE).insert(row).execute()
            return (res.data or [row])[0]
        except Exception:
            pass
    _mem.insert(0, row)
    return row


def _exists(external_id: str) -> bool:
    """同じメッセージを二重に保存しないための確認。

    LINEは配信を保証する代わりに、同じイベントを2回送ることがある。
    そのまま入れると「新着2件」と嘘の数を報告してしまう。
    """
    c = config.get_supabase()
    if c:
        try:
            rows = (c.table(TABLE).select("id").eq("external_id", external_id)
                    .limit(1).execute().data) or []
            return bool(rows)
        except Exception:
            pass
    return any(m.get("external_id") == external_id for m in _mem)


def list_messages(channel: str = "", unread_only: bool = False,
                  limit: int = 50) -> List[dict]:
    limit = max(1, min(int(limit or 50), 200))
    c = config.get_supabase()
    if c:
        try:
            q = c.table(TABLE).select("*").order("created_at", desc=True).limit(limit)
            if channel:
                q = q.eq("channel", channel)
            if unread_only:
                q = q.eq("read", False)
            rows = q.execute().data
            if rows is not None:
                return rows
        except Exception:
            pass
    items = list(_mem)
    if channel:
        items = [m for m in items if m.get("channel") == channel]
    if unread_only:
        items = [m for m in items if not m.get("read")]
    return items[:limit]


def unread_count(channel: str = "") -> int:
    return len(list_messages(channel=channel, unread_only=True, limit=200))


def mark_read(message_id: str) -> dict:
    for m in _mem:
        if m.get("id") == message_id:
            m["read"] = True
    c = config.get_supabase()
    if c:
        try:
            c.table(TABLE).update({"read": True}).eq("id", message_id).execute()
        except Exception:
            pass
    return {"ok": True}


def mark_all_read(channel: str = "") -> dict:
    for m in _mem:
        if not channel or m.get("channel") == channel:
            m["read"] = True
    c = config.get_supabase()
    if c:
        try:
            q = c.table(TABLE).update({"read": True}).eq("read", False)
            if channel:
                q = q.eq("channel", channel)
            q.execute()
        except Exception:
            pass
    return {"ok": True}


# ── LINEのイベントを取り込む ─────────────────────────────────────────
def ingest_line(payload: dict) -> dict:
    """検証済みのLINE Webhook本文から、テキストメッセージだけを取り出して保存する。

    LINEは既読・友だち追加・スタンプなど色々送ってくるが、
    見張りとして意味があるのは人が書いた文だけ。
    """
    events = (payload or {}).get("events") or []
    saved, skipped = 0, 0
    for ev in events[:MAX_PER_REQUEST]:
        if not isinstance(ev, dict):
            continue
        if ev.get("type") != "message":
            skipped += 1
            continue
        msg = ev.get("message") or {}
        if msg.get("type") != "text":
            skipped += 1
            continue
        src = ev.get("source") or {}
        res = add(
            channel="line",
            text=msg.get("text") or "",
            sender=(src.get("userId") or src.get("groupId") or src.get("roomId") or ""),
            ts=str(ev.get("timestamp") or ""),
            external_id=str(msg.get("id") or ""),
        )
        if res.get("skipped") or res.get("error"):
            skipped += 1
        else:
            saved += 1
    return {"ok": True, "saved": saved, "skipped": skipped}


def status(user_id: str = "") -> dict:
    """UI用。窓口のURLに使う合言葉と、未読の数。"""
    import keychain
    tok = webhook_token(user_id) if user_id else ""
    return {
        "secret_set": bool((keychain.get_key("LINE_CHANNEL_SECRET") or "").strip()),
        "token": tok,
        "path": f"/line/webhook/{tok}" if tok else "/line/webhook",
        "unread": unread_count("line"),
    }
