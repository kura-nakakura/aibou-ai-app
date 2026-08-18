"use client";

/**
 * Policy — プライバシーと利用についての説明。
 *
 * アカウント作成の画面（バックエンド未接続）と、アプリ内のGUIDEの両方から
 * 同じものを出す。本文は lib/policy.ts が唯一の出どころ。
 */

import { PRIVACY, POLICY_VERSION } from "@/lib/policy";

export function PolicyBody() {
  return (
    <div className="grid gap-3">
      {PRIVACY.map((s) => (
        <section key={s.id} className="panel p-4">
          <h3 className="text-[13px] text-fg-strong">{s.title}</h3>
          <ul className="mt-2 space-y-1.5">
            {s.points.map((p) => (
              <li key={p} className="flex gap-2 text-[12px] leading-relaxed text-fg">
                <span aria-hidden className="mt-[7px] h-1 w-1 shrink-0 rounded-full"
                      style={{ background: "var(--accent)" }} />
                <span className="min-w-0">{p}</span>
              </li>
            ))}
          </ul>
          {s.notes && s.notes.length > 0 && (
            <ul className="mt-2.5 space-y-1 border-t border-panel pt-2.5">
              {s.notes.map((n) => (
                <li key={n} className="text-[11px] leading-relaxed text-muted">※ {n}</li>
              ))}
            </ul>
          )}
        </section>
      ))}
      <p className="px-1 text-[10px] text-muted">最終更新 {POLICY_VERSION}</p>
    </div>
  );
}

/** 全画面で読ませるための箱（アカウント作成画面から開く）。 */
export default function PolicyOverlay({ onClose }: { onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-[80] flex flex-col bg-[var(--bg)]"
      role="dialog"
      aria-label="プライバシーと利用について"
    >
      <div className="flex items-center justify-between border-b border-panel p-4">
        <h2 className="text-[13px] text-fg-strong label-mono">PRIVACY &amp; TERMS</h2>
        <button
          type="button"
          onClick={onClose}
          className="min-h-[44px] px-3 text-[12px] text-muted transition hover:text-fg-strong"
        >
          閉じる
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4 pb-[max(env(safe-area-inset-bottom),1rem)]">
        <div className="mx-auto w-full max-w-2xl">
          <PolicyBody />
        </div>
      </div>
    </div>
  );
}
