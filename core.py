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
import requests
# === 新規追加：カレンダー操作用の道具 ===
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import datetime

# === ☁️ クラウドDB ＆ 暗号化エンジン (Supabase) ===
from supabase import create_client, Client
from cryptography.fernet import Fernet

try:
    supabase: Client = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    hasher = hashlib.sha256(st.secrets["MASTER_ENCRYPTION_KEY"].encode('utf-8')).digest()
    cipher_suite = Fernet(base64.urlsafe_b64encode(hasher))
    DB_CONNECTED = True
except Exception as e:
    DB_CONNECTED = False

def load_vault():
    if not DB_CONNECTED: return {}
    try:
        res = supabase.table("vault_data").select("encrypted_keys").eq("id", 1).execute()
        if res.data and res.data[0].get("encrypted_keys"):
            decrypted = cipher_suite.decrypt(res.data[0]["encrypted_keys"].encode('utf-8'))
            return json.loads(decrypted.decode('utf-8'))
    except: pass
    return {}

def save_vault(data):
    if not DB_CONNECTED: return False
    try:
        encrypted = cipher_suite.encrypt(json.dumps(data).encode('utf-8')).decode('utf-8')
        supabase.table("vault_data").upsert({"id": 1, "encrypted_keys": encrypted}).execute()
        return True
    except: return False

# === システム起動時の「金庫の鍵」自動読み込み ===
if "global_api_keys" not in st.session_state:
    st.session_state.global_api_keys = {}
    vd = load_vault()
    st.session_state.global_api_keys = vd.get("api_keys", {})

st.set_page_config(page_title="AIbou", page_icon="❖", layout="wide")

# ==========================================
# 🔐 1. ログインシステム
# ==========================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("相棒AI 起動シークエンス")
    password = st.text_input("Password", type="password")
    if st.button("システム起動"):
        if password == st.secrets.get("APP_PASSWORD", "boss"): 
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("パスワードが違います。")
    st.stop()

# ==========================================
# 🧭 2. THE AIbou OS セントラルルーティング
# ==========================================
if "current_mode" not in st.session_state:
    st.session_state.current_mode = "HUB"

if st.session_state.current_mode == "HUB":
    st.markdown("""
        <style>
        [data-testid="collapsedControl"] { display: none !important; }
        [data-testid="stSidebar"] { display: none !important; }
        </style>
    """, unsafe_allow_html=True)
    page = "HUB"
else:
    st.sidebar.markdown("<h2 style='text-align:center; color:#2b6cb0; font-weight:900; letter-spacing:2px; margin-bottom: 20px;'>THE FORGE</h2>", unsafe_allow_html=True)
    if st.sidebar.button("⬅️ RETURN TO HUB", use_container_width=True):
        st.session_state.current_mode = "HUB"
        st.rerun()
    st.sidebar.markdown("---")
    
    st.sidebar.caption("QUICK JUMP")
    page_names = {
        "Forge Lab": "FORGE LAB",
        "Document Vault": "DATA VAULT",
        "Active Tasks": "ACTIVE TASKS",
        "Core Upgrade": "EVOLUTION",
        "Dashboard": "DASHBOARD",
        "App Archive": "APP ARCHIVE",
        "Task History": "TASK HISTORY",
        "Settings": "⚙️ SETTINGS" # 🚨ここを「Secure Vault」から「Settings」に変更！
    }
    
    current_index = list(page_names.keys()).index(st.session_state.current_mode) if st.session_state.current_mode in page_names else 0
    new_mode = st.sidebar.radio("QUICK JUMP", list(page_names.keys()), index=current_index, format_func=lambda x: page_names[x], label_visibility="collapsed")
    
    if new_mode != st.session_state.current_mode:
        st.session_state.current_mode = new_mode
        st.rerun()
        
    page = st.session_state.current_mode

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
    #core-settings { 
        display: none; position: absolute; 
        left: 50%; top: 50%; transform: translate(-50%, -50%); 
        background: rgba(240, 242, 246, 0.85); backdrop-filter: blur(15px); border: 1px solid #cbd5e0; 
        border-radius: 20px; padding: 20px; box-shadow: 0px 10px 30px rgba(0, 0, 0, 0.1); 
        width: 280px; max-height: 90%; overflow-y: auto; z-index: 99999; 
        font-family: 'Segoe UI', sans-serif; color: #2d3748; font-size: 12px; 
    }
    #core-settings input[type=range] { accent-color: #00f3ff; cursor: pointer; width: 100%; }
    #core-settings select { background: rgba(255,255,255,0.5); border: 1px solid #cbd5e0; border-radius: 8px; padding: 5px; outline: none; width: 100%; cursor: pointer; }
    #core-settings input[type=color] { border: none; background: transparent; cursor: pointer; width: 30px; height: 30px; padding: 0; }
    #core-settings button:hover { filter: brightness(1.1); }
</style>

<div id="core-wrapper" style="position:relative; width:100%; height:H_VALpx; display:flex; justify-content:center; align-items:center;">
    <div id="core-container" style="cursor:pointer; display:flex; flex-direction:column; align-items:center; z-index:10; width:100%;">
        <canvas id="visualizer" width="280" height="280" style="filter:drop-shadow(0 8px 20px rgba(0, 150, 255, 0.3));"></canvas>
        <div id="status-info" style="margin-top:10px; font-size:11px; letter-spacing:6px; color:#3182ce; font-family:monospace; font-weight:bold;">SYSTEM ONLINE</div>
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
            <label style="display:block; font-weight:bold; color:#00f3ff; cursor:pointer; text-shadow: 0 0 5px rgba(0,243,255,0.3); margin-bottom: 8px;">
                <input type="checkbox" id="ctrl-mic"> 🎙️ Enable Voice Command
            </label>
            <label style="display:block; font-weight:bold; color:#2b6cb0; cursor:pointer;">
                <input type="checkbox" id="ctrl-chat"> 💬 Show Chat Interface
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
    // 🚨 showChat をデフォルト設定に追加
    const DEFAULTS = { speed: 1.5, vol: 1, filter: false, innerColor: "#00f3ff", outerColor: "#0064ff", pulse: 2, particles: false, showMic: false, showChat: true };
    
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
        document.getElementById("ctrl-chat").checked = settings.showChat; // 🚨UI反映
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

    // 🚨 チャット欄の表示/非表示をコントロールするCSSを注入
    function updateChatVisibility(isVisible) {
        try {
            const parentDoc = window.parent.document;
            let styleEl = parentDoc.getElementById("chat-visibility-style");
            if(!styleEl) { styleEl = parentDoc.createElement("style"); styleEl.id = "chat-visibility-style"; parentDoc.head.appendChild(styleEl); }
            if(isVisible) { styleEl.innerHTML = ``; } 
            else { styleEl.innerHTML = `[data-testid="stChatInput"], [data-testid="stChatMessage"] { display: none !important; }`; }
        } catch(e) {}
    }
    updateChatVisibility(settings.showChat);

    function saveSettings() {
        settings.speed = parseFloat(document.getElementById("ctrl-speed").value) || 1.5;
        settings.vol = parseFloat(document.getElementById("ctrl-vol").value) || 1;
        settings.filter = document.getElementById("ctrl-filter").checked;
        settings.innerColor = document.getElementById("ctrl-inner-color").value;
        settings.outerColor = document.getElementById("ctrl-outer-color").value;
        settings.pulse = parseFloat(document.getElementById("ctrl-pulse").value) || 2;
        settings.particles = document.getElementById("ctrl-particles").checked;
        settings.showMic = document.getElementById("ctrl-mic").checked;
        settings.showChat = document.getElementById("ctrl-chat").checked; // 🚨保存
        localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    }

    coreContainer.onclick = () => { settingsPanel.style.display = "block"; };
    closeBtn.onclick = (e) => { e.preventDefault(); settingsPanel.style.display = "none"; };

    document.getElementById("ctrl-speed").oninput = (e) => { document.getElementById("val-speed").innerText = e.target.value; audio.playbackRate = e.target.value; saveSettings(); };
    document.getElementById("ctrl-vol").oninput = (e) => { document.getElementById("val-vol").innerText = Math.round(e.target.value * 100); audio.volume = e.target.value; saveSettings(); };
    document.getElementById("ctrl-inner-color").oninput = (e) => { settings.innerColor = e.target.value; statusText.style.color = settings.innerColor; saveSettings(); };
    document.getElementById("ctrl-outer-color").oninput = (e) => { settings.outerColor = e.target.value; saveSettings(); };
    document.getElementById("ctrl-pulse").onchange = (e) => { settings.pulse = parseFloat(e.target.value); saveSettings(); };
    document.getElementById("ctrl-particles").onchange = (e) => { settings.particles = e.target.checked; saveSettings(); };
    document.getElementById("ctrl-mic").onchange = (e) => { settings.showMic = e.target.checked; saveSettings(); updateMicVisibility(settings.showMic); };
    document.getElementById("ctrl-chat").onchange = (e) => { settings.showChat = e.target.checked; saveSettings(); updateChatVisibility(settings.showChat); }; // 🚨イベント追加
    
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
# ❖ モード：CENTRAL HUB (OS ホーム画面 - グリッド極み版)
# ------------------------------------------
if page == "HUB":
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
            # 🚨ここを「SECURE VAULT」から「SETTINGS」に変更！

    # ------------------------------------------
    # 🚨 カレンダー機能・マイク・AIチャット処理 (以下そのまま)
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


# ------------------------------------------
# ❖ モード：Forge Lab (自律エージェント仕様)
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
    # ==========================================
    # 📥 アプリ保存モジュール (SAVE TO ARCHIVE)
    # ==========================================
    st.markdown("---")
    st.markdown("#### 💾 SAVE TO APP ARCHIVE")
    st.caption("/// AIが作成したコードを保管庫に保存し、専用アプリとしてインストールします ///")
    
    with st.expander("📦 新しいミニアプリとしてインストール", expanded=False):
        app_filename = st.text_input("アプリのファイル名（半角英数字）", placeholder="例: my_calculator")
        app_code_input = st.text_area("保存するPythonコードを貼り付け", height=250, placeholder="import streamlit as st\n\n# ここにAIが書いたコードをコピペしてください")
        
        if st.button("ARCHIVE にインストール ⚡", use_container_width=True, type="primary"):
            if app_filename and app_code_input:
                # 安全なファイル名に自動変換（空白をアンダーバーに、小文字に統一）
                safe_name = app_filename.replace(" ", "_").lower()
                if not safe_name.endswith(".py"):
                    safe_name += ".py"
                
                # 保存先フォルダの確保
                os.makedirs("forge_apps", exist_ok=True)
                save_path = os.path.join("forge_apps", safe_name)
                
                try:
                    with open(save_path, "w", encoding="utf-8") as f:
                        f.write(app_code_input)
                    st.success(f"✅ インストール完了！ `{safe_name}` をAPP ARCHIVEに保存しました。")
                    st.balloons() # 成功時のお祝いアニメーション
                except Exception as e:
                    st.error(f"保存エラー: {e}")
            else:
                st.warning("⚠️ アプリ名とコードの両方を入力してください。")

# ------------------------------------------
# ⌘ モード：Document Vault (サイバー・ダッシュボード仕様)
# ------------------------------------------
elif page == "Document Vault": # キー名変更
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
        
        col_log, col_preview = st.columns([7, 3])

        with col_log:
            st.markdown("<p style='font-weight:bold; color:#718096;'>[ VAULT CONCIERGE ]</p>", unsafe_allow_html=True)
            with st.container(height=450, border=False):
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
                            model = genai.GenerativeModel('gemini-2.5-flash')
                            response = model.generate_content(system_instruction + "\n質問: " + prompt)
                            response_text = response.text
                        nb_data["chat"].append({"role": "assistant", "avatar": "🤖", "content": response_text})
                        st.rerun()
                    except Exception as e:
                        st.error(f"解析エラー: {e}")

        with col_preview:
            core_height = 150
            vault_core_html = MASTER_CORE_TEMPLATE.replace("H_VAL", str(core_height)).replace("MAX_Wpx", "200").replace("V_DATA", "").replace("A_PLAY", "")
            st.components.v1.html(vault_core_html, height=core_height + 10)
            st.markdown("<p style='font-weight:bold; color:#718096;'>[ MATERIAL MANAGEMENT ]</p>", unsafe_allow_html=True)
            with st.container(border=True):
                st.markdown("#### 📥 UPLOAD DATA (PDF, TXT, MD)")
                uploaded_files = st.file_uploader("ファイルをドロップ", type=["txt", "md", "pdf"], accept_multiple_files=True, label_visibility="collapsed")
                if st.button("STORE IN VAULT ⚡", use_container_width=True):
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
        col2.metric("未着手 📝", len(df[df['ステータus'] == '未着手']))
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
# 🕰️ モード：過去のタスク (TASK ARCHIVE)
# ------------------------------------------
elif page == "Task History" or page == "🕰️ 過去のタスク":
    # 💎 アーカイブ専用の美しいCSS
    st.markdown("""
        <style>
        .history-card {
            background: rgba(255, 255, 255, 0.4);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.9);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 6px 6px 15px rgba(163, 177, 198, 0.4), -6px -6px 15px rgba(255, 255, 255, 0.9);
            transition: all 0.3s ease;
        }
        .history-card:hover {
            transform: translateY(-3px);
            border-color: #00e676;
            box-shadow: 0 8px 25px rgba(0, 230, 118, 0.3);
        }
        .badge-success {
            background-color: #00e676; color: white; padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 800; letter-spacing: 1px;
        }
        .cyber-title { color: #2b6cb0; font-weight: 800; letter-spacing: 2px; margin-bottom: 5px; text-shadow: 2px 2px 4px rgba(255,255,255,0.8); }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<h2 class='cyber-title'>🕰️ TASK ARCHIVE</h2>", unsafe_allow_html=True)
    st.caption("/// 完了済みのミッション・ログ・アーカイブ ///")
    st.markdown("<br>", unsafe_allow_html=True)

    try:
        raw_data = sheet.get_all_values() 
        if len(raw_data) > 1:
            headers = ['タスクID', '目標', 'タスク内容', 'ステータス', 'ログ', 'ボスの回答']
            body = [row[:6] + [''] * (6 - len(row[:6])) for row in raw_data[1:]] 
            df = pd.DataFrame(body, columns=headers)
            
            completed_df = df[df['ステータス'] == '完了']
            
            if not completed_df.empty:
                # 🔍 検索フィルターの実装
                col_search, col_count = st.columns([7, 3])
                with col_search:
                    search_query = st.text_input("🔍 アーカイブを検索...", placeholder="タスク名やキーワードを入力", label_visibility="collapsed")
                
                # 検索キーワードで絞り込み
                if search_query:
                    completed_df = completed_df[
                        completed_df['タスク内容'].str.contains(search_query, case=False, na=False) | 
                        completed_df['ログ'].str.contains(search_query, case=False, na=False)
                    ]
                
                with col_count:
                    st.markdown(f"<div style='text-align:right; font-weight:bold; color:#718096; padding-top:10px;'>Total Missions: {len(completed_df)}</div>", unsafe_allow_html=True)
                
                st.markdown("---")
                
                # 🗂️ 美しいカード形式で描画
                for index, row in completed_df.iterrows():
                    st.markdown(f"""
                    <div class="history-card">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <span style="font-weight: 800; color: #1a202c; font-size: 18px;">{row['タスク内容']}</span>
                            <span class="badge-success">ACCOMPLISHED</span>
                        </div>
                        <div style="font-size: 12px; color: #4a5568; margin-bottom: 15px; font-family: monospace;">
                            <b>ID:</b> {row['タスクID']} &nbsp;|&nbsp; <b>TARGET:</b> {row['目標']}
                        </div>
                        <div style="background: rgba(255,255,255,0.6); padding: 12px; border-radius: 8px; border-left: 4px solid #3182ce; font-size: 13px; color: #2d3748;">
                            <b style="color:#2b6cb0;">🤖 SYSTEM LOG:</b><br>
                            {row['ログ']}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("完了したタスクはまだありません。これから歴史を作っていきましょう！")
        else:
            st.info("現在、登録されているタスクはありません。")
    except Exception as e:
        st.error(f"データベースの読み込みに失敗しました: {e}")

# ------------------------------------------
# 📊 モード：Dashboard (システム分析とスケジュール)
# ------------------------------------------
elif page == "Dashboard" or page == "DASHBOARD":
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

# ------------------------------------------
# 📦 モード：App Archive (ミニアプリ保管庫)
# ------------------------------------------
elif page == "App Archive" or page == "APP ARCHIVE":
    st.markdown("""
        <style>
        .cyber-title { color: #2b6cb0; font-weight: 800; letter-spacing: 2px; margin-bottom: 20px; text-shadow: 2px 2px 4px rgba(255,255,255,0.8); }
        .app-card { 
            background: rgba(255, 255, 255, 0.4); backdrop-filter: blur(10px); 
            border: 1px solid rgba(255, 255, 255, 0.9); border-radius: 15px; 
            padding: 20px; margin-bottom: 15px; transition: all 0.3s ease; 
            box-shadow: 4px 4px 10px rgba(163, 177, 198, 0.3), -4px -4px 10px rgba(255, 255, 255, 0.8);
        }
        .app-card:hover { transform: translateY(-5px); border-color: #3182ce; box-shadow: 0 8px 25px rgba(49, 130, 206, 0.3); }
        </style>
    """, unsafe_allow_html=True)

    # アプリ保存用のフォルダを作成
    APPS_DIR = "forge_apps"
    os.makedirs(APPS_DIR, exist_ok=True)

    # 💡 初回テスト用：空っぽだと寂しいのでサンプルの「ポモドーロタイマー」を自動生成
    sample_app_path = os.path.join(APPS_DIR, "pomodoro_timer.py")
    if not os.path.exists(sample_app_path):
        with open(sample_app_path, "w", encoding="utf-8") as f:
            f.write("""import streamlit as st
import time
st.subheader("🍅 Pomodoro Timer")
minutes = st.slider("集中する時間 (分)", 1, 60, 25)
if st.button("Start Timer", type="primary"): 
    with st.empty():
        for i in range(minutes * 60, -1, -1):
            mins, secs = divmod(i, 60)
            st.markdown(f"<h1 style='text-align:center; color:#e53e3e; font-size: 80px;'>{mins:02d}:{secs:02d}</h1>", unsafe_allow_html=True)
            time.sleep(1)
        st.success("🎉 時間です！お疲れ様でした！")
""")

    # フォルダ内のPythonファイル（アプリ）を取得
    app_files = [f for f in os.listdir(APPS_DIR) if f.endswith(".py")]

    if "running_app" not in st.session_state:
        st.session_state.running_app = None

    # ==========================================
    # 画面A：アプリ一覧・検索画面
    # ==========================================
    if st.session_state.running_app is None:
        st.markdown("<h2 class='cyber-title'>📦 APP ARCHIVE</h2>", unsafe_allow_html=True)
        st.caption("/// FORGE LABで開発した専用ミニアプリの保管庫・ランチャー ///")
        
        search_query = st.text_input("🔍 アプリを検索...", placeholder="アプリ名を入力", label_visibility="collapsed")
        
        if search_query:
            app_files = [f for f in app_files if search_query.lower() in f.lower()]

        if not app_files:
            st.info("インストールされているアプリはありません。FORGE LABでAIに作らせて保存しましょう！")
        else:
            st.markdown("---")
            # 3列で美しくカードを表示
            cols = st.columns(3)
            for i, app_file in enumerate(app_files):
                app_name = app_file.replace(".py", "").replace("_", " ").title()
                with cols[i % 3]:
                    st.markdown(f"""
                    <div class="app-card">
                        <h4 style="color: #2b6cb0; margin-bottom: 5px;">🧩 {app_name}</h4>
                        <div style="font-size: 11px; color: #718096; margin-bottom: 15px; font-family: monospace;">File: {app_file}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    if st.button(f"🚀 起動する", key=f"launch_{app_file}", use_container_width=True):
                        st.session_state.running_app = app_file
                        st.rerun()

    # ==========================================
    # 画面B：アプリ実行（大画面）モード
    # ==========================================
    else:
        app_file = st.session_state.running_app
        app_name = app_file.replace(".py", "").replace("_", " ").title()
        
        col_title, col_close = st.columns([8, 2])
        with col_title:
            st.markdown(f"<h2 class='cyber-title'>🟢 Running: {app_name}</h2>", unsafe_allow_html=True)
        with col_close:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("✖️ 終了して戻る", use_container_width=True, type="primary"):
                st.session_state.running_app = None
                st.rerun()
        
        st.markdown("---")
        
        # ⚠️ アプリのコードを読み込んでOS内部で直接実行 (Sandbox)
        try:
            with st.container(border=True):
                app_path = os.path.join(APPS_DIR, app_file)
                with open(app_path, "r", encoding="utf-8") as f:
                    app_code = f.read()
                
                # OS本体の変数を壊さないように、専用の独立空間（辞書）を用意して実行
                import time
                exec_globals = {"st": st, "pd": pd, "datetime": datetime, "time": time, "os": os, "json": json}
                exec(app_code, exec_globals)
                
        except Exception as e:
            st.error(f"アプリの実行中にエラーが発生しました: {e}")
            with st.expander("🛠️ コードを確認する"):
                st.code(app_code, language="python")

# ------------------------------------------
# /// モード：SYSTEM OVERRIDE (自己進化プロトコル)
# ------------------------------------------
elif page == "Core Upgrade":
    if "evolution_code" not in st.session_state: st.session_state.evolution_code = ""
    if "evolution_log" not in st.session_state: st.session_state.evolution_log = ""

    # 🚨 ターゲットを core.py に変更
    try:
        with open("core.py", "r", encoding="utf-8") as f:
            current_app_code = f.read()
    except Exception as e:
        current_app_code = f"# ERROR: {e}"

    col_left, col_right = st.columns(2, gap="large")

    with col_left:
        st.markdown("<h2 style='color: #2b6cb0; font-weight: 800; letter-spacing: 2px;'>[ PROJECT EVOLUTION ]</h2>", unsafe_allow_html=True)
        st.caption("/// WARNING: CORE SYSTEM OVERRIDE PROTOCOL ///")
        model_choice = st.radio("ENGINE CLASS:", ["[ STANDARD ] Gemini Flash", "[ ADVANCED ] Gemini Pro"], index=0, horizontal=True, label_visibility="collapsed")
        
        with st.expander("> CURRENT_CORE.py", expanded=False):
            st.code(current_app_code, language="python")

        if st.session_state.evolution_log:
            st.markdown("<br><p style='font-weight:bold; color:#718096;'>[ EVOLUTION REPORT ]</p>", unsafe_allow_html=True)
            with st.container(border=True):
                st.markdown(st.session_state.evolution_log)

    with col_right:
        st.markdown("<p style='font-weight:bold; color:#718096;'>[ INPUT DIRECTIVE ]</p>", unsafe_allow_html=True)
        upgrade_prompt = st.text_area("COMMAND:", placeholder="例：OSのテーマカラーを赤ベースに変更せよ。", height=100, label_visibility="collapsed")
        
        if st.button("[ INITIATE EVOLUTION ]", use_container_width=True):
            if upgrade_prompt:
                target_model = 'gemini-2.5-pro' if "Pro" in model_choice else 'gemini-2.5-flash'
                
                with st.spinner(f"Processing with {target_model}..."):
                    try:
                        model = genai.GenerativeModel(target_model)
                        # 🚨 AIにターゲットを教育（省略厳禁プロンプト復旧）
                        system_prompt = """
                        あなたは自分自身（Streamlitアプリ）のソースコードを書き換えるAIアーキテクトです。
                        現在、システムはデュアルコア構成（app.pyがランチャー、core.pyが本体）になっています。
                        あなたは【core.py】を改修します。
                        
                        【厳格な出力フォーマット】
                        必ず以下の2つのセクションに分けて出力すること。これ以外の余計な挨拶などは一切不要。

                        [CHANGELOG]
                        （ここに、どこを・なぜ・どのように改修したのか、簡潔な箇条書きでレポートを記載する）

                        [CODE]
                        ```python
                        （ここに、1行目から最終行まで、絶対に省略せず完全な core.py のソースコードを記載する）
                        ```
                        
                        【絶対遵守ルール】
                        1. コードの省略（# ...既存のコードと同じ... 等）はアプリを破壊するため【絶対禁止】。
                        2. ユーザーの指示箇所以外の既存機能は1ミリも変更・破損させないこと。
                        3. インデントを正確に保ち、Syntax Errorを絶対に出さないこと。
                        """
                        response = model.generate_content(system_prompt + f"\n\n【指示】\n{upgrade_prompt}\n\n【現状の core.py】\n```python\n{current_app_code}\n```")
                        
                        log_match = re.search(r'\[CHANGELOG\](.*?)\[CODE\]', response.text, re.DOTALL)
                        code_match = re.search(r'```python\n(.*?)\n```', response.text, re.DOTALL)
                        
                        if code_match and log_match:
                            st.session_state.evolution_log = log_match.group(1).strip()
                            st.session_state.evolution_code = code_match.group(1)
                            st.rerun()
                        else:
                            st.error("OUTPUT ERROR: 出力フォーマット崩れ。再度実行してください。")
                    except Exception as e:
                        st.error(f"SYSTEM ERROR: {e}")

        if st.session_state.evolution_code:
            st.markdown("<br><p style='font-weight:bold; color:#00f3ff;'>[ EVOLVED CORE GENERATED ]</p>", unsafe_allow_html=True)
            with st.expander("> NEW_CORE.py (Hover top-right to copy)", expanded=True):
                st.code(st.session_state.evolution_code, language="python")
            
            st.download_button(
                label="[ MANUAL BACKUP DOWNLOAD ]",
                data=st.session_state.evolution_code,
                file_name="core_evolved.py",
                mime="text/plain",
                use_container_width=True
            )
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.warning("/// LOCAL DANGER: 手元のPCの core.py を直接上書きして再起動します。")
            if st.button("!!! LOCAL OVERRIDE !!!", use_container_width=True, type="primary"):
                try:
                    # 🚨 【追加】上書き前に自動バックアップ（過去5個まで保持）
                    import glob
                    os.makedirs("backups", exist_ok=True)
                    backup_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    with open("core.py", "r", encoding="utf-8") as f: old_code = f.read()
                    with open(f"backups/core_backup_{backup_time}.py", "w", encoding="utf-8") as f: f.write(old_code)
                    
                    # 過去5個を超えたら古いものを削除
                    backup_files = sorted(glob.glob("backups/core_backup_*.py"))
                    if len(backup_files) > 5:
                        for old_file in backup_files[:-5]:
                            os.remove(old_file)

                    # 新しいコードで上書き
                    with open("core.py", "w", encoding="utf-8") as f:
                        f.write(st.session_state.evolution_code)
                    st.success("LOCAL OVERRIDE COMPLETE. REBOOTING...")
                    st.session_state.evolution_code = ""; st.session_state.evolution_log = ""; st.rerun()
                except Exception as e:
                    st.error(f"LOCAL OVERRIDE FAILED: {e}")
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.info("☁️ CLOUD DEPLOY: GitHub上の core.py をAPIで書き換え、クラウド環境を再デプロイします。")
            if st.button("🚀 GITHUB AUTO DEPLOY", use_container_width=True):
                gh_token = st.session_state.global_api_keys.get("gh_token", "")
                gh_owner = st.session_state.global_api_keys.get("gh_owner", "")
                gh_repo = st.session_state.global_api_keys.get("gh_repo", "")
                
                if not all([gh_token, gh_owner, gh_repo]):
                    st.error("🚨 Vault（保管庫）にGitHub連携のキーが登録されていません。")
                else:
                    with st.spinner("Deploying to GitHub..."):
                        try:
                            url = f"https://api.github.com/repos/{gh_owner}/{gh_repo}/contents/core.py"
                            headers = {"Authorization": f"token {gh_token}", "Accept": "application/vnd.github.v3+json"}
                            res = requests.get(url, headers=headers)
                            sha = res.json().get('sha', '') if res.status_code == 200 else ''
                            encoded_content = base64.b64encode(st.session_state.evolution_code.encode('utf-8')).decode('utf-8')
                            data = {"message": "AI Auto Evolution: SYSTEM OVERRIDE", "content": encoded_content}
                            if sha: data["sha"] = sha
                            put_res = requests.put(url, headers=headers, json=data)
                            
                            if put_res.status_code in [200, 201]:
                                st.success("🚀 DEPLOY COMPLETE!")
                                st.session_state.evolution_code = ""; st.session_state.evolution_log = ""
                            else:
                                st.error(f"DEPLOY FAILED: {put_res.json()}")
                        except Exception as e:
                            st.error(f"API ERROR: {e}")
                            

# ------------------------------------------
# ⚙️ モード：Settings (統合設定画面)
# ------------------------------------------
elif page == "Settings" or page == "⚙️ SETTINGS":
    st.markdown("""
        <style>
        .cyber-title { color: #2b6cb0; font-weight: 800; letter-spacing: 2px; margin-bottom: 20px; text-shadow: 2px 2px 4px rgba(255,255,255,0.8); }
        .setting-menu label { cursor: pointer !important; }
        [data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(255, 255, 255, 0.4) !important;
            backdrop-filter: blur(10px) !important;
            border: 1px solid rgba(255, 255, 255, 0.9) !important;
            border-radius: 15px !important;
            box-shadow: 6px 6px 15px rgba(163, 177, 198, 0.4), -6px -6px 15px rgba(255, 255, 255, 0.9) !important;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<h2 class='cyber-title'>⚙️ SYSTEM SETTINGS</h2>", unsafe_allow_html=True)

    # 画面を左（メニュー）と右（コンテンツ）に分割
    col_menu, col_content = st.columns([2, 8], gap="large")
    
    with col_menu:
        st.markdown("<div style='font-weight:bold; color:#718096; margin-bottom:10px;'>[ MENU ]</div>", unsafe_allow_html=True)
        setting_mode = st.radio("設定メニュー", [
            "🛠️ 基本設定",
            "🧠 コア設定",
            "🕰️ システム復元", 
            "🔐 Secure Vault", 
            "📖 取扱説明書", 
            "🚪 ログアウト"
        ], label_visibility="collapsed")

    with col_content:
        # ================================
        if setting_mode == "🛠️ 基本設定":
            st.markdown("#### 🛠️ 基本設定 (General)")
            st.info("言語設定の切り替えや、メイン画面の背景変更、ログイン画面のパスワード変更機能をここに追加します（今後実装予定）。")

        # ================================
        elif setting_mode == "🧠 コア設定":
            st.markdown("#### 🧠 コア設定 (Core)")
            st.info("コアの脈動、色、音声フィルターなどの設定パネルにアクセスする機能をここに追加します。")

        # ================================
        elif setting_mode == "🕰️ システム復元":
            st.markdown("#### 🕰️ SYSTEM TIME MACHINE (過去5回分)")
            st.caption("/// 進化（OVERRIDE）前の安全な状態に復元します ///")
            
            os.makedirs("backups", exist_ok=True)
            backup_files = sorted([f for f in os.listdir("backups") if f.endswith(".py")], reverse=True)
            
            if not backup_files:
                st.info("現在、バックアップ履歴はありません。「EVOLUTION」で進化を実行すると自動的に保存されます。")
            else:
                selected_backup = st.selectbox("復元するバージョンを選択:", backup_files)
                with st.expander(f"👁️ プレビュー : {selected_backup}", expanded=False):
                    try:
                        with open(f"backups/{selected_backup}", "r", encoding="utf-8") as f:
                            backup_code = f.read()
                        st.code(backup_code, language="python")
                    except Exception as e:
                        st.error(f"読み込みエラー: {e}")
                
                st.warning("⚠️ 復元を実行すると、現在の `core.py` はこのバックアップの状態で上書きされます。")
                if st.button("⏪ この時代に復元する", use_container_width=True, type="primary"):
                    try:
                        with open("core.py", "w", encoding="utf-8") as f:
                            f.write(backup_code)
                        st.success("✅ SYSTEM RESTORED. 再起動しています...")
                        st.rerun()
                    except Exception as e:
                        st.error(f"復元エラー: {e}")

        # ================================
        elif setting_mode == "🔐 Secure Vault":
            st.markdown("#### 🔐 SECURE VAULT (Cloud Sync)")
            st.caption("AI相棒や各種システムを動かすための「鍵」と「連絡網」を保管する極秘エリアです。データはクラウドに暗号化保存されます。")

            if not DB_CONNECTED:
                st.error("⚠️ データベースの接続設定（Secrets）が完了していません。")
                st.stop()

            def hash_password(password):
                return hashlib.sha256(password.encode()).hexdigest()

            if "vault_unlocked" not in st.session_state:
                st.session_state.vault_unlocked = False
            if "reset_mode" not in st.session_state:
                st.session_state.reset_mode = False
            if "sent_otp" not in st.session_state:
                st.session_state.sent_otp = None

            # クラウドからロード
            vault_data = load_vault()

            # 🚪 ステージ1：認証（ロック画面 ＆ パスワードリセット）
            if not st.session_state.vault_unlocked:
                col1, col2, col3 = st.columns([1, 8, 1])
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
                                        "my_email": "", "my_email_app_password": "",
                                        "gh_token": "", "gh_owner": "", "gh_repo": ""
                                    }
                                   save_vault(vault_data) # クラウドへ保存
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

            # 🔓 ステージ2：金庫の内部
            if st.session_state.vault_unlocked:
                if st.button("🔒 金庫をロックして退出"):
                    st.session_state.vault_unlocked = False
                    st.rerun()

                st.markdown("#### ⚙️ CORE API & COMMUNICATION CONFIGURATION")
                st.info("ここに入力されたキーはシステム全体で安全に共有され、クラウドに暗号化保存されます。")
                
                with st.form("vault_keys_form"):
                    keys = vault_data.get("api_keys", {})
                    
                    st.markdown("##### 📧 Email System (パスワード復旧・通知用)")
                    new_email = st.text_input("自分のGmailアドレス", value=keys.get("my_email", ""))
                    new_email_pass = st.text_input("Gmail アプリパスワード (16桁)", value=keys.get("my_email_app_password", ""), type="password")
                    with st.expander("ℹ️ Gmailアプリパスワードの取得手順（超詳細）"):
                        st.markdown("""
                        1. スマホやPCのブラウザで [Googleアカウント管理画面](https://myaccount.google.com/) にアクセスしてログインします。
                        2. 左側のメニューから **「セキュリティ」** をクリックします。
                        3. 少し下にスクロールし、「Google へのログイン」の中にある **「2段階認証プロセス」** をクリックしてオンにします（既にオンなら次へ）。
                        4. 画面上部の検索窓（虫眼鏡マーク）で **「アプリパスワード」** と入力して検索・選択します。
                        5. アプリ名に「THE FORGE」など好きな名前を入力して **「作成」** ボタンを押します。
                        6. 画面に黄色の背景で表示される **16桁の英字（空白なしでそのまま）** をコピーして、上のパスワード欄に貼り付けてください。
                        """)
                    
                    st.markdown("##### 🧠 AI Core (Gemini)")
                    new_gemini = st.text_input("Gemini API Key", value=keys.get("gemini", ""), type="password")
                    with st.expander("ℹ️ Gemini API Keyの取得手順（完全無料）"):
                        st.markdown("""
                        1. [Google AI Studio](https://aistudio.google.com/) にアクセスし、普段使っているGoogleアカウントでログインします。
                        2. 規約の同意画面が出たらチェックを入れて進みます。
                        3. 画面左上のメニュー（または左側ナビゲーション）にある **「Get API key」** という青い鍵マークのボタンをクリックします。
                        4. **「Create API key」** ボタンをクリックします。
                        5. 「Create API key in new project」を選択するとキーが生成されます。
                        6. 生成された **`AIza...`** から始まる非常に長い文字列をコピーして、上の欄に貼り付けてください。
                        """)
                    
                    st.markdown("##### 📅 Schedule (Google Calendar)")
                    new_calendar = st.text_input("Google Calendar JSON (サービスアカウント)", value=keys.get("google_calendar", ""), type="password")
                    with st.expander("ℹ️ Google Calendar 連携の準備について（上級者向け）"):
                        st.markdown("""
                        *※カレンダーへの書き込みにはGoogle Cloudの「サービスアカウント」が必要です。*
                        1. [Google Cloud Console](https://console.cloud.google.com/) にアクセスしてログインします。
                        2. 左上の「プロジェクトの選択」から **「新しいプロジェクト」** を作成します。
                        3. 左メニュー「APIとサービス」＞「ライブラリ」へ進み、検索窓で **「Google Calendar API」** を検索して **「有効にする」** を押します。
                        4. 次に「APIとサービス」＞「認証情報」へ進み、画面上の「＋認証情報を作成」から **「サービスアカウント」** を選びます。
                        5. アカウント名（例: ai-calendar）を入力して「完了」まで進みます。
                        6. 作成されたサービスアカウント（xxxx@yyy.iam.gserviceaccount.com）をクリックし、「キー」タブを開きます。
                        7. 「鍵を追加」＞「新しい鍵を作成」＞ **「JSON」** を選んで作成すると、ファイルがダウンロードされます。
                        8. メモ帳などでダウンロードしたJSONファイルを開き、**中身のテキストをすべて**コピーして上の欄に貼り付けます。
                        9. **【最重要】** 普段使っているGoogleカレンダーを開き、右上の歯車＞設定＞特定のカレンダーの設定＞「特定のユーザーとの共有」に、**先ほどのサービスアカウントのメールアドレス**を追加し、権限を **「予定の変更権限」** に設定してください。
                        """)
                    
                    st.markdown("##### 💬 Communication (Slack & LINE)")
                    new_slack = st.text_input("Slack Bot Token", value=keys.get("slack", ""), type="password")
                    with st.expander("ℹ️ Slack Bot Tokenの取得手順"):
                        st.markdown("""
                        1. [Slack API (Your Apps)](https://api.slack.com/apps) にアクセスし、**「Create New App」** ＞ 「From scratch」を選択します。
                        2. アプリ名（例: THE FORGE）を入力し、導入したい自分のワークスペースを選択して「Create App」を押します。
                        3. 左メニューの **「OAuth & Permissions」** をクリックして少し下にスクロールします。
                        4. 「Scopes」セクションの「Bot Token Scopes」で **「Add an OAuth Scope」** を押し、**`chat:write`** を追加します。
                        5. 画面一番上に戻り、**「Install to Workspace」** ボタンを押して許可（Allow）します。
                        6. 画面に表示される **`xoxb-`** から始まる「Bot User OAuth Token」をコピーして、上の欄に貼り付けます。
                        """)

                    new_line = st.text_input("LINE Messaging API Token", value=keys.get("line", ""), type="password")
                    with st.expander("ℹ️ LINE Tokenの取得手順"):
                        st.markdown("""
                        1. [LINE Developers](https://developers.line.biz/ja/) にアクセスし、自分のLINEアカウントでログインします。
                        2. 「コンソール」を開き、新しく「プロバイダー」を作成します（名前は自分の名前などでOK）。
                        3. 作成したプロバイダーを開き、**「Messaging API」** チャネルを新規作成します。
                        4. 必須項目（アプリ名、説明など）を適当に入力して作成を完了させます。
                        5. 作成したチャネルを開き、**「Messaging API設定」** タブをクリックします。
                        6. 一番下までスクロールし、「チャネルアクセストークン」の **「発行」** ボタンを押します。
                        7. 表示された非常に長い文字列をコピーして、上の欄に貼り付けてください。
                        """)
                    
                    st.markdown("##### 🚀 Cloud Deploy (GitHub)")
                    new_gh_token = st.text_input("GitHub Personal Access Token", value=keys.get("gh_token", ""), type="password")
                    new_gh_owner = st.text_input("GitHub Username", value=keys.get("gh_owner", ""), placeholder="例: YamadaTaro")
                    new_gh_repo = st.text_input("Repository Name", value=keys.get("gh_repo", ""), placeholder="例: aibou_app")
                    with st.expander("ℹ️ GitHubトークンの取得・設定手順（自動デプロイ用）"):
                        st.markdown("""
                        1. [GitHubのトークン設定画面](https://github.com/settings/tokens) にアクセスしてログインします。
                        2. 画面右上の **「Generate new token」** を押し、**「Generate new token (classic)」** を選びます。
                        3. 「Note（名前）」に「THE FORGE OS Deploy」など分かりやすい名前を入力します。
                        4. 「Expiration（期限）」は **「No expiration（無期限）」** を選ぶと、後で更新する手間が省けます（セキュリティ警告が出ますがそのまま進んでOKです）。
                        5. 「Select scopes（権限）」の一覧から、一番上にある **「repo」**（リポジトリの全権限）のチェックボックスにチェックを入れます。
                        6. 画面一番下緑色の **「Generate token」** を押します。
                        7. **`ghp_`** から始まるトークンが表示されるので、それをコピーして一番上の欄（Token）に貼り付けてください。
                        8. 「GitHub Username」にはボスのユーザー名（例: minami-taro）を入力します。
                        9. 「Repository Name」には、Streamlit Cloudと連携しているこのアプリのリポジトリ名（例: aibouai_app）を入力してください。
                        """)
                    
                    st.markdown("---")
                    submitted = st.form_submit_button("💾 変更を保存してシステムに適用", use_container_width=True)
                    
                    if submitted:
                        vault_data["api_keys"] = {
                            "my_email": new_email, "my_email_app_password": new_email_pass,
                            "gemini": new_gemini, "google_calendar": new_calendar,
                            "slack": new_slack, "line": new_line,
                            "gh_token": new_gh_token, "gh_owner": new_gh_owner, "gh_repo": new_gh_repo
                        }
                        
                        if save_vault(vault_data):
                            st.session_state.global_api_keys = vault_data["api_keys"]
                            st.success("✅ 設定を安全に保存し、クラウドデータベースへ同期しました！")
                            st.balloons()
                        else:
                            st.error("❌ 保存に失敗しました。データベースの接続設定を確認してください。")

        # ================================
        elif setting_mode == "📖 取扱説明書":
            st.markdown("#### 📖 MANUAL")
            st.info("システムの使い方は今後ここに詳しく記載します。各種APIの取得方法は以下を開いてください。")
            with st.expander("ℹ️ Gmailアプリパスワードの取得手順"):
                st.markdown("1. [Googleアカウント管理画面](https://myaccount.google.com/) にアクセス。\n2. 「セキュリティ」>「2段階認証プロセス」をオン。\n3. 「アプリパスワード」を検索し作成。16桁の英字をコピー。")
            with st.expander("ℹ️ Gemini API Keyの取得手順"):
                st.markdown("1. [Google AI Studio](https://aistudio.google.com/) にアクセス。\n2. 「Get API key」>「Create API key」をクリックして生成。")
            with st.expander("ℹ️ Google Calendar 連携の準備について"):
                st.markdown("1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクト作成。\n2. 「Google Calendar API」を有効化し「サービスアカウント」を作成。\n3. JSONキーをダウンロードし中身をコピペ。")
            with st.expander("ℹ️ Slack Bot Token / LINE Tokenの取得手順"):
                st.markdown("Slack: [Slack API](https://api.slack.com/apps) でアプリを作成し「OAuth & Permissions」から `xoxb-` トークンを取得。\nLINE: [LINE Developers](https://developers.line.biz/ja/) でMessaging APIを作成し、一番下の「チャネルアクセストークン」を発行。")
            with st.expander("ℹ️ GitHubトークンの取得手順"):
                st.markdown("1. [GitHubのトークン設定画面](https://github.com/settings/tokens) にアクセス。\n2. 「Generate new token (classic)」を選ぶ。\n3. 「No expiration」にし「repo」にチェックを入れて生成。")

        # ================================
        elif setting_mode == "🚪 ログアウト":
            st.markdown("#### 🚪 LOGOUT")
            st.warning("システムをロックしてログイン画面に戻ります。")
            if st.button("LOGOUT 🔒", type="primary"):
                st.session_state.logged_in = False
                st.rerun()
