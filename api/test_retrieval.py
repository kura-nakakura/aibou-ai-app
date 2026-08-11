# test_retrieval.py — 資料が多くても関連箇所を取り出せるかの検証
#
# 直したかった問題：これまでは全文を先頭から12,000字で切っていたので、
# 後ろに答えがある資料では永久に届かなかった。

import retrieval


def _long(marker: str, pad_paras: int = 200) -> str:
    """答え(marker)を末尾に置いた、上限を超える長さの資料を作る。"""
    filler = "\n\n".join(
        f"これは関係のない段落です。番号は{i}。社内の一般的な説明が続きます。" * 6
        for i in range(pad_paras)
    )
    return filler + "\n\n" + marker


# ── チャンク分割 ─────────────────────────────────────────────────────
def test_splits_on_blank_lines():
    ch = retrieval.split_chunks("規程", "第一段落です。\n\n第二段落です。\n\n第三段落です。")
    assert [c["text"] for c in ch] == ["第一段落です。", "第二段落です。", "第三段落です。"]
    assert all(c["title"] == "規程" for c in ch)


def test_long_paragraph_is_cut_with_overlap():
    body = "あ" * (retrieval.CHUNK_CHARS * 2 + 100)
    ch = retrieval.split_chunks("長文", body)
    assert len(ch) >= 3
    assert all(len(c["text"]) <= retrieval.CHUNK_CHARS for c in ch)
    # 重ねているので、単純合計は元より長くなる（文脈が切れないため）
    assert sum(len(c["text"]) for c in ch) > len(body)


def test_empty_docs_are_skipped():
    assert retrieval.split_chunks("t", "") == []
    assert retrieval.split_chunks("t", "   \n\n  ") == []
    assert retrieval.build_chunks({}) == []
    assert retrieval.build_chunks({"a": "", "b": "中身"})[0]["title"] == "b"


# ── トークン化（日本語の部分一致） ───────────────────────────────────
def test_japanese_partial_match_via_bigrams():
    # 「有給休暇」の一部が「年次有給休暇」にも含まれる
    q = set(retrieval.tokens("有給休暇"))
    d = set(retrieval.tokens("年次有給休暇は20日です"))
    assert q & d


def test_alphanumeric_words_are_kept_whole():
    assert "gemini" in retrieval.tokens("Gemini APIキー")
    assert "2026" in retrieval.tokens("2026年度")


# ── 並べ替え ─────────────────────────────────────────────────────────
def test_relevant_chunk_ranks_first():
    docs = {"規程": "交通費は実費精算です。\n\n年次有給休暇は20日です。\n\n服装は自由です。"}
    ranked = retrieval.rank(retrieval.build_chunks(docs), "有給は何日？")
    assert "有給休暇は20日" in ranked[0][1]["text"]
    assert ranked[0][0] > 0


def test_empty_question_keeps_original_order():
    docs = {"d": "一つ目。\n\n二つ目。"}
    ranked = retrieval.rank(retrieval.build_chunks(docs), "")
    assert [c["text"] for _s, c in ranked] == ["一つ目。", "二つ目。"]


def test_rank_handles_no_chunks():
    assert retrieval.rank([], "質問") == []


# ── 選択（ここが本題） ───────────────────────────────────────────────
def test_answer_at_the_end_of_a_huge_doc_is_reached():
    """全文投入だと切り捨てられていた「末尾の答え」に届く。"""
    docs = {"就業規則": _long("年次有給休暇は20日付与されます。")}
    assert len(docs["就業規則"]) > retrieval.DEFAULT_BUDGET   # 上限を超える資料
    res = retrieval.select(docs, "有給は何日もらえますか？")
    assert res["matched"] is True
    assert "20日付与されます" in res["context"]
    assert len(res["context"]) <= retrieval.DEFAULT_BUDGET + 200


def test_selection_respects_the_budget():
    docs = {f"資料{i}": _long(f"目印{i}", pad_paras=20) for i in range(6)}
    res = retrieval.select(docs, "目印3", budget=3000)
    assert len(res["context"]) <= 3200
    assert "目印3" in res["context"]


def test_reports_what_was_used():
    docs = {"A": "りんごの説明。", "B": "みかんの説明。"}
    res = retrieval.select(docs, "みかん")
    assert res["chunks"] == 2
    assert res["total_chars"] > 0
    titles = [u["title"] for u in res["used"]]
    assert "B" in titles


def test_no_match_still_returns_something():
    """一致が無くても空にしない（先頭から詰める）。ただし matched=False で伝える。"""
    docs = {"A": "りんごの説明です。\n\nみかんの説明です。"}
    res = retrieval.select(docs, "宇宙船の設計図")
    assert res["matched"] is False
    assert res["context"]           # 空にはしない


def test_empty_notebook():
    res = retrieval.select({}, "何か")
    assert res["context"] == "" and res["chunks"] == 0 and res["matched"] is False


def test_context_keeps_document_order_not_score_order():
    """読みやすさのため、選んだ断片は資料内の並びに戻す。"""
    docs = {"d": "最初の段落。目印A。\n\n真ん中の段落。\n\n最後の段落。目印B。"}
    res = retrieval.select(docs, "目印B 目印A")
    a = res["context"].index("目印A")
    b = res["context"].index("目印B")
    assert a < b                    # スコア順（Bが先）ではなく元の順


def test_context_includes_source_titles():
    res = retrieval.select({"就業規則": "有給は20日。"}, "有給")
    assert "## 就業規則" in res["context"]


def test_very_large_corpus_stays_within_budget():
    docs = {f"doc{i}": _long(f"marker{i}", pad_paras=100) for i in range(20)}
    res = retrieval.select(docs, "marker7")
    assert res["total_chars"] > 200_000        # 元は巨大
    assert len(res["context"]) <= retrieval.DEFAULT_BUDGET + 500
    assert "marker7" in res["context"]
