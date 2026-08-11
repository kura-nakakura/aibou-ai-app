/**
 * diff.ts — 行単位の差分。エージェントの変更を「見てから受け入れる」ために使う.
 *
 * 生成AIに任せるうえで一番怖いのは、何が変わったのか分からないまま
 * ファイルが書き換わることなので、適用前後を並べて確認できるようにする。
 *
 * 実装は「共通の先頭・末尾を削ってから、残りだけLCS」。コード編集は
 * 大部分が一致するので、この前処理だけで実用的な速度になる。
 * それでも大きすぎる場合は行数上限で打ち切り、打ち切ったことを返す
 * （黙って一部だけ見せると差分を信用できなくなる）。
 */

export type DiffOp = "same" | "add" | "del";

export interface DiffLine {
  op: DiffOp;
  text: string;
  /** 変更前の行番号（1始まり。追加行では undefined） */
  a?: number;
  /** 変更後の行番号（1始まり。削除行では undefined） */
  b?: number;
}

export interface DiffResult {
  lines: DiffLine[];
  added: number;
  removed: number;
  /** 大きすぎて全部は比較しなかった場合に true */
  truncated: boolean;
}

/** LCSを計算する行数の上限（before×after のセル数）。 */
const MAX_CELLS = 1_500_000;

function splitLines(s: string): string[] {
  if (s === "") return [];
  return s.replace(/\r\n?/g, "\n").split("\n");
}

/** 変更前後の行差分を求める。 */
export function diffLines(before: string, after: string): DiffResult {
  const A = splitLines(before);
  const B = splitLines(after);

  // 共通の先頭
  let head = 0;
  while (head < A.length && head < B.length && A[head] === B[head]) head += 1;
  // 共通の末尾（先頭ぶんを侵食しないように止める）
  let tail = 0;
  while (
    tail < A.length - head
    && tail < B.length - head
    && A[A.length - 1 - tail] === B[B.length - 1 - tail]
  ) tail += 1;

  const midA = A.slice(head, A.length - tail);
  const midB = B.slice(head, B.length - tail);

  const lines: DiffLine[] = [];
  for (let i = 0; i < head; i += 1) lines.push({ op: "same", text: A[i], a: i + 1, b: i + 1 });

  let truncated = false;
  if (midA.length * midB.length > MAX_CELLS) {
    // 大きすぎるときはLCSを諦め、削除→追加としてまとめて見せる
    truncated = true;
    midA.forEach((t, i) => lines.push({ op: "del", text: t, a: head + i + 1 }));
    midB.forEach((t, i) => lines.push({ op: "add", text: t, b: head + i + 1 }));
  } else {
    // LCS の長さ表（midA × midB）
    const n = midA.length, m = midB.length;
    const dp: Uint32Array = new Uint32Array((n + 1) * (m + 1));
    const at = (i: number, j: number) => i * (m + 1) + j;
    for (let i = n - 1; i >= 0; i -= 1) {
      for (let j = m - 1; j >= 0; j -= 1) {
        dp[at(i, j)] = midA[i] === midB[j]
          ? dp[at(i + 1, j + 1)] + 1
          : Math.max(dp[at(i + 1, j)], dp[at(i, j + 1)]);
      }
    }
    let i = 0, j = 0;
    while (i < n && j < m) {
      if (midA[i] === midB[j]) {
        lines.push({ op: "same", text: midA[i], a: head + i + 1, b: head + j + 1 });
        i += 1; j += 1;
      } else if (dp[at(i + 1, j)] >= dp[at(i, j + 1)]) {
        lines.push({ op: "del", text: midA[i], a: head + i + 1 });
        i += 1;
      } else {
        lines.push({ op: "add", text: midB[j], b: head + j + 1 });
        j += 1;
      }
    }
    while (i < n) { lines.push({ op: "del", text: midA[i], a: head + i + 1 }); i += 1; }
    while (j < m) { lines.push({ op: "add", text: midB[j], b: head + j + 1 }); j += 1; }
  }

  for (let k = 0; k < tail; k += 1) {
    const ai = A.length - tail + k;
    const bi = B.length - tail + k;
    lines.push({ op: "same", text: A[ai], a: ai + 1, b: bi + 1 });
  }

  return {
    lines,
    added: lines.filter((l) => l.op === "add").length,
    removed: lines.filter((l) => l.op === "del").length,
    truncated,
  };
}

/**
 * 変更のない行を畳んで、変更箇所の周辺だけを残す（unified diff の -U 相当）。
 * 畳んだ位置には gap を入れて「省略した行数」が分かるようにする。
 */
export interface DiffChunk { kind: "line"; line: DiffLine }
export interface DiffGap { kind: "gap"; count: number }
export type DiffRow = DiffChunk | DiffGap;

export function collapseDiff(lines: DiffLine[], context = 3): DiffRow[] {
  const keep = new Array<boolean>(lines.length).fill(false);
  lines.forEach((l, i) => {
    if (l.op === "same") return;
    for (let k = Math.max(0, i - context); k <= Math.min(lines.length - 1, i + context); k += 1) {
      keep[k] = true;
    }
  });
  // 変更が無いファイルは先頭だけ見せる（真っ白より状況が分かる）
  if (!keep.some(Boolean)) {
    return lines.slice(0, context * 2).map((line) => ({ kind: "line" as const, line }));
  }
  const rows: DiffRow[] = [];
  let gap = 0;
  for (let i = 0; i < lines.length; i += 1) {
    if (keep[i]) {
      if (gap) { rows.push({ kind: "gap", count: gap }); gap = 0; }
      rows.push({ kind: "line", line: lines[i] });
    } else {
      gap += 1;
    }
  }
  if (gap) rows.push({ kind: "gap", count: gap });
  return rows;
}

export interface FileChange {
  path: string;
  before: string | null;   // null = 新規作成
  after: string | null;    // null = 削除
  added: number;
  removed: number;
}

/** 適用前後のファイル集合を比べて、変わったファイルだけを返す。 */
export function changedFiles(
  before: { path: string; content: string }[],
  after: { path: string; content: string }[],
): FileChange[] {
  const b = new Map(before.map((f) => [f.path, f.content]));
  const a = new Map(after.map((f) => [f.path, f.content]));
  const paths = Array.from(new Set([...b.keys(), ...a.keys()])).sort();
  const out: FileChange[] = [];
  for (const path of paths) {
    const bc = b.has(path) ? b.get(path)! : null;
    const ac = a.has(path) ? a.get(path)! : null;
    if (bc === ac) continue;
    const d = diffLines(bc ?? "", ac ?? "");
    out.push({ path, before: bc, after: ac, added: d.added, removed: d.removed });
  }
  return out;
}
