/**
 * 読み上げテキストの整形の検証。
 *
 * 確かめたいのは「コアが記号を口に出さないこと」。実際にこのアプリの返答へ
 * 出てくる形（Markdown・矢印・絵文字・URL・表・コード）を通して、声にした
 * ときに変にならないかを見る。
 */

import { test, expect } from "@playwright/test";
import { speakableText, splitForSpeech, takeCompleteSentences } from "../src/lib/speech";

/** 読み上げてはいけない記号が1つも残っていないこと。 */
function expectNoSymbols(s: string) {
  expect(s).not.toMatch(/[*_#`|~><\\]/);
  expect(s).not.toMatch(/https?:\/\//);
  expect(s).not.toMatch(/\p{Extended_Pictographic}/u);
}

/* ── 記号を読ませない ─────────────────────────────────────────────── */
test("強調・見出し・箇条書きの記号は落ちて、中身だけ残る", () => {
  const out = speakableText("## 今日の予定\n\n- **10時** に会議\n- *歯医者* は15時\n");
  expect(out).toContain("今日の予定");
  expect(out).toContain("10時");
  expect(out).toContain("歯医者");
  expectNoSymbols(out);
});

test("絵文字は読み上げない", () => {
  const out = speakableText("完了しました 🎉👍 お疲れさまです😀");
  expect(out).toContain("完了しました");
  expect(out).toContain("お疲れさまです");
  expectNoSymbols(out);
});

test("URLとメールアドレスは読み上げない", () => {
  const out = speakableText("詳しくは https://example.com/a/b を見てください。連絡は a.b@example.com です。");
  expect(out).toContain("詳しくは");
  expect(out).toContain("見てください");
  expect(out).not.toContain("example.com");
  expectNoSymbols(out);
});

test("リンクは表示している文字だけ読む", () => {
  const out = speakableText("[議事録](https://example.com/doc) を確認してください。");
  expect(out).toContain("議事録");
  expect(out).not.toContain("example.com");
});

test("コードブロックは読まずに、存在だけ伝える", () => {
  const out = speakableText("こう書きます。\n```python\nprint('hello')\n```\n以上です。");
  expect(out).toContain("こう書きます");
  expect(out).toContain("以上です");
  expect(out).not.toContain("print");
  expectNoSymbols(out);
});

test("受信途中で閉じていないコードブロックも読み上げない", () => {
  // ストリーミング中は ``` が片方しか来ていない瞬間がある
  const out = speakableText("手順です。\n```bash\nnpm ru");
  expect(out).toContain("手順です");
  expect(out).not.toContain("npm");
});

test("アプリで使っている飾り記号（⚠ ◈ ▸ など）は読み上げない", () => {
  const out = speakableText("⚠ 接続できません ◈ 再試行 ▸ 設定を確認");
  expect(out).toContain("接続できません");
  expect(out).toContain("設定を確認");
  expectNoSymbols(out);
});

test("表は縦棒ではなく区切りとして読む", () => {
  const out = speakableText("| 項目 | 金額 |\n|---|---|\n| 交通費 | 1200円 |");
  expect(out).toContain("交通費");
  expect(out).toContain("1200円");
  expectNoSymbols(out);
});

/* ── 記号でも、消すと意味が変わるものは残す ───────────────────────── */
test("矢印は読点になって流れが残る", () => {
  const out = speakableText("計画→実行→確認 を繰り返します。");
  expect(out).toContain("計画、実行、確認");
  expect(out).not.toContain("→");
});

test("中黒とスラッシュは読点になる", () => {
  expect(speakableText("資料・スライド・画像")).toBe("資料、スライド、画像");
  expect(speakableText("LP/HP を作る")).toContain("LP、HP");
});

test("数字の範囲は「から」と読む", () => {
  expect(speakableText("10-20分ほどかかります。")).toContain("10から20分");
});

test("読点が連続しない", () => {
  const out = speakableText("A・→・B");
  expect(out).not.toMatch(/、、/);
});

/* ── 文の分け方 ───────────────────────────────────────────────────── */
test("文末で分かれる", () => {
  expect(splitForSpeech("はい、承知しました。明日15時ですね。登録しました。"))
    .toEqual(["はい、承知しました。", "明日15時ですね。", "登録しました。"]);
});

test("長すぎる文は読点で折る（音声合成が途中で切れるのを防ぐ）", () => {
  const long = `${"あ".repeat(60)}、${"い".repeat(60)}、${"う".repeat(60)}。`;
  const parts = splitForSpeech(long, 80);
  expect(parts.length).toBeGreaterThan(1);
  for (const p of parts) expect(p.length).toBeLessThanOrEqual(80);
  // 分けても中身は失われない
  expect(parts.join("")).toBe(long);
});

test("短すぎる断片は前にくっつけて、ぶつ切りにしない", () => {
  const parts = splitForSpeech("はい。承知しました。");
  expect(parts).toEqual(["はい。承知しました。"]);
});

test("空文字は何も返さない", () => {
  expect(splitForSpeech("")).toEqual([]);
  expect(splitForSpeech("   ")).toEqual([]);
  expect(speakableText("")).toBe("");
});

/* ── 受信途中から喋り始める ───────────────────────────────────────── */
test("言い切った文だけを取り出し、書きかけの末尾は残す", () => {
  const r = takeCompleteSentences("承知しました。明日の15時ですね。いま登録して");
  expect(r.chunks).toEqual(["承知しました。", "明日の15時ですね。"]);
  // 「いま登録して」はまだ渡さない
  expect("承知しました。明日の15時ですね。いま登録して".slice(r.consumed)).toBe("いま登録して");
});

test("まだ1文も終わっていなければ何も喋らない", () => {
  const r = takeCompleteSentences("承知しま");
  expect(r.chunks).toEqual([]);
  expect(r.consumed).toBe(0);
});

test("受信を続けても、同じ文を二度読まない", () => {
  // ストリーミングを模して、少しずつ増やしながら消費位置を進める
  const full = "了解です。まず予定を確認します。次にタスクを登録します。";
  let spokenUpTo = 0;
  const said: string[] = [];
  for (let i = 1; i <= full.length; i++) {
    const r = takeCompleteSentences(full.slice(spokenUpTo, i));
    if (r.chunks.length) {
      said.push(...r.chunks);
      spokenUpTo += r.consumed;
    }
  }
  expect(said).toEqual(["了解です。", "まず予定を確認します。", "次にタスクを登録します。"]);
  expect(said.join("")).toBe(full);
});

test("コードブロックの案内を二度言わない", () => {
  // 実際に踏んだ不具合。``` が届いた時点と閉じた時点で2回喋っていた。
  const tokens = ["説明します。", "\n", "```js\nconsole.log(1)\n```", "\n", "以上です。"];
  let acc = "";
  let spokenUpTo = 0;
  const said: string[] = [];
  for (const t of tokens) {
    acc += t;
    const r = takeCompleteSentences(acc.slice(spokenUpTo));
    if (r.consumed) { spokenUpTo += r.consumed; said.push(...r.chunks); }
  }
  const guides = said.filter((s) => s.includes("コードは画面"));
  expect(guides).toHaveLength(1);
  expect(said.join(" ")).toContain("説明します。");
  expect(said.join(" ")).toContain("以上です。");
  expect(said.join(" ")).not.toContain("console");
});

test("コードブロックの途中では喋り出さない", () => {
  // 閉じるまでは、その手前までしか読まない
  const r = takeCompleteSentences("手順です。\n```bash\nnpm run build\n");
  expect(r.chunks).toEqual(["手順です。"]);
});

test("句読点の前に余白を残さない", () => {
  // 絵文字を消した跡が「ました 。」のように残らないこと
  expect(speakableText("完了しました 🎉。")).toBe("完了しました。");
});

test("記号だらけの返答でも、読める文だけが渡る", () => {
  const reply = "**完了** しました 🎉\n\n- 詳細は [ここ](https://x.test/a)\n- 次は `npm run build` です。";
  const r = takeCompleteSentences(reply);
  const joined = r.chunks.join(" ");
  expect(joined).toContain("完了");
  expectNoSymbols(joined);
});
