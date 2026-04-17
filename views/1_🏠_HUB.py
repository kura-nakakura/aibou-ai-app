if "hub_view_mode" not in st.session_state: st.session_state.hub_view_mode = "CORE"

# 💎 THE ORBITAL RINGS (Arc Reactor Theme)
st.markdown("""
    <style>
    /* 1. 全体を漆黒の宇宙空間（ダークテーマ）に強制上書き */
    [data-testid="stAppViewContainer"], .stApp { 
        background-color: #050a15 !important; 
        background-image: radial-gradient(circle at 50% 50%, rgba(0, 243, 255, 0.05), #050a15 60%) !important;
        overflow-y: hidden !important; 
    }
    
    .hub-title { 
        text-align: center; color: #00f3ff; font-weight: 900;
        letter-spacing: 15px; margin-bottom: 30px; font-family: 'Share Tech Mono', monospace;
        text-shadow: 0 0 20px rgba(0, 243, 255, 0.4);
    }

    /* 2. 透明なサイバーボタン */
    div.stButton > button {
        background: rgba(10, 20, 35, 0.6) !important; 
        border: 1px solid rgba(0, 243, 255, 0.2) !important; 
        border-radius: 8px !important; 
        color: #a0aec0 !important; font-weight: 700 !important; letter-spacing: 2px !important;
        transition: all 0.3s ease !important; padding: 10px !important; font-size: 13px !important;
    }
    div.stButton > button:hover {
        background: rgba(0, 243, 255, 0.1) !important;
        border-color: #00f3ff !important;
        color: #ffffff !important;
        box-shadow: 0 0 15px rgba(0, 243, 255, 0.4), inset 0 0 10px rgba(0, 243, 255, 0.2) !important;
        transform: translateY(-2px);
    }
    
    .view-toggle button {
        border-radius: 20px !important; padding: 5px 15px !important; font-size: 11px !important;
        background: transparent !important; color: #00f3ff !important;
        border: 1px solid #00f3ff !important; width: auto !important; display: inline-block;
    }

    /* 🌟 3. 衛星軌道パネル（The Orbital Rings）のCSSハック */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(5, 12, 25, 0.7) !important;
        backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(0, 243, 255, 0.2) !important;
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) !important;
        padding: 15px !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: #00f3ff !important;
        box-shadow: 0 0 25px rgba(0, 243, 255, 0.3), inset 0 0 10px rgba(0, 243, 255, 0.1) !important;
        transform: scale(1.03);
    }
    
    /* 左側のパネル（FACTORY, AGENCY）: 右側を大きくカーブさせてコアを包む */
    [data-testid="column"]:nth-of-type(1) [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 15px 70px 70px 15px !important;
        border-right: 3px solid rgba(0, 243, 255, 0.5) !important;
    }
    /* 右側のパネル（BRAIN, CORE）: 左側を大きくカーブさせてコアを包む */
    [data-testid="column"]:nth-of-type(3) [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 70px 15px 15px 70px !important;
        border-left: 3px solid rgba(0, 243, 255, 0.5) !important;
    }
    
    .panel-header {
        font-weight: 900; color: #ffffff; letter-spacing: 4px; font-size: 14px; 
        margin-bottom: 15px; text-shadow: 0 0 10px rgba(255,255,255,0.5);
    }
    .panel-header-left { text-align: left; }
    .panel-header-right { text-align: right; }
    </style>
""", unsafe_allow_html=True)

st.markdown("<h2 class='hub-title'>⬡ THE FORGE OS</h2>", unsafe_allow_html=True)

if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "ai_voice_base64" not in st.session_state: st.session_state.ai_voice_base64 = None
if "just_generated_audio" not in st.session_state: st.session_state.just_generated_audio = False
if "pending_event" not in st.session_state: st.session_state.pending_event = None 

v_data = st.session_state.ai_voice_base64 if st.session_state.ai_voice_base64 else ""
autoplay_attr = "autoplay" if st.session_state.just_generated_audio else ""
st.session_state.just_generated_audio = False 

# 👑 カラムを [1 : 1.5 : 1] のワイドグリッドに配置（中央コアを大きく）
core_height = 320
col_left, col_core, col_right = st.columns([1, 1.5, 1], gap="medium")

with col_left:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.session_state.hub_view_mode == "HUB":
        # パネル1: FACTORY
        with st.container(border=True):
            st.markdown("<div class='panel-header panel-header-left'>❖ FACTORY</div>", unsafe_allow_html=True)
            if st.button("＞ Forge Lab", use_container_width=True): st.session_state.current_mode = "Forge Lab"; st.rerun()
            if st.button("＞ App Archive", use_container_width=True): st.session_state.current_mode = "App Archive"; st.rerun()
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # パネル2: AGENCY
        with st.container(border=True):
            st.markdown("<div class='panel-header panel-header-left'>❖ AGENCY</div>", unsafe_allow_html=True)
            if st.button("＞ Active Tasks", use_container_width=True): st.session_state.current_mode = "Active Tasks"; st.rerun()
            if st.button("＞ Task History", use_container_width=True): st.session_state.current_mode = "Task History"; st.rerun()

with col_core:
    st.markdown("<div class='view-toggle' style='text-align:center;'>", unsafe_allow_html=True)
    toggle_label = "◈ VIEW: CORE" if st.session_state.hub_view_mode == "HUB" else "◈ VIEW: HUB"
    if st.button(toggle_label, key="toggle_view"):
        st.session_state.hub_view_mode = "CORE" if st.session_state.hub_view_mode == "HUB" else "HUB"
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # コアをド真ん中に鎮座させる
    core_html = MASTER_CORE_TEMPLATE.replace("H_VAL", str(core_height)).replace("MAX_Wpx", "300").replace("V_DATA", v_data).replace("A_PLAY", autoplay_attr)
    st.components.v1.html(core_html, height=core_height + 20)
    
    if st.session_state.hub_view_mode == "CORE":
        with st.container(height=280, border=False):
            for m in st.session_state.chat_history:
                with st.chat_message(m["role"], avatar=m["avatar"]):
                    st.markdown(m["content"])

with col_right:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.session_state.hub_view_mode == "HUB":
        # パネル3: BRAIN
        with st.container(border=True):
            st.markdown("<div class='panel-header panel-header-right'>BRAIN ❖</div>", unsafe_allow_html=True)
            if st.button("Data Vault ＜", use_container_width=True): st.session_state.current_mode = "Document Vault"; st.rerun()
            # 🌟 新規追加: Miro Boardへの導線
            if st.button("Miro Board ＜", use_container_width=True): st.session_state.current_mode = "Dashboard"; st.rerun()
            
        st.markdown("<br>", unsafe_allow_html=True)

        # パネル4: CORE
        with st.container(border=True):
            st.markdown("<div class='panel-header panel-header-right'>CORE ❖</div>", unsafe_allow_html=True)
            if st.button("Evolution ＜", use_container_width=True): st.session_state.current_mode = "Core Upgrade"; st.rerun()
            if st.button("Settings ＜", use_container_width=True): st.session_state.current_mode = "Settings"; st.rerun()

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
    iframe[title*='mic'] { mix-blend-mode: screen !important; opacity: 0.5; transition: all 0.3s ease-in-out; } 
    iframe[title*='mic']:hover { opacity: 1.0; filter: drop-shadow(0px 5px 15px rgba(0, 243, 255, 0.8)); transform: translateY(-2px); } 
    [data-testid='stVerticalBlock'] > div:has(iframe[title*='mic']) { margin-bottom: -25px !important; position: relative; z-index: 50; }
    </style>
""", unsafe_allow_html=True)

col1, col2, col3 = st.columns([4, 4, 4]) 
with col2:
    # 音声入力マイクをコアの直下に配置
    spoken_text = speech_to_text(language='ja', start_prompt="◈ PUSH TO TALK", stop_prompt="⬡ TAP TO SEND", use_container_width=True, just_once=True, key='STT')

if not st.session_state.pending_event:
    if spoken_text:
        st.session_state.chat_history.append({"role": "user", "avatar": "👤", "content": spoken_text})
        st.rerun()

    if prompt := st.chat_input("/// コマンドを入力してください、ボス", key="console_input"):
        st.session_state.chat_history.append({"role": "user", "avatar": "👤", "content": prompt})
        st.rerun()

if st.session_state.chat_history and st.session_state.chat_history[-1]["role"] == "user" and not st.session_state.pending_event:
    last_prompt = st.session_state.chat_history[-1]["content"]
    with st.chat_message("assistant", avatar="◈"):
        with st.spinner(" "):
            gemini_key = st.session_state.global_api_keys.get("gemini", "")
            if gemini_key:
                genai.configure(api_key=gemini_key)
            
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            system_instruction = f"""
            あなたは総合システム「THE FORGE OS」全体を統括するマスターAI（J.A.R.V.I.S.型）です。
            ボスの右腕としてあらゆる相談、技術的な質問、日常の会話に高度な知性と端的な言葉で対応してください。
            絵文字は一切使用せず、システムライクで冷静なトーンを維持してください。

            【現在の状況】
            現在時刻: {now_str}

            【カレンダー登録時のシステムコマンド（絶対ルール）】
            会話の流れでユーザーから「〇〇の予定を追加して」「アポを入れといて」と明確に頼まれた場合【のみ】、返答の最後に以下の隠しコマンドを出力してください。普段の会話では絶対に出力しないでください。
            形式: [CALENDAR_ADD: 予定のタイトル | YYYY-MM-DDTHH:MM:00 | YYYY-MM-DDTHH:MM:00]
            """
            
            # 🚨 制限回避のため gemini-1.5-flash を指定
            model = genai.GenerativeModel(model_name='gemini-1.5-flash')
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
            
            st.session_state.chat_history.append({"role": "assistant", "avatar": "◈", "content": ai_text})
            st.rerun()
