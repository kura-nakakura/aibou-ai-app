/**
 * はじめる手順（初回設定）。
 *
 * ここはフロント側に置いてある。理由:
 *   この手順は「まだ何も繋がっていない人」が読むもの。バックエンドから
 *   取ってくる作りにしていたため、繋がっていないと手順そのものが消え、
 *   「自分のDBを繋ぎたいのに、繋ぎ方がどこにも書いていない」状態になった。
 *   繋がる前に必要な案内を、繋がらないと読めない場所に置いてはいけない。
 *
 * 貼り付けるSQLは public/supabase_schema.sql をそのまま配信する
 * （本文に書き写すと、本物のスキーマと必ずズレる）。
 *
 * 書くときの決まり
 *   ・押すボタンの文言、成功したときの表示まで書く
 *   ・つまずくところは先回りして書く（あとで問い合わせになる）
 */

export interface SetupStep {
  id: string;
  title: string;
  /** なぜ必要か。意味が分かると間違えにくい。 */
  detail?: string;
  /** 実際の操作。見たままの文言で。 */
  steps: string[];
  /** 貼り付けるものを、この場所から取ってくる。 */
  codeUrl?: string;
  codeLabel?: string;
  /** つまずきどころ・やってはいけないこと。 */
  caution?: string[];
}

/** 貼り付け用のSQL（アプリ自身が配信する。バックエンド不要）。 */
export const SCHEMA_SQL_URL = "/supabase_schema.sql";

export const SETUP_STEPS: SetupStep[] = [
  {
    id: "account",
    title: "1. アカウントを作る",
    detail: "ログインすると、あなたのデータが他の人と混ざらないように分けられます。",
    steps: [
      "最初の画面で「アカウントを作成」を押す",
      "メールアドレスとパスワード（6文字以上）を入れる",
      "「データの扱い」を読んで、チェックを入れる",
      "「アカウント作成」を押す",
      "確認メールが届いたら、リンクを開いてからサインインする",
    ],
    caution: [
      "確認メールが来ないときは、迷惑メールフォルダを見てください。",
      "「このメールアドレスは登録済みです」と出たら、作成ではなくサインインしてください。",
    ],
  },
  {
    id: "supabase-project",
    title: "2. 自分の保存先（Supabase）を作る",
    detail:
      "あなたのタスク・予定・記録は、あなた自身のデータベースに入ります。"
      + "無料の枠で足ります。作るのは1回だけです。",
    steps: [
      "supabase.com を開いて、GitHubアカウントなどで登録する",
      "「New project」を押す",
      "Name は好きな名前（例: aibou）。Database Password は自動生成のままでよい（控えておく）",
      "Region は Northeast Asia (Tokyo) を選ぶと速い",
      "「Create new project」を押して、2分ほど待つ",
    ],
    caution: ["Database Password は再表示できません。控えを取ってください。"],
  },
  {
    id: "supabase-sql",
    title: "3. 保存する場所（テーブル）を作る",
    detail:
      "アプリが読み書きする入れ物を用意します。下のSQLを丸ごと貼って実行するだけです。"
      + "中身は理解しなくて構いません。",
    steps: [
      "Supabase の左メニューから「SQL Editor」を開く",
      "「New query」を押す",
      "下のボタンでSQLをコピーして、エディタに貼り付ける",
      "右下の「Run」を押す",
      "「Success. No rows returned」と出れば成功",
    ],
    codeUrl: SCHEMA_SQL_URL,
    codeLabel: "Supabase の SQL Editor に貼り付けるSQL",
    caution: [
      "何度実行しても大丈夫です（既にあるものは作り直しません。データも消えません）。",
      "赤いエラーが出た場合は、貼り付けが途中で切れていないか確認してください。",
    ],
  },
  {
    id: "supabase-keys",
    title: "4. 接続情報を取り出す",
    detail: "アプリがあなたのデータベースへ入るための、住所と鍵です。",
    steps: [
      "Supabase の左メニュー下部の「Project Settings」→「API」を開く",
      "「Project URL」をコピーする（https://xxxxx.supabase.co の形）",
      "同じ画面の「Project API keys」から service_role の鍵をコピーする（Reveal を押すと見えます）",
    ],
    caution: [
      "service_role の鍵は、あなたのデータベースを何でもできる強い鍵です。"
      + "人に見せない、チャットに貼らない、スクリーンショットに写さないでください。",
      "anon キーではありません。service_role のほうです。",
    ],
  },
  {
    id: "connect",
    title: "5. アプリに繋ぐ",
    detail: "ここまで来れば、あとは貼るだけです。",
    steps: [
      "画面右上の歯車（設定）を押す",
      "上のタブから「KEYCHAIN」を選ぶ",
      "「自分のデータベース」の欄に、4で取った URL と service_role キーを貼る",
      "「接続」を押す",
      "「接続できました」と出れば完了。以後、あなたのデータはここに入ります",
    ],
    caution: [
      "繋ぐまでは、入力した内容はどこにも保存されません（再読み込みで消えます）。",
      "「ログインしていないため使えません」と出る場合は、先にサインインしてください。",
    ],
  },
  {
    id: "ai-key",
    title: "6. AIの鍵を入れる",
    detail:
      "AIが考えるための鍵です。管理者が共通の鍵を用意している場合は不要です"
      + "（設定 → KEYCHAIN で GEMINI_API_KEY が「設定済み」なら飛ばしてください）。",
    steps: [
      "aistudio.google.com/app/apikey を開く",
      "Googleアカウントでログインし、「Create API key」を押す",
      "表示された鍵（AIza… で始まる文字列）をコピーする",
      "設定 →「KEYCHAIN」→ GEMINI_API_KEY に貼って保存する",
    ],
    caution: [
      "自分の鍵を入れると、利用料は自分の枠から引かれます（無料枠があります）。",
      "鍵は暗号化して保存され、画面には伏せ字でしか出ません。",
    ],
  },
  {
    id: "try",
    title: "7. 使ってみる",
    detail: "ここまでで準備は終わりです。",
    steps: [
      "CHAT に「明日15時に歯医者の予定を入れて」と書いて送る",
      "TASKS や HOME を開いて、入っていることを確かめる",
      "うまくいかないときは、設定 →「DIAGNOSTICS」で接続状態を見る",
    ],
  },
];
