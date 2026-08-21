# llm.py — AIプロバイダ抽象化（Gemini / HuggingFace / OpenAI）＋自動フォールバック。
# どのモード(chat/me/forge/code/…)も、Geminiに固定せずここ経由でテキスト生成する。
# Geminiが429(無料枠0)等で失敗したら、HuggingFace(設定があれば)へ自動で切替える。
#
# HuggingFace は OpenAI 互換ルーター(router.huggingface.co)を使用。
#   - トークン: KEYCHAIN の HUGGINGFACE_TOKEN（または環境変数）
#   - モデル:   KEYCHAIN/env の HF_MODEL（既定 Llama-3.3-70B-Instruct）
#   - プロバイダ選択: LLM_PROVIDER = gemini | huggingface | auto(既定)
#     auto は「HFトークンがあればHF優先(ユーザーが意図的に入れたため)、無ければGemini」。
#   - 多くのHFプロバイダは入力を学習に使わない（プライバシー用途に向く）。
import json
import os

import requests

import config
import keychain

HF_ROUTER = "https://router.huggingface.co/v1/chat/completions"
# OpenAI も同じ chat/completions の形なので、同じ読み取りコードを使い回せる。
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_HF_MODEL = "meta-llama/Llama-3.3-70B-Instruct"
# CODEモード用のコーディング特化モデル（HF）。KEYCHAIN/env の CODE_MODEL で上書き可。
DEFAULT_CODE_MODEL = "Qwen/Qwen2.5-Coder-32B-Instruct"


def _kc(name: str) -> str:
    """KEYCHAIN → 環境変数 の順で設定値を取る。"""
    try:
        v = keychain.get_key(name)
        if v:
            return v
    except Exception:
        pass
    return os.environ.get(name, "").strip()


def _hf_token() -> str:
    return _kc("HUGGINGFACE_TOKEN")


def _openai_token() -> str:
    return _kc("OPENAI_API_KEY")


def openai_model() -> str:
    return _kc("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL


def hf_model() -> str:
    return _kc("HF_MODEL") or DEFAULT_HF_MODEL


def code_model() -> str:
    """CODEモード用モデル（HF時）。CODE_MODEL 指定 → HF_MODEL → コーディング既定。"""
    return _kc("CODE_MODEL") or _kc("HF_MODEL") or DEFAULT_CODE_MODEL


def _provider_pref() -> str:
    return (_kc("LLM_PROVIDER") or "auto").strip().lower()


def providers_in_order() -> list:
    """使用を試みるプロバイダを優先順で返す（設定済みのもののみ）。

    OpenAI は明示的に選んだときだけ先頭に来る。従量課金なので、
    鍵を入れただけで勝手に使い始めると請求が発生する。
    ただし他が全部落ちたときの最後の受け皿には入れる（無言で止まるよりよい）。
    """
    hf = bool(_hf_token())
    gem = config.gemini_configured()
    oai = bool(_openai_token())
    pref = _provider_pref()
    if pref == "huggingface":
        order = ["huggingface", "gemini", "openai"]
    elif pref == "gemini":
        order = ["gemini", "huggingface", "openai"]
    elif pref == "openai":
        order = ["openai", "gemini", "huggingface"]
    else:  # auto
        order = (["huggingface", "gemini"] if hf else ["gemini", "huggingface"]) + ["openai"]
    avail = {"huggingface": hf, "gemini": gem, "openai": oai}
    return [p for p in order if avail.get(p)]


def active_provider() -> str:
    order = providers_in_order()
    return order[0] if order else "none"


# ── Gemini ────────────────────────────────────────────────────────
def _stream_gemini(prompt):
    stream = config.generate_resilient(prompt, stream=True)
    if stream is None:
        raise RuntimeError("gemini not configured")
    for chunk in stream:
        t = getattr(chunk, "text", None)
        if t:
            yield t


def _gen_gemini(prompt) -> str:
    resp = config.generate_resilient(prompt)
    if resp is None:
        raise RuntimeError("gemini not configured")
    return getattr(resp, "text", "") or ""


# ── HuggingFace (OpenAI互換ルーター) ──────────────────────────────
def _hf_messages(prompt):
    return [{"role": "user", "content": prompt if isinstance(prompt, str) else str(prompt)}]


def _stream_chat_completions(url: str, token: str, model: str, prompt, label: str):
    """OpenAI互換の chat/completions を逐次読む。HFもOpenAIも同じ形。"""
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"model": model, "messages": _hf_messages(prompt), "stream": True, "max_tokens": 1800},
        stream=True,
        timeout=120,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"{label} {resp.status_code}: {resp.text[:300]}")
    for raw in resp.iter_lines():
        if not raw:
            continue
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            obj = json.loads(data)
            delta = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
            if delta:
                yield delta
        except Exception:
            continue


def _stream_openai(prompt):
    token = _openai_token()
    if not token:
        raise RuntimeError("OPENAI_API_KEY not set")
    yield from _stream_chat_completions(OPENAI_URL, token, openai_model(), prompt, "OpenAI")


def _gen_openai(prompt, max_tokens=2200) -> str:
    token = _openai_token()
    if not token:
        raise RuntimeError("OPENAI_API_KEY not set")
    r = requests.post(
        OPENAI_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"model": openai_model(), "messages": _hf_messages(prompt), "max_tokens": max_tokens},
        timeout=180,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
    return ((r.json().get("choices") or [{}])[0].get("message", {}).get("content")) or ""


def _stream_hf(prompt):
    token = _hf_token()
    if not token:
        raise RuntimeError("HUGGINGFACE_TOKEN not set")
    resp = requests.post(
        HF_ROUTER,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"model": hf_model(), "messages": _hf_messages(prompt), "stream": True, "max_tokens": 1800},
        stream=True,
        timeout=120,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"HuggingFace {resp.status_code}: {resp.text[:300]}")
    for raw in resp.iter_lines():
        if not raw:
            continue
        line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            obj = json.loads(data)
            delta = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
            if delta:
                yield delta
        except Exception:
            continue


def _gen_hf(prompt, model=None, max_tokens=2200) -> str:
    token = _hf_token()
    if not token:
        raise RuntimeError("HUGGINGFACE_TOKEN not set")
    r = requests.post(
        HF_ROUTER,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"model": model or hf_model(), "messages": _hf_messages(prompt), "max_tokens": max_tokens},
        timeout=180,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"HuggingFace {r.status_code}: {r.text[:300]}")
    return ((r.json().get("choices") or [{}])[0].get("message", {}).get("content")) or ""


# ── 公開API（プロバイダ横断＋フォールバック） ───────────────────────
def stream_text(prompt):
    """トークンを逐次 yield する。最初の1トークンが出る前に失敗したら次の
    プロバイダへフォールバックする（例: Gemini 429 → HuggingFace）。"""
    order = providers_in_order()
    if not order:
        raise RuntimeError("AIプロバイダ未設定（GEMINI_API_KEY / HUGGINGFACE_TOKEN / OPENAI_API_KEY のいずれかを設定してください）")
    last_err = None
    for prov in order:
        gen = (_stream_gemini(prompt) if prov == "gemini"
               else _stream_openai(prompt) if prov == "openai"
               else _stream_hf(prompt))
        try:
            first = next(gen)
        except StopIteration:
            return
        except Exception as e:
            last_err = e
            continue  # このプロバイダは開始前に失敗 → 次へ
        yield first
        for tok in gen:
            yield tok
        return
    raise last_err or RuntimeError("全プロバイダで生成に失敗しました")


def generate_text(prompt, hf_model_override=None, max_tokens=2200) -> str:
    """非ストリームでテキストを1回生成（フォールバック付き）。
    hf_model_override: HF使用時に使うモデル（CODEモードのコーディング特化等）。"""
    order = providers_in_order()
    if not order:
        raise RuntimeError("AIプロバイダ未設定（GEMINI_API_KEY / HUGGINGFACE_TOKEN / OPENAI_API_KEY のいずれかを設定してください）")
    last_err = None
    for prov in order:
        try:
            if prov == "gemini":
                return _gen_gemini(prompt)
            if prov == "openai":
                return _gen_openai(prompt, max_tokens=max_tokens)
            return _gen_hf(prompt, model=hf_model_override, max_tokens=max_tokens)
        except Exception as e:
            last_err = e
            continue
    raise last_err or RuntimeError("全プロバイダで生成に失敗しました")
