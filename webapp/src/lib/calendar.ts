/**
 * calendar — 月表示の組み立て。
 *
 * 日付の計算は画面から切り離す。月またぎ・週の始まり・今日の判定は
 * 目で見て確かめにくく、ズレても「なんとなく合っている」ように見えるため。
 */

export type Cell = {
  /** YYYY-MM-DD。前後の月のマス目も入る */
  date: string;
  /** この月の日か（前後の月は薄く出す） */
  inMonth: boolean;
  day: number;
};

/** ローカル時刻で YYYY-MM-DD。toISOString はUTCに寄るので使わない。 */
export function ymd(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/**
 * その月のカレンダーのマス目。日曜始まりの6週ぶん（42マス）を必ず返す。
 * 月によって行数が変わると、切り替えるたびに下の要素が跳ねる。
 */
export function monthCells(year: number, month0: number): Cell[] {
  const first = new Date(year, month0, 1);
  const start = new Date(year, month0, 1 - first.getDay());
  const cells: Cell[] = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i);
    cells.push({ date: ymd(d), inMonth: d.getMonth() === month0, day: d.getDate() });
  }
  return cells;
}

/** 日付ごとに束ねる。同じ日の中は時刻順（終日は先頭）。 */
export function groupByDate<T extends { date: string; time?: string }>(
  items: T[],
): Record<string, T[]> {
  const out: Record<string, T[]> = {};
  for (const it of items) {
    const key = (it.date || "").slice(0, 10);
    if (!key) continue;
    (out[key] ||= []).push(it);
  }
  for (const k of Object.keys(out)) {
    out[k].sort((a, b) => (a.time || "").localeCompare(b.time || ""));
  }
  return out;
}

/** 月を動かす。12月の次を1月にする計算をあちこちに書かない。 */
export function shiftMonth(year: number, month0: number, delta: number):
  { year: number; month0: number } {
  const d = new Date(year, month0 + delta, 1);
  return { year: d.getFullYear(), month0: d.getMonth() };
}

export const WEEKDAYS = ["日", "月", "火", "水", "木", "金", "土"];

export function monthLabel(year: number, month0: number): string {
  return `${year}年${month0 + 1}月`;
}
