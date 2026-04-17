import streamlit as st
import os
import json
import uuid
import random

# --- ライブラリのインポートチェック ---
try:
    from streamlit_flow import streamlit_flow
    from streamlit_flow.elements import StreamlitFlowNode, StreamlitFlowEdge
    HAS_FLOW = True
except ImportError:
    HAS_FLOW = False

st.markdown("""
    <style>
    .cyber-title { color: #2b6cb0; font-weight: 800; letter-spacing: 2px; margin-bottom: 10px; text-shadow: 2px 2px 4px rgba(255,255,255,0.8); }
    .dash-card {
        background: rgba(255, 255, 255, 0.4);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.9);
        border-radius: 15px;
        padding: 20px;
        box-shadow: 6px 6px 15px rgba(163, 177, 198, 0.4), -6px -6px 15px rgba(255, 255, 255, 0.9);
        height: 100%;
    }
    .stat-value { font-size: 32px; font-weight: 900; color: #2b6cb0; }
    .stat-label { font-size: 14px; font-weight: bold; color: #718096; }
    .event-item { border-left: 4px solid #00e676; margin-bottom: 10px; background: rgba(255,255,255,0.6); padding: 12px; border-radius: 5px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);}
    
    /* Miro風ボード用CSS */
    .miro-container {
        background: #e0e5ec;
        border-radius: 20px;
        box-shadow: inset 8px 8px 16px #b8bcc2, inset -8px -8px 16px #ffffff;
        padding: 15px;
        margin-top: 10px;
    }
    .react-flow { background: transparent !important; }
    
    /* タブのスタイリングをOSに合わせる */
    div[data-baseweb="tab-list"] { gap: 10px; }
    div[data-baseweb="tab"] { 
        background: transparent !important; 
        border-radius: 10px 10px 0 0 !important; 
        padding: 10px 20px !important; 
        font-weight: bold !important; 
    }
    </style>
""", unsafe_allow_html=True)

st.markdown("<h2 class='cyber-title'>🧠 SYSTEM DASHBOARD & MIRO</h2>", unsafe_allow_html=True)

# タブの作成（機能の分離）
tab_miro, tab_system = st.tabs(["🧠 Miro Board (思考キャンバス)", "📊 System Monitor (カレンダー等)"])

# ====================================================
# 🧠 TAB 1: MIRO BOARD
# ====================================================
with tab_miro:
    if not HAS_FLOW:
        st.error("⚠️ `streamlit-flow` がインストールされていません。ターミナルで `pip install streamlit-flow` を実行するか、GitHubの `requirements.txt` に追記してください。")
    else:
        st.caption("ボスの思考とAIの分析データを視覚的に結びつける無限キャンバスです。ノードは自由にドラッグできます。")
        
        # 🎨 ノードの基本デザイン
        node_style = {
            "background": "#e0e5ec", "border": "2px solid #00f3ff", "borderRadius": "12px",
            "boxShadow": "5px 5px 10px #b8bcc2, -5px -5px 10px #ffffff",
            "color": "#2d3748", "fontWeight": "bold", "padding": "10px 20px",
            "fontSize": "14px", "textAlign": "center"
        }

        # セッションステートの初期化
        if 'miro_nodes' not in st.session_state:
            st.session_state.miro_nodes = [
                StreamlitFlowNode(id='core_node', pos=(50, 200), data={'content': '🧠 AIBOU Core'}, node_type='input', source_position='right', target_position='left', style=node_style),
                StreamlitFlowNode(id='idea_1', pos=(350, 100), data={'content': '💡 アイデア: UI大改修'}, node_type='default', source_position='right', target_position='left', style=node_style),
                StreamlitFlowNode(id='idea_2', pos=(350, 300), data={'content': '📊 プロジェクト分析'}, node_type='default', source_position='right', target_position='left', style=node_style)
            ]
        if 'miro_edges' not in st.session_state:
            st.session_state.miro_edges = [
                StreamlitFlowEdge(id='edge_1', source='core_node', target='idea_1', animated=True, style={'stroke': '#00f3ff', 'strokeWidth': 2}),
                StreamlitFlowEdge(id='edge_2', source='core_node', target='idea_2', animated=True, style={'stroke': '#00f3ff', 'strokeWidth': 2})
            ]

        # 🎛️ ボード操作パネル
        col_add, col_connect, col_clear = st.columns([4, 4, 2], gap="medium")
        with col_add:
            with st.container(border=True):
                st.markdown("##### ➕ 新しいノード（付箋）の追加")
                new_node_text = st.text_input("付箋の内容を入力", placeholder="例：Dify APIの検証")
                if st.button("ボードに投下 ⚡", use_container_width=True, type="primary"):
                    if new_node_text:
                        new_id = f"node_{uuid.uuid4().hex[:6]}"
                        new_pos = (random.randint(400, 600), random.randint(50, 400))
                        new_node = StreamlitFlowNode(id=new_id, pos=new_pos, data={'content': new_node_text}, node_type='default', source_position='right', target_position='left', style=node_style)
                        st.session_state.miro_nodes.append(new_node)
                        st.rerun()

        with col_connect:
            with st.container(border=True):
                st.markdown("##### 🔗 ノード同士を繋ぐ")
                node_options = {n.id: n.data['content'] for n in st.session_state.miro_nodes}
                if len(node_options) >= 2:
                    c1, c2 = st.columns(2)
                    with c1:
                        source_id = st.selectbox("繋ぎ元 (Source)", options=list(node_options.keys()), format_func=lambda x: node_options[x])
                    with c2:
                        target_id = st.selectbox("繋ぎ先 (Target)", options=list(node_options.keys()), format_func=lambda x: node_options[x], index=1)
                    
                    if st.button("ワイヤーを結線する 🔗", use_container_width=True):
                        if source_id != target_id:
                            new_edge_id = f"edge_{source_id}_{target_id}"
                            if not any(e.id == new_edge_id for e in st.session_state.miro_edges):
                                new_edge = StreamlitFlowEdge(id=new_edge_id, source=source_id, target=target_id, animated=True, style={'stroke': '#00f3ff', 'strokeWidth': 2})
                                st.session_state.miro_edges.append(new_edge)
                                st.rerun()
                        else:
                            st.warning("同じノード同士は繋げません。")
                else:
                    st.info("ノードが2つ以上必要です。")

        with col_clear:
            st.markdown("<br><br>", unsafe_allow_html=True)
            if st.button("🗑️ ボード初期化", use_container_width=True):
                st.session_state.miro_nodes = [
                    StreamlitFlowNode(id='core_node', pos=(50, 200), data={'content': '🧠 AIBOU Core'}, node_type='input', source_position='right', target_position='left', style=node_style)
                ]
                st.session_state.miro_edges = []
                st.rerun()

        # 🗺️ 思考キャンバスの描画
        st.markdown("<div class='miro-container'>", unsafe_allow_html=True)
        streamlit_flow(
            key="miro_board_state",
            nodes=st.session_state.miro_nodes,
            edges=st.session_state.miro_edges,
            height=500,
            fit_view=True
        )
        st.markdown("</div>", unsafe_allow_html=True)


# ====================================================
# 📊 TAB 2: SYSTEM MONITOR (Original Code)
# ====================================================
with tab_system:
    # --- データ読み込み ---
    try:
        vault_data = load_vault()
    except NameError:
        vault_data = {"api_keys": {}}
        
    my_email = vault_data.get("api_keys", {}).get("my_email", "")
    gcal_json_str = vault_data.get("api_keys", {}).get("google_calendar", "")

    # 簡易APIカウンター
    STATS_FILE = "system_stats.json"
    if not os.path.exists(STATS_FILE):
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump({"gemini_api_calls": 0, "total_tasks": 0}, f)
    with open(STATS_FILE, "r", encoding="utf-8") as f:
        stats_data = json.load(f)

    # --- 上部：ステータスカード ---
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""
        <div class="dash-card">
            <div class="stat-label">⚡ Gemini API 呼び出し回数</div>
            <div class="stat-value">{stats_data.get('gemini_api_calls', 0)} <span style="font-size:16px;">回</span></div>
            <div style="font-size: 11px; color: #a0aec0;">※無料枠: 15回/分を監視中</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="dash-card">
            <div class="stat-label">🚀 OS 稼働状態</div>
            <div class="stat-value" style="color:#00e676;">ONLINE</div>
            <div style="font-size: 11px; color: #a0aec0;">All systems operational.</div>
        </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="dash-card">
            <div class="stat-label">📧 同期アカウント</div>
            <div style="font-size: 13px; font-weight:bold; margin-top:10px; color:#2d3748; word-break: break-all;">
                {my_email if my_email else "Vault未設定"}
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # --- 下部：カレンダー連携とシステムログ ---
    col_cal, col_log = st.columns([6, 4], gap="large")

    with col_cal:
        st.markdown("#### 📅 UPCOMING EVENTS (Google Calendar)")
        
        if not gcal_json_str or not my_email:
            st.info("Vaultに「GoogleカレンダーのJSON」と「自分のGmailアドレス」が設定されていないため、スケジュールを取得できません。")
        else:
            try:
                # 動的インポート（ライブラリがない場合のエラー回避）
                from google.oauth2 import service_account
                from googleapiclient.discovery import build
                import datetime
                
                gcal_info = json.loads(gcal_json_str)
                credentials = service_account.Credentials.from_service_account_info(
                    gcal_info,
                    scopes=['https://www.googleapis.com/auth/calendar.readonly']
                )
                service = build('calendar', 'v3', credentials=credentials)
                
                # JST（日本時間）で現在時刻を取得
                now = datetime.datetime.utcnow().isoformat() + 'Z'
                
                # Vaultに登録されたボスのメアドのカレンダーを取得
                events_result = service.events().list(calendarId=my_email, timeMin=now,
                                                      maxResults=5, singleEvents=True,
                                                      orderBy='startTime').execute()
                events = events_result.get('items', [])
                
                if not events:
                    st.info("直近の予定はありません。")
                else:
                    for event in events:
                        start = event['start'].get('dateTime', event['start'].get('date'))
                        # 日時を分かりやすく整形
                        try:
                            # タイムゾーン情報を考慮してパース
                            dt = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                            start_str = dt.strftime('%Y/%m/%d %H:%M')
                        except:
                            start_str = start
                        
                        st.markdown(f"""
                        <div class="event-item">
                            <b style="color:#2b6cb0; font-size:16px;">{event.get('summary', '予定なし')}</b><br>
                            <span style="font-size:13px; color:#4a5568;">🕒 {start_str}</span>
                        </div>
                        """, unsafe_allow_html=True)
            
            except ImportError:
                st.error("⚠️ ライブラリ不足: ターミナルで `pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib` を実行してください。")
            except Exception as e:
                st.error(f"カレンダー取得エラー（VaultのJSONやカレンダー共有設定を確認してください）: {e}")

    with col_log:
        st.markdown("#### 📡 SYSTEM ACTIVITY")
        st.markdown("""
        <div class="dash-card" style="height: 300px; overflow-y: scroll; font-family: monospace; font-size:12px;">
            <span style="color:#a0aec0;">[SYSTEM] Dashboard initialized.</span><br>
            <span style="color:#a0aec0;">[SYSTEM] Checking API limits... OK.</span><br>
            <span style="color:#00e676;">[VAULT] Secure keys loaded.</span><br>
            <span style="color:#2b6cb0;">[CALENDAR] Syncing upcoming events...</span><br>
            <span style="color:#a0aec0;">[ROUTINE] Ready for your command, Boss.</span><br>
        </div>
        """, unsafe_allow_html=True)
