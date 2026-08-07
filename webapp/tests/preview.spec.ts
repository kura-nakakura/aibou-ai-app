/**
 * 生成アプリのプレビューが「実際に動く」ことの検証.
 *
 * ① アプリ作成の要は、生成したHTMLを iframe の中でそのまま操作できること。
 * そのために iframe には allow-scripts を与え、allow-same-origin は与えない
 * （＝不透明オリジン。親のデータには触れない）。その代償で iframe 内の
 * localStorage が SecurityError を投げるので、lib/preview.ts がメモリ実装を
 * 注入する。ここではその仕組みが本物のブラウザで機能することを確かめる。
 */

import { test, expect } from "@playwright/test";
import { previewDoc, PREVIEW_SANDBOX } from "../src/lib/preview";

/** localStorage を使う最小の「アプリ」。動けば #out に結果が出る。 */
const APP = `<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"><title>メモ</title></head>
<body><h1>メモ</h1><input id="t"><button id="add">追加</button><ul id="list"></ul><p id="out">未実行</p>
<script>
  var KEY = "memo";
  function load() { try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (e) { return []; } }
  function save(v) { localStorage.setItem(KEY, JSON.stringify(v)); }
  function render() {
    var items = load();
    document.getElementById("list").innerHTML = items.map(function (i) { return "<li>" + i + "</li>"; }).join("");
    document.getElementById("out").textContent = "件数:" + items.length;
  }
  document.getElementById("add").addEventListener("click", function () {
    var v = document.getElementById("t").value.trim();
    if (!v) return;
    var items = load(); items.push(v); save(items);
    document.getElementById("t").value = ""; render();
  });
  render();
</script></body></html>`;

/** テスト用に iframe を1つ置いたページを用意する。 */
async function mountPreview(page: import("@playwright/test").Page, html: string) {
  await page.setContent("<!DOCTYPE html><html><body></body></html>");
  await page.evaluate(
    ({ doc, sandbox }) => {
      const f = document.createElement("iframe");
      f.setAttribute("sandbox", sandbox);
      f.setAttribute("title", "preview");
      f.style.width = "600px";
      f.style.height = "400px";
      f.srcdoc = doc;
      document.body.appendChild(f);
    },
    { doc: previewDoc(html), sandbox: PREVIEW_SANDBOX },
  );
  return page.frameLocator("iframe");
}

test("preview runs the generated app's JavaScript", async ({ page }) => {
  const frame = await mountPreview(page, APP);
  // render() が走っていれば「未実行」ではなくなる
  await expect(frame.locator("#out")).toHaveText("件数:0", { timeout: 5_000 });
});

test("preview supports add → list → count without a real localStorage", async ({ page }) => {
  const frame = await mountPreview(page, APP);
  await expect(frame.locator("#out")).toHaveText("件数:0", { timeout: 5_000 });
  await frame.locator("#t").fill("牛乳を買う");
  await frame.locator("#add").click();
  await expect(frame.locator("#list li")).toHaveCount(1);
  await expect(frame.locator("#out")).toHaveText("件数:1");
  await frame.locator("#t").fill("郵便を出す");
  await frame.locator("#add").click();
  await expect(frame.locator("#out")).toHaveText("件数:2");
});

test("preview allows form submit handlers (the most common app pattern)", async ({ page }) => {
  // allow-forms が無いとブラウザが submit を握り潰し、onsubmit が呼ばれない。
  const frame = await mountPreview(
    page,
    `<!DOCTYPE html><html><head><meta charset="utf-8"><title>t</title></head><body>
     <form id="f"><input id="v" value="牛乳"><button type="submit">追加</button></form>
     <ul id="list"></ul><p id="out">未送信</p>
     <script>
       document.getElementById("f").addEventListener("submit", function (e) {
         e.preventDefault();
         var li = document.createElement("li");
         li.textContent = document.getElementById("v").value;
         document.getElementById("list").appendChild(li);
         document.getElementById("out").textContent = "件数:" + document.querySelectorAll("#list li").length;
       });
     </script></body></html>`,
  );
  await frame.locator('button[type="submit"]').click();
  await expect(frame.locator("#out")).toHaveText("件数:1", { timeout: 5_000 });
  await expect(frame.locator("#list li")).toHaveCount(1);
});

test("preview cannot reach the parent page (no allow-same-origin)", async ({ page }) => {
  const frame = await mountPreview(
    page,
    `<!DOCTYPE html><html><head><meta charset="utf-8"><title>t</title></head><body><p id="out">?</p>
     <script>
       var r;
       try { r = parent.document ? "LEAK" : "blocked"; } catch (e) { r = "blocked"; }
       document.getElementById("out").textContent = r;
     </script></body></html>`,
  );
  await expect(frame.locator("#out")).toHaveText("blocked", { timeout: 5_000 });
});

test("preview injection keeps the document's own head content", async ({ page }) => {
  const frame = await mountPreview(
    page,
    `<!DOCTYPE html><html><head><meta charset="utf-8"><title>t</title>
     <style>#out{color:rgb(0,128,0)}</style></head><body><p id="out">緑</p></body></html>`,
  );
  await expect(frame.locator("#out")).toHaveCSS("color", "rgb(0, 128, 0)");
});

test("previewDoc leaves the original HTML untouched", () => {
  const out = previewDoc(APP);
  expect(out).toContain("Content-Security-Policy");
  expect(out).toContain('<h1>メモ</h1>');   // 本文はそのまま
  expect(previewDoc("")).toBe("");
  // <head> が無くても壊れない
  expect(previewDoc("<html><body>x</body></html>")).toContain("Content-Security-Policy");
  expect(previewDoc("<p>x</p>")).toContain("<p>x</p>");
});
