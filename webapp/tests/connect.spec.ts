/**
 * 連携が「押すだけ」であることの見張り。
 *
 * 要望: 「ClaudeはGoogleアドレスで連携できるのに、なぜこのアプリはAPIキーを
 * 入れないといけないのか」。
 *
 * 答えは OAuth で、Anthropic が提供元にアプリを一度だけ登録してあり、その
 * client_id/secret を自分のサーバーに持っているから。利用者が鍵を持たないの
 * ではなく、作り手が代わりに持っている。ここも同じ形にした。
 *
 * 画面で守りたいのは3つ:
 *   ・鍵の入力欄ではなく「◯◯と連携する」が先に出ること
 *   ・「持ち主のアプリ登録がまだ」と「この人がまだ許可していない」を混ぜないこと
 *     （混ぜると、利用者が自分では直せないことを直そうとして詰まる）
 *   ・AIの鍵だけは手入力のままで、その理由が言えること
 */

import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const src = (p: string) => readFileSync(join(process.cwd(), "src", p), "utf8");
const api = (p: string) => readFileSync(join(process.cwd(), "..", "api", p), "utf8");

test("押すだけで繋げる先が、鍵の入力欄より先に出る", () => {
  const ui = src("components/Extensions.tsx");
  const connectAt = ui.indexOf("と連携する");
  const fieldsAt = ui.indexOf("ext.fields.map");
  expect(connectAt).toBeGreaterThan(-1);
  expect(connectAt).toBeLessThan(fieldsAt);
});

test("繋がっていれば、貼る欄は畳んである", () => {
  const ui = src("components/Extensions.tsx");
  expect(ui).toContain("手で入れる（上級者向け）");
  // 押すだけで繋げる先か、アプリ登録の値を持つ先は畳む
  expect(ui).toMatch(/foldKeys\s*=\s*Boolean\(provider\)/);
});

test("アプリ登録の値は、利用者に見せない", () => {
  // GOOGLE_CLIENT_ID は「このアプリ自身の身分証」で、利用者が取ってくる物ではない。
  // 全員に見せると「自分が用意しないといけない値」に見えてしまう。
  const list = src("lib/extensions.ts");
  const g = list.slice(list.indexOf('id: "google"'), list.indexOf('id: "github"'));
  expect(g).toMatch(/GOOGLE_CLIENT_ID[^\n]*appOnly: true/);
  expect(g).toMatch(/GOOGLE_CLIENT_SECRET[^\n]*appOnly: true/);
  // 手順も「持ち主が1回だけ」と分かる書き方になっていること
  expect(g).toContain("アプリの持ち主が1回だけ行います");
});

test("「登録がまだ」と「許可がまだ」を分けている", () => {
  const ui = src("components/Extensions.tsx");
  expect(ui).toContain("アプリ登録をまだ済ませていない");

  const py = api("oauth.py");
  expect(py).toMatch(/"configured": configured\(provider\)/);
  expect(py).toMatch(/"connected": rec is not None/);
});

test("Googleを繋げば、メールにアプリパスワードが要らない", () => {
  // 設定の中でいちばん脱落する手順（2段階認証→アプリパスワード→16文字）
  const list = src("lib/extensions.ts");
  const g = list.slice(list.indexOf('id: "google"'), list.indexOf('id: "github"'));
  expect(g).toContain("アプリパスワードを作る手順が要らなくなります");

  const py = api("oauth.py");
  expect(py).toContain("gmail.readonly");
  expect(api("email_svc.py")).toContain("def _gmail_ready");
});

test("AIの鍵だけは手入力のままで、理由が言える", () => {
  // OAuth は「代理で持つ」仕組みなので、請求先そのものには使えない。
  const py = api("oauth.py");
  expect(py).toContain("GEMINI_API_KEY");
  expect(py).toMatch(/請求先そのものなので、代理で持てません/);
  // LINE も、公式アカウントが1人1つなので代理で作れない
  expect(py).toMatch(/LINE_CHANNEL_TOKEN[\s\S]{0,80}代理で作れません/);
});

test("戻りは、始めた本人のものとして扱われる", () => {
  // ここを省いていたのが元の漏れ。誰か1人の連携がサーバー全体の既定になり、
  // 繋いでいない他の利用者がその人のアカウントで動いていた。
  const m = api("main.py");
  expect(m).toContain("checked.get(\"owner\")");
  expect(m).toMatch(/if client is not None or not is_owner:/);
  expect(m).toContain("bind_request_client(client)");

  const py = api("oauth.py");
  expect(py).toContain("def sign_state");
  expect(py).toContain("hmac.compare_digest");
});

test("連携の失敗を、成功に見せない", () => {
  // 画面は赤いのに機械からは 200 に見える、という食い違いを作らない
  const m = api("main.py");
  expect(m).toMatch(/status_code=status if not ok else 200/);
});
