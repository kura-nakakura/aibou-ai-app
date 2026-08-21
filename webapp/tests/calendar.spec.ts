/**
 * カレンダーの組み立ての検証。
 *
 * 日付の計算はズレても「なんとなく合っている」ように見えるので、目視では
 * 気づけない。月またぎ・うるう年・時差の扱いを、ここで固定しておく。
 */

import { test, expect } from "@playwright/test";
import { groupByDate, monthCells, monthLabel, shiftMonth, WEEKDAYS, ymd } from "../src/lib/calendar";

test("ymd はローカルの日付を返す（UTCに寄せない）", () => {
  // toISOString を使うと、日本時間の朝9時より前が前日になる
  const d = new Date(2026, 7, 21, 3, 0, 0);   // 8月21日 午前3時
  expect(ymd(d)).toBe("2026-08-21");
});

test("月のマス目は必ず42個（切り替えで高さが跳ねない）", () => {
  for (const [y, m] of [[2026, 0], [2026, 1], [2026, 7], [2024, 1]] as const) {
    expect(monthCells(y, m)).toHaveLength(42);
  }
});

test("マス目は日曜から始まる", () => {
  const cells = monthCells(2026, 7);           // 2026年8月
  expect(new Date(cells[0].date + "T00:00:00").getDay()).toBe(0);
  expect(WEEKDAYS[0]).toBe("日");
});

test("その月の日だけ inMonth が立つ", () => {
  const cells = monthCells(2026, 7);           // 8月は31日まで
  expect(cells.filter((c) => c.inMonth)).toHaveLength(31);
  const first = cells.find((c) => c.inMonth)!;
  expect(first.date).toBe("2026-08-01");
});

test("うるう年の2月は29日ある", () => {
  expect(monthCells(2024, 1).filter((c) => c.inMonth)).toHaveLength(29);
  expect(monthCells(2026, 1).filter((c) => c.inMonth)).toHaveLength(28);
});

test("月またぎ（12月の次は翌年1月）", () => {
  expect(shiftMonth(2026, 11, 1)).toEqual({ year: 2027, month0: 0 });
  expect(shiftMonth(2026, 0, -1)).toEqual({ year: 2025, month0: 11 });
  expect(monthLabel(2027, 0)).toBe("2027年1月");
});

test("同じ日の予定は時刻順、終日が先", () => {
  const grouped = groupByDate([
    { date: "2026-08-21", time: "15:00", title: "夕方" },
    { date: "2026-08-21", time: "", title: "終日" },
    { date: "2026-08-21", time: "09:30", title: "朝" },
    { date: "2026-08-22", time: "10:00", title: "翌日" },
  ]);
  expect(grouped["2026-08-21"].map((e) => e.title)).toEqual(["終日", "朝", "夕方"]);
  expect(grouped["2026-08-22"]).toHaveLength(1);
});

test("日時つきの値でも日付で束ねられる", () => {
  // Googleカレンダーは 2026-08-21T15:00:00+09:00 の形で返ってくる
  const grouped = groupByDate([{ date: "2026-08-21T15:00:00+09:00", time: "15:00", title: "G" }]);
  expect(grouped["2026-08-21"]).toHaveLength(1);
});

test("日付が空のものは落とす（キーが空の束ができない）", () => {
  const grouped = groupByDate([{ date: "", time: "", title: "壊れた行" }]);
  expect(Object.keys(grouped)).toHaveLength(0);
});
