/**
 * /g/[slug] — Programmatic SEO の公開ページ（サーバーレンダリング）.
 *
 * バックエンドの /pseo/public/{slug} から「承認済み」ページだけを取得して描画する。
 * SPA本体(app/page.tsx)とは独立した静的寄りの公開ページなので、検索エンジンに
 * インデックスされることを目的にHTMLを直接返す（Vercel無料枠で動く）。
 * 1時間ごとに再検証するので、承認したページは再デプロイなしで公開される。
 */

import type { Metadata } from "next";
import SubscribeForm from "@/components/SubscribeForm";

export const revalidate = 3600;

interface Section { h2?: string; body?: string }
interface Faq { q?: string; a?: string }
interface PageContent {
  disclosure?: string;
  lead?: string;
  meta_description?: string;
  sections?: Section[];
  faq?: Faq[];
}
interface PseoPage {
  slug: string;
  title: string;
  keywords?: string;
  content?: PageContent;
  updated_at?: string;
}

const API = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

async function fetchPage(slug: string): Promise<PseoPage | null> {
  if (!API) return null;
  try {
    const res = await fetch(`${API}/pseo/public/${encodeURIComponent(slug)}`, {
      next: { revalidate },
    });
    if (!res.ok) return null;
    return (await res.json()) as PseoPage;
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const page = await fetchPage(slug);
  if (!page) return { title: "ページが見つかりません" };
  const desc = page.content?.meta_description || page.content?.lead || page.title;
  return {
    title: page.title,
    description: desc.slice(0, 160),
    keywords: page.keywords,
    openGraph: { title: page.title, description: desc.slice(0, 160), type: "article" },
  };
}

export default async function PseoPageView({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const page = await fetchPage(slug);

  // 公開ページはアプリ本体のダークテーマを継承しない（読み物として白地に統一）。
  // ラッパーで背景色を明示しないと、記事本文が暗い背景に暗い文字で埋もれてしまう。
  const shell: React.CSSProperties = {
    background: "#ffffff",
    color: "#1a1d24",
    minHeight: "100vh",
    fontFamily: "system-ui, -apple-system, 'Hiragino Sans', 'Noto Sans JP', sans-serif",
  };

  if (!page) {
    return (
      <div style={shell}>
        <main style={{ maxWidth: 720, margin: "0 auto", padding: "80px 20px" }}>
          <h1 style={{ fontSize: 22, margin: "0 0 8px" }}>ページが見つかりません</h1>
          <p style={{ color: "#6b7280", fontSize: 14 }}>公開が承認されていない、または削除された可能性があります。</p>
        </main>
      </div>
    );
  }

  const c = page.content ?? {};
  return (
    <div style={shell}>
    <main style={{ maxWidth: 760, margin: "0 auto", padding: "40px 20px 80px", lineHeight: 1.85 }}>
      {/* 景品表示法（ステマ規制）対応の表記 */}
      {c.disclosure && (
        <p style={{ fontSize: 12, color: "#6b7280", background: "#f3f4f6", padding: "8px 12px", borderRadius: 6, margin: "0 0 24px" }}>
          {c.disclosure}
        </p>
      )}

      {/* globals.css が見出しを明色にしているため、公開ページでは色を明示する */}
      <h1 style={{ fontSize: 28, lineHeight: 1.35, margin: "0 0 16px", color: "#0b0f19" }}>{page.title}</h1>
      {c.lead && <p style={{ fontSize: 16, color: "#374151" }}>{c.lead}</p>}

      {(c.sections ?? []).map((s, i) => (
        <section key={i} style={{ marginTop: 36 }}>
          {s.h2 && <h2 style={{ fontSize: 20, borderLeft: "4px solid #2563eb", paddingLeft: 10, margin: "0 0 12px", color: "#111827" }}>{s.h2}</h2>}
          {s.body && <p style={{ fontSize: 15, whiteSpace: "pre-wrap" }}>{s.body}</p>}
        </section>
      ))}

      {(c.faq ?? []).length > 0 && (
        <section style={{ marginTop: 48 }}>
          <h2 style={{ fontSize: 20, margin: "0 0 16px", color: "#111827" }}>よくある質問</h2>
          {(c.faq ?? []).map((f, i) => (
            <div key={i} style={{ marginBottom: 18 }}>
              {f.q && <p style={{ fontWeight: 700, fontSize: 15, margin: "0 0 4px" }}>Q. {f.q}</p>}
              {f.a && <p style={{ fontSize: 15, color: "#374151", margin: 0 }}>A. {f.a}</p>}
            </div>
          ))}
        </section>
      )}

      {/* 構造化データ（FAQPage）— 検索結果でのリッチ表示を狙う */}
      {(c.faq ?? []).length > 0 && (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "FAQPage",
              mainEntity: (c.faq ?? []).filter((f) => f.q && f.a).map((f) => ({
                "@type": "Question",
                name: f.q,
                acceptedAnswer: { "@type": "Answer", text: f.a },
              })),
            }),
          }}
        />
      )}

      {/* 企画書⑤：SEOトラフィック → 顧客リストへの送客ルート */}
      <SubscribeForm source={`/g/${page.slug}`} />

      <footer style={{ marginTop: 56, paddingTop: 20, borderTop: "1px solid #e5e7eb", fontSize: 12, color: "#9ca3af" }}>
        {page.updated_at && <span>最終更新: {page.updated_at.slice(0, 10)}</span>}
      </footer>
    </main>
    </div>
  );
}
