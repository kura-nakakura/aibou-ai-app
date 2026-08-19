/**
 * ログインの案内文の検証。
 *
 * ここが壊れると「何を直せばいいのか分からないログイン画面」になる。
 * 事故になりやすいのは
 *   ・Supabaseの英語がそのまま出る（利用者には意味が分からない）
 *   ・入力ミスなのにサーバーへ投げてしまう（待たされた上で英語が返る）
 *   ・エラーと成功が同じ色で出る（送信できたのか分からない）
 * なので、そこを重点的に確かめる。
 */

import { test, expect } from "@playwright/test";
import {
  authNotice, validateCredentials, confirmState, NOTICE_COLOR,
} from "../src/lib/authMessages";

/* ── Supabaseの英語 → 日本語 ────────────────────────────────────── */
test("the common sign-in failure is explained in Japanese, not English", () => {
  const n = authNotice("Invalid login credentials");
  expect(n.text).toBe("メールアドレスかパスワードが違います");
  expect(n.tone).toBe("error");
  // 英語が混ざっていないこと
  expect(n.text).not.toMatch(/[A-Za-z]/);
});

test("an unconfirmed email tells you to open the link (not an error)", () => {
  const n = authNotice("Email not confirmed");
  expect(n.text).toContain("リンク");
  expect(n.tone).toBe("info");     // 失敗ではなく「やることが残っている」
});

test("an already-registered address points at sign-in", () => {
  expect(authNotice("User already registered").text).toContain("サインイン");
});

test("a short password says the required length", () => {
  expect(authNotice("Password should be at least 6 characters").text).toContain("6文字");
});

test("a network failure suggests checking the connection", () => {
  expect(authNotice(new Error("Failed to fetch")).text).toContain("通信");
});

test("rate limiting asks you to wait rather than retry immediately", () => {
  const n = authNotice("email rate limit exceeded");
  expect(n.text).toContain("時間");
  expect(n.tone).toBe("info");
});

test("unknown errors are shown as-is instead of being swallowed", () => {
  // 知らないものを「認証に失敗しました」で潰すと、原因の手掛かりが消える
  const n = authNotice("Some brand new upstream failure");
  expect(n.text).toBe("Some brand new upstream failure");
  expect(n.tone).toBe("error");
});

test("empty input still produces a message", () => {
  expect(authNotice("").text).toBe("認証に失敗しました");
  expect(authNotice(null).text).toBe("認証に失敗しました");
  expect(authNotice(undefined).text).toBe("認証に失敗しました");
});

/* ── 送信前チェック ─────────────────────────────────────────────── */
test("missing fields are caught before hitting the server", () => {
  const noEmail = validateCredentials("", "pw", "signin");
  expect(noEmail?.text).toContain("メールアドレス");
  expect(noEmail?.field).toBe("email");      // その欄にフォーカスを戻すため

  const noPw = validateCredentials("me@example.com", "", "signin");
  expect(noPw?.text).toContain("パスワード");
  expect(noPw?.field).toBe("password");
});

test("an obviously malformed address is caught locally", () => {
  for (const bad of ["not-an-email", "a@b", "a b@c.com", "@example.com", "me@"]) {
    expect(validateCredentials(bad, "pw123456", "signin"), bad).not.toBeNull();
  }
});

test("valid credentials pass, and whitespace around the address is tolerated", () => {
  expect(validateCredentials("me@example.com", "pw", "signin")).toBeNull();
  expect(validateCredentials("  me@example.com  ", "pw", "signin")).toBeNull();
});

test("sign-up requires 6+ characters, sign-in does not", () => {
  // 新規作成のときだけ長さを見る。既存アカウントの短いパスワードを弾かない。
  expect(validateCredentials("me@example.com", "12345", "signup", "12345")?.field).toBe("password");
  expect(validateCredentials("me@example.com", "123456", "signup", "123456")).toBeNull();
  expect(validateCredentials("me@example.com", "12345", "signin")).toBeNull();
});

/* ── 確認用パスワード ────────────────────────────────────────────── */
test("新規登録は確認用の一致を求める", () => {
  // 1回しか打たないと、打ち間違えたまま登録が通り、次から入れなくなる。
  // 本人には打ち間違いだと分からないので、ここで必ず止める。
  const missing = validateCredentials("me@example.com", "pw123456", "signup");
  expect(missing?.field).toBe("confirm");
  expect(missing?.text).toContain("確認用");

  const mismatch = validateCredentials("me@example.com", "pw123456", "signup", "pw12345X");
  expect(mismatch?.field).toBe("confirm");
  expect(mismatch?.text).toContain("一致しません");

  expect(validateCredentials("me@example.com", "pw123456", "signup", "pw123456")).toBeNull();
});

test("サインインでは確認用を求めない", () => {
  // 既存アカウントで入るときに、確認欄を出すのは邪魔なだけ
  expect(validateCredentials("me@example.com", "pw123456", "signin")).toBeNull();
  expect(validateCredentials("me@example.com", "pw123456", "signin", "")).toBeNull();
});

test("長さ不足のほうを先に伝える", () => {
  // 一致していても短ければ通らない。指摘は1つずつ、直せる順に出す。
  const r = validateCredentials("me@example.com", "123", "signup", "123");
  expect(r?.field).toBe("password");
});

test("確認欄の状態は 空 / 一致 / 不一致 の3つ", () => {
  expect(confirmState("pw123456", "")).toBe("empty");
  expect(confirmState("pw123456", "pw123456")).toBe("match");
  expect(confirmState("pw123456", "pw12345")).toBe("mismatch");
  // 打っている途中は不一致だが、それを伝えるのは正しい（打ち終わってからでは遅い）
  expect(confirmState("pw123456", "p")).toBe("mismatch");
  // 大文字小文字・空白も別物として扱う
  expect(confirmState("PW123456", "pw123456")).toBe("mismatch");
  expect(confirmState("pw123456", "pw123456 ")).toBe("mismatch");
});

/* ── 色 ─────────────────────────────────────────────────────────── */
test("error / info / ok are three distinct colours", () => {
  const { error, info, ok } = NOTICE_COLOR;
  expect(new Set([error, info, ok]).size).toBe(3);
});
