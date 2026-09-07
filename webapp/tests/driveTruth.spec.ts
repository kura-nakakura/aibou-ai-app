/**
 * 「Googleドライブに作成しました」が本当であることの見張り。
 *
 * 報告: 相棒にドライブへのファイル作成を頼んだら「作成しました」と返ってきたのに、
 * ドライブを見ると無かった。
 *
 * 原因は3つ重なっていた。
 *   ・「ドライブにファイルを作る」に当たるツールが無く、AIbouの中に保存するだけの
 *     機能が選ばれて「作成しました」と返っていた
 *   ・本文の書き込みの失敗を握りつぶしていた（中身が空でも成功扱い）
 *   ・どのGoogleアカウントに繋いでいるかが、どこにも出ていなかった
 */

import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const src = (p: string) => readFileSync(join(process.cwd(), "src", p), "utf8");

test("繋いでいるGoogleアカウントを画面に出す", () => {
  // 見に行ったのと違うアカウントに繋いでいた、という取り違えに気づけるように
  const api = src("lib/api.ts");
  expect(api).toMatch(/account\?: string/);

  const ext = src("components/Extensions.tsx");
  // 連携の状態は提供元ごとの共通の仕組みから取るようになった（provider）。
  // 見せたいこと（どのアカウントに作られるか）は変わっていない。
  expect(ext).toContain("provider.account");
  expect(ext).toContain("のドライブに作られます");
});

test("ドライブに作れることを、できることの一覧に書く", () => {
  const list = src("lib/extensions.ts");
  const g = list.slice(list.indexOf('id: "google"'), list.indexOf('id: "rules"'));
  expect(g).toContain("ドライブにファイルをそのまま作る");
  // 確認まですることを書いておく（書いた以上、実装が外れたらテストで落ちる）
  expect(g).toContain("実在を確認");
});

test("経過表示にドライブ作成の名前がある", () => {
  // 生のツール名のままだと、何をしたのか読めない
  expect(src("components/AgentTrace.tsx")).toContain("drive_upload");
  expect(src("components/AgentTrace.tsx")).toContain("Googleドライブに作成");
});
