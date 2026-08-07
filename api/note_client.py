# note_client.py — note への下書き投稿（非公式API）
# =====================================================================
# note には公開APIが無いため、ブラウザが使うのと同じ内部エンドポイントを叩く。
#
#   ⚠ 重要（利用者の判断が必要）
#   * 非公式のため、noteの仕様変更で予告なく動かなくなる可能性がある。
#   * 規約上のリスク（アカウント停止等）は利用者に帰属する。
#   * そのため既定では無効。ALLOW_NOTE_AUTOPOST=1 のときだけ動く。
#   * 公開はせず「下書き(draft)」までに留める（セミオート原則）。
#
# エンドポイントは環境変数/KEYCHAINで差し替え可能にしてある（仕様変更に追従できる）。
#   NOTE_EMAIL, NOTE_PASSWORD … ログイン情報
#   NOTE_SIGNIN_URL  (既定 https://note.com/api/v1/email_signin)
#   NOTE_DRAFT_URL   (既定 https://note.com/api/v1/text_notes)
# 絶対に raise せず、必ず {status, ...} を返す。
# =====================================================================

import compliance

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

DEFAULT_SIGNIN_URL = "https://note.com/api/v1/email_signin"
DEFAULT_DRAFT_URL = "https://note.com/api/v1/text_notes"
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


def _cfg(name: str, default: str = "") -> str:
    """KEYCHAIN → 環境変数の順に設定を読む。"""
    try:
        import keychain
        v = (keychain.get_key(name) or "").strip()
        if v:
            return v
    except Exception:
        pass
    import os
    return (os.environ.get(name, "") or "").strip() or default


def enabled() -> bool:
    """自動投稿が有効か（オプトイン＋認証情報あり）。"""
    gate = compliance.gate("note", ai_generated=True)
    if not gate.get("ok") or not gate.get("overridden"):
        return False
    return bool(_cfg("NOTE_EMAIL") and _cfg("NOTE_PASSWORD"))


def status() -> dict:
    """UI/ログ用の状態。認証情報の値そのものは返さない。"""
    gate = compliance.gate("note", ai_generated=True)
    return {
        "opted_in": bool(gate.get("overridden")),
        "credentials": bool(_cfg("NOTE_EMAIL") and _cfg("NOTE_PASSWORD")),
        "enabled": enabled(),
        "reason": gate.get("reason", ""),
    }


def _login():
    """ログインしてセッション(cookie付き)を返す。失敗時は (None, 理由)。"""
    if requests is None:
        return None, "requests が利用できません"
    email, password = _cfg("NOTE_EMAIL"), _cfg("NOTE_PASSWORD")
    if not (email and password):
        return None, "NOTE_EMAIL / NOTE_PASSWORD が未設定です"
    s = requests.Session()
    s.headers.update({"User-Agent": _UA, "Content-Type": "application/json"})
    try:
        r = s.post(_cfg("NOTE_SIGNIN_URL", DEFAULT_SIGNIN_URL),
                   json={"login": email, "password": password}, timeout=30)
    except Exception as e:
        return None, f"ログイン通信に失敗: {e}"
    if r.status_code >= 400:
        return None, f"ログインに失敗しました（status={r.status_code}）。認証情報またはエンドポイントを確認してください。"
    if not s.cookies:
        return None, "ログインしましたがセッションCookieを取得できませんでした（仕様変更の可能性）"
    return s, ""


def create_draft(title: str, body_markdown: str) -> dict:
    """note に下書きを作成する。{status, url?, reason?}。公開はしない。"""
    title = (title or "").strip()
    body = (body_markdown or "").strip()
    if not (title and body):
        return {"platform": "note", "status": "skipped", "reason": "タイトルまたは本文が空です"}

    st = status()
    if not st["opted_in"]:
        return {"platform": "note", "status": "skipped",
                "reason": "自動投稿は既定で無効です（ALLOW_NOTE_AUTOPOST=1 で有効化）。下書きファイル出力のみ行われます。"}
    if not st["credentials"]:
        return {"platform": "note", "status": "skipped", "reason": "NOTE_EMAIL / NOTE_PASSWORD が未設定です"}

    # 景品表示法（ステマ規制）対応の表記を必ず入れる
    body = compliance.with_disclosure(body, "article")

    session, err = _login()
    if session is None:
        return {"platform": "note", "status": "error", "reason": err}

    compliance.polite_delay(2, 5)  # 連続アクセスを避ける（相手先への配慮）

    payload = {"title": title[:100], "body": body, "status": "draft"}
    try:
        r = session.post(_cfg("NOTE_DRAFT_URL", DEFAULT_DRAFT_URL), json=payload, timeout=45)
    except Exception as e:
        return {"platform": "note", "status": "error", "reason": f"下書き作成の通信に失敗: {e}"}

    if r.status_code >= 400:
        return {"platform": "note", "status": "error",
                "reason": f"下書き作成に失敗（status={r.status_code}）。非公式APIの仕様変更の可能性があります。"}

    key = ""
    try:
        data = r.json() or {}
        d = data.get("data") if isinstance(data.get("data"), dict) else data
        key = str((d or {}).get("key") or (d or {}).get("id") or "")
    except Exception:
        key = ""
    return {
        "platform": "note", "status": "draft_created",
        "url": f"https://note.com/notes/{key}/edit" if key else "https://note.com/notes",
        "note": "下書きとして保存しました。内容を確認して手動で公開してください。",
    }
