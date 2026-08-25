/**
 * freeOps — お金をかけずに、定期実行を確実に動かす方法。
 *
 * 事情:
 *   無料プランのサーバーは、しばらく使われないと寝る。寝ている間は時刻が来ても
 *   何も起きない。定期実行そのものは「時刻を過ぎて本日未実行なら走らせる」ので、
 *   外から起こしさえすれば追いついてくれる。
 *   つまり必要なのは「定期的に叩いてくれる誰か」だけ。
 *
 * 手はいくつもあって、どれも無料。しかもすでに持っているものばかりなので、
 * 新しくサービスに登録する必要がない。そこを画面から示す。
 *
 * 並びは「持っている可能性が高い順」。
 */

export type FreeOpsMethod = {
  id: string;
  name: string;
  /** すでに持っている前提のもの */
  youAlreadyHave: string;
  /** どれくらい正確に動くか */
  accuracy: string;
  steps: string[];
  /** そのまま貼れるもの（あれば） */
  snippet?: (opts: { apiUrl: string; hookUrl?: string }) => string;
  note?: string;
};

export const FREE_OPS: FreeOpsMethod[] = [
  {
    id: "github",
    name: "GitHub Actions（おすすめ）",
    youAlreadyHave: "このアプリのソースが置いてあるGitHub",
    accuracy: "毎時05分に確認（最大1時間の遅れ）",
    steps: [
      "GitHubでこのリポジトリを開く",
      "Settings → Secrets and variables → Actions",
      "「New repository secret」を押す",
      "名前に BACKEND_URL、値にバックエンドのURL（https://〜.onrender.com）を入れて保存",
      "Actions タブ →「Scheduler Tick」→ Run workflow で、いま動くか試せます",
    ],
    note:
      "設定は1回だけ。仕組みはもうリポジトリに入っています（.github/workflows/scheduler-tick.yml）。"
      + " 60日間リポジトリに動きが無いと、GitHubが自動で止めることがあります。",
  },
  {
    id: "supabase",
    name: "自分のSupabaseから起こす",
    youAlreadyHave: "保存先として繋いだSupabase",
    accuracy: "5分ごと（ほぼ時刻どおり）",
    steps: [
      "Supabase の SQL Editor を開く",
      "下のSQLを貼って実行する（1回だけ）",
      "以後、あなたのSupabaseが5分ごとにアプリを起こします",
    ],
    snippet: ({ apiUrl }) => `-- 5分ごとにアプリを起こして、時刻の来た予定を走らせる
-- （拡張の有効化は1回だけ。すでに有効なら何も起きません）
create extension if not exists pg_cron;
create extension if not exists pg_net;

select cron.schedule(
  'aibou-tick',
  '*/5 * * * *',
  $$ select net.http_post(
       url := '${apiUrl}/scheduler/tick',
       headers := '{"Content-Type":"application/json"}'::jsonb
     ) $$
);

-- やめるとき:  select cron.unschedule('aibou-tick');`,
    note:
      "Supabaseの無料プランで使えます。あなたのDBから叩くので、"
      + "他の人の設定に左右されません。",
  },
  {
    id: "shortcut",
    name: "iPhoneのショートカット",
    youAlreadyHave: "iPhone",
    accuracy: "自分で決めた時刻（オートメーションにすると自動）",
    steps: [
      "ショートカットアプリ →「オートメーション」→ 時刻",
      "アクションに「URLの内容を取得」を追加",
      "方法を POST にして、下のURLを入れる",
      "これで、その時刻に自動化が動きます",
    ],
    snippet: ({ hookUrl }) => hookUrl || "（先にトリガーを作ってください）",
    note: "スマホが圏外・電源オフのときは動きません。確実さを求めるなら上の2つを。",
  },
  {
    id: "cronjob",
    name: "外部の無料cron（cron-job.org など）",
    youAlreadyHave: "とくに無し（無料登録が要ります）",
    accuracy: "1分ごとまで指定できる",
    steps: [
      "cron-job.org などで無料登録する",
      "実行方法を POST にして、下のURLを登録する",
      "間隔を5〜15分にする",
    ],
    snippet: ({ apiUrl }) => `${apiUrl}/scheduler/tick`,
    note: "共通トークン（APP_TOKEN）を設定している場合は、"
      + "ヘッダに Authorization: Bearer <トークン> を足してください。",
  },
];

/** どれか1つやれば足りる、と伝えるための一言。 */
export const FREE_OPS_SUMMARY =
  "どれか1つで足ります。すでに持っているものから選んでください。"
  + "設定は1回だけで、あとは放っておけます。";
