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

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import config
import llm

_mem_ais: list = []
_mem_workflows: list = []

MAX_STEPS = 20
_KNOWLEDGE_CHARS = 12_000   # 1ステップに渡す資料の上限（プロンプトが膨らみすぎないように）


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
    global _mem_ais
    c = config.get_supabase()
    if c:
        try:
            c.table("studio_ais").delete().eq("id", ai_id).execute()
            return {"ok": True}
        except Exception as e:
            return {"error": str(e)}
    _mem_ais = [a for a in _mem_ais if a.get("id") != ai_id]
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
    global _mem_workflows
    c = config.get_supabase()
    if c:
        try:
            c.table("studio_workflows").delete().eq("id", wf_id).execute()
            return {"ok": True}
        except Exception as e:
            return {"error": str(e)}
    _mem_workflows = [w for w in _mem_workflows if w.get("id") != wf_id]
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


def _persona_prefix(ai: Optional[dict]) -> str:
    """カスタムAIの人格とルールを、そのステップの前置きにする。"""
    if not ai:
        return ""
    parts = []
    if (ai.get("persona") or "").strip():
        parts.append(f"あなたは「{ai.get('name')}」です。{ai['persona'].strip()}")
    else:
        parts.append(f"あなたは「{ai.get('name')}」です。")
    if (ai.get("rules") or "").strip():
        parts.append(f"【必ず守るルール】\n{ai['rules'].strip()}")
    return "\n".join(parts) + "\n\n"


def _knowledge_block(notebook_id: str) -> tuple:
    """VAULTのノートブックを資料として読み込む。(block, label, warning)。

    資料が使えないときも止めず、trace に理由を残して素の生成を続ける
    （途中で全体が失敗するほうが困るため）。
    """
    if not notebook_id:
        return "", "", ""
    try:
        import vault
        context, err = vault._load_context(notebook_id)
    except Exception as e:
        return "", "", f"資料を読み込めませんでした（{e}）"
    if err:
        return "", "", f"資料を読み込めませんでした（{err.get('error')}）"
    if not context:
        return "", "", "指定のノートブックに資料がありません"
    block = (
        "【資料】以下の資料に書かれていることだけを根拠にしてください。"
        "資料に無いことは推測せず「資料には記載がありません」と書いてください。\n"
        + context[:_KNOWLEDGE_CHARS] + "\n\n"
    )
    return block, notebook_id, ""


def _fill(template: str, original: str, current: str, outputs: list) -> str:
    """{input}（直前の出力）{original}（最初の入力）{stepN}（N番目の出力）を差し込む。"""
    out = (template or "").replace("{input}", current or "").replace("{original}", original or "")

    def sub(m):
        n = int(m.group(1))
        return outputs[n - 1] if 1 <= n <= len(outputs) else ""

    return re.sub(r"\{step(\d+)\}", sub, out)


def _condition_met(when: str, original: str, current: str) -> tuple:
    """分岐条件を判定する。(met: bool, reason: str)。

    判定できないときは実行する側に倒す（作った本人はそのステップを走らせたい
    はずで、黙って飛ばすほうが分かりにくい）。
    """
    when = (when or "").strip()
    if not when:
        return True, ""
    prompt = (
        "次の条件が満たされているかを判定してください。"
        "説明は書かず、YES か NO の1語だけで答えてください。\n\n"
        f"【条件】{when}\n\n"
        f"【最初の入力】\n{(original or '')[:2000]}\n\n"
        f"【直前の出力】\n{(current or '')[:4000]}\n\n"
        "【判定(YES/NO)】"
    )
    try:
        ans = (llm.generate_text(prompt, max_tokens=8) or "").strip().upper()
    except Exception as e:
        return True, f"条件を判定できなかったため実行しました（{e}）"
    if ans.startswith("NO") or ans.startswith("いいえ"):
        return False, f"条件「{when}」を満たさないためスキップ"
    if ans.startswith("YES") or ans.startswith("はい"):
        return True, ""
    return True, "条件の判定が曖昧だったため実行しました"


def run_workflow(wf_id: str, input_text: str = "") -> dict:
    """ワークフローを順番に実行する。

    各ステップは
      ・担当のカスタムAI（人格・ルール）を適用でき
      ・VAULTのノートブックを根拠資料にでき（RAG）
      ・条件を満たさなければ飛ばせる（分岐）
    最後にどのステップが動いた/飛んだかを trace として返す。
    """
    wf = get_workflow(wf_id)
    if wf is None:
        return {"error": "workflow not found"}

    steps = (wf.get("steps") or [])[:MAX_STEPS]
    if not steps:
        return {"error": "no steps defined"}

    results = []
    outputs: list = []            # {stepN} 用に全ステップの出力を積む
    original = input_text or ""
    current_input = original

    for i, step in enumerate(steps):
        name = step.get("name") or f"Step {i + 1}"
        template = step.get("prompt") or ""
        if not template:
            outputs.append("")
            results.append({"step": i + 1, "name": name, "output": "",
                            "skipped": True, "reason": "指示が空のためスキップ"})
            continue

        met, reason = _condition_met(step.get("when") or "", original, current_input)
        if not met:
            # 飛ばしたステップは出力を持たないが、後続の {stepN} の番号は保つ
            outputs.append("")
            results.append({"step": i + 1, "name": name, "output": "",
                            "skipped": True, "reason": reason})
            continue

        ai = _find_ai(step.get("ai_id") or "")
        knowledge, nb_id, warn = _knowledge_block(step.get("notebook_id") or "")
        prompt = _persona_prefix(ai) + knowledge + _fill(template, original, current_input, outputs)

        try:
            step_output = llm.generate_text(prompt, max_tokens=2200) or ""
        except Exception as e:
            step_output = f"[error: {e}]"

        outputs.append(step_output)
        row = {"step": i + 1, "name": name, "output": step_output, "skipped": False}
        if reason:
            row["reason"] = reason
        if ai:
            row["ai"] = ai.get("name")
        if nb_id:
            row["knowledge"] = nb_id
        if warn:
            row["warning"] = warn
        results.append(row)
        current_input = step_output      # 次ステップの {input}

    ran = [r for r in results if not r.get("skipped")]
    return {
        "workflow_id": wf_id,
        "workflow_name": wf.get("name", ""),
        "results": results,
        "final_output": ran[-1]["output"] if ran else "",
        "ran": len(ran),
        "skipped": len(results) - len(ran),
    }
