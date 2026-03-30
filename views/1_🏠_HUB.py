if "hub_view_mode" not in st.session_state: st.session_state.hub_view_mode = "CORE"

# 純粋なNeumorphismと完全なグリッドレイアウト（変なズレ一切なし）
st.markdown("""
    <style>
    /* 🚨 画面全体の無駄な縦スクロールバーを完全に消去 */
    [data-testid="stAppViewContainer"] { overflow-y: hidden !important; }
    
    .hub-title { 
        text-align: center; color: #4a5568; font-weight: 300;
        letter-spacing: 12px; margin-bottom: 40px; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    
    div.stButton > button {
        background: #e0e5ec !important; 
        border: none !important; border-radius: 15px !important; 
        color: #4a5568 !important; font-weight: 700 !important; letter-spacing: 2px !important;
        box-shadow: 6px 6px 12px #b8bcc2, -6px -6px 12px #ffffff !important;
        transition: all 0.2s ease !important; padding: 10px !important; font-size: 13px !important;
    }
    div.stButton > button:hover {
        box-shadow: inset 4px 4px 8px #b8bcc2, inset -4px -4px 8px #ffffff !important;
        color: #00f3ff !important;
    }
    
    .view-toggle button {
        border-radius: 20px !important; padding: 5px 15px !important; font-size: 11px !important;
        background: transparent !important; box-shadow: none !important; color: #718096 !important;
        border: 1px solid #cbd5e0 !important; width: auto !important; display: inline-block;
    }
    .view-toggle button:hover { color: #00f3ff !important; border-color: #00f3ff !important; background: transparent !important; }
    </style>
""", unsafe_allow_html=True)

st.markdown("<h2 class='hub-title'>THE FORGE OS</h2>", unsafe_allow_html=True)

if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "ai_voice_base64" not in st.session_state: st.session_state.ai_voice_base64 = None
if "just_generated_audio" not in st.session_state: st.session_state.just_generated_audio = False
if "pending_event" not in st.session_state: st.session_state.pending_event = None 

v_data = st.session_state.ai_voice_base64 if st.session_state.ai_voice_base64 else ""
autoplay_attr = "autoplay" if st.session_state.just_generated_audio else ""
st.session_state.just_generated_audio = False 

# 👑 カラムを [1 : 1.2 : 1] の美しいグリッドに完全固定（コアは絶対動かない）
core_height = 350
col_left, col_core, col_right = st.columns([0.7, 1.6, 0.7], gap="large")

with col_left:
    st.markdown("<div class='view-toggle'>", unsafe_allow_html=True)
    toggle_label = "🌐 CORE" if st.session_state.hub_view_mode == "HUB" else "🌐 HUB VIEW"
    if st.button(toggle_label, key="toggle_view"):
        st.session_state.hub_view_mode = "CORE" if st.session_state.hub_view_mode == "HUB" else "HUB"
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.hub_view_mode == "HUB":
        st.markdown("<p style='text-align:center; font-weight:bold; color:#a0aec0; letter-spacing:3px; font-size:11px; margin-bottom:15px;'>[ MODES ]</p>", unsafe_allow_html=True)
        if st.button("FORGE LAB", use_container_width=True): st.session_state.current_mode = "Forge Lab"; st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("DATA VAULT", use_container_width=True): st.session_state.current_mode = "Document Vault"; st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("ACTIVE TASKS", use_container_width=True): st.session_state.current_mode = "Active Tasks"; st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("EVOLUTION", use_container_width=True): st.session_state.current_mode = "Core Upgrade"; st.rerun()

with col_core:
    # 指示に従い、コアの位置を中央に押し下げるために上部に余白を追加
    st.markdown("<br><br>", unsafe_allow_html=True)
    # コア部分は高さに余裕を持たせているため、下のSYSTEM ONLINEが一切見切れない
    core_html = MASTER_CORE_TEMPLATE.replace("H_VAL", str(core_height)).replace("MAX_Wpx", "300").replace("V_DATA", v_data).replace("A_PLAY", autoplay_attr)
    st.components.v1.html(core_html, height=core_height + 20)
    
    if st.session_state.hub_view_mode == "CORE":
        with st.container(height=300, border=False):
            for m in st.session_state.chat_history:
                with st.chat_message(m["role"], avatar=m["avatar"]):
                    st.markdown(m["content"])

with col_right:
    st.markdown("<br><br><br><br>", unsafe_allow_html=True) 
    if st.session_state.hub_view_mode == "HUB":
        st.markdown("<p style='text-align:center; font-weight:bold; color:#a0aec0; letter-spacing:3px; font-size:11px; margin-bottom:15px;'>[ MANAGEMENT ]</p>", unsafe_allow_html=True)
        if st.button("DASHBOARD", use_container_width=True): st.session_state.current_mode = "Dashboard"; st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("APP ARCHIVE", use_container_width=True): st.session_state.current_mode = "App Archive"; st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("TASK HISTORY", use_container_width=True): st.session_state.current_mode = "Task History"; st.rerun()
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("SETTINGS", use_container_width=True): st.session_state.current_mode = "Settings"; st.rerun()

# ------------------------------------------
# 🚨 カレンダー機能・マイク・AIチャット処理
# ------------------------------------------
if st.session_state.pending_event:
    pe = st.session_state.pending_event
    st.warning(f"📅 以下の予定をカレンダーに登録しますか？\n\n**{pe['title']}**\n開始: {pe['start']}\n終了: {pe['end']}")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ 登録する (Approve)", use_container_width=True, key="cal_approve"):
            with st.spinner("カレンダーに登録中..."):
                cal_json = st.session_state.global_api_keys.get("google_calendar", "")
                cal_service = get_calendar_service(cal_json)
                success = create_calendar_event(cal_service, pe['title'], pe['start'], pe['end'])
                if success:
                    st.session_state.chat_history.append({"role": "assistant", "avatar": "🤖", "content": f"📅 「{pe['title']}」をカレンダーに登録しました！"})
                else:
                    st.session_state.chat_history.append({"role": "assistant", "avatar": "🤖", "content": "❌ カレンダーの登録に失敗しました。VaultのJSON設定を確認してください。"})
            st.session_state.pending_event = None
            st.rerun()
    with c2:
        if st.button("❌ キャンセル (Reject)", use_container_width=True, key="cal_reject"):
            st.session_state.chat_history.append({"role": "assistant", "avatar": "🤖", "content": "登録をキャンセルしました。"})
            st.session_state.pending_event = None
            st.rerun()

st.markdown("""
    <style>
    iframe[title*='mic'] { mix-blend-mode: multiply !important; opacity: 0.7; transition: all 0.3s ease-in-out; } 
    iframe[title*='mic']:hover { opacity: 1.0; filter: drop-shadow(0px 5px 8px rgba(0, 243, 255, 0.6)); transform: translateY(-2px); } 
    [data-testid='stVerticalBlock'] > div:has(iframe[title*='mic']) { margin-bottom: -25px !important; position: relative; z-index: 50; }
    </style>
""", unsafe_allow_html=True)

col1, col2, col3 = st.columns([5, 3, 5]) 
with col2:
    spoken_text = speech_to_text(language='ja', start_prompt="🎙️ PUSH TO TALK", stop_prompt="🛑 TAP TO SEND", use_container_width=True, just_once=True, key='STT')

if not st.session_state.pending_event:
    if spoken_text:
        st.session_state.chat_history.append({"role": "user", "avatar": "👤", "content": spoken_text})
        st.rerun()

    if prompt := st.chat_input("コマンドを入力してください、ボス", key="console_input"):
        st.session_state.chat_history.append({"role": "user", "avatar": "👤", "content": prompt})
        st.rerun()

if st.session_state.chat_history and st.session_state.chat_history[-1]["role"] == "user" and not st.session_state.pending_event:
    last_prompt = st.session_state.chat_history[-1]["content"]
    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner(" "):
            gemini_key = st.session_state.global_api_keys.get("gemini", "")
            if gemini_key:
                genai.configure(api_key=gemini_key)
            
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            system_instruction = f"""
            あなたは総合システム「THE FORGE」全体を統括するメインの相棒AI（マスターAI）です。
            単なるカレンダー秘書ではなく、ボスの右腕としてあらゆる相談、技術的な質問、ブレインストーミング、日常の会話に高度な知性で対応してください。

            【現在の状況】
            現在時刻: {now_str}

            【カレンダー登録時のシステムコマンド（絶対ルール）】
            会話の流れでユーザーから「〇〇の予定を追加して」「アポを入れといて」と明確に頼まれた場合【のみ】、システムを動かすために返答の最後に以下の隠しコマンドを出力してください。普段の会話では絶対に出力しないでください。
            形式: [CALENDAR_ADD: 予定のタイトル | YYYY-MM-DDTHH:MM:00 | YYYY-MM-DDTHH:MM:00]
            例: [CALENDAR_ADD: 会議 | 2026-03-27T15:00:00 | 2026-03-27T16:00:00]
            """
            
            model = genai.GenerativeModel(model_name='gemini-2.5-flash')
            history_text = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.chat_history[:-1]])
            full_prompt = system_instruction + "\n\n【会話履歴】\n" + history_text + "\n\nボス: " + last_prompt

            response = model.generate_content(full_prompt)
            ai_text = response.text
            
            match = re.search(r'\[CALENDAR_ADD:\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\]', ai_text)
            if match:
                title, start, end = match.groups()
                st.session_state.pending_event = {"title": title.strip(), "start": start.strip(), "end": end.strip()}
                ai_text = ai_text.replace(match.group(0), "").strip()
            
            st.markdown(ai_text)
            
            clean_text = ai_text.replace("*", "").replace("#", "").replace("`", "").replace("_", "")
            tts = gTTS(text=clean_text, lang='ja')
            audio_fp = io.BytesIO()
            tts.write_to_fp(audio_fp)
            st.session_state.ai_voice_base64 = base64.b64encode(audio_fp.getvalue()).decode()
            st.session_state.just_generated_audio = True 
            
            st.session_state.chat_history.append({"role": "assistant", "avatar": "🤖", "content": ai_text})
            st.rerun()