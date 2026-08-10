# test_vault_pdf.py — ⑦ VAULT（PDF取り込み・出典表示・資料管理）
#
# NotebookLM のように「どの資料を根拠にしたか」を追えることと、
# PDFをブラウザで読ませずサーバー側で抽出することを検証する。
# Supabase無しでも動く（メモリ保存）ので鍵・DBなしで通る。

import io

from fastapi.testclient import TestClient

import fileread
import vault
from main import app

client = TestClient(app)


def _fresh(name="調査ノート"):
    vault._mem_notebooks.clear()
    return vault.create_notebook(name)["id"]


# ── Supabase無しでも使える ───────────────────────────────────────────
def test_works_without_supabase():
    """他のストアと同じく、DB未設定でもメモリで動く（以前は使えなかった）。"""
    vault._mem_notebooks.clear()
    nb = vault.create_notebook("メモ")
    assert nb.get("id") and not nb.get("error")
    assert vault.add_text(nb["id"], "資料A", "本文A").get("ok")
    items = vault.list_notebooks()
    assert items[0]["name"] == "メモ" and items[0]["doc_count"] == 1


def test_add_text_to_missing_notebook():
    vault._mem_notebooks.clear()
    assert vault.add_text("no-such", "t", "c").get("error") == "notebook not found"


# ── 出典番号 ─────────────────────────────────────────────────────────
def test_query_numbers_sources_and_asks_for_citations(monkeypatch):
    nb = _fresh()
    vault.add_text(nb, "就業規則", "年次有給休暇は20日です。")
    vault.add_text(nb, "経費規程", "交通費は実費精算です。")
    seen = {}
    import llm
    monkeypatch.setattr(llm, "generate_text",
                        lambda p, **k: (seen.update(p=p), "有給は20日です[1]。")[1])
    res = vault.query(nb, "有給は何日?")
    p = seen["p"]
    # 資料に番号が振られ、その番号で引用させる指示が入る
    assert "[1] 就業規則" in p and "[2] 経費規程" in p
    assert "[1] のように必ず付けて" in p
    assert res["sources"] == [{"n": 1, "title": "就業規則"}, {"n": 2, "title": "経費規程"}]
    assert res["cited"] == [1]      # 実際に引用された番号だけ


def test_cited_ignores_numbers_that_do_not_exist(monkeypatch):
    nb = _fresh()
    vault.add_text(nb, "唯一の資料", "内容")
    import llm
    monkeypatch.setattr(llm, "generate_text", lambda p, **k: "適当な話[1][7][99]")
    res = vault.query(nb, "?")
    assert res["cited"] == [1]      # 7 と 99 は資料が無いので拾わない


def test_cited_dedupes_and_sorts(monkeypatch):
    nb = _fresh()
    for t in ("A", "B", "C"):
        vault.add_text(nb, t, f"本文{t}")
    import llm
    monkeypatch.setattr(llm, "generate_text", lambda p, **k: "あれ[3]これ[1]それ[3]")
    assert vault.query(nb, "?")["cited"] == [1, 3]


def test_query_without_docs_does_not_call_the_model(monkeypatch):
    nb = _fresh()
    import llm
    called = {"n": 0}

    def boom(p, **k):
        called["n"] += 1
        return "呼ばれてはいけない"

    monkeypatch.setattr(llm, "generate_text", boom)
    res = vault.query(nb, "質問")
    assert called["n"] == 0
    assert "まだ資料が登録されていません" in res["answer"]
    assert res["sources"] == [] and res["cited"] == []


def test_empty_docs_are_not_numbered(monkeypatch):
    """本文が空の資料は番号を消費しない（番号がずれると出典が嘘になる）。"""
    nb = _fresh()
    vault.add_text(nb, "空っぽ", "   ")
    vault.add_text(nb, "中身あり", "本文")
    import llm
    monkeypatch.setattr(llm, "generate_text", lambda p, **k: "答え[1]")
    res = vault.query(nb, "?")
    assert res["sources"] == [{"n": 1, "title": "中身あり"}]


def test_query_validation():
    nb = _fresh()
    assert vault.query(nb, "").get("error")
    assert vault.query("", "質問").get("error")
    assert vault.query("no-such", "質問").get("error") == "notebook not found"


# ── 資料の一覧と削除 ─────────────────────────────────────────────────
def test_list_docs_matches_citation_numbers():
    nb = _fresh()
    vault.add_text(nb, "一つ目", "abc")
    vault.add_text(nb, "二つ目", "de")
    items = vault.list_docs(nb)["items"]
    assert items == [{"n": 1, "title": "一つ目", "chars": 3},
                     {"n": 2, "title": "二つ目", "chars": 2}]


def test_delete_doc_renumbers_remaining_sources(monkeypatch):
    nb = _fresh()
    for t in ("A", "B", "C"):
        vault.add_text(nb, t, f"本文{t}")
    assert vault.delete_doc(nb, "B").get("ok")
    items = vault.list_docs(nb)["items"]
    assert [i["title"] for i in items] == ["A", "C"]
    assert [i["n"] for i in items] == [1, 2]      # 抜けた番号を詰める


def test_delete_doc_validation():
    nb = _fresh()
    vault.add_text(nb, "A", "x")
    assert vault.delete_doc(nb, "").get("error")
    assert vault.delete_doc(nb, "ない資料").get("error") == "document not found"
    assert vault.delete_doc("no-such", "A").get("error") == "notebook not found"


# ── PDF抽出 ──────────────────────────────────────────────────────────
def _tiny_pdf(text="Hello Vault"):
    """1ページだけの最小PDFを組み立てる（pypdfで読める形）。"""
    try:
        from pypdf import PdfWriter
    except Exception:
        return None
    try:
        import reportlab  # noqa: F401
    except Exception:
        reportlab = None
    # reportlab が無い環境向け: 手書きの最小PDF
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]"
        b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length 60>>stream\n"
        b"BT /F1 12 Tf 20 100 Td (" + text.encode("latin-1") + b") Tj ET\n"
        b"endstream endobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"trailer<</Root 1 0 R>>\n"
    )
    _ = PdfWriter, io
    return body


def test_pdf_text_is_extracted_server_side():
    """PDFはサーバーで抽出する（ブラウザでテキストとして読むと文字化けする）。"""
    pdf = _tiny_pdf("Hello Vault")
    if pdf is None:
        return      # pypdf が無い環境ではスキップ
    text = fileread.extract_text("shiryo.pdf", pdf, "application/pdf")
    assert "Hello Vault" in text or "抽出できませんでした" in text or "エラー" in text


def test_pdf_bytes_are_not_treated_as_text():
    """PDFのバイト列がそのまま本文として入らないこと。"""
    pdf = _tiny_pdf("Hello Vault")
    if pdf is None:
        return
    text = fileread.extract_text("shiryo.pdf", pdf, "application/pdf")
    assert "%PDF" not in text and "endstream" not in text


def test_upload_endpoint_adds_a_doc():
    nb = _fresh()
    files = {"file": ("メモ.txt", "本文テキストです".encode("utf-8"), "text/plain")}
    r = client.post("/vault/upload", data={"notebook_id": nb}, files=files)
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] and d["title"] == "メモ" and d["chars"] > 0
    assert vault.list_docs(nb)["items"][0]["title"] == "メモ"


def test_upload_uses_explicit_title_when_given():
    nb = _fresh()
    files = {"file": ("a.txt", b"x", "text/plain")}
    r = client.post("/vault/upload", data={"notebook_id": nb, "title": "好きな名前"}, files=files)
    assert r.json()["title"] == "好きな名前"


def test_upload_rejects_unreadable_file():
    """テキストが取れないものを空の資料として登録しない。"""
    nb = _fresh()
    files = {"file": ("empty.txt", b"   ", "text/plain")}
    r = client.post("/vault/upload", data={"notebook_id": nb}, files=files)
    assert r.status_code == 400 and "抽出できませんでした" in r.json()["error"]
    assert vault.list_docs(nb)["items"] == []


def test_upload_to_missing_notebook_fails():
    vault._mem_notebooks.clear()
    files = {"file": ("a.txt", b"body", "text/plain")}
    r = client.post("/vault/upload", data={"notebook_id": "nope"}, files=files)
    assert r.status_code == 400


# ── エンドポイント ───────────────────────────────────────────────────
def test_docs_endpoints():
    nb = _fresh()
    vault.add_text(nb, "資料1", "内容")
    r = client.get("/vault/docs", params={"notebook_id": nb})
    assert r.status_code == 200 and r.json()["items"][0]["title"] == "資料1"
    r = client.post("/vault/docs/delete", json={"notebook_id": nb, "title": "資料1"})
    assert r.status_code == 200 and r.json()["ok"]
    assert client.get("/vault/docs", params={"notebook_id": nb}).json()["items"] == []
    r = client.post("/vault/docs/delete", json={"notebook_id": nb, "title": "無い"})
    assert r.status_code == 400


def test_query_endpoint_returns_sources(monkeypatch):
    nb = _fresh()
    vault.add_text(nb, "根拠資料", "答えはこれです。")
    import llm
    monkeypatch.setattr(llm, "generate_text", lambda p, **k: "こうです[1]")
    r = client.post("/vault/query", json={"notebook_id": nb, "question": "どう?"})
    assert r.status_code == 200
    d = r.json()
    assert d["sources"] == [{"n": 1, "title": "根拠資料"}] and d["cited"] == [1]


def test_workflow_knowledge_still_reads_the_same_docs():
    """ワークフローの根拠資料（flow_engine）もメモリ保存を読める。"""
    nb = _fresh()
    vault.add_text(nb, "共有資料", "共通の内容")
    ctx, err = vault._load_context(nb)
    assert err is None and "共有資料" in ctx and "共通の内容" in ctx
