"use client";

/**
 * Workshop — 「作る」ためのモード（旧 FORGE と旧 STUDIO を統合）.
 *  - FORGE（生成）: アプリ/画像/スライド/表/文書を生成
 *  - AI STUDIO   : カスタムAI・ワークフロー・自己進化
 * 外側タブで切替。選択タブは記憶される。
 */

import { useEffect, useState } from "react";
import Forge from "@/components/Forge";
import Studio from "@/components/Studio";
import LpBuilder from "@/components/LpBuilder";

type Tab = "forge" | "lp" | "studio";

export default function Workshop() {
  const [tab, setTab] = useState<Tab>("forge");

  useEffect(() => {
    try {
      const t = localStorage.getItem("forge_workshop_tab");
      if (t === "studio" || t === "lp") setTab(t);
    } catch { /* ignore */ }
  }, []);
  useEffect(() => {
    try { localStorage.setItem("forge_workshop_tab", tab); } catch { /* ignore */ }
  }, [tab]);

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      <div className="mx-auto flex items-center gap-1.5">
        {([
          { key: "forge", label: "✦ FORGE" },
          { key: "lp", label: "◫ LP / HP" },
          { key: "studio", label: "⚙ AI STUDIO" },
        ] as const).map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            aria-pressed={tab === t.key}
            className="rounded-forge border px-4 py-1.5 text-[10px] tracking-[0.16em] transition label-mono"
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
        {tab === "forge" ? <Forge /> : tab === "lp" ? <LpBuilder /> : <Studio />}
      </div>
    </div>
  );
}
