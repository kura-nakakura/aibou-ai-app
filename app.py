import streamlit as st
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import json
import re

st.set_page_config(page_title="相棒AI ダッシュボード", page_icon="🤖", layout="wide")

# ==========================================
# 🔐 1. ログインシステム
# ==========================================
# セッション状態（ログインしているかどうかの記憶）を初期化
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 相棒AI 起動シークエンス")
    st.write("認証コードを入力してください。")
    
    password = st.text_input("Password", type="password")
    if st.button("システム起動 🚀"):
        # 秘密のパスワード（secrets.toml から読み込むか、無ければ "boss"）
        if password == st.secrets.get("APP_PASSWORD", "boss"): 
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("パスワードが違います。")
    st.stop() # ログインしていない場合はここで処理を止める（これより下は実行されない）

# ==========================================
# 🧭 2. サイドバー・ナビゲーション（ログイン成功後）
# ==========================================
st.sidebar.title("🤖 相棒AI メニュー")
page = st.sidebar.radio("モード選択", 
    ["💬 相棒とチャット＆依頼", "📋 現在のタスク", "🕰️ 過去のタスク", "📊 ダッシュボード", "🗝️ 秘密の保管庫"]
)

st.sidebar.divider()
if st.sidebar.button("ログアウト"):
    st.session_state.logged_in = False
    st.rerun()

# ==========================================
# 🧠 3. バックグラウンド設定（API・シート接続）
# ==========================================
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# スプレッドシートの読み込みはキャッシュして高速化
@st.cache_resource
def get_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    if "GOOGLE_CREDENTIALS" in st.secrets:
        creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    client = gspread.authorize(creds)
    return client.open("AibouAgent").worksheet("Agent_Brain")

try:
    sheet = get_sheet()
except Exception as e:
    st.error(f"データベース接続エラー: {e}")
    st.stop()

# ==========================================
# 🖥️ 4. メイン画面の切り替え表示
# ==========================================

# ------------------------------------------
# 💬 モード：相棒とチャット＆依頼
# ------------------------------------------
if page == "💬 相棒とチャット＆依頼":
    st.title("💬 相棒AI コマンドセンター")
    st.info("ここに相棒のアバターと、対話しながらタスクを依頼できるチャットUIを作ります！（次回実装！）")
    
    # とりあえず今の「作戦開始」機能はここに置いておきます
    st.markdown("### 🆕 暫定版：新規プロジェクト依頼")
    new_goal = st.text_area("相棒への新しい依頼:", placeholder="例：来週の東京の天気を調べて要約して")

    if st.button("作戦開始 🚀"):
        if new_goal:
            with st.status("🧠 相棒が作戦を立案中...", expanded=True) as status:
                try: 
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    prompt = f"""目標「{new_goal}」を達成するための具体的な手順を3〜5個のタスクに分解して。
                    出力は必ず以下のJSON形式のリストのみにして。余計な説明は不要。
                    [ {{"id": 1, "task": "..."}}, {{"id": 2, "task": "..."}} ]"""
                    
                    response = model.generate_content(prompt)
                    json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
                    
                    if json_match:
                        tasks = json.loads(json_match.group())
                        for t in tasks:
                            sheet.append_row([t['id'], new_goal, t['task'], "未着手", "", ""])
                        status.update(label="✅ 作戦をシートに書き込みました！「現在のタスク」を確認してください。", state="complete")
                    else:
                        status.update(label="⚠️ JSON解析失敗", state="error")
                        st.error("AIが指定通りのフォーマットで答えてくれませんでした。")
                        
                except Exception as e:
                    status.update(label="🚨 通信エラーまたはシステムエラー", state="error")
                    st.error(f"エラーの詳細: {e}")

# ------------------------------------------
# 📋 モード：現在のタスク（ボスのデザインを完全移植！）
# ------------------------------------------
elif page == "📋 現在のタスク":
    st.title("📋 現在のタスク")
    raw_data = sheet.get_all_values() 
    
    if len(raw_data) > 1:
        headers = ['タスクID', '目標', 'タスク内容', 'ステータス', 'ログ', 'ボスの回答']
        body = [row[:6] + [''] * (6 - len(row[:6])) for row in raw_data[1:]] 
        df = pd.DataFrame(body, columns=headers)
        
        # ボス作：カッコいいメトリクスボード
        st.markdown("### 📈 プロジェクト状況")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("総タスク数", len(df))
        col2.metric("未着手 📝", len(df[df['ステータス'] == '未着手']))
        col3.metric("実行中 ⚙️", len(df[df['ステータス'] == '実行中']))
        col4.metric("確認待ち 🚨", len(df[df['ステータス'] == '確認待ち']))
        st.divider()

        # ボス作：AIからの質問アクションエリア
        waiting_tasks = df[df['ステータス'] == '確認待ち']
        if not waiting_tasks.empty:
            st.warning("🚨 AIがあなたの指示を待っています！")
            for index, row in waiting_tasks.iterrows():
                with st.expander(f"質問: {row['タスク内容']}", expanded=True):
                    st.info(f"**AIからのメッセージ:**\n{row['ログ']}")
                    with st.form(key=f"form_{index}"):
                        answer = st.text_input("ボスの回答:")
                        submit = st.form_submit_button("回答を送信してタスクを再開 🚀")
                        if submit and answer:
                            sheet_row = index + 2 
                            sheet.update_cell(sheet_row, 6, answer)
                            sheet.update_cell(sheet_row, 4, "未着手")
                            st.success("指示を送信しました！画面を更新します...")
                            st.rerun()
            st.divider()

        # ボス作：カラー設定付きタスク一覧
        st.markdown("### 📋 進行中のタスク一覧")
        # 完了以外のタスクだけを表示するよう微調整
        current_df = df[df['ステータス'] != '完了'] 
        
        def color_status(val):
            color = 'white'
            if val == '完了': color = '#c8e6c9'
            elif val == '実行中': color = '#bbdefb'
            elif val == '確認待ち': color = '#ffcdd2'
            return f'background-color: {color}'
        
        styled_df = current_df.style.map(color_status, subset=['ステータス'])
        st.dataframe(styled_df, use_container_width=True)
    else:
        st.info("現在、登録されているタスクはありません。")

# ------------------------------------------
# 🕰️ モード：過去のタスク
# ------------------------------------------
elif page == "🕰️ 過去のタスク":
    st.title("🕰️ 過去のタスク (完了済み)")
    raw_data = sheet.get_all_values() 
    if len(raw_data) > 1:
        headers = ['タスクID', '目標', 'タスク内容', 'ステータス', 'ログ', 'ボスの回答']
        body = [row[:6] + [''] * (6 - len(row[:6])) for row in raw_data[1:]] 
        df = pd.DataFrame(body, columns=headers)
        
        # 完了したタスクだけを抽出して表示
        completed_df = df[df['ステータス'] == '完了']
        if not completed_df.empty:
            st.dataframe(completed_df, use_container_width=True)
        else:
            st.info("完了したタスクはまだありません。")

# ------------------------------------------
# 📊 モード：ダッシュボード
# ------------------------------------------
elif page == "📊 ダッシュボード":
    st.title("📊 ダッシュボード")
    st.info("ここに全体のグラフや、相棒の稼働状況などの分析画面を追加します！（次回実装！）")

# ------------------------------------------
# 🗝️ モード：秘密の保管庫
# ------------------------------------------
elif page == "🗝️ 秘密の保管庫":
    st.title("🗝️ 秘密の保管庫")
    st.warning("⚠️ 新しいAPIキー（Slack, n8nなど）を登録・管理する厳重管理エリアを作ります。（次回実装！）")