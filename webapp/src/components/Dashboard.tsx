"use client";

/**
 * Dashboard — BOARD モード：Miro風ホワイトボード + ノーコード自動化（Zapier風）.
 *
 * タブ構成:
 *  - WHITEBOARD（既定）… 付箋・接続・パン/ズームの無限キャンバス（Whiteboard.tsx）
 *  - AUTOMATION … 「トリガー → ステップ」のフローをカードで組み立てるビルダー
 */

import { motion, AnimatePresence } from "framer-motion";
import { useCallback, useEffect, useState } from "react";
import {
  automationsList,
  automationsCreate,
  automationsDelete,
  automationsRun,
  evolvePropose,
  studioListAIs,
  vaultList,
  scheduleAdd,
  type Automation,
  type StudioAI,
  type VaultNotebook,
  type AutomationStep,
  type StepType,
  type AutomationRunResult,
} from "@/lib/api";
import Tilt3D from "@/components/Tilt3D";
import Whiteboard from "@/components/Whiteboard";

const STEP_META: Record<StepType, { label: string; color: string; field: string; placeholder: string }> = {
  ai_generate: { label: "AI生成", color: "#00f3ff", field: "prompt", placeholder: "{input}を要約して…" },
  notify: { label: "通知", color: "#60d394", field: "message", placeholder: "完了しました: {input}" },
  create_task: { label: "タスク作成", color: "#ffd060", field: "title", placeholder: "タスク名…" },
};

// Miro/Zapier-style template chips — quick-start automations.
const TEMPLATES = [
  "毎朝トレンドを要約してLINEに通知する",
  "問い合わせ内容を整理してタスク化する",
  "週次レポートを自動生成する",
  "テーマからSNS投稿案を作る",
  "アイデアを出して箇条書きに整理する",
];

export default function Dashboard() {
  const [tab, setTab] = useState<"board" | "auto">("board");

  // Restore the last tab (whiteboard is the default).
  useEffect(() => {
    try {
      if (localStorage.getItem("forge_board_tab") === "auto") setTab("auto");
    } catch { /* ignore */ }
  }, []);
  useEffect(() => {
    try { localStorage.setItem("forge_board_tab", tab); } catch { /* ignore */ }
  }, [tab]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      {/* Tab bar */}
      <div className="flex items-center gap-1.5">
        {([
          { key: "board", label: "⊞ WHITEBOARD" },
          { key: "auto", label: "⚡ AUTOMATION" },
        ] as const).map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            aria-pressed={tab === t.key}
            className="rounded-forge border px-3 py-1.5 text-[10px] tracking-[0.16em] transition label-mono"
            style={{
              borderColor: tab === t.key ? "var(--accent)" : "var(--panel-bd)",
              color: tab === t.key ? "var(--fg-strong)" : "var(--muted)",
              background: tab === t.key ? "var(--btn-bg)" : "transparent",
              boxShadow: tab === t.key ? "0 0 10px var(--glow)" : "none",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1">
        {tab === "board" ? <Whiteboard /> : <AutomationBoard />}
      </div>
    </div>
  );
}

function AutomationBoard() {
  const [flows, setFlows] = useState<Automation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  // Zapier-copilot style natural-language creation
  const [nl, setNl] = useState("");
  const [nlBusy, setNlBusy] = useState(false);
  const [nlNote, setNlNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setFlows(await automationsList());
      setError(null);
    } catch {
      setError("バックエンド未接続です。自動化はバックエンド接続後に利用できます。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  // Natural language → automation (via the evolve engine, with a safe fallback).
  const createFromNL = async (text: string) => {
    const wish = text.trim();
    if (!wish || nlBusy) return;
    setNlBusy(true);
    setNlNote(null);
    setError(null);
    try {
      let name = wish.slice(0, 32);
      let steps: AutomationStep[] = [{ type: "ai_generate", name: "AI生成", params: { prompt: wish + "\n\n対象: {input}" } }];
      try {
        const p = await evolvePropose(wish);
        if (p.type === "automation" && Array.isArray((p.params as { steps?: unknown }).steps)) {
          steps = (p.params as { steps: AutomationStep[] }).steps;
          name = String((p.params as { name?: string }).name || name);
        }
      } catch {
        /* evolve unavailable → keep the single-step fallback */
      }
      const f = await automationsCreate(name, steps);
      setFlows((prev) => [f, ...prev]);
      setNl("");
      setNlNote(`「${f.name}」を作成しました（${f.steps.length} ステップ）。`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "自動化の作成に失敗しました（バックエンド未接続の可能性）");
    } finally {
      setNlBusy(false);
    }
  };

  return (
    <div className="relative h-full min-h-0 overflow-y-auto pb-4">
      {/* Miro-style canvas backdrop */}
      <div aria-hidden className="forge-grid pointer-events-none absolute inset-0 opacity-50" />

      <div className="relative z-10 mx-auto flex w-full max-w-5xl flex-col gap-4 pt-1">
        {/* Zapier-copilot style creation hero (subtle 3D tilt) */}
        <Tilt3D className="mx-auto w-full max-w-3xl" max={3}>
        <div className="glass-silver w-full p-5 text-center">
          <div className="mb-1 flex items-center justify-center gap-2">
            <span className="grid h-7 w-7 place-items-center rounded-full border border-[var(--line)] text-[var(--accent)]"><SparkIcon /></span>
            <span className="text-[10px] tracking-[0.24em] text-muted label-mono">AUTOMATION COPILOT</span>
          </div>
          <h2 className="label-mono text-glow text-sm text-fg-strong">何を自動化しますか？</h2>

          <div className="mt-3 flex items-end gap-2 rounded-forge border border-[var(--input-bd)] bg-[var(--input-bg)] p-2 text-left focus-within:border-[var(--line)]">
            <textarea
              value={nl}
              onChange={(e) => setNl(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing && !e.shiftKey) { e.preventDefault(); void createFromNL(nl); } }}
              rows={2}
              placeholder="やりたいことを自然言語で…（例：毎朝ニュースを要約してLINEに送る）"
              className="min-h-[2.5rem] flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-fg-strong placeholder:text-muted focus:outline-none"
            />
            <button
              type="button"
              onClick={() => void createFromNL(nl)}
              disabled={nlBusy || !nl.trim()}
              className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-[var(--line)] bg-[var(--btn-bg)] text-fg-strong shadow-glow transition hover:shadow-glow-strong disabled:opacity-40"
              aria-label="Create automation"
            >
              {nlBusy ? "…" : "↑"}
            </button>
          </div>

          {/* Template chips (Miro-style quick starts) */}
          <div className="mt-3 flex flex-wrap justify-center gap-1.5">
            {TEMPLATES.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setNl(t)}
                className="rounded-full border border-panel px-3 py-1.5 text-[11px] text-muted transition hover:border-[var(--line)] hover:text-fg-strong"
              >
                {t}
              </button>
            ))}
          </div>

          <div className="mt-3 flex items-center justify-center gap-4">
            <button
              type="button"
              onClick={() => setShowForm((s) => !s)}
              className="text-[10px] tracking-[0.16em] text-[var(--accent)] hover:underline label-mono"
            >
              {showForm ? "▲ ビルダーを閉じる" : "⊞ 手動ビルダーで細かく作る"}
            </button>
          </div>

          {nlNote && <p className="mt-2 text-[11px] text-[var(--accent)] label-mono">◈ {nlNote}</p>}
          {error && <p className="mt-2 text-[11px] text-[#ff9b9b]">⚠️ {error}</p>}
        </div>
        </Tilt3D>

        {/* Manual builder (Zapier step editor) */}
        <AnimatePresence>
          {showForm && (
            <motion.div
              className="mx-auto w-full max-w-3xl"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
            >
              <FlowBuilder
                onCreated={(f) => { setFlows((p) => [f, ...p]); setShowForm(false); }}
                onError={setError}
              />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Created automations — cards on the canvas */}
        {loading ? (
          <motion.div className="mx-auto max-w-3xl panel p-4 text-center text-[11px] tracking-[0.2em] text-muted label-mono" animate={{ opacity: [0.4, 1, 0.4] }} transition={{ duration: 1.4, repeat: Infinity }}>
            ◈ LOADING BOARD…
          </motion.div>
        ) : flows.length === 0 ? (
          <div className="mx-auto max-w-3xl rounded-forge border border-dashed border-panel p-6 text-center text-[11px] tracking-[0.18em] text-muted/70 label-mono">
            まだ自動化はありません。上で作成すると、ここにカードで並びます。
          </div>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {flows.map((f) => (
              <FlowCard key={f.id} flow={f} onDelete={async () => {
                if (!window.confirm(`自動化「${f.name}」を削除しますか？`)) return;
                try { await automationsDelete(f.id); setFlows((p) => p.filter((x) => x.id !== f.id)); }
                catch { setError("削除に失敗しました（バックエンド未接続の可能性）"); }
              }} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SparkIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z" />
    </svg>
  );
}

function FlowBuilder({ onCreated, onError }: { onCreated: (f: Automation) => void; onError: (e: string | null) => void }) {
  const [name, setName] = useState("");
  const [steps, setSteps] = useState<AutomationStep[]>([{ type: "ai_generate", name: "AI生成", params: {} }]);
  const [saving, setSaving] = useState(false);
  // トリガー：手動 or 毎日この時刻（scheduler経由で実際に発火する）
  const [trigger, setTrigger] = useState<"manual" | "schedule">("manual");
  const [atTime, setAtTime] = useState("08:00");
  // ステップに割り当てる候補（AI STUDIO のカスタムAI / VAULT のノートブック）
  const [ais, setAis] = useState<StudioAI[]>([]);
  const [notebooks, setNotebooks] = useState<VaultNotebook[]>([]);

  useEffect(() => {
    let alive = true;
    studioListAIs().then((v) => { if (alive) setAis(v); }).catch(() => { /* 任意項目 */ });
    vaultList().then((v) => { if (alive) setNotebooks(v); }).catch(() => { /* 任意項目 */ });
    return () => { alive = false; };
  }, []);

  const addStep = () => setSteps((p) => [...p, { type: "ai_generate", name: "AI生成", params: {} }]);
  const removeStep = (i: number) => setSteps((p) => p.filter((_, idx) => idx !== i));
  const updateType = (i: number, type: StepType) =>
    setSteps((p) => p.map((s, idx) => (idx === i ? { type, name: STEP_META[type].label, params: {} } : s)));
  const updateParam = (i: number, value: string) =>
    setSteps((p) => p.map((s, idx) => (idx === i ? { ...s, params: { [STEP_META[s.type].field]: value } } : s)));
  /** 担当AI・根拠資料・条件（AI STUDIO のワークフローと共通の拡張）。 */
  const updateExtra = (i: number, key: "ai_id" | "notebook_id" | "when", value: string) =>
    setSteps((p) => p.map((s, idx) => (idx === i ? { ...s, [key]: value } : s)));

  const create = async () => {
    if (!name.trim() || saving) return;
    setSaving(true);
    onError(null);
    try {
      const f = await automationsCreate(name.trim(), steps,
        trigger === "schedule" ? { type: "schedule" } : { type: "manual" });
      // 毎日実行は scheduler に登録して初めて発火する。
      // ここを繋いでいなかったので、これまで「毎朝〜」は動かなかった。
      if (trigger === "schedule") {
        try {
          await scheduleAdd("", atTime, "daily", f.id);
        } catch {
          onError("自動化は作成しましたが、定期実行の登録に失敗しました");
        }
      }
      setName("");
      setSteps([{ type: "ai_generate", name: "AI生成", params: {} }]);
      setTrigger("manual");
      onCreated(f);
    } catch (e) {
      onError(e instanceof Error ? e.message : "自動化の作成に失敗しました");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="panel p-3">
      <label className="mb-1 block text-[10px] tracking-[0.2em] text-muted label-mono">AUTOMATION NAME</label>
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="例：毎朝のニュース要約 → LINE通知"
        className="mb-3 w-full rounded-forge border border-[var(--input-bd)] bg-[var(--input-bg)] px-3 py-2 text-sm text-fg-strong placeholder:text-muted focus:border-[var(--line)] focus:outline-none"
      />

      <div className="mb-1 text-[10px] tracking-[0.2em] text-muted label-mono">STEPS</div>
      <div className="flex flex-col gap-1.5">
        {/* Trigger node (visual) */}
        {/* トリガー — 手動 / 毎日この時刻 */}
        <div className="rounded-forge border border-dashed border-panel px-3 py-2">
          <div className="flex flex-wrap items-center justify-center gap-1.5">
            <span className="text-[10px] tracking-[0.16em] text-muted label-mono">⚡ TRIGGER</span>
            {([["manual", "手動で実行"], ["schedule", "毎日この時刻"]] as const).map(([k, label]) => (
              <button key={k} type="button" onClick={() => setTrigger(k)} aria-pressed={trigger === k}
                className="rounded-full border px-2.5 py-0.5 text-[10px] label-mono"
                style={{
                  borderColor: trigger === k ? "var(--accent)" : "var(--panel-bd)",
                  color: trigger === k ? "var(--fg-strong)" : "var(--muted)",
                }}>
                {label}
              </button>
            ))}
            {trigger === "schedule" && (
              <input type="time" value={atTime} onChange={(e) => setAtTime(e.target.value)}
                aria-label="実行時刻"
                className="rounded-forge border border-[var(--input-bd)] bg-[var(--input-bg)] px-2 py-0.5 text-[11px] text-fg-strong focus:outline-none" />
            )}
          </div>
          {trigger === "schedule" && (
            <p className="mt-1 text-center text-[9px] leading-relaxed text-muted">
              バックエンドが動いている間、毎日この時刻に自動で実行して結果を通知します
            </p>
          )}
        </div>
        {steps.map((s, i) => (
          <div key={i}>
            <Connector />
            <div className="rounded-forge border border-panel p-2" style={{ borderLeftColor: STEP_META[s.type].color, borderLeftWidth: 2 }}>
              <div className="mb-1.5 flex items-center gap-2">
                <select
                  value={s.type}
                  onChange={(e) => updateType(i, e.target.value as StepType)}
                  className="rounded-forge border border-[var(--input-bd)] bg-[var(--input-bg)] px-2 py-1 text-[11px] text-fg-strong focus:outline-none"
                >
                  {(Object.keys(STEP_META) as StepType[]).map((t) => (
                    <option key={t} value={t} className="bg-[#0a0e16]">{STEP_META[t].label}</option>
                  ))}
                </select>
                <span className="text-[9px] text-muted label-mono">STEP {i + 1}</span>
                {steps.length > 1 && (
                  <button type="button" onClick={() => removeStep(i)} className="ml-auto text-[11px] text-[#ff6b6b]">✕</button>
                )}
              </div>
              <input
                value={s.params?.[STEP_META[s.type].field] ?? ""}
                onChange={(e) => updateParam(i, e.target.value)}
                placeholder={STEP_META[s.type].placeholder}
                aria-label={`ステップ${i + 1}の内容`}
                className="w-full rounded-forge border border-[var(--input-bd)] bg-[var(--input-bg)] px-2.5 py-1.5 text-sm text-fg-strong placeholder:text-muted focus:border-[var(--line)] focus:outline-none"
              />

              {/* AI STUDIO のワークフローと共通の拡張。AI生成のステップだけ
                  担当AIと根拠資料が意味を持つので、そこだけ出す。 */}
              {s.type === "ai_generate" && (
                <div className="mt-1.5 grid gap-1.5 sm:grid-cols-2">
                  <label className="flex flex-col gap-0.5">
                    <span className="text-[9px] tracking-[0.14em] text-muted label-mono">担当AI</span>
                    <select value={s.ai_id ?? ""} onChange={(e) => updateExtra(i, "ai_id", e.target.value)}
                      aria-label={`ステップ${i + 1}の担当AI`}
                      className="rounded-forge border border-[var(--input-bd)] bg-[var(--input-bg)] px-2 py-1 text-[11px] text-fg-strong focus:outline-none">
                      <option value="" className="bg-[#0a0e16]">指定なし</option>
                      {ais.map((a) => <option key={a.id} value={a.id} className="bg-[#0a0e16]">{a.name}</option>)}
                    </select>
                  </label>
                  <label className="flex flex-col gap-0.5">
                    <span className="text-[9px] tracking-[0.14em] text-muted label-mono">根拠資料（VAULT）</span>
                    <select value={s.notebook_id ?? ""} onChange={(e) => updateExtra(i, "notebook_id", e.target.value)}
                      aria-label={`ステップ${i + 1}の根拠資料`}
                      className="rounded-forge border border-[var(--input-bd)] bg-[var(--input-bg)] px-2 py-1 text-[11px] text-fg-strong focus:outline-none">
                      <option value="" className="bg-[#0a0e16]">使わない</option>
                      {notebooks.map((n) => <option key={n.id} value={n.id} className="bg-[#0a0e16]">{n.name}</option>)}
                    </select>
                  </label>
                </div>
              )}
              <label className="mt-1.5 flex flex-col gap-0.5">
                <span className="text-[9px] tracking-[0.14em] text-muted label-mono">実行する条件（空なら必ず実行）</span>
                <input value={s.when ?? ""} onChange={(e) => updateExtra(i, "when", e.target.value)}
                  aria-label={`ステップ${i + 1}の条件`}
                  placeholder="例：要約が3行を超えるとき"
                  className="rounded-forge border border-[var(--input-bd)] bg-[var(--input-bg)] px-2 py-1 text-[11px] text-fg-strong placeholder:text-muted focus:outline-none" />
              </label>
            </div>
          </div>
        ))}
      </div>

      <button type="button" onClick={addStep} className="mt-2 w-full rounded-forge border border-dashed border-panel py-1.5 text-[10px] tracking-[0.16em] text-muted hover:text-fg-strong label-mono">
        + ADD STEP
      </button>

      <button
        type="button"
        onClick={() => void create()}
        disabled={saving || !name.trim()}
        className="mt-2 w-full rounded-forge border border-[var(--line)] bg-[var(--btn-bg)] py-2.5 text-[11px] tracking-[0.2em] text-fg-strong shadow-glow transition hover:shadow-glow-strong disabled:opacity-40 label-mono"
      >
        {saving ? "SAVING…" : "CREATE AUTOMATION"}
      </button>
    </div>
  );
}

function FlowCard({ flow, onDelete }: { flow: Automation; onDelete: () => void }) {
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<AutomationRunResult | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setErr(null);
    setResult(null);
    try {
      setResult(await automationsRun(flow.id, input));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "実行に失敗しました");
    } finally {
      setRunning(false);
    }
  };

  return (
    <Tilt3D max={5}>
    <div className="panel p-3">
      <div className="flex items-center justify-between">
        <span className="text-sm text-fg-strong">{flow.name}</span>
        <button type="button" onClick={() => void onDelete()} className="text-[10px] text-[#ff8888] label-mono">✕</button>
      </div>

      {/* Visual flow: trigger → steps */}
      <div className="mt-2 flex flex-col gap-1">
        <div className="rounded-forge border border-dashed border-panel px-2 py-1 text-center text-[9px] tracking-[0.16em] text-muted label-mono">⚡ TRIGGER</div>
        {(flow.steps || []).map((s) => (
          <div key={s.id ?? s.n}>
            <Connector />
            <div className="rounded-forge border border-panel px-2 py-1.5 text-[11px] text-fg" style={{ borderLeftColor: STEP_META[s.type]?.color ?? "var(--accent)", borderLeftWidth: 2 }}>
              <span className="text-[9px] tracking-[0.14em] text-muted label-mono">{STEP_META[s.type]?.label ?? s.type}</span>
              <div className="truncate text-[11px] text-fg">{s.params?.[STEP_META[s.type]?.field] ?? ""}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Run */}
      <div className="mt-2 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="入力（{input}に入る値）…"
          className="min-w-0 flex-1 rounded-forge border border-[var(--input-bd)] bg-[var(--input-bg)] px-2.5 py-1.5 text-sm text-fg-strong placeholder:text-muted focus:border-[var(--line)] focus:outline-none"
        />
        <button type="button" onClick={() => void run()} disabled={running} className="shrink-0 rounded-forge border border-[var(--line)] bg-[var(--btn-bg)] px-4 text-[10px] tracking-[0.14em] text-fg-strong disabled:opacity-40 label-mono">
          {running ? "…" : "▶ RUN"}
        </button>
      </div>

      {err && <p className="mt-2 text-[11px] text-[#ff9b9b]">⚠️ {err}</p>}

      {result && (
        <div className="mt-2 flex flex-col gap-1">
          {result.results.map((r) => (
            <div key={r.step} className="rounded-forge border border-panel p-2" style={{ opacity: r.skipped ? 0.55 : 1 }}>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[9px] label-mono" style={{ color: r.skipped ? "var(--muted)" : r.ok ? "#60d394" : "#ff6b6b" }}>
                  {r.skipped ? "–" : r.ok ? "✓" : "✕"}
                </span>
                <span className="text-[10px] tracking-[0.12em] text-muted label-mono">{r.name}</span>
                {/* 担当AI・根拠資料・分岐は AI STUDIO のワークフローと共通の機能 */}
                {r.ai && <span className="rounded-full border border-panel px-1.5 text-[9px] text-muted label-mono">◇ {r.ai}</span>}
                {r.knowledge && <span className="rounded-full border border-panel px-1.5 text-[9px] text-muted label-mono">▤ 資料あり</span>}
                {r.skipped && <span className="rounded-full border border-panel px-1.5 text-[9px] text-muted label-mono">スキップ</span>}
              </div>
              {r.reason && <p className="mt-1 text-[10px] text-muted">{r.reason}</p>}
              {r.warning && <p className="mt-1 text-[10px] text-[#ffcf8b]">⚠ {r.warning}</p>}
              {!r.skipped && r.output && <p className="mt-1 whitespace-pre-wrap text-[11px] leading-relaxed text-fg">{r.output.slice(0, 600)}</p>}
              {r.error && <p className="mt-1 text-[10px] text-[#ff9b9b]">{r.error}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
    </Tilt3D>
  );
}

function Connector() {
  return (
    <div className="flex justify-center" aria-hidden>
      <span className="h-3 w-px bg-[var(--accent)] opacity-40" />
    </div>
  );
}
