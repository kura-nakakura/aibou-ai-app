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
import { PolicyBody } from "@/components/Policy";
import { SETUP_STEPS, type SetupStep } from "@/lib/setup";

export default function Guide() {
  const [doc, setDoc] = useState<GuideDoc | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [zoom, setZoom] = useState<GuideMode | null>(null);
  const [policyOpen, setPolicyOpen] = useState(false);
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

      {/* はじめる手順 — 必ず出す。
          これは「まだ何も繋がっていない人」が読むもの。バックエンドから
          取ってくる作りだと、繋がっていないときに手順ごと消えてしまい、
          「自分のDBを繋ぎたいのに繋ぎ方が書いていない」状態になる。 */}
      <section className="panel mb-3 p-4">
        <h3 className="text-[13px] text-fg-strong">はじめる手順（初回だけ）</h3>
        <p className="mt-1 text-[11px] leading-relaxed text-muted">
          上から順にやれば終わります。3の「SQL」は、意味が分からなくても
          コピーして貼るだけで大丈夫です。
        </p>
        <div className="mt-3 grid gap-2.5">
          {SETUP_STEPS.map((s) => <SetupStepCard key={s.id} step={s} />)}
        </div>
      </section>

      {loading && (
        <div className="panel mb-3 p-4 text-center text-[10px] tracking-[0.2em] text-muted label-mono">
          ◈ LOADING GUIDE…
        </div>
      )}

      {!loading && !doc && (
        <div className="panel mb-3 p-4">
          <p className="text-[12px] leading-relaxed text-fg">
            各画面の使い方（写真つき）は、バックエンドに繋がると、この下に出ます。
          </p>
          {err && <p className="mt-1.5 text-[11px] text-muted">{err}</p>}
          <p className="mt-1.5 text-[11px] text-muted">
            上の手順は接続に関係なく読めます。まずは 1 から進めてください。
          </p>
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

      {/* データの扱い — 説明書からもいつでも読めるようにする */}
      <section className="panel mt-3 p-4">
        <h3 className="text-[13px] text-fg-strong">プライバシーと利用について</h3>
        <p className="mt-1 text-[11px] leading-relaxed text-muted">
          データがどこに入るか、外部のどこへ送られるか、管理者に何ができるか。
        </p>
        <button
          type="button"
          onClick={() => setPolicyOpen((v) => !v)}
          className="mt-2 min-h-[40px] text-[11px] text-[var(--accent)] underline"
        >
          {policyOpen ? "閉じる" : "全文を読む"}
        </button>
        {policyOpen && <div className="mt-3"><PolicyBody /></div>}
      </section>

      {zoom && <ZoomOverlay mode={zoom} onClose={() => setZoom(null)} />}
    </div>
  );
}

/**
 * はじめる手順の1ステップ。
 *
 * 貼り付ける中身（SQL）は長いので、既定では畳んでおく。ボタン1つで
 * クリップボードに入るようにしないと、スマホでは全選択すら難しい。
 */
function SetupStepCard({ step }: { step: SetupStep }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [code, setCode] = useState<string | null>(null);
  const [codeErr, setCodeErr] = useState(false);

  // 貼り付けるSQLは、アプリ自身が配信しているファイルから取る。
  // バックエンドに依存させると、繋がっていない人がSQLを取れなくなる。
  useEffect(() => {
    if (!step.codeUrl) return;
    let alive = true;
    fetch(step.codeUrl, { cache: "force-cache" })
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status)))))
      .then((t) => { if (alive) setCode(t); })
      .catch(() => { if (alive) setCodeErr(true); });
    return () => { alive = false; };
  }, [step.codeUrl]);

  const copy = async () => {
    if (!code) return;
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setOpen(true);      // コピーできない環境では、せめて中身を出す
    }
  };

  return (
    // min-w-0 が無いと、中の <pre> の長い行が親を押し広げ、画面全体が
    // 横スクロールしてしまう（グリッド／フレックスの子は既定で縮まないため）。
    <div className="min-w-0 rounded-forge border border-panel p-3">
      <h4 className="text-[12px] text-fg-strong">{step.title}</h4>
      {step.detail && (
        <p className="mt-1 text-[11px] leading-relaxed text-muted">{step.detail}</p>
      )}
      <ol className="mt-2 ml-4 list-decimal space-y-1 text-[12px] leading-relaxed text-fg">
        {step.steps.map((s) => <li key={s}>{s}</li>)}
      </ol>

      {step.codeUrl && (
        <div className="mt-2.5">
          {code ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={copy}
                  className="rounded-forge border border-[var(--line)] bg-[var(--btn-bg)] px-3 py-1.5 text-[10px] tracking-[0.12em] text-fg-strong label-mono"
                >
                  {copied ? "✓ コピーしました" : "⧉ SQLをコピー"}
                </button>
                <button
                  type="button"
                  onClick={() => setOpen((v) => !v)}
                  className="text-[10px] text-muted underline"
                >
                  {open ? "中身を隠す" : "中身を見る"}
                </button>
                <span className="text-[10px] text-muted">{code.split("\n").length} 行</span>
              </div>
              {step.codeLabel && (
                <p className="mt-1 text-[10px] text-muted">{step.codeLabel}</p>
              )}
              {open && (
                <pre className="mt-2 max-h-64 w-full max-w-full overflow-auto rounded-forge border border-panel bg-[var(--input-bg)] p-2.5 text-[10px] leading-relaxed text-fg">
                  <code>{code}</code>
                </pre>
              )}
            </>
          ) : codeErr ? (
            <p className="text-[11px] text-muted">
              SQLを読み込めませんでした。
              <a href={step.codeUrl} target="_blank" rel="noopener noreferrer"
                 className="ml-1 text-[var(--accent)] underline">
                こちらから開いて
              </a>
              コピーしてください。
            </p>
          ) : (
            <p className="text-[10px] text-muted label-mono">SQL を読み込み中…</p>
          )}
        </div>
      )}

      {step.caution && step.caution.length > 0 && (
        <ul className="mt-2.5 space-y-1 border-t border-panel pt-2.5">
          {step.caution.map((c) => (
            <li key={c} className="text-[11px] leading-relaxed text-muted">※ {c}</li>
          ))}
        </ul>
      )}
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
