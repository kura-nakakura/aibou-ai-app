"use client";

/**
 * FreeOps — 「お金をかけずに、時刻どおり動かす」ための手順。
 *
 * 無料プランのサーバーは寝るので、定期実行は外から起こしてもらう必要がある。
 * これは直せない制約なので、代わりに「もう持っているもので済む」ことを示す。
 *
 * 見回りが止まっているときだけ大きく出す。動いているのに手順を並べても
 * ただの雑音になる。
 */

import { useState } from "react";
import { API_URL } from "@/lib/api";
import { FREE_OPS, FREE_OPS_SUMMARY } from "@/lib/freeOps";

export default function FreeOps({ hookUrl = "" }: { hookUrl?: string }) {
  const [open, setOpen] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const copy = async (id: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(id);
      setTimeout(() => setCopied(null), 2000);
    } catch { /* コピーできない環境では、選んで手でコピーしてもらう */ }
  };

  return (
    <div className="rounded-forge border border-panel p-3">
      <div className="mb-1 text-[10px] tracking-[0.2em] text-muted label-mono">
        お金をかけずに、時刻どおり動かす
      </div>
      <p className="mb-2 text-[11px] leading-relaxed text-fg">{FREE_OPS_SUMMARY}</p>

      <div className="grid gap-1.5">
        {FREE_OPS.map((m) => {
          const isOpen = open === m.id;
          const snippet = m.snippet?.({ apiUrl: API_URL, hookUrl });
          return (
            <div key={m.id} className="rounded-forge border border-panel">
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : m.id)}
                aria-expanded={isOpen}
                className="flex w-full items-start gap-2 p-2.5 text-left"
              >
                <span className="mt-[2px] shrink-0 text-[10px] text-muted">{isOpen ? "▾" : "▸"}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[12px] text-fg-strong">{m.name}</span>
                  <span className="mt-0.5 block text-[10px] leading-relaxed text-muted">
                    すでにあるもの: {m.youAlreadyHave} ／ {m.accuracy}
                  </span>
                </span>
              </button>

              {isOpen && (
                <div className="border-t border-panel p-2.5">
                  <ol className="ml-4 list-decimal space-y-1 text-[11px] leading-relaxed text-fg">
                    {m.steps.map((s) => <li key={s}>{s}</li>)}
                  </ol>

                  {snippet && (
                    <div className="mt-2">
                      {/* 長い行が画面を横に広げないよう、この中だけで横スクロールさせる */}
                      <pre className="min-w-0 max-h-56 overflow-auto rounded-forge bg-black/40 p-2 text-[10px] leading-relaxed text-fg">
                        <code>{snippet}</code>
                      </pre>
                      <button
                        type="button"
                        onClick={() => void copy(m.id, snippet)}
                        className="mt-1 text-[10px] text-[var(--accent)] underline"
                      >
                        {copied === m.id ? "✓ コピーしました" : "コピーする"}
                      </button>
                    </div>
                  )}

                  {m.note && (
                    <p className="mt-2 text-[10px] leading-relaxed text-muted/80">{m.note}</p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
