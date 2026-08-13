/**
 * 見た目（スキン）の切り替え。
 *
 *   forge … 既定。黒＋シルバーのHUD（THE FORGE OS）
 *   aibou … 白＋薄紫のライト。AIbouブランドの明るい画面
 *
 * 仕組みは <html data-skin="..."> の1属性だけ。色・面・角丸・ラベルの体裁は
 * すべて globals.css の `html[data-skin="aibou"]` ブロックで上書きするので、
 * 各コンポーネントを書き換えずに全画面の見た目が変わる。
 *
 * ここは副作用の無い関数と、DOMに1回だけ触る関数に分けてある（テストしやすさ）。
 */

export type Skin = "forge" | "aibou";

export const SKINS: { key: Skin; label: string; hint: string }[] = [
  { key: "forge", label: "FORGE（ダーク）", hint: "黒×シルバーのHUD。既定" },
  { key: "aibou", label: "AIbou（ライト）", hint: "白×淡い紫の明るい画面" },
];

export const DEFAULT_SKIN: Skin = "forge";

/** localStorage のキー。他の設定と同じ forge_ 接頭辞に揃える。 */
export const SKIN_KEY = "forge_skin";

/** ブラウザのUI色（アドレスバー等）。切り替え時に meta も合わせる。 */
export const SKIN_THEME_COLOR: Record<Skin, string> = {
  forge: "#0a0b0f",
  aibou: "#f4f5fd",
};

/** 未知の値・null を既定に丸める（保存値が壊れていても落ちないように）。 */
export function normalizeSkin(value: unknown): Skin {
  return value === "aibou" || value === "forge" ? value : DEFAULT_SKIN;
}

/** 保存済みのスキンを読む。localStorage が使えない環境でも例外を投げない。 */
export function readSkin(): Skin {
  try {
    return normalizeSkin(localStorage.getItem(SKIN_KEY));
  } catch {
    return DEFAULT_SKIN;
  }
}

/** DOM に反映する（<html data-skin> と theme-color）。 */
export function applySkin(skin: Skin): void {
  const s = normalizeSkin(skin);
  try {
    document.documentElement.dataset.skin = s;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", SKIN_THEME_COLOR[s]);
  } catch {
    /* SSR や属性が触れない環境では何もしない */
  }
}

/** 保存して反映する。 */
export function setSkin(skin: Skin): Skin {
  const s = normalizeSkin(skin);
  try {
    localStorage.setItem(SKIN_KEY, s);
  } catch {
    /* 保存できなくても見た目だけは変える */
  }
  applySkin(s);
  return s;
}

/**
 * 最初の描画より前に <html data-skin> を立てるための素のJS。
 * layout.tsx から <script> として差し込む（Reactのマウントを待つと、
 * ダークで一瞬描かれてから白に切り替わる「ちらつき」が出る）。
 */
export const SKIN_BOOT_SCRIPT = `(function(){try{var s=localStorage.getItem("${SKIN_KEY}");if(s!=="aibou"&&s!=="forge")s="${DEFAULT_SKIN}";document.documentElement.setAttribute("data-skin",s);var m=document.querySelector('meta[name="theme-color"]');if(m)m.setAttribute("content",s==="aibou"?"${SKIN_THEME_COLOR.aibou}":"${SKIN_THEME_COLOR.forge}");}catch(e){}})();`;
