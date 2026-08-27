/**
 * 経過表示（AIbouが「いま何をしているか」）の見張り。
 *
 * これまで HOME と CHAT が同じものを別々に書いていた。片方だけ直すとずれるので、
 * AgentTrace に一本化した。ここが分かれ直すと、また片方だけ古くなる。
 *
 * 時間を出しているのは、ルールをGitHubから読む機能を足したときに
 * 「足したせいで遅くなったのか」を自分の目で判断できるようにするため。
 * 準備（記憶やルールの読み込み）は返事が始まる前に終わらせる必要があるので、
 * 重くなるとそのまま待ち時間になる。そこが見えないと原因を追えない。
 */

import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { formatMs } from "../src/components/AgentTrace";

const src = (p: string) => readFileSync(join(process.cwd(), "src", p), "utf8");

test("HOMEとCHATが同じ経過表示を使う", () => {
  const home = src("components/Home.tsx");
  const chat = src("components/Chat.tsx");
  expect(home).toContain("AgentTrace");
  expect(chat).toContain("AgentTrace");
  // それぞれが工程を独自に描き直していたら、また見た目がずれる。
  // （音声モードの「考えています…」は別物なので、工程の分岐だけを見る）
  expect(home).not.toContain('step.kind === "observation"');
  expect(chat).not.toContain('st.kind === "observation"');
});

test("準備の工程を画面に流す", () => {
  // ここを捨てると、記憶やルールの読み込みが重くなっても画面から見えない
  for (const f of ["components/Home.tsx", "components/Chat.tsx"]) {
    expect(src(f), f).toContain('case "prepare"');
  }
  expect(src("components/AgentTrace.tsx")).toContain('kind === "prepare"');
});

test("各工程にかかった時間を受け取っている", () => {
  for (const f of ["components/Home.tsx", "components/Chat.tsx"]) {
    expect(src(f), f).toContain("ms: ev.ms");
  }
  // 合計はターンが終わってから出す
  expect(src("components/Home.tsx")).toContain("total_ms");
  expect(src("components/Chat.tsx")).toContain("total_ms");
});

test("速いときは時間を出さない", () => {
  // 全部に数字を出すと、目が滑って肝心の遅い所が埋もれる
  expect(formatMs(0)).toBe("");
  expect(formatMs(120)).toBe("");
  expect(formatMs(399)).toBe("");
  expect(formatMs(undefined)).toBe("");
});

test("遅いときは読める形で出す", () => {
  expect(formatMs(400)).toBe("400ms");
  expect(formatMs(999)).toBe("999ms");
  expect(formatMs(1000)).toBe("1.0秒");
  expect(formatMs(4200)).toBe("4.2秒");
});

test("こわれた数字で表示が崩れない", () => {
  // SSEは外から来る。数値でない値が混ざっても画面は落とさない
  expect(formatMs(NaN)).toBe("");
  expect(formatMs(Infinity)).toBe("");
  expect(formatMs(-50)).toBe("");
});

test("イベントの型に時間と準備が入っている", () => {
  const api = src("lib/api.ts");
  expect(api).toContain('"prepare"');
  expect(api).toMatch(/ms\?: number/);
  expect(api).toMatch(/total_ms\?: number/);
});
