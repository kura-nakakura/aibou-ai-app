"use client";

/**
 * Guide — アプリの使い方（初めての人が最初に開く画面）。
 *
 * 本文はバックエンドの guide.py が持つ。CHATが「使い方は？」と聞かれたときに
 * 答える内容と同じ出どころなので、説明が2つに割れて片方だけ古くなることがない。
 *
 * バックエンド未接続でも最低限の始め方は出す（新しい人が最初に開く画面で
 * 「接続してください」しか出ないのは案内として不親切なため）。ただし
 * 内蔵しているのは出だしの3行だけで、詳細は必ずサーバー側を見る。
 */

import { useEffect, useState } from "react";
import { API_URL, guideGet, type GuideDoc } from "@/lib/api";

/** 未接続時にだけ出す、最小限の始め方。 */
const OFFLINE_STEPS = [
  "下の CHAT に、やりたいことをそのまま書いてください（例：「明日15時に歯医者の予定を入れて」）",
  "右上の ⚙ → KEYCHAIN に AIの鍵（GEMINI_API_KEY か HUGGINGFACE_TOKEN）を1つ保存します",
  "接続できると、ここに詳しい使い方が出ます（設定 → DIAGNOSTICS で状態を確認できます）",
];

export default function Guide() {
  const [doc, setDoc] = useState<GuideDoc | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!API_URL) { setLoading(false); return; }
    guideGet()
      .then(setDoc)
      .catch(() => setErr("使い方を取得できませんでした（バックエンド未接続）"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="mx-auto w-full max-w-3xl pb-6">
      <div className="mb-3 text-center">
        <h2 className="brand-wordmark text-[20px] text-fg-strong">
          {doc?.app ?? "AIbou"} の使い方
        </h2>
        <p className="mt-1 text-[11px] text-muted">
          はじめての人はここから。困ったら CHAT で「使い方教えて」と聞いてもOKです。
        </p>
      </div>

      {/* 共有環境であることは、最初に目に入る場所で伝える */}
      {doc?.shared_data && (
        <div
          className="mb-3 rounded-forge border p-3 text-[11px] leading-relaxed"
          style={{ borderColor: "#ffd07f", color: "#ffd07f" }}
        >
          <b>ベータ版のお願い</b>
          <br />
          いまは1つの環境をみんなで共有しています。タスク・予定・ノートは利用者ごとに
          分かれておらず、ログインした人全員が同じデータを見ます。APIキーも共有です。
          個人的な内容や、人に見られたくない情報はまだ入れないでください。
        </div>
      )}

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
    </div>
  );
}
