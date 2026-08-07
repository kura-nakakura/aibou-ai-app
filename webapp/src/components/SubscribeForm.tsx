"use client";

/**
 * SubscribeForm — 公開SEOページに置くニュースレター登録フォーム.
 *
 * 企画書⑤の「SEOサイトからの自動送客ルート」。ここで取得したアドレスが
 * 顧客リストになる。ダブルオプトイン（確認メールを踏むまで配信しない）なので、
 * ここでは「確認メールを送りました」までを案内する。
 */

import { useState } from "react";

const API = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

export default function SubscribeForm({ source }: { source?: string }) {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");
  const [msg, setMsg] = useState("");

  if (!API) return null;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim() || state === "busy") return;
    setState("busy");
    setMsg("");
    try {
      const res = await fetch(`${API}/newsletter/subscribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), source: source || "" }),
      });
      const data = (await res.json().catch(() => ({}))) as { status?: string; error?: string };
      if (!res.ok) {
        setState("error");
        setMsg(data.error || "登録できませんでした。");
        return;
      }
      setState("done");
      setMsg(data.status === "already_confirmed"
        ? "すでにご登録済みです。ありがとうございます。"
        : "確認メールをお送りしました。メール内のリンクを開くと登録が完了します。");
      setEmail("");
    } catch {
      setState("error");
      setMsg("通信に失敗しました。時間をおいてお試しください。");
    }
  };

  return (
    <section style={{ marginTop: 48, padding: 20, border: "1px solid #e5e7eb", borderRadius: 10, background: "#f9fafb" }}>
      <h2 style={{ fontSize: 17, margin: "0 0 6px", color: "#111827" }}>役立つ情報をメールで受け取る</h2>
      <p style={{ fontSize: 13, color: "#4b5563", margin: "0 0 12px", lineHeight: 1.7 }}>
        同じテーマの実践的な内容を、まとめてお届けします。配信はいつでも停止できます。
      </p>

      {state === "done" ? (
        <p style={{ fontSize: 13, color: "#047857", margin: 0 }}>✓ {msg}</p>
      ) : (
        <form onSubmit={submit} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            type="email"
            required
            value={email}
            onChange={(ev) => setEmail(ev.target.value)}
            placeholder="you@example.com"
            aria-label="メールアドレス"
            style={{
              flex: "1 1 220px", minWidth: 0, padding: "10px 12px", fontSize: 14,
              border: "1px solid #d1d5db", borderRadius: 6, background: "#fff", color: "#111827",
            }}
          />
          <button
            type="submit"
            disabled={state === "busy"}
            style={{
              padding: "10px 20px", fontSize: 14, fontWeight: 700, cursor: "pointer",
              background: state === "busy" ? "#9ca3af" : "#2563eb",
              color: "#fff", border: "none", borderRadius: 6,
            }}
          >
            {state === "busy" ? "送信中…" : "登録する"}
          </button>
        </form>
      )}

      {state === "error" && <p style={{ fontSize: 12, color: "#b91c1c", margin: "8px 0 0" }}>{msg}</p>}
      <p style={{ fontSize: 11, color: "#9ca3af", margin: "10px 0 0", lineHeight: 1.6 }}>
        ご登録いただいたアドレスは配信のみに使用します。確認メールのリンクを開くまで配信は行いません。
      </p>
    </section>
  );
}
