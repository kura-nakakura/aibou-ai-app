"""
api/memstore.py — 保存先が無いときの控えを、人ごとに分ける。

見つけた問題:
  各モジュールは「DBを引く → 失敗したらプロセス内のリストを返す」形だった。
  そのリストはモジュール変数なので、プロセス全体で1つしかない。

  つまり、AさんのDBが一瞬でも読めなかったとき（通信の揺れ、表の欠け、権限）、
  Aさんの画面に、そのプロセスで前に動いた別の人のデータが出る。
  黙って出るので、誰も気づかない。人に配る構成では、これは事故になる。

  書き込み側は require_storage で塞いだが、読み取り側は素通りだった。

直し方:
  控えを「そのとき繋いでいる保存先ごと」に分ける。リストとして振る舞うので、
  各モジュールは宣言を1行変えるだけでよく、append / insert / スライス /
  for / 内包表記 は今までどおり動く。

  保存先が違えば中身も違うので、他人のものが混ざらない。
  誰にも繋いでいない状態（1人運用）は、これまでどおり1つの控えを使う。
"""

from typing import Any, Dict, Iterator, List

import config


def _key() -> str:
    """いまの保存先を表す合言葉。

    クライアントの同一性で分ける。同じ人の同じ接続なら同じ鍵になり、
    別の人なら必ず別になる。繋いでいなければ "default"。
    """
    try:
        c = config.get_supabase()
    except Exception:
        c = None
    return f"c{id(c)}" if c is not None else "default"


class TenantList:
    """保存先ごとに中身が変わるリスト。

    list をそのまま継承しないのは、継承すると「自分自身の中身」と
    「保存先ごとの中身」が二重になり、どちらが正か分からなくなるため。
    必要な操作だけを、保存先ごとの実体に橋渡しする。
    """

    def __init__(self) -> None:
        self._by_tenant: Dict[str, List[Any]] = {}

    # ── 実体 ──────────────────────────────────────────────────────
    def _list(self) -> List[Any]:
        return self._by_tenant.setdefault(_key(), [])

    # ── リストとしての振る舞い ────────────────────────────────────
    def __iter__(self) -> Iterator[Any]:
        return iter(self._list())

    def __len__(self) -> int:
        return len(self._list())

    def __bool__(self) -> bool:
        return bool(self._list())

    def __getitem__(self, i):
        return self._list()[i]

    def __setitem__(self, i, v) -> None:
        self._list()[i] = v

    def __delitem__(self, i) -> None:
        del self._list()[i]

    def __contains__(self, v) -> bool:
        return v in self._list()

    def __repr__(self) -> str:
        return repr(self._list())

    def append(self, v) -> None:
        self._list().append(v)

    def insert(self, i, v) -> None:
        self._list().insert(i, v)

    def extend(self, vs) -> None:
        self._list().extend(vs)

    def remove(self, v) -> None:
        self._list().remove(v)

    def pop(self, i=-1):
        return self._list().pop(i)

    def sort(self, **kw) -> None:
        self._list().sort(**kw)

    def reverse(self) -> None:
        self._list().reverse()

    def index(self, v, *a):
        return self._list().index(v, *a)

    def count(self, v) -> int:
        return self._list().count(v)

    def clear(self) -> None:
        """テストの後片付けで使う。全部の保存先ぶんを消す。"""
        self._by_tenant.clear()


class TenantDict:
    """保存先ごとに中身が変わる辞書。用途は TenantList と同じ。"""

    def __init__(self) -> None:
        self._by_tenant: Dict[str, Dict[Any, Any]] = {}

    def _d(self) -> Dict[Any, Any]:
        return self._by_tenant.setdefault(_key(), {})

    def __iter__(self):
        return iter(self._d())

    def __len__(self) -> int:
        return len(self._d())

    def __bool__(self) -> bool:
        return bool(self._d())

    def __getitem__(self, k):
        return self._d()[k]

    def __setitem__(self, k, v) -> None:
        self._d()[k] = v

    def __delitem__(self, k) -> None:
        del self._d()[k]

    def __contains__(self, k) -> bool:
        return k in self._d()

    def __repr__(self) -> str:
        return repr(self._d())

    def get(self, k, default=None):
        return self._d().get(k, default)

    def setdefault(self, k, default=None):
        return self._d().setdefault(k, default)

    def pop(self, k, *a):
        return self._d().pop(k, *a)

    def keys(self):
        return self._d().keys()

    def values(self):
        return self._d().values()

    def items(self):
        return self._d().items()

    def update(self, *a, **kw) -> None:
        self._d().update(*a, **kw)

    def clear(self) -> None:
        self._by_tenant.clear()
