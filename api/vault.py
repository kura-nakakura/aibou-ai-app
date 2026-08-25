# vault.py — Document Vault（資料ノートブック）のRAGロジック（絶対にcrashしない）
# =====================================================================
# ユーザーがアップロードしたテキスト資料を「ノートブック」単位で蓄え、
# その資料”だけ”を根拠にGeminiへ質問するシンプルなRAG（検索拡張生成）。
#
# Streamlit / core.py には一切依存しない自己完結モジュール。設定（Supabase /
# Gemini）が欠けていても例外を出さず、空リスト / エラーdict で優雅に縮退する。
#
# Supabase テーブル vault_notebooks（supabase_schema.sql 参照）:
#   id    uuid    primary key default gen_random_uuid()
#   name  text    not null
#   docs  jsonb   default '{}'::jsonb   … {タイトル: 本文} のマップ
#   chat  jsonb   default '[]'::jsonb   … 質問応答の履歴（将来拡張用）
#   created_at timestamptz default now()
# =====================================================================

import re
import uuid

import config
import memstore

# Supabase が無いときの保存先。他のストアと同じく、設定が無くても使える。
_mem_notebooks = memstore.TenantList()
def _mem_find(notebook_id: str):
    for nb in _mem_notebooks:
        if nb.get("id") == notebook_id:
            return nb
    return None


def _numbered_sources(docs: dict) -> list:
    """docs（{タイトル: 本文}）を 1 から番号付けした一覧にする。

    出典表示（[1][2]）の番号はここで決め、プロンプトと戻り値で必ず一致させる。
    """
    out = []
    for title, content in (docs or {}).items():
        body = content if isinstance(content, str) else str(content or "")
        if body.strip():
            out.append({"n": len(out) + 1, "title": str(title), "body": body.strip()})
    return out


def _cited_numbers(answer: str, total: int) -> list:
    """回答本文から [1] [2] のような出典番号を拾う（存在する番号だけ）。"""
    found = []
    for m in re.finditer(r"\[(\d{1,2})\]", answer or ""):
        n = int(m.group(1))
        if 1 <= n <= total and n not in found:
            found.append(n)
    return sorted(found)


def list_notebooks() -> list:
    """ノートブック一覧を [{id, name, doc_count}] で返す。
    新しい順（created_at降順）→ 同着は name 昇順。
    Supabaseが無ければメモリ上のものを返す（絶対にraiseしない）。"""
    c = config.get_supabase()
    if not c:
        return [{"id": nb["id"], "name": nb["name"], "doc_count": len(nb.get("docs") or {})}
                for nb in _mem_notebooks]
    try:
        rows = (c.table("vault_notebooks")
                .select("id,name,docs,created_at")
                .order("created_at", desc=True)
                .order("name", desc=False)
                .limit(1000)
                .execute().data) or []
    except Exception:
        return []

    result = []
    for r in rows:
        docs = r.get("docs") or {}
        # docs は jsonb のマップ想定。万一マップでなければ件数0扱い。
        doc_count = len(docs) if isinstance(docs, dict) else 0
        result.append({
            "id": r.get("id"),
            "name": r.get("name") or "",
            "doc_count": doc_count,
        })
    return result


def create_notebook(name: str) -> dict:
    """ノートブックを1件作成し {id, name} を返す。
    名前が空、またはSupabase未設定/失敗時は error dict を返す（絶対にraiseしない）。"""
    name = (name or "").strip()
    if not name:
        return {"error": "name is empty"}
    c = config.get_supabase()
    if not c:
        nb = {"id": str(uuid.uuid4()), "name": name, "docs": {}, "chat": []}
        _mem_notebooks.insert(0, nb)
        return {"id": nb["id"], "name": name}
    try:
        res = (c.table("vault_notebooks")
               .insert({"name": name, "docs": {}, "chat": []})
               .execute())
        row = (res.data or [{}])[0]
        return {"id": row.get("id"), "name": row.get("name") or name}
    except Exception as e:
        return {"error": f"create failed: {e}"}


def add_text(notebook_id: str, title: str, content: str) -> dict:
    """対象ノートブックの docs(jsonb) に {title: content} をマージしてupdateする。
    成功で {ok: True}。引数不足・未設定・失敗時は error dict（絶対にraiseしない）。"""
    notebook_id = (notebook_id or "").strip()
    title = (title or "").strip()
    content = content or ""
    if not notebook_id:
        return {"error": "notebook_id is empty"}
    if not title:
        return {"error": "title is empty"}
    c = config.get_supabase()
    if not c:
        nb = _mem_find(notebook_id)
        if nb is None:
            return {"error": "notebook not found"}
        nb.setdefault("docs", {})[title] = content
        return {"ok": True}
    try:
        # 既存 docs を読み込み、新しい資料をマージ（同名タイトルは上書き）。
        rows = (c.table("vault_notebooks")
                .select("docs")
                .eq("id", notebook_id)
                .limit(1)
                .execute().data) or []
        if not rows:
            return {"error": "notebook not found"}
        docs = rows[0].get("docs") or {}
        if not isinstance(docs, dict):
            docs = {}
        docs[title] = content
        c.table("vault_notebooks").update({"docs": docs}).eq("id", notebook_id).execute()
        return {"ok": True}
    except Exception as e:
        return {"error": f"add_text failed: {e}"}


def _load_docs(notebook_id: str):
    """ノートブックの docs マップを取得する。(docs, error_dict)。"""
    notebook_id = (notebook_id or "").strip()
    if not notebook_id:
        return None, {"error": "notebook_id is empty"}
    c = config.get_supabase()
    if not c:
        nb = _mem_find(notebook_id)
        if nb is None:
            return None, {"error": "notebook not found"}
        docs = nb.get("docs") or {}
        return (docs if isinstance(docs, dict) else {}), None
    try:
        rows = (c.table("vault_notebooks").select("docs")
                .eq("id", notebook_id).limit(1).execute().data) or []
    except Exception as e:
        return None, {"error": f"load failed: {e}"}
    if not rows:
        return None, {"error": "notebook not found"}
    docs = rows[0].get("docs") or {}
    return (docs if isinstance(docs, dict) else {}), None


def list_docs(notebook_id: str) -> dict:
    """資料の一覧を [{n, title, chars}] で返す（本文は返さない）。

    番号は query() の出典番号と同じ規則で振るので、UIで突き合わせられる。
    """
    docs, err = _load_docs(notebook_id)
    if err:
        return err
    return {"items": [{"n": s["n"], "title": s["title"], "chars": len(s["body"])}
                      for s in _numbered_sources(docs)]}


def delete_doc(notebook_id: str, title: str) -> dict:
    """資料を1件消す（間違って入れた資料が根拠に混ざり続けないように）。"""
    title = (title or "").strip()
    if not title:
        return {"error": "title is empty"}
    docs, err = _load_docs(notebook_id)
    if err:
        return err
    if title not in docs:
        return {"error": "document not found"}
    docs = {k: v for k, v in docs.items() if k != title}
    c = config.get_supabase()
    if not c:
        nb = _mem_find(notebook_id)
        if nb is None:
            return {"error": "notebook not found"}
        nb["docs"] = docs
        return {"ok": True}
    try:
        c.table("vault_notebooks").update({"docs": docs}).eq("id", notebook_id).execute()
        return {"ok": True}
    except Exception as e:
        return {"error": f"delete failed: {e}"}


def query(notebook_id: str, question: str) -> dict:
    """ノートブックの資料“だけ”を根拠に質問へ答える。出典番号つきで返す。

    {answer, sources: [{n, title}], cited: [n...]} を返す。
    NotebookLM のように「どの資料を根拠にしたか」を追えるようにするのが要点で、
    番号は _numbered_sources() で一意に決め、プロンプトと戻り値で必ず一致させる。
    """
    question = (question or "").strip()
    if not question:
        return {"error": "question is empty"}

    docs, err = _load_docs(notebook_id)
    if err:
        return err

    sources = _numbered_sources(docs)
    # 資料が無ければAIを呼ばず案内文を返す
    if not sources:
        return {"answer": "このノートブックにはまだ資料が登録されていません。先に資料を追加してください。",
                "sources": [], "cited": []}

    # 資料が多いと全文は入り切らない。質問に関係する段落だけを選んで渡す。
    # 出典番号は資料単位で決めてあるので、断片には元の番号を付け直す。
    num_of = {s["title"]: s["n"] for s in sources}
    try:
        import retrieval
        picked = retrieval.select({s["title"]: s["body"] for s in sources}, question)
        parts = []
        for line in picked["context"].split("\n\n"):
            if not line.startswith("## "):
                parts.append(line)
                continue
            head, _, rest = line.partition("\n")
            title = head[3:].strip()
            parts.append(f"[{num_of.get(title, 0)}] {title}\n{rest}")
        context = "\n\n".join(parts) if parts else ""
        truncated = picked["total_chars"] > len(picked["context"])
    except Exception:
        # 検索側で何かあっても答えられるように、従来どおり先頭から詰める
        context = "\n\n".join(f"[{s['n']}] {s['title']}\n{s['body']}" for s in sources)
        truncated = False

    prompt = (
        "あなたは資料に基づいて回答するアシスタントです。"
        "以下の【資料】に書かれている情報”だけ”を根拠に、日本語で簡潔かつ正確に回答してください。\n"
        "・根拠にした資料の番号を、その記述の直後に [1] のように必ず付けてください"
        "（複数なら [1][3] と並べる）\n"
        "・資料に答えが書かれていない場合は推測せず「資料には記載がありません」と答えてください\n"
        "・存在しない番号は書かないでください\n\n"
        f"【資料】\n{context}\n\n"
        f"【質問】\n{question}\n\n"
        "【回答】\n"
    )
    try:
        import llm
        answer = llm.generate_text(prompt, max_tokens=2200) or ""
    except Exception as e:
        return {"error": f"generation failed: {e}"}

    return {
        "answer": answer,
        "sources": [{"n": s["n"], "title": s["title"]} for s in sources],
        "cited": _cited_numbers(answer, len(sources)),
        # 資料の一部だけを見て答えたことを隠さない（全部読んだと誤解させない）
        "partial": bool(truncated),
    }


def _load_context(notebook_id: str):
    """ノートブックの全資料を「## タイトル\\n本文」で連結して返す。
    (context, error_dict) のタプル。error_dict が None なら成功。
    ワークフローの根拠資料（flow_engine）もここを通る。"""
    docs, err = _load_docs(notebook_id)
    if err:
        return None, err
    parts = [f"## {s['title']}\n{s['body']}" for s in _numbered_sources(docs)]
    return "\n\n".join(parts).strip(), None


def generate_doc(notebook_id: str, instruction: str) -> dict:
    """ノートブックの資料を根拠に、指示に沿った文書(Markdown)を作成する。"""
    instruction = (instruction or "").strip() or "資料を分かりやすくまとめた要約資料を作成してください。"
    context, err = _load_context(notebook_id)
    if err:
        return err
    if not context:
        return {"error": "このノートブックにはまだ資料が登録されていません。"}
    model = config.get_gemini_model()
    if model is None:
        return {"error": "GEMINI_API_KEY is not configured"}
    prompt = (
        "あなたは資料を整理して文書を作成する編集者です。"
        "以下の【資料】の情報だけを根拠に、【指示】に沿った文書を日本語の Markdown で作成してください。"
        "見出し(H2/H3)・箇条書き・表を適切に使い、読みやすく構成してください。\n\n"
        f"【資料】\n{context}\n\n【指示】\n{instruction}\n\n【文書(Markdown)】\n"
    )
    try:
        resp = model.generate_content(prompt)
        return {"markdown": getattr(resp, "text", "") or ""}
    except Exception as e:
        return {"error": f"generation failed: {e}"}


def generate_diagram(notebook_id: str, kind: str = "tree") -> dict:
    """資料から Mermaid 図（ロジックツリー等）を生成する。{mermaid, kind} を返す。"""
    kind = (kind or "tree").strip().lower()
    diagram_hint = {
        "tree": "ロジックツリー（mindmap または graph TD の木構造）",
        "flow": "フローチャート（flowchart TD）",
        "mindmap": "マインドマップ（mindmap）",
        "sequence": "シーケンス図（sequenceDiagram）",
    }.get(kind, "ロジックツリー（graph TD）")

    context, err = _load_context(notebook_id)
    if err:
        return err
    if not context:
        return {"error": "このノートブックにはまだ資料が登録されていません。"}
    model = config.get_gemini_model()
    if model is None:
        return {"error": "GEMINI_API_KEY is not configured"}
    prompt = (
        "あなたは情報を構造化して図解する専門家です。"
        f"以下の【資料】の要点を、{diagram_hint} として Mermaid 記法で表現してください。"
        "出力は Mermaid のコードだけにし、説明文やコードフェンスは付けないでください。"
        "日本語ノードラベルは半角の () [] {} を含めないでください（図が壊れます）。\n\n"
        f"【資料】\n{context}\n\n【Mermaid】\n"
    )
    try:
        resp = model.generate_content(prompt)
        code = (getattr(resp, "text", "") or "").strip()
        # 念のためコードフェンスを除去
        code = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", code).strip()
        return {"mermaid": code, "kind": kind}
    except Exception as e:
        return {"error": f"generation failed: {e}"}
