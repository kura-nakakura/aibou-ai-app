import type { Metadata, Viewport } from "next";
import { Inter, Share_Tech_Mono } from "next/font/google";
import "./globals.css";
import { SKIN_BOOT_SCRIPT } from "@/lib/skin";

/**
 * Fonts (loaded via next/font/google, self-hosted at build time):
 *  - Share Tech Mono → headings / labels / mono HUD chrome
 *  - Inter           → body text
 * Both expose CSS variables consumed by globals.css + tailwind.config.ts.
 */
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const shareTechMono = Share_Tech_Mono({
  weight: "400",
  subsets: ["latin"],
  variable: "--font-share-tech-mono",
  display: "swap",
});

export const metadata: Metadata = {
  // ブランドは AIbou、その中で動くシステムが THE FORGE OS。
  // 2つ名で並べる（ホーム画面のラベルは短い方＝AIbou を使う）。
  title: "AIbou — THE FORGE OS",
  description: "AIbou — あなた専属のAIアシスタント。THE FORGE OS で動きます。",
  applicationName: "AIbou",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "AIbou",
  },
  // アイコンは AIbou のロゴマーク（（ ・ ））。ホーム画面用は余白入り、
  // タブ用は小さくても読めるよう寄せたものを別に用意している。
  // apple- は正方形を角丸に切られるため、192をそのまま使わず専用サイズを渡す。
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/favicon-16.png", type: "image/png", sizes: "16x16" },
      { url: "/favicon-32.png", type: "image/png", sizes: "32x32" },
      { url: "/icon-192.png", type: "image/png", sizes: "192x192" },
      { url: "/icon-512.png", type: "image/png", sizes: "512x512" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
    shortcut: "/favicon.ico",
  },
  formatDetection: {
    telephone: false,
  },
};

export const viewport: Viewport = {
  themeColor: "#0a0b0f",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // data-skin は下の <script> が描画前に付ける。サーバー出力には無いので、
    // React の「属性が増えている」警告だけ抑える（意図した差分）。
    <html lang="en" suppressHydrationWarning className={`${inter.variable} ${shareTechMono.variable}`}>
      <head>
        {/* iOS PWA niceties (mirrors appleWebApp metadata for older Safari). */}
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <meta name="mobile-web-app-capable" content="yes" />
        {/* 見た目（スキン）は最初の描画より前に <html data-skin> を立てる。
            Reactのマウントを待つと、ダークで一瞬描かれてから白へ切り替わる
            「ちらつき」が出るため、ここで同期的に実行する。 */}
        <script dangerouslySetInnerHTML={{ __html: SKIN_BOOT_SCRIPT }} />
      </head>
      {/* No bg on <body> — backgrounds live on <html> (globals.css) so the
          fixed z-index:-1 Backdrop3D starfield paints above them. */}
      <body className="min-h-[100dvh] font-sans text-fg antialiased">
        {children}
      </body>
    </html>
  );
}
