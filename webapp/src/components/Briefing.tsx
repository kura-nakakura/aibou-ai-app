"use client";

/**
 * Briefing — 「今日のブリーフィング」。バックエンド /briefing を呼び、結果を表示＋読み上げ。
 * プロアクティブの即時版（毎朝のDiscord配信はGitHub Actionが担当）。
 */

import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { API_URL, getBriefing } from "@/lib/api";
import { loadVoiceSettings, speakCore } from "@/lib/coreVoice";

export default function Briefing() {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");

  const run = async () => {
    setBusy(true);
    setOpen(true);
    try {
      const r = await getBriefing();
      setText(r.text || "（ブリーフィングを取得できませんでした）");
      // 設定した声・速さで読む（CHATと同じ経路。記号や絵文字は読み上げない）
      if (r.text) speakCore(r.text, loadVoiceSettings(), {}, Boolean(API_URL));
    } catch {
      setText("ブリーフィングの取得に失敗しました。");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={run}
        className="rounded-lg border border-panel px-2.5 py-1 text-[10px] tracking-[0.16em] text-muted transition hover:border-[var(--line)] hover:text-fg-strong label-mono"
        title="今日のブリーフィング"
      >
        ☀ BRIEF
      </button>

      <AnimatePresence>
        {open && (
          <>
            <button
              type="button"
              aria-hidden
              tabIndex={-1}
              onClick={() => setOpen(false)}
              className="fixed inset-0 z-40 cursor-default"
            />
          <motion.div
            className="absolute right-0 z-50 mt-2 w-[min(80vw,320px)] panel p-3"
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
          >
            <div className="mb-1 flex items-center justify-between">
              <span className="text-[10px] tracking-[0.2em] text-muted label-mono">BRIEFING</span>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-muted transition hover:text-fg-strong"
                aria-label="Close"
              >
                ✕
              </button>
            </div>
            {busy ? (
              <motion.p
                className="text-[11px] tracking-[0.18em] text-muted label-mono"
                animate={{ opacity: [0.4, 1, 0.4] }}
                transition={{ duration: 1.4, repeat: Infinity }}
              >
                ◈ 生成中…
              </motion.p>
            ) : (
              <p className="whitespace-pre-wrap text-[12px] leading-relaxed text-fg">{text}</p>
            )}
          </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
