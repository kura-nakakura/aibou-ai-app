/**
 * shape — サーバーの応答を、画面が触っても落ちない形に整える。
 *
 * 全モードを一斉に開いて分かったこと: MEモードが真っ白だった。
 * /life/entries の応答に categories が無く、それをそのまま画面へ渡していたので
 * categories.length で例外になり、モードごと消えていた。
 *
 * サーバーが古い・エラー時に縮退する・一部のキーだけ返す、は普通に起きる。
 * キーが1つ欠けただけで画面が消えるのは、原因も分からず一番きつい。
 * 「配列のはずの場所は必ず配列にする」をここに一本化しておく。
 */

/** 配列でなければ空配列。null/undefined/文字列/オブジェクト、どれが来ても落ちない。 */
export function asArray<T>(v: unknown): T[] {
  return Array.isArray(v) ? (v as T[]) : [];
}

/** 有限な数でなければ既定値。Number(null)===0 に引っかからないよう、型から見る。 */
export function asNumber(v: unknown, fallback = 0): number {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v);
    if (Number.isFinite(n)) return n;
  }
  return fallback;
}

/** 文字列でなければ空文字。 */
export function asText(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}
