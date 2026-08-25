/**
 * 「お金をかけずに時刻どおり動かす」案内の検証。
 *
 * 無料プランのサーバーは寝るので、定期実行は外から起こしてもらう必要がある。
 * これはコードでは直せない制約なので、代わりに「もう持っているもので済む」
 * ことを示す。ここが不正確だと、そのとおりにやったのに動かない、になる。
 */

import { test, expect } from "@playwright/test";
import { FREE_OPS, FREE_OPS_SUMMARY } from "../src/lib/freeOps";

test("どの方法にも、手順と「すでに持っているもの」がある", () => {
  for (const m of FREE_OPS) {
    expect(m.steps.length, `${m.id} の手順`).toBeGreaterThan(1);
    expect(m.youAlreadyHave.length, `${m.id} の前提`).toBeGreaterThan(2);
    expect(m.accuracy, `${m.id} の正確さ`).toBeTruthy();
  }
});

test("すでに持っているものから順に並んでいる", () => {
  // 新しくサービス登録が要るものを先頭に置くと、そこで諦められる
  expect(FREE_OPS[0].id).toBe("github");
  expect(FREE_OPS[FREE_OPS.length - 1].id).toBe("cronjob");
});

test("どれか1つで足りると言っている", () => {
  // 全部やる必要があると読まれると、重すぎて誰もやらない
  expect(FREE_OPS_SUMMARY).toContain("どれか1つ");
});

test("GitHubの手順が、実在するワークフローを指している", () => {
  const gh = FREE_OPS.find((m) => m.id === "github")!;
  expect(gh.note).toContain("scheduler-tick.yml");
  // 設定するのは1つだけ（増やすと詰まる）
  expect(gh.steps.join("")).toContain("BACKEND_URL");
});

test("SupabaseのSQLが、貼れる形になっている", () => {
  const sb = FREE_OPS.find((m) => m.id === "supabase")!;
  const sql = sb.snippet!({ apiUrl: "https://api.example.com" });
  expect(sql).toContain("create extension if not exists pg_cron");
  expect(sql).toContain("create extension if not exists pg_net");
  expect(sql).toContain("https://api.example.com/scheduler/tick");
  // 何度実行しても壊れない形
  expect(sql).toContain("if not exists");
  // やめ方も書く（始め方だけ書いて放置させない）
  expect(sql).toContain("unschedule");
});

test("SQLに秘密を埋め込んでいない", () => {
  const sql = FREE_OPS.find((m) => m.id === "supabase")!
    .snippet!({ apiUrl: "https://api.example.com" });
  // SQL Editor に貼る＝画面に出る。鍵を混ぜてはいけない
  expect(sql.toLowerCase()).not.toContain("service_role");
  expect(sql.toLowerCase()).not.toContain("apikey");
  expect(sql).not.toContain("Bearer ");
});

test("ショートカットは、トリガーが無いときに空URLを出さない", () => {
  const sc = FREE_OPS.find((m) => m.id === "shortcut")!;
  expect(sc.snippet!({ apiUrl: "https://api.example.com" }))
    .toContain("先にトリガーを作ってください");
  expect(sc.snippet!({ apiUrl: "x", hookUrl: "https://api.example.com/hook/abc" }))
    .toBe("https://api.example.com/hook/abc");
});

test("確実でない方法には、そう書いてある", () => {
  // スマホが圏外なら動かない。期待させない
  const sc = FREE_OPS.find((m) => m.id === "shortcut")!;
  expect(sc.note).toContain("圏外");
});

test("トークンが要る場合の足し方が書いてある", () => {
  const cj = FREE_OPS.find((m) => m.id === "cronjob")!;
  expect(cj.note).toContain("Authorization");
});
