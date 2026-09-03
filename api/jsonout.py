"""
api/jsonout.py — AIの出力からJSONを取り出す（1本にまとめたもの）。

なぜ1本にしたか
---------------
同じ役目の関数が10のモジュールにあり、中身は7種類に分かれていた。
実際に崩れたJSONを食わせて測ったところ、末尾カンマ付き（AIがよく出す）で
6モジュールが失敗し、3モジュールだけが復帰できた。

つまり「予定を登録して」は失敗しやすく「スライドを作って」は成功しやすい、
という差が、機能の違いではなく実装の写し間違いから出ていた。
利用者にはただの気まぐれに見える。1本に寄せて、どのモードでも同じだけ粘る。

方針
----
・こちらから直せる崩れ方だけを直す（勝手に中身を作らない）
・読み取れなければ None を返す。呼び出し側が「読めませんでした」と言えるように。
"""

import json
import re
from typing import Any, Optional

# ```json … ``` / ``` … ``` のフェンス
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
# 閉じ括弧の直前のカンマ（AIがよく置いていく）
_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _balanced(text: str, open_ch: str, close_ch: str) -> Optional[str]:
    """最初の開き括弧から、対応する閉じ括弧までを切り出す。

    文字列の中とエスケープを見ながら数える。ここを単純な rfind で済ませると、
    JSONの値としてソースコードや本文（`{` や `}` を含む）が入っているときに、
    関係のない括弧で切ってしまう。CODEモードやスライドの本文で実際に起きる。
    """
    start = text.find(open_ch)
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _slice(text: str, open_ch: str, close_ch: str) -> Optional[str]:
    """最初の開き括弧から、最後の閉じ括弧までを大きく切り出す（最後の手段）。"""
    i, j = text.find(open_ch), text.rfind(close_ch)
    return text[i:j + 1] if (i != -1 and j > i) else None


def _from(text: str):
    """1つの文字列から、読み取ってみる価値のある断片を可能性の高い順に出す。"""
    yield text
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        for cut in (_balanced(text, open_ch, close_ch), _slice(text, open_ch, close_ch)):
            if cut and cut != text:
                yield cut


def _candidates(text: str):
    """読み取ってみる価値のある文字列を、可能性の高い順に出す。"""
    t = (text or "").strip()
    if not t:
        return
    m = _FENCE.search(t)
    if m:
        inner = m.group(1).strip()
        if inner:
            # フェンスの中にも前置きが混ざることがある
            yield from _from(inner)
    yield from _from(t)


def extract(text: str) -> Optional[Any]:
    """本文からJSON（dict または list）を取り出す。読めなければ None。"""
    for raw in _candidates(text):
        for attempt in (raw, _TRAILING_COMMA.sub(r"\1", raw)):
            try:
                return json.loads(attempt)
            except Exception:
                continue
    return None


def extract_dict(text: str) -> Optional[dict]:
    """dict のときだけ返す（配列で返ってきたモデルの揺れを弾く）。"""
    v = extract(text)
    return v if isinstance(v, dict) else None


def extract_list(text: str) -> Optional[list]:
    """list のときだけ返す。"""
    v = extract(text)
    return v if isinstance(v, list) else None
