"use client";

/**
 * BrandIcon — 連携サービスの目印。
 *
 * 文字だけの一覧は読まないと分からないが、色と形は一瞬で分かる。
 * ロゴ画像は外から読み込めない（CSPで止まる）ので、その場で描く。
 * 本物のロゴの複製ではなく、見分けがつく程度の簡略な図形にしている。
 */

export default function BrandIcon({ id, size = 22 }: { id: string; size?: number }) {
  const p = { width: size, height: size, viewBox: "0 0 24 24" };

  switch (id) {
    case "line":
      return (
        <svg {...p} aria-hidden>
          <rect x="1" y="2" width="22" height="17" rx="5" fill="#06C755" />
          <path d="M8 19l-1.5 3 5-3z" fill="#06C755" />
          <text x="12" y="14" textAnchor="middle" fontSize="8.5" fontWeight="700" fill="#fff"
                fontFamily="system-ui, sans-serif">LINE</text>
        </svg>
      );

    case "x":
      return (
        <svg {...p} aria-hidden>
          <rect x="2" y="2" width="20" height="20" rx="4.5" fill="#000" />
          <path d="M7 7l10 10M17 7L7 17" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" />
        </svg>
      );

    case "slack": {
      // 4色の格子。Slackは「4色が十字に組み合う」形で覚えられている
      const bar = (x: number, y: number, w: number, h: number, c: string) => (
        <rect x={x} y={y} width={w} height={h} rx={h / 2 < w / 2 ? h / 2 : w / 2} fill={c} />
      );
      return (
        <svg {...p} aria-hidden>
          {bar(3, 10, 8, 3.2, "#36C5F0")}
          {bar(10.8, 3, 3.2, 8, "#2EB67D")}
          {bar(13, 10.8, 8, 3.2, "#ECB22E")}
          {bar(10, 13, 3.2, 8, "#E01E5A")}
        </svg>
      );
    }

    case "discord":
      return (
        <svg {...p} aria-hidden>
          <rect x="1" y="4" width="22" height="16" rx="6" fill="#5865F2" />
          <ellipse cx="8.6" cy="12" rx="2" ry="2.6" fill="#fff" />
          <ellipse cx="15.4" cy="12" rx="2" ry="2.6" fill="#fff" />
        </svg>
      );

    case "google":
      return (
        <svg {...p} aria-hidden>
          <path d="M21.6 12.2c0-.7-.06-1.2-.18-1.8H12v3.4h5.5c-.11.9-.7 2.3-2.03 3.2l3.1 2.4c1.84-1.7 2.9-4.2 2.9-7.2z" fill="#4285F4" />
          <path d="M12 22c2.7 0 4.96-.9 6.6-2.4l-3.1-2.4c-.85.6-1.98 1-3.5 1-2.7 0-4.98-1.8-5.8-4.2l-3.2 2.5C4.66 19.7 8.06 22 12 22z" fill="#34A853" />
          <path d="M6.2 14c-.22-.6-.34-1.3-.34-2s.12-1.4.33-2L2.99 7.5A10 10 0 0 0 2 12c0 1.6.39 3.2 1 4.5z" fill="#FBBC05" />
          <path d="M12 5.8c1.9 0 3.2.8 3.95 1.5l2.85-2.8C17 2.9 14.7 2 12 2 8.06 2 4.66 4.3 3 7.5l3.2 2.5C7.02 7.6 9.3 5.8 12 5.8z" fill="#EA4335" />
        </svg>
      );

    case "supabase":
      return (
        <svg {...p} aria-hidden>
          <path d="M13 2 4.5 12.6c-.5.6-.06 1.5.72 1.5H12v7.9c0 .9 1.15 1.3 1.7.6L22 12c.5-.6.06-1.5-.72-1.5H14V2.6c0-.9-.6-1.2-1-.6z" fill="#3ECF8E" />
        </svg>
      );

    case "github":
      return (
        <svg {...p} aria-hidden>
          <circle cx="12" cy="12" r="10" fill="currentColor" opacity="0.9" />
          <path d="M12 5.5c-3.6 0-6.5 2.9-6.5 6.5 0 2.9 1.86 5.3 4.44 6.17.33.06.44-.14.44-.31v-1.2c-1.8.4-2.19-.77-2.19-.77-.3-.75-.72-.95-.72-.95-.6-.4.04-.4.04-.4.66.05 1 .68 1 .68.58 1 1.53.71 1.9.54.06-.42.23-.71.42-.87-1.44-.16-2.96-.72-2.96-3.2 0-.71.25-1.29.67-1.74-.07-.17-.29-.83.06-1.72 0 0 .55-.18 1.8.66a6.2 6.2 0 0 1 3.28 0c1.25-.84 1.8-.66 1.8-.66.35.9.13 1.55.06 1.72.42.45.67 1.03.67 1.74 0 2.49-1.53 3.04-2.98 3.2.24.2.44.6.44 1.2v1.79c0 .17.11.38.45.31A6.51 6.51 0 0 0 18.5 12c0-3.6-2.9-6.5-6.5-6.5z"
                fill="var(--bg, #0a0e17)" />
        </svg>
      );

    case "notion":
      return (
        <svg {...p} aria-hidden>
          <rect x="2.5" y="2.5" width="19" height="19" rx="3" fill="#fff" stroke="#111" strokeWidth="1" />
          <path d="M8 16.5v-9l8 9v-9" stroke="#111" strokeWidth="1.7" fill="none"
                strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );

    case "gemini":
      return (
        <svg {...p} aria-hidden>
          <path d="M12 2c.5 5 4.5 9 10 10-5.5 1-9.5 5-10 10-.5-5-4.5-9-10-10 5.5-1 9.5-5 10-10z" fill="#8AB4F8" />
        </svg>
      );

    case "huggingface":
      return (
        <svg {...p} aria-hidden>
          <circle cx="12" cy="12" r="9.5" fill="#FFD21E" />
          <circle cx="8.8" cy="10" r="1.3" fill="#111" />
          <circle cx="15.2" cy="10" r="1.3" fill="#111" />
          <path d="M8 14.5c1 1.6 2.4 2.4 4 2.4s3-.8 4-2.4" stroke="#111" strokeWidth="1.5"
                fill="none" strokeLinecap="round" />
        </svg>
      );

    case "openai":
      return (
        <svg {...p} aria-hidden>
          <circle cx="12" cy="12" r="9.5" fill="#111" stroke="currentColor" strokeWidth="0.8" opacity="0.95" />
          <path d="M12 6.5l4.8 2.75v5.5L12 17.5l-4.8-2.75v-5.5z" stroke="#fff" strokeWidth="1.4" fill="none"
                strokeLinejoin="round" />
        </svg>
      );

    case "email":
      return (
        <svg {...p} aria-hidden>
          <rect x="2.5" y="5" width="19" height="14" rx="2.5" fill="#EA4335" />
          <path d="M3.5 7l8.5 6 8.5-6" stroke="#fff" strokeWidth="1.7" fill="none"
                strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );

    case "leonardo":
      return (
        <svg {...p} aria-hidden>
          <path d="M12 3l8 5v8l-8 5-8-5V8z" fill="#A78BFA" />
          <path d="M12 8l4 2.5v3L12 16l-4-2.5v-3z" fill="#1b1030" />
        </svg>
      );

    case "note":
      return (
        <svg {...p} aria-hidden>
          <rect x="2.5" y="2.5" width="19" height="19" rx="9.5" fill="#41C9B4" />
          <text x="12" y="15.5" textAnchor="middle" fontSize="10" fontWeight="700" fill="#fff"
                fontFamily="system-ui, sans-serif">n</text>
        </svg>
      );

    default:
      return (
        <svg {...p} aria-hidden>
          <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.6" />
          <path d="M12 8v8M8 12h8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
      );
  }
}
