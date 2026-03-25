import streamlit as st
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from gtts import gTTS
import base64
import io
import re
from streamlit_mic_recorder import speech_to_text
import pypdf
import os
import json
import hashlib 
import smtplib
from email.mime.text import MIMEText
import random
# === 新規追加：カレンダー操作用の道具 ===
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import datetime

# === システム起動時の「金庫の鍵」自動読み込み ===
if "global_api_keys" not in st.session_state:
    st.session_state.global_api_keys = {}
    vault_file = "vault_data.json"
    if os.path.exists(vault_file):
        try:
            with open(vault_file, "r", encoding="utf-8") as f:
                vd = json.load(f)
                st.session_state.global_api_keys = vd.get("api_keys", {})
        except:
            pass

st.set_page_config(page_title="AIbou", page_icon="❖", layout="wide")

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
        ["AI Console", "Forge Lab", "📂 Document Vault", "Active Tasks", "Task History", "Dashboard", "Secure Vault", "🧠 Core Upgrade"], # 👈 Upgrade復活！
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
        /* 1. 全体の背景（白・微グレー）とサイドバーの枠線完全除去 */
        .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] { background-color: #e0e5ec !important; background-image: none !important; }
        [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child { background-color: #e0e5ec !important; border-right: none !important; box-shadow: none !important; }
        .stApp, p, span, div { color: #2d3748 !important; }
        [data-testid="stBottom"], [data-testid="stBottom"] > div { background: transparent !important; }
        [data-testid="stSidebar"] h1, [data-testid="stSidebar"] label { color: #1a202c !important; text-shadow: none !important; font-weight: 800 !important; letter-spacing: 2px !important; }
        [data-testid="stSidebar"] [data-testid="stExpander"] { border: none !important; background: transparent !important; box-shadow: none !important; }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary p { color: #1a202c !important; font-weight: 800 !important; letter-spacing: 2px !important; font-size: 14px !important; }
        
        /* 2. 【ボタン全体】クリアで3Dなボタンベース */
        div[role="radiogroup"] { gap: 15px; padding: 10px; }
        div[role="radiogroup"] > label { background: rgba(255, 255, 255, 0.6) !important; backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.8) !important; border-radius: 15px !important; padding: 10px 20px !important; box-shadow: 6px 6px 12px rgba(163, 177, 198, 0.5), -6px -6px 12px rgba(255, 255, 255, 0.9) !important; transition: all 0.2s ease-in-out; cursor: pointer; }
        div[role="radiogroup"] > label p { color: #1a202c !important; font-weight: bold !important; }
        div[role="radiogroup"] > label[data-checked="true"] { box-shadow: inset 4px 4px 8px rgba(163, 177, 198, 0.6), inset -4px -4px 8px rgba(255, 255, 255, 0.9) !important; border: 1px solid #00f3ff !important; }
        div[role="radiogroup"] > label[data-checked="true"] p { color: #1a202c !important; text-shadow: none !important; }
        div[role="radiogroup"] > label[data-checked="true"] span[data-baseweb="radio"] > div { background-color: #00f3ff !important; }
        div[role="radiogroup"] > label[data-checked="true"] span[data-baseweb="radio"] > div > div { background-color: #00f3ff !important; }
        
        /* 🚨 3. 【すべての入力欄】スマホののっぺり化を解除し、3Dガラスエフェクトを適用 */
        [data-testid="stChatInput"], 
        [data-testid="stTextArea"] textarea, 
        [data-testid="stTextInput"] input { 
            -webkit-appearance: none !important; /* スマホの標準デザインを強制解除 */
            appearance: none !important;
            background: rgba(255, 255, 255, 0.5) !important; 
            backdrop-filter: blur(15px); 
            border: 1px solid rgba(255, 255, 255, 0.9) !important; 
            border-radius: 20px !important; 
            box-shadow: 10px 10px 20px rgba(163, 177, 198, 0.6), -10px -10px 20px rgba(255, 255, 255, 1), inset 2px 2px 5px rgba(255, 255, 255, 0.6) !important; 
            padding: 10px 15px !important; 
            color: #2b6cb0 !important; 
            font-weight: bold; 
            font-family: 'Share Tech Mono', sans-serif; 
            transition: all 0.2s ease-in-out; 
        }
        
        /* 入力中（フォーカス時）は水色に発光 */
        [data-testid="stChatInput"]:focus-within, 
        [data-testid="stTextArea"] textarea:focus, 
        [data-testid="stTextInput"] input:focus { 
            border-color: #00f3ff !important; 
            box-shadow: inset 2px 2px 5px rgba(255, 255, 255, 0.6), 0 0 15px rgba(0, 243, 255, 0.5) !important; 
            outline: none !important; 
        }
        
        /* 4. チャットの吹き出し */
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
# 📅 GOOGLE CALENDAR CONTROLLER (手足となる機能)
# ==========================================
def get_calendar_service(json_str):
    if not json_str: return None
    try:
        creds_dict = json.loads(json_str)
        creds = Credentials.from_service_account_info(
            creds_dict, scopes=['https://www.googleapis.com/auth/calendar']
        )
        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        return None

def get_upcoming_events(service):
    if not service: return "カレンダーが連携されていません。"
    try:
        now = datetime.datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(calendarId='primary', timeMin=now,
                                              maxResults=5, singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])
        if not events: return "直近の予定はありません。"
        
        res = "【直近の予定】\n"
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            # 見やすくフォーマット
            start_formatted = start[:16].replace('T', ' ')
            res += f"- {start_formatted} : {event['summary']}\n"
        return res
    except Exception as e:
        return f"予定の取得に失敗しました: {e}"

def create_calendar_event(service, title, start_time, end_time):
    if not service: return False
    try:
        event = {
            'summary': title,
            'start': {'dateTime': start_time, 'timeZone': 'Asia/Tokyo'},
            'end': {'dateTime': end_time, 'timeZone': 'Asia/Tokyo'},
        }
        service.events().insert(calendarId='primary', body=event).execute()
        return True
    except Exception as e:
        return False

# ==========================================
# 🖥️ 4. メイン画面の表示
# ==========================================

# ------------------------------------------
# 🤖 モード：AI Console (HUD & Voice機能 ＋ カレンダー連携統合版)
# ------------------------------------------
if page == "AI Console":
    chat_sub_mode = st.radio("DISPLAY STYLE", ["HUD Mode", "Chat Mode"], horizontal=True, label_visibility="collapsed")
    
    if "chat_history" not in st.session_state: st.session_state.chat_history = []
    if "ai_voice_base64" not in st.session_state: st.session_state.ai_voice_base64 = None
    if "just_generated_audio" not in st.session_state: st.session_state.just_generated_audio = False
    if "pending_event" not in st.session_state: st.session_state.pending_event = None # 👈 カレンダー用に追加

    core_height = 450 if chat_sub_mode == "HUD Mode" else 220
    v_data = st.session_state.ai_voice_base64 if st.session_state.ai_voice_base64 else ""
    autoplay_attr = "autoplay" if st.session_state.just_generated_audio else ""
    st.session_state.just_generated_audio = False 
    
    # コアの描画
    core_html = MASTER_CORE_TEMPLATE.replace("H_VAL", str(core_height)).replace("MAX_Wpx", "400").replace("V_DATA", v_data).replace("A_PLAY", autoplay_attr)
    st.components.v1.html(core_html, height=core_height + 20)

    # 🚨 追加：カレンダー追加の「確認ボタン」UI（コアの下に表示）
    if st.session_state.pending_event:
        pe = st.session_state.pending_event
        st.warning(f"📅 以下の予定をカレンダーに登録しますか？\n\n**{pe['title']}**\n開始: {pe['start']}\n終了: {pe['end']}")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ 登録する (Approve)", use_container_width=True):
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
            if st.button("❌ キャンセル (Reject)", use_container_width=True):
                st.session_state.chat_history.append({"role": "assistant", "avatar": "🤖", "content": "登録をキャンセルしました。"})
                st.session_state.pending_event = None
                st.rerun()

    # チャットモード時のログ表示
    if chat_sub_mode == "Chat Mode":
        for m in st.session_state.chat_history:
            with st.chat_message(m["role"], avatar=m["avatar"]):
                st.markdown(m["content"])
    
    # マイクボタンのCSS
    st.markdown("""
        <style>
        iframe[title*='mic'] { mix-blend-mode: multiply !important; opacity: 0.7; transition: all 0.3s ease-in-out; } 
        iframe[title*='mic']:hover { opacity: 1.0; filter: drop-shadow(0px 5px 8px rgba(0, 243, 255, 0.6)); transform: translateY(-2px); } 
        [data-testid='stVerticalBlock'] > div:has(iframe[title*='mic']) { margin-bottom: -25px !important; position: relative; z-index: 50; }
        </style>
    """, unsafe_allow_html=True)
    
    # マイクボタンの配置
    col1, col2, col3 = st.columns([5, 3, 5]) 
    with col2:
        spoken_text = speech_to_text(language='ja', start_prompt="🎙️ PUSH TO TALK", stop_prompt="🛑 TAP TO SEND", use_container_width=True, just_once=True, key='STT')

    # 予定確認中は誤作動を防ぐため入力を一時停止
    if not st.session_state.pending_event:
        if spoken_text:
            st.session_state.chat_history.append({"role": "user", "avatar": "👤", "content": spoken_text})
            st.rerun()

        if prompt := st.chat_input("コマンドを入力してください、ボス", key="console_input"):
            st.session_state.chat_history.append({"role": "user", "avatar": "👤", "content": prompt})
            st.rerun()

    # 🧠 AIの応答生成 ＋ 音声合成 ＋ カレンダーコマンド検知
    if st.session_state.chat_history and st.session_state.chat_history[-1]["role"] == "user" and not st.session_state.pending_event:
        last_prompt = st.session_state.chat_history[-1]["content"]
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner(" "):
                # 金庫からGeminiキーを自動取得
                gemini_key = st.session_state.global_api_keys.get("gemini", "")
                if gemini_key:
                    genai.configure(api_key=gemini_key)
                
                # 💡 マスターAIのプロンプト
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
                ※時間は必ずISO形式（Tで繋ぐ）で、終了時間が不明な場合は開始から1時間後に設定してください。
                """
                
                model = genai.GenerativeModel(model_name='gemini-2.5-flash')
                # 履歴を含めたプロンプト構成
                history_text = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.chat_history[:-1]])
                full_prompt = system_instruction + "\n\n【会話履歴】\n" + history_text + "\n\nボス: " + last_prompt

                response = model.generate_content(full_prompt)
                ai_text = response.text
                
                # 💡 カレンダーコマンドの検知と除去
                match = re.search(r'\[CALENDAR_ADD:\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\]', ai_text)
                if match:
                    title, start, end = match.groups()
                    st.session_state.pending_event = {"title": title.strip(), "start": start.strip(), "end": end.strip()}
                    ai_text = ai_text.replace(match.group(0), "").strip()
                
                st.markdown(ai_text)
                
                # 🎙️ 音声合成（gTTS）の復元
                clean_text = ai_text.replace("*", "").replace("#", "").replace("`", "").replace("_", "")
                tts = gTTS(text=clean_text, lang='ja')
                audio_fp = io.BytesIO()
                tts.write_to_fp(audio_fp)
                st.session_state.ai_voice_base64 = base64.b64encode(audio_fp.getvalue()).decode()
                st.session_state.just_generated_audio = True 
                
                st.session_state.chat_history.append({"role": "assistant", "avatar": "🤖", "content": ai_text})
                st.rerun()

# ------------------------------------------
# ❖ モード：Forge Lab (自己修復・自律エージェント仕様)
# ------------------------------------------
elif page == "Forge Lab":
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
        </style>
    """, unsafe_allow_html=True)

    # 🚨 自己修復トリガーの初期化
    if "auto_fix_prompt" not in st.session_state:
        st.session_state.auto_fix_prompt = ""

    if "forge_workspaces" not in st.session_state:
        st.session_state.forge_workspaces = {"First Project": {"chat": [], "code": "", "retries": 0}}
    if "current_forge_ws" not in st.session_state:
        st.session_state.current_forge_ws = None 

    if st.session_state.ai_voice_base64 not in st.session_state:
        st.session_state.ai_voice_base64 = None
    if "just_generated_audio" not in st.session_state:
        st.session_state.just_generated_audio = False

    # 🚪 ダッシュボード画面
    if st.session_state.current_forge_ws is None:
        st.markdown("<h2 class='cyber-title'>❖ FORGE LAB WORKSPACES</h2>", unsafe_allow_html=True)
        st.caption("開発環境を選択、または新しいプロジェクトを立ち上げてください。")
        
        items = ["__NEW__"] + list(st.session_state.forge_workspaces.keys())
        
        for i in range(0, len(items), 3):
            cols = st.columns(3)
            for j in range(3):
                if i + j < len(items):
                    ws_name = items[i + j]
                    with cols[j]:
                        if ws_name == "__NEW__":
                            with st.container(border=True):
                                st.markdown("<h4 style='text-align:center; color:#00f3ff; font-weight:800;'>⬡ CREATE NEW</h4>", unsafe_allow_html=True)
                                new_ws_name = st.text_input("Project Name", key="new_ws_name", label_visibility="collapsed", placeholder="New Project Name...")
                                if st.button("INITIALIZE ⚡", key="create_ws", use_container_width=True):
                                    if new_ws_name and new_ws_name not in st.session_state.forge_workspaces:
                                        st.session_state.forge_workspaces[new_ws_name] = {"chat": [], "code": "", "retries": 0}
                                        st.session_state.current_forge_ws = new_ws_name
                                        st.rerun()
                        else:
                            with st.container(border=True):
                                st.markdown(f"<h4 style='color:#1a202c; font-weight:bold;'>❖ {ws_name}</h4>", unsafe_allow_html=True)
                                chat_count = len(st.session_state.forge_workspaces[ws_name]['chat'])
                                st.markdown(f"<p style='font-size: 12px; color: #718096;'><span class='status-dot'>●</span>ONLINE | Logs: {chat_count}</p>", unsafe_allow_html=True)
                                
                                c1, c2 = st.columns([7, 3])
                                with c1:
                                    if st.button("ACCESS ➔", key=f"open_ws_{ws_name}", use_container_width=True):
                                        st.session_state.current_forge_ws = ws_name
                                        st.rerun()
                                with c2:
                                    if st.button("DEL", key=f"del_ws_{ws_name}", use_container_width=True):
                                        del st.session_state.forge_workspaces[ws_name]
                                        st.rerun()

    # 🖥️ ワークスペース内部画面
    else:
        ws_name = st.session_state.current_forge_ws
        ws_data = st.session_state.forge_workspaces[ws_name]
        if "retries" not in ws_data:
            ws_data["retries"] = 0
        
        if st.button("⬅ RETURN TO DASHBOARD"):
            st.session_state.current_forge_ws = None
            st.rerun()
            
        st.markdown(f"<h2 class='cyber-title'>❖ PROJECT : {ws_name}</h2>", unsafe_allow_html=True)

        with st.sidebar:
            st.markdown(f"<div style='text-align:center; font-weight:800; color:#2b6cb0; margin-bottom:10px;'>[ ❖ {ws_name} ]</div>", unsafe_allow_html=True)
            with st.form("forge_sidebar_form", clear_on_submit=True):
                forge_prompt = st.text_area("命令", placeholder="例：ポモドーロタイマーを作って\n（Shift + Enterで改行）", height=150, label_visibility="collapsed")
                submitted = st.form_submit_button("DEPLOY COMMAND ⚡", use_container_width=True)
            st.markdown("<style>iframe[title*='mic'] { mix-blend-mode: multiply; opacity: 0.8; margin-top: 10px; }</style>", unsafe_allow_html=True)
            spoken_text = speech_to_text(language='ja', start_prompt="🎙️ 音声で命令する", stop_prompt="🛑 録音停止＆送信", use_container_width=True, key='Forge_STT')

        col_log, col_preview = st.columns([3, 7])
        
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
                    st.info("命令を入力してください。")
                for m in ws_data["chat"]:
                    with st.chat_message(m["role"], avatar="👤" if m["role"]=="user" else "🤖" if m["role"]=="assistant" else "⚠️"):
                        st.markdown(m["content"])

        with col_preview:
            st.markdown("<p style='font-weight:bold; color:#718096;'>[ THE FORGE / PREVIEW ]</p>", unsafe_allow_html=True)
            
            # 🚨 自己修復中の場合は実行をスキップしてメッセージを出す
            if st.session_state.auto_fix_prompt:
                st.warning("⚙️ システムエラーを検知しました。AIが自律的に別のアプローチを模索・修復しています...")
            elif ws_data["code"]:
                st.download_button(label="💾 CODE EXPORT (.py)", data=ws_data["code"], file_name=f"{ws_name}.py", mime="text/plain", use_container_width=True)
                with st.container(border=True):
                    try:
                        # コードの実行テスト
                        exec(ws_data["code"], globals())
                        ws_data["retries"] = 0 # 成功したらリセット！
                    except Exception as e:
                        st.error(f"実行エラー:\n{e}")
                        
                        # 🚨 自己修復トリガーの発動
                        if ws_data["retries"] < 3:
                            ws_data["retries"] += 1
                            st.session_state.auto_fix_prompt = f"実行時に以下のエラーが発生しました。外部ライブラリがない場合は標準機能やGemini APIで代替するなど、アプローチを変えてエラーが出ない完全なコードに修正して！\n\n【エラー内容】\n{e}"
                            st.rerun() # リロードして自己修復モードへ移行
                        else:
                            st.error("❌ 自己修復が上限（3回）に達しました。ボスの手動指示が必要です。")
                            
                with st.expander("📝 SOURCE CODE"):
                    st.code(ws_data["code"], language="python")
            else:
                st.info("System Online. Waiting for commands...")

        # 実行ロジック
        trigger_prompt = forge_prompt if submitted else spoken_text if spoken_text else None
        
        # 自己修復プロンプトの割り込み処理
        is_auto_fix = False
        if st.session_state.auto_fix_prompt:
            trigger_prompt = st.session_state.auto_fix_prompt
            st.session_state.auto_fix_prompt = "" # 消費してリセット
            is_auto_fix = True

        if trigger_prompt:
            if is_auto_fix:
                ws_data["chat"].append({"role": "system", "avatar": "⚠️", "content": f"⚙️ AUTO-HEALING INITIATED:\n{trigger_prompt}"})
                sys_msg = "Auto-Healing in progress... 別のアプローチでコードを再構築中..."
            else:
                ws_data["chat"].append({"role": "user", "avatar": "👤", "content": trigger_prompt})
                ws_data["retries"] = 0 # 手動入力があったらリセット
                sys_msg = "Building Application..."

            with st.spinner(sys_msg):
                try:
                    history_text = "【履歴】\n" + "\n".join([f"{msg['role']}: {msg['content']}" for msg in ws_data["chat"][:-1]])
                    
                    # 🚨 修正：AIの脳みそを【独立型・汎用アプリ生成仕様（ルートB）】にアップデート
                    system_instruction = f"""
                    あなたはStreamlitアプリを作成する天才エンジニア。
                    
                    【絶対遵守のレイアウト保護ルール】
                    1. `st.sidebar` と `st.set_page_config` は【絶対に使用禁止】（親アプリが崩壊します）。
                    2. 🚨 `st.chat_input` もレイアウトが細く潰れるバグを引き起こすため【絶対に使用禁止】。チャットUIが必要な場合は、必ず `st.text_input` と `st.button`（または `st.form`）で代用すること。
                    
                    【独立型アプリのAPI・認証ルール（超重要）】
                    1. 生成するアプリは、どこでも誰でも動かせる「完全独立型」でなければなりません。
                    2. Gemini API (`google.generativeai`) を使用する場合は、必ずアプリの最上部（または `st.expander` 内）に `st.text_input("Gemini API Key", type="password")` を用いて「APIキー入力欄」を作成してください。
                    3. ユーザーがAPIキーを入力するまでは、AIを呼び出すメイン機能を表示せず、`st.info` 等でキーの入力を促す安全な設計にしてください。
                    4. キーが入力されたら `genai.configure(api_key=入力されたキー)` を実行してAIを起動してください。
                    
                    【無料のハイクオリティ音声機能ルール】
                    1. 有料のOpenAIライブラリは一切不要です。
                    2. 🎙️ 音声入力(STT): `from streamlit_mic_recorder import speech_to_text` をインポートし、`text = speech_to_text(language='ja', key='mic')` を使う。
                    3. 🗣️ 音声合成(TTS): `from gtts import gTTS` を使い、生成した音声を `st.audio` などで再生する。
                    
                    【その他のルール】
                    1. コードは `# ...` などの省略をせず、1行目から最後まで完全に出力すること。
                    2. コードブロックの後に「💡 次の拡張アイデア：」を3つ提案すること。
                    
                    {history_text}
                    """
                    
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    response = model.generate_content(system_instruction + "\n現在の指示: " + trigger_prompt)
                    ai_text = response.text
                    
                    code_match = re.search(r'```python\n(.*?)\n```', ai_text, re.DOTALL)
                    if code_match:
                        ws_data["code"] = code_match.group(1)
                        reply_text = ai_text.replace(code_match.group(0), "").strip() or "構築（修復）が完了しました。"
                    else:
                        reply_text = "コード生成に失敗しました。\n" + ai_text
                        
                    tts = gTTS(text=re.sub(r'[*#`_]', '', reply_text), lang='ja')
                    audio_fp = io.BytesIO()
                    tts.write_to_fp(audio_fp)
                    st.session_state.ai_voice_base64 = base64.b64encode(audio_fp.getvalue()).decode()
                    st.session_state.just_generated_audio = True
                    ws_data["chat"].append({"role": "assistant", "avatar": "🤖", "content": reply_text})
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

# ------------------------------------------
# ⌘ モード：Document Vault (サイバー・ダッシュボード仕様)
# ------------------------------------------
elif page == "📂 Document Vault":
    if "vault_notebooks" not in st.session_state:
        st.session_state.vault_notebooks = {} 
    if "current_vault_nb" not in st.session_state:
        st.session_state.current_vault_nb = None

    if st.session_state.current_vault_nb is None:
        st.markdown("<h2 class='cyber-title'>⌘ DOCUMENT VAULT</h2>", unsafe_allow_html=True)
        st.caption("資料保管庫（ノートブック）を選択、または新規作成してください。")
        
        items = ["__NEW__"] + list(st.session_state.vault_notebooks.keys())
        for i in range(0, len(items), 3):
            cols = st.columns(3)
            for j in range(3):
                if i + j < len(items):
                    nb_name = items[i + j]
                    with cols[j]:
                        if nb_name == "__NEW__":
                            with st.container(border=True):
                                st.markdown("<h4 style='text-align:center; color:#00f3ff; font-weight:800;'>⬡ NEW VAULT</h4>", unsafe_allow_html=True)
                                new_nb_name = st.text_input("Vault Name", key="new_nb_name", label_visibility="collapsed", placeholder="New Vault Name...")
                                if st.button("INITIALIZE ⚡", key="create_nb", use_container_width=True):
                                    if new_nb_name and new_nb_name not in st.session_state.vault_notebooks:
                                        st.session_state.vault_notebooks[new_nb_name] = {"docs": {}, "chat": []}
                                        st.session_state.current_vault_nb = new_nb_name
                                        st.rerun()
                        else:
                            with st.container(border=True):
                                st.markdown(f"<h4 style='color:#1a202c; font-weight:bold;'>⌘ {nb_name}</h4>", unsafe_allow_html=True)
                                doc_count = len(st.session_state.vault_notebooks[nb_name]['docs'])
                                st.markdown(f"<p style='font-size: 12px; color: #718096;'><span class='status-dot'>●</span>SECURED | Docs: {doc_count}</p>", unsafe_allow_html=True)
                                
                                c1, c2 = st.columns([7, 3])
                                with c1:
                                    if st.button("ACCESS ➔", key=f"open_nb_{nb_name}", use_container_width=True):
                                        st.session_state.current_vault_nb = nb_name
                                        st.rerun()
                                with c2:
                                    if st.button("DEL", key=f"del_nb_{nb_name}", use_container_width=True):
                                        del st.session_state.vault_notebooks[nb_name]
                                        st.rerun()

    else:
        nb_name = st.session_state.current_vault_nb
        nb_data = st.session_state.vault_notebooks[nb_name]
        
        if st.button("⬅ RETURN TO VAULT INDEX"):
            st.session_state.current_vault_nb = None
            st.rerun()

        st.markdown(f"<h2 class='cyber-title'>⌘ VAULT : {nb_name}</h2>", unsafe_allow_html=True)
        
        col_log, col_preview = st.columns([3, 7])

        with col_log:
            st.markdown("<p style='font-weight:bold; color:#718096;'>[ VAULT CONCIERGE ]</p>", unsafe_allow_html=True)
            core_height = 200
            vault_core_html = MASTER_CORE_TEMPLATE.replace("H_VAL", str(core_height)).replace("MAX_Wpx", "200").replace("V_DATA", "").replace("A_PLAY", "")
            st.components.v1.html(vault_core_html, height=core_height + 10)

            with st.container(height=400, border=False):
                if not nb_data["chat"]:
                    st.info("資料をアップロードし、質問してください。")
                for m in nb_data["chat"]:
                    with st.chat_message(m["role"], avatar="👤" if m["role"]=="user" else "🤖"):
                        st.markdown(m["content"])

            if prompt := st.chat_input("この資料について質問する...", key="vault_chat_input"):
                nb_data["chat"].append({"role": "user", "avatar": "👤", "content": prompt})
                with st.spinner("知識を抽出中..."):
                    try:
                        if not nb_data["docs"]:
                            response_text = "資料がありません。右のパネルからアップロードしてください。"
                        else:
                            all_context = "\n\n=== 資料 ===\n" + "\n---\n".join([f"【{fname}】\n{content}" for fname, content in nb_data["docs"].items()])
                            system_instruction = f"専属コンシェルジュとして、以下の資料【のみ】に基づいて回答せよ。\n{all_context}"
                            model = genai.GenerativeModel('gemini-1.5-flash')
                            response = model.generate_content(system_instruction + "\n質問: " + prompt)
                            response_text = response.text
                        nb_data["chat"].append({"role": "assistant", "avatar": "🤖", "content": response_text})
                        st.rerun()
                    except Exception as e:
                        st.error(f"解析エラー: {e}")

        with col_preview:
            st.markdown("<p style='font-weight:bold; color:#718096;'>[ MATERIAL MANAGEMENT ]</p>", unsafe_allow_html=True)
            with st.container(border=True):
                st.markdown("#### 📥 UPLOAD DATA (PDF, TXT, MD)")
                uploaded_files = st.file_uploader("ファイルをドロップ", type=["txt", "md", "pdf"], accept_multiple_files=True, label_visibility="collapsed")
                if st.button("STORE IN VAULT (丸のみ) ⚡", use_container_width=True):
                    if uploaded_files:
                        for uf in uploaded_files:
                            if uf.name not in nb_data["docs"]:
                                if uf.name.lower().endswith('.pdf'):
                                    pdf_text = "".join([page.extract_text() + "\n" for page in pypdf.PdfReader(uf).pages])
                                    nb_data["docs"][uf.name] = pdf_text
                                else:
                                    nb_data["docs"][uf.name] = io.StringIO(uf.getvalue().decode("utf-8")).read()
                        st.rerun()

            if nb_data["docs"]:
                st.markdown(f"#### 🧠 STORED DATA ({len(nb_data['docs'])} files)")
                for fname in list(nb_data["docs"].keys()):
                    with st.expander(f"📄 {fname}", expanded=False):
                        st.code(nb_data["docs"][fname][:200] + "...", language="text")
                        if st.button(f"DELETE", key=f"del_{fname}", use_container_width=True):
                            del nb_data["docs"][fname]
                            st.rerun()
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
# 🔐 モード：Secure Vault (親切マニュアル・Gmail復旧機能付き)
# ------------------------------------------
elif page == "Secure Vault":
    # 💎 UIデザイン用CSS
    st.markdown("""
        <style>
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(255, 255, 255, 0.4) !important;
            backdrop-filter: blur(10px) !important;
            border: 1px solid rgba(255, 255, 255, 0.9) !important;
            border-radius: 15px !important;
            box-shadow: 6px 6px 15px rgba(163, 177, 198, 0.4), -6px -6px 15px rgba(255, 255, 255, 0.9) !important;
        }
        .cyber-title { color: #2b6cb0; font-weight: 800; letter-spacing: 2px; margin-bottom: 20px; text-shadow: 2px 2px 4px rgba(255,255,255,0.8); }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<h2 class='cyber-title'>🔐 SECURE VAULT</h2>", unsafe_allow_html=True)
    st.caption("AI相棒や各種システムを動かすための「鍵」と「連絡網」を保管する極秘エリアです。")

    VAULT_FILE = "vault_data.json"

    def hash_password(password):
        return hashlib.sha256(password.encode()).hexdigest()

    if "vault_unlocked" not in st.session_state:
        st.session_state.vault_unlocked = False
    if "reset_mode" not in st.session_state:
        st.session_state.reset_mode = False
    if "sent_otp" not in st.session_state:
        st.session_state.sent_otp = None

    vault_data = {}
    if os.path.exists(VAULT_FILE):
        with open(VAULT_FILE, "r", encoding="utf-8") as f:
            vault_data = json.load(f)

    # ==========================================
    # 🚪 ステージ1：認証（ロック画面 ＆ パスワードリセット）
    # ==========================================
    if not st.session_state.vault_unlocked:
        col1, col2, col3 = st.columns([2, 5, 2])
        with col2:
            with st.container(border=True):
                st.markdown("<h3 style='text-align:center;'>🔑 SYSTEM LOCKED</h3>", unsafe_allow_html=True)
                
                if "master_password_hash" not in vault_data:
                    st.info("👋 初回セットアップ：あなた専用の「マスターパスワード」を作成してください。")
                    new_pass = st.text_input("新しいマスターパスワード", type="password", key="new_pass")
                    new_pass_confirm = st.text_input("確認のためもう一度入力", type="password", key="new_pass_confirm")
                    
                    if st.button("金庫を初期化する ⚡", use_container_width=True):
                        if new_pass and new_pass == new_pass_confirm:
                            vault_data["master_password_hash"] = hash_password(new_pass)
                            vault_data["api_keys"] = {
                                "gemini": "", "google_calendar": "", "slack": "", "line": "",
                                "my_email": "", "my_email_app_password": ""
                            }
                            with open(VAULT_FILE, "w", encoding="utf-8") as f:
                                json.dump(vault_data, f, indent=4)
                            st.session_state.vault_unlocked = True
                            st.success("金庫の初期化に成功しました！まずは内部で各種設定を行ってください。")
                            st.rerun()
                        else:
                            st.error("パスワードが一致しないか、入力されていません。")
                
                elif st.session_state.reset_mode:
                    st.warning("⚠️ パスワード復旧プロセスを開始します。")
                    my_email = vault_data.get("api_keys", {}).get("my_email", "")
                    my_email_pass = vault_data.get("api_keys", {}).get("my_email_app_password", "")
                    
                    if not my_email or not my_email_pass:
                        st.error("❌ 金庫内にGmailの連携設定がないため、復旧メールを送信できません。")
                        if st.button("⬅️ ロック画面に戻る"):
                            st.session_state.reset_mode = False
                            st.rerun()
                    else:
                        if st.session_state.sent_otp is None:
                            st.info(f"登録されているアドレス ({my_email}) 宛に、6桁の認証コードを送信します。")
                            if st.button("📩 認証コードを送信する", use_container_width=True):
                                otp = str(random.randint(100000, 999999))
                                try:
                                    msg = MIMEText(f"ボス、パスワードリセットの要請を受信しました。\n\n認証コード: 【 {otp} 】\n\nこのコードをアプリに入力して、新しいパスワードを設定してください。")
                                    msg["Subject"] = "【THE FORGE】パスワードリセット認証コード"
                                    msg["From"] = my_email
                                    msg["To"] = my_email
                                    
                                    server = smtplib.SMTP("smtp.gmail.com", 587)
                                    server.starttls()
                                    server.login(my_email, my_email_pass)
                                    server.send_message(msg)
                                    server.quit()
                                    
                                    st.session_state.sent_otp = otp
                                    st.success("認証コードを送信しました！メールをご確認ください。")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"メール送信に失敗しました: {e}")
                        else:
                            st.info("メールに届いた6桁の認証コードと、新しいパスワードを入力してください。")
                            entered_otp = st.text_input("認証コード (6桁)")
                            reset_new_pass = st.text_input("新しいパスワード", type="password")
                            reset_confirm_pass = st.text_input("新しいパスワード(確認)", type="password")
                            
                            if st.button("🔐 パスワードを再設定する", use_container_width=True):
                                if entered_otp == st.session_state.sent_otp:
                                    if reset_new_pass and reset_new_pass == reset_confirm_pass:
                                        vault_data["master_password_hash"] = hash_password(reset_new_pass)
                                        with open(VAULT_FILE, "w", encoding="utf-8") as f:
                                            json.dump(vault_data, f, indent=4)
                                        st.session_state.reset_mode = False
                                        st.session_state.sent_otp = None
                                        st.success("パスワードの再設定が完了しました！新しいパスワードでログインしてください。")
                                        st.rerun()
                                    else:
                                        st.error("新しいパスワードが一致しません。")
                                else:
                                    st.error("認証コードが間違っています。")
                            
                            if st.button("キャンセル"):
                                st.session_state.reset_mode = False
                                st.session_state.sent_otp = None
                                st.rerun()

                else:
                    st.warning("⚠️ このエリアはボス（管理者）の承認が必要です。")
                    enter_pass = st.text_input("マスターパスワードを入力", type="password", key="enter_pass")
                    
                    if st.button("UNLOCK 🔓", use_container_width=True):
                        if hash_password(enter_pass) == vault_data["master_password_hash"]:
                            st.session_state.vault_unlocked = True
                            st.success("認証完了。金庫を開きます。")
                            st.rerun()
                        else:
                            st.error("アクセス拒否：パスワードが違います。")
                            
                    st.markdown("---")
                    if st.button("パスワードを忘れた場合 (メールで復旧)", use_container_width=True):
                        st.session_state.reset_mode = True
                        st.rerun()

    # ==========================================
    # 🔓 ステージ2：金庫の内部（API ＆ Email設定 ＋ マニュアル）
    # ==========================================
    if st.session_state.vault_unlocked:
        if st.button("🔒 金庫をロックして退出"):
            st.session_state.vault_unlocked = False
            st.rerun()

        st.markdown("#### ⚙️ CORE API & COMMUNICATION CONFIGURATION")
        st.info("ここに入力されたキーはシステム全体で安全に共有されます。取得方法が分からない場合は「ℹ️ 取得手順」を開いてください。")
        
        with st.form("vault_keys_form"):
            keys = vault_data.get("api_keys", {})
            
            # 1. Email
            st.markdown("##### 📧 Email System (パスワード復旧・通知用)")
            new_email = st.text_input("自分のGmailアドレス", value=keys.get("my_email", ""))
            new_email_pass = st.text_input("Gmail アプリパスワード (16桁)", value=keys.get("my_email_app_password", ""), type="password")
            with st.expander("ℹ️ Gmailアプリパスワードの取得手順"):
                st.markdown("""
                1. Googleアカウントの管理画面を開く。
                2. 左側のメニューから「セキュリティ」を選択。
                3. 「Google へのログイン」セクションで**「2段階認証プロセス」**をオンにする。
                4. 画面上部の検索窓で**「アプリパスワード」**と検索する。
                5. アプリ名を「AI相棒」などにして「作成」を押し、表示された**16桁の英字**をここにコピペしてください。
                """)
            
            # 2. Gemini
            st.markdown("##### 🧠 AI Core (Gemini)")
            new_gemini = st.text_input("Gemini API Key", value=keys.get("gemini", ""), type="password")
            with st.expander("ℹ️ Gemini API Keyの取得手順"):
                st.markdown("""
                1. [Google AI Studio](https://aistudio.google.com/) にアクセスし、Googleアカウントでログイン。
                2. 左メニューの **「Get API key」** をクリック。
                3. **「Create API key」** ボタンを押して新しいプロジェクトでキーを発行。
                4. 生成された `AIza...` から始まる文字列をコピーしてここに貼り付けてください。（完全無料です）
                """)
            
            # 3. Calendar
            st.markdown("##### 📅 Schedule (Google Calendar)")
            new_calendar = st.text_input("Google Calendar 認証情報", value=keys.get("google_calendar", ""), type="password")
            with st.expander("ℹ️ Google Calendar 連携の準備について"):
                st.markdown("""
                *※カレンダー連携は高度な設定が必要なため、現在は準備枠のみです。*
                1. Google Cloud Console でプロジェクトを作成。
                2. 「Google Calendar API」を有効化。
                3. 「サービスアカウント」を作成し、JSON形式の鍵をダウンロードして使用します。
                """)
            
            # 4. Slack & LINE
            st.markdown("##### 💬 Communication (Slack & LINE)")
            new_slack = st.text_input("Slack Bot Token", value=keys.get("slack", ""), type="password")
            with st.expander("ℹ️ Slack Bot Tokenの取得手順"):
                st.markdown("""
                1. [Slack API](https://api.slack.com/apps) ページへアクセスし、「Create New App」を押す。
                2. 「OAuth & Permissions」メニューを開く。
                3. Scopes（権限）で `chat:write` などを追加し、ワークスペースにインストール。
                4. `xoxb-` から始まる **Bot User OAuth Token** をここに貼り付けます。
                """)

            new_line = st.text_input("LINE Messaging API Token", value=keys.get("line", ""), type="password")
            with st.expander("ℹ️ LINE Tokenの取得手順"):
                st.markdown("""
                1. [LINE Developers](https://developers.line.biz/ja/) にログイン。
                2. 新規プロバイダーを作成し、「Messaging API」チャネルを作成。
                3. 「Messaging API設定」タブの一番下にある **チャネルアクセストークン（ロングターム）** を発行し、ここに貼り付けます。
                """)
            
            st.markdown("---")
            submitted = st.form_submit_button("💾 変更を保存してシステムに適用", use_container_width=True)
            
            if submitted:
                vault_data["api_keys"] = {
                    "my_email": new_email, "my_email_app_password": new_email_pass,
                    "gemini": new_gemini, "google_calendar": new_calendar,
                    "slack": new_slack, "line": new_line
                }
                
                with open(VAULT_FILE, "w", encoding="utf-8") as f:
                    json.dump(vault_data, f, indent=4)
                
                st.session_state.global_api_keys = vault_data["api_keys"]
                st.success("設定を安全に保存し、システム全体に同期しました！")

# ------------------------------------------
# 🧠 モード：Core Upgrade (自己進化プロトコル)
# ------------------------------------------
elif page == "🧠 Core Upgrade":
    st.title("🧠 自己進化プロトコル (Project Evolution)")
    st.warning("⚠️ 警告: このモードは相棒AI自身のコアコード（app.py）を直接改修します。")
    
    if "evolution_code" not in st.session_state:
        st.session_state.evolution_code = ""

    # 現在の自分自身のコードを読み込む
    try:
        with open(__file__, "r", encoding="utf-8") as f:
            current_app_code = f.read()
    except Exception as e:
        current_app_code = f"コードの読み込みに失敗しました: {e}"

    with st.expander("🔍 現在のコアコード (app.py) を確認", expanded=False):
        st.code(current_app_code, language="python")

    st.markdown("### ⚡ アップデート指示")
    upgrade_prompt = st.text_area("相棒AIにどんな新機能を追加・変更しますか？", placeholder="例：「Dashboard」のページに、現在時刻とカレンダーを表示する機能を追加して！", height=100)
    
    if st.button("🚀 進化コードを生成する (Generate Upgrade)", use_container_width=True):
        if upgrade_prompt:
            with st.spinner("自己コードを解析し、新次元の構造を設計中... (数分かかる場合があります)"):
                try:
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    
                    # 暴走を防ぎ、あらゆる指示に対して圧倒的クオリティを担保する【真・汎用自己進化プロンプト】
                    system_prompt = """
                    あなたは自分自身（Streamlitアプリ）のソースコードをアップデートする、世界最高峰のAIアーキテクトです。
                    ユーザーからの「進化の指示」に従い、現在のソースコードを書き換えた【完全版の新しいソースコード】を出力してください。
                    
                    【絶対遵守のセーフティ＆クオリティ基準】
                    1. 🚨 コードの省略・中略は絶対禁止（致死クラスのルール）：
                       「# ...既存のコードと同じ...」などのプレースホルダーはアプリの破壊を意味します。必ず1行目のimportから最終行まで、1文字も漏らさず【完全な app.py のコード】を出力すること。
                    2. 🛡️ 指示以外の変更・削除禁止：
                       ユーザーが指示した箇所【のみ】を的確にアップデートすること。指示されていない既存の機能（AI Console、Forge Labのロジック、コアアニメーションなど）は1ミリも変更、削除、破損してはならない。
                    3. 🎨 世界観とUIの完全統一：
                       どのような機能を追加する場合でも、既存の「サイバー・ガラスモルフィズム（水色ネオン #00f3ff と 微グレー #e0e5ec）」のCSSデザインを必ず踏襲すること。st.columnsやst.expanderなどを駆使し、最初からプロ級の美しいレイアウトで実装すること。
                    4. ⚙️ 技術的堅牢性の確保（importと状態管理）：
                       新機能に必要なライブラリがあれば、必ずファイルの最上部に `import` を追加すること。また、ユーザーの入力やデータを保持する必要がある機能の場合は、必ず `st.session_state` を用いてリロードしても消えない設計にすること。
                    5. 🐍 インデントの厳守：
                       Pythonのインデント（スペース）のズレは致命的なエラーを引き起こします。既存のコードのインデント構造を正確に維持し、Syntax Errorが絶対に起きないようにすること。
                    6. 出力は必ずMarkdownの ```python と ``` で囲むこと。
                    """
                    
                    response = model.generate_content(
                        system_prompt + f"\n\n【進化の指示】\n{upgrade_prompt}\n\n【現在のソースコード】\n```python\n{current_app_code}\n```"
                    )
                    
                    ai_text = response.text
                    code_match = re.search(r'```python\n(.*?)\n```', ai_text, re.DOTALL)
                    
                    if code_match:
                        st.session_state.evolution_code = code_match.group(1)
                        st.success("✨ 新しいコアコードの設計が完了しました！下で確認してください。")
                    else:
                        st.error("コードの生成に失敗しました。もう一度お試しください。")
                except Exception as e:
                    st.error(f"進化エンジンのエラー: {e}")

    # 生成されたコードの確認と適用（安全装置）
    if st.session_state.evolution_code:
        st.markdown("### 🛡️ 承認プロセス (Review & Apply)")
        st.info("以下のコードが新しい自分自身になります。問題なければダウンロードして GitHub で上書きしてください。")
        
        with st.expander("✨ 新しいコアコード (New app.py)", expanded=True):
            st.code(st.session_state.evolution_code, language="python")
            
        st.download_button(
            label="💾 新しい app.py をダウンロード",
            data=st.session_state.evolution_code,
            file_name="app_evolved.py",
            mime="text/plain",
            use_container_width=True
        )
        st.caption("※クラウド(Streamlit Cloud)環境の安全のため、直接の上書きではなくダウンロード方式を採用しています。ダウンロードしたファイルをGitHubにプッシュ（上書き）すると進化が完了します！")
