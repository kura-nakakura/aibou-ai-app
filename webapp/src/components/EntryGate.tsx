"use client";

/**
 * EntryGate — the branded "login" splash (login_bg.gif backdrop).
 *
 * Recreates the original FORGE OS entry ritual: an animated geometric
 * background, a glass card with the core + wordmark, and an ENTER affordance.
 * If NEXT_PUBLIC_GATE_PIN is set it acts as a soft lock (client-side only —
 * a deterrent, not real auth); otherwise it's a single ENTER tap.
 *
 * Entry is remembered for the tab session (sessionStorage) so internal reloads
 * don't re-prompt, while a fresh session still gets the ritual. Once entered,
 * children mount (BootScreen → HUD).
 */

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import CoreOrb from "./CoreOrb";
import { supabase, supabaseEnabled } from "@/lib/supabase";
import { authNotice, NOTICE_COLOR, validateCredentials, type AuthNotice } from "@/lib/authMessages";
import { APP_VERSION } from "@/lib/version";

const SS_KEY = "forge_entered";
const GATE_PIN = process.env.NEXT_PUBLIC_GATE_PIN || "";

export default function EntryGate({ children }: { children: React.ReactNode }) {
  const [entered, setEntered] = useState(false);
  const [ready, setReady] = useState(false); // hydration guard (avoid gate flash)
  const [pin, setPin] = useState("");
  const [error, setError] = useState(false);

  // Supabase auth (only when configured)
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authMode, setAuthMode] = useState<"signin" | "signup">("signin");
  const [authBusy, setAuthBusy] = useState(false);
  const [authMsg, setAuthMsg] = useState<AuthNotice | null>(null);
  const [showPw, setShowPw] = useState(false);      // スマホは打った文字を確かめたい
  const emailRef = useRef<HTMLInputElement | null>(null);
  const pwRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (supabaseEnabled && supabase) {
      // Real auth: entry follows the Supabase session.
      supabase.auth.getSession().then(({ data }) => {
        setEntered(!!data.session);
        setReady(true);
      });
      const { data: sub } = supabase.auth.onAuthStateChange((_e, session) => {
        setEntered(!!session);
      });
      return () => sub.subscription.unsubscribe();
    }
    // Soft gate: remembered per tab session.
    try {
      if (sessionStorage.getItem(SS_KEY) === "1") setEntered(true);
    } catch {
      /* ignore */
    }
    setReady(true);
  }, []);

  const enter = useCallback(() => {
    if (GATE_PIN && pin.trim() !== GATE_PIN) {
      setError(true);
      return;
    }
    try {
      sessionStorage.setItem(SS_KEY, "1");
    } catch {
      /* ignore */
    }
    setEntered(true);
  }, [pin]);

  const submitAuth = useCallback(async () => {
    if (!supabase || authBusy) return;
    // サーバーに行く前に、明らかな入力ミスはその場で伝える
    const bad = validateCredentials(email, password, authMode);
    if (bad) {
      setAuthMsg(bad);
      // 直すべき欄にカーソルを置く（スマホは自分で探すのが手間）
      (bad.field === "password" ? pwRef : emailRef).current?.focus();
      return;
    }
    setAuthBusy(true);
    setAuthMsg(null);
    try {
      if (authMode === "signup") {
        const { error: e } = await supabase.auth.signUp({ email: email.trim(), password });
        if (e) setAuthMsg(authNotice(e.message));
        else setAuthMsg({ text: "確認メールを送りました。リンクを開いてからサインインしてください", tone: "ok" });
      } else {
        const { error: e } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
        if (e) setAuthMsg(authNotice(e.message));
        // 成功時は onAuthStateChange が entered を立てる
      }
    } catch (err) {
      setAuthMsg(authNotice(err));
    } finally {
      setAuthBusy(false);
    }
  }, [authBusy, authMode, email, password]);

  /** パスワードを忘れた場合の再設定メール。スマホで詰まりやすいので導線を出す。 */
  const sendReset = useCallback(async () => {
    if (!supabase || authBusy) return;
    if (!email.trim()) {
      setAuthMsg({ text: "先にメールアドレスを入力してください", tone: "error" });
      return;
    }
    setAuthBusy(true);
    try {
      const { error: e } = await supabase.auth.resetPasswordForEmail(email.trim(), {
        redirectTo: typeof window !== "undefined" ? window.location.origin : undefined,
      });
      setAuthMsg(e ? authNotice(e.message)
                   : { text: "再設定メールを送りました。メールのリンクから設定し直してください", tone: "ok" });
    } catch (err) {
      setAuthMsg(authNotice(err));
    } finally {
      setAuthBusy(false);
    }
  }, [authBusy, email]);

  // Renderのコールドスタート対策: ゲート表示中にバックエンドを起こしておく
  // （ENTER時にはウォーム済み）。失敗は無視 — 純粋な先行ウォームアップ。
  useEffect(() => {
    const api = (process.env.NEXT_PUBLIC_API_URL || "").trim();
    if (!api) return;
    fetch(`${api}/health`, { cache: "no-store" }).catch(() => { /* warming only */ });
  }, []);

  // Before hydration: hold a plain dark screen (no flash of either state).
  if (!ready) return <div className="fixed inset-0" style={{ background: "var(--bg)" }} />;

  return (
    <>
      {entered && children}

      <AnimatePresence>
        {!entered && (
          <motion.div
            key="entrygate"
            // スマホでキーボードが出ると縦が縮む。overflow-hidden のままだと
            // 送信ボタンに手が届かなくなるので、スクロールできるようにする。
            className="fixed inset-0 z-[60] flex flex-col items-center justify-center overflow-y-auto px-6 py-8"
            style={{
              background: "var(--bg)",
              paddingTop: "max(env(safe-area-inset-top), 2rem)",
              paddingBottom: "max(env(safe-area-inset-bottom), 2rem)",
            }}
            initial={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: 0.7, ease: "easeInOut" } }}
          >
            {/* Animated login backdrop (GIF) — blurred + dimmed for legibility. */}
            <div
              aria-hidden
              className="pointer-events-none absolute inset-0"
              style={{
                backgroundImage: "url('/login_bg.gif')",
                backgroundSize: "cover",
                backgroundPosition: "center",
                filter: "blur(3px) brightness(0.45) saturate(1.1)",
                transform: "scale(1.08)",
              }}
            />
            <div aria-hidden className="forge-grid pointer-events-none absolute inset-0 opacity-60" />
            <div
              aria-hidden
              className="pointer-events-none absolute inset-0"
              style={{ background: "radial-gradient(700px 520px at 50% 42%, rgba(150,200,255,0.10), transparent 62%), rgba(5,6,9,0.5)" }}
            />
            <div aria-hidden className="forge-scan pointer-events-none" />

            {/* Glass entry card. */}
            <motion.div
              className="panel relative z-10 flex w-full max-w-sm flex-col items-center px-6 py-8 text-center"
              initial={{ opacity: 0, y: 16, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ type: "spring", stiffness: 280, damping: 28 }}
            >
              <CoreOrb size={120} state="idle" />

              {/* ブランド（AIbou 相棒）を主、システム名（THE FORGE OS）を従にする。 */}
              <h1 className="brand-wordmark text-glow mt-6 flex items-baseline gap-2 text-[22px] text-fg-strong">
                AIbou
                <span className="brand-wordmark text-[12px] text-muted">相棒</span>
              </h1>
              <p className="brand-sub mt-2 text-[9px] text-muted">THE FORGE OS · PERSONAL AI CORE</p>

              {supabaseEnabled ? (
                /* form にしておくと、スマホのキーボードの「確定/Go」で送信でき、
                   パスワード管理アプリもログイン欄として認識してくれる。 */
                <form
                  className="mt-7 w-full space-y-2"
                  /* noValidate: ブラウザ標準の英語まじりの検証バブルより、
                     こちらの日本語の案内に統一したい（標準検証が有効だと
                     submit そのものが発火せず、自前の案内が出せない）。 */
                  noValidate
                  onSubmit={(e) => { e.preventDefault(); void submitAuth(); }}
                >
                  <input
                    ref={emailRef}
                    value={email}
                    onChange={(e) => { setEmail(e.target.value); setAuthMsg(null); }}
                    type="email"
                    name="email"
                    autoComplete="email"
                    inputMode="email"
                    enterKeyHint="next"
                    autoCapitalize="none"
                    autoCorrect="off"
                    spellCheck={false}
                    aria-label="メールアドレス"
                    placeholder="メールアドレス"
                    /* 16px 未満だと iOS Safari が focus 時に画面を拡大する。
                       ログイン欄はそれが一番わずらわしいので text-base にする。 */
                    className="min-h-[48px] w-full rounded-forge border border-[var(--input-bd)] bg-[var(--input-bg)] px-3.5 text-base text-fg-strong placeholder:text-muted focus:border-[var(--line)] focus:shadow-glow focus:outline-none"
                  />

                  <div className="relative">
                    <input
                      ref={pwRef}
                      value={password}
                      onChange={(e) => { setPassword(e.target.value); setAuthMsg(null); }}
                      type={showPw ? "text" : "password"}
                      name="password"
                      autoComplete={authMode === "signup" ? "new-password" : "current-password"}
                      enterKeyHint="go"
                      autoCapitalize="none"
                      autoCorrect="off"
                      spellCheck={false}
                      aria-label="パスワード"
                      placeholder="パスワード"
                      className="min-h-[48px] w-full rounded-forge border border-[var(--input-bd)] bg-[var(--input-bg)] pl-3.5 pr-[52px] text-base text-fg-strong placeholder:text-muted focus:border-[var(--line)] focus:shadow-glow focus:outline-none"
                    />
                    {/* 打ち間違いを目で確かめられるように。指で押せる幅を確保する。 */}
                    <button
                      type="button"
                      onClick={() => setShowPw((v) => !v)}
                      aria-label={showPw ? "パスワードを隠す" : "パスワードを表示"}
                      aria-pressed={showPw}
                      className="absolute right-0 top-0 flex h-full w-[52px] items-center justify-center text-[10px] text-muted transition hover:text-fg-strong label-mono"
                    >
                      {showPw ? "隠す" : "表示"}
                    </button>
                  </div>

                  {authMsg && (
                    <p
                      role="status"
                      aria-live="polite"
                      className="px-0.5 text-left text-[11px] leading-relaxed"
                      style={{ color: NOTICE_COLOR[authMsg.tone] }}
                    >
                      {authMsg.text}
                    </p>
                  )}

                  <button
                    type="submit"
                    disabled={authBusy}
                    className="min-h-[48px] w-full rounded-forge border border-[var(--line)] bg-[var(--btn-bg)] text-[12px] tracking-[0.28em] text-fg-strong shadow-glow transition hover:shadow-glow-strong disabled:opacity-50 label-mono"
                  >
                    {authBusy ? "…" : authMode === "signup" ? "▸ アカウント作成" : "▸ サインイン"}
                  </button>

                  <div className="flex items-center justify-between gap-2 pt-1">
                    <button
                      type="button"
                      onClick={() => { setAuthMode((m) => (m === "signup" ? "signin" : "signup")); setAuthMsg(null); }}
                      className="-mx-1 min-h-[40px] flex-1 px-1 text-left text-[11px] text-muted transition hover:text-fg-strong"
                    >
                      {authMode === "signup" ? "サインインに戻る" : "アカウントを作成"}
                    </button>
                    {authMode === "signin" && (
                      <button
                        type="button"
                        onClick={() => void sendReset()}
                        disabled={authBusy}
                        className="-mx-1 min-h-[40px] px-1 text-right text-[11px] text-muted transition hover:text-fg-strong disabled:opacity-40"
                      >
                        パスワードを忘れた
                      </button>
                    )}
                  </div>
                </form>
              ) : GATE_PIN ? (
                <div className="mt-7 w-full">
                  <input
                    value={pin}
                    onChange={(e) => {
                      setPin(e.target.value);
                      setError(false);
                    }}
                    onKeyDown={(e) => e.key === "Enter" && enter()}
                    type="password"
                    inputMode="numeric"
                    autoFocus
                    placeholder="ACCESS CODE"
                    className="w-full rounded-forge border bg-[var(--input-bg)] px-3 py-2.5 text-center text-sm tracking-[0.3em] text-fg-strong placeholder:text-muted focus:shadow-glow focus:outline-none label-mono"
                    style={{ borderColor: error ? "#ff6b6b" : "var(--input-bd)" }}
                  />
                  {error && (
                    <p className="mt-2 text-[10px] tracking-[0.2em] text-[#ff9b9b] label-mono">ACCESS DENIED</p>
                  )}
                </div>
              ) : null}

              {!supabaseEnabled && (
                <button
                  type="button"
                  onClick={enter}
                  className="mt-7 w-full rounded-forge border border-[var(--line)] bg-[var(--btn-bg)] py-3 text-[11px] tracking-[0.34em] text-fg-strong shadow-glow transition hover:shadow-glow-strong label-mono"
                >
                  ▸ ENTER
                </button>
              )}

              <motion.p
                className="mt-4 text-[9px] tracking-[0.3em] text-muted/60 label-mono"
                animate={{ opacity: [0.35, 0.85, 0.35] }}
                transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
              >
                AUTHORIZED ACCESS ONLY
              </motion.p>
              <p className="mt-1 text-[8px] tracking-[0.24em] text-muted/40 label-mono">
                BUILD {APP_VERSION}
              </p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
