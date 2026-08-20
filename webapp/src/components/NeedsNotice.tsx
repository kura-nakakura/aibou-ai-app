"use client";

/**
 * NeedsNotice — 「この画面を使うには◯◯を設定してください」。
 *
 * 各モードの一番上に出す。鍵が入っていないまま操作させると、押した先で
 * 「401」「503」といった数字が返ってきて、何をすればいいのか分からない。
 * 先回りして、足りないものと入れる場所を出す。
 *
 * 足りているときは何も出さない（毎回出ると邪魔になる）。
 */

import { useEffect, useState } from "react";
import { API_URL, listKeys } from "@/lib/api";
import { explain, MODE_NEEDS, NEED, needMessage } from "@/lib/needs";

interface State {
  missing: string[];      // 未設定の鍵の名前
  error: string | null;   // 鍵の一覧すら取れない（接続・認証の問題）
  loading: boolean;
}

export default function NeedsNotice({ mode }: { mode: string }) {
  const [s, setS] = useState<State>({ missing: [], error: null, loading: true });

  useEffect(() => {
    const wanted = MODE_NEEDS[mode] ?? [];
    if (!wanted.length || !API_URL) { setS({ missing: [], error: null, loading: false }); return; }
    let alive = true;
    listKeys()
      .then((keys) => {
        if (!alive) return;
        const have = new Set(keys.filter((k) => k.set).map((k) => k.name));
        setS({ missing: wanted.filter((w) => !have.has(w)), error: null, loading: false });
      })
      .catch((e) => {
        if (!alive) return;
        setS({ missing: [], error: explain(e, "設定の確認"), loading: false });
      });
    return () => { alive = false; };
  }, [mode]);

  if (s.loading) return null;

  // 接続・認証がそもそも通っていない。ここが一番混乱するので最優先で出す。
  if (s.error) {
    return (
      <Banner tone="error" title="いまこの画面は使えません">
        {s.error}
      </Banner>
    );
  }

  const required = s.missing.filter((k) => !NEED[k]?.optional);
  const optional = s.missing.filter((k) => NEED[k]?.optional);
  if (!required.length && !optional.length) return null;

  return (
    <>
      {required.map((k) => (
        <Banner key={k} tone="warn" title="先に設定が必要です">
          {needMessage(NEED[k])}
        </Banner>
      ))}
      {optional.map((k) => (
        <Banner key={k} tone="info" title="設定すると、さらに使えます">
          {needMessage(NEED[k])}
        </Banner>
      ))}
    </>
  );
}

const TONE = {
  error: { color: "#ff9b9b", mark: "⚠" },
  warn: { color: "#ffd060", mark: "⚠" },
  info: { color: "var(--muted)", mark: "＋" },
} as const;

function Banner({ tone, title, children }: {
  tone: keyof typeof TONE; title: string; children: React.ReactNode;
}) {
  const t = TONE[tone];
  return (
    <div className="mb-2 rounded-forge border p-3"
         style={{ borderColor: tone === "info" ? "var(--panel-bd)" : `${t.color}55` }}>
      <div className="mb-1 text-[10px] tracking-[0.16em] label-mono" style={{ color: t.color }}>
        {t.mark} {title}
      </div>
      <p className="text-[11px] leading-relaxed text-fg">{children}</p>
    </div>
  );
}
