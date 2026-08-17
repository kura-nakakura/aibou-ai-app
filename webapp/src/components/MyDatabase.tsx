"use client";

/**
 * MyDatabase — 「自分のSupabaseを接続する」設定。
 *
 * ログインは管理者のSupabaseで行い、タスク・予定・ノートなどのデータは
 * ここで繋いだ“その人自身の”Supabaseへ保存される。未接続のあいだは
 * どこにも保存されない（管理者のDBへ黙って書かない）ので、その状態は
 * はっきり画面に出す。
 *
 * service_role キーは強い権限を持つ。ここでは入力後は伏せて表示し、
 * サーバーは暗号化して保管し、APIはマスクした値しか返さない。
 */

import { useCallback, useEffect, useState } from "react";
import {
  API_URL, myDatabase, myDatabaseConnect, myDatabaseDisconnect,
  myDatabaseMigrate, myDatabaseTest, type MyDatabase as DbState,
} from "@/lib/api";

type Note = { text: string; tone: "error" | "info" | "ok" } | null;
const COLOR = { error: "#ff9b9b", info: "#ffd07f", ok: "#7fe0a8" } as const;

export default function MyDatabase() {
  const [state, setState] = useState<DbState | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"" | "test" | "connect" | "migrate" | "off">("");
  const [note, setNote] = useState<Note>(null);
  const [open, setOpen] = useState(false);

  const [url, setUrl] = useState("");
  const [key, setKey] = useState("");
  const [dbUrl, setDbUrl] = useState("");

  const reload = useCallback(async () => {
    const s = await myDatabase();
    setState(s);
    if (!s.connected) setOpen(true);      // 未接続の人には最初から入力欄を見せる
  }, []);

  useEffect(() => {
    if (!API_URL) { setLoading(false); return; }
    reload().catch(() => setNote({ text: "接続状態を取得できませんでした", tone: "error" }))
      .finally(() => setLoading(false));
  }, [reload]);

  if (!API_URL) {
    return (
      <div className="mb-4 rounded-forge border border-panel p-3 text-[11px] leading-relaxed text-muted">
        自分のデータベースの接続は、バックエンド接続後に使えます（DIAGNOSTICS参照）。
      </div>
    );
  }
  if (loading) {
    return <div className="mb-4 rounded-forge border border-panel p-3 text-center text-[10px] tracking-[0.2em] text-muted label-mono">◈ LOADING DB…</div>;
  }
  if (state && !state.available) {
    return (
      <div className="mb-4 rounded-forge border border-panel p-3 text-[11px] leading-relaxed text-muted">
        {state.reason ?? "ログインすると、自分のデータベースを接続できます。"}
      </div>
    );
  }

  const connected = Boolean(state?.connected);

  const run = async (kind: typeof busy, fn: () => Promise<Note>) => {
    setBusy(kind);
    setNote(null);
    try {
      setNote(await fn());
    } finally {
      setBusy("");
    }
  };

  const doTest = () => run("test", async () => {
    const r = await myDatabaseTest({ url: url.trim(), service_key: key.trim() });
    if (r.error) return { text: r.error, tone: "error" };
    return r.tables_ready
      ? { text: "繋がりました。テーブルも揃っています", tone: "ok" }
      : { text: "繋がりました。まだテーブルが無いので、接続後に「テーブルを作成」を押してください", tone: "info" };
  });

  const doConnect = () => run("connect", async () => {
    const r = await myDatabaseConnect({ url: url.trim(), service_key: key.trim(), db_url: dbUrl.trim() });
    if (r.error) return { text: r.error, tone: "error" };
    setKey("");                       // 画面に残さない
    await reload();
    setOpen(false);
    return r.tables_ready
      ? { text: "接続しました。以後このDBに保存されます", tone: "ok" }
      : { text: "接続しました。次に「テーブルを作成」を押してください", tone: "info" };
  });

  const doMigrate = () => run("migrate", async () => {
    const r = await myDatabaseMigrate();
    if (r.error) return { text: r.error, tone: "error" };
    if (r.skipped) return { text: r.reason ?? "作成をスキップしました", tone: "info" };
    await reload();
    return { text: `テーブルを用意しました（${r.tables ?? 0}件）`, tone: "ok" };
  });

  const doDisconnect = () => run("off", async () => {
    const r = await myDatabaseDisconnect();
    if (r.error) return { text: r.error, tone: "error" };
    await reload();
    setOpen(true);
    return { text: "接続を外しました。以後データは保存されません（DBは消していません）", tone: "info" };
  });

  return (
    <div className="mb-4 rounded-forge border border-panel p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-[10px] tracking-[0.2em] text-muted label-mono">自分のデータベース</span>
        <span className="shrink-0 text-[9px] tracking-[0.1em] label-mono"
              style={{ color: connected ? "#7fe0a8" : "#ffd07f" }}>
          ● {connected ? "接続済み" : "未接続"}
        </span>
      </div>

      {!connected && (
        <p className="mb-2 text-[10px] leading-relaxed" style={{ color: "#ffd07f" }}>
          いまは<b>どこにも保存されていません</b>。アプリを再起動すると消えます。
          自分の Supabase を繋ぐと、タスク・予定・ノートがあなたのDBに残ります。
        </p>
      )}

      {connected && state && (
        <div className="mb-2 grid gap-1 text-[11px] text-fg">
          <div className="flex min-w-0 justify-between gap-2">
            <span className="shrink-0 text-muted">保存先</span>
            <span className="min-w-0 truncate" title={state.url}>{state.url}</span>
          </div>
          <div className="flex justify-between gap-2">
            <span className="text-muted">service key</span>
            <span className="label-mono">{state.masked_key}</span>
          </div>
          <div className="flex justify-between gap-2">
            <span className="text-muted">テーブル作成用のDB接続</span>
            <span>{state.db_url_set ? "設定済み" : "未設定"}</span>
          </div>
        </div>
      )}

      {connected && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          <button type="button" onClick={() => void doMigrate()} disabled={busy !== ""}
                  className="rounded-forge border border-panel px-2.5 py-1.5 text-[10px] text-fg-strong label-mono disabled:opacity-40">
            {busy === "migrate" ? "作成中…" : "テーブルを作成"}
          </button>
          <button type="button" onClick={() => setOpen((v) => !v)} disabled={busy !== ""}
                  className="rounded-forge border border-panel px-2.5 py-1.5 text-[10px] text-fg-strong label-mono disabled:opacity-40">
            繋ぎ直す
          </button>
          <button type="button" onClick={() => void doDisconnect()} disabled={busy !== ""}
                  className="rounded-forge border border-panel px-2.5 py-1.5 text-[10px] text-[#ff9b9b] label-mono disabled:opacity-40">
            {busy === "off" ? "…" : "接続を外す"}
          </button>
        </div>
      )}

      {open && (
        <div className="grid gap-1.5 border-t border-panel pt-2.5">
          <label className="text-[9px] tracking-[0.16em] text-muted label-mono">Project URL</label>
          <input
            value={url}
            onChange={(e) => { setUrl(e.target.value); setNote(null); }}
            placeholder="https://xxxxxxxx.supabase.co"
            aria-label="Supabase の Project URL"
            autoCapitalize="none" autoCorrect="off" spellCheck={false} inputMode="url"
            className="min-h-[44px] w-full rounded-forge border border-[var(--input-bd)] bg-[var(--input-bg)] px-3 text-[13px] text-fg-strong placeholder:text-muted focus:border-[var(--line)] focus:outline-none"
          />

          <label className="mt-1 text-[9px] tracking-[0.16em] text-muted label-mono">service_role キー</label>
          <input
            value={key}
            onChange={(e) => { setKey(e.target.value); setNote(null); }}
            type="password"
            placeholder="eyJhbGciOi…"
            aria-label="Supabase の service_role キー"
            autoCapitalize="none" autoCorrect="off" spellCheck={false}
            className="min-h-[44px] w-full rounded-forge border border-[var(--input-bd)] bg-[var(--input-bg)] px-3 text-[13px] text-fg-strong placeholder:text-muted focus:border-[var(--line)] focus:outline-none"
          />

          <label className="mt-1 text-[9px] tracking-[0.16em] text-muted label-mono">
            DB接続URL（テーブル自動作成に使う・任意）
          </label>
          <input
            value={dbUrl}
            onChange={(e) => { setDbUrl(e.target.value); setNote(null); }}
            type="password"
            placeholder="postgresql://postgres:…@…pooler.supabase.com:5432/postgres"
            aria-label="テーブル作成用のDB接続URL"
            autoCapitalize="none" autoCorrect="off" spellCheck={false}
            className="min-h-[44px] w-full rounded-forge border border-[var(--input-bd)] bg-[var(--input-bg)] px-3 text-[13px] text-fg-strong placeholder:text-muted focus:border-[var(--line)] focus:outline-none"
          />

          <div className="mt-1 flex gap-1.5">
            <button type="button" onClick={() => void doTest()}
                    disabled={busy !== "" || !url.trim() || !key.trim()}
                    className="flex-1 rounded-forge border border-panel px-2 py-2 text-[10px] text-fg-strong label-mono disabled:opacity-30">
              {busy === "test" ? "確認中…" : "接続テスト"}
            </button>
            <button type="button" onClick={() => void doConnect()}
                    disabled={busy !== "" || !url.trim() || !key.trim()}
                    className="flex-1 rounded-forge border px-2 py-2 text-[10px] label-mono disabled:opacity-30"
                    style={{ borderColor: "var(--accent)", color: "var(--fg-strong)", background: "var(--btn-bg)" }}>
              {busy === "connect" ? "接続中…" : "接続する"}
            </button>
          </div>

          <details className="mt-1">
            <summary className="cursor-pointer text-[10px] text-muted">値のとり方（Supabaseの画面）</summary>
            <ol className="ml-4 mt-1 list-decimal space-y-1 text-[10px] leading-relaxed text-muted">
              <li>supabase.com で自分のプロジェクトを作る（無料枠でOK）</li>
              <li>Project Settings → API の「Project URL」と「service_role」をコピー</li>
              <li>Connect → Session pooler の postgresql://… をコピー（テーブル作成用）</li>
              <li>ここに貼って「接続テスト」→「接続する」→「テーブルを作成」</li>
            </ol>
          </details>
        </div>
      )}

      {note && (
        <p role="status" aria-live="polite"
           className="mt-2 text-[11px] leading-relaxed" style={{ color: COLOR[note.tone] }}>
          {note.text}
        </p>
      )}

      <p className="mt-2 text-[9px] leading-relaxed text-muted">
        service_role キーは強い権限を持ちます。サーバーで暗号化して保管し、画面には伏せ字でしか出しません。
        他人に渡さないでください。
      </p>
    </div>
  );
}
