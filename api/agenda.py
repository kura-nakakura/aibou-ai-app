"""
api/agenda.py — 組み込みカレンダー（予定）。

ホーム画面の「予定」。自然言語（例:「明日15時に歯医者」）を Gemini で
{title, date, time} に解釈して登録できる。Supabase `events`、未設定なら
メモリにフォールバック（外部サービスが無くても crash しない）。

※ Google カレンダー等の外部同期はキー設定後の連携フェーズで対応（本モジュールは
   アプリ内蔵カレンダーとして単独で機能する）。
"""

import jsonout

import json
import re
import uuid
from typing import List, Optional

import config
import memstore

_mem_events = memstore.TenantList()
def _extract_json(text: str):
    """AIの出力からJSONを取り出す。読めなければ None。

    中身は jsonout に1本化してある（同じ関数が10か所にあり、崩れ方への
    強さがばらついていたため）。
    """
    return jsonout.extract(text)


def _persist(ev: dict) -> None:
    c = config.get_supabase()
    if not c:
        return
    try:
        c.table("events").upsert(ev).execute()
    except Exception:
        pass


def list_events(limit: int = 100) -> List[dict]:
    c = config.get_supabase()
    if c:
        try:
            rows = (c.table("events").select("*")
                    .order("date", desc=False).limit(limit).execute().data)
            if rows is not None:
                return rows
        except Exception:
            pass
    # メモリは date 昇順で返す
    return sorted(_mem_events, key=lambda e: (e.get("date") or "", e.get("time") or ""))[:limit]


def add_event(title: str, date: str = "", time: str = "", note: str = "") -> dict:
    title = (title or "").strip()
    if not title:
        return {"error": "title is empty"}
    ev = {
        "id": str(uuid.uuid4()),
        "title": title,
        "date": (date or "").strip(),
        "time": (time or "").strip(),
        "note": (note or "").strip(),
    }
    _mem_events.append(ev)
    _persist(ev)
    return ev


def delete_event(event_id: str) -> dict:
    # 入れ物ごと置き換えると、保存先ごとに分けている意味が消える。
    # その場で削る。
    for _i in range(len(_mem_events) - 1, -1, -1):
        e = _mem_events[_i]
        if not (e.get("id") != event_id):
            del _mem_events[_i]
    c = config.get_supabase()
    if c:
        try:
            c.table("events").delete().eq("id", event_id).execute()
        except Exception:
            pass
    return {"ok": True}


def parse_and_add(text: str, today: str = "") -> dict:
    """自然言語の予定文を Gemini で {title, date, time} に解釈して登録する。
    Gemini 未設定時は、文面そのものを title としてそのまま登録する（縮退）。"""
    text = (text or "").strip()
    if not text:
        return {"error": "text is empty"}

    model = config.get_gemini_model()
    if model is None:
        # 縮退: 解釈せずそのまま登録
        return add_event(text)

    hint = f"今日の日付は {today} です。" if today else ""
    prompt = (
        "次の予定文を解釈し、JSONだけを ```json ... ``` の中に出力してください。"
        "日付は YYYY-MM-DD、時刻は HH:MM（24h）。不明な項目は空文字にしてください。" + hint + "\n"
        '{"title": "予定名", "date": "YYYY-MM-DD", "time": "HH:MM"}\n\n'
        f"予定文: {text}"
    )
    try:
        resp = model.generate_content(prompt)
        data = _extract_json(getattr(resp, "text", "") or "") or {}
    except Exception:
        data = {}

    title = (data.get("title") or text).strip()
    return add_event(title, data.get("date", ""), data.get("time", ""))
