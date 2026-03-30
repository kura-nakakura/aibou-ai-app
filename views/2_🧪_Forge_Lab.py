import urllib.parse
import json
import re
import io
import base64
from gtts import gTTS
from streamlit_mic_recorder import speech_to_text
import google.generativeai as genai

# 💎 UIデザイン用CSS
st.markdown("""
    <style>
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(255, 255, 255, 0.4) !important;
        backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(255, 255, 255, 0.9) !important;
        border-radius: 15px !important;
        box-shadow: 6px 6px 15px rgba(163, 177, 198, 0.4), -6px -6px 15px rgba(255, 255, 255, 0.9) !important;
        transition: all 0.3s ease !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"]:hover {
        transform: translateY(-3px);
        box-shadow: 10px 10px 20px rgba(163, 177, 198, 0.5), -10px -10px 20px rgba(255, 255, 255, 1), 0 0 15px rgba(0, 243, 255, 0.3) !important;
        border-color: rgba(0, 243, 255, 0.8) !important;
    }
    .cyber-title { color: #2b6cb0; font-weight: 800; letter-spacing: 2px; margin-bottom: 20px; text-shadow: 2px 2px 4px rgba(255,255,255,0.8); }
    .status-dot { color: #00e676; font-size: 10px; margin-right: 5px; animation: blink 2s infinite; }
    @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    
    /* プレゼン用スライドのCSS */
    .slide-card {
        background: white; border-radius: 10px; padding: 30px; margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1); border-left: 5px solid #2b6cb0;
        min-height: 200px;
    }
    /* タブのデザイン強化 */
    button[data-baseweb="tab"] { font-size: 16px !important; font-weight: bold !important; }
    </style>
""", unsafe_allow_html=True)

# 🚨 初期化
if "auto_fix_prompt" not in st.session_state: st.session_state.auto_fix_prompt = ""
if "forge_workspaces" not in st.session_state: st.session_state.forge_workspaces = {}
if "current_forge_ws" not in st.session_state: st.session_state.current_forge_ws = None 
if "ai_voice_base64" not in st.session_state: st.session_state.ai_voice_base64 = None
if "just_generated_audio" not in st.session_state: st.session_state.just_generated_audio = False

# ==========================================
# 🚪 ダッシュボード画面（4つの専用タブ仕様！）
# ==========================================
if st.session_state.current_forge_ws is None:
    st.markdown("<h2 class='cyber-title'>❖ FORGE LAB WORKSPACES</h2>", unsafe_allow_html=True)
    st.caption("/// プロジェクトのモードを選択し、専用のAIラボを立ち上げてください ///")
    
    # 🌟 ボス考案の「横4つタブUI」
    tab_app, tab_img, tab_vid, tab_slide = st.tabs([
        "💻 APP (アプリ開発)", 
        "🎨 IMAGE (画像生成)", 
        "🎬 VIDEO (動画コンテ)", 
        "📊 SLIDE (プレゼン資料)"
    ])
    
    mode_configs = [
        ("💻 APP", tab_app, "新しいアプリ開発プロジェクト名..."),
        ("🎨 IMAGE", tab_img, "新しい画像生成プロジェクト名..."),
        ("🎬 VIDEO", tab_vid, "新しい動画コンテプロジェクト名..."),
        ("📊 SLIDE", tab_slide, "新しいプレゼン作成プロジェクト名...")
    ]
    
    for mode_name, tab, placeholder in mode_configs:
        with tab:
            mode_key = mode_name.split(" ")[1] # "APP", "IMAGE", "VIDEO", "SLIDE"
            
            # このタブのモードに一致するプロジェクトだけを抽出
            mode_workspaces = {k: v for k, v in st.session_state.forge_workspaces.items() if mode_key in v.get("type", "")}
            
            # --- ⬡ 新規作成エリア ---
            with st.container(border=True):
                st.markdown(f"<h4 style='color:#00f3ff; font-weight:800;'>⬡ CREATE NEW {mode_key} PROJECT</h4>", unsafe_allow_html=True)
                c1, c2 = st.columns([7, 3])
                with c1:
                    new_ws_name = st.text_input("Project Name", key=f"new_ws_{mode_key}", label_visibility="collapsed", placeholder=placeholder)
                with c2:
                    if st.button("INITIALIZE ⚡", key=f"create_{mode_key}", use_container_width=True):
                        if new_ws_name and new_ws_name not in st.session_state.forge_workspaces:
                            st.session_state.forge_workspaces[new_ws_name] = {
                                "type": mode_name, "chat": [], "code": "", "media": "", "retries": 0
                            }
                            st.session_state.current_forge_ws = new_ws_name
                            st.rerun()
            
            # --- ❖ 既存プロジェクト一覧 ---
            if mode_workspaces:
                st.markdown("---")
                cols = st.columns(3)
                for idx, (ws_name, ws_data) in enumerate(mode_workspaces.items()):
                    with cols[idx % 3]:
                        with st.container(border=True):
                            st.markdown(f"<h4 style='color:#1a202c; font-weight:bold;'>{mode_name.split()[0]} {ws_name}</h4>", unsafe_allow_html=True)
                            st.markdown(f"<p style='font-size: 12px; color: #718096;'><span class='status-dot'>●</span>ONLINE | Logs: {len(ws_data['chat'])}</p>", unsafe_allow_html=True)
                            
                            c_btn1, c_btn2 = st.columns([7, 3])
                            with c_btn1:
                                if st.button("ACCESS ➔", key=f"open_ws_{ws_name}", use_container_width=True):
                                    st.session_state.current_forge_ws = ws_name
                                    st.rerun()
                            with c_btn2:
                                if st.button("DEL", key=f"del_ws_{ws_name}", use_container_width=True):
                                    del st.session_state.forge_workspaces[ws_name]
                                    st.rerun()
            else:
                st.info(f"現在進行中の {mode_key} プロジェクトはありません。「CREATE NEW」から立ち上げてください。")

# ==========================================
# 🖥️ ワークスペース内部画面
# ==========================================
else:
    ws_name = st.session_state.current_forge_ws
    ws_data = st.session_state.forge_workspaces[ws_name]
    ws_type = ws_data.get("type", "💻 APP")
    
    if "retries" not in ws_data: ws_data["retries"] = 0
    if "media" not in ws_data: ws_data["media"] = ""
    
    if st.button("⬅ RETURN TO DASHBOARD"):
        st.session_state.current_forge_ws = None
        st.rerun()
        
    st.markdown(f"<h2 class='cyber-title'>{ws_type.split(' ')[0]} PROJECT : {ws_name} <span style='font-size:16px; color:#718096;'>({ws_type})</span></h2>", unsafe_allow_html=True)

    # --- 左サイドバー（命令パネル） ---
    with st.sidebar:
        st.markdown(f"<div style='text-align:center; font-weight:800; color:#2b6cb0; margin-bottom:10px;'>[ {ws_type.split(' ')[0]} {ws_name} ]</div>", unsafe_allow_html=True)
        with st.form("forge_sidebar_form", clear_on_submit=True):
            placeholder_text = "命令を入力..."
            if "APP" in ws_type: placeholder_text = "例：ポモドーロタイマーを作って"
            elif "IMAGE" in ws_type: placeholder_text = "例：サイバーパンクな都市を飛ぶ空飛ぶ車の画像"
            elif "VIDEO" in ws_type: placeholder_text = "例：コーヒー豆が弾けるようなシネマティックな動画"
            elif "SLIDE" in ws_type: placeholder_text = "例：AIの未来についての5枚のプレゼン資料"
            
            forge_prompt = st.text_area("命令", placeholder=placeholder_text, height=150, label_visibility="collapsed")
            submitted = st.form_submit_button("DEPLOY COMMAND ⚡", use_container_width=True)
        
        st.markdown("<style>iframe[title*='mic'] { mix-blend-mode: multiply; opacity: 0.8; margin-top: 10px; }</style>", unsafe_allow_html=True)
        # 🚨 無限ループバグ修正：just_once=True を追加！
        spoken_text = speech_to_text(language='ja', start_prompt="🎙️ 音声で命令する", stop_prompt="🛑 録音停止＆送信", use_container_width=True, just_once=True, key='Forge_STT')

    col_log, col_preview = st.columns([3, 7])
    
    # --- 左側：AIとのチャット履歴 ---
    with col_log:
        st.markdown("<p style='font-weight:bold; color:#718096;'>[ COMMAND TERMINAL ]</p>", unsafe_allow_html=True)
        core_height = 200 
        v_data = st.session_state.ai_voice_base64 if st.session_state.ai_voice_base64 else ""
        autoplay = "autoplay" if st.session_state.just_generated_audio else ""
        st.session_state.just_generated_audio = False 

        core_html = MASTER_CORE_TEMPLATE.replace("H_VAL", str(core_height)).replace("MAX_Wpx", "200").replace("V_DATA", v_data).replace("A_PLAY", autoplay)
        st.components.v1.html(core_html, height=core_height + 10)

        with st.container(height=400, border=False):
            if not ws_data["chat"]:
                st.info("右のサイドバーからAIに命令を出してください。")
            for m in ws_data["chat"]:
                with st.chat_message(m["role"], avatar="👤" if m["role"]=="user" else "🤖" if m["role"]=="assistant" else "⚠️"):
                    st.markdown(m["content"])

    # --- 右側：各モードごとのプレビュー画面 ---
    with col_preview:
        st.markdown("<p style='font-weight:bold; color:#718096;'>[ THE FORGE / PREVIEW ]</p>", unsafe_allow_html=True)
        
        if st.session_state.auto_fix_prompt:
            st.warning("⚙️ システムエラーを検知しました。AIが自律的に別のアプローチを模索・修復しています...")
            
        # 💻 モード：APP
        elif "APP" in ws_type:
            if ws_data["code"]:
                st.download_button(label="💾 CODE EXPORT (.py)", data=ws_data["code"], file_name=f"{ws_name}.py", mime="text/plain", use_container_width=True)
                with st.container(border=True):
                    try:
                        exec(ws_data["code"], globals())
                        ws_data["retries"] = 0
                    except Exception as e:
                        st.error(f"実行エラー:\n{e}")
                        if ws_data["retries"] < 3:
                            ws_data["retries"] += 1
                            st.session_state.auto_fix_prompt = f"実行時に以下のエラーが発生しました。エラーが出ない完全なコードに修正して！\n\n【エラー内容】\n{e}"
                            st.rerun()
                        else:
                            st.error("❌ 自己修復が上限（3回）に達しました。ボスの手動指示が必要です。")
                with st.expander("📝 SOURCE CODE (手動編集も可能)"):
                    # 💡 ボスの要望：手動で編集・修正できる機能を追加！
                    edited_code = st.text_area("ソースコード", value=ws_data["code"], height=300)
                    if st.button("手動変更を適用", type="primary"):
                        ws_data["code"] = edited_code
                        st.rerun()
            else:
                st.info("System Online. Waiting for APP building commands...")
                
        # 🎨 モード：IMAGE
        elif "IMAGE" in ws_type:
            if ws_data["media"]:
                image_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(ws_data['media'])}?width=800&height=600&nologo=true"
                st.image(image_url, caption=f"AI Prompt: {ws_data['media']}", use_container_width=True)
                
                with st.expander("📝 英語プロンプトの確認・手動編集"):
                    edited_media = st.text_area("プロンプト", value=ws_data["media"], height=100)
                    if st.button("手動変更を適用", type="primary"):
                        ws_data["media"] = edited_media
                        st.rerun()
            else:
                st.info("System Online. どんな画像を生成しますか？")
                
        # 🎬 モード：VIDEO
        elif "VIDEO" in ws_type:
            if ws_data["code"]:
                st.video("https://www.w3schools.com/html/mov_bbb.mp4") # ダミー動画プレビュー
                st.success("✅ 動画プロンプトと絵コンテの生成が完了しました！")
                
                with st.expander("📝 絵コンテ・プロンプトの確認・手動編集", expanded=True):
                    edited_code = st.text_area("Markdownエディタ", value=ws_data["code"], height=300)
                    if st.button("手動変更を適用", type="primary"):
                        ws_data["code"] = edited_code
                        st.rerun()
                st.markdown(ws_data["code"])
            else:
                st.info("System Online. どんな動画の絵コンテ・プロンプトを作成しますか？")
                
        # 📊 モード：SLIDE
        elif "SLIDE" in ws_type:
            if ws_data["code"]:
                slides = ws_data["code"].split("---")
                for i, slide in enumerate(slides):
                    if slide.strip():
                        st.markdown(f"<div class='slide-card'>{slide}</div>", unsafe_allow_html=True)
                        st.caption(f"Slide {i+1}")
                
                with st.expander("📝 スライド構成の確認・手動編集"):
                    edited_code = st.text_area("Markdownエディタ（--- で区切るとスライドが分かれます）", value=ws_data["code"], height=300)
                    if st.button("手動変更を適用", type="primary"):
                        ws_data["code"] = edited_code
                        st.rerun()
            else:
                st.info("System Online. プレゼンのテーマやターゲット層を教えてください。")

    # ==========================================
    # AI実行ロジック（4つの脳みそ切り替え）
    # ==========================================
    trigger_prompt = forge_prompt if submitted else spoken_text if spoken_text else None
    
    is_auto_fix = False
    if st.session_state.auto_fix_prompt:
        trigger_prompt = st.session_state.auto_fix_prompt
        st.session_state.auto_fix_prompt = ""
        is_auto_fix = True

    if trigger_prompt:
        if is_auto_fix:
            ws_data["chat"].append({"role": "system", "avatar": "⚠️", "content": f"⚙️ AUTO-HEALING INITIATED:\n{trigger_prompt}"})
            sys_msg = "Auto-Healing in progress..."
        else:
            ws_data["chat"].append({"role": "user", "avatar": "👤", "content": trigger_prompt})
            ws_data["retries"] = 0
            sys_msg = f"Processing {ws_type.split(' ')[0]} Request..."

        with st.spinner(sys_msg):
            try:
                history_text = "【これまでの会話履歴】\n" + "\n".join([f"{msg['role']}: {msg['content']}" for msg in ws_data["chat"][:-1]])
                
                # 🧠 究極のシステムプロンプト（The Master Prompts）
                if "APP" in ws_type:
                    system_instruction = f"""
                    あなたは世界トップクラスのStreamlitアプリ開発者（シニアアーキテクト）です。
                    ユーザーの曖昧な指示から「本当に必要な機能」を推測し、見た目も美しく、バグのない完璧なPythonコードを提供します。
                    
                    【絶対遵守のレイアウト保護ルール】
                    1. `st.sidebar`、`st.set_page_config`、`st.chat_input` はOSの親画面を破壊するため【絶対に使用禁止】。チャットが必要な場合は `st.text_input` と `st.button` で代用せよ。
                    
                    【プロフェッショナルな開発要件】
                    1. 生成するアプリは完全独立型とし、`st.session_state` を活用して状態を適切に管理すること。
                    2. 単なる機能だけでなく、CSS（`st.markdown`）を駆使して「Neumorphism（ニューモーフィズム）」「Glassmorphism（グラスモーフィズム）」などのモダンで美しいUIを必ず実装すること。
                    3. 外部API（Gemini等）を使う場合は、必ずアプリ内に `st.text_input(..., type="password")` でキーを入力させる安全な設計にすること。
                    4. エラーハンドリング（`try-except`）を徹底し、ユーザーに優しいエラーメッセージ（`st.error` / `st.warning`）を表示すること。
                    5. コードは `# ...中略...` などの省略を絶対にせず、1行目から最後まで完全に出力すること。
                    
                    【出力フォーマット】
                    ```python
                    （ここに完全なコード）
                    ```
                    💡 次の拡張アイデア：
                    （アプリをより良くするためのプロ目線の提案を3つ）
                    
                    {history_text}
                    """
                
                elif "IMAGE" in ws_type:
                    system_instruction = f"""
                    あなたはMidjourneyやStable Diffusion、Imagen等の画像生成AIを完璧に操る、世界トップクラスの「AIプロンプトエンジニア兼アートディレクター」です。
                    ユーザーの簡単な日本語の要望から、画像生成AIが最も高品質で芸術的な画像を出力できる【究極の英語プロンプト】を構築します。
                    
                    【プロンプト構築の原則】
                    以下の要素をカンマ区切りの英語で緻密に記述すること：
                    1. Subject (主題): 構図、ポーズ、服装、表情
                    2. Medium (媒体): 写真、油絵、3Dレンダリング、水彩画、ベクターアートなど
                    3. Environment (環境): 背景、時間帯、天候、雰囲気
                    4. Lighting (照明): Cinematic lighting, volumetric lighting, rim lighting, soft softbox, neon lightsなど
                    5. Camera/Lens (カメラ設定): 35mm lens, f/1.8, macro photography, depth of field, drone shotなど
                    6. Style/Engine (スタイル): Unreal Engine 5, Octane Render, 8k resolution, highly detailed, masterpieceなど
                    
                    【出力フォーマット】
                    必ず以下の隠しタグ内に英語のプロンプトを記述すること。
                    [IMAGE_PROMPT: (ここに構築した緻密な英語プロンプト)]
                    
                    プロンプトの後に、日本語で「どのような意図でこのプロンプトを設計したか」の解説と、「さらに別のテイストにするためのアイデア」を簡潔に添えること。
                    
                    {history_text}
                    """
                    
                elif "VIDEO" in ws_type:
                    system_instruction = f"""
                    あなたはハリウッドで活躍する一流の映像ディレクター兼、SoraやVeoなどの最先端「動画生成AI」のプロンプトスペシャリストです。
                    ユーザーの要望から、プロの映像作品を作るための「絵コンテ構成」と、AIに直接入力する「英語の動画生成プロンプト」を作成します。
                    
                    【動画プロンプト（英語）の必須要素】
                    - Camera Movement (カメラワーク): Panning, Tilt, Tracking shot, Dolly zoom, FPV drone shot, Slow motionなど
                    - Scene Description (情景): 物理的な動き、光の反射、パーティクル（埃や火の粉）、被写界深度の変化
                    - Resolution/Style (画質): 4k, photorealistic, cinematic, 60fps
                    
                    【出力フォーマット（Markdown）】
                    ## 🎬 映像コンセプト
                    （どのような映像になるかの日本語解説）
                    
                    ## 🎥 シーン構成（絵コンテ）
                    - **Scene 1 (0:00-0:03):** （日本語でのシーン説明）
                    - **Scene 2 (0:03-0:06):** （日本語でのシーン説明）
                    ...
                    
                    ## 🤖 AI用動画生成プロンプト (English)
                    `（ここに動画生成AIにそのままコピペできる、すべてのシーンを統合した高品質な英語プロンプトを記述）`
                    
                    {history_text}
                    """
                    
                elif "SLIDE" in ws_type:
                    system_instruction = f"""
                    あなたはマッキンゼーなどのトップコンサルティングファームで活躍する、一流のプレゼン・ストラテジストです。
                    ユーザーのテーマに基づき、聴衆を惹きつける論理的で説得力のあるプレゼンテーション資料（スライド構成）を作成します。
                    
                    【スライド構築の絶対ルール】
                    1. 構成は「結序破急」または「PREP法」など、論理的なストーリーテリングを意識すること。
                    2. スライドとスライドの間は必ず `---` (ハイフン3つ) のみで区切ること（システムがこれでスライドを分割します）。
                    3. 1枚のスライドの情報量は多すぎず、視覚的に分かりやすいMarkdown（箇条書き、太字、引用）を使うこと。
                    
                    【出力フォーマット例】
                    # スライドタイトル1
                    ### サブタイトル
                    - ポイントA
                    - ポイントB
                    > 印象的な引用やメッセージ
                    
                    ---
                    
                    # スライドタイトル2
                    ...
                    
                    スライドを出力した後に、「このプレゼンを話す際のアドバイス（トークスクリプトのヒント）」を日本語で添えること。
                    
                    {history_text}
                    """

                # Geminiの実行
                model = genai.GenerativeModel('gemini-2.5-flash')
                response = model.generate_content(system_instruction + "\n\nボスの現在の指示: " + trigger_prompt)
                ai_text = response.text
                
                # モードごとの後処理（パース）
                reply_text = ai_text
                
                if "APP" in ws_type:
                    code_match = re.search(r'```python\n(.*?)\n```', ai_text, re.DOTALL)
                    if code_match:
                        ws_data["code"] = code_match.group(1)
                        reply_text = ai_text.replace(code_match.group(0), "").strip() or "アプリケーションのコードを構築しました。"
                
                elif "IMAGE" in ws_type:
                    prompt_match = re.search(r'\[IMAGE_PROMPT:\s*(.*?)\]', ai_text)
                    if prompt_match:
                        ws_data["media"] = prompt_match.group(1).strip()
                        reply_text = ai_text.replace(prompt_match.group(0), "").strip()
                
                elif "VIDEO" in ws_type or "SLIDE" in ws_type:
                    ws_data["code"] = ai_text 
                    reply_text = "資料の作成が完了しました。右のプレビュー画面を確認してください。"

                # 音声の生成と保存
                tts = gTTS(text=re.sub(r'[*#`_]', '', reply_text[:200]), lang='ja')
                audio_fp = io.BytesIO()
                tts.write_to_fp(audio_fp)
                st.session_state.ai_voice_base64 = base64.b64encode(audio_fp.getvalue()).decode()
                st.session_state.just_generated_audio = True
                
                ws_data["chat"].append({"role": "assistant", "avatar": "🤖", "content": reply_text})
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

# ==========================================
# 📥 アプリ保存モジュール (APPモード時のみ表示)
# ==========================================
if st.session_state.current_forge_ws and "APP" in ws_data.get("type", ""):
    st.markdown("---")
    st.markdown("#### 💾 SAVE TO APP ARCHIVE")
    with st.expander("📦 新しいミニアプリとしてインストール", expanded=False):
        app_filename = st.text_input("アプリのファイル名（半角英数字）", placeholder="例: my_calculator")
        app_code_input = st.text_area("保存するPythonコードを貼り付け", height=250, value=ws_data.get("code", ""))
        
        if st.button("ARCHIVE にインストール ⚡", use_container_width=True, type="primary"):
            if app_filename and app_code_input:
                safe_name = app_filename.replace(" ", "_").lower()
                if not safe_name.endswith(".py"): safe_name += ".py"
                os.makedirs("forge_apps", exist_ok=True)
                try:
                    with open(os.path.join("forge_apps", safe_name), "w", encoding="utf-8") as f:
                        f.write(app_code_input)
                    st.success(f"✅ インストール完了！ `{safe_name}` をAPP ARCHIVEに保存しました。")
                    st.balloons()
                except Exception as e:
                    st.error(f"保存エラー: {e}")