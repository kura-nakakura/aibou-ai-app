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
import {
  authErrorFromHash, authNotice, confirmState, NOTICE_COLOR, validateCredentials,
  type AuthNotice,
} from "@/lib/authMessages";
import { SIGNUP_SUMMARY } from "@/lib/policy";
import PolicyOverlay from "@/components/Policy";
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
  const [confirm, setConfirm] = useState("");       // 新規登録の確認用
  const [showPw, setShowPw] = useState(false);      // スマホは打った文字を確かめたい
  const emailRef = useRef<HTMLInputElement | null>(null);
  const pwRef = useRef<HTMLInputElement | null>(null);
  const confirmRef = useRef<HTMLInputElement | null>(null);

  // 確認用の欄の状態（空 / 一致 / 不一致）。打っている最中に出す。
  const pwState = confirmState(password, confirm);

  // 登録の前に、データの扱いを読んで同意してもらう。
  // 「知らないうちに自分のデータがどこかへ行っていた」を作らないため。
  const [agreed, setAgreed] = useState(false);
  const [policyOpen, setPolicyOpen] = useState(false);
  // 確認リンクが期限切れ・使用済みだったとき、再送の導線を出す
  const [needsResend, setNeedsResend] = useState(false);

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
    const bad = validateCredentials(email, password, authMode, confirm);
    if (bad) {
      setAuthMsg(bad);
      // 直すべき欄にカーソルを置く（スマホは自分で探すのが手間）
      const target = bad.field === "confirm" ? confirmRef
        : bad.field === "password" ? pwRef
        : emailRef;
      target.current?.focus();
      return;
    }
    if (authMode === "signup" && !agreed) {
      setAuthMsg({ text: "データの扱いを確認して、チェックを入れてください", tone: "error" });
      return;
    }
    setAuthBusy(true);
    setAuthMsg(null);
    try {
      if (authMode === "signup") {
        // 戻り先を明示する。指定しないと Supabase 側の Site URL
        // （初期値は http://localhost:3000）へ飛ばされ、確認リンクが死ぬ。
        const { error: e } = await supabase.auth.signUp({
          email: email.trim(),
          password,
          options: { emailRedirectTo: window.location.origin },
        });
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
  }, [authBusy, authMode, email, password, confirm, agreed]);

  /**
   * 確認リンクから戻ってきたときのエラーを拾って出す。
   *
   * Supabase は失敗を «#» のうしろに載せて戻してくる。読まずに捨てると、
   * リンクを開いたのに何も起きない画面になり「壊れている」と受け取られる。
   * 読んだあとは hash を消す（再読み込みで同じ警告が出続けないように）。
   */
  useEffect(() => {
    if (typeof window === "undefined") return;
    const notice = authErrorFromHash(window.location.hash);
    if (!notice) return;
    setAuthMsg(notice);
    setNeedsResend(true);
    try {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    } catch { /* ignore */ }
  }, []);

  /** 確認メールをもう一度送る（リンクが期限切れ・使用済みのとき）。 */
  const resendConfirm = useCallback(async () => {
    if (!supabase || authBusy) return;
    if (!email.trim()) {
      setAuthMsg({ text: "先にメールアドレスを入力してください", tone: "error", field: "email" });
      emailRef.current?.focus();
      return;
    }
    setAuthBusy(true);
    try {
      const { error: e } = await supabase.auth.resend({
        type: "signup",
        email: email.trim(),
        options: { emailRedirectTo: window.location.origin },
      });
      setAuthMsg(e ? authNotice(e.message)
                   : { text: "確認メールを送り直しました。新しいメールのリンクを開いてください", tone: "ok" });
    } catch (err) {
      setAuthMsg(authNotice(err));
    } finally {
      setAuthBusy(false);
    }
  }, [authBusy, email]);

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

              {/* ブランドは AIbou の1語。システム名（THE FORGE OS）は従。 */}
              <h1 className="brand-wordmark text-glow mt-6 text-[22px] text-fg-strong">
                AIbou
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
                      placeholder={authMode === "signup" ? "パスワード（6文字以上）" : "パスワード"}
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

                  {/* 確認用のパスワード。1回しか打たないと、打ち間違えたまま
                      登録が通り、次から入れなくなる（本人には原因が分からない）。
                      表示/隠すは上の欄と連動するので、ここにボタンは置かない。 */}
                  {authMode === "signup" && (
                    <div>
                      <input
                        ref={confirmRef}
                        value={confirm}
                        onChange={(e) => { setConfirm(e.target.value); setAuthMsg(null); }}
                        type={showPw ? "text" : "password"}
                        name="confirm-password"
                        autoComplete="new-password"
                        enterKeyHint="go"
                        autoCapitalize="none"
                        autoCorrect="off"
                        spellCheck={false}
                        aria-label="パスワード（確認用）"
                        placeholder="パスワード（確認用）"
                        className="min-h-[48px] w-full rounded-forge border bg-[var(--input-bg)] px-3.5 text-base text-fg-strong placeholder:text-muted focus:shadow-glow focus:outline-none"
                        style={{
                          borderColor:
                            pwState === "mismatch" ? NOTICE_COLOR.error
                            : pwState === "match" ? NOTICE_COLOR.ok
                            : "var(--input-bd)",
                        }}
                      />
                      {/* 打ち終わってから分かるのでは遅いので、その場で伝える */}
                      {pwState !== "empty" && (
                        <p
                          aria-live="polite"
                          className="mt-1 px-0.5 text-left text-[11px]"
                          style={{ color: pwState === "match" ? NOTICE_COLOR.ok : NOTICE_COLOR.error }}
                        >
                          {pwState === "match" ? "✓ 一致しました" : "一致しません"}
                        </p>
                      )}
                    </div>
                  )}

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

                  {/* 登録前に、データの扱いを先に見せる。あとから説明書で
                      気づいてもらう形にすると、預ける判断ができない。 */}
                  {authMode === "signup" && (
                    <div className="rounded-forge border border-panel p-3 text-left">
                      <div className="mb-1.5 text-[10px] tracking-[0.16em] text-muted label-mono">
                        データの扱い
                      </div>
                      <ul className="space-y-1.5">
                        {SIGNUP_SUMMARY.map((s) => (
                          <li key={s} className="flex gap-2 text-[11px] leading-relaxed text-fg">
                            <span aria-hidden className="mt-[6px] h-1 w-1 shrink-0 rounded-full"
                                  style={{ background: "var(--accent)" }} />
                            <span className="min-w-0">{s}</span>
                          </li>
                        ))}
                      </ul>
                      <button
                        type="button"
                        onClick={() => setPolicyOpen(true)}
                        className="mt-2 min-h-[40px] text-[11px] text-[var(--accent)] underline"
                      >
                        くわしく読む（プライバシーと利用について）
                      </button>
                      <label className="mt-1 flex cursor-pointer items-start gap-2.5">
                        <input
                          type="checkbox"
                          checked={agreed}
                          onChange={(e) => setAgreed(e.target.checked)}
                          className="mt-[3px] h-[18px] w-[18px] shrink-0 accent-[var(--accent)]"
                        />
                        <span className="text-[11px] leading-relaxed text-fg">
                          上記を確認しました
                        </span>
                      </label>
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={authBusy || (authMode === "signup" && (!agreed || pwState !== "match"))}
                    className="min-h-[48px] w-full rounded-forge border border-[var(--line)] bg-[var(--btn-bg)] text-[12px] tracking-[0.28em] text-fg-strong shadow-glow transition hover:shadow-glow-strong disabled:opacity-50 label-mono"
                  >
                    {authBusy ? "…" : authMode === "signup" ? "▸ アカウント作成" : "▸ サインイン"}
                  </button>

                  <div className="flex items-center justify-between gap-2 pt-1">
                    <button
                      type="button"
                      onClick={() => {
                        setAuthMode((m) => (m === "signup" ? "signin" : "signup"));
                        setAuthMsg(null);
                        setConfirm("");        // 切り替えたら確認欄は持ち越さない
                      }}
                      className="-mx-1 min-h-[40px] flex-1 px-1 text-left text-[11px] text-muted transition hover:text-fg-strong"
                    >
                      {authMode === "signup" ? "サインインに戻る" : "アカウントを作成"}
                    </button>
                    {authMode === "signin" && !needsResend && (
                      <button
                        type="button"
                        onClick={() => void sendReset()}
                        disabled={authBusy}
                        className="-mx-1 min-h-[40px] px-1 text-right text-[11px] text-muted transition hover:text-fg-strong disabled:opacity-40"
                      >
                        パスワードを忘れた
                      </button>
                    )}
                    {needsResend && (
                      <button
                        type="button"
                        onClick={() => void resendConfirm()}
                        disabled={authBusy}
                        className="-mx-1 min-h-[40px] px-1 text-right text-[11px] text-[var(--accent)] underline transition disabled:opacity-40"
                      >
                        確認メールを再送
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
              {/* サインイン側からも、いつでも読めるようにしておく */}
              <button
                type="button"
                onClick={() => setPolicyOpen(true)}
                className="mt-2 min-h-[40px] text-[10px] text-muted underline transition hover:text-fg-strong"
              >
                プライバシーと利用について
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {policyOpen && <PolicyOverlay onClose={() => setPolicyOpen(false)} />}
    </>
  );
}
