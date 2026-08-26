/**
 * 「入れたはずの鍵が、更新したら未設定に戻る」の見張り。
 *
 * 報告: GitHubのトークンを入れたのに、アップデートを重ねたら入っていないことに
 * なっていた。原因は2つとも「保存できていないのに保存したと言う」形だった。
 *
 *   1. サーバー側が upsert の失敗を握りつぶし、DBが無い構成では
 *      プロセスのメモリにしか書かないのに「保存しました」と返していた。
 *      Renderが再起動するたび（＝アプリを更新するたび）に消える。
 *
 *   2. 利用者ごとにDBを分ける前、鍵はサーバー既定のDBに入っていた。
 *      あとから自分のDBを繋ぐと読む先が変わるので、前に入れた鍵が
 *      「未設定」に見える。消えたのではなく、前の場所に残っている。
 *
 * 画面がここを黙って通すと、また同じことが起きる。だから
 * 「本当に残ったか」を受け取って、残らないなら残らないと出すことを固定する。
 */

import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const src = (p: string) => readFileSync(join(process.cwd(), "src", p), "utf8");

test("鍵の保存は「本当に残ったか」を返す", () => {
  const api = src("lib/api.ts");
  expect(api).toContain("persisted");
  // 既定を true に倒すと、古いサーバーに繋いだとき警告が出っぱなしになる
  expect(api).toContain("data.persisted !== false");
});

test("残らなかったときは「保存しました」と言わない", () => {
  const ext = src("components/Extensions.tsx");
  // 戻り値を捨てていたら、また黙って消える
  expect(ext).toContain("r.persisted");
  expect(ext).toContain("warnings.push");
  // 成功メッセージは、警告が無いときだけ
  expect(ext).toMatch(/warnings\.length > 0[\s\S]{0,160}保存しました/);
});

test("鍵がどこに入っているかを画面に出す", () => {
  const ext = src("components/Extensions.tsx");
  expect(ext).toContain("WhereBadge");
  // 3つの状態を出し分ける。「設定済み」だけでは消えるものと残るものが同じに見える
  expect(ext).toContain("保存済み");
  expect(ext).toContain("サーバー設定");
  expect(ext).toContain("一時・更新で消えます");
});

test("更新で消える鍵は、消える前にまとめて知らせる", () => {
  const ext = src("components/Extensions.tsx");
  expect(ext).toContain('k.where === "memory"');
  expect(ext).toMatch(/アプリを更新すると消えます/);
});

test("消える鍵を「✓ 連携できています」と言わない", () => {
  // 緑で「できています」と出しながら下の欄に「消えます」と書くと、
  // どちらを信じればいいか分からない。残らないなら、そう出す。
  const ext = src("components/Extensions.tsx");
  expect(ext).toContain("const fragile =");
  // 緑の「✓ 連携できています」は fragile の三項の外れ側にしか無いこと
  expect(ext).toMatch(/fragile \?[\s\S]*?✓ 連携できています/);
  expect(ext).toContain("いまは使えますが、この鍵は保存先に残っていません");
});

test("前の保存先に残った鍵を取り込める", () => {
  const api = src("lib/api.ts");
  expect(api).toContain("keyOrphans");
  expect(api).toContain("keyRescue");
  // 持ち主でなければ 403 が返る。そこで例外を投げると画面ごと落ちる
  expect(api).toMatch(/keys\/orphans[\s\S]{0,220}if \(!res\.ok\) return \{ available: false/);

  const ext = src("components/Extensions.tsx");
  expect(ext).toContain("RescueBanner");
  expect(ext).toContain("keyRescue");
  // 取り込んだら読み直す（取り込んだのに未設定のまま見えると意味がない）
  expect(ext).toContain("onDone");
});

test("取り残しの一覧に鍵の値そのものを載せない", () => {
  const api = src("lib/api.ts");
  // OrphanKey は名前とマスクだけ。value を持たせると画面に平文が出る
  const m = api.match(/export interface OrphanKey \{[\s\S]*?\}/);
  expect(m, "OrphanKey の定義が見つからない").toBeTruthy();
  expect(m![0]).toContain("masked");
  expect(m![0]).not.toContain("value");
});
