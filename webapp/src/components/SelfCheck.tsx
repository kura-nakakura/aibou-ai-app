"use client";

/**
 * SelfCheck — 「うまく動かない」ときに、原因をアプリ自身に答えさせる。
 *
 * 何かが動かないとき、画面に出るのは「401」のような数字だけで、利用者には
 * 手の打ちようがない。管理者に伝えようにも、何を伝えればいいか分からない。
 * （実際、原因を突き止めるのに何往復もかかった。）
 *
 * ボタン1つで結果を出し、そのまま管理者へ送れる形にする。
 * サーバーは秘密を返さない（設定の有無と、受け取ったものの「形」だけ）。
 */

import { useState } from "react";
import { API_URL, diagnose } from "@/lib/api";
import { explain } from "@/lib/needs";

export default function SelfCheck() {
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const run = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await diagnose());
    } catch (e) {
      setError(explain(e, "自己診断"));
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    const text = error
      ? `AIbou 自己診断\n接続先: ${API_URL || "(未設定)"}\nエラー: ${error}`
      : `AIbou 自己診断\n接続先: ${API_URL || "(未設定)"}\n`
        + JSON.stringify(result, null, 2);
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch { /* コピーできない環境では、画面の内容を見せて手で送ってもらう */ }
  };

  const ok = result?.["通るか"] === true;

  return (
    <div className="rounded-forge border border-panel p-3">
      <div className="mb-1 text-[10px] tracking-[0.2em] text-muted label-mono">
        うまく動かないとき
      </div>
      <p className="mb-2 text-[11px] leading-relaxed text-fg">
        エラーが出て困ったら、これを押してください。原因を調べて、そのまま
        管理者に送れる形で出します。
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void run()}
          disabled={busy || !API_URL}
          className="rounded-forge border border-[var(--line)] bg-[var(--btn-bg)] px-3 py-1.5 text-[10px] tracking-[0.12em] text-fg-strong disabled:opacity-40 label-mono"
        >
          {busy ? "調べています…" : "◈ 自己診断する"}
        </button>
        {(result || error) && (
          <button
            type="button"
            onClick={() => void copy()}
            className="text-[10px] text-[var(--accent)] underline"
          >
            {copied ? "✓ コピーしました" : "結果をコピー（管理者に送る）"}
          </button>
        )}
      </div>

      {!API_URL && (
        <p className="mt-2 text-[11px] text-muted">
          接続先が設定されていないため、診断できません。管理者に連絡してください。
        </p>
      )}

      {error && (
        <p className="mt-2 text-[11px] leading-relaxed" style={{ color: "#ff9b9b" }}>
          {error}
        </p>
      )}

      {result && (
        <div className="mt-3">
          {/* いちばん知りたいのは「使える状態か」。最初に大きく出す */}
          <div
            className="mb-2 rounded-forge border p-2.5"
            style={{ borderColor: ok ? "#60d39455" : "#ff9b9b55" }}
          >
            <div className="text-[11px]" style={{ color: ok ? "#60d394" : "#ff9b9b" }}>
              {ok ? "✓ サーバーとのやりとりは通っています" : "⚠ サーバーに断られています"}
            </div>
            {typeof result["理由"] === "string" && (
              <p className="mt-1 text-[11px] leading-relaxed text-fg">{String(result["理由"])}</p>
            )}
          </div>

          {/* 残りはそのまま並べる。項目が増えても勝手に出る */}
          <div className="grid gap-2">
            {Object.entries(result)
              .filter(([k]) => k !== "通るか" && k !== "理由")
              .map(([k, v]) => (
                <Section key={k} label={k} value={v} />
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** 1項目。中が入れ子なら、そのまま並べる。 */
function Section({ label, value }: { label: string; value: unknown }) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return (
      <div>
        <div className="mb-1 text-[10px] tracking-[0.16em] text-muted label-mono">{label}</div>
        <div className="grid gap-0.5">
          {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
            <div key={k} className="flex items-baseline justify-between gap-2 text-[11px]">
              <span className="min-w-0 break-all text-muted">{k}</span>
              <Value v={v} />
            </div>
          ))}
        </div>
      </div>
    );
  }
  return (
    <div className="flex items-baseline justify-between gap-2 text-[11px]">
      <span className="text-muted">{label}</span>
      <Value v={value} />
    </div>
  );
}

function Value({ v }: { v: unknown }) {
  if (typeof v === "boolean") {
    return (
      <span className="shrink-0 text-[11px]" style={{ color: v ? "#60d394" : "var(--muted)" }}>
        {v ? "設定済み" : "未設定"}
      </span>
    );
  }
  return (
    <span className="shrink-0 break-all text-right text-[11px] text-fg">
      {Array.isArray(v) ? v.join(" / ") : String(v)}
    </span>
  );
}
