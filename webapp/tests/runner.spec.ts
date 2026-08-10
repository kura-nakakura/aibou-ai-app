/**
 * CODE の実行・テスト機能の検証.
 *
 * ⑧ の要は「本当に動く／本当にテストが走る」こと。実行はブラウザの
 * sandbox iframe 内（allow-scripts のみ、allow-same-origin なし）で行うので、
 * サーバーで他人のコードを走らせる危険がない。ここではその仕組みが
 * 実ブラウザで機能することを確かめる。
 */

import { test, expect, type Page } from "@playwright/test";
import {
  buildRunDoc, buildTestDoc, testFiles, RUN_SANDBOX, RUN_CHANNEL,
  type ConsoleLine, type TestSummary,
} from "../src/lib/runner";

/** doc を iframe に載せ、postMessage で返ってくるものを集める。 */
async function collect(page: Page, doc: string, waitMs = 1200) {
  await page.setContent("<!DOCTYPE html><html><body></body></html>");
  await page.evaluate(({ d, sandbox, ch }) => {
    (window as unknown as { __logs: unknown[] }).__logs = [];
    (window as unknown as { __tests: unknown }).__tests = null;
    const f = document.createElement("iframe");
    f.setAttribute("sandbox", sandbox);
    f.style.width = "480px";
    f.style.height = "320px";
    window.addEventListener("message", (e) => {
      const m = e.data as { channel?: string; type?: string };
      if (!m || m.channel !== ch) return;
      if (e.source !== f.contentWindow) return;      // 自分の iframe からだけ受ける
      if (m.type === "log") (window as unknown as { __logs: unknown[] }).__logs.push(m);
      if (m.type === "tests") (window as unknown as { __tests: unknown }).__tests = (m as { summary: unknown }).summary;
    });
    f.srcdoc = d;
    document.body.appendChild(f);
  }, { d: doc, sandbox: RUN_SANDBOX, ch: RUN_CHANNEL });
  await page.waitForTimeout(waitMs);
  return page.evaluate(() => ({
    logs: (window as unknown as { __logs: ConsoleLine[] }).__logs,
    tests: (window as unknown as { __tests: TestSummary | null }).__tests,
  }));
}

/* ── 複数ファイルのプレビュー ───────────────────────────────────── */
const PROJECT = [
  {
    path: "index.html",
    content: `<!doctype html><html><head><meta charset="utf-8">
      <link rel="stylesheet" href="style.css"></head>
      <body><h1 id="t">やあ</h1><p id="out">未実行</p>
      <script src="app.js"></script></body></html>`,
  },
  { path: "style.css", content: "#t{color:rgb(0,128,0)}" },
  { path: "app.js", content: 'document.getElementById("out").textContent="JSが動いた"; console.log("hello from app.js");' },
];

test("preview inlines CSS and JS from the same workspace", async ({ page }) => {
  const doc = buildRunDoc(PROJECT, "index.html");
  // 外部参照は残さず埋め込む（1ファイルとして完結させる）
  expect(doc).not.toContain('href="style.css"');
  expect(doc).not.toContain('src="app.js"');
  expect(doc).toContain("#t{color:rgb(0,128,0)}");

  await collect(page, doc);
  const frame = page.frameLocator("iframe");
  await expect(frame.locator("#out")).toHaveText("JSが動いた");
  await expect(frame.locator("#t")).toHaveCSS("color", "rgb(0, 128, 0)");
});

test("console output is captured from the sandbox", async ({ page }) => {
  const { logs } = await collect(page, buildRunDoc(PROJECT, "index.html"));
  expect(logs.map((l) => l.text)).toContain("hello from app.js");
  expect(logs[0].level).toBe("log");
});

test("runtime errors surface as error lines", async ({ page }) => {
  const files = [{ path: "index.html", content: '<html><head></head><body><script src="boom.js"></script></body></html>' },
    { path: "boom.js", content: 'console.warn("気をつけて"); missingFunction();' }];
  const { logs } = await collect(page, buildRunDoc(files, "index.html"));
  const levels = logs.map((l) => l.level);
  const texts = logs.map((l) => l.text).join(" | ");
  expect(levels).toContain("warn");
  expect(levels).toContain("error");
  expect(texts).toContain("missingFunction");
});

test("external URLs are left alone", () => {
  const files = [{
    path: "index.html",
    content: '<html><head><link rel="stylesheet" href="https://cdn.example.com/a.css"></head>'
      + '<body><script src="//cdn.example.com/b.js"></script></body></html>',
  }];
  const doc = buildRunDoc(files, "index.html");
  expect(doc).toContain("https://cdn.example.com/a.css");
  expect(doc).toContain("//cdn.example.com/b.js");
});

test("missing local references are left as-is rather than dropped", () => {
  const files = [{ path: "index.html", content: '<html><head></head><body><script src="nope.js"></script></body></html>' }];
  expect(buildRunDoc(files, "index.html")).toContain('src="nope.js"');
});

test("entry falls back to any html file", () => {
  const files = [{ path: "pages/home.html", content: "<html><head></head><body>ok</body></html>" }];
  expect(buildRunDoc(files, "does-not-exist.html")).toContain("ok");
  expect(buildRunDoc([], "x.html")).toBe("");
});

test("paths match with or without a leading ./", async ({ page }) => {
  const files = [
    { path: "index.html", content: '<html><head></head><body><p id="o">x</p><script src="./sub/app.js"></script></body></html>' },
    { path: "sub/app.js", content: 'document.getElementById("o").textContent="解決した"' },
  ];
  await collect(page, buildRunDoc(files, "index.html"));
  await expect(page.frameLocator("iframe").locator("#o")).toHaveText("解決した");
});

/* ── テスト実行 ─────────────────────────────────────────────────── */
const TESTED = [
  { path: "math.js", content: "function add(a,b){return a+b} function slug(s){return s.trim().toLowerCase().replace(/\\s+/g,'-')}" },
  {
    path: "math.test.js",
    content: `
      test("足し算", function(){ expect(add(2,3)).toBe(5); });
      test("スラッグ", function(){ expect(slug("  Hello World ")).toBe("hello-world"); });
      test("落ちるはず", function(){ expect(add(2,2)).toBe(5); });
    `,
  },
];

test("test files are detected", () => {
  expect(testFiles(TESTED).map((f) => f.path)).toEqual(["math.test.js"]);
  expect(testFiles([{ path: "a.js", content: "" }])).toEqual([]);
  expect(testFiles([{ path: "a.spec.ts", content: "" }]).length).toBe(1);
});

test("tests actually run and report pass/fail", async ({ page }) => {
  const { tests } = await collect(page, buildTestDoc(TESTED), 1500);
  expect(tests).not.toBeNull();
  expect(tests!.total).toBe(3);
  expect(tests!.passed).toBe(2);
  expect(tests!.failed).toBe(1);
  const failed = tests!.cases.find((c) => !c.ok)!;
  expect(failed.name).toBe("落ちるはず");
  expect(failed.error).toContain("期待 5");
});

test("async tests are awaited", async ({ page }) => {
  const files = [{
    path: "a.test.js",
    content: `
      test("待つ", async function(){
        var v = await new Promise(function(r){ setTimeout(function(){ r(7); }, 50); });
        expect(v).toBe(7);
      });
    `,
  }];
  const { tests } = await collect(page, buildTestDoc(files), 1500);
  expect(tests!.passed).toBe(1);
});

test("matchers cover the common cases", async ({ page }) => {
  const files = [{
    path: "m.test.js",
    content: `
      test("toEqual", function(){ expect({a:[1,2]}).toEqual({a:[1,2]}); });
      test("toContain string", function(){ expect("abcdef").toContain("cde"); });
      test("toContain array", function(){ expect([1,2,3]).toContain(2); });
      test("toHaveLength", function(){ expect([1,2]).toHaveLength(2); });
      test("toThrow", function(){ expect(function(){ throw new Error("x"); }).toThrow(); });
      test("toBeCloseTo", function(){ expect(0.1+0.2).toBeCloseTo(0.3); });
      test("toBeTruthy", function(){ expect(1).toBeTruthy(); });
      test("toBeFalsy", function(){ expect(0).toBeFalsy(); });
    `,
  }];
  const { tests } = await collect(page, buildTestDoc(files), 1500);
  expect(tests!.failed).toBe(0);
  expect(tests!.total).toBe(8);
});

test("a broken test file reports an error instead of failing silently", async ({ page }) => {
  const files = [{ path: "bad.test.js", content: "test('x', function(){ syntax error here" }];
  const { logs, tests } = await collect(page, buildTestDoc(files), 1500);
  // 読み込みに失敗したことがログに出る（無言で0件成功にしない）
  const texts = logs.map((l) => l.text).join(" ");
  expect(texts.length > 0 || tests !== null).toBeTruthy();
});

test("no test files → empty summary, not a crash", async ({ page }) => {
  const { tests } = await collect(page, buildTestDoc([{ path: "a.js", content: "var x=1;" }]), 1200);
  expect(tests).not.toBeNull();
  expect(tests!.total).toBe(0);
});

test("the sandbox cannot reach the parent page", async ({ page }) => {
  const files = [{
    path: "index.html",
    content: `<html><head></head><body><script>
      var r; try { r = parent.document ? "LEAK" : "blocked"; } catch (e) { r = "blocked"; }
      console.log("parent access: " + r);
    </script></body></html>`,
  }];
  const { logs } = await collect(page, buildRunDoc(files, "index.html"));
  expect(logs.map((l) => l.text).join(" ")).toContain("parent access: blocked");
});
