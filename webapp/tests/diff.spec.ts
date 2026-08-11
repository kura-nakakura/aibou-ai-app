/**
 * 差分エンジンの検証。
 *
 * エージェントの変更を「見てから受け入れる」ための土台なので、
 * 行番号と追加/削除の数がずれないことを厳しめに確かめる。
 */

import { test, expect } from "@playwright/test";
import { diffLines, collapseDiff, changedFiles } from "../src/lib/diff";

const render = (before: string, after: string) =>
  diffLines(before, after).lines.map((l) =>
    `${l.op === "same" ? " " : l.op === "add" ? "+" : "-"}${l.text}`);

test("no change → all lines are same", () => {
  const d = diffLines("a\nb\nc", "a\nb\nc");
  expect(d.added).toBe(0);
  expect(d.removed).toBe(0);
  expect(d.lines.every((l) => l.op === "same")).toBeTruthy();
});

test("a changed middle line shows as del + add", () => {
  expect(render("a\nb\nc", "a\nB\nc")).toEqual([" a", "-b", "+B", " c"]);
});

test("insertion in the middle", () => {
  expect(render("a\nc", "a\nb\nc")).toEqual([" a", "+b", " c"]);
});

test("deletion in the middle", () => {
  expect(render("a\nb\nc", "a\nc")).toEqual([" a", "-b", " c"]);
});

test("append at the end", () => {
  expect(render("a", "a\nb")).toEqual([" a", "+b"]);
});

test("new file (empty before) is all additions", () => {
  const d = diffLines("", "x\ny");
  expect(d.added).toBe(2);
  expect(d.removed).toBe(0);
});

test("deleted file (empty after) is all removals", () => {
  const d = diffLines("x\ny", "");
  expect(d.removed).toBe(2);
  expect(d.added).toBe(0);
});

test("line numbers line up on both sides", () => {
  const d = diffLines("a\nb\nc\nd", "a\nB\nc\nd\ne");
  const same = d.lines.filter((l) => l.op === "same");
  // 変更のない行は前後の行番号を両方持つ
  expect(same.every((l) => l.a !== undefined && l.b !== undefined)).toBeTruthy();
  const del = d.lines.find((l) => l.op === "del")!;
  expect(del.a).toBe(2);
  expect(del.b).toBeUndefined();
  const add = d.lines.find((l) => l.op === "add")!;
  expect(add.b).toBe(2);
  expect(add.a).toBeUndefined();
  // 末尾の追加行は変更後の5行目
  const lastAdd = d.lines.filter((l) => l.op === "add").at(-1)!;
  expect(lastAdd.b).toBe(5);
});

test("CRLF is normalized so it is not reported as a change", () => {
  const d = diffLines("a\r\nb", "a\nb");
  expect(d.added).toBe(0);
  expect(d.removed).toBe(0);
});

test("repeated lines do not confuse the alignment", () => {
  // 同じ行が並ぶケースでも、追加は1行だけ
  const d = diffLines("x\nx\nx", "x\nx\nx\nx");
  expect(d.added).toBe(1);
  expect(d.removed).toBe(0);
});

test("a large rewrite is truncated but says so", () => {
  const before = Array.from({ length: 1500 }, (_, i) => `a${i}`).join("\n");
  const after = Array.from({ length: 1500 }, (_, i) => `b${i}`).join("\n");
  const d = diffLines(before, after);
  expect(d.truncated).toBeTruthy();
  expect(d.added).toBe(1500);
  expect(d.removed).toBe(1500);
});

test("a large file with a small edit is NOT truncated (prefix/suffix trim)", () => {
  const lines = Array.from({ length: 4000 }, (_, i) => `line ${i}`);
  const before = lines.join("\n");
  const copy = [...lines];
  copy[2000] = "changed here";
  const d = diffLines(before, copy.join("\n"));
  expect(d.truncated).toBeFalsy();
  expect(d.added).toBe(1);
  expect(d.removed).toBe(1);
});

/* ── 折り畳み ───────────────────────────────────────────────────── */
test("unchanged runs collapse into a gap", () => {
  const lines = Array.from({ length: 40 }, (_, i) => `l${i}`);
  const after = [...lines];
  after[20] = "changed";
  const rows = collapseDiff(diffLines(lines.join("\n"), after.join("\n")).lines, 2);
  const gaps = rows.filter((r) => r.kind === "gap");
  expect(gaps.length).toBeGreaterThan(0);
  // 表示される行は変更周辺だけ（40行より大幅に少ない）
  expect(rows.filter((r) => r.kind === "line").length).toBeLessThan(12);
});

test("a file with no changes still shows a few lines", () => {
  const rows = collapseDiff(diffLines("a\nb\nc\nd", "a\nb\nc\nd").lines, 2);
  expect(rows.filter((r) => r.kind === "line").length).toBeGreaterThan(0);
  expect(rows.some((r) => r.kind === "gap")).toBeFalsy();
});

/* ── ファイル集合の比較 ─────────────────────────────────────────── */
test("changedFiles reports created / edited / deleted", () => {
  const before = [{ path: "a.js", content: "1" }, { path: "b.js", content: "keep" }];
  const after = [{ path: "b.js", content: "keep" }, { path: "c.js", content: "new" }];
  const ch = changedFiles(before, after);
  expect(ch.map((c) => c.path)).toEqual(["a.js", "c.js"]);   // b.js は無変更なので出ない
  const del = ch.find((c) => c.path === "a.js")!;
  expect(del.after).toBeNull();
  const add = ch.find((c) => c.path === "c.js")!;
  expect(add.before).toBeNull();
  expect(add.added).toBe(1);
});

test("changedFiles counts added/removed per file", () => {
  const ch = changedFiles(
    [{ path: "x.js", content: "a\nb\nc" }],
    [{ path: "x.js", content: "a\nB\nc\nd" }],
  );
  expect(ch[0].added).toBe(2);
  expect(ch[0].removed).toBe(1);
});
