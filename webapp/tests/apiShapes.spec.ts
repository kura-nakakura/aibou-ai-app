/**
 * 「応答の形が足りないとき、画面が真っ白にならないか」の検証。
 *
 * 全モードを一斉に開いて分かったこと: MEモードが完全に落ちていた。
 * /life/entries の応答に categories が無く、それをそのまま画面へ渡していたので
 * LifeMode の categories.length で例外になり、モードごと空白になっていた。
 * 画面には何も出ないので、利用者には「壊れた」としか分からない。
 *
 * サーバーが古い・エラー時に縮退する・一部のキーだけ返す、は普通に起きる。
 * 配列のはずの場所は必ず配列にする、を lib/shape.ts に一本化した。
 */

import { test, expect } from "@playwright/test";
import { asArray, asNumber, asText } from "../src/lib/shape";

test("配列でない値は、すべて空配列になる", () => {
  // 実際に来たことがある形を並べる。どれも画面は .length / .map で触る
  for (const v of [undefined, null, "壊れた値", 0, {}, true, NaN]) {
    expect(asArray(v), `${String(v)} が配列にならない`).toEqual([]);
  }
});

test("配列はそのまま通す（中身を勝手に変えない）", () => {
  const src = [{ key: "work", label: "仕事" }];
  expect(asArray(src)).toBe(src);
  expect(asArray([])).toEqual([]);
});

test("数値でない値は既定値になる", () => {
  expect(asNumber(undefined)).toBe(0);
  expect(asNumber(null)).toBe(0);
  expect(asNumber("たくさん")).toBe(0);
  expect(asNumber(NaN)).toBe(0);
  expect(asNumber(Infinity)).toBe(0);
  expect(asNumber(undefined, 5)).toBe(5);
});

test("数値と、数値の文字列は通す", () => {
  expect(asNumber(3)).toBe(3);
  expect(asNumber(0)).toBe(0);          // 0 を「未設定」と誤判定しない
  expect(asNumber("12")).toBe(12);
  expect(asNumber(-1)).toBe(-1);
});

test("空文字は既定値に落ちない（意図して空にした値を消さない）", () => {
  expect(asText("")).toBe("");
  expect(asText(undefined)).toBe("");
  expect(asText(undefined, "既定")).toBe("既定");
  expect(asText(123)).toBe("");
});

/* ── 画面が実際にする操作を、欠けた応答に対してやってみる ────────── */
test("欠けた応答でも、画面がする操作が例外にならない", () => {
  // LifeMode がやっていたこと: categories.length / categories.map / find
  const broken = { items: undefined, categories: undefined } as Record<string, unknown>;
  const categories = asArray<{ key: string; label: string }>(broken.categories);
  const items = asArray<{ id: string }>(broken.items);

  expect(() => {
    void categories.length;
    categories.map((c) => c.label);
    categories.find((c) => c.key === "work");
    items.filter(Boolean);
  }).not.toThrow();
});
