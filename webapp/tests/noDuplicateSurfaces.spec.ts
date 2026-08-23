/**
 * 「同じことをする入口が増えていないか」の見張り。
 *
 * 点検で分かったこと: アプリを作る入口が3つあった。
 *   ・STUDIO → FORGE → APP … Streamlit の Python コード。ブラウザでは動かず、
 *                             手元に Python を入れて streamlit run が要る
 *   ・STUDIO → アプリ      … 1ファイルHTML。プレビューでそのまま動く
 *   ・CODE                 … 複数ファイルの開発環境
 * 一番使いにくいものが「APP」という一番わかりやすい名前を占めていた。
 *
 * 入口を1つに絞ったので、また増えたらここで気づけるようにする。
 * 文字列で見張るのは雑に見えるが、UIの重複はテストしにくく、
 * 気づいたときには利用者が迷ったあと、というのが実際に起きたこと。
 */

import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const src = (p: string) => readFileSync(join(process.cwd(), "src", p), "utf8");

test("素材づくりの画面に「アプリ」は無い", () => {
  const forge = src("components/Forge.tsx");
  expect(forge).not.toMatch(/key:\s*"app"/);
  // 既定タブが app に戻ると、消したはずの Streamlit 生成に落ちる
  expect(forge).not.toMatch(/useState<ForgeKind \| "video">\("app"\)/);
});

test("素材づくりの種類は、素材だけ", () => {
  const forge = src("components/Forge.tsx");
  const kinds = [...forge.matchAll(/\{ key: "(\w+)", label:/g)].map((m) => m[1]);
  expect(kinds).toEqual(["image", "slides", "sheet", "doc"]);
});

test("タブ名が「何を作るか」になっている", () => {
  const w = src("components/Workshop.tsx");
  // FORGE のような、初めての人に何が出るか伝わらない名前を表に出さない
  expect(w).toContain("▣ アプリ");
  expect(w).toContain("◫ LP・ホームページ");
  expect(w).toContain("✦ 素材（画像・資料）");
  expect(w).not.toContain('label: "✦ FORGE"');
});

test("アプリを作ったら保管庫に残る", () => {
  // 以前は「アプリ」タブの成果物がどこにも保存されず、
  // ダウンロードしないとタブを閉じた時点で消えていた
  const lp = src("components/LpBuilder.tsx");
  expect(lp).toContain("addToArchive");
  expect(lp).toMatch(/addToArchive\(.*"html"\)/);
});

test("保管庫は HTML と Python の両方を扱える", () => {
  const a = src("components/AppArchive.tsx");
  expect(a).toContain("kindOf");
  expect(a).toContain("openHtml");        // HTMLはその場で開ける
  expect(a).not.toMatch(/Forge で生成したアプリのコードを保管/);
});

test("空のときの案内が、実在するタブを指している", () => {
  const a = src("components/AppArchive.tsx");
  // 「FORGE タブで APP を生成」は、APPを消したあとでは嘘になる
  expect(a).not.toContain("FORGE タブで APP");
  expect(a).toContain("「アプリ」タブ");
});
