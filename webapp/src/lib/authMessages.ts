/**
 * Supabase 認証エラーの日本語化。
 *
 * 素の Supabase は英語で "Invalid login credentials" のように返す。ログイン
 * 画面でそのまま出すと、何を直せばいいのか分からない。ここで「次に何をすれば
 * よいか」が分かる日本語に置き換える。
 *
 * 見つからないものは英語のまま返す（黙って握りつぶさない）。
 */

export interface AuthNotice {
  text: string;
  /** error は赤、info は黄、ok は緑で出す。 */
  tone: "error" | "info" | "ok";
  /** 入力ミスのときは、その欄にフォーカスを戻すために使う。 */
  field?: "email" | "password" | "confirm";
}

const MAP: { match: RegExp; text: string; tone: AuthNotice["tone"] }[] = [
  {
    match: /invalid login credentials/i,
    text: "メールアドレスかパスワードが違います",
    tone: "error",
  },
  {
    match: /email not confirmed/i,
    text: "メールの確認がまだです。届いているリンクを開いてから、もう一度サインインしてください",
    tone: "info",
  },
  {
    match: /user already registered|already been registered/i,
    text: "そのメールアドレスは登録済みです。サインインに切り替えてください",
    tone: "info",
  },
  {
    match: /password should be at least (\d+)/i,
    text: "パスワードが短すぎます（6文字以上にしてください）",
    tone: "error",
  },
  {
    match: /unable to validate email address|invalid format/i,
    text: "メールアドレスの形式が正しくありません",
    tone: "error",
  },
  {
    match: /email rate limit|too many requests|rate limit/i,
    text: "試行が多すぎます。少し時間をおいてからもう一度お試しください",
    tone: "info",
  },
  {
    match: /signups not allowed|signup is disabled/i,
    text: "このプロジェクトでは新規登録が無効になっています",
    tone: "error",
  },
  {
    match: /failed to fetch|network|load failed/i,
    text: "通信できませんでした。電波の良い場所でもう一度お試しください",
    tone: "error",
  },
];

/** アカウント作成を試したあと、画面がどう振る舞うか。 */
export interface SignUpOutcome {
  notice: AuthNotice;
  /** サインイン側へ切り替えるべきか（すでに登録済みのとき）。 */
  switchToSignIn: boolean;
}

/**
 * signUp の結果から、利用者に何と伝えるかを決める。
 *
 * Supabase は「そのアドレスが登録済みかどうか」を外から探れないように、
 * 登録済みでもエラーを返さず成功のように振る舞い、メールも送らない。
 * 返り値をそのまま成功として扱うと「確認メールを送りました」と出したまま
 * いつまでも届かず、原因が誰にも分からなくなる（実際に踏んだ）。
 *
 * 見分け方: 登録済みのとき user.identities が空配列で返る。
 */
export function signUpOutcome(
  user: { identities?: unknown[] | null } | null | undefined,
  session: unknown,
): SignUpOutcome {
  // メール確認が無効な設定では、その場でセッションが返る
  if (session) {
    return {
      notice: { text: "アカウントを作成しました", tone: "ok" },
      switchToSignIn: false,
    };
  }
  if (user && Array.isArray(user.identities) && user.identities.length === 0) {
    return {
      notice: {
        text: "このメールアドレスは登録済みです。パスワードを入れてサインインしてください"
            + "（分からなければ「パスワードを忘れた」から再設定できます）",
        tone: "info",
      },
      switchToSignIn: true,
    };
  }
  return {
    notice: { text: "確認メールを送りました。リンクを開いてからサインインしてください", tone: "ok" },
    switchToSignIn: false,
  };
}

/**
 * 確認メールのリンクから戻ってきたときのエラーを読み取る。
 *
 * Supabase は失敗を URL の «#» のうしろに載せて戻してくる。例:
 *   #error=access_denied&error_code=otp_expired&error_description=Email+link+is+invalid...
 * これを拾って出さないと、利用者はリンクを開いたのに何も起きない画面を見て
 * 「壊れている」と受け取る（実際に踏んだ）。
 *
 * hash は "#..." でも "..." でも受け付ける。エラーが無ければ null。
 */
export function authErrorFromHash(hash: string): AuthNotice | null {
  const raw = (hash || "").replace(/^#/, "");
  if (!raw) return null;
  let p: URLSearchParams;
  try {
    p = new URLSearchParams(raw);
  } catch {
    return null;
  }
  const code = (p.get("error_code") || "").toLowerCase();
  const err = (p.get("error") || "").toLowerCase();
  if (!code && !err) return null;

  // 期限切れ・使用済み。いちばん多い。
  if (code.includes("otp_expired") || code.includes("expired")) {
    return {
      text: "確認リンクの期限が切れているか、すでに使われています。下の「確認メールを再送」を押してください",
      tone: "info",
    };
  }
  if (code.includes("email_link_invalid") || code.includes("invalid")) {
    return {
      text: "確認リンクが正しくありません。下の「確認メールを再送」から、新しいリンクを受け取ってください",
      tone: "info",
    };
  }
  if (err.includes("access_denied")) {
    return {
      text: "確認リンクが使えませんでした。下の「確認メールを再送」を押してください",
      tone: "info",
    };
  }
  // 知らないものは説明文をそのまま見せる（黙って握りつぶさない）
  const desc = (p.get("error_description") || "").replace(/\+/g, " ").trim();
  return { text: desc || `確認に失敗しました（${err || code}）`, tone: "error" };
}

/** Supabase のエラー文（英語）を日本語の案内に変換する。 */
export function authNotice(raw: unknown): AuthNotice {
  const msg = (raw instanceof Error ? raw.message : String(raw ?? "")).trim();
  if (!msg) return { text: "認証に失敗しました", tone: "error" };
  for (const m of MAP) {
    if (m.match.test(msg)) return { text: m.text, tone: m.tone };
  }
  return { text: msg, tone: "error" };
}

/**
 * 送信前の簡単な入力チェック（サーバーに行く前に気づけるように）。
 *
 * 新規登録では確認用のパスワードも見る。1回しか打たないと、打ち間違えたまま
 * 登録が通ってしまい、次に入れなくなる（本人には打ち間違いだと分からない）。
 */
export function validateCredentials(
  email: string,
  password: string,
  mode: "signin" | "signup",
  confirm?: string,
): AuthNotice | null {
  const e = email.trim();
  if (!e) return { text: "メールアドレスを入力してください", tone: "error", field: "email" };
  // 厳密な検証はサーバーに任せ、ここは「明らかに違う」だけ弾く
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e)) {
    return { text: "メールアドレスの形式が正しくありません", tone: "error", field: "email" };
  }
  if (!password) return { text: "パスワードを入力してください", tone: "error", field: "password" };
  if (mode === "signup") {
    if (password.length < 6) {
      return { text: "パスワードは6文字以上にしてください", tone: "error", field: "password" };
    }
    if (!confirm) {
      return { text: "確認用のパスワードを入力してください", tone: "error", field: "confirm" };
    }
    if (password !== confirm) {
      return { text: "パスワードが一致しません", tone: "error", field: "confirm" };
    }
  }
  return null;
}

/**
 * 確認用の欄に、その場で出す状態。
 * 打っている途中で赤を出すと急かされている感じになるので、
 * 「まだ何も打っていない」「一致した」「違う」の3つだけにする。
 */
export function confirmState(password: string, confirm: string): "empty" | "match" | "mismatch" {
  if (!confirm) return "empty";
  return password === confirm ? "match" : "mismatch";
}

/** tone に対応する文字色（globals.css のトークンではなく、状態色の直値）。 */
export const NOTICE_COLOR: Record<AuthNotice["tone"], string> = {
  error: "#ff9b9b",
  info: "#ffd07f",
  ok: "#7fe0a8",
};
