# income.py — 副業オートメーション（Mission Control）のAPIロジック。
# Supabase の income_jobs を直接読み書きし、Geminiで各媒体メタデータを生成する（自己完結）。
import jsonout

import json
import re

import config

_INCOME_SYS = (
    "あなたは副業コンテンツの編集者です。与えられたテーマから、各プラットフォーム用メタデータを"
    "生成します。必ず次のJSONだけを ```json ... ``` のコードフェンス内に出力してください：\n"
    "{\n"
    '  "shutterstock": {"title_en": "英語タイトル", "tags": ["最大50個の英語タグ"]},\n'
    '  "youtube": {"title": "日本語タイトル", "description": "概要", "hashtags": ["#..."]},\n'
    '  "note": {"markdown": "H2/H3を含む日本語記事(Markdown)"}\n'
    "}\n"
)


def _extract_json(text: str):
    """AIの出力からJSONを取り出す。読めなければ None。

    中身は jsonout に1本化してある（同じ関数が10か所にあり、崩れ方への
    強さがばらついていたため）。
    """
    return jsonout.extract(text)


def list_jobs(status: str | None = None, limit: int = 50) -> list:
    c = config.get_supabase()
    if not c:
        return []
    try:
        q = c.table("income_jobs").select("*").order("created_at", desc=True).limit(limit)
        if status:
            q = q.eq("status", status)
        return q.execute().data or []
    except Exception:
        return []


def enqueue(theme: str) -> dict:
    """テーマから各媒体メタデータを生成し、income_jobs に pending で積む。生成物を返す。"""
    theme = (theme or "").strip()
    if not theme:
        return {"error": "theme is empty"}
    model = config.get_gemini_model()
    if model is None:
        return {"error": "GEMINI_API_KEY is not configured"}
    try:
        resp = model.generate_content(_INCOME_SYS + "\n\nテーマ: " + theme)
        payload = _extract_json(getattr(resp, "text", "") or "") or {"raw": getattr(resp, "text", "")}
    except Exception as e:
        return {"error": f"generation failed: {e}"}

    job = {
        "theme": theme,
        "status": "pending",
        "payload": payload,
        "log": "生成完了（承認待ち）",
        "dedupe_key": theme.lower(),
    }
    c = config.get_supabase()
    if c:
        try:
            res = c.table("income_jobs").insert(job).execute()
            if res.data:
                return res.data[0]
        except Exception as e:
            return {**job, "warning": f"DB保存に失敗（生成は成功）: {e}"}
    return job


def set_status(job_id: str, status: str) -> bool:
    c = config.get_supabase()
    if not c:
        return False
    try:
        c.table("income_jobs").update({"status": status}).eq("id", job_id).execute()
        return True
    except Exception:
        return False
