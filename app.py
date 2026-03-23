import streamlit as st
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import json
import re
from gtts import gTTS
import io
import base64
import os
from streamlit_mic_recorder import speech_to_text

st.set_page_config(page_title="相棒AI ダッシュボード", page_icon="🤖", layout="wide")

# ==========================================
# 🔐 1. ログインシステム
# ==========================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 相棒AI 起動シークエンス")
    password = st.text_input("Password", type="password")
    if st.button("システム起動 🚀"):
        if password == st.secrets.get("APP_PASSWORD", "boss"): 
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("パスワードが違います。")
    st.stop()

# ==========================================
# 🧭 2. ナビゲーション（開閉式スマートメニュー）
# ==========================================
st.sidebar.title("A.I. CORE")

with st.sidebar.expander("SELECT MODE", expanded=False):
    page = st.radio("mode_select", 
        ["AI Console", "Forge Lab", "Active Tasks", "Task History", "Dashboard", "Secure Vault"],
        label_visibility="collapsed"
    )

def get_base64_video(file_path):
    if not os.path.exists(file_path): return None
    try:
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception: return None

video_base64 = get_base64_video("bg.mp4")

if video_base64:
    st.markdown("""
        <style>
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] { background-color: #e0e5ec !important; background-image: none !important; }
        [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child { background-color: #e0e5ec !important; border-right: none !important; box-shadow: none !important; }
        .stApp, p, span, div { color: #2d3748 !important; }
        [data-testid="stBottom"], [data-testid="stBottom"] > div { background: transparent !important; }
        [data-testid="stSidebar"] h1, [data-testid="stSidebar"] label { color: #1a202c !important; text-shadow: none !important; font-weight: 800 !important; letter-spacing: 2px !important; }
        [data-testid="stSidebar"] [data-testid="stExpander"] { border: none !important; background: transparent !important; box-shadow: none !important; }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary p { color: #1a202c !important; font-weight: 800 !important; letter-spacing: 2px !important; font-size: 14px !important; }
        
        div[role="radiogroup"] { gap: 15px; padding: 10px; }
        div[role="radiogroup"] > label { background: rgba(255, 255, 255, 0.6) !important; backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.8) !important; border-radius: 15px !important; padding: 10px 20px !important; box-shadow: 6px 6px 12px rgba(163, 177, 198, 0.5), -6px -6px 12px rgba(255, 255, 255, 0.9) !important; transition: all 0.2s ease-in-out; cursor: pointer; }
        div[role="radiogroup"] > label p { color: #1a202c !important; font-weight: bold !important; }
        div[role="radiogroup"] > label[data-checked="true"] { box-shadow: inset 4px 4px 8px rgba(163, 177, 198, 0.6), inset -4px -4px 8px rgba(255, 255, 255, 0.9) !important; border: 1px solid #00f3ff !important; }
        div[role="radiogroup"] > label[data-checked="true"] p { color: #1a202c !important; text-shadow: none !important; }
        div[role="radiogroup"] > label[data-checked="true"] span[data-baseweb="radio"] > div { background-color: #00f3ff !important; }
        div[role="radiogroup"] > label[data-checked="true"] span[data-baseweb="radio"] > div > div { background-color: #00f3ff !important; }
        
        [data-testid="stChatInput"] { background: rgba(255, 255, 255, 0.5) !important; backdrop-filter: blur(15px); border: 1px solid rgba(255, 255, 255, 0.9) !important; border-radius: 20px !important; box-shadow: 10px 10px 20px rgba(163, 177, 198, 0.6), -10px -10px 20px rgba(255, 255, 255, 1), inset 2px 2px 5px rgba(255, 255, 255, 0.6) !important; padding: 5px !important; transition: all 0.2s ease-in-out; }
        [data-testid="stChatInput"] textarea { color: #2b6cb0 !important; font-weight: bold; font-family: 'Share Tech Mono', sans-serif; }
        [data-testid="stChatInput"]:focus-within { border-color: #00f3ff !important; box-shadow: inset 2px 2px 5px rgba(255, 255, 255, 0.6), 0 0 15px rgba(0, 243, 255, 0.5) !important; outline: none !important; }
        [data-testid="stChatMessage"] { background: rgba(255, 255, 255, 0.4) !important; backdrop-filter: blur(8px); border: 1px solid rgba(255, 255, 255, 0.8) !important; border-radius: 15px !important; box-shadow: 5px 5px 10px rgba(163, 177, 198, 0.3), -5px -5px 10px rgba(255, 255, 255, 0.8); }
        [data-testid="stChatMessage"] p, [data-testid="stChatMessage"] div { color: #1a202c !important; }
        .stChatFloatingInputContainer { box-shadow: none !important; }
        </style>
    """, unsafe_allow_html=True)

if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.rerun()

# ==========================================
# 🧠 3. バックグラウンド接続
# ==========================================
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

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


# 🚨【超重要】AI Console と Forge Lab のコアを完全に共通化する設計図
MASTER_CORE_TEMPLATE = """
<style>
    /* 🚨 パネルを中央ではなく、コアの右横に表示するように変更 */
    #core-settings { 
        display: none; position: absolute; 
        left: calc(50% + 140px); /* コアの中心から右にズラす */
        top: 50%; transform: translateY(-50%); 
        background: rgba(255, 255, 255, 0.7); backdrop-filter: blur(25px); border: 2px solid #00f3ff; 
        border-radius: 20px; padding: 20px; box-shadow: 0px 0px 50px rgba(0, 243, 255, 0.5); 
        width: 320px; max-height: 90%; overflow-y: auto; z-index: 99999; 
        font-family: 'Segoe UI', sans-serif; color: #2d3748; font-size: 12px; 
    }
    /* モバイルなどの狭い画面では中央にフォールバック */
    @media (max-width: 768px) {
        #core-settings {
            left: 50%; transform: translate(-50%, -50%);
        }
    }
    
    #core-settings input[type=range] { accent-color: #00f3ff; cursor: pointer; width: 100%; }
    #core-settings select { background: rgba(255,255,255,0.5); border: 1px solid #cbd5e0; border-radius: 8px; padding: 5px; outline: none; width: 100%; cursor: pointer; }
    #core-settings input[type=color] { border: none; background: transparent; cursor: pointer; width: 30px; height: 30px; padding: 0; }
    #core-settings button:hover { filter: brightness(1.2); }
</style>

<div id="core-wrapper" style="position:relative; width:100%; height:H_VALpx; display:flex; justify-content:center; align-items:center;">
    <div id="core-container" style="cursor:pointer; display:flex; flex-direction:column; align-items:center; z-index:10; width:100%; transition: transform 0.3s ease;">
        <canvas id="visualizer" width="400" height="400" style="filter:drop-shadow(0 5px 15px rgba(0, 150, 255, 0.4));"></canvas>
        <div id="status-info" style="margin-top:-20px; font-size:12px; letter-spacing:6px; color:#3182ce; font-family:monospace; font-weight:bold;">SYSTEM ONLINE</div>
    </div>

    <div id="core-settings">
        <h4 style="margin:0 0 15px 0; color:#1a202c; text-align:center; font-weight:800; letter-spacing:2px;">A.I. SETTINGS</h4>
        <div style="margin-bottom: 12px;"><label style="font-weight:bold; display:block; margin-bottom:2px;">Voice Speed: <span id="val-speed">1.5</span>x</label><input type="range" id="ctrl-speed" min="0.5" max="2.0" step="0.1" value="1.5"></div>
        <div style="margin-bottom: 12px;"><label style="font-weight:bold; display:block; margin-bottom:2px;">Volume: <span id="val-vol">100</span>%</label><input type="range" id="ctrl-vol" min="0" max="1" step="0.05" value="1"></div>
        <label style="display:block; margin-bottom:12px; font-weight:bold; cursor:pointer;"><input type="checkbox" id="ctrl-filter"> Sci-Fi Voice Filter</label>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 8px;"><label style="font-weight:bold;">Inner Core Color:</label><input type="color" id="ctrl-inner-color"></div>
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 12px;"><label style="font-weight:bold;">Outer Ring Color:</label><input type="color" id="ctrl-outer-color"></div>
        <div style="margin-bottom: 12px;"><label style="font-weight:bold; display:block; margin-bottom:2px;">Pulse Mode:</label><select id="ctrl-pulse"><option value="1">Relax</option><option value="2">Active</option><option value="4">Overdrive</option></select></div>
        <label style="display:block; margin-bottom:15px; font-weight:bold; cursor:pointer;"><input type="checkbox" id="ctrl-particles"> Hologram Particles</label>
        
        <div style="border-top: 1px solid rgba(0,0,0,0.1); padding-top: 10px; margin-bottom: 15px;">
            <label style="display:block; font-weight:bold; color:#00f3ff; cursor:pointer; text-shadow: 0 0 5px rgba(0,243,255,0.3);">
                <input type="checkbox" id="ctrl-mic"> 🎙️ Enable Voice Command
            </label>
        </div>
        
        <button id="ctrl-zen" style="width:100%; padding:8px; background:#1a202c; color:white; border-radius:10px; border:none; cursor:pointer; font-weight:bold; margin-bottom:8px;">Activate Zen Protocol</button>
        <button id="ctrl-reset" style="width:100%; padding:8px; background:transparent; color:#e53e3e; border:1px solid #e53e3e; border-radius:10px; cursor:pointer; font-weight:bold;">Reset to Default</button>
        <div style="text-align:center; margin-top:10px;"><a href="#" id="close-settings" style="color:#2b6cb0; text-decoration:none; font-weight:bold;">[ Close Panel ]</a></div>
    </div>
</div>

<audio id="ai-voice" A_PLAY><source src="data:audio/mp3;base64,V_DATA" type="audio/mp3"></audio>

<script>
    const coreContainer = document.getElementById("core-container");
    const settingsPanel = document.getElementById("core-settings");
    const closeBtn = document.getElementById("close-settings");
    const audio = document.getElementById("ai-voice");
    const canvas = document.getElementById("visualizer");
    const ctx = canvas.getContext("2d");
    const statusText = document.getElementById("status-info");

    const STORAGE_KEY = "jarvis_core_settings";
    const DEFAULTS = { speed: 1.5, vol: 1, filter: false, innerColor: "#00f3ff", outerColor: "#0064ff", pulse: 2, particles: false, showMic: false };
    
    let settings = { ...DEFAULTS };
    try { 
        let saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
        if (saved && typeof saved === 'object') { settings = { ...DEFAULTS, ...saved }; }
    } catch(e) {}

    try {
        document.getElementById("ctrl-speed").value = settings.speed;
        document.getElementById("val-speed").innerText = settings.speed; audio.playbackRate = settings.speed;
        document.getElementById("ctrl-vol").value = settings.vol;
        document.getElementById("val-vol").innerText = Math.round(settings.vol * 100); audio.volume = settings.vol;
        document.getElementById("ctrl-filter").checked = settings.filter;
        document.getElementById("ctrl-inner-color").value = settings.innerColor;
        document.getElementById("ctrl-outer-color").value = settings.outerColor;
        document.getElementById("ctrl-pulse").value = settings.pulse;
        document.getElementById("ctrl-particles").checked = settings.particles;
        document.getElementById("ctrl-mic").checked = settings.showMic;
        statusText.style.color = settings.innerColor;
    } catch(e) { console.error(e); }

    function updateMicVisibility(isVisible) {
        try {
            const parentDoc = window.parent.document;
            let styleEl = parentDoc.getElementById("mic-visibility-style");
            if(!styleEl) { styleEl = parentDoc.createElement("style"); styleEl.id = "mic-visibility-style"; parentDoc.head.appendChild(styleEl); }
            if(isVisible) { styleEl.innerHTML = ``; } 
            else { styleEl.innerHTML = `[data-testid="stVerticalBlock"] > div:has(iframe[title*="streamlit_mic_recorder"]) { display: none !important; height: 0px !important; margin: 0 !important; overflow: hidden !important; }`; }
        } catch(e) {}
    }
    updateMicVisibility(settings.showMic);

    function saveSettings() {
        settings.speed = parseFloat(document.getElementById("ctrl-speed").value) || 1.5;
        settings.vol = parseFloat(document.getElementById("ctrl-vol").value) || 1;
        settings.filter = document.getElementById("ctrl-filter").checked;
        settings.innerColor = document.getElementById("ctrl-inner-color").value;
        settings.outerColor = document.getElementById("ctrl-outer-color").value;
        settings.pulse = parseFloat(document.getElementById("ctrl-pulse").value) || 2;
        settings.particles = document.getElementById("ctrl-particles").checked;
        settings.showMic = document.getElementById("ctrl-mic").checked;
        localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    }

    // 🚨 パネルを開いた時、コアを少し左に避けてあげるアニメーション
    coreContainer.onclick = () => { 
        settingsPanel.style.display = "block"; 
        if (window.innerWidth > 768) {
            coreContainer.style.transform = "translateX(-80px)"; 
        }
    };
    closeBtn.onclick = (e) => { 
        e.preventDefault(); 
        settingsPanel.style.display = "none"; 
        coreContainer.style.transform = "translateX(0)";
    };

    document.getElementById("ctrl-speed").oninput = (e) => { document.getElementById("val-speed").innerText = e.target.value; audio.playbackRate = e.target.value; saveSettings(); };
    document.getElementById("ctrl-vol").oninput = (e) => { document.getElementById("val-vol").innerText = Math.round(e.target.value * 100); audio.volume = e.target.value; saveSettings(); };
    document.getElementById("ctrl-inner-color").oninput = (e) => { settings.innerColor = e.target.value; statusText.style.color = settings.innerColor; saveSettings(); };
    document.getElementById("ctrl-outer-color").oninput = (e) => { settings.outerColor = e.target.value; saveSettings(); };
    document.getElementById("ctrl-pulse").onchange = (e) => { settings.pulse = parseFloat(e.target.value); saveSettings(); };
    document.getElementById("ctrl-particles").onchange = (e) => { settings.particles = e.target.checked; saveSettings(); };
    document.getElementById("ctrl-mic").onchange = (e) => { settings.showMic = e.target.checked; saveSettings(); updateMicVisibility(settings.showMic); };
    
    let isZenMode = false;
    document.getElementById("ctrl-zen").onclick = () => {
        try {
            const parentDoc = window.parent.document; isZenMode = !isZenMode; let btn = document.getElementById("ctrl-zen");
            if(isZenMode) { btn.innerText = "Deactivate Zen Protocol"; btn.style.background = "#e53e3e"; if(!parentDoc.getElementById("zen-style")) { const style = parentDoc.createElement("style"); style.id = "zen-style"; style.innerHTML = `[data-testid="stSidebar"], [data-testid="stChatInput"], [data-testid="stChatMessage"] { display: none !important; transition: all 0.5s; } .stApp { background-color: #ffffff !important; }`; parentDoc.head.appendChild(style); } } 
            else { btn.innerText = "Activate Zen Protocol"; btn.style.background = "#1a202c"; const style = parentDoc.getElementById("zen-style"); if(style) style.remove(); }
        } catch(e) {}
    };

    document.getElementById("ctrl-reset").onclick = () => { localStorage.removeItem(STORAGE_KEY); location.reload(); };

    let audioCtx, analyser, source, biquadFilter, dataArray, smoothedData, isSetup = false;
    function setup() { 
        if (isSetup || !audio.src.includes("base64")) return; 
        try { 
            audioCtx = new (window.AudioContext || window.webkitAudioContext)(); analyser = audioCtx.createAnalyser(); analyser.fftSize = 128; 
            biquadFilter = audioCtx.createBiquadFilter(); biquadFilter.type = "bandpass"; biquadFilter.frequency.value = 1500; biquadFilter.Q.value = 1.5; 
            source = audioCtx.createMediaElementSource(audio); 
            if(settings.filter) { source.connect(biquadFilter); biquadFilter.connect(analyser); } else { source.connect(analyser); } 
            analyser.connect(audioCtx.destination); 
            dataArray = new Uint8Array(analyser.frequencyBinCount); smoothedData = new Float32Array(analyser.frequencyBinCount); 
            isSetup = true; 
        } catch(e) {} 
    }
    
    function hexToRgb(hex) { let result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex); return result ? `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}` : "0, 243, 255"; }
    
    let particles = [];
    function draw() { 
        requestAnimationFrame(draw); 
        const cx = canvas.width/2, cy = canvas.height/2; ctx.clearRect(0,0,canvas.width,canvas.height); 
        let avg = 0; let time = Date.now() / 1000; 
        
        if(isSetup && !audio.paused) { 
            analyser.getByteFrequencyData(dataArray); 
            for(let i=0; i<30; i++) { smoothedData[i] += (dataArray[i]-smoothedData[i])*0.25; avg += smoothedData[i]; } 
            avg /= 30; 
        } else { 
            avg = 15 + Math.sin(time * settings.pulse) * 8; 
        } 
        
        let rgbInner = hexToRgb(settings.innerColor); let rgbOuter = hexToRgb(settings.outerColor); 
        let r = 55 + avg * 0.9; 
        
        let g = ctx.createRadialGradient(cx,cy,0,cx,cy,r); 
        g.addColorStop(0,"rgba(255,255,255,1)"); g.addColorStop(0.4, `rgba(${rgbInner}, 0.8)`); g.addColorStop(1,"transparent"); 
        ctx.fillStyle=g; ctx.beginPath(); ctx.arc(cx,cy,r,0,Math.PI*2); ctx.fill(); 
        
        for(let j=0; j<2; j++) { 
            ctx.beginPath(); let rot = (j==0 ? time : -time * 0.7); let baseR = 75 + (j*15); 
            for(let i=0; i<=60; i++) { 
                let a = (i/60)*Math.PI*2 + rot; let dIdx = i <= 30 ? i : 60 - i; 
                let wave = (isSetup && !audio.paused) ? smoothedData[dIdx % 30]*0.5 : Math.sin(time * settings.pulse * 2 + i/5)*3; 
                let x = cx + Math.cos(a)*(baseR + wave), y = cy + Math.sin(a)*(baseR + wave); 
                if(i==0) ctx.moveTo(x,y); else ctx.lineTo(x,y); 
            } 
            ctx.strokeStyle = j==0 ? `rgba(${rgbOuter}, 0.9)` : `rgba(${rgbOuter}, 0.4)`; ctx.lineWidth = j==0 ? 2 : 1.5; ctx.stroke(); 
        } 
        
        if (settings.particles) { 
            if(particles.length < 30) particles.push({x: cx, y: cy, vx: (Math.random()-0.5)*2, vy: (Math.random()-0.5)*2, life: 1}); 
            for(let i=0; i<particles.length; i++) { 
                let p = particles[i]; p.x += p.vx; p.y += p.vy; p.life -= 0.02; 
                if(p.life <= 0) { particles.splice(i, 1); i--; continue; } 
                ctx.fillStyle = `rgba(${rgbInner}, ${p.life})`; ctx.beginPath(); ctx.arc(p.x, p.y, 2, 0, Math.PI*2); ctx.fill(); 
            } 
        } 
    }
    audio.onplay = setup; draw();
</script>
"""

# ==========================================
# 🖥️ 4. メイン画面の表示
# ==========================================

# ------------------------------------------
# ⚡ モード：AI Console
# ------------------------------------------
if page == "AI Console":
    chat_sub_mode = st.radio("DISPLAY STYLE", ["HUD Mode", "Chat Mode"], horizontal=True, label_visibility="collapsed")
    
    if "chat_history" not in st.session_state: st.session_state.chat_history = []
    if "ai_voice_base64" not in st.session_state: st.session_state.ai_voice_base64 = None
    if "just_generated_audio" not in st.session_state: st.session_state.just_generated_audio = False

    core_height = 450 if chat_sub_mode == "HUD Mode" else 220
    v_data = st.session_state.ai_voice_base64 if st.session_state.ai_voice_base64 else ""
    autoplay_attr = "autoplay" if st.session_state.just_generated_audio else ""
    st.session_state.just_generated_audio = False 
    
    core_html = MASTER_CORE_TEMPLATE.replace("H_VAL", str(core_height)).replace("MAX_Wpx", "400").replace("V_DATA", v_data).replace("A_PLAY", autoplay_attr)
    st.components.v1.html(core_html, height=core_height + 20)

    if chat_sub_mode == "Chat Mode":
        for m in st.session_state.chat_history:
            with st.chat_message(m["role"], avatar=m["avatar"]):
                st.markdown(m["content"])
    
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

    if spoken_text:
        st.session_state.chat_history.append({"role": "user", "avatar": "👤", "content": spoken_text})
        st.rerun()

    if prompt := st.chat_input("コマンドを入力してください、ボス", key="console_input"):
        st.session_state.chat_history.append({"role": "user", "avatar": "👤", "content": prompt})
        st.rerun()

    if st.session_state.chat_history and st.session_state.chat_history[-1]["role"] == "user":
        last_prompt = st.session_state.chat_history[-1]["content"]
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner(" "):
                model = genai.GenerativeModel(model_name='gemini-2.5-flash')
                response = model.generate_content(last_prompt)
                ai_text = response.text
                st.markdown(ai_text)
                
                clean_text = ai_text.replace("*", "").replace("#", "").replace("`", "").replace("_", "")
                tts = gTTS(text=clean_text, lang='ja')
                audio_fp = io.BytesIO()
                tts.write_to_fp(audio_fp)
                st.session_state.ai_voice_base64 = base64.b64encode(audio_fp.getvalue()).decode()
                st.session_state.just_generated_audio = True 
                
                st.session_state.chat_history.append({"role": "assistant", "avatar": "🤖", "content": ai_text})
                st.rerun()

# ------------------------------------------
# 🔥 モード：Forge Lab (App Forge)
# ------------------------------------------
elif page == "Forge Lab":
    if "projects" not in st.session_state:
        st.session_state.projects = {"Project Alpha": []}
    if "current_project" not in st.session_state:
        st.session_state.current_project = "Project Alpha"
    if "ai_voice_base64" not in st.session_state:
        st.session_state.ai_voice_base64 = None
    if "just_generated_audio" not in st.session_state:
        st.session_state.just_generated_audio = False
    if "generated_app_code" not in st.session_state:
        st.session_state.generated_app_code = ""

    # 🎛️ サイドバー：プロジェクト管理 ＆ コマンド入力
    with st.sidebar:
        st.markdown("<hr style='margin: 10px 0; border: 0.5px solid rgba(0,0,0,0.1);'>", unsafe_allow_html=True)
        st.markdown("<div style='text-align:center; font-weight:800; color:#2b6cb0; letter-spacing:2px; font-size:12px; margin-bottom:10px;'>[ WORKSPACE ]</div>", unsafe_allow_html=True)
        
        project_list = list(st.session_state.projects.keys())
        selected_project = st.selectbox("Current Project", project_list, index=project_list.index(st.session_state.current_project), label_visibility="collapsed")
        
        if selected_project != st.session_state.current_project:
            st.session_state.current_project = selected_project
            st.rerun()

        with st.expander("⚙️ Manage Projects"):
            new_proj_name = st.text_input("New Project Name", placeholder="プロジェクト名...")
            if st.button("➕ Create Project", use_container_width=True):
                if new_proj_name and new_proj_name not in st.session_state.projects:
                    st.session_state.projects[new_proj_name] = []
                    st.session_state.current_project = new_proj_name
                    st.rerun()
            st.divider()
            if st.button("🗑️ Delete Current", use_container_width=True):
                if len(st.session_state.projects) > 1:
                    del st.session_state.projects[st.session_state.current_project]
                    st.session_state.current_project = list(st.session_state.projects.keys())[0]
                    st.rerun()
                else:
                    st.error("最後のプロジェクトは削除できません。")

        st.markdown("<div style='text-align:center; font-weight:800; color:#2b6cb0; letter-spacing:2px; font-size:12px; margin-top:20px; margin-bottom:10px;'>[ COMMAND INPUT ]</div>", unsafe_allow_html=True)
        
        with st.form("forge_sidebar_form", clear_on_submit=True):
            forge_prompt = st.text_area("命令", placeholder="例：ポモドーロタイマーを作って\n（Shift + Enterで改行）", height=150, label_visibility="collapsed")
            submitted = st.form_submit_button("DEPLOY COMMAND ⚡", use_container_width=True)
        
        st.markdown("<style>iframe[title*='mic'] { mix-blend-mode: multiply; opacity: 0.8; margin-top: 10px; }</style>", unsafe_allow_html=True)
        spoken_text = speech_to_text(language='ja', start_prompt="🎙️ 音声で命令する", stop_prompt="🛑 録音停止＆送信", use_container_width=True, key='Forge_STT')

    # 🖥️ メイン画面：左(コア＆ログ) / 右(プレビュー)
    col_log, col_preview = st.columns([4, 6])

    with col_log:
        st.subheader("COMMAND TERMINAL")
        
        core_height = 250 
        v_data = st.session_state.ai_voice_base64 if st.session_state.ai_voice_base64 else ""
        autoplay = "autoplay" if st.session_state.just_generated_audio else ""
        st.session_state.just_generated_audio = False 

        core_html = MASTER_CORE_TEMPLATE.replace("H_VAL", str(core_height)).replace("MAX_Wpx", "250").replace("V_DATA", v_data).replace("A_PLAY", autoplay)
        st.components.v1.html(core_html, height=core_height + 20)

        with st.container(height=400, border=False):
            current_history = st.session_state.projects[st.session_state.current_project]
            if not current_history:
                st.info("プロジェクトを開始しました。命令を入力してください。")
            for m in current_history:
                with st.chat_message(m["role"], avatar=m["avatar"]):
                    st.markdown(m["content"])

    with col_preview:
        st.subheader("THE FORGE")
        
        if st.session_state.generated_app_code:
            st.success(f"✨ 実行中: {st.session_state.current_project}")
            with st.container(border=True):
                try:
                    exec(st.session_state.generated_app_code)
                except Exception as e:
                    st.error(f"実行エラー:\n{e}")
                    
            with st.expander("📝 ソースコードを表示"):
                st.code(st.session_state.generated_app_code, language="python")
        else:
            st.markdown("""
                <div style="background: rgba(255, 255, 255, 0.4); backdrop-filter: blur(10px); border-radius: 15px; padding: 25px; border: 1px solid white; box-shadow: 6px 6px 12px rgba(163, 177, 198, 0.5); min-height: 550px;">
                    <p style="color: #2b6cb0; font-weight: bold; margin-bottom: 5px;">[ FORGE ENGINE STATUS ]</p>
                    <code style="color: #1a202c;">System: Online... Waiting for build commands.</code>
                    <hr style="border: 0.5px solid rgba(0,0,0,0.1); margin: 20px 0;">
                    <div style="text-align: center; color: #a0aec0; margin-top: 150px;">
                        <p>ここにAIが具現化したアプリやコードが表示されます、ボス。</p>
                    </div>
                </div>
            """, unsafe_allow_html=True)

    # ⚙️ 実行ロジック
    trigger_prompt = None
    if submitted and forge_prompt:
        trigger_prompt = forge_prompt
    elif spoken_text:
        trigger_prompt = spoken_text

    if trigger_prompt:
        st.session_state.projects[st.session_state.current_project].append({"role": "user", "avatar": "👤", "content": trigger_prompt})
        
        with st.spinner("Building Application..."):
            try:
                system_instruction = """
                あなたは優秀なPythonエンジニアです。ユーザーの指示に従って、Streamlitで動くアプリケーションのコードを作成してください。
                【重要ルール】
                1. 返答は、実行可能なPythonコードのみを含めてください。
                2. Markdownの ```python と ``` でコードを囲んでください。
                3. import streamlit as st は必ず含めてください。
                4. st.set_page_config() は絶対に書かないでください。
                """
                
                model = genai.GenerativeModel('gemini-2.5-flash')
                response = model.generate_content(system_instruction + "\n指示: " + trigger_prompt)
                ai_text = response.text
                
                code_match = re.search(r'```python\n(.*?)\n```', ai_text, re.DOTALL)
                
                if code_match:
                    extracted_code = code_match.group(1)
                    st.session_state.generated_app_code = extracted_code
                    reply_text = "構築が完了しました。右側のパネルをご確認ください。"
                else:
                    reply_text = "申し訳ありません、コードの生成に失敗しました。\n\n" + ai_text
                
                clean_text = re.sub(r'[*#`_]', '', reply_text)
                tts = gTTS(text=clean_text, lang='ja')
                audio_fp = io.BytesIO()
                tts.write_to_fp(audio_fp)
                st.session_state.ai_voice_base64 = base64.b64encode(audio_fp.getvalue()).decode()
                st.session_state.just_generated_audio = True
                
                st.session_state.projects[st.session_state.current_project].append({"role": "assistant", "avatar": "🤖", "content": reply_text})
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

# ------------------------------------------
# 📋 モード：現在のタスク
# ------------------------------------------
elif page == "Active Tasks" or page == "📋 現在のタスク":
    st.title("📋 現在のタスク")
    raw_data = sheet.get_all_values() 
    
    if len(raw_data) > 1:
        headers = ['タスクID', '目標', 'タスク内容', 'ステータス', 'ログ', 'ボスの回答']
        body = [row[:6] + [''] * (6 - len(row[:6])) for row in raw_data[1:]] 
        df = pd.DataFrame(body, columns=headers)
        
        st.markdown("### 📈 プロジェクト状況")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("総タスク数", len(df))
        col2.metric("未着手 📝", len(df[df['ステータス'] == '未着手']))
        col3.metric("実行中 ⚙️", len(df[df['ステータス'] == '実行中']))
        col4.metric("確認待ち 🚨", len(df[df['ステータス'] == '確認待ち']))
        st.divider()

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

        st.markdown("### 📋 進行中のタスク一覧")
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
elif page == "Task History" or page == "🕰️ 過去のタスク":
    st.title("🕰️ 過去のタスク (完了済み)")
    raw_data = sheet.get_all_values() 
    if len(raw_data) > 1:
        headers = ['タスクID', '目標', 'タスク内容', 'ステータス', 'ログ', 'ボスの回答']
        body = [row[:6] + [''] * (6 - len(row[:6])) for row in raw_data[1:]] 
        df = pd.DataFrame(body, columns=headers)
        
        completed_df = df[df['ステータス'] == '完了']
        if not completed_df.empty:
            st.dataframe(completed_df, use_container_width=True)
        else:
            st.info("完了したタスクはまだありません。")

# ------------------------------------------
# 📊 モード：ダッシュボード
# ------------------------------------------
elif page == "Dashboard" or page == "📊 ダッシュボード":
    st.title("📊 ダッシュボード")
    st.info("ここに全体のグラフや、相棒の稼働状況などの分析画面を追加します！（次回実装！）")

# ------------------------------------------
# 🗝️ モード：秘密の保管庫
# ------------------------------------------
elif page == "Secure Vault" or page == "🗝️ 秘密の保管庫":
    st.title("🗝️ 秘密の保管庫")
    st.warning("⚠️ 新しいAPIキー（Slack, n8nなど）を登録・管理する厳重管理エリアを作ります。（次回実装！）")
