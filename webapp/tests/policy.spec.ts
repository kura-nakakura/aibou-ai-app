/**
 * プライバシー規約と、アカウント作成時の説明の検証。
 *
 * 人に配るアプリなので「知らないうちにデータがどこかへ行っていた」を作らない
 * ことが大事。登録の前に説明が出ること、規約がバックエンド無しでも読めること、
 * そして本文が実装と食い違っていないことを見る。
 */

import { test, expect } from "@playwright/test";
import { PRIVACY, SIGNUP_SUMMARY, POLICY_VERSION } from "../src/lib/policy";

/* ── 本文そのものの検証（実装とズレていないか）───────────────────── */
test("規約の各節が、中身のある形になっている", () => {
  expect(PRIVACY.length).toBeGreaterThanOrEqual(5);
  for (const s of PRIVACY) {
    expect(s.id).toBeTruthy();
    expect(s.title).toBeTruthy();
    expect(s.points.length).toBeGreaterThan(0);
    for (const p of s.points) expect(p.length).toBeGreaterThan(10);
  }
});

test("節のidが重複していない", () => {
  const ids = PRIVACY.map((s) => s.id);
  expect(new Set(ids).size).toBe(ids.length);
});

test("データの置き場をはっきり書いている", () => {
  const where = PRIVACY.find((s) => s.id === "where");
  const text = where!.points.join(" ");
  expect(text).toContain("Supabase");
  // 繋ぐまでは保存されない。黙って消すのをやめ、その場で断るようにしたので
  // 「消えます」ではなく「受け付けません」と書いてあることを見る
  expect(text).toContain("保存先がつながっていません");
  expect(text).toContain("黙って消えることはありません");
  expect(text).toContain("他の利用者");
});

test("外部に送られる先を隠していない", () => {
  const ext = PRIVACY.find((s) => s.id === "external");
  const text = ext!.points.join(" ");
  // 実装が実際に送っている先は全部書く
  expect(text).toContain("Google");
  expect(text).toContain("HuggingFace");
  expect(text).toContain("Microsoft");     // サーバーの声（edge-tts）
  expect(text).toContain("X");             // 実投稿できるようにしたため
});

test("管理者が技術的に何をできるかを、都合よく省いていない", () => {
  const admin = PRIVACY.find((s) => s.id === "admin");
  const text = admin!.points.join(" ") + (admin!.notes ?? []).join(" ");
  // 「絶対に見られません」と書いてしまうのが一番まずい
  expect(text).not.toContain("絶対に見られません");
  expect(text).toMatch(/技術的には|接続できます/);
  expect(text).toContain("パスワード");     // パスワードは見られない、は書く
});

test("鍵の扱いを書いている", () => {
  const keys = PRIVACY.find((s) => s.id === "keys");
  const text = keys!.points.join(" ");
  expect(text).toContain("暗号化");
  expect(text).toMatch(/マスク|伏せ字|全文は返しません/);
});

test("やめ方・消し方が書いてある", () => {
  const del = PRIVACY.find((s) => s.id === "delete");
  expect(del!.points.join(" ")).toMatch(/解除|削除/);
});

test("登録画面の要点は、短く読み切れる量にする", () => {
  expect(SIGNUP_SUMMARY.length).toBeGreaterThanOrEqual(3);
  expect(SIGNUP_SUMMARY.length).toBeLessThanOrEqual(6);
  for (const s of SIGNUP_SUMMARY) expect(s.length).toBeLessThan(120);
});

test("更新日が入っている", () => {
  expect(POLICY_VERSION).toMatch(/^\d{4}\.\d{2}\.\d{2}$/);
});

/* ── 画面での見え方 ──────────────────────────────────────────────── */
test("最初の画面から、バックエンド無しでも規約が読める", async ({ page }) => {
  // 規約はサーバーが落ちていても読めないと意味がない（登録は接続前に行う）
  await page.goto("/");
  await page.getByRole("button", { name: /プライバシーと利用について/ }).click();
  await expect(page.getByRole("dialog", { name: /プライバシー/ })).toBeVisible({ timeout: 5_000 });
  await expect(page.getByText("あなたのデータがどこに入るか")).toBeVisible();
  await expect(page.getByText("管理者ができること・できないこと")).toBeVisible();
  await page.getByRole("button", { name: "閉じる" }).click();
  await expect(page.getByRole("dialog", { name: /プライバシー/ })).toBeHidden();
});
