# main.py — AIbou Brain API（JARVIS的パーソナルAIのFastAPIバックエンド）
# =====================================================================
# Next.jsフロントから叩かれる「脳」。Streamlit / core.py には一切依存しない自己完結版。
# 無料デプロイ先: Google Cloud Run / Hugging Face Spaces（ffmpeg入りコンテナ）。
#
# 提供する機能:
#   GET  /health          ヘルスチェック（認証不要・コールドスタート温め用）
#   POST /chat            SSEストリーミング会話（記憶を注入＋会話を記憶）
#   POST /vision          画像＋プロンプトのマルチモーダル理解
#   POST /tts             テキスト→音声（edge-tts, MP3 base64）
#   POST /memory/add      記憶を1件追加
#   GET  /memory/recent   直近の記憶
#   GET  /income/summary  副業ジョブ(income_jobs)のステータス別集計
#   POST /video           絵コンテ→動画（リポジトリ root の renderer.py を再利用）
#
# 設計方針: 設定が欠けていても絶対にcrashせず、helpfulなJSONエラーを返す。
# =====================================================================

import asyncio
import base64
import os
import sys
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

import agenda
import agent
import artifacts
import autopilot
import board
import automations
import compliance
import config
import code_agent
import evolve
import fileread
import forge
import gh
import gservice
import guide as guide_mod
import tenancy
import hfhub
import imagegen
import income
import keepalive as keepalive_mod
import keychain
import life
import llm
import lp as lp_mod
import migrate
import newsletter
import note_client
import notify
import proactive
import pseo
import scheduler
import shellrun
import slides as slides_mod
import sns as sns_mod
import studio
import tasks as tasks_module
import tools
import transcribe as transcribe_mod
import vault
import video_script
from memory_store import mem_add, mem_recall, mem_recent

async def _scheduler_loop():
    """常駐ループ：60秒ごとに定期実行(scheduler.tick)を確認する（best-effort）。
    あわせて1日1回 Supabase を触って自動一時停止（7日）を防ぐ。
    サーバーがスリープする無料プランでは起きている間のみ動く
    （外部cronは /scheduler/tick と /keepalive）。"""
    ticks = 0
    while True:
        try:
            await asyncio.sleep(60)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, scheduler.tick)
            ticks += 1
            if ticks % 1440 == 1:  # 起動直後 + 以後およそ24時間ごと
                res = await loop.run_in_executor(None, keepalive_mod.ping)
                print(f"[keepalive] {res}")
        except asyncio.CancelledError:
            break
        except Exception as e:  # pragma: no cover
            print(f"[scheduler] loop error: {e}")


@asynccontextmanager
async def _lifespan(_app: "FastAPI"):
    """起動時：SUPABASE_DB_URL があればテーブルを自動作成（冪等・best-effort）。
    定期実行の常駐ループも起動する。未設定でも何もせず、絶対に起動を止めない。"""
    try:
        if migrate.db_url():
            res = await asyncio.get_event_loop().run_in_executor(None, migrate.run_migrations)
            print(f"[migrate] startup: {res}")
    except Exception as e:  # pragma: no cover
        print(f"[migrate] startup error: {e}")
    task = asyncio.ensure_future(_scheduler_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(
    title="AIbou Brain API",
    description="JARVIS的パーソナルAIアシスタントのバックエンド（chat / vision / tts / memory / income / video）",
    version="1.0.0",
    lifespan=_lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────
# FRONTEND_ORIGIN（既定 "*"）を許可。カンマ区切りで複数指定も可。
_origins = ["*"] if config.FRONTEND_ORIGIN == "*" else [
    o.strip() for o in config.FRONTEND_ORIGIN.split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_credentials=False,  # "*" と credentials は併用不可。Bearer運用なのでFalseで十分。
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 認証（任意のBearerトークン） ─────────────────────────────────
def _decode_supabase_jwt(token: str) -> Optional[dict]:
    """Supabase Auth の access_token (HS256) を検証して claims を返す。失敗は None。"""
    secret = config.SUPABASE_JWT_SECRET
    if not (secret and token):
        return None
    try:
        import jwt as pyjwt
        return pyjwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")
    except Exception:
        return None


def _verify_supabase_jwt(token: str) -> bool:
    return _decode_supabase_jwt(token) is not None


async def current_user(authorization: Optional[str] = Header(default=None)) -> str:
    """ログイン中の利用者ID（SupabaseのJWTの sub）。特定できなければ空文字。"""
    if authorization and authorization.strip().lower().startswith("bearer "):
        claims = _decode_supabase_jwt(authorization.strip()[7:].strip())
        if claims:
            return str(claims.get("sub") or "")
    return ""


async def current_claims(authorization: Optional[str] = Header(default=None)) -> dict:
    """ログイン中の利用者の claims（sub / email など）。分からなければ空dict。"""
    if authorization and authorization.strip().lower().startswith("bearer "):
        return _decode_supabase_jwt(authorization.strip()[7:].strip()) or {}
    return {}


def is_owner_claims(claims: Optional[dict]) -> bool:
    """このアプリの持ち主かどうか。

    OWNER_EMAIL / OWNER_USER_ID をどちらも設定していないときは「1人で使って
    いる」とみなして True（設定し忘れで自分が締め出されないようにする）。
    誰かに配るときは、必ずどちらかを設定すること。
    """
    if not (config.OWNER_EMAIL or config.OWNER_USER_ID):
        return True
    if not claims:
        return False
    if config.OWNER_USER_ID and str(claims.get("sub") or "") == config.OWNER_USER_ID:
        return True
    email = str(claims.get("email") or "").strip().lower()
    return bool(config.OWNER_EMAIL and email == config.OWNER_EMAIL)


async def require_owner(claims: dict = Depends(current_claims)) -> None:
    """持ち主専用のAPI。画面を隠すだけでは直接叩けてしまうので、ここでも塞ぐ。"""
    if not is_owner_claims(claims):
        raise HTTPException(status_code=403, detail="このモードは管理者専用です")


async def use_own_database(user_id: str = Depends(current_user)):
    """このリクエストの保存先を「その人のSupabase」に差し替える。

    ・接続済み  … その人のクライアント
    ・未接続    … None（保存しない）。管理者の共有DBへ黙って書かないため。
    ・そもそも利用者を特定できない（JWT無し/単独運用）… 差し替えない
      （従来どおりサーバーの既定Supabaseを使う）
    """
    if not user_id:
        yield ""
        return
    token = config.bind_request_client(tenancy.client_for(user_id))
    try:
        yield user_id
    finally:
        config.reset_request_client(token)


async def require_auth(authorization: Optional[str] = Header(default=None),
                       _db: str = Depends(use_own_database)) -> None:
    """認証。次のいずれかで通過:
      1) APP_TOKEN 設定時: Authorization: Bearer <APP_TOKEN> の一致
      2) SUPABASE_JWT_SECRET 設定時: Supabase ログインの JWT（HS256）が有効
    APP_TOKEN も REQUIRE_AUTH も無ければ従来どおりオープン。
    REQUIRE_AUTH=1 なら上記いずれかを必須にする（バンドル埋め込みトークン不要の
    実効的な保護は「SUPABASE_JWT_SECRET + REQUIRE_AUTH=1」の組み合わせ）。
    /health はこの依存を付けない。"""
    token = ""
    if authorization and authorization.strip().lower().startswith("bearer "):
        token = authorization.strip()[7:].strip()

    if config.APP_TOKEN and token == config.APP_TOKEN:
        return
    if _verify_supabase_jwt(token):
        return
    # どの保護も構成されていなければオープン
    if not config.APP_TOKEN and not config.REQUIRE_AUTH:
        return
    raise HTTPException(status_code=401, detail="Unauthorized: valid bearer token required")


# =====================================================================
# Pydantic リクエストモデル
# =====================================================================
class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' | 'assistant' | 'model'")
    content: str = ""


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = None
    persona: Optional[str] = None
    name: Optional[str] = None  # アシスタント名（既定 "AIbou"）


class VisionRequest(BaseModel):
    prompt: Optional[str] = "この画像について説明してください。"
    image_base64: str
    mime: Optional[str] = "image/jpeg"


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None  # 既定は config.DEFAULT_TTS_VOICE
    rate: Optional[str] = None   # 話速 例 "+0%" / "-20%" / "+30%"。既定 config.DEFAULT_TTS_RATE
    pitch: Optional[str] = None  # 声の高さ 例 "+0Hz" / "-20Hz"。既定 "+0Hz"


class KeySetRequest(BaseModel):
    name: str
    value: str = ""


class VaultGenerateRequest(BaseModel):
    notebook_id: str
    instruction: str = ""


class VaultDiagramRequest(BaseModel):
    notebook_id: str
    kind: str = "tree"


class MissionCreateRequest(BaseModel):
    goal: str
    notify: bool = True


class NotifyRequest(BaseModel):
    message: str


class AutomationCreateRequest(BaseModel):
    name: str
    trigger: Optional[dict] = None
    steps: list = []


class AutomationRunRequest(BaseModel):
    input: str = ""


class EvolveRequest(BaseModel):
    instruction: str


class AgendaAddRequest(BaseModel):
    title: str
    date: str = ""
    time: str = ""
    note: str = ""


class AgendaParseRequest(BaseModel):
    text: str
    today: str = ""


class MemoryAddRequest(BaseModel):
    role: str = "user"
    content: str
    importance: Optional[int] = 0


class Scene(BaseModel):
    narration: str = ""
    visual: str = ""


class VideoRequest(BaseModel):
    scenes: List[Scene]
    image_prompt: Optional[str] = ""
    aspect: str = "16:9"        # 16:9 / 9:16（Shorts） / 1:1
    subtitles: bool = True      # ナレーションを字幕として焼き込む


class StoryboardRequest(BaseModel):
    topic: str
    n: int = 5
    aspect: str = "16:9"
    tone: str = "friendly"
    style: str = ""


class ForgeRequest(BaseModel):
    kind: str = "app"          # app | image | slides | sheet | doc
    prompt: str = ""


class CodeFile(BaseModel):
    path: str
    content: str = ""
    action: Optional[str] = None


class CodeGenerateRequest(BaseModel):
    instruction: str
    files: List[CodeFile] = Field(default_factory=list)
    history: List[ChatMessage] = Field(default_factory=list)
    depth: str = "normal"      # normal | deep（計画→実装→自己レビュー）


class AiConfigRequest(BaseModel):
    provider: Optional[str] = None   # auto | gemini | huggingface
    hf_model: Optional[str] = None
    code_model: Optional[str] = None


class HfModelAddRequest(BaseModel):
    model: str
    task: str
    label: str = ""
    note: str = ""


class HfTestRequest(BaseModel):
    model: str
    task: str


class HfAssignRequest(BaseModel):
    role: str                        # chat | code | image | asr
    model: str = ""                  # 空文字で解除


class HfRunRequest(BaseModel):
    """お試し実行（音声入力のASRは /capture/transcribe 側を使う）。"""
    model: str
    task: str
    text: str = ""
    labels: Optional[List[str]] = None


class AgentActRequest(BaseModel):
    instruction: str
    history: Optional[List[ChatMessage]] = None
    name: Optional[str] = None       # アシスタント名（既定 "AIbou"）
    approval: bool = False           # 機微なツールを実行前に承認させる


class AgentExecuteRequest(BaseModel):
    tool: str
    params: dict = Field(default_factory=dict)


class ScheduleRequest(BaseModel):
    instruction: str = ""
    time: str = "08:00"
    days: str = "daily"        # "daily" | "mon,wed,fri" 形式
    automation_id: str = ""    # 指定すると BOARD の自動化を時刻で回す


class GithubImportRequest(BaseModel):
    repo: str
    ref: str = ""
    path: str = ""


class LifeEntryRequest(BaseModel):
    category: str = "other"
    content: str
    entry_date: str = ""


class LifeExtractRequest(BaseModel):
    turns: List[ChatMessage] = Field(default_factory=list)


class GithubPushRequest(BaseModel):
    repo: str
    base: str = "main"
    branch: str = ""
    message: str = ""
    files: List[CodeFile] = Field(default_factory=list)
    create_pr: bool = True
    pr_title: str = ""



class EnqueueRequest(BaseModel):
    theme: str


class JobActionRequest(BaseModel):
    id: str


class VaultCreateRequest(BaseModel):
    name: str


class VaultAddRequest(BaseModel):
    notebook_id: str
    title: str = ""
    content: str = ""


class VaultDocDeleteRequest(BaseModel):
    notebook_id: str
    title: str


class VaultQueryRequest(BaseModel):
    notebook_id: str
    question: str


class TaskCreateRequest(BaseModel):
    title: str
    content: str = ""
    status: str = "pending"
    priority: str = "mid"     # high | mid | low
    due: str = ""             # YYYY-MM-DD
    project: str = ""         # プロジェクト（グループ）名


class TaskUpdateRequest(BaseModel):
    status: Optional[str] = None
    response: Optional[str] = None
    content: Optional[str] = None
    priority: Optional[str] = None
    due: Optional[str] = None
    project: Optional[str] = None


class BoardSaveRequest(BaseModel):
    nodes: list = Field(default_factory=list)
    edges: list = Field(default_factory=list)


class SlidesExportRequest(BaseModel):
    title: str = ""
    slides: list = Field(default_factory=list)
    theme: str = ""


class NarrateRequest(BaseModel):
    source: str
    style: str = "explain"
    seconds: int = 0
    instruction: str = ""


class ShellRunRequest(BaseModel):
    command: str
    files: list = Field(default_factory=list)   # [{"path","content"}]
    timeout: int = 60


class SlideReviseRequest(BaseModel):
    slide: dict = Field(default_factory=dict)
    instruction: str
    deck_title: str = ""
    layout: str = ""
    context: str = ""


class ArtifactUpdateRequest(BaseModel):
    content: Optional[str] = None
    title: Optional[str] = None


class PseoPlanRequest(BaseModel):
    axes: List[List[str]] = Field(default_factory=list)
    template: str = ""
    limit: int = 20


class PseoStatusRequest(BaseModel):
    status: str


class SubscribeRequest(BaseModel):
    email: str
    source: str = ""


class IssueDraftRequest(BaseModel):
    subject: str = ""
    body: str = ""
    topic: str = ""


class IssueSendRequest(BaseModel):
    test_to: str = ""


class NoteDraftRequest(BaseModel):
    title: str
    markdown: str


class LpGenerateRequest(BaseModel):
    brief: str
    style: str = "modern"
    sections: str = ""
    current: str = ""     # 既存HTML（指定すると改善モード）
    save: bool = False    # 生成物として保存するか
    kind: str = "lp"      # lp（ページ）| app（動くWebアプリ）


class ImageGenerateRequest(BaseModel):
    prompt: str
    aspect: str = "1:1"
    n: int = 2
    save: bool = False
    offset: int = 0   # 同じ指示で“さらに別案”を出すためのseedずらし
    engine: str = "auto"   # auto | pollinations | hf


class SnsGenerateRequest(BaseModel):
    platform: str = "x"
    topic: str
    n: int = 3
    tone: str = ""
    promo: bool = False
    thread: bool = False
    with_images: bool = False


class BoardCreateRequest(BaseModel):
    name: str = ""


class BoardRenameRequest(BaseModel):
    name: str


class AiCreateRequest(BaseModel):
    name: str
    persona: str = ""
    model: str = "gemini-2.5-flash"
    rules: str = ""


class WorkflowCreateRequest(BaseModel):
    name: str
    steps: list = []


class WorkflowRunRequest(BaseModel):
    input: str = ""


# =====================================================================
# プロンプト構築
# =====================================================================
def build_system_prompt(name: Optional[str], persona: Optional[str], memory_block: str) -> str:
    """アシスタントの基本人格＋persona＋想起した記憶 を1つのsystem promptに合成する。"""
    assistant_name = (name or "AIbou").strip() or "AIbou"
    parts = [
        f"あなたは「{assistant_name}」という名前の、ユーザー専属のパーソナルAIアシスタント（JARVIS的存在）です。",
        "簡潔で的確、かつ親しみやすい口調で、ユーザーの目標達成を全力でサポートしてください。",
        "わからないことは正直に伝え、必要なら確認を取ってください。",
    ]
    if persona and persona.strip():
        parts.append(f"\n【ペルソナ / 振る舞いの指針】\n{persona.strip()}")
    # アプリ自身の説明は guide.py が唯一の出どころ。ここに直接書くと、
    # 画面のガイドと食い違って古くなる。
    parts.append(f"\n{guide_mod.prompt_block()}")
    if memory_block:
        parts.append(f"\n{memory_block}")
    return "\n".join(parts)


def build_conversation(system_prompt: str, history: Optional[List[ChatMessage]], message: str) -> str:
    """system prompt ＋ 履歴 ＋ 今回のメッセージ を1つのテキストプロンプトに結合する。
    google-generativeai のシンプルな single-prompt 形式（stream対応）に合わせる。"""
    lines = [system_prompt, "\n--- 会話履歴 ---"]
    for m in (history or []):
        role = (m.role or "").lower()
        speaker = "ユーザー" if role in ("user", "human") else "アシスタント"
        content = (m.content or "").strip()
        if content:
            lines.append(f"{speaker}: {content}")
    lines.append(f"ユーザー: {message.strip()}")
    lines.append("アシスタント:")
    return "\n".join(lines)


# SSE を「溜めずにその場で流す」ための指示。
#   X-Accel-Buffering: no … nginx系のプロキシに、まとめずに素通しさせる。
#     これが無いと、プロキシが数KB貯まるか応答が終わるまで送出を待つことが
#     あり、「しばらく無反応 → 突然まとめて出る」という遅さになる。
#   Cache-Control / Connection … 途中のキャッシュや圧縮に触らせない。
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


def _sse_response(gen) -> StreamingResponse:
    """SSE をバッファされない形で返す。"""
    return StreamingResponse(gen, media_type="text/event-stream", headers=SSE_HEADERS)


def _sse(data: dict) -> str:
    """dict を SSE の1イベント（data: <json>\\n\\n）に変換する。"""
    import json
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# =====================================================================
# エンドポイント
# =====================================================================
@app.get("/health")
async def health():
    """ヘルスチェック（認証不要）。フロントがコールドスタートを温めるのに使う。"""
    return {"status": "ok"}


@app.post("/chat")
async def chat(req: ChatRequest, _auth: None = Depends(require_auth)):
    """SSEストリーミング会話。
    1) 記憶を想起して system prompt を構築
    2) Gemini を stream=True で呼び、トークンを data: {"token": "..."} で逐次送信
    3) 完了後 data: {"done": true} を送り、会話を agent_memory に保存（best-effort）
    """
    # AIプロバイダ（Gemini か HuggingFace）が1つも無ければ crash させず案内。
    if llm.active_provider() == "none":
        async def err_stream():
            yield _sse({"error": "AI未設定です。Settings → KEYCHAIN に GEMINI_API_KEY か HUGGINGFACE_TOKEN を保存してください。"})
            yield _sse({"done": True})
        return _sse_response(err_stream())

    # 記憶を想起（Supabaseが無ければ空文字）。
    # Supabase も埋め込みも同期呼び出しなので、そのまま await 無しで呼ぶと
    # 返事が始まるまでの間ずっとイベントループを止めてしまう（他の人の
    # リクエストごと止まる）。別スレッドへ逃がす。
    memory_block = await asyncio.get_event_loop().run_in_executor(
        None, lambda: mem_recall(req.message, limit=8)
    )
    system_prompt = build_system_prompt(req.name, req.persona, memory_block)
    # ツール実行を許可（行動を頼まれた時だけマーカーを使う旨をルール付けする）
    system_prompt += (
        "\n\n" + tools.TOOLS_DOC + "\n"
        "【ツールの使い方】行動（記憶・通知・副業投入・メモ保存など）を明確に頼まれた時だけ、"
        "返答の冒頭で必ず " + tools.TOOL_CALL_MARKER + '{"tool":"名","params":{...}} を1行で出すこと。'
        "通常の会話・質問では絶対に使わないこと。"
    )
    prompt = build_conversation(system_prompt, req.history, req.message)
    marker = tools.TOOL_CALL_MARKER

    async def event_stream():
        collected: List[str] = []
        loop = asyncio.get_event_loop()

        def _next(it):
            try:
                return next(it)
            except StopIteration:
                return None

        try:
            it = llm.stream_text(prompt)
            buf = ""
            decided = None  # None=判定中 / "tool" / "normal"

            while True:
                text = await loop.run_in_executor(None, _next, it)
                if text is None:
                    break
                if not text:
                    continue
                if decided == "normal":
                    collected.append(text)
                    yield _sse({"token": text})
                    continue
                if decided == "tool":
                    buf += text  # ツール呼び出し全体を黙って蓄積
                    continue
                # 判定中：先頭がツールマーカーか見極める
                buf += text
                stripped = buf.lstrip()
                if not stripped:
                    continue
                if stripped.startswith(marker):
                    decided = "tool"
                elif marker.startswith(stripped):
                    continue  # まだマーカーになる可能性 → さらにバッファ
                else:
                    decided = "normal"
                    collected.append(buf)
                    yield _sse({"token": buf})
                    buf = ""

            # 判定がつかないまま終了した短い応答は通常扱いで送出
            if decided is None and buf:
                collected.append(buf)
                yield _sse({"token": buf})

            # ツール呼び出しなら実行 → 結果を踏まえ最終回答をストリーム
            if decided == "tool":
                call, preface = tools.extract_tool_call(buf)
                if call:
                    result = await loop.run_in_executor(
                        None, lambda: tools.execute_tool(call.get("tool", ""), call.get("params", {}) or {})
                    )
                    followup = (
                        prompt
                        + "\nアシスタント:（ツールを実行しました）"
                        + "\n<<<TOOL_RESULT>>> " + result
                        + "\nアシスタント（上の結果を踏まえ、ツール記法は使わず日本語で簡潔に報告）:"
                    )
                    it2 = llm.stream_text(followup)
                    while True:
                        t2 = await loop.run_in_executor(None, _next, it2)
                        if t2 is None:
                            break
                        if t2:
                            collected.append(t2)
                            yield _sse({"token": t2})
                else:
                    collected.append(buf)
                    yield _sse({"token": buf})
        except Exception as e:
            if config.is_zero_quota_429(e):
                yield _sse({"error": (
                    "Gemini無料枠の上限（またはこのキーの無料枠が0）に達しました。"
                    "KEYCHAIN に HUGGINGFACE_TOKEN を入れると自動でHuggingFaceに切り替わります。"
                )})
            else:
                yield _sse({"error": f"generation failed: {e}"})

        yield _sse({"done": True})

        # 会話を記憶（best-effort）
        try:
            full = "".join(collected).strip()
            if req.message:
                mem_add("user", req.message, importance=0)
            if full:
                mem_add("assistant", full, importance=0)
        except Exception:
            pass

    return _sse_response(event_stream())


@app.post("/agent/act")
async def agent_act(req: AgentActRequest, _auth: None = Depends(require_auth)):
    """HOME：手足となって動く自律エージェント（SSE）。plan→act→observe を
    繰り返し、進捗を data:{"phase":...} で実況、最後に final→done を送る。"""
    if llm.active_provider() == "none":
        async def err_stream():
            yield _sse({"phase": "error", "detail": "AI未設定です。Settings → KEYCHAIN に GEMINI_API_KEY か HUGGINGFACE_TOKEN を保存してください。"})
            yield _sse({"phase": "done", "steps": 0})
        return _sse_response(err_stream())

    history = [h.model_dump() for h in (req.history or [])]

    async def event_stream():
        loop = asyncio.get_event_loop()
        gen = agent.run_stream(req.instruction, history, req.name or "AIbou", req.approval)

        def _next(g):
            try:
                return next(g)
            except StopIteration:
                return None

        collected_final = ""
        while True:
            ev = await loop.run_in_executor(None, _next, gen)
            if ev is None:
                break
            if ev.get("phase") == "final":
                collected_final = ev.get("text", "")
            yield _sse(ev)

        # 会話を記憶（best-effort）— CHAT と同じ扱い。
        try:
            if req.instruction:
                mem_add("user", req.instruction, importance=0)
            if collected_final:
                mem_add("assistant", collected_final, importance=0)
        except Exception:
            pass

    return _sse_response(event_stream())


@app.post("/agent/execute")
async def agent_execute(req: AgentExecuteRequest, _auth: None = Depends(require_auth)):
    """承認された単一ツールを実行する（承認モードの『承認』ボタン用）。"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: tools.execute_tool(req.tool, req.params or {}))
    return {"result": result}


@app.post("/vision")
async def vision(req: VisionRequest, _auth: None = Depends(require_auth)):
    """画像（base64）＋プロンプトをGeminiのマルチモーダルで理解し、テキストを返す。"""
    model = config.get_gemini_model()
    if model is None:
        return JSONResponse(
            status_code=503,
            content={"error": "GEMINI_API_KEY is not configured on the server."},
        )
    try:
        raw = base64.b64decode(req.image_base64)
    except Exception:
        return JSONResponse(status_code=400, content={"error": "image_base64 is not valid base64."})

    prompt = req.prompt or "この画像について説明してください。"
    mime = req.mime or "image/jpeg"
    try:
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: model.generate_content([prompt, {"mime_type": mime, "data": raw}]),
        )
        return {"text": getattr(resp, "text", "") or ""}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"vision failed: {e}"})


@app.post("/tts")
async def tts(req: TTSRequest, _auth: None = Depends(require_auth)):
    """edge-tts でテキストを音声(MP3)化し、base64で返す。失敗時は audio_base64="" を返す。"""
    text = (req.text or "").strip()
    if not text:
        return {"audio_base64": "", "error": "text is empty"}
    voice = (req.voice or config.DEFAULT_TTS_VOICE).strip() or config.DEFAULT_TTS_VOICE
    rate = (req.rate or config.DEFAULT_TTS_RATE).strip() or config.DEFAULT_TTS_RATE
    pitch = (req.pitch or "+0Hz").strip() or "+0Hz"

    try:
        audio_bytes = await _synthesize_tts(text, voice, rate, pitch)
        if not audio_bytes:
            return {"audio_base64": "", "error": "tts produced no audio"}
        return {"audio_base64": base64.b64encode(audio_bytes).decode("ascii")}
    except Exception as e:
        # フォールバック: 空文字（フロント側で無音扱い）
        return {"audio_base64": "", "error": f"tts failed: {e}"}


async def _synthesize_tts(text: str, voice: str, rate: str = "+0%",
                          pitch: str = "+0Hz") -> bytes:
    """edge-tts で MP3 バイト列を生成する（asyncで実行）。

    rate は "+0%"、pitch は "+0Hz" の形式。どちらも書式が違うと edge-tts が
    例外を出すので、その場合は既定値に落とす（声が出ないより既定で出るほうがよい）。
    """
    import edge_tts
    r = (rate or "+0%").strip()
    if not (r.endswith("%") and (r[0] in "+-") and r[1:-1].lstrip("-").isdigit()):
        r = "+0%"
    p = (pitch or "+0Hz").strip()
    if not (p.endswith("Hz") and (p[0] in "+-") and p[1:-2].lstrip("-").isdigit()):
        p = "+0Hz"
    communicate = edge_tts.Communicate(text, voice, rate=r, pitch=p)
    buf = bytearray()
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio" and chunk.get("data"):
            buf.extend(chunk["data"])
    return bytes(buf)


@app.post("/memory/add")
async def memory_add(req: MemoryAddRequest, _auth: None = Depends(require_auth)):
    """記憶を1件追加する。Supabaseが無ければ ok=false（ただしcrashはしない）。"""
    ok = mem_add(req.role, req.content, importance=req.importance or 0)
    if not ok:
        return {"ok": False, "error": "memory store unavailable (Supabase not configured)"}
    return {"ok": True}


@app.get("/memory/recent")
async def memory_recent(limit: int = 20, _auth: None = Depends(require_auth)):
    """直近の記憶を返す。Supabaseが無ければ空リスト。"""
    return {"items": mem_recent(limit=limit)}


@app.get("/income/summary")
async def income_summary(_auth: None = Depends(require_auth), _own: None = Depends(require_owner)):
    """副業ジョブ(income_jobs)のステータス別件数＋合計を返す。
    Supabaseが無ければ {} を返す（crashしない）。"""
    c = config.get_supabase()
    if not c:
        return {}
    statuses = ["pending", "approved", "rejected", "completed", "failed"]
    summary = {s: 0 for s in statuses}
    total = 0
    try:
        rows = (c.table("income_jobs")
                .select("status")
                .limit(10000)
                .execute().data) or []
        for r in rows:
            st = (r.get("status") or "").strip()
            total += 1
            if st in summary:
                summary[st] += 1
        summary["total"] = total
        return summary
    except Exception:
        # テーブルが無い等。空で縮退。
        return {}


@app.post("/forge/generate")
async def forge_generate(req: ForgeRequest, _auth: None = Depends(require_auth)):
    """Forge：アプリ/画像/スライド/表/文書 を生成して返す。
    重い同期処理（Gemini）はスレッドに逃がす。"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: forge.generate(req.kind, req.prompt))
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(status_code=503, content=result)
    return result


@app.post("/code/generate")
async def code_generate(req: CodeGenerateRequest, _auth: None = Depends(require_auth)):
    """CODE：AIコーディングエージェント（SSE）。段階進捗を data:{"phase":...} で流し、
    最後に data:{"phase":"done", explanation, files, edits} を送る（Claude Code 風の実況）。"""
    files = [f.model_dump() for f in req.files]
    history = [h.model_dump() for h in req.history]
    depth = req.depth

    async def event_stream():
        loop = asyncio.get_event_loop()
        gen = code_agent.run_stream(req.instruction, files, history, depth)

        def _next(g):
            try:
                return next(g)
            except StopIteration:
                return None

        while True:
            ev = await loop.run_in_executor(None, _next, gen)
            if ev is None:
                break
            yield _sse(ev)

    return _sse_response(event_stream())


# ── CAPTURE：文字起こし / ナレーション ──────────────────────────────

@app.get("/capture/status")
async def capture_status(_auth: None = Depends(require_auth)):
    """この環境で文字起こし・ナレーションが使えるか（ffmpegとキーの有無）。"""
    return transcribe_mod.status()


@app.post("/capture/transcribe")
async def capture_transcribe(file: UploadFile = File(...), engine: str = Form("auto"),
                             _auth: None = Depends(require_auth)):
    """録画/録音を文字起こしする（サーバーで音声を抽出してからAIに渡す）。

    engine: auto（既定）/ gemini / hf。auto はHFにASRモデルが割り当ててあればHF。
    """
    data = await file.read()
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(
        None, lambda: transcribe_mod.transcribe(data, file.filename or "rec.webm",
                                                file.content_type or "", engine or "auto"))
    if res.get("error"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.post("/capture/narrate")
async def capture_narrate(req: NarrateRequest, _auth: None = Depends(require_auth)):
    """文字起こし（または構成メモ）から読み上げ台本を作る。"""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(
        None, lambda: transcribe_mod.narration_script(
            req.source, req.style, req.seconds, req.instruction))
    if res.get("error"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.post("/capture/voiceover")
async def capture_voiceover(file: UploadFile = File(...), script: str = Form(...),
                            voice: str = Form(""), rate: str = Form(""),
                            keep_original: str = Form("0"),
                            _auth: None = Depends(require_auth)):
    """台本を読み上げて、録画に重ねた mp4 を返す（base64）。"""
    text = (script or "").strip()
    if not text:
        return JSONResponse(status_code=400, content={"error": "ナレーション台本が空です"})
    if not transcribe_mod.ffmpeg_available():
        return JSONResponse(status_code=503, content={
            "error": "サーバーに ffmpeg が無いためナレーションを重ねられません"})

    video = await file.read()
    # 台本を音声にする（既存のTTSをそのまま使う）
    try:
        audio = await _synthesize_tts(
            text[:transcribe_mod.MAX_SCRIPT_CHARS],
            (voice or config.DEFAULT_TTS_VOICE).strip() or config.DEFAULT_TTS_VOICE,
            (rate or config.DEFAULT_TTS_RATE).strip() or config.DEFAULT_TTS_RATE)
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": f"読み上げに失敗しました: {e}"})
    if not audio:
        return JSONResponse(status_code=503, content={"error": "読み上げ音声を作れませんでした"})

    keep = str(keep_original).strip() in ("1", "true", "yes", "on")
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(
        None, lambda: transcribe_mod.voiceover(video, audio, keep))
    if res.get("error"):
        return JSONResponse(status_code=400, content=res)
    return {"ok": True, "video_base64": base64.b64encode(res["data"]).decode("ascii"),
            "seconds": res.get("seconds"), "mixed": res.get("mixed", False)}


@app.get("/code/shell")
async def code_shell_status(_auth: None = Depends(require_auth)):
    """サーバー実行が有効かどうかと、許可コマンドの一覧。"""
    return shellrun.status()


@app.post("/code/shell")
async def code_shell_run(req: ShellRunRequest, _auth: None = Depends(require_auth)):
    """CODEのワークスペースを一時ディレクトリに展開して1コマンド実行する。

    既定では無効（ENABLE_SHELL=1 のときだけ動く）。有効時も環境変数を洗い、
    許可コマンド・CPU/メモリ/時間の上限つきで実行する（shellrun.py 参照）。
    """
    if not shellrun.enabled():
        return JSONResponse(status_code=403, content=shellrun.status())
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(
        None, lambda: shellrun.run(req.command, req.files, req.timeout))
    if isinstance(res, dict) and res.get("error"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.get("/code/scaffold")
async def code_scaffold(kind: str = "web", _auth: None = Depends(require_auth)):
    """CODE：スターターワークスペース（web | python | empty）。"""
    return code_agent.scaffold(kind)


def _abs_media_url(request: Request, url: str) -> str:
    """/hf/image/... のような相対URLを、絶対URLに直す。

    画像URLはフロント(Vercel)の <img src> と「生成物」履歴の両方に載る。
    相対のままだと Vercel 側のオリジンに解決されて壊れるので、必ず絶対にする。
    優先度は 明示env → リクエストのホスト。https を強制するのは、Renderの
    プロキシ配下で base_url が http になり、httpsのページから読めなくなるため
    （localhost だけは http のまま）。
    """
    if not url.startswith("/"):
        return url
    base = (os.environ.get("PUBLIC_API_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    if not base:
        b = str(request.base_url).rstrip("/")
        host = b.split("://")[-1].split(":")[0]
        if b.startswith("http://") and host not in ("localhost", "127.0.0.1", "testserver"):
            b = "https://" + b[len("http://"):]
        base = b
    return f"{base}{url}"


def _hf_text_choices(defaults: List[str]) -> List[str]:
    """HF MODELS に自分で登録したテキストモデルを、既定候補の先に並べる。

    2箇所（AI PROVIDER と HF MODELS）で別々の一覧が出て混乱しないよう、
    台帳に入れたものは必ず選択肢に現れるようにする。
    """
    try:
        mine = [m.get("model", "") for m in hfhub.list_models()
                if m.get("task") == "text" and m.get("model")]
    except Exception:
        mine = []
    out: List[str] = []
    for m in mine + defaults:
        if m and m not in out:
            out.append(m)
    return out


@app.get("/ai/config")
async def ai_config_get(_auth: None = Depends(require_auth)):
    """AIプロバイダ/モデルの現在設定と選択肢を返す（設定UI用）。"""
    return {
        "provider": llm._kc("LLM_PROVIDER") or "auto",
        "hf_model": llm._kc("HF_MODEL") or llm.DEFAULT_HF_MODEL,
        "code_model": llm._kc("CODE_MODEL") or llm.DEFAULT_CODE_MODEL,
        "active": llm.active_provider(),
        "gemini_ready": config.gemini_configured(),
        "hf_ready": bool(llm._hf_token()),
        "presets": {
            "chat": _hf_text_choices([
                "meta-llama/Llama-3.3-70B-Instruct",
                "Qwen/Qwen2.5-72B-Instruct",
                "deepseek-ai/DeepSeek-V3-0324",
                "mistralai/Mistral-Small-24B-Instruct-2501",
                "meta-llama/Llama-3.1-8B-Instruct",
            ]),
            "code": _hf_text_choices([
                "Qwen/Qwen2.5-Coder-32B-Instruct",
                "deepseek-ai/DeepSeek-V3-0324",
                "Qwen/Qwen2.5-Coder-7B-Instruct",
            ]),
        },
    }


@app.post("/ai/config")
async def ai_config_set(req: AiConfigRequest, _auth: None = Depends(require_auth)):
    """AIプロバイダ/モデルを設定（KEYCHAIN経由で永続化）。"""
    if req.provider is not None:
        keychain.set_key("LLM_PROVIDER", req.provider.strip())
    if req.hf_model is not None:
        keychain.set_key("HF_MODEL", req.hf_model.strip())
    if req.code_model is not None:
        keychain.set_key("CODE_MODEL", req.code_model.strip())
    return await ai_config_get()


# ── 自分のデータベース（利用者ごと） ──────────────────────────────

class DatabaseConnectRequest(BaseModel):
    url: str
    service_key: str
    db_url: str = ""     # テーブル自動作成に使う postgresql://…（任意）
    label: str = ""


@app.get("/account/database")
async def account_database(user_id: str = Depends(current_user)):
    """自分のDBの接続状態。鍵の値は返さない（マスクのみ）。"""
    if not user_id:
        return {"available": False,
                "reason": "ログインしていないため、個人のデータベースは使えません"}
    return {"available": True, **tenancy.status(user_id)}


@app.post("/account/database/test")
async def account_database_test(req: DatabaseConnectRequest,
                                _user: str = Depends(current_user)):
    """保存せずに、その接続で本当に繋がるかだけ確かめる。"""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: tenancy.check(req.url, req.service_key))
    if res.get("error"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.post("/account/database")
async def account_database_connect(req: DatabaseConnectRequest,
                                   user_id: str = Depends(current_user)):
    """自分のDBを接続する（繋がることを確かめてから保存）。"""
    if not user_id:
        return JSONResponse(status_code=401,
                            content={"error": "ログインしてから接続してください"})
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(
        None, lambda: tenancy.connect(user_id, req.url, req.service_key, req.db_url, req.label))
    if res.get("error"):
        return JSONResponse(status_code=400, content=res)
    return {**res, **tenancy.status(user_id)}


@app.post("/account/database/migrate")
async def account_database_migrate(user_id: str = Depends(current_user)):
    """自分のDBに必要なテーブルを作る。"""
    if not user_id:
        return JSONResponse(status_code=401, content={"error": "ログインしてください"})
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: tenancy.create_tables(user_id))
    if res.get("error"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.delete("/account/database")
async def account_database_disconnect(user_id: str = Depends(current_user)):
    """接続を外す。以後この人のデータは保存されない（DB自体は消さない）。"""
    if not user_id:
        return JSONResponse(status_code=401, content={"error": "ログインしてください"})
    return tenancy.disconnect(user_id)


@app.get("/account/profile")
async def account_profile(claims: dict = Depends(current_claims)):
    """画面が出し分けるための、その人の立場。

    持ち主専用モードはここを見て隠す。ただし隠すだけでは直接APIを叩けて
    しまうので、各エンドポイント側でも require_owner で塞いでいる。
    """
    owner = is_owner_claims(claims)
    return {
        "signed_in": bool(claims),
        "user_id": str(claims.get("sub") or ""),
        "email": str(claims.get("email") or ""),
        "is_owner": owner,
        # 持ち主だけの機能。UIはこの一覧を見て出し分ける
        "owner_only_modes": ["income", "evolve"],
        "owner_configured": bool(config.OWNER_EMAIL or config.OWNER_USER_ID),
    }


@app.get("/guide")
async def guide(_auth: None = Depends(require_auth), claims: dict = Depends(current_claims)):
    """アプリの使い方（画面のガイドとCHATが同じ内容を見る）。

    持ち主専用のモードは、持ち主以外の説明書には出さない
    （使えない機能の説明が並ぶと、壊れているように見えるため）。
    """
    owner = is_owner_claims(claims)
    return {
        "sections": guide_mod.sections(owner=owner),
        "modes": guide_mod.modes(owner=owner),
        "setup": _setup_with_schema(),
        "is_owner": owner,
        **guide_mod.status(owner=owner),
    }


def _read_schema_sql() -> str:
    """貼り付け用のSQL全文。リポジトリ同梱のものをそのまま返す。

    説明書に手で書き写すと、本物のスキーマと必ずズレる。実物を読んで返す。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, "supabase_schema.sql"),
              os.path.join(os.path.dirname(here), "supabase_schema.sql")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            continue
    return ""


def _setup_with_schema() -> list:
    """はじめる手順。code:"schema" を実際のSQL全文に差し替える。"""
    sql = _read_schema_sql()
    out = []
    for s in guide_mod.setup_steps():
        if s.get("code") == "schema":
            s = {**s, "code": sql, "code_lang": "sql",
                 "code_label": "Supabase の SQL Editor に貼り付けるSQL"}
        out.append(s)
    return out


# ── HF MODELS：HuggingFaceのモデルを登録して役割に割り当てる ──────────

@app.get("/hf/status")
async def hf_status(_auth: None = Depends(require_auth)):
    """扱えるタスク・役割の割り当て・登録数。トークンの値は返さない。"""
    return hfhub.status()


@app.get("/hf/models")
async def hf_models(_auth: None = Depends(require_auth)):
    """登録済みモデルの台帳。"""
    loop = asyncio.get_event_loop()
    return {"models": await loop.run_in_executor(None, hfhub.list_models)}


@app.post("/hf/models")
async def hf_models_add(req: HfModelAddRequest, _auth: None = Depends(require_auth)):
    """モデルを台帳に登録する（動作確認は別途 /hf/test）。"""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(
        None, lambda: hfhub.add_model(req.model, req.task, req.label, req.note))
    if res.get("error"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.delete("/hf/models/{model_row_id}")
async def hf_models_delete(model_row_id: str, _auth: None = Depends(require_auth)):
    """台帳から削除する（割り当て中の役割も外れる）。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: hfhub.delete_model(model_row_id))


@app.post("/hf/models/{model_row_id}/test")
async def hf_models_test(model_row_id: str, _auth: None = Depends(require_auth)):
    """台帳のモデルを実際に1回叩いて、結果を台帳に記録する。"""
    loop = asyncio.get_event_loop()
    row = await loop.run_in_executor(None, lambda: hfhub.get_model(model_row_id))
    if not row:
        return JSONResponse(status_code=404, content={"error": "そのモデルは台帳にありません"})
    res = await loop.run_in_executor(
        None, lambda: hfhub.test_model(row.get("model", ""), row.get("task", "")))
    await loop.run_in_executor(
        None, lambda: hfhub.update_check(model_row_id, bool(res.get("ok")),
                                        res.get("error", "")))
    if not res.get("ok"):
        return JSONResponse(status_code=502, content=res)
    return res


@app.post("/hf/test")
async def hf_test(req: HfTestRequest, _auth: None = Depends(require_auth)):
    """台帳に入れる前に、モデルIDとタスクの組み合わせを試す。"""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: hfhub.test_model(req.model, req.task))
    if not res.get("ok"):
        return JSONResponse(status_code=502, content=res)
    return res


@app.post("/hf/assign")
async def hf_assign(req: HfAssignRequest, _auth: None = Depends(require_auth)):
    """役割（会話/コード/画像/文字起こし）にモデルを割り当てる。"""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: hfhub.assign(req.role, req.model))
    if res.get("error"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.get("/hf/search")
async def hf_search(q: str = "", task: str = "", limit: int = 12,
                    _auth: None = Depends(require_auth)):
    """HuggingFace Hub からモデルを探す（トークン不要の公開API）。"""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: hfhub.search(q, task, limit))
    if res.get("error"):
        return JSONResponse(status_code=502, content=res)
    return res


@app.post("/hf/run")
async def hf_run(req: HfRunRequest, request: Request, _auth: None = Depends(require_auth)):
    """お試し実行。画像/音声はbase64、それ以外はテキストやラベルを返す。"""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(
        None, lambda: hfhub.run(req.task, req.model, text=req.text, labels=req.labels))
    if res.get("error"):
        return JSONResponse(status_code=502, content=res)
    if res.get("kind") == "image":
        img_id = await loop.run_in_executor(
            None, lambda: hfhub.save_image(res["data"], res.get("mime", "image/png"), req.text))
        return {"ok": True, "kind": "image",
                "url": _abs_media_url(request, hfhub.image_url(img_id)),
                "mime": res.get("mime"), "bytes": res.get("bytes")}
    if res.get("kind") == "audio":
        return {"ok": True, "kind": "audio", "mime": res.get("mime"),
                "bytes": res.get("bytes"),
                "audio_base64": base64.b64encode(res["data"]).decode("ascii")}
    return res


@app.get("/hf/image/{img_id}")
async def hf_image(img_id: str):
    """生成画像を配る。IDは推測できないUUIDで、一覧は公開しない。

    <img src> はヘッダを付けられないため、ここだけ認証を通さない
    （中身は自分が生成した画像で、鍵や個人データは含まれない）。
    """
    loop = asyncio.get_event_loop()
    data, mime = await loop.run_in_executor(None, lambda: hfhub.get_image(img_id))
    if not data:
        return JSONResponse(status_code=404, content={"error": "画像が見つかりません"})
    from fastapi.responses import Response
    return Response(content=data, media_type=mime or "image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/github/repos")
async def github_repos(_auth: None = Depends(require_auth)):
    """CODE：アクセス可能なGitHubリポジトリ一覧（GITHUB_TOKEN必須）。"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, gh.list_repos)
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(status_code=503, content=result)
    return result


@app.post("/github/import")
async def github_import(req: GithubImportRequest, _auth: None = Depends(require_auth)):
    """CODE：リポジトリ（またはフォルダ）をワークスペースとして取り込む。"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: gh.import_repo(req.repo, req.ref, req.path))
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(status_code=503, content=result)
    return result


@app.post("/github/push")
async def github_push(req: GithubPushRequest, _auth: None = Depends(require_auth)):
    """CODE：ワークスペースを新ブランチへ1コミットでプッシュ（+PR作成）。"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: gh.push_files(
            req.repo, req.base, req.branch, req.message,
            [f.model_dump() for f in req.files], req.create_pr, req.pr_title,
        ),
    )
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(status_code=503, content=result)
    return result


@app.get("/life/entries")
async def life_entries(category: Optional[str] = None, _auth: None = Depends(require_auth)):
    """ME：経験の箱の一覧（category で絞り込み可）。"""
    loop = asyncio.get_event_loop()
    items = await loop.run_in_executor(None, lambda: life.list_entries(category or ""))
    return {"items": items, "categories": life.CATEGORIES}


@app.post("/life/entries")
async def life_add(req: LifeEntryRequest, _auth: None = Depends(require_auth)):
    """ME：経験を1件保存。"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: life.add_entry(req.category, req.content, req.entry_date))
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(status_code=400, content=result)
    return result


@app.delete("/life/entries/{entry_id}")
async def life_delete(entry_id: str, _auth: None = Depends(require_auth)):
    """ME：経験を1件削除。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: life.delete_entry(entry_id))


@app.post("/life/extract")
async def life_extract(req: LifeExtractRequest, _auth: None = Depends(require_auth)):
    """ME：直近の相談会話から「経験の箱」候補を抽出（保存はユーザー確認後）。"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, lambda: life.extract_entries([t.model_dump() for t in req.turns])
    )
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(status_code=503, content=result)
    return result


@app.post("/life/chat")
async def life_chat(req: ChatRequest, _auth: None = Depends(require_auth)):
    """ME：経験の箱を常に踏まえた相談チャット（SSE）。
    通常 /chat と違いツール実行は無し — 純粋な相談相手として振る舞う。"""
    if llm.active_provider() == "none":
        async def err_stream():
            yield _sse({"error": "AI未設定です。Settings → KEYCHAIN に GEMINI_API_KEY か HUGGINGFACE_TOKEN を保存してください。"})
            yield _sse({"done": True})
        return _sse_response(err_stream())

    system_prompt = await asyncio.get_event_loop().run_in_executor(
        None, lambda: life.build_life_prompt(req.name or "")
    )
    prompt = build_conversation(system_prompt, req.history, req.message)

    async def event_stream():
        loop = asyncio.get_event_loop()

        def _next(it):
            try:
                return next(it)
            except StopIteration:
                return None

        try:
            it = llm.stream_text(prompt)
            while True:
                text = await loop.run_in_executor(None, _next, it)
                if text is None:
                    break
                if text:
                    yield _sse({"token": text})
            yield _sse({"done": True})
        except Exception as e:
            if config.is_zero_quota_429(e):
                yield _sse({"error": (
                    "Gemini無料枠の上限に達しました。KEYCHAIN に HUGGINGFACE_TOKEN を入れると"
                    "自動でHuggingFaceに切り替わります。"
                )})
            else:
                yield _sse({"error": f"life chat failed: {e}"})
            yield _sse({"done": True})

    return _sse_response(event_stream())


@app.get("/income/jobs")
async def income_jobs(status: Optional[str] = None, limit: int = 50, _auth: None = Depends(require_auth), _own: None = Depends(require_owner)):
    """副業ジョブの一覧（新しい順）。status で絞り込み可。Supabase未設定なら空。"""
    loop = asyncio.get_event_loop()
    items = await loop.run_in_executor(None, lambda: income.list_jobs(status, limit))
    return {"items": items}


@app.post("/income/enqueue")
async def income_enqueue(req: EnqueueRequest, _auth: None = Depends(require_auth), _own: None = Depends(require_owner)):
    """テーマから各媒体メタデータを生成し、承認待ち(pending)で積む。"""
    loop = asyncio.get_event_loop()
    job = await loop.run_in_executor(None, lambda: income.enqueue(req.theme))
    if isinstance(job, dict) and job.get("error"):
        return JSONResponse(status_code=503, content=job)
    return job


@app.post("/income/approve")
async def income_approve(req: JobActionRequest, _auth: None = Depends(require_auth), _own: None = Depends(require_owner)):
    ok = await asyncio.get_event_loop().run_in_executor(None, lambda: income.set_status(req.id, "approved"))
    return {"ok": ok}


@app.post("/income/reject")
async def income_reject(req: JobActionRequest, _auth: None = Depends(require_auth), _own: None = Depends(require_owner)):
    ok = await asyncio.get_event_loop().run_in_executor(None, lambda: income.set_status(req.id, "rejected"))
    return {"ok": ok}


# ── Document Vault（知識/RAG） ───────────────────────────────────
@app.get("/vault/notebooks")
async def vault_notebooks(_auth: None = Depends(require_auth)):
    items = await asyncio.get_event_loop().run_in_executor(None, vault.list_notebooks)
    return {"items": items}


@app.post("/vault/create")
async def vault_create(req: VaultCreateRequest, _auth: None = Depends(require_auth)):
    return await asyncio.get_event_loop().run_in_executor(None, lambda: vault.create_notebook(req.name))


@app.post("/vault/add")
async def vault_add(req: VaultAddRequest, _auth: None = Depends(require_auth)):
    return await asyncio.get_event_loop().run_in_executor(
        None, lambda: vault.add_text(req.notebook_id, req.title, req.content)
    )


@app.post("/vault/upload")
async def vault_upload(notebook_id: str = Form(...), file: UploadFile = File(...),
                       title: str = Form(""), _auth: None = Depends(require_auth)):
    """PDF等をアップロードし、テキストを抽出してノートブックに資料として入れる。

    ブラウザ側でPDFをテキストとして読むと文字化けするので、抽出はここで行う。
    """
    data = await file.read()
    name = file.filename or "file"
    ctype = file.content_type or ""
    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(None, lambda: fileread.extract_text(name, data, ctype))
    doc_title = (title or "").strip() or name.rsplit(".", 1)[0]
    if not (text or "").strip():
        return JSONResponse(status_code=400, content={
            "error": f"{name} からテキストを抽出できませんでした（画像PDFの可能性があります）"})
    res = await loop.run_in_executor(None, lambda: vault.add_text(notebook_id, doc_title, text))
    if isinstance(res, dict) and res.get("error"):
        return JSONResponse(status_code=400, content=res)
    return {"ok": True, "title": doc_title, "chars": len(text), "name": name}


@app.get("/vault/docs")
async def vault_docs(notebook_id: str, _auth: None = Depends(require_auth)):
    """ノートブック内の資料一覧（出典番号つき・本文は含まない）。"""
    res = await asyncio.get_event_loop().run_in_executor(
        None, lambda: vault.list_docs(notebook_id))
    if isinstance(res, dict) and res.get("error"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.post("/vault/docs/delete")
async def vault_doc_delete(req: VaultDocDeleteRequest, _auth: None = Depends(require_auth)):
    res = await asyncio.get_event_loop().run_in_executor(
        None, lambda: vault.delete_doc(req.notebook_id, req.title))
    if isinstance(res, dict) and res.get("error"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.post("/vault/query")
async def vault_query(req: VaultQueryRequest, _auth: None = Depends(require_auth)):
    return await asyncio.get_event_loop().run_in_executor(
        None, lambda: vault.query(req.notebook_id, req.question)
    )


@app.post("/vault/generate")
async def vault_generate(req: VaultGenerateRequest, _auth: None = Depends(require_auth)):
    """ノートブックの資料を根拠に文書(Markdown)を作成する。"""
    result = await asyncio.get_event_loop().run_in_executor(
        None, lambda: vault.generate_doc(req.notebook_id, req.instruction)
    )
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(status_code=503, content=result)
    return result


@app.post("/vault/diagram")
async def vault_diagram(req: VaultDiagramRequest, _auth: None = Depends(require_auth)):
    """資料から Mermaid 図（ロジックツリー等）を生成する。"""
    result = await asyncio.get_event_loop().run_in_executor(
        None, lambda: vault.generate_diagram(req.notebook_id, req.kind)
    )
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(status_code=503, content=result)
    return result


# ── プロアクティブ（今日のブリーフィング） ───────────────────────
@app.get("/briefing")
async def briefing(_auth: None = Depends(require_auth)):
    text = await asyncio.get_event_loop().run_in_executor(None, proactive.build_briefing)
    return {"text": text}


@app.get("/video/aspects")
async def video_aspects(_auth: None = Depends(require_auth)):
    """出力比率のプリセットと、この環境で字幕を焼けるかを返す。"""
    renderer = _load_renderer()
    presets = [
        {"key": "16:9", "w": 1280, "h": 720, "label": "横長（YouTube）"},
        {"key": "9:16", "w": 720, "h": 1280, "label": "縦型（Shorts / Reels / TikTok）"},
        {"key": "1:1", "w": 1080, "h": 1080, "label": "正方形（Instagramフィード）"},
    ]
    available, subs = False, False
    if renderer is not None:
        try:
            available = bool(renderer.is_available())
            # フォントが無い環境では日本語字幕が焼けない（□になる）ので正直に伝える
            subs = available and bool(renderer.font_path())
        except Exception:
            pass
        try:
            presets = [{"key": k, "w": v[0], "h": v[1], "label": v[2]}
                       for k, v in renderer.VIDEO_ASPECTS.items()]
        except Exception:
            pass
    return {"aspects": presets, "available": available, "subtitles_available": subs}


@app.post("/video/storyboard")
async def video_storyboard(req: StoryboardRequest, _auth: None = Depends(require_auth)):
    """テーマから絵コンテ（シーン割り＋ナレーション＋画のプロンプト）を作る。"""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(
        None, lambda: video_script.storyboard(req.topic, req.n, req.aspect, req.tone, req.style))
    if res.get("error"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.post("/video")
async def video(req: VideoRequest, _auth: None = Depends(require_auth)):
    """絵コンテ(scenes)から動画を生成する。リポジトリ root の renderer.py を再利用する。
    renderer / ffmpeg が使えない場合は 503 {"error": "video rendering unavailable"}。"""
    renderer = _load_renderer()
    if renderer is None:
        return JSONResponse(status_code=503, content={"error": "video rendering unavailable"})

    # ffmpeg が無ければ即座に縮退（renderer.is_available があれば利用）
    try:
        if hasattr(renderer, "is_available") and not renderer.is_available():
            return JSONResponse(status_code=503, content={"error": "video rendering unavailable"})
    except Exception:
        pass

    scenes = [{"narration": s.narration, "visual": s.visual} for s in req.scenes]
    image_prompt = req.image_prompt or ""

    try:
        loop = asyncio.get_event_loop()
        path = await loop.run_in_executor(
            None, lambda: renderer.render_forge_video(
                scenes, image_prompt, aspect=req.aspect, subtitles=req.subtitles)
        )
    except Exception:
        path = None

    if not path or not os.path.exists(path):
        return JSONResponse(status_code=503, content={"error": "video rendering unavailable"})

    try:
        with open(path, "rb") as f:
            data = f.read()
        return {"video_base64": base64.b64encode(data).decode("ascii")}
    except Exception:
        return JSONResponse(status_code=503, content={"error": "video rendering unavailable"})


# ── renderer.py（リポジトリ root）の遅延ロード ───────────────────
_renderer_module = None
_renderer_tried = False


def _load_renderer():
    """リポジトリ root の renderer.py を import する（api/ の親を sys.path に追加）。
    import できなければ None（絶対にraiseしない）。"""
    global _renderer_module, _renderer_tried
    if _renderer_module is not None:
        return _renderer_module
    if _renderer_tried:
        return None
    _renderer_tried = True
    try:
        parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if parent not in sys.path:
            sys.path.insert(0, parent)
        import renderer  # type: ignore
        _renderer_module = renderer
        return renderer
    except Exception:
        _renderer_module = None
        return None


# ── Tasks（アクティブタスク管理） ─────────────────────────────────

@app.get("/tasks")
async def get_tasks(status: Optional[str] = None, limit: int = 100,
                    _auth: None = Depends(require_auth)):
    """タスク一覧を返す。status パラメータで絞り込み可。"""
    loop = asyncio.get_event_loop()
    items = await loop.run_in_executor(None, lambda: tasks_module.list_tasks(status, limit))
    return {"items": items}


@app.post("/tasks")
async def create_task(req: TaskCreateRequest, _auth: None = Depends(require_auth)):
    """新しいタスクを作成する。"""
    loop = asyncio.get_event_loop()
    task = await loop.run_in_executor(
        None, lambda: tasks_module.create_task(req.title, req.content, req.status,
                                               req.priority, req.due, req.project)
    )
    if isinstance(task, dict) and task.get("error"):
        return JSONResponse(status_code=400, content=task)
    return task


@app.patch("/tasks/{task_id}")
async def update_task(task_id: str, req: TaskUpdateRequest,
                      _auth: None = Depends(require_auth)):
    """タスクのステータス・返答・内容・優先度・期限・プロジェクトを更新する。"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, lambda: tasks_module.update_task(task_id, req.status, req.response, req.content,
                                               req.priority, req.due, req.project)
    )
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(status_code=404, content=result)
    return result


@app.delete("/tasks/{task_id}")
async def delete_task(task_id: str, _auth: None = Depends(require_auth)):
    """タスクを削除する。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: tasks_module.delete_task(task_id))


# ── AI Studio（カスタムAI・ワークフロー） ──────────────────────────

@app.get("/studio/ais")
async def studio_list_ais(_auth: None = Depends(require_auth), _own: None = Depends(require_owner)):
    loop = asyncio.get_event_loop()
    return {"items": await loop.run_in_executor(None, studio.list_ais)}


@app.post("/studio/ais")
async def studio_create_ai(req: AiCreateRequest, _auth: None = Depends(require_auth), _own: None = Depends(require_owner)):
    loop = asyncio.get_event_loop()
    ai = await loop.run_in_executor(
        None, lambda: studio.create_ai(req.name, req.persona, req.model, req.rules)
    )
    if isinstance(ai, dict) and ai.get("error"):
        return JSONResponse(status_code=400, content=ai)
    return ai


@app.delete("/studio/ais/{ai_id}")
async def studio_delete_ai(ai_id: str, _auth: None = Depends(require_auth), _own: None = Depends(require_owner)):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: studio.delete_ai(ai_id))


@app.get("/studio/workflows")
async def studio_list_workflows(_auth: None = Depends(require_auth), _own: None = Depends(require_owner)):
    loop = asyncio.get_event_loop()
    return {"items": await loop.run_in_executor(None, studio.list_workflows)}


@app.post("/studio/workflows")
async def studio_create_workflow(req: WorkflowCreateRequest, _auth: None = Depends(require_auth), _own: None = Depends(require_owner)):
    loop = asyncio.get_event_loop()
    wf = await loop.run_in_executor(
        None, lambda: studio.create_workflow(req.name, req.steps)
    )
    if isinstance(wf, dict) and wf.get("error"):
        return JSONResponse(status_code=400, content=wf)
    return wf


@app.delete("/studio/workflows/{wf_id}")
async def studio_delete_workflow(wf_id: str, _auth: None = Depends(require_auth), _own: None = Depends(require_owner)):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: studio.delete_workflow(wf_id))


@app.post("/studio/workflows/{wf_id}/run")
async def studio_run_workflow(wf_id: str, req: WorkflowRunRequest,
                              _auth: None = Depends(require_auth),
                              _own: None = Depends(require_owner)):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, lambda: studio.run_workflow(wf_id, req.input)
    )
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(status_code=503, content=result)
    return result


# ── Autopilot（ゴール自動実行） ───────────────────────────────────

@app.get("/autopilot/missions")
async def autopilot_list(_auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    return {"items": await loop.run_in_executor(None, autopilot.list_missions)}


@app.post("/autopilot/missions")
async def autopilot_create(req: MissionCreateRequest, _auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    m = await loop.run_in_executor(None, lambda: autopilot.create_mission(req.goal, req.notify))
    if isinstance(m, dict) and m.get("error"):
        return JSONResponse(status_code=400, content=m)
    return m


@app.post("/autopilot/missions/{mission_id}/step")
async def autopilot_step(mission_id: str, _auth: None = Depends(require_auth)):
    """次の未完了ステップを1つ実行する（フロント or cron が繰り返し呼ぶ）。"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: autopilot.run_step(mission_id))
    if isinstance(result, dict) and result.get("error") and not result.get("mission"):
        return JSONResponse(status_code=404, content=result)
    return result


@app.delete("/autopilot/missions/{mission_id}")
async def autopilot_delete(mission_id: str, _auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: autopilot.delete_mission(mission_id))


@app.post("/notify")
async def notify_send(req: NotifyRequest, _auth: None = Depends(require_auth)):
    """設定済みチャンネル（LINE/Discord/Slack）へ通知を送る。未設定なら skipped。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: notify.notify_all(req.message))


# ── Automations（ノーコード自動化 / Zapier風） ────────────────────

@app.get("/automations")
async def automations_list(_auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    return {"items": await loop.run_in_executor(None, automations.list_flows)}


@app.post("/automations")
async def automations_create(req: AutomationCreateRequest, _auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    f = await loop.run_in_executor(
        None, lambda: automations.create_flow(req.name, req.trigger, req.steps)
    )
    if isinstance(f, dict) and f.get("error"):
        return JSONResponse(status_code=400, content=f)
    return f


@app.delete("/automations/{flow_id}")
async def automations_delete(flow_id: str, _auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: automations.delete_flow(flow_id))


@app.post("/automations/{flow_id}/run")
async def automations_run(flow_id: str, req: AutomationRunRequest,
                          _auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: automations.run_flow(flow_id, req.input))
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(status_code=404, content=result)
    return result


# ── Agenda（組み込みカレンダー / 予定） ───────────────────────────

@app.get("/agenda")
async def agenda_list(_auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    return {"items": await loop.run_in_executor(None, agenda.list_events)}


@app.post("/agenda")
async def agenda_add(req: AgendaAddRequest, _auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    ev = await loop.run_in_executor(
        None, lambda: agenda.add_event(req.title, req.date, req.time, req.note)
    )
    if isinstance(ev, dict) and ev.get("error"):
        return JSONResponse(status_code=400, content=ev)
    return ev


@app.post("/agenda/parse")
async def agenda_parse(req: AgendaParseRequest, _auth: None = Depends(require_auth)):
    """自然言語の予定文を解釈して登録する。"""
    loop = asyncio.get_event_loop()
    ev = await loop.run_in_executor(None, lambda: agenda.parse_and_add(req.text, req.today))
    if isinstance(ev, dict) and ev.get("error"):
        return JSONResponse(status_code=400, content=ev)
    return ev


@app.delete("/agenda/{event_id}")
async def agenda_delete(event_id: str, _auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: agenda.delete_event(event_id))


# ── Notifications（アプリ内通知） ─────────────────────────────────

@app.get("/notifications")
async def notifications_list(_auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    items = await loop.run_in_executor(None, notify.list_internal)
    unread = sum(1 for n in items if not n.get("read"))
    return {"items": items, "unread": unread}


@app.post("/notifications/read")
async def notifications_read(_auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, notify.mark_all_read)


# ── Board（Miro風ホワイトボード・複数ボード） ─────────────────────────

@app.get("/board")
async def board_get(_auth: None = Depends(require_auth)):
    """（旧API互換）最初のボードを返す。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, board.get_board)


@app.post("/board")
async def board_save(req: BoardSaveRequest, _auth: None = Depends(require_auth)):
    """（旧API互換）最初のボードを保存する。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: board.save_board(req.nodes, req.edges))


@app.get("/boards")
async def boards_list(_auth: None = Depends(require_auth)):
    """ボード一覧（メタのみ・更新順）。"""
    loop = asyncio.get_event_loop()
    return {"items": await loop.run_in_executor(None, board.list_boards)}


@app.post("/boards")
async def boards_create(req: BoardCreateRequest, _auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: board.create_board(req.name))


@app.get("/boards/{board_id}")
async def boards_get(board_id: str, _auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: board.get_board(board_id))
    if res.get("error"):
        return JSONResponse(status_code=404, content=res)
    return res


@app.post("/boards/{board_id}")
async def boards_save(board_id: str, req: BoardSaveRequest, _auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: board.save_board(req.nodes, req.edges, board_id))


@app.patch("/boards/{board_id}")
async def boards_rename(board_id: str, req: BoardRenameRequest, _auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: board.rename_board(board_id, req.name))


@app.post("/boards/{board_id}/duplicate")
async def boards_duplicate(board_id: str, _auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: board.duplicate_board(board_id))


@app.delete("/boards/{board_id}")
async def boards_delete(board_id: str, _auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: board.delete_board(board_id))


# ── Artifacts（エージェント生成物：ドキュメント / スプレッドシート） ──

@app.get("/artifacts")
async def artifacts_list(_auth: None = Depends(require_auth)):
    """生成物のメタデータ一覧（content は含めない・新しい順）。"""
    loop = asyncio.get_event_loop()
    return {"items": await loop.run_in_executor(None, artifacts.list_artifacts)}


@app.get("/artifacts/{artifact_id}")
async def artifacts_get(artifact_id: str, _auth: None = Depends(require_auth)):
    """1件の完全な内容（content 込み）。ダウンロードに使う。"""
    loop = asyncio.get_event_loop()
    art = await loop.run_in_executor(None, lambda: artifacts.get(artifact_id))
    if not art:
        return JSONResponse(status_code=404, content={"error": "artifact not found"})
    return art


@app.patch("/artifacts/{artifact_id}")
async def artifacts_update(artifact_id: str, req: ArtifactUpdateRequest, _auth: None = Depends(require_auth)):
    """成果物の内容/タイトルを更新（スライドのテーマ変更など）。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: artifacts.update(artifact_id, req.content, req.title))


@app.delete("/artifacts/{artifact_id}")
async def artifacts_delete(artifact_id: str, _auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: artifacts.delete(artifact_id))


# ── Admin：DB永続化（テーブル自動作成） ──────────────────────────────

@app.get("/admin/db/status")
async def admin_db_status(_auth: None = Depends(require_auth)):
    """必要テーブルの存在状況（永続化の可否を判断するUI用）。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, migrate.table_status)


@app.post("/admin/migrate")
async def admin_migrate(_auth: None = Depends(require_auth)):
    """SUPABASE_DB_URL を使って supabase_schema.sql を実行（テーブル自動作成）。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, migrate.run_migrations)


# ── ファイル読み取り（PDF / テキスト → 本文抽出） ──────────────────────

@app.post("/file/extract")
async def file_extract(file: UploadFile = File(...), _auth: None = Depends(require_auth)):
    """アップロードされたファイルからテキストを抽出して返す（PDF/テキスト対応）。"""
    data = await file.read()
    name = file.filename or "file"
    ctype = file.content_type or ""
    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(None, lambda: fileread.extract_text(name, data, ctype))
    return {"name": name, "chars": len(text), "text": text}


# ── 定期実行（スケジューラ） ──────────────────────────────────────────

@app.get("/scheduler")
async def scheduler_list(_auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    return {"items": await loop.run_in_executor(None, scheduler.list_schedules)}


@app.post("/scheduler")
async def scheduler_add(req: ScheduleRequest, _auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, lambda: scheduler.add(req.instruction, req.time, req.days, req.automation_id))


@app.delete("/scheduler/{schedule_id}")
async def scheduler_delete(schedule_id: str, _auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: scheduler.delete(schedule_id))


# ── Programmatic SEO（掛け合わせキーワードの大量ページ） ──────────────

@app.post("/pseo/plan")
async def pseo_plan(req: PseoPlanRequest, _auth: None = Depends(require_auth)):
    """軸の掛け合わせでページ計画を返す（生成はしない・プレビュー用）。"""
    loop = asyncio.get_event_loop()
    items = await loop.run_in_executor(None, lambda: pseo.plan_pages(req.axes, req.template, req.limit))
    return {"items": items, "count": len(items)}


@app.post("/pseo/generate")
async def pseo_generate(req: PseoPlanRequest, _auth: None = Depends(require_auth)):
    """計画→本文生成→draft保存を一括実行（公開はされない）。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: pseo.generate_batch(req.axes, req.template, req.limit))


@app.get("/pseo/pages")
async def pseo_pages(status: Optional[str] = None, _auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    items = await loop.run_in_executor(None, lambda: pseo.list_pages(status))
    return {"items": items}


@app.patch("/pseo/pages/{slug}")
async def pseo_set_status(slug: str, req: PseoStatusRequest, _auth: None = Depends(require_auth)):
    """承認 / 却下（セミオート運用：承認したページだけ公開される）。"""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: pseo.set_status(slug, req.status))
    if res.get("error"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.delete("/pseo/pages/{slug}")
async def pseo_delete(slug: str, _auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: pseo.delete_page(slug))


@app.get("/pseo/public/{slug}")
async def pseo_public(slug: str):
    """公開ページ用（認証不要）。承認済み以外は404にして未公開を守る。"""
    loop = asyncio.get_event_loop()
    page = await loop.run_in_executor(None, lambda: pseo.get_page(slug))
    if not page or page.get("status") != "approved":
        return JSONResponse(status_code=404, content={"error": "not found"})
    return page


@app.get("/pseo/sitemap")
async def pseo_sitemap():
    """承認済みページのみのサイトマップ（認証不要）。"""
    loop = asyncio.get_event_loop()
    return {"items": await loop.run_in_executor(None, pseo.sitemap)}


# ── LP / HP 作成（1ファイル完結HTML・反復デザイン） ────────────────────

@app.post("/lp/generate")
async def lp_generate(req: LpGenerateRequest, _auth: None = Depends(require_auth)):
    """LPを生成する。current を渡すと「その内容を指示どおり直す」改善モード。"""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(
        None, lambda: lp_mod.generate(req.brief, req.style, req.sections, req.current, req.kind))
    if res.get("error"):
        return JSONResponse(status_code=400, content=res)
    if req.save:
        meta = await loop.run_in_executor(None, lambda: lp_mod.save_as_artifact(res["title"], res["html"]))
        res["artifact"] = meta
    return res


@app.get("/lp/styles")
async def lp_styles(_auth: None = Depends(require_auth)):
    return {"styles": [{"key": k, "note": v} for k, v in lp_mod.STYLES.items()]}


# ── 画像スタジオ（アスペクト比・複数枚・履歴） ─────────────────────────

@app.get("/image/aspects")
async def image_aspects(_auth: None = Depends(require_auth)):
    return {"aspects": [{"key": k, "w": v[0], "h": v[1], "label": v[2]}
                        for k, v in imagegen.ASPECTS.items()]}


@app.get("/image/engines")
async def image_engines(_auth: None = Depends(require_auth)):
    """選べる生成エンジン（無料 / HFの割り当てモデル）と現在使えるか。"""
    return {"engines": imagegen.engines()}


@app.post("/image/generate")
async def image_generate(req: ImageGenerateRequest, request: Request,
                         _auth: None = Depends(require_auth)):
    """同じ指示で複数バリエーションを作る。save=Trueで生成物（履歴）に保存。"""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(
        None, lambda: imagegen.generate_variants(req.prompt, req.n, req.aspect,
                                                 req.offset, req.engine))
    if res.get("error"):
        return JSONResponse(status_code=400, content=res)
    # 履歴に保存する前に絶対URLへ直す（保存後だと相対URLが残ってしまう）
    for img in res.get("images", []):
        img["url"] = _abs_media_url(request, img.get("url", ""))
    if req.save:
        def _save():
            import artifacts
            saved = []
            for i, img in enumerate(res["images"], start=1):
                title = f"{req.prompt[:40]}" + (f" ({i})" if len(res["images"]) > 1 else "")
                saved.append(artifacts.create("image", title, img["url"], "image/url"))
            return saved
        res["artifacts"] = await loop.run_in_executor(None, _save)
    return res


# ── SNS投稿サポート（Instagram / X） ──────────────────────────────────

@app.get("/sns/platforms")
async def sns_platforms(_auth: None = Depends(require_auth)):
    return {"platforms": [{"key": k, **v} for k, v in sns_mod.PLATFORMS.items()]}


@app.post("/sns/generate")
async def sns_generate(req: SnsGenerateRequest, _auth: None = Depends(require_auth)):
    """SNS投稿案を複数生成する（自動投稿はしない・コピーして使う）。"""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(
        None, lambda: sns_mod.generate_posts(req.platform, req.topic, req.n, req.tone, req.promo, req.thread))
    if res.get("error"):
        return JSONResponse(status_code=400, content=res)
    if req.with_images:
        res["posts"] = await loop.run_in_executor(
            None, lambda: [sns_mod.with_image(p) for p in res["posts"]])
    return res


# ── ニュースレター（⑤ リスト取得 → 定期配信） ────────────────────────

@app.post("/newsletter/subscribe")
async def newsletter_subscribe(req: SubscribeRequest):
    """公開フォームからの購読登録（認証不要）。確認メールを送るまで配信しない。"""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: newsletter.subscribe(req.email, req.source))
    if res.get("error"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.get("/newsletter/confirm")
async def newsletter_confirm(token: str = ""):
    """確認リンク（メール内から開かれる・認証不要）。"""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: newsletter.confirm(token))
    ok = not res.get("error")
    msg = "購読を確定しました。ありがとうございます。" if ok else res["error"]
    return HTMLResponse(
        f"<div style='font-family:sans-serif;text-align:center;margin-top:14%'>"
        f"<h2>{'✓ 登録完了' if ok else '⚠ エラー'}</h2><p>{msg}</p></div>",
        status_code=200 if ok else 400,
    )


@app.get("/newsletter/unsubscribe")
async def newsletter_unsubscribe(token: str = ""):
    """配信停止リンク（全配信メールに記載・認証不要）。"""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: newsletter.unsubscribe(token))
    ok = not res.get("error")
    msg = "配信を停止しました。今後お送りしません。" if ok else res["error"]
    return HTMLResponse(
        f"<div style='font-family:sans-serif;text-align:center;margin-top:14%'>"
        f"<h2>{'配信停止しました' if ok else '⚠ エラー'}</h2><p>{msg}</p></div>",
        status_code=200 if ok else 400,
    )


@app.get("/newsletter/subscribers")
async def newsletter_subscribers(status: Optional[str] = None, _auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    items = await loop.run_in_executor(None, lambda: newsletter.list_subscribers(status))
    st = await loop.run_in_executor(None, newsletter.stats)
    return {"items": items, "stats": st}


@app.get("/newsletter/issues")
async def newsletter_issues(_auth: None = Depends(require_auth)):
    loop = asyncio.get_event_loop()
    return {"items": await loop.run_in_executor(None, newsletter.list_issues)}


@app.post("/newsletter/issues")
async def newsletter_draft(req: IssueDraftRequest, _auth: None = Depends(require_auth)):
    """配信の下書きを作る（topic指定でAIが本文を執筆）。送信はしない。"""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: newsletter.draft_issue(req.subject, req.body, req.topic))
    if res.get("error"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.post("/newsletter/issues/{issue_id}/send")
async def newsletter_send(issue_id: str, req: IssueSendRequest, _auth: None = Depends(require_auth)):
    """確認済み購読者へ送信（test_to 指定でテスト送信のみ）。"""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(None, lambda: newsletter.send_issue(issue_id, req.test_to))
    if res.get("error"):
        return JSONResponse(status_code=400, content=res)
    return res


# ── note（非公式APIでの下書き投稿・既定OFF） ──────────────────────────

@app.get("/note/status")
async def note_status(_auth: None = Depends(require_auth)):
    """note自動投稿の有効/無効と理由（認証情報の値は返さない）。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, note_client.status)


@app.post("/note/draft")
async def note_draft(req: NoteDraftRequest, _auth: None = Depends(require_auth)):
    """noteに下書きを作成（ALLOW_NOTE_AUTOPOST=1 のときのみ実行）。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: note_client.create_draft(req.title, req.markdown))


@app.get("/compliance/policy")
async def compliance_policy(_auth: None = Depends(require_auth)):
    """送信先ごとの配信ポリシー（既定ブロック／オプトインで解除済み）を返す。"""
    loop = asyncio.get_event_loop()
    return {"platforms": await loop.run_in_executor(None, compliance.policy_report)}


# ── Keep-Alive（Supabaseの自動一時停止を防ぐ） ────────────────────────

@app.get("/keepalive")
async def keepalive_get():
    """DBを軽く触って「活動あり」にする。外部cron（GitHub Actions等）から叩く。
    認証不要（副作用は1行のupsertのみ）。/health より確実にSupabaseを起こし続ける。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, keepalive_mod.ping)


@app.get("/keepalive/status")
async def keepalive_status(_auth: None = Depends(require_auth)):
    """最後に実行した時刻と結果（UI表示用）。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, keepalive_mod.status)


@app.post("/scheduler/tick")
async def scheduler_tick():
    """外部cron（無料のcron-job.org等）から叩く実行トリガ。認証不要（副作用は登録済み定期のみ）。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, scheduler.tick)


# ── Google 連携（OAuth：スプレッドシート / ドキュメント） ──────────────
# start / callback はブラウザ遷移 & Google からのリダイレクトなので認証を付けない
# （OAuth 自体が本人確認になる）。status は認証必須。

def _google_redirect(request: Request) -> str:
    """明示設定を最優先。無ければリクエストから callback URL を組み立てる。"""
    base = str(request.base_url).rstrip("/")
    # プロキシ(Render/Vercel)越しは https を強制（localhost は除く）。
    if base.startswith("http://") and "localhost" not in base and "127.0.0.1" not in base:
        base = "https://" + base[len("http://"):]
    return gservice.redirect_uri(default=f"{base}/google/auth/callback")


@app.get("/google/status")
async def google_status(_auth: None = Depends(require_auth)):
    """Google連携の状態（設定済み / 接続済み）を返す。"""
    return gservice.status()


@app.get("/google/auth/start")
async def google_auth_start(request: Request):
    """Googleの同意画面へリダイレクト（KEYCHAINにCLIENT_ID/SECRETが必要）。"""
    if not gservice.configured():
        return HTMLResponse(
            "<h3>Google未設定です</h3><p>Settings → KEYCHAIN で "
            "GOOGLE_CLIENT_ID と GOOGLE_CLIENT_SECRET を設定してください。</p>",
            status_code=400,
        )
    return RedirectResponse(gservice.auth_url(_google_redirect(request)))


@app.get("/google/auth/callback")
async def google_auth_callback(request: Request, code: str = "", error: str = ""):
    """Googleからのコールバック。コードを refresh_token に交換して保存する。"""
    if error:
        return HTMLResponse(f"<h3>接続に失敗しました</h3><p>{error}</p>")
    redirect = _google_redirect(request)
    res = await asyncio.get_event_loop().run_in_executor(None, lambda: gservice.exchange_code(code, redirect))
    if res.get("ok"):
        return HTMLResponse(
            "<div style='font-family:sans-serif;text-align:center;margin-top:15%'>"
            "<h2>✓ Google連携が完了しました</h2>"
            "<p>このタブを閉じて、アプリに戻ってください。</p></div>"
        )
    return HTMLResponse(
        "<div style='font-family:sans-serif;text-align:center;margin-top:12%'>"
        f"<h3>接続に失敗しました</h3><p>{res.get('error')}</p>"
        f"<p style='color:#888;font-size:13px'>Google Cloud の『承認済みのリダイレクトURI』が<br>"
        f"<code>{redirect}</code><br>と完全一致しているか確認してください。</p></div>"
    )


@app.post("/google/disconnect")
async def google_disconnect(_auth: None = Depends(require_auth)):
    return gservice.disconnect()


@app.get("/slides/layouts")
async def slides_layouts(_auth: None = Depends(require_auth)):
    """スライド1枚ごとの編集UIが使うレイアウト定義（使うフィールドと表示名）。"""
    return {
        "layouts": [
            {"key": k, "label": slides_mod.LAYOUT_LABELS.get(k, k),
             "fields": slides_mod.LAYOUT_FIELDS.get(k, [])}
            for k in slides_mod.LAYOUTS
        ],
        "themes": slides_mod.THEMES,
    }


@app.post("/slides/revise")
async def slides_revise(req: SlideReviseRequest, _auth: None = Depends(require_auth)):
    """スライド1枚だけをAIで書き直す（他の枚は変えない）。"""
    loop = asyncio.get_event_loop()
    res = await loop.run_in_executor(
        None, lambda: slides_mod.revise_slide(
            req.slide, req.instruction, req.deck_title, req.layout, req.context))
    if res.get("error"):
        return JSONResponse(status_code=400, content=res)
    return res


@app.post("/slides/google")
async def slides_to_google(req: SlidesExportRequest, _auth: None = Depends(require_auth)):
    """スライド構成（title + slides[] + theme）を Google スライドに変換して URL を返す。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: gservice.create_presentation(req.title, req.slides, req.theme))


# ── Home（コックピット集約サマリー） ──────────────────────────────

@app.get("/home/summary")
async def home_summary(_auth: None = Depends(require_auth)):
    """ホーム画面のKPIを1回で集約して返す（各機能の進捗）。"""
    loop = asyncio.get_event_loop()

    def _gather():
        # タスク
        try:
            all_tasks = tasks_module.list_tasks(None, 1000)
        except Exception:
            all_tasks = []
        task_counts = {}
        for t in all_tasks:
            s = t.get("status") or "pending"
            task_counts[s] = task_counts.get(s, 0) + 1
        # ミッション
        try:
            missions = autopilot.list_missions(1000)
        except Exception:
            missions = []
        active_missions = sum(1 for m in missions if m.get("status") == "active")
        # 自動化
        try:
            flows = automations.list_flows(1000)
        except Exception:
            flows = []
        # 副業
        try:
            pending_income = len(income.list_jobs("pending", 1000))
        except Exception:
            pending_income = 0
        # 予定
        try:
            events = agenda.list_events(1000)
        except Exception:
            events = []
        # 通知
        try:
            unread = notify.unread_count()
        except Exception:
            unread = 0
        return {
            "tasks": {"total": len(all_tasks), "by_status": task_counts,
                      "open": task_counts.get("pending", 0) + task_counts.get("in_progress", 0)},
            "missions": {"total": len(missions), "active": active_missions},
            "automations": {"total": len(flows)},
            "income": {"pending": pending_income},
            "events": {"total": len(events), "upcoming": events[:5]},
            "notifications": {"unread": unread},
        }

    return await loop.run_in_executor(None, _gather)


# ── Evolve（セルフ進化：指示→提案） ──────────────────────────────

@app.post("/evolve/propose")
async def evolve_propose(req: EvolveRequest, _auth: None = Depends(require_auth), _own: None = Depends(require_owner)):
    """自然言語の指示から、app/custom_ai/automation/answer の提案を返す。"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: evolve.propose(req.instruction))
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(status_code=503, content=result)
    return result


# ── Keychain（APIキー保管庫） ────────────────────────────────────

@app.get("/keys")
async def list_keys(_auth: None = Depends(require_auth)):
    """保存済みキーを「マスク値 + 設定有無」で返す（フル値は決して返さない）。"""
    loop = asyncio.get_event_loop()
    return {"items": await loop.run_in_executor(None, keychain.list_keys)}


@app.post("/keys")
async def set_key(req: KeySetRequest, _auth: None = Depends(require_auth)):
    """キーを保存/更新する。"""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: keychain.set_key(req.name, req.value))
    if isinstance(result, dict) and result.get("error"):
        return JSONResponse(status_code=400, content=result)
    return result


@app.delete("/keys/{name}")
async def delete_key(name: str, _auth: None = Depends(require_auth)):
    """キーを削除する。"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: keychain.delete_key(name))


# ローカル実行用エントリ（uvicorn main:app --reload と同等）
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
