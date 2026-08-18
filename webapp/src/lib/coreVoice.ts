/**
 * コアの喋り方をまとめたところ。読み上げが要る画面は必ずここを通す。
 *
 * 以前は Chat と Briefing がそれぞれ speak() を直接呼んでいて、
 *   ・記号や絵文字をそのまま読み上げていた
 *   ・設定で選んだ声が使われていなかった（常に端末の最初の日本語音声）
 *   ・返答を全部受け取ってから読み始めるので、長い返答ほど黙る時間が長い
 * という状態だった。読み上げの決まりを1か所に集めて、全部の画面で同じに
 * なるようにしている。
 *
 * 声の出どころは2つ:
 *   browser … 端末に入っている音声。すぐ鳴る（通信なし）。品質は端末次第
 *   server  … サーバーの edge-tts。なめらかで端末差が無いが、通信が要る
 * どちらも駄目なときは黙って諦めるのではなく、もう一方へ倒す。
 */
"use client";

import { tts } from "@/lib/api";
import { speakableText, splitForSpeech } from "@/lib/speech";
import {
  hasUsableVoice,
  isSpeechSynthesisSupported,
  playBase64AudioControllable,
  speakSequence,
  stopSpeaking,
} from "@/lib/voice";

export type VoiceEngine = "browser" | "server";

export interface CoreVoiceSettings {
  engine: VoiceEngine;
  /** 端末の音声名（SpeechSynthesisVoice.name）。browser のとき使う。 */
  browserVoice?: string;
  /** edge-tts の音声名（ja-JP-NanamiNeural など）。server のとき使う。 */
  serverVoice?: string;
  /** 話す速さ。1.0 が等倍。 */
  rate: number;
  /** 声の高さ。1.0 が標準。 */
  pitch: number;
}

export const DEFAULT_VOICE_SETTINGS: CoreVoiceSettings = {
  engine: "browser",
  serverVoice: "ja-JP-NanamiNeural",
  rate: 1.0,
  pitch: 1.0,
};

/* ── 保存先 ───────────────────────────────────────────────────────────
   設定画面と、設定を持たない画面（ブリーフィングなど）の両方から読むので、
   キーはここに置いて1か所にする。別々に書くと片方だけ古い声で喋る。      */
export const LS_VOICE_ENGINE = "forge_voice_engine";
export const LS_BROWSER_VOICE = "forge_browser_voice";
export const LS_TTS_VOICE = "forge_tts_voice";
export const LS_TTS_RATE = "forge_tts_rate";
export const LS_TTS_PITCH = "forge_tts_pitch";

/**
 * 保存値を数値にする。未保存・空・数値でない場合は既定値。
 *
 * Number(null) は 0 になる（NaN ではない）ので、そのまま範囲に押し込むと
 * 未設定の人がいきなり最低速（0.5倍）になってしまう。ここで必ず既定へ倒す。
 */
function readNumber(key: string, lo: number, hi: number, fallback: number): number {
  const raw = localStorage.getItem(key);
  if (raw === null || raw.trim() === "") return fallback;
  const n = Number(raw);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(hi, Math.max(lo, n));
}

export function loadVoiceSettings(): CoreVoiceSettings {
  if (typeof window === "undefined") return { ...DEFAULT_VOICE_SETTINGS };
  try {
    const engine = localStorage.getItem(LS_VOICE_ENGINE) === "server" ? "server" : "browser";
    return {
      engine,
      browserVoice: localStorage.getItem(LS_BROWSER_VOICE) || undefined,
      serverVoice: localStorage.getItem(LS_TTS_VOICE) || DEFAULT_VOICE_SETTINGS.serverVoice,
      rate: readNumber(LS_TTS_RATE, 0.5, 2, DEFAULT_VOICE_SETTINGS.rate),
      pitch: readNumber(LS_TTS_PITCH, 0.5, 1.5, DEFAULT_VOICE_SETTINGS.pitch),
    };
  } catch {
    return { ...DEFAULT_VOICE_SETTINGS };
  }
}

export function saveVoiceSettings(s: CoreVoiceSettings): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(LS_VOICE_ENGINE, s.engine);
    localStorage.setItem(LS_BROWSER_VOICE, s.browserVoice ?? "");
    localStorage.setItem(LS_TTS_VOICE, s.serverVoice ?? "");
    localStorage.setItem(LS_TTS_RATE, String(s.rate));
    localStorage.setItem(LS_TTS_PITCH, String(s.pitch));
  } catch { /* ignore */ }
}

export interface SpeakHandlers {
  onStart?: () => void;
  onEnd?: () => void;
}

/** 止めるための関数。 */
export type CancelSpeech = () => void;

/** rate(0.5〜2.0) を edge-tts の "+20%" 形式へ。 */
export function rateToPercent(rate: number): string {
  const pct = Math.round(((rate || 1) - 1) * 100);
  return `${pct >= 0 ? "+" : ""}${pct}%`;
}

/** pitch(0.5〜1.5) を edge-tts の "+10Hz" 形式へ。標準を 0Hz とみなす。 */
export function pitchToHz(pitch: number): string {
  const hz = Math.round(((pitch || 1) - 1) * 50);
  return `${hz >= 0 ? "+" : ""}${hz}Hz`;
}

/**
 * 実際に使える出どころを決める。
 *
 * 「speechSynthesis はあるが声が1つも入っていない」端末があり、そのまま
 * browser を選ぶと無音になる。設定がどうであれ、鳴らないほうは選ばない。
 */
export function resolveEngine(s: CoreVoiceSettings, apiAvailable: boolean): VoiceEngine {
  const browserOk = isSpeechSynthesisSupported() && hasUsableVoice("ja-JP");
  if (s.engine === "server") return apiAvailable ? "server" : "browser";
  return browserOk ? "browser" : apiAvailable ? "server" : "browser";
}

/**
 * 読み上げる。文ごとに分けて順に流すので、長い返答でも最初の文からすぐ
 * 喋り始められる。サーバー音声のときは次の文を先読みして間を空けない。
 */
export function speakCore(
  raw: string,
  settings: CoreVoiceSettings,
  handlers: SpeakHandlers = {},
  apiAvailable = true,
): CancelSpeech {
  const chunks = splitForSpeech(speakableText(raw));
  if (!chunks.length) { handlers.onEnd?.(); return () => {}; }

  const engine = resolveEngine(settings, apiAvailable);
  if (engine === "browser") {
    stopSpeaking();
    return speakSequence(chunks, {
      lang: "ja-JP",
      voiceName: settings.browserVoice,
      rate: settings.rate,
      pitch: settings.pitch,
      onStart: handlers.onStart,
      onEnd: handlers.onEnd,
    });
  }
  return speakViaServer(chunks, settings, handlers);
}

/**
 * サーバー音声で順に鳴らす。
 *
 * 1文めを鳴らしている間に2文めを取りに行く（先読み）。全部まとめて1回で
 * 合成すると、長い返答ほど最初の音が出るまで待たされるため。
 * 取得に失敗した文は端末の音声で代わりに読む（黙るよりはよい）。
 */
function speakViaServer(
  chunks: string[],
  settings: CoreVoiceSettings,
  handlers: SpeakHandlers,
): CancelSpeech {
  let cancelled = false;
  let stopCurrent: () => void = () => {};
  const rate = rateToPercent(settings.rate);
  const pitch = pitchToHz(settings.pitch);

  const fetchAudio = (text: string): Promise<string> =>
    tts({ text, voice: settings.serverVoice, rate, pitch }).catch(() => "");

  void (async () => {
    let started = false;
    let pending: Promise<string> | null = fetchAudio(chunks[0]);
    for (let i = 0; i < chunks.length; i++) {
      if (cancelled) break;
      const b64 = await (pending as Promise<string>);
      if (cancelled) break;
      pending = i + 1 < chunks.length ? fetchAudio(chunks[i + 1]) : null;

      if (!started) { started = true; handlers.onStart?.(); }
      if (b64) {
        const p = playBase64AudioControllable(b64);
        stopCurrent = p.stop;
        await p.done;
      } else {
        // サーバーが返せなかった分だけ端末の音声で読む
        await new Promise<void>((resolve) => {
          const cancel = speakSequence([chunks[i]], {
            lang: "ja-JP",
            voiceName: settings.browserVoice,
            rate: settings.rate,
            pitch: settings.pitch,
            onEnd: resolve,
          });
          stopCurrent = () => { cancel(); resolve(); };
        });
      }
    }
    if (!cancelled) handlers.onEnd?.();
  })();

  return () => {
    cancelled = true;
    stopCurrent();
    stopSpeaking();
  };
}

/** 進行中の読み上げを全部止める。 */
export function stopCoreVoice(): void {
  stopSpeaking();
}
