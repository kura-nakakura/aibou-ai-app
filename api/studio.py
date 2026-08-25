# studio.py — AI Studio（カスタムAIとワークフロー管理）絶対にcrashしない
# =====================================================================
# ユーザーが独自のAIペルソナやワークフローを作成・実行できるモジュール。
# Supabaseが設定されていればDBに永続化、なければインメモリで動作。
#
# Supabase テーブル studio_ais:
#   id         text  primary key
#   name       text  not null
#   persona    text  default ''
#   model      text  default 'gemini-2.5-flash'
#   rules      text  default ''
#   created_at timestamptz default now()
#
# Supabase テーブル studio_workflows:
#   id         text  primary key
#   name       text  not null
#   steps      jsonb default '[]'
#   created_at timestamptz default now()
#
# ステップの形（Dify のようにナレッジと分岐を持てる）:
#   {
#     "name":        表示名,
#     "prompt":      指示。{input} {original} {step1}… を差し込める,
#     "ai_id":       このステップを担当するカスタムAI（人格とルールを適用）,
#     "notebook_id": VAULTのノートブック。指定するとその資料だけを根拠にする,
#     "when":        条件（日本語）。満たさなければこのステップを飛ばす
#   }
# =====================================================================

import uuid
from datetime import datetime, timezone
from typing import Optional

import config
import memstore
import flow_engine

_mem_ais = memstore.TenantList()
_mem_workflows = memstore.TenantList()   # 実行の上限は flow_engine と共通（片方だけ変わってずれないように参照する）
MAX_STEPS = flow_engine.MAX_STEPS


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


# ── カスタムAI ───────────────────────────────────────────────────────

def list_ais() -> list:
    c = config.get_supabase()
    if c:
        try:
            return (c.table("studio_ais").select("*").order("created_at", desc=True)
                    .limit(200).execute().data) or []
        except Exception:
            pass
    return _mem_ais[:]


def create_ai(name: str, persona: str = "", model: str = "", rules: str = "") -> dict:
    name = (name or "").strip()
    if not name:
        return {"error": "name is empty"}
    ai = {
        "id": _uuid(),
        "name": name,
        "persona": persona or "",
        "model": model or "gemini-2.5-flash",
        "rules": rules or "",
        "created_at": _now_iso(),
    }
    c = config.get_supabase()
    if c:
        try:
            res = c.table("studio_ais").insert(ai).execute()
            return (res.data or [ai])[0]
        except Exception:
            pass
    _mem_ais.insert(0, ai)
    return ai


def delete_ai(ai_id: str) -> dict:
    c = config.get_supabase()
    if c:
        try:
            c.table("studio_ais").delete().eq("id", ai_id).execute()
            return {"ok": True}
        except Exception as e:
            return {"error": str(e)}
    # 入れ物ごと置き換えると、保存先ごとに分けている意味が消える。その場で削る。
    for _i in range(len(_mem_ais) - 1, -1, -1):
        a = _mem_ais[_i]
        if not (a.get("id") != ai_id):
            del _mem_ais[_i]
    return {"ok": True}


# ── ワークフロー ─────────────────────────────────────────────────────

def list_workflows() -> list:
    c = config.get_supabase()
    if c:
        try:
            return (c.table("studio_workflows").select("*").order("created_at", desc=True)
                    .limit(200).execute().data) or []
        except Exception:
            pass
    return _mem_workflows[:]


def create_workflow(name: str, steps: list) -> dict:
    name = (name or "").strip()
    if not name:
        return {"error": "name is empty"}
    wf = {
        "id": _uuid(),
        "name": name,
        "steps": steps or [],
        "created_at": _now_iso(),
    }
    c = config.get_supabase()
    if c:
        try:
            res = c.table("studio_workflows").insert(wf).execute()
            return (res.data or [wf])[0]
        except Exception:
            pass
    _mem_workflows.insert(0, wf)
    return wf


def delete_workflow(wf_id: str) -> dict:
    c = config.get_supabase()
    if c:
        try:
            c.table("studio_workflows").delete().eq("id", wf_id).execute()
            return {"ok": True}
        except Exception as e:
            return {"error": str(e)}
    # 入れ物ごと置き換えると、保存先ごとに分けている意味が消える。その場で削る。
    for _i in range(len(_mem_workflows) - 1, -1, -1):
        w = _mem_workflows[_i]
        if not (w.get("id") != wf_id):
            del _mem_workflows[_i]
    return {"ok": True}


def get_workflow(wf_id: str) -> Optional[dict]:
    """IDでワークフローを1件取得する（Supabase → メモリの順に探す）。"""
    c = config.get_supabase()
    if c:
        try:
            rows = c.table("studio_workflows").select("*").eq("id", wf_id).limit(1).execute().data
            if rows:
                return rows[0]
        except Exception:
            pass
    for w in _mem_workflows:
        if w.get("id") == wf_id:
            return w
    return None


def _find_ai(ai_id: str) -> Optional[dict]:
    if not ai_id:
        return None
    for a in list_ais():
        if a.get("id") == ai_id:
            return a
    return None


def run_workflow(wf_id: str, input_text: str = "") -> dict:
    """ワークフローを順番に実行する。

    実行そのものは flow_engine（BOARDの自動化と共通の1実装）に任せる。
    各ステップは担当のカスタムAI・根拠資料（VAULT）・実行条件を持てる。
    """
    wf = get_workflow(wf_id)
    if wf is None:
        return {"error": "workflow not found"}

    steps = wf.get("steps") or []
    if not steps:
        return {"error": "no steps defined"}

    run = flow_engine.run_steps(steps, input_text, resolve_ai=_find_ai)
    return {
        "workflow_id": wf_id,
        "workflow_name": wf.get("name", ""),
        **run,
    }
