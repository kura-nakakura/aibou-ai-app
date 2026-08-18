/**
 * 送る会話履歴の刈り込みの検証。
 *
 * ここは「速さのために文脈を捨てる」場所なので、捨てすぎないことが大事。
 * 普通の会話には一切触らず、長すぎるときだけ古いほうから落とすこと。
 */

import { test, expect } from "@playwright/test";
import { trimHistory, type HistoryTurn } from "../src/lib/history";

const turn = (role: "user" | "assistant", content: string): HistoryTurn => ({ role, content });

test("普通の長さの会話は何も変えない", () => {
  const h = [
    turn("user", "明日15時に歯医者の予定を入れて"),
    turn("assistant", "承知しました。登録しました。"),
    turn("user", "ありがとう"),
  ];
  expect(trimHistory(h)).toEqual(h);
});

test("空の履歴は空のまま", () => {
  expect(trimHistory([])).toEqual([]);
});

test("極端に長い1件は切って、切ったと分かるようにする", () => {
  const long = "あ".repeat(5000);
  const out = trimHistory([turn("assistant", long)]);
  expect(out).toHaveLength(1);
  expect(out[0].content.length).toBeLessThan(long.length);
  // 途中で終わっていると誤解されないよう、省略した旨を残す
  expect(out[0].content).toContain("省略");
});

test("全体が長すぎるときは、古いほうから落とす", () => {
  const h: HistoryTurn[] = [];
  for (let i = 0; i < 20; i++) h.push(turn("user", `${i}番目 ${"あ".repeat(1400)}`));
  const out = trimHistory(h);

  const total = out.reduce((n, t) => n + t.content.length, 0);
  expect(total).toBeLessThanOrEqual(12000 + 1500 * 4);   // 直近ぶんの余地は許す
  // 最新は必ず残る
  expect(out[out.length - 1].content).toContain("19番目");
  // 最古は落ちている
  expect(out.some((t) => t.content.includes("0番目"))).toBeFalsy();
  // 順番は保たれる（古い→新しい）
  const nums = out.map((t) => Number(t.content.split("番目")[0]));
  expect([...nums].sort((a, b) => a - b)).toEqual(nums);
});

test("直近のやりとりは、上限を超えても残す", () => {
  // 直近が全部巨大でも、文脈が消えると会話にならない
  const h = [
    turn("user", "い".repeat(9000)),
    turn("assistant", "ろ".repeat(9000)),
    turn("user", "は".repeat(9000)),
    turn("assistant", "に".repeat(9000)),
  ];
  const out = trimHistory(h);
  expect(out).toHaveLength(4);
});

test("役割（user / assistant）は変わらない", () => {
  const h = [turn("user", "あ"), turn("assistant", "い"), turn("user", "う")];
  expect(trimHistory(h).map((t) => t.role)).toEqual(["user", "assistant", "user"]);
});

test("上限は指定できる", () => {
  const h = [turn("user", "あ".repeat(100)), turn("assistant", "い".repeat(100))];
  const out = trimHistory(h, { perMessage: 10, total: 50, keepRecent: 0 });
  for (const t of out) expect(t.content.length).toBeLessThanOrEqual(10 + "…（長いため省略）".length);
});
