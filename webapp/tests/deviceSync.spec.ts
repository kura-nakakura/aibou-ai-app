/**
 * 「端末を変えたら消える」が残っていないかの見張り。
 *
 * 調べて分かったこと: 会話履歴も、作ったアプリも、ブラウザの localStorage に
 * しか無かった。スマホで作ったものがPCで見えず、ブラウザのデータを消すと
 * 全部消える。規約には「あなたのSupabaseに保存されます」と書いてあったので、
 * 会話については実装のほうが嘘をついていた。
 *
 * 手元の控えは残してよい（オフラインでも読める）。ただし control は
 * 自分のDBであるべきで、書くだけでなく読み戻せないと片道になる。
 */

import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const src = (p: string) => readFileSync(join(process.cwd(), "src", p), "utf8");
const schema = () => readFileSync(join(process.cwd(), "public", "supabase_schema.sql"), "utf8");

test("会話履歴は自分のDBにも保存される", () => {
  const chat = src("components/Chat.tsx");
  expect(chat).toContain("conversationSave");
  expect(chat).toContain("conversationsList");
  // 読み戻せないと片道になる（他の端末で作った会話が開けない）
  expect(chat).toContain("conversationGet");
  // 削除も効かせないと、消したはずの会話が別の端末で生き返る
  expect(chat).toContain("conversationDelete");
});

test("会話の表がスキーマにある", () => {
  // 配るSQLに無いと、説明どおりにやってもテーブルが足りない
  expect(schema()).toContain("CREATE TABLE IF NOT EXISTS conversations");
  expect(schema()).toContain("messages   jsonb");
});

test("手元の控えは残してある（オフラインでも読める）", () => {
  const chat = src("components/Chat.tsx");
  expect(chat).toContain("forge_chat_convos");
  expect(chat).toContain("loadConvos");
});

test("作ったアプリも自分のDBに残る", () => {
  const a = src("components/AppArchive.tsx");
  expect(a).toContain("artifactCreate");
  expect(a).toContain("artifactsList");
  expect(a).toContain("artifactGet");     // 他の端末の分を開ける
  expect(a).toContain("artifactDelete");
});

test("保管庫は新しい表を作らず、生成物と同じ場所を使う", () => {
  const a = src("components/AppArchive.tsx");
  // 「作ったもの」の置き場が2つあると、どちらを見ればいいか分からなくなる
  expect(a).toContain("artifacts");
  expect(a).not.toContain("forge_apps");
});

test("本文は開いたときに取りに行く（一覧で全部読まない）", () => {
  // 一覧で本文まで返すと、増えるほど開くのが遅くなる
  const a = src("components/AppArchive.tsx");
  expect(a).toContain("fetchCode");
  expect(a).toMatch(/code: "",\s*\/\//);   // 一覧の時点では空
  const chat = src("components/Chat.tsx");
  expect(chat).toMatch(/messages: \[\],\s*\/\//);
});

test("保存に失敗しても、その場の作業は止めない", () => {
  // 会話の途中で保存が転んだからといって、会話ができなくなるのは本末転倒。
  // 保存先が無いことは他の画面が理由つきで教える。
  const chat = src("components/Chat.tsx");
  expect(chat).toMatch(/conversationSave\([\s\S]*?\)\.catch\(\(\) => \{\}\)/);
});
