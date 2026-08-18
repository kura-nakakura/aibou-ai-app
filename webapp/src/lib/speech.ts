/**
 * 読み上げ用のテキスト整形。
 *
 * 画面に出す文章と、声に出す文章は同じではない。返答には Markdown の記号
 * （** ## - ` []()）や矢印・絵文字・URL が混ざっていて、そのまま合成音声に
 * 渡すと「アスタリスク アスタリスク」「みぎむき やじるし」「エイチティー
 * ティーピーコロン スラッシュ スラッシュ」と読み上げてしまう。
 *
 *   speakableText()  … 声に出さない記号を落とす／読める形に置き換える
 *   splitForSpeech() … 文の切れ目で分ける（先頭の文から喋り始めるため）
 *   takeCompleteSentences() … 受信途中の文字列から、言い切った文だけを取る
 *
 * ここは純粋関数だけにしてある（ブラウザAPIに触れない）ので、テストで
 * 実際の返答例を通して確かめられる。
 */

/** 記号だが、消すと意味が変わるもの。読める形に置き換える。 */
const MEANINGFUL: Array<[RegExp, string]> = [
  // 矢印は流れを表しているので、読点にして間を作る（「計画→実行」→「計画、実行」）
  [/[→⇒➡▶►~〜]+/gu, "、"],
  [/[←⇐◀◄]+/gu, "、"],
  // 中黒・全角スラッシュは区切り。読点にすると自然な間になる
  [/[・･]/gu, "、"],
  [/\s*[／/]\s*/gu, "、"],
  // 波ダッシュの範囲（10〜20）は「から」
  [/(\d)\s*[-–—]\s*(?=\d)/gu, "$1から"],
];

/** 画面の飾りとして使っているだけの記号（読ませない）。 */
const DECORATIVE = /[◈▸✦⊞✕✓★☆◆●○■□▲▼⚠⚙⭳↗↺⌗☀☁※＊*#>|~^`＝=＋+_–—－]/gu;

/**
 * 読み上げても意味が通る文章にする。
 *
 * 消す順番には理由がある。コードブロックを先に消さないと、その中の記号を
 * 「意味のある記号」として置換してしまう。
 */
export function speakableText(raw: string): string {
  if (!raw) return "";
  let t = raw;

  // 1) コードブロックは読まない（読んでも伝わらないので存在だけ伝える）
  t = t.replace(/```[\s\S]*?```/g, " コードは画面をご覧ください。 ");
  t = t.replace(/```\s*$/g, " ");                                     // 閉じの ``` だけ残った分
  t = t.replace(/```[\s\S]*$/g, " コードは画面をご覧ください。 ");   // 閉じ忘れ・受信途中
  t = t.replace(/`([^`]*)`/g, "$1");                                  // インラインコードは中身だけ

  // 2) リンクは表示文字だけ読む。裸のURLは読まない
  t = t.replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1");
  t = t.replace(/<https?:\/\/[^>\s]+>/gu, " ");
  t = t.replace(/https?:\/\/\S+/gu, " ");
  t = t.replace(/\b[\w.+-]+@[\w-]+\.[\w.]+\b/gu, " ");                // メールアドレスも読ませない

  // 3) 表は行ごとの区切りにする（縦棒をそのまま読ませない）
  t = t.replace(/^\s*\|?[\s:|-]+\|[\s:|-]*$/gmu, " ");                // 区切り行 |---|---|
  t = t.replace(/\|/gu, "、");

  // 4) 行頭の記号（見出し・箇条書き・引用）は落とす
  t = t.replace(/^\s{0,3}#{1,6}\s*/gmu, "");
  t = t.replace(/^\s{0,3}>+\s*/gmu, "");
  t = t.replace(/^\s*[-*+•]\s+/gmu, "");
  t = t.replace(/^\s*\d+[.)]\s+/gmu, "");
  t = t.replace(/^\s*[-*_]{3,}\s*$/gmu, " ");                         // 水平線

  // 5) 強調記号は外して中身を残す
  t = t.replace(/\*\*\*([^*]+)\*\*\*/g, "$1");
  t = t.replace(/\*\*([^*]+)\*\*/g, "$1");
  t = t.replace(/(?<!\w)\*([^*\n]+)\*(?!\w)/g, "$1");
  t = t.replace(/(?<!\w)_([^_\n]+)_(?!\w)/g, "$1");
  t = t.replace(/~~([^~]+)~~/g, "$1");

  // 6) 意味のある記号を読める形へ
  for (const [re, to] of MEANINGFUL) t = t.replace(re, to);

  // 7) 絵文字・ピクトグラム・飾り記号を落とす
  t = t.replace(/[\u{FE00}-\u{FE0F}\u{200D}\u{20E3}]/gu, "");         // 異体字セレクタ・ZWJ
  t = t.replace(/\p{Extended_Pictographic}/gu, " ");
  t = t.replace(/[\p{So}]/gu, " ");
  t = t.replace(DECORATIVE, " ");

  // 8) 体裁を整える
  t = t.replace(/[ \t　]+/gu, " ");
  t = t.replace(/\s*\n\s*/gu, "\n");
  t = t.replace(/\n{2,}/gu, "\n");
  t = t.replace(/、\s*(?=、)/gu, "");                                  // 読点の連続
  t = t.replace(/^[\s、。]+/u, "");
  t = t.replace(/([。！？])\s*、/gu, "$1");                            // 句点直後の読点
  t = t.replace(/\s+([。、！？])/gu, "$1");                            // 句読点の前の余白
  return t.trim();
}

/** 文の終わりとみなす文字。 */
const SENTENCE_END = /[。．.!！?？\n]/;

/**
 * 読み上げ単位に分ける。
 *
 * 1文ずつ渡すと、最初の文が用意でき次第すぐ喋り始められる。長すぎる塊を
 * そのまま渡すとブラウザの音声合成が途中で切れることがあるので、句読点でも
 * 折る。逆に短すぎる断片は前後にくっつける（「はい。」だけで一度切れると
 * ぶつ切りに聞こえるため）。
 */
export function splitForSpeech(text: string, maxLen = 120, minLen = 6): string[] {
  const clean = (text || "").trim();
  if (!clean) return [];

  // まず文末で切る
  const rough: string[] = [];
  let buf = "";
  for (const ch of clean) {
    buf += ch;
    if (SENTENCE_END.test(ch)) {
      const s = buf.trim();
      if (s) rough.push(s);
      buf = "";
    }
  }
  if (buf.trim()) rough.push(buf.trim());

  // 長すぎるものは読点で折る
  const sized: string[] = [];
  for (const s of rough) {
    if (s.length <= maxLen) { sized.push(s); continue; }
    let rest = s;
    while (rest.length > maxLen) {
      let cut = rest.lastIndexOf("、", maxLen);
      if (cut < minLen) cut = maxLen;         // 読点が無ければ諦めて長さで折る
      else cut += 1;                          // 読点は前の塊に含める
      sized.push(rest.slice(0, cut).trim());
      rest = rest.slice(cut);
    }
    if (rest.trim()) sized.push(rest.trim());
  }

  // 短すぎる塊は次とくっつける。「はい。」だけで一度切れるとぶつ切りに
  // 聞こえるため。先頭が短い場合も拾えるよう、後ろへ寄せる向きで繋ぐ。
  const out: string[] = [];
  for (const s of sized) {
    const prev = out[out.length - 1];
    if (prev && prev.length < minLen && prev.length + s.length <= maxLen) {
      out[out.length - 1] = `${prev}${s}`;
    } else {
      out.push(s);
    }
  }
  return out.filter(Boolean);
}

/**
 * 受信途中の文字列から、言い切った文だけを取り出す。
 *
 * 返答を受け取りながら喋るために使う。まだ続きが来るかもしれない末尾は
 * 残しておく（途中で切って読むと不自然になるため）。
 * 返り値の consumed は「何文字ぶん処理したか」で、次回はその続きから渡す。
 */
export function takeCompleteSentences(acc: string): { chunks: string[]; consumed: number } {
  if (!acc) return { chunks: [], consumed: 0 };

  // コードブロックの扱い。
  //   ・閉じていない間は、その手前までしか読まない（閉じるまで待つ）
  //   ・閉じたブロックは、その ``` までを1区切りとして読み切る
  // 「``` が来た時点」と「閉じた時点」で2回案内してしまう不具合と、
  // 閉じの ``` を残したまま先へ進めなくなる不具合の両方を防ぐ。
  const fences: number[] = [];
  for (let i = acc.indexOf("```"); i >= 0; i = acc.indexOf("```", i + 3)) fences.push(i);
  const limit = fences.length % 2 === 1 ? fences[fences.length - 1] : acc.length;

  // 最後の文末記号までが「言い切った」範囲
  let end = -1;
  for (let i = limit - 1; i >= 0; i--) {
    if (SENTENCE_END.test(acc[i])) { end = i; break; }
  }
  // 閉じたコードブロックの終わりも「言い切り」とみなす
  for (let k = 0; k + 1 < fences.length && fences[k + 1] < limit; k += 2) {
    end = Math.max(end, fences[k + 1] + 2);
  }
  if (end < 0) return { chunks: [], consumed: 0 };

  const ready = acc.slice(0, end + 1);
  const spoken = speakableText(ready);
  return { chunks: splitForSpeech(spoken), consumed: end + 1 };
}
