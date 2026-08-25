"""
api/hooks.py — 外から AIbou を動かすための入口（Webhookトリガー）。

なぜ作るか:
  ・定期実行を無料で確実に回すには、外から叩いてもらうのがいちばん確実
    （無料プランのサーバーは寝るので、内側のループだけでは足りない）。
  ・そして「外から叩ける」ようにすると、それ自体が拡張性になる。
    iOSのショートカット、Googleスプレッドシートのスクリプト、IFTTT、
    そして各自のSupabase（pg_cron）からも、自分の自動化を起こせる。
    どれも無料で、こちらは何も足さなくていい。

安全のための決めごと:
  ・URLを1つ知られただけで何でもできる、にはしない。
    トリガーは「あらかじめ自分で登録した自動化1つ」に結びつける。
    任意の命令を実行させる作りにはしない（URLが漏れた瞬間に乗っ取られる）。
  ・トークンは推測できない長さで、いつでも作り直せる。
  ・誰のトリガーかはトークンから分かる（署名つき）。叩いた人が本人かは
    問わない代わりに、できることを最初から絞ってある。
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import config
import memstore

TABLE = "hooks"

# 保存先が無いときの控え（1人運用）。プロセスが死ぬと消える。
_mem = memstore.TenantList()
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _secret() -> bytes:
    raw = (getattr(config, "KEYCHAIN_SECRET", "")
           or config.SUPABASE_SERVICE_KEY or config.SUPABASE_URL or "aibou-local")
    return hashlib.sha256(str(raw).encode("utf-8")).digest()


def _sign(token_id: str) -> str:
    return hmac.new(_secret(), token_id.encode("ascii"), hashlib.sha256).hexdigest()[:16]


def make_token(token_id: str) -> str:
    """URLに載せる合言葉。id と署名を繋いだもの。"""
    return f"{token_id}.{_sign(token_id)}"


def parse_token(token: str) -> str:
    """合言葉から id を取り出す。壊れていれば空。"""
    t = (token or "").strip()
    if "." not in t:
        return ""
    tid, _, sig = t.partition(".")
    return tid if hmac.compare_digest(sig, _sign(tid)) else ""


def create(user_id: str, automation_id: str, label: str = "") -> dict:
    """トリガーを1つ作る。起動できるのは、その自動化だけ。"""
    user_id = (user_id or "").strip()
    automation_id = (automation_id or "").strip()
    if not automation_id:
        return {"error": "起動する自動化を選んでください"}

    token_id = secrets.token_urlsafe(18)
    row = {
        "id": str(uuid.uuid4()),
        "token_id": token_id,
        "user_id": user_id,
        "automation_id": automation_id,
        "label": (label or "").strip()[:60],
        "created_at": _now(),
        "last_used_at": "",
        "uses": 0,
    }
    c = config.get_supabase()
    if c:
        try:
            c.table(TABLE).insert(row).execute()
        except Exception as e:
            return {"error": f"トリガーを作れませんでした: {str(e)[:180]}"}
    else:
        _mem.insert(0, row)

    return {"ok": True, "id": row["id"], "token": make_token(token_id),
            "label": row["label"], "automation_id": automation_id}


def list_hooks(user_id: str = "") -> List[dict]:
    """一覧。合言葉は作り直さないと二度と見られない、ではなく毎回出す
    （URLを控え忘れた人が詰まないように。漏れたら作り直せばよい）。"""
    rows: List[dict] = []
    c = config.get_supabase()
    if c:
        try:
            rows = (c.table(TABLE).select("*").order("created_at", desc=True)
                    .limit(100).execute().data) or []
        except Exception:
            rows = []
    if not rows:
        rows = list(_mem)
    out = []
    for r in rows:
        out.append({
            "id": r.get("id"),
            "label": r.get("label") or "",
            "automation_id": r.get("automation_id") or "",
            "token": make_token(str(r.get("token_id") or "")),
            "created_at": r.get("created_at") or "",
            "last_used_at": r.get("last_used_at") or "",
            "uses": int(r.get("uses") or 0),
        })
    return out


def delete(hook_id: str) -> dict:
    hid = (hook_id or "").strip()
    if not hid:
        return {"error": "idが空です"}
    c = config.get_supabase()
    if c:
        try:
            c.table(TABLE).delete().eq("id", hid).execute()
            return {"ok": True}
        except Exception as e:
            return {"error": f"削除できませんでした: {str(e)[:180]}"}
    before = len(_mem)
    _mem[:] = [r for r in _mem if r.get("id") != hid]
    return {"ok": True, "removed": before - len(_mem)}


# 連打よけ。1つのトリガーは、この間隔より短く続けては動かさない。
#
# 外に開いた入口なので、URLを知っている人が連打できてしまう。1回ごとに
# AIが動くため、無料枠が一気に削られる。実際の用途（時報・定期実行）で
# 数十秒に何度も叩く必要は無いので、短い間隔を1つ引いておく。
MIN_INTERVAL_SEC = 20.0
_last_fired: dict = {}


def too_soon(hook_id: str) -> bool:
    """直前に動かしたばかりか。連打を弾くために見る。"""
    import time
    last = _last_fired.get(hook_id)
    return bool(last and (time.monotonic() - last) < MIN_INTERVAL_SEC)


def note_fired(hook_id: str) -> None:
    import time
    _last_fired[hook_id] = time.monotonic()


def find_by_token(token: str) -> Optional[dict]:
    """合言葉から、どの人のどの自動化かを引く。

    署名を先に確かめる。総当たりでDBを引かせないため。
    """
    token_id = parse_token(token)
    if not token_id:
        return None
    c = config.get_supabase()
    if c:
        try:
            rows = (c.table(TABLE).select("*").eq("token_id", token_id)
                    .limit(1).execute().data) or []
            if rows:
                return rows[0]
        except Exception:
            pass
    for r in _mem:
        if r.get("token_id") == token_id:
            return r
    return None


def mark_used(hook_id: str) -> None:
    """使われた記録。動いていないトリガーに気づけるように。"""
    for r in _mem:
        if r.get("id") == hook_id:
            r["last_used_at"] = _now()
            r["uses"] = int(r.get("uses") or 0) + 1
    c = config.get_supabase()
    if c:
        try:
            cur = (c.table(TABLE).select("uses").eq("id", hook_id)
                   .limit(1).execute().data) or []
            uses = int((cur[0] if cur else {}).get("uses") or 0) + 1
            c.table(TABLE).update({"last_used_at": _now(), "uses": uses}) \
             .eq("id", hook_id).execute()
        except Exception:
            pass
