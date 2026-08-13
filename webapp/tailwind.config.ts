import type { Config } from "tailwindcss";

/**
 * THE FORGE OS — Tailwind theme.
 * Colors mirror the canonical design tokens in src/app/globals.css
 * (white × silver × black, calm pale-blue core glow). We expose them here
 * so utilities like `bg-bg`, `text-fg`, `border-panel` stay on-brand.
 */
const config: Config = {
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
    "./src/lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      // 色は globals.css のトークンを参照する。ここに実値を書くと
      // スキン切替（<html data-skin>）で色が変わらない。
      // muted だけは text-muted/60 のような不透明度指定が使われているので、
      // Tailwind が alpha を差し込める「チャンネル値」の形にしている。
      colors: {
        bg: "var(--bg)",
        bg2: "var(--bg2)",
        fg: "var(--fg)",
        "fg-strong": "var(--fg-strong)",
        muted: "rgb(var(--muted-rgb) / <alpha-value>)",
        line: "var(--line)",
        silver: "var(--line)",
        accent: "var(--accent)",
      },
      backgroundColor: {
        panel: "var(--panel)",
      },
      borderColor: {
        panel: "var(--panel-bd)",
        "panel-strong": "var(--btn-bd)",
      },
      boxShadow: {
        glow: "0 0 18px var(--glow)",
        "glow-strong": "0 0 28px var(--glow-strong)",
        cyan: "0 0 18px rgba(0,243,255,0.45)",
        panel: "0 6px 18px var(--shadow)",
      },
      borderRadius: {
        forge: "14px",
      },
      fontFamily: {
        // Wired to the next/font CSS variables defined in layout.tsx.
        mono: ["var(--font-share-tech-mono)", "ui-monospace", "monospace"],
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      keyframes: {
        "core-pulse": {
          "0%, 100%": { transform: "scale(1)", opacity: "0.92" },
          "50%": { transform: "scale(1.04)", opacity: "1" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "core-pulse": "core-pulse 4s ease-in-out infinite",
        shimmer: "shimmer 2.2s linear infinite",
        "fade-in": "fade-in 0.4s ease both",
      },
    },
  },
  plugins: [],
};

export default config;
