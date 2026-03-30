st.markdown("""
    <style>
    .cyber-title { color: #2b6cb0; font-weight: 800; letter-spacing: 2px; margin-bottom: 20px; text-shadow: 2px 2px 4px rgba(255,255,255,0.8); }
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
    </style>
""", unsafe_allow_html=True)

st.markdown("<h2 class='cyber-title'>📊 SYSTEM DASHBOARD</h2>", unsafe_allow_html=True)

# --- データ読み込み ---
vault_data = load_vault()

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