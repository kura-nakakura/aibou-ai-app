# retrieval.py — 資料が多くても関連箇所だけを取り出す（RAGの検索部分）
# =====================================================================
# これまでは「ノートブックの全文をそのままプロンプトへ（上限12,000字）」だった。
# 資料が増えると先頭12,000字で切られ、後ろに答えがあっても永久に届かない。
#
# ここでは資料を段落単位に切り、質問との関連度で並べ替えて上位だけを渡す。
# 日本語は単語の区切りが無いので、形態素解析なし・追加依存なしで動くよう
# 「文字bi-gram + BM25」で照合する（"有給休暇" が "年次有給休暇" にも当たる）。
#
# 埋め込み（ベクトル検索）ではないので、言い換えだけの一致には弱い。
# そのぶん鍵もDBも不要で、オフラインでも同じ結果になる（再現性がある）。
# =====================================================================

import math
import re
from collections import Counter

CHUNK_CHARS = 700          # 1チャンクの目安（段落が長い場合はここで割る）
CHUNK_OVERLAP = 80         # 文脈が切れないように少し重ねる
DEFAULT_BUDGET = 12_000    # プロンプトに載せる合計文字数の上限

# BM25 の標準的な既定値
_K1 = 1.5
_B = 0.75

# 助詞など、当たっても情報量が無い2文字（bi-gramなので短い機能語が混ざりやすい）
_STOP = {"です", "ます", "した", "して", "する", "ある", "いる", "この", "その",
         "こと", "もの", "ため", "から", "まで", "より", "ので", "など", "ては"}


def _norm(text: str) -> str:
    """全角空白や連続改行を潰して、比較しやすい形にする。"""
    t = (text or "").replace("　", " ")
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


def tokens(text: str) -> list:
    """照合用のトークン列。

    英数字は単語として、日本語は文字bi-gramとして扱う。
    分かち書きが無い日本語で「部分一致」を効かせるための実装。
    """
    t = _norm(text).lower()
    out = []
    # 英数字・記号混じりの語はそのまま単語として拾う
    for w in re.findall(r"[a-z0-9][a-z0-9_.+-]*", t):
        if len(w) >= 2:
            out.append(w)
    # 日本語（かな・漢字）は連続部分を取り出して bi-gram にする
    for run in re.findall(r"[぀-ヿ一-鿿ｦ-ﾟ]+", t):
        if len(run) == 1:
            out.append(run)
            continue
        for i in range(len(run) - 1):
            g = run[i:i + 2]
            if g not in _STOP:
                out.append(g)
    return out


def split_chunks(title: str, body: str) -> list:
    """資料を段落単位に切る。長い段落は CHUNK_CHARS で分割し、少し重ねる。

    返り値: [{"title", "text"}]
    """
    body = _norm(body)
    if not body:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    chunks = []
    for para in paras or [body]:
        if len(para) <= CHUNK_CHARS:
            chunks.append(para)
            continue
        start = 0
        while start < len(para):
            end = min(len(para), start + CHUNK_CHARS)
            chunks.append(para[start:end])
            if end >= len(para):
                break
            start = end - CHUNK_OVERLAP
    return [{"title": title, "text": c} for c in chunks if c.strip()]


def build_chunks(docs: dict) -> list:
    """docs（{タイトル: 本文}）を全部チャンクに分解する。"""
    out = []
    for title, content in (docs or {}).items():
        body = content if isinstance(content, str) else str(content or "")
        out.extend(split_chunks(str(title), body))
    return out


def rank(chunks: list, question: str) -> list:
    """質問との関連度（BM25）で並べ替えて [(score, chunk)] を返す。

    質問が空、または一致が無い場合はスコア0で元の順序を保つ
    （「関連が無いから何も渡さない」よりは、先頭から渡すほうが実用的）。
    """
    if not chunks:
        return []
    q = [t for t in tokens(question) if t]
    docs = [tokens(c["text"]) for c in chunks]
    if not q:
        return [(0.0, c) for c in chunks]

    n = len(docs)
    avg = sum(len(d) for d in docs) / n if n else 0.0
    # 各語が何チャンクに現れるか（IDF用）
    df = Counter()
    for d in docs:
        for t in set(d):
            if t in q:
                df[t] += 1

    scored = []
    for i, d in enumerate(docs):
        tf = Counter(d)
        dl = len(d) or 1
        s = 0.0
        for t in set(q):
            f = tf.get(t, 0)
            if not f:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * (f * (_K1 + 1)) / (f + _K1 * (1 - _B + _B * dl / (avg or 1)))
        scored.append((s, i))
    # スコア降順、同点は元の順序（資料の並びを尊重して安定させる）
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [(s, chunks[i]) for s, i in scored]


def select(docs: dict, question: str, budget: int = DEFAULT_BUDGET) -> dict:
    """質問に関係する部分だけを budget 文字ぶん選ぶ。

    返り値 {"context": str, "used": [{"title","chars"}], "chunks": int,
            "total_chars": int, "matched": bool}
      context … そのままプロンプトに載せられる本文（資料名つき）
      matched … 1つでも関連が見つかったか（Falseなら先頭から詰めただけ）
    """
    chunks = build_chunks(docs)
    total = sum(len(c["text"]) for c in chunks)
    if not chunks:
        return {"context": "", "used": [], "chunks": 0, "total_chars": 0, "matched": False}

    ranked = rank(chunks, question)
    matched = any(s > 0 for s, _ in ranked)

    picked, used, size = [], [], 0
    for score, c in ranked:
        piece = f"## {c['title']}\n{c['text']}"
        if size + len(piece) > budget and picked:
            break
        picked.append((score, c, piece))
        used.append({"title": c["title"], "chars": len(c["text"])})
        size += len(piece)

    # 選んだ順（関連度順）だと読みにくいので、資料内の元の並びに戻す
    order = {id(c): i for i, c in enumerate(chunks)}
    picked.sort(key=lambda x: order.get(id(x[1]), 0))
    return {
        "context": "\n\n".join(p for _s, _c, p in picked),
        "used": used,
        "chunks": len(chunks),
        "total_chars": total,
        "matched": matched,
    }
