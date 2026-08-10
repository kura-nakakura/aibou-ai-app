/**
 * runner.ts — ワークスペースのコードを「本当に動かす」ための組み立て.
 *
 * 実行はブラウザの sandbox iframe 内で行う。サーバー側で任意のコードを
 * 実行させるのは危険（バックエンドは暗号化済みキーチェーンやDBキーを持つ
 * プロセスなので、そこで他人のコードを走らせるべきではない）。
 * ブラウザなら allow-scripts だけを与えて allow-same-origin を外せるので、
 * 親のDOM・localStorage・Cookieには一切触れられない状態で実行できる。
 *
 *   buildRunDoc(files, entry)  … HTMLに同一ワークスペースのCSS/JSを埋め込む
 *   buildTestDoc(files)        … *.test.js を最小のテストハーネスで実行する
 *
 * どちらも iframe から postMessage でログ／結果を親へ返す。
 */

export interface RunnerFile { path: string; content: string }

/** iframe → 親 のメッセージ。channel で自分宛てだけを拾う。 */
export const RUN_CHANNEL = "forge-run";

export interface ConsoleLine {
  level: "log" | "info" | "warn" | "error";
  text: string;
}

export interface TestCase { name: string; ok: boolean; error?: string; ms: number }
export interface TestSummary { total: number; passed: number; failed: number; cases: TestCase[] }

const esc = (s: string) => s.replace(/<\/script/gi, "<\\/script");

/** 親へログを送る橋渡し。console と未捕捉エラーを拾う。 */
const CONSOLE_BRIDGE = `<script>(function(){
  var CH = ${JSON.stringify(RUN_CHANNEL)};
  function send(m){ try { parent.postMessage(Object.assign({channel:CH}, m), "*"); } catch(e){} }
  function str(v){
    if (typeof v === "string") return v;
    if (v instanceof Error) return v.stack || (v.name + ": " + v.message);
    try { return JSON.stringify(v, function(k, x){ return typeof x === "function" ? "[Function]" : x; }, 2); }
    catch(e){ return String(v); }
  }
  ["log","info","warn","error"].forEach(function(level){
    var orig = console[level] ? console[level].bind(console) : function(){};
    console[level] = function(){
      var args = Array.prototype.slice.call(arguments).map(str).join(" ");
      send({type:"log", level: level, text: args});
      orig.apply(null, arguments);
    };
  });
  window.addEventListener("error", function(e){
    send({type:"log", level:"error", text: (e.message || "エラー") + (e.lineno ? " (" + e.lineno + "行)" : "")});
  });
  window.addEventListener("unhandledrejection", function(e){
    send({type:"log", level:"error", text: "未処理のPromise: " + str(e.reason)});
  });
})();</script>`;

/** localStorage が使えない不透明オリジンでメモリ実装に差し替える（lib/preview と同じ理屈）。 */
const STORAGE_SHIM = `<script>(function(){function mem(){var m=Object.create(null);return{getItem:function(k){k=String(k);return k in m?m[k]:null},setItem:function(k,v){m[String(k)]=String(v)},removeItem:function(k){delete m[String(k)]},clear:function(){m=Object.create(null)},key:function(i){var s=Object.keys(m);return i<s.length?s[i]:null},get length(){return Object.keys(m).length}}}
["localStorage","sessionStorage"].forEach(function(n){var ok=false;try{window[n].setItem("__p__","1");window[n].removeItem("__p__");ok=true}catch(e){}
if(!ok){try{Object.defineProperty(window,n,{value:mem(),configurable:true,writable:true})}catch(e){}}});})();</script>`;

/** パスを正規化して「./a.js」「/a.js」「a.js」を同じものとして扱う。 */
function norm(p: string): string {
  return (p || "").replace(/^\.?\//, "").replace(/^\/+/, "").trim();
}

function findFile(files: RunnerFile[], ref: string): RunnerFile | undefined {
  const want = norm(ref).split(/[?#]/)[0];
  if (!want) return undefined;
  return files.find((f) => norm(f.path) === want)
    // ディレクトリ付きで書かれていても末尾一致で拾う（src/app.js ↔ app.js）
    || files.find((f) => norm(f.path).endsWith(`/${want}`));
}

/**
 * HTMLを実行用に組み立てる。
 *
 * 同じワークスペースの CSS/JS を <link>/<script src> から解決して埋め込む。
 * これが無いと、複数ファイルに分けたプロジェクトのプレビューが
 * スタイルもJSも当たらない“素のHTML”になってしまう。
 */
export function buildRunDoc(files: RunnerFile[], entryPath: string): string {
  const entry = findFile(files, entryPath) ?? files.find((f) => /\.html?$/i.test(f.path));
  if (!entry) return "";
  let html = entry.content || "";

  // <link rel="stylesheet" href="style.css"> → <style>…</style>
  html = html.replace(/<link\b[^>]*href\s*=\s*["']([^"']+)["'][^>]*>/gi, (tag, href) => {
    if (!/stylesheet/i.test(tag) && !/\.css(\?|#|$)/i.test(href)) return tag;
    if (/^(https?:)?\/\//i.test(href) || href.startsWith("data:")) return tag;
    const f = findFile(files, href);
    return f ? `<style>\n${f.content}\n</style>` : tag;
  });

  // <script src="app.js"></script> → <script>…</script>
  html = html.replace(/<script\b([^>]*)\bsrc\s*=\s*["']([^"']+)["']([^>]*)>\s*<\/script>/gi,
    (tag, pre, src, post) => {
      if (/^(https?:)?\/\//i.test(src) || src.startsWith("data:")) return tag;
      const f = findFile(files, src);
      if (!f) return tag;
      const isModule = /type\s*=\s*["']module["']/i.test(`${pre} ${post}`);
      return `<script${isModule ? ' type="module"' : ""}>\n${esc(f.content)}\n</script>`;
    });

  const inject = STORAGE_SHIM + CONSOLE_BRIDGE;
  const head = /<head[^>]*>/i.exec(html);
  if (head) {
    const at = head.index + head[0].length;
    return html.slice(0, at) + inject + html.slice(at);
  }
  const htmlTag = /<html[^>]*>/i.exec(html);
  if (htmlTag) {
    const at = htmlTag.index + htmlTag[0].length;
    return html.slice(0, at) + inject + html.slice(at);
  }
  return inject + html;
}

/** テスト対象になるファイル（*.test.js / *.spec.js）。 */
export function testFiles(files: RunnerFile[]): RunnerFile[] {
  return files.filter((f) => /\.(test|spec)\.[jt]sx?$/i.test(f.path));
}

/** テストから import される可能性のあるソース（テスト以外の js）。 */
function sourceFiles(files: RunnerFile[]): RunnerFile[] {
  return files.filter((f) => /\.[jt]sx?$/i.test(f.path) && !/\.(test|spec)\.[jt]sx?$/i.test(f.path));
}

/**
 * *.test.js を実行するドキュメントを組み立てる。
 *
 * 外部のテストランナーは読み込めない（1ファイル完結・外部通信なしで動かす）ので、
 * test() / expect() だけの最小ハーネスを同梱する。ソースは同じスコープに
 * 先に読み込むので、モジュール構文なしで関数を参照できる。
 */
export function buildTestDoc(files: RunnerFile[]): string {
  const tests = testFiles(files);
  const sources = sourceFiles(files);

  const harness = `
var __results = [], __queue = [];
function test(name, fn){ __queue.push({name: name, fn: fn}); }
var it = test;
function describe(name, fn){ fn(); }
function expect(actual){
  function eq(a, b){
    if (a === b) return true;
    if (typeof a !== typeof b) return false;
    if (a && b && typeof a === "object") {
      try { return JSON.stringify(a) === JSON.stringify(b); } catch (e) { return false; }
    }
    return Number.isNaN(a) && Number.isNaN(b);
  }
  function show(v){ try { return typeof v === "string" ? JSON.stringify(v) : JSON.stringify(v); } catch(e){ return String(v); } }
  return {
    toBe: function(e){ if (actual !== e) throw new Error("期待 " + show(e) + " / 実際 " + show(actual)); },
    toEqual: function(e){ if (!eq(actual, e)) throw new Error("期待 " + show(e) + " / 実際 " + show(actual)); },
    toBeTruthy: function(){ if (!actual) throw new Error(show(actual) + " は真ではありません"); },
    toBeFalsy: function(){ if (actual) throw new Error(show(actual) + " は偽ではありません"); },
    toBeNull: function(){ if (actual !== null) throw new Error(show(actual) + " は null ではありません"); },
    toBeCloseTo: function(e, d){ var p = Math.pow(10, -(d === undefined ? 2 : d)) / 2;
      if (Math.abs(actual - e) > p) throw new Error("期待 " + show(e) + " に近い値 / 実際 " + show(actual)); },
    toContain: function(e){
      var ok = typeof actual === "string" ? actual.indexOf(e) !== -1
        : Array.isArray(actual) ? actual.some(function(x){ return eq(x, e); }) : false;
      if (!ok) throw new Error(show(actual) + " は " + show(e) + " を含みません"); },
    toHaveLength: function(n){ if (!actual || actual.length !== n)
      throw new Error("長さ " + n + " を期待 / 実際 " + (actual ? actual.length : "なし")); },
    toThrow: function(){
      var threw = false;
      try { actual(); } catch (e) { threw = true; }
      if (!threw) throw new Error("例外が投げられませんでした"); },
  };
}
async function __run(){
  for (var i = 0; i < __queue.length; i++) {
    var t = __queue[i], t0 = Date.now();
    try { await t.fn(); __results.push({name: t.name, ok: true, ms: Date.now() - t0}); }
    catch (e) { __results.push({name: t.name, ok: false, ms: Date.now() - t0,
      error: (e && e.message) ? e.message : String(e)}); }
  }
  var passed = __results.filter(function(r){ return r.ok; }).length;
  parent.postMessage({channel: ${JSON.stringify(RUN_CHANNEL)}, type: "tests",
    summary: {total: __results.length, passed: passed,
              failed: __results.length - passed, cases: __results}}, "*");
}
`;

  const body = tests.length
    ? sources.map((f) => `/* ${f.path} */\n${esc(f.content)}`).join("\n;\n")
      + "\n;\n"
      + tests.map((f) => `/* ${f.path} */\n${esc(f.content)}`).join("\n;\n")
    : "";

  return `<!doctype html><html><head><meta charset="utf-8">${STORAGE_SHIM}${CONSOLE_BRIDGE}</head><body>
<script>
${harness}
try {
${body}
} catch (e) {
  console.error("テストの読み込みに失敗しました: " + ((e && e.message) || e));
}
__run();
</script></body></html>`;
}

/** 実行用 iframe の sandbox 値。allow-same-origin は付けない（親を守るため）。 */
export const RUN_SANDBOX = "allow-scripts allow-forms allow-modals allow-popups";
