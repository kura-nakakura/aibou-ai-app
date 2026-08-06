/**
 * /sitemap.xml — Programmatic SEO ページのサイトマップ.
 *
 * バックエンドの /pseo/sitemap（承認済みのみ）から一覧を取り、XMLで返す。
 * Google Search Console にこのURLを登録すれば、承認したページが順次
 * インデックスされる（未承認/却下は含まれない）。
 */

export const revalidate = 3600;

const API = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

function baseUrl(req: Request): string {
  const explicit = process.env.NEXT_PUBLIC_SITE_URL;
  if (explicit) return explicit.replace(/\/$/, "");
  try {
    const u = new URL(req.url);
    return `${u.protocol}//${u.host}`;
  } catch {
    return "";
  }
}

export async function GET(req: Request) {
  const site = baseUrl(req);
  let items: { slug: string; updated_at?: string }[] = [];
  if (API) {
    try {
      const res = await fetch(`${API}/pseo/sitemap`, { next: { revalidate } });
      if (res.ok) {
        const data = (await res.json()) as { items?: { slug: string; updated_at?: string }[] };
        items = data.items ?? [];
      }
    } catch {
      /* サイトマップは落とさない（空で返す） */
    }
  }

  const urls = [
    `<url><loc>${site}/</loc></url>`,
    ...items
      .filter((i) => i.slug)
      .map((i) => {
        const lastmod = (i.updated_at || "").slice(0, 10);
        return `<url><loc>${site}/g/${encodeURIComponent(i.slug)}</loc>${lastmod ? `<lastmod>${lastmod}</lastmod>` : ""}</url>`;
      }),
  ].join("");

  const xml = `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls}</urlset>`;
  return new Response(xml, {
    headers: { "Content-Type": "application/xml; charset=utf-8", "Cache-Control": "public, max-age=3600" },
  });
}
