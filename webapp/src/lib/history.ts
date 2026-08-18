/**
 * 送る会話履歴の量を抑える。
 *
 * 返事が出始めるまでの時間は、送った文章の長さに比例して伸びる。履歴は
 * 直近12件をそのまま全文送っていたので、長い生成物（資料・コードなど）が
 * 1つ混じるだけで入力が一気に膨らみ、そのぶん待たされていた。
 *
 * 方針は「普通の会話には一切触らない」。長さの上限を普通の会話より十分
 * 大きく取り、はみ出したときだけ古い順に削る。直近のやりとりは文脈として
 * 効くので必ず残し、削るのは古いほうから。
 */

export interface HistoryTurn {
  role: "user" | "assistant";
  content: string;
}

export interface TrimOptions {
  /** 1件あたりの上限。これを超える発言は末尾を落とす。 */
  perMessage?: number;
  /** 履歴全体の上限。古いものから落として収める。 */
  total?: number;
  /** 何があっても残す直近の件数。 */
  keepRecent?: number;
}

const DEFAULTS: Required<TrimOptions> = {
  perMessage: 1500,
  total: 12000,
  keepRecent: 4,
};

/** 長すぎる発言を、切ったと分かる形で短くする。 */
function clip(text: string, max: number): string {
  if (text.length <= max) return text;
  // 切ったことを伝えないと、AIが「途中で終わっている」と誤解して読み直そうとする
  return `${text.slice(0, max)}…（長いため省略）`;
}

/**
 * 履歴を上限内に収める。新しいものを優先して残す。
 * 普通の長さの会話では、渡したものがそのまま返る。
 */
export function trimHistory(turns: HistoryTurn[], opts: TrimOptions = {}): HistoryTurn[] {
  const { perMessage, total, keepRecent } = { ...DEFAULTS, ...opts };
  if (!turns.length) return [];

  // 新しい順に見て、上限に収まるぶんだけ採用する
  const picked: HistoryTurn[] = [];
  let used = 0;
  for (let i = turns.length - 1; i >= 0; i--) {
    const t = turns[i];
    const content = clip(t.content ?? "", perMessage);
    const isRecent = turns.length - 1 - i < keepRecent;
    if (!isRecent && used + content.length > total) break;   // ここより古いのは捨てる
    picked.push({ role: t.role, content });
    used += content.length;
  }
  return picked.reverse();
}
