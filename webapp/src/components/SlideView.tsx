"use client";

/**
 * SlideView — スライド1枚の見た目（テーマ配色 × レイアウト別）.
 *
 * ビューア（ArtifactViewer）・編集（SlideEditor）・発表・PDF書き出しが
 * すべて同じ描画を使うために切り出したモジュール。
 * サイズは container query 単位（cqw）なので、サムネイルでも全画面でも
 * 同じ見た目のまま拡大縮小される。
 */

import type { Slide } from "@/lib/api";

/* ── themes ─────────────────────────────────────────────────────── */
export interface Theme { bg: string; accent: string; accent2: string; title: string; text: string; sub: string; light?: boolean }
export const THEMES: Record<string, Theme> = {
  midnight: { bg: "linear-gradient(135deg,#0e1526,#1b2540)", accent: "#00c8ff", accent2: "#7b2ff7", title: "#ffffff", text: "#dfe6f2", sub: "#9fb2cc" },
  aurora: { bg: "linear-gradient(135deg,#06231f,#0d4a40)", accent: "#34e0a1", accent2: "#00c8ff", title: "#eafff8", text: "#cdeee3", sub: "#8fc7b6" },
  sunset: { bg: "linear-gradient(135deg,#2a1020,#4a1e2e)", accent: "#ff8a3d", accent2: "#ff3d77", title: "#fff0ea", text: "#f3ddd4", sub: "#d8a99c" },
  forge: { bg: "linear-gradient(135deg,#080b12,#12233a)", accent: "#00f3ff", accent2: "#00f3ff", title: "#eafcff", text: "#cfe6ec", sub: "#8fb3bd" },
  mono: { bg: "linear-gradient(135deg,#f6f6f8,#e8e8ee)", accent: "#1f2937", accent2: "#6b7280", title: "#0b0f19", text: "#20242e", sub: "#5b6270", light: true },
};
export const THEME_ORDER = ["midnight", "aurora", "sunset", "forge", "mono"];
export const getTheme = (name?: string): Theme => THEMES[(name || "midnight")] ?? THEMES.midnight;

export const esc = (s: string) => (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");


/* ── one slide (themed, per-layout). Scales via container query units. ── */
export default function SlideView({ slide, theme }: { slide: Slide; theme: Theme }) {
  const layout = slide.layout || "bullets";
  const hasImg = !!slide.image;
  const t = theme;

  const Bar = () => <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: "1.6cqw", background: `linear-gradient(${t.accent},${t.accent2})` }} />;
  const bulletList = (items: string[], cols = 1) => (
    <ul style={{ display: "grid", gridTemplateColumns: cols === 2 ? "1fr 1fr" : "1fr", gap: "1.6cqw 4cqw", listStyle: "none", margin: 0, padding: 0 }}>
      {items.map((b, i) => (
        <li key={i} style={{ display: "flex", gap: "1.5cqw", color: t.text, fontSize: "3cqw", lineHeight: 1.35 }}>
          <span style={{ color: t.accent, flexShrink: 0 }}>▸</span><span>{b}</span>
        </li>
      ))}
    </ul>
  );

  /* 外枠＝クエリコンテナ。cqw を使うのは必ず「内側」の要素にする。
     同じ要素に container-type と cqw を書くと、その要素自身の padding は
     自分の幅を基準にできず祖先（実質ビューポート）で解決されてしまう。
     結果、幅の狭いサムネイルでは padding が枠を超えて中身が消える。 */
  const Frame = ({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) => (
    <div style={{
      position: "relative", width: "100%", height: "100%", overflow: "hidden",
      background: t.bg, borderRadius: 12,
      containerType: "inline-size" as unknown as undefined,
    }}>
      <div style={{
        position: "absolute", inset: 0, padding: "7cqw 8cqw",
        display: "flex", flexDirection: "column", justifyContent: "center",
        ...style,
      }}>
        {children}
      </div>
    </div>
  );

  // image background layouts (title/image/section with an image)
  if (hasImg && (layout === "title" || layout === "image" || layout === "section")) {
    return (
      <Frame style={{ padding: 0 }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={slide.image} alt="" style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }} />
        <div style={{ position: "absolute", inset: 0, background: "linear-gradient(90deg, rgba(0,0,0,0.82) 30%, rgba(0,0,0,0.25))" }} />
        <div style={{ position: "relative", padding: "7cqw 8cqw", height: "100%", display: "flex", flexDirection: "column", justifyContent: "center" }}>
          {layout === "section" && <div style={{ color: t.accent, fontSize: "2.4cqw", letterSpacing: "0.3em", marginBottom: "2cqw" }}>SECTION</div>}
          <h2 style={{ color: "#fff", fontSize: layout === "title" ? "7cqw" : "5.5cqw", fontWeight: 800, lineHeight: 1.1, margin: 0, textShadow: "0 2px 20px rgba(0,0,0,0.6)" }}>{slide.title}</h2>
          {slide.subtitle && <p style={{ color: "#e6edf7", fontSize: "3.2cqw", marginTop: "2.5cqw" }}>{slide.subtitle}</p>}
          {slide.bullets && slide.bullets.length > 0 && <div style={{ marginTop: "3cqw" }}>{bulletList(slide.bullets)}</div>}
          <span style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: "1.6cqw", background: `linear-gradient(${t.accent},${t.accent2})` }} />
        </div>
      </Frame>
    );
  }

  if (layout === "title") {
    return (
      <Frame style={{ justifyContent: "center" }}>
        <Bar />
        <h1 style={{ color: t.title, fontSize: "7.5cqw", fontWeight: 800, lineHeight: 1.08, margin: 0 }}>{slide.title}</h1>
        {slide.subtitle && <p style={{ color: t.sub, fontSize: "3.4cqw", marginTop: "3cqw" }}>{slide.subtitle}</p>}
        <span style={{ marginTop: "4cqw", width: "18cqw", height: "0.8cqw", borderRadius: 4, background: `linear-gradient(90deg,${t.accent},${t.accent2})` }} />
      </Frame>
    );
  }
  if (layout === "section") {
    return (
      <Frame style={{ justifyContent: "center", alignItems: "flex-start" }}>
        <Bar />
        <div style={{ color: t.accent, fontSize: "2.6cqw", letterSpacing: "0.32em", marginBottom: "2.5cqw" }}>SECTION</div>
        <h2 style={{ color: t.title, fontSize: "6.5cqw", fontWeight: 800, lineHeight: 1.12, margin: 0 }}>{slide.title}</h2>
      </Frame>
    );
  }
  if (layout === "stat") {
    return (
      <Frame style={{ alignItems: "center", justifyContent: "center", textAlign: "center" }}>
        <div style={{ fontSize: "18cqw", fontWeight: 900, lineHeight: 1, background: `linear-gradient(90deg,${t.accent},${t.accent2})`, WebkitBackgroundClip: "text", backgroundClip: "text", color: "transparent" }}>{slide.stat || slide.title}</div>
        {slide.title && slide.stat && <p style={{ color: t.text, fontSize: "3.6cqw", marginTop: "3cqw" }}>{slide.title}</p>}
        {slide.bullets && slide.bullets.length > 0 && <p style={{ color: t.sub, fontSize: "2.8cqw", marginTop: "1.5cqw" }}>{slide.bullets.join(" ・ ")}</p>}
      </Frame>
    );
  }
  if (layout === "quote") {
    return (
      <Frame style={{ justifyContent: "center" }}>
        <span style={{ position: "absolute", left: "5cqw", top: "1cqw", fontSize: "22cqw", color: t.accent, opacity: 0.25, lineHeight: 1 }}>“</span>
        <p style={{ color: t.title, fontSize: "5cqw", fontWeight: 700, lineHeight: 1.35, margin: 0, position: "relative" }}>{slide.quote || slide.title}</p>
        {slide.author && <p style={{ color: t.accent, fontSize: "3cqw", marginTop: "3cqw" }}>— {slide.author}</p>}
      </Frame>
    );
  }
  if (layout === "image" && hasImg) {
    return (
      <Frame style={{ padding: 0, flexDirection: "row" }}>
        <div style={{ flex: 1, padding: "7cqw", display: "flex", flexDirection: "column", justifyContent: "center", position: "relative" }}>
          <Bar />
          <h2 style={{ color: t.title, fontSize: "5cqw", fontWeight: 800, lineHeight: 1.15, margin: "0 0 2.5cqw" }}>{slide.title}</h2>
          {slide.bullets && bulletList(slide.bullets)}
        </div>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={slide.image} alt="" style={{ width: "42%", height: "100%", objectFit: "cover" }} />
      </Frame>
    );
  }

  // bullets / two_col (default)
  const cols = layout === "two_col" ? 2 : 1;
  return (
    <Frame>
      <Bar />
      <h2 style={{ color: t.title, fontSize: "5cqw", fontWeight: 800, lineHeight: 1.15, margin: "0 0 3.5cqw" }}>{slide.title}</h2>
      {slide.bullets && slide.bullets.length > 0 ? bulletList(slide.bullets, cols) : <p style={{ color: t.sub, fontSize: "3cqw" }}>{slide.subtitle || ""}</p>}
    </Frame>
  );
}

/* ── PDF (print) HTML per layout, themed ─────────────────────────── */
export function slidePrintHtml(s: Slide, t: Theme, idx: number, total: number): string {
  const layout = s.layout || "bullets";
  const bar = `<span class="bar" style="background:linear-gradient(${t.accent},${t.accent2})"></span>`;
  const bullets = (items: string[], cols = 1) =>
    `<ul class="bl" style="columns:${cols}">${items.map((b) => `<li style="color:${t.text}"><span style="color:${t.accent}">▸</span> ${esc(b)}</li>`).join("")}</ul>`;
  let inner = "";
  if (s.image && (layout === "title" || layout === "image" || layout === "section")) {
    inner = `<div class="imgbg" style="background-image:url('${s.image}')"></div><div class="imgov"></div><div class="pad">${bar}<h2 style="color:#fff;font-size:44px">${esc(s.title || "")}</h2>${s.subtitle ? `<p style="color:#e6edf7;font-size:22px">${esc(s.subtitle)}</p>` : ""}${s.bullets?.length ? bullets(s.bullets) : ""}</div>`;
    return `<section class="slide" style="background:${t.bg}"><div class="pageno" style="color:${t.sub}">${idx}/${total}</div>${inner}</section>`;
  }
  if (layout === "title") inner = `${bar}<h1 style="color:${t.title};font-size:52px">${esc(s.title || "")}</h1>${s.subtitle ? `<p style="color:${t.sub};font-size:24px">${esc(s.subtitle)}</p>` : ""}`;
  else if (layout === "section") inner = `${bar}<div style="color:${t.accent};letter-spacing:.3em;font-size:16px">SECTION</div><h2 style="color:${t.title};font-size:46px">${esc(s.title || "")}</h2>`;
  else if (layout === "stat") inner = `<div class="stat" style="background:linear-gradient(90deg,${t.accent},${t.accent2});-webkit-background-clip:text;background-clip:text;color:transparent">${esc(s.stat || s.title || "")}</div>${s.stat && s.title ? `<p style="color:${t.text};font-size:24px;text-align:center">${esc(s.title)}</p>` : ""}`;
  else if (layout === "quote") inner = `<p style="color:${t.title};font-size:34px;font-weight:700;line-height:1.4">“${esc(s.quote || s.title || "")}”</p>${s.author ? `<p style="color:${t.accent};font-size:20px">— ${esc(s.author)}</p>` : ""}`;
  else inner = `${bar}<h2 style="color:${t.title};font-size:40px">${esc(s.title || "")}</h2>${s.bullets?.length ? bullets(s.bullets, layout === "two_col" ? 2 : 1) : ""}`;
  return `<section class="slide ${layout}" style="background:${t.bg}"><div class="pageno" style="color:${t.sub}">${idx}/${total}</div>${inner}</section>`;
}

export const PRINT_BASE_CSS = `
  *{box-sizing:border-box;-webkit-print-color-adjust:exact;print-color-adjust:exact;margin:0}
  body{font-family:-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif}
  .doc{max-width:760px;margin:32px auto;padding:0 24px;line-height:1.7;color:#111}
  .doc h1{font-size:26px;border-bottom:2px solid #eee;padding-bottom:8px}
  .doc h2{font-size:20px;margin-top:26px}.doc pre{background:#f5f5f7;padding:12px;border-radius:8px}
  .doc table{border-collapse:collapse;width:100%}.doc th,.doc td{border:1px solid #ddd;padding:6px 10px}
  table.sheet{border-collapse:collapse;width:calc(100% - 48px);margin:24px}
  table.sheet th,table.sheet td{border:1px solid #ccc;padding:6px 10px;font-size:13px}table.sheet th{background:#f3f4f6}
  .slide{position:relative;width:100%;height:100vh;padding:8% 9%;display:flex;flex-direction:column;justify-content:center;page-break-after:always;overflow:hidden}
  .slide:last-child{page-break-after:auto}
  .slide.stat{align-items:center;text-align:center}.slide.quote{justify-content:center}
  .slide .bar{position:absolute;left:0;top:0;bottom:0;width:10px}
  .slide h1,.slide h2{font-weight:800;line-height:1.12;margin-bottom:20px}
  .slide .stat{font-size:150px;font-weight:900;line-height:1}
  .slide .bl{list-style:none;padding:0;font-size:24px;line-height:1.9}.slide .bl li{margin-bottom:6px}
  .slide .imgbg{position:absolute;inset:0;background-size:cover;background-position:center}
  .slide .imgov{position:absolute;inset:0;background:linear-gradient(90deg,rgba(0,0,0,.82) 30%,rgba(0,0,0,.25))}
  .slide .pad{position:relative;z-index:2}.slide .pad h2{color:#fff}
  .slide .pageno{position:absolute;right:6%;bottom:5%;font-size:14px;opacity:.6}
  @page{size:landscape;margin:0}
`;
