/**
 * preview.ts — 生成HTMLを iframe で「実際に動かして」確認するための下ごしらえ.
 *
 * 生成されたアプリは操作できないと意味がない（入力→保存→一覧に出る、が確認したい）。
 * そのため iframe には allow-scripts を与えてJSを動かす。ただし allow-same-origin は
 * 与えない ＝ iframe は不透明オリジンになるので、
 *   ・親（このアプリ）のDOM・localStorage・Cookie には一切触れない
 *   ・代わりに iframe 内の localStorage が SecurityError を投げる
 * という状態になる。後者を埋めるため、メモリ実装の localStorage を注入する。
 *
 * さらに meta CSP で「1ファイル完結・外部通信なし」をブラウザ側でも強制する
 * （生成物が外部へ送信することを構造的に防ぐ）。
 *
 * 注入するのはプレビュー用のコピーだけ。ダウンロード・保存・修正には
 * 元のHTMLをそのまま使うので、成果物にこのコードは混ざらない。
 */

/** 不透明オリジンで localStorage が使えないときに差し替えるメモリ実装＋CSP。 */
const SHIM = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data: blob:; media-src data: blob:; font-src data:; connect-src 'none'; form-action 'none'">
<script>(function(){function mem(){var m=Object.create(null);return{getItem:function(k){k=String(k);return k in m?m[k]:null},setItem:function(k,v){m[String(k)]=String(v)},removeItem:function(k){delete m[String(k)]},clear:function(){m=Object.create(null)},key:function(i){var s=Object.keys(m);return i<s.length?s[i]:null},get length(){return Object.keys(m).length}}}
["localStorage","sessionStorage"].forEach(function(n){var ok=false;try{window[n].setItem("__p__","1");window[n].removeItem("__p__");ok=true}catch(e){}
if(!ok){try{Object.defineProperty(window,n,{value:mem(),configurable:true,writable:true})}catch(e){}}});})();</script>`;

/**
 * プレビュー用HTMLを作る（<head> の先頭にシムとCSPを差し込む）。
 * 空文字なら空文字を返す（呼び出し側の分岐を単純に保つ）。
 */
export function previewDoc(html: string): string {
  if (!html) return "";
  const head = /<head[^>]*>/i.exec(html);
  if (head) {
    const at = head.index + head[0].length;
    return html.slice(0, at) + SHIM + html.slice(at);
  }
  const htmlTag = /<html[^>]*>/i.exec(html);
  if (htmlTag) {
    const at = htmlTag.index + htmlTag[0].length;
    return html.slice(0, at) + SHIM + html.slice(at);
  }
  return SHIM + html;
}

/** iframe の sandbox 値。allow-same-origin は付けない（親を守るため）。
 *
 *  allow-forms が無いと <form onsubmit> の submit がブラウザに握り潰され、
 *  「入力→追加」が動かない（生成アプリで最も多い書き方なので必須）。
 *  外部への送信は上のCSPの form-action 'none' で止めているので、
 *  許可されるのはJSで処理する送信だけ。
 */
export const PREVIEW_SANDBOX = "allow-scripts allow-forms allow-modals allow-popups";
