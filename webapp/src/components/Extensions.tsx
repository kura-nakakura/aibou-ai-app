"use client";

/**
 * Extensions — 「拡張機能」モード。連携をサービス単位で選ぶ。
 *
 * これまでは設定のKEYCHAINに鍵の名前が縦に並ぶだけだった。
 * GITHUB_TOKEN と書かれていても、入れると何ができるようになるのかが
 * 分からないので、結局だれも入れない。
 *
 * ここでは「LINE」のような見慣れた名前と印を先に見せ、押したら
 * ①何ができるようになるか ②必要な値 ③取り方 ④保存 の順で出す。
 * つないだ直後に、その場で試せるようにもする（通知はテスト送信）。
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import {
  API_URL, deleteKey, googleAuthStartUrl, googleDisconnect, googleStatus,
  listKeys, myDatabase, profileGet, sendNotify, setKey,
} from "@/lib/api";
import {
  EXTENSIONS, GROUP_LABEL, GROUP_ORDER, isConnected, visibleExtensions,
  type Extension,
} from "@/lib/extensions";
import { explain } from "@/lib/needs";
import BrandIcon from "@/components/BrandIcon";
import MyDatabase from "@/components/MyDatabase";

export default function Extensions({ onNavigate }: { onNavigate?: (v: "guide") => void }) {
  const [keysSet, setKeysSet] = useState<Set<string>>(new Set());
  const [isOwner, setIsOwner] = useState<boolean | null>(null);
  const [google, setGoogle] = useState<{ configured: boolean; connected: boolean } | null>(null);
  const [dbOn, setDbOn] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<Extension | null>(null);

  const load = useCallback(async () => {
    if (!API_URL) { setLoading(false); return; }
    setError(null);
    const [keys, prof, g, db] = await Promise.all([
      listKeys().catch((e) => { setError(explain(e, "連携状況の読み込み")); return null; }),
      profileGet().catch(() => null),
      googleStatus().catch(() => null),
      myDatabase().catch(() => null),
    ]);
    if (keys) setKeysSet(new Set(keys.filter((k) => k.set).map((k) => k.name)));
    if (prof) setIsOwner(Boolean(prof.is_owner));
    setGoogle(g);
    // 既定DBに保存されている人も「保存先は決まっている」ので済み扱いにする
    setDbOn(Boolean(db?.connected) || Boolean(db?.using_server_db));
    setLoading(false);
  }, []);

  useEffect(() => { void load(); }, [load]);

  const exts = useMemo(() => visibleExtensions(isOwner), [isOwner]);

  /** 連携済みか。Googleは鍵だけでなく「許可」まで済んで初めて使える。 */
  const connectedOf = useCallback((e: Extension) => {
    if (e.kind === "oauth") return Boolean(google?.connected);
    if (e.kind === "database") return dbOn;
    return isConnected(e, keysSet);
  }, [google, keysSet, dbOn]);

  const doneCount = exts.filter((e) => connectedOf(e) === true).length;

  if (!API_URL) {
    return (
      <div className="panel p-6 text-center text-[11px] leading-relaxed text-muted">
        拡張機能は、バックエンドに繋がってから使えます。
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto pb-2">
      <div className="panel p-3">
        <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
          <span className="text-[10px] tracking-[0.2em] text-muted label-mono">拡張機能</span>
          <span className="text-[10px] text-muted label-mono">{doneCount} / {exts.length} 連携済み</span>
        </div>
        <p className="text-[11px] leading-relaxed text-fg">
          使いたいサービスを選んでつなぐと、その分だけできることが増えます。
          <span className="text-muted">つながなくても、CHATと基本の機能は動きます。</span>
        </p>
      </div>

      {error && <div className="panel p-3 text-[11px] leading-relaxed text-[#ff9b9b]">⚠️ {error}</div>}

      {loading ? (
        <div className="panel p-6 text-center text-[10px] tracking-[0.2em] text-muted label-mono">
          ◈ LOADING…
        </div>
      ) : (
        GROUP_ORDER.map((g) => {
          const items = exts.filter((e) => e.group === g);
          if (items.length === 0) return null;
          return (
            <div key={g}>
              <div className="mb-1.5 text-[10px] tracking-[0.2em] text-muted label-mono">
                {GROUP_LABEL[g]}
              </div>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {items.map((e) => (
                  <Card key={e.id} ext={e} state={connectedOf(e)} onOpen={() => setOpen(e)} />
                ))}
              </div>
            </div>
          );
        })
      )}

      <p className="px-1 text-[10px] leading-relaxed text-muted/70">
        入れた値はサーバーで暗号化して保管され、画面には伏せ字でしか出ません。
        いつでも「連携を外す」で消せます。
        {onNavigate && (
          <button type="button" onClick={() => onNavigate("guide")}
                  className="ml-1 text-[var(--accent)] underline">
            説明書を見る
          </button>
        )}
      </p>

      {open && (
        <Detail
          ext={open}
          connected={connectedOf(open)}
          google={google}
          onClose={() => setOpen(null)}
          onChanged={() => void load()}
        />
      )}
    </div>
  );
}

/* ── カード ───────────────────────────────────────────────────── */
function Card({ ext, state, onOpen }:
  { ext: Extension; state: boolean | null; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="panel flex w-full items-start gap-2.5 p-3 text-left transition hover:shadow-glow"
    >
      <span className="mt-0.5 shrink-0"><BrandIcon id={ext.id} size={24} /></span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <span className="truncate text-[13px] text-fg-strong">{ext.name}</span>
          {state === true && <span className="shrink-0 text-[10px]" style={{ color: "#60d394" }}>✓ 連携済み</span>}
        </span>
        <span className="mt-0.5 block text-[11px] leading-relaxed text-muted">{ext.tagline}</span>
      </span>
    </button>
  );
}

/* ── 詳細（本文に出す。祖先の transform に captured されないように） ── */
function Detail({ ext, connected, google, onClose, onChanged }: {
  ext: Extension;
  connected: boolean | null;
  google: { configured: boolean; connected: boolean } | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ text: string; ok: boolean } | null>(null);
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const save = async () => {
    setBusy(true);
    setNote(null);
    try {
      const entries = ext.fields
        .map((f) => [f.name, (values[f.name] ?? "").trim()] as const)
        .filter(([, v]) => v !== "");
      if (entries.length === 0) {
        setNote({ text: "値を入れてから保存してください", ok: false });
        return;
      }
      for (const [name, value] of entries) await setKey(name, value);
      setValues({});
      onChanged();
      setNote({ text: "保存しました", ok: true });
    } catch (e) {
      setNote({ text: explain(e, "保存"), ok: false });
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!window.confirm(`${ext.name} の連携を外しますか？（保存した値を消します）`)) return;
    setBusy(true);
    setNote(null);
    try {
      for (const f of ext.fields) await deleteKey(f.name).catch(() => false);
      onChanged();
      setNote({ text: "連携を外しました", ok: true });
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    setBusy(true);
    setNote(null);
    try {
      const r = await sendNotify(`AIbou のテスト送信です（${ext.name}）`);
      const mine = r.results?.find((x) => x.channel === ext.id);
      if (mine?.ok) setNote({ text: "送りました。届いているか確認してください", ok: true });
      else if (mine?.error) setNote({ text: mine.error, ok: false });
      else setNote({ text: "まだ設定が足りないため送れませんでした", ok: false });
    } catch (e) {
      setNote({ text: explain(e, "テスト送信"), ok: false });
    } finally {
      setBusy(false);
    }
  };

  const body = (
    <div className="fixed inset-0 z-[80] flex items-start justify-center overflow-y-auto bg-[rgba(4,6,12,0.72)] p-3 backdrop-blur-sm"
         onClick={onClose}>
      <div className="panel my-6 w-full max-w-lg p-4" onClick={(e) => e.stopPropagation()}>
        <div className="mb-2 flex items-start justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <BrandIcon id={ext.id} size={26} />
            <div className="min-w-0">
              <div className="truncate text-[15px] text-fg-strong">{ext.name}</div>
              <div className="text-[11px] text-muted">{ext.tagline}</div>
            </div>
          </div>
          <button type="button" onClick={onClose} aria-label="閉じる"
                  className="shrink-0 rounded-forge border border-panel px-2 py-1 text-[11px] text-muted">✕</button>
        </div>

        {connected === true && (
          <div className="mb-2 rounded-forge border p-2 text-[11px]"
               style={{ borderColor: "#60d39455", color: "#60d394" }}>
            ✓ 連携できています
          </div>
        )}

        {/* ① 何ができるようになるか。ここが「入れる理由」 */}
        <div className="mb-3 rounded-forge border border-panel p-2.5">
          <div className="mb-1 text-[10px] tracking-[0.16em] text-muted label-mono">
            連携すると、できるようになること
          </div>
          <ul className="ml-4 list-disc space-y-0.5 text-[11px] leading-relaxed text-fg">
            {ext.unlocks.map((u) => <li key={u}>{u}</li>)}
          </ul>
        </div>

        {ext.warning && (
          <p className="mb-3 rounded-forge border p-2 text-[11px] leading-relaxed"
             style={{ borderColor: "#ffd07f55", color: "#ffd07f" }}>
            {ext.warning}
          </p>
        )}

        {/* ② 保存先はここで直接つなぐ。
            以前は「設定→KEYCHAINへ」と案内していたが、拡張機能を開いた人が
            そこから設定できないなら、拡張機能である意味がない。 */}
        {ext.kind === "database" && (
          <div className="mb-3">
            <MyDatabase compact />
          </div>
        )}

        {/* ③ 値の入力 */}
        {ext.fields.length > 0 && (
          <div className="mb-3 grid gap-1.5">
            {ext.fields.map((f) => (
              <div key={f.name}>
                <label htmlFor={`ext-${f.name}`}
                       className="text-[10px] tracking-[0.14em] text-muted label-mono">
                  {f.label}
                </label>
                <input
                  id={`ext-${f.name}`}
                  value={values[f.name] ?? ""}
                  onChange={(e) => { setValues((v) => ({ ...v, [f.name]: e.target.value })); setNote(null); }}
                  type={f.secret ? "password" : "text"}
                  placeholder={f.placeholder ?? (connected ? "設定済み（変えるときだけ入力）" : "")}
                  /* ブラウザの自動入力に、保存済みのログイン情報を差し込まれないようにする */
                  name={`ext-${f.name}`}
                  autoComplete={f.secret ? "new-password" : "off"}
                  autoCapitalize="none" autoCorrect="off" spellCheck={false}
                  className="mt-0.5 min-h-[44px] w-full rounded-forge border border-[var(--input-bd)] bg-[var(--input-bg)] px-3 text-[13px] text-fg-strong placeholder:text-muted focus:border-[var(--line)] focus:outline-none"
                />
              </div>
            ))}
            <div className="mt-1 flex flex-wrap gap-1.5">
              <button type="button" onClick={() => void save()} disabled={busy}
                      className="rounded-forge border px-3 py-2 text-[11px] label-mono disabled:opacity-40"
                      style={{ borderColor: "var(--accent)", color: "var(--fg-strong)", background: "var(--btn-bg)" }}>
                {busy ? "…" : "保存する"}
              </button>
              {connected === true && (
                <button type="button" onClick={() => void remove()} disabled={busy}
                        className="rounded-forge border border-panel px-3 py-2 text-[11px] text-[#ff9b9b] label-mono disabled:opacity-40">
                  連携を外す
                </button>
              )}
              {/* つないだ直後に試せる。届かないことに後で気づくのが一番困る */}
              {ext.group === "notify" && connected === true && (
                <button type="button" onClick={() => void test()} disabled={busy}
                        className="rounded-forge border border-panel px-3 py-2 text-[11px] text-fg-strong label-mono disabled:opacity-40">
                  テスト送信
                </button>
              )}
            </div>
          </div>
        )}

        {/* ④ Google は許可（OAuth）まで済ませて初めて使える */}
        {ext.kind === "oauth" && (
          <div className="mb-3 flex flex-wrap items-center gap-1.5">
            {google?.connected ? (
              <button type="button" disabled={busy}
                      onClick={() => { setBusy(true); void googleDisconnect().finally(() => { setBusy(false); onChanged(); }); }}
                      className="rounded-forge border border-panel px-3 py-2 text-[11px] text-[#ff9b9b] label-mono disabled:opacity-40">
                Googleとの接続を解除
              </button>
            ) : (
              <a href={googleAuthStartUrl()} target="_blank" rel="noreferrer"
                 className="rounded-forge border px-3 py-2 text-[11px] label-mono"
                 style={{ borderColor: "var(--accent)", color: "var(--fg-strong)", background: "var(--btn-bg)" }}>
                Googleと接続する
              </a>
            )}
            {!google?.configured && (
              <span className="text-[10px] text-muted">
                先に上の2つを保存してください
              </span>
            )}
          </div>
        )}

        {note && (
          <p role="status" aria-live="polite" className="mb-2 text-[11px] leading-relaxed"
             style={{ color: note.ok ? "#60d394" : "#ff9b9b" }}>
            {note.text}
          </p>
        )}

        {/* ⑤ 取り方。ここが無いと、値を持っていない人はここで止まる */}
        <details open={connected !== true}>
          <summary className="cursor-pointer text-[11px] text-[var(--accent)]">
            値のとり方（画面の手順）
          </summary>
          <ol className="ml-4 mt-1.5 list-decimal space-y-1 text-[11px] leading-relaxed text-muted">
            {ext.howto.map((h) => <li key={h}>{h}</li>)}
          </ol>
        </details>
      </div>
    </div>
  );

  // 祖先に transform があると position:fixed がその中に閉じ込められる（GUIDEで踏んだ）
  return mounted ? createPortal(body, document.body) : null;
}
