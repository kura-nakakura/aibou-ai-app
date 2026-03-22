import streamlit as st
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import json
import re

# --- 🔑 シークレットからAPIキーを読み込む ---
if "GEMINI_API_KEY" in st.secrets:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_API_KEY)
else:
    st.error("APIキーが設定されていません。")

# 画面のタイトルとレイアウト設定
st.set_page_config(page_title="相棒AI ダッシュボード", layout="wide")
st.title("🤖 相棒AI コントロールパネル")

# 認証設定
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

try:
    # 🌟 クラウドとローカルで鍵の取り出し方を自動で切り替える！
    if "GOOGLE_CREDENTIALS" in st.secrets:
        # クラウド（Streamlit）の場合：Secretsから読み込む
        creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        # 手元のPC（VS Code）の場合：ファイルから読み込む
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        
    client = gspread.authorize(creds)
    sheet = client.open("AibouAgent").worksheet("Agent_Brain")
    
    # ==========================================
    # 🚀 NEW: サイドバーから新しい目標を依頼する（API節約の要！）
    # ==========================================
    st.sidebar.title("🆕 新規プロジェクト")
    new_goal = st.sidebar.text_area("相棒への新しい依頼:", placeholder="例：来週の東京の天気を調べて要約して")

    if st.sidebar.button("作戦開始 🚀"):
        if new_goal:
            with st.status("🧠 相棒が作戦を立案中...", expanded=True) as status:
                try: # ★エラーを捕まえる網をここにも張る！
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    prompt = f"""目標「{new_goal}」を達成するための具体的な手順を3〜5個のタスクに分解して。
                    出力は必ず以下のJSON形式のリストのみにして。余計な説明は不要。
                    [ {{"id": 1, "task": "..."}}, {{"id": 2, "task": "..."}} ]"""
                    
                    response = model.generate_content(prompt)
                    
                    # 💡 デバッグ：AIが実際に何と答えたか画面に出してみる
                    st.write("【AIの生の回答（デバッグ用）】")
                    st.code(response.text)
                    
                    json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
                    
                    if json_match:
                        tasks = json.loads(json_match.group())
                        for t in tasks:
                            sheet.append_row([t['id'], new_goal, t['task'], "未着手", "", ""])
                        status.update(label="✅ 作戦をシートに書き込みました！", state="complete")
                        st.rerun()
                    else:
                        status.update(label="⚠️ JSON解析失敗", state="error")
                        st.error("AIが指定通りのフォーマットで答えてくれませんでした。")
                        
                except Exception as e:
                    # 🚨 何かエラーが起きたら、ここでローディングを止めて詳細を出す！
                    status.update(label="🚨 通信エラーまたはシステムエラー", state="error")
                    st.error(f"エラーの詳細: {e}")

    # ==========================================
    # 📊 メイン画面のデータ処理
    # ==========================================
    raw_data = sheet.get_all_values() 
    
    if len(raw_data) > 1:
        headers = ['タスクID', '目標', 'タスク内容', 'ステータス', 'ログ', 'ボスの回答']
        body = [row[:6] + [''] * (6 - len(row[:6])) for row in raw_data[1:]] 
        
        df = pd.DataFrame(body, columns=headers)
        
        # 1. カッコいいメトリクス（数字）ボード
        st.markdown("### 📈 プロジェクト状況")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("総タスク数", len(df))
        col2.metric("未着手 📝", len(df[df['ステータス'] == '未着手']))
        col3.metric("実行中 ⚙️", len(df[df['ステータス'] == '実行中']))
        col4.metric("確認待ち 🚨", len(df[df['ステータス'] == '確認待ち']))
        
        st.divider()

        # 2. AIからの質問に答えるアクションエリア
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

        # 3. タスク一覧表（ボスのカラー設定を維持！）
        st.markdown("### 📋 タスク一覧")
        
        def color_status(val):
            color = 'white'
            if val == '完了': color = '#c8e6c9' # 薄い緑
            elif val == '実行中': color = '#bbdefb' # 薄い青
            elif val == '確認待ち': color = '#ffcdd2' # 薄い赤
            return f'background-color: {color}'
        
        styled_df = df.style.map(color_status, subset=['ステータス'])
        st.dataframe(styled_df, use_container_width=True)

    else:
        st.info("現在、登録されているタスクはありません。左のサイドバーから新しい目標を依頼してください！")

except Exception as e:
    st.error(f"🚨 エラーが発生しました: {e}")
