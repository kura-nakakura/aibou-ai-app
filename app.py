import streamlit as st
import google.generativeai as genai

# --- 🔑 シークレットからAPIキーを読み込む ---
# ローカルなら secrets.toml、クラウドなら管理画面のSecretsを勝手に見に行ってくれます
if "GEMINI_API_KEY" in st.secrets:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_API_KEY)
else:
    st.error("APIキーが設定されていません。")

# （以下、スプレッドシートの認証なども同様に st.secrets で管理可能です）

# 画面のタイトルとレイアウト設定
st.set_page_config(page_title="相棒AI ダッシュボード", layout="wide")
st.title("🤖 相棒AI コントロールパネル")

# 認証設定
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

try:
    creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    client = gspread.authorize(creds)
    sheet = client.open("AibouAgent").worksheet("Agent_Brain")
    raw_data = sheet.get_all_values() 
    
    if len(raw_data) > 1:
        # ★エラーを完全に防ぐため、列の名前と数を強制的に固定！
        headers = ['タスクID', '目標', 'タスク内容', 'ステータス', 'ログ', 'ボスの回答']
        # 空の列があってもエラーにならないように整形
        body = [row[:6] + [''] * (6 - len(row[:6])) for row in raw_data[1:]] 
        
        df = pd.DataFrame(body, columns=headers)
        
        # ==========================================
        # 📊 1. カッコいいメトリクス（数字）ボード
        # ==========================================
        st.markdown("### 📈 プロジェクト状況")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("総タスク数", len(df))
        col2.metric("未着手 📝", len(df[df['ステータス'] == '未着手']))
        col3.metric("実行中 ⚙️", len(df[df['ステータス'] == '実行中']))
        col4.metric("確認待ち 🚨", len(df[df['ステータス'] == '確認待ち']))
        
        st.divider() # 区切り線

        # ==========================================
        # 🙋‍♂️ 2. AIからの質問に答えるアクションエリア
        # ==========================================
        waiting_tasks = df[df['ステータス'] == '確認待ち']
        
        if not waiting_tasks.empty:
            st.warning("🚨 AIがあなたの指示を待っています！")
            
            for index, row in waiting_tasks.iterrows():
                with st.expander(f"質問: {row['タスク内容']}", expanded=True):
                    st.info(f"**AIからのメッセージ:**\n{row['ログ']}")
                    
                    # 回答入力フォーム
                    with st.form(key=f"form_{index}"):
                        answer = st.text_input("ボスの回答:")
                        submit = st.form_submit_button("回答を送信してタスクを再開 🚀")
                        
                        if submit and answer:
                            # スプレッドシートの書き込む行を計算（ヘッダー1行 + インデックス + 1）
                            sheet_row = index + 2 
                            
                            # F列(6番目)に回答を書き込み、D列(4番目)を「未着手」に戻す
                            sheet.update_cell(sheet_row, 6, answer)
                            sheet.update_cell(sheet_row, 4, "未着手")
                            
                            st.success("指示を送信しました！画面を更新します...")
                            st.rerun() # 画面を自動リロード
                            
        st.divider()

        # ==========================================
        # 📋 3. タスク一覧表
        # ==========================================
        st.markdown("### 📋 タスク一覧")
        
        # ステータスごとに色を付ける設定（おまけのオシャレ機能）
        def color_status(val):
            color = 'white'
            if val == '完了': color = '#c8e6c9' # 薄い緑
            elif val == '実行中': color = '#bbdefb' # 薄い青
            elif val == '確認待ち': color = '#ffcdd2' # 薄い赤
            return f'background-color: {color}'
        
        styled_df = df.style.map(color_status, subset=['ステータス'])
        st.dataframe(styled_df, use_container_width=True)

    else:
        st.info("現在、登録されているタスクはありません。スプレッドシートから新しい目標を依頼してください！")

except Exception as e:
    st.error(f"🚨 エラーが発生しました: {e}")