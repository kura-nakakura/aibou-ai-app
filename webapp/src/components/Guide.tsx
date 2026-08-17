"use client";

/**
 * Guide — アプリの説明書（初めての人が最初に開く画面）。
 *
 * 構成は「読みもの（節）→ 全モードの説明書（実画面つき）」。本文も画面写真の
 * パスもバックエンドの guide.py が持つ。CHATが「使い方は？」と聞かれたときに
 * 答える内容と同じ出どころなので、説明が2つに割れて片方だけ古くなることがない。
 *
 * 画面写真は実際に撮った初回表示（webapp/public/guide/*.webp）。作り物の
 * モックではないので、開いたときの見え方とズレない。
 *
 * バックエンド未接続でも最低限の始め方は出す（新しい人が最初に開く画面で
 * 「接続してください」しか出ないのは案内として不親切なため）。
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { API_URL, guideGet, type GuideDoc, type GuideMode } from "@/lib/api";

/** 未接続時にだけ出す、最小限の始め方。 */
const OFFLINE_STEPS = [
  "下の CHAT に、やりたいことをそのまま書いてください（例：「明日15時に歯医者の予定を入れて」）",
  "右上の ⚙ → KEYCHAIN で「自分のデータベース」を繋ぎ、AIの鍵を1つ保存します",
  "接続できると、ここに全モードの説明書（画面写真つき）が出ます",
];

export default function Guide() {
  const [doc, setDoc] = useState<GuideDoc | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [zoom, setZoom] = useState<GuideMode | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!API_URL) { setLoading(false); return; }
    guideGet()
      .then(setDoc)
      .catch(() => setErr("説明書を取得できませんでした（バックエンド未接続）"))
      .finally(() => setLoading(false));
  }, []);

  // 目次から飛べるように、モードごとの位置を覚えておく
  const anchors = useMemo(() => new Map<string, HTMLElement>(), []);
  const jump = (id: string) => {
    anchors.get(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div ref={listRef} className="mx-auto w-full max-w-3xl pb-6">
      <div className="mb-3 text-center">
        <h2 className="brand-wordmark text-[20px] text-fg-strong">
          {doc?.app ?? "AIbou"} の説明書
        </h2>
        <p className="mt-1 text-[11px] text-muted">
          はじめての人はここから。困ったら CHAT で「使い方教えて」と聞いてもOKです。
        </p>
      </div>

      {loading && (
        <div className="panel p-4 text-center text-[10px] tracking-[0.2em] text-muted label-mono">
          ◈ LOADING GUIDE…
        </div>
      )}

      {!loading && !doc && (
        <div className="panel p-4">
          <div className="mb-2 text-[10px] tracking-[0.16em] text-muted label-mono">まずはここから</div>
          <ol className="ml-4 list-decimal space-y-1.5 text-[12px] leading-relaxed text-fg">
            {OFFLINE_STEPS.map((s) => <li key={s}>{s}</li>)}
          </ol>
          {err && <p className="mt-2 text-[10px] text-muted">{err}</p>}
        </div>
      )}

      {/* 読みもの（はじめに・秘書としての使い方・自分のDB・ベータの注意 など） */}
      <div className="grid gap-3">
        {doc?.sections.map((s) => (
          <section key={s.id} className="panel p-4">
            <h3 className="text-[13px] text-fg-strong">{s.title}</h3>
            <p className="mt-1 text-[12px] leading-relaxed text-fg">{s.summary}</p>
            {s.steps.length > 0 && (
              <ul className="mt-2.5 space-y-1.5">
                {s.steps.map((step) => (
                  <li key={step} className="flex gap-2 text-[12px] leading-relaxed text-fg">
                    <span aria-hidden className="mt-[7px] h-1 w-1 shrink-0 rounded-full"
                          style={{ background: "var(--accent)" }} />
                    <span className="min-w-0">{step}</span>
                  </li>
                ))}
              </ul>
            )}
            {s.notes.length > 0 && (
              <ul className="mt-2.5 space-y-1 border-t border-panel pt-2.5">
                {s.notes.map((n) => (
                  <li key={n} className="text-[11px] leading-relaxed text-muted">※ {n}</li>
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>

      {/* 目次 — 画面が多いので、探している画面へ直接飛べるようにする */}
      {doc && doc.modes.length > 0 && (
        <>
          <div className="panel mt-3 p-3">
            <div className="mb-2 text-[10px] tracking-[0.16em] text-muted label-mono">
              画面いちらん（{doc.modes.length}）
            </div>
            <div className="flex flex-wrap gap-1.5">
              {doc.modes.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => jump(m.id)}
                  className="rounded-full border border-panel px-2.5 py-1 text-[10px] text-muted transition hover:border-[var(--line)] hover:text-fg-strong"
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>

          {/* 全モードの説明書 */}
          <div className="mt-3 grid gap-3">
            {doc.modes.map((m) => (
              <section
                key={m.id}
                ref={(el) => { if (el) anchors.set(m.id, el); }}
                className="panel scroll-mt-3 p-4"
              >
                {/* スマホでは写真を大きめに（小さすぎると中の文字が読めず、
                    説明書として役に立たない）。押せば全画面で拡大できる。 */}
                <div className="grid gap-3 sm:grid-cols-[190px_1fr]">
                  {/* 実画面（押すと拡大） */}
                  <button
                    type="button"
                    onClick={() => setZoom(m)}
                    aria-label={`${m.label} の画面を拡大`}
                    className="mx-auto w-[232px] shrink-0 overflow-hidden rounded-forge border border-panel transition hover:border-[var(--line)] sm:w-[190px]"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={m.image}
                      alt={`${m.label}（${m.name}）の画面`}
                      loading="lazy"
                      decoding="async"
                      className="block w-full"
                    />
                  </button>

                  <div className="min-w-0">
                    <h3 className="flex flex-wrap items-baseline gap-2">
                      <span className="text-[13px] text-fg-strong label-mono">{m.label}</span>
                      <span className="text-[11px] text-muted">{m.name}</span>
                    </h3>
                    <p className="mt-1 text-[12px] leading-relaxed text-fg">{m.what}</p>

                    {m.how.length > 0 && (
                      <ul className="mt-2.5 space-y-1.5">
                        {m.how.map((h) => (
                          <li key={h} className="flex gap-2 text-[12px] leading-relaxed text-fg">
                            <span aria-hidden className="mt-[7px] h-1 w-1 shrink-0 rounded-full"
                                  style={{ background: "var(--accent)" }} />
                            <span className="min-w-0">{h}</span>
                          </li>
                        ))}
                      </ul>
                    )}

                    {m.tips.length > 0 && (
                      <ul className="mt-2.5 space-y-1 border-t border-panel pt-2.5">
                        {m.tips.map((t) => (
                          <li key={t} className="text-[11px] leading-relaxed text-muted">※ {t}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </section>
            ))}
          </div>
        </>
      )}

      {zoom && <ZoomOverlay mode={zoom} onClose={() => setZoom(null)} />}
    </div>
  );
}

/** 画面写真の拡大。Escでも閉じられる。 */
function ZoomOverlay({ mode, onClose }: { mode: GuideMode; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // 親に perspective/rotateX が掛かっていると fixed がビューポート基準に
  // ならず、画面の外（スクロール分だけ上）に出てしまう。押しても何も
  // 起きないように見えるので、body へポータルする。
  return createPortal(
    <div
      className="fixed inset-0 z-[70] flex flex-col items-center justify-center gap-3 bg-black/85 p-4 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-label={`${mode.label} の画面`}
    >
      <div className="text-center">
        <span className="text-[12px] text-fg-strong label-mono">{mode.label}</span>
        <span className="ml-2 text-[11px] text-muted">{mode.name}</span>
      </div>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={mode.image}
        alt={`${mode.label}（${mode.name}）の画面`}
        className="max-h-[76vh] w-auto rounded-forge border border-panel"
      />
      <button
        type="button"
        onClick={onClose}
        className="rounded-forge border border-panel bg-[var(--btn-bg)] px-4 py-2 text-[11px] text-fg-strong label-mono"
      >
        閉じる
      </button>
    </div>,
    document.body,
  );
}
