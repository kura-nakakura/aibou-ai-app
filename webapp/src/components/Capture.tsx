"use client";

/**
 * Capture — PC画面の録画 / 音声の録音（ブラウザ内で完結・無料）.
 *
 *  - 画面録画: getDisplayMedia で画面/ウィンドウ/タブを録画（タブ音声も可）
 *  - 画面＋マイク: 画面音声とマイクを Web Audio でミックスして録画
 *  - 音声のみ: マイクを録音
 * MediaRecorder で WebM を生成し、その場で再生＆ダウンロード。サーバー送信なし。
 * 非対応ブラウザ（iOS Safari 等の画面録画）では丁寧に案内して縮退する。
 */

import { useEffect, useRef, useState } from "react";

type Mode = "screen" | "screen_mic" | "mic";
interface Result { url: string; isVideo: boolean; size: number }

const MODES: { key: Mode; label: string; hint: string; video: boolean }[] = [
  { key: "screen", label: "画面録画", hint: "画面＋タブ音声", video: true },
  { key: "screen_mic", label: "画面＋マイク", hint: "解説ナレーション向け", video: true },
  { key: "mic", label: "音声のみ", hint: "ボイスメモ・録音", video: false },
];

function pickMime(video: boolean): string {
  const cands = video
    ? ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm", "video/mp4"]
    : ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  const MR = typeof window !== "undefined" ? window.MediaRecorder : undefined;
  for (const c of cands) {
    try { if (MR && MR.isTypeSupported(c)) return c; } catch { /* ignore */ }
  }
  return "";
}

function fmtSize(n: number): string {
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
function fmtTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

export default function Capture() {
  const [mode, setMode] = useState<Mode>("screen");
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamsRef = useRef<{ streams: MediaStream[]; ctx: AudioContext | null }>({ streams: [], ctx: null });
  const previewRef = useRef<HTMLVideoElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastUrlRef = useRef<string | null>(null);

  const screenSupported = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getDisplayMedia;
  const micSupported = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

  const cleanupStreams = () => {
    streamsRef.current.streams.forEach((s) => s.getTracks().forEach((t) => t.stop()));
    try { streamsRef.current.ctx?.close(); } catch { /* ignore */ }
    streamsRef.current = { streams: [], ctx: null };
  };

  const stopTimer = () => { if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; } };

  // Cleanup on unmount.
  useEffect(() => () => {
    try { recorderRef.current?.state !== "inactive" && recorderRef.current?.stop(); } catch { /* ignore */ }
    cleanupStreams();
    stopTimer();
    if (lastUrlRef.current) URL.revokeObjectURL(lastUrlRef.current);
  }, []);

  const stop = () => {
    try {
      if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
    } catch { /* ignore */ }
  };

  const start = async () => {
    setError(null);
    if (result) { if (lastUrlRef.current) URL.revokeObjectURL(lastUrlRef.current); setResult(null); }
    const wantVideo = mode !== "mic";
    if (wantVideo && !screenSupported) { setError("この端末/ブラウザは画面録画に未対応です（PCのChrome/Edge推奨）。音声のみは利用できます。"); return; }
    if (!wantVideo && !micSupported) { setError("マイクにアクセスできません。"); return; }

    try {
      let recStream: MediaStream;
      let ctx: AudioContext | null = null;
      const streams: MediaStream[] = [];

      if (mode === "mic") {
        recStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        streams.push(recStream);
      } else {
        const display = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 30 }, audio: true });
        streams.push(display);
        let audioTrack: MediaStreamTrack | undefined = display.getAudioTracks()[0];
        if (mode === "screen_mic") {
          const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
          streams.push(mic);
          ctx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
          const dest = ctx.createMediaStreamDestination();
          [display, mic].forEach((s) => { if (s.getAudioTracks().length) ctx!.createMediaStreamSource(s).connect(dest); });
          audioTrack = dest.stream.getAudioTracks()[0];
        }
        recStream = new MediaStream([...display.getVideoTracks(), ...(audioTrack ? [audioTrack] : [])]);
        // ユーザーがブラウザUIの「共有を停止」を押したら録画も止める。
        const vt = display.getVideoTracks()[0];
        if (vt) vt.addEventListener("ended", stop);
      }

      const mime = pickMime(wantVideo);
      const rec = new MediaRecorder(recStream, mime ? { mimeType: mime } : undefined);
      chunksRef.current = [];
      rec.ondataavailable = (e) => { if (e.data && e.data.size) chunksRef.current.push(e.data); };
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mime || (wantVideo ? "video/webm" : "audio/webm") });
        const url = URL.createObjectURL(blob);
        lastUrlRef.current = url;
        setResult({ url, isVideo: wantVideo, size: blob.size });
        cleanupStreams();
        stopTimer();
        setRecording(false);
      };

      recorderRef.current = rec;
      streamsRef.current = { streams, ctx };
      rec.start();
      setRecording(true);
      setElapsed(0);
      timerRef.current = setInterval(() => setElapsed((s) => s + 1), 1000);

      if (wantVideo && previewRef.current) {
        previewRef.current.srcObject = recStream;
        previewRef.current.muted = true;
        void previewRef.current.play?.().catch(() => {});
      }
    } catch (e) {
      cleanupStreams();
      const msg = (e as Error)?.name === "NotAllowedError" ? "権限が拒否されました。" : "録画を開始できませんでした。";
      setError(msg);
      setRecording(false);
    }
  };

  const download = () => {
    if (!result) return;
    const ts = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    const name = `capture_${ts.getFullYear()}${pad(ts.getMonth() + 1)}${pad(ts.getDate())}-${pad(ts.getHours())}${pad(ts.getMinutes())}${pad(ts.getSeconds())}.webm`;
    const a = document.createElement("a");
    a.href = result.url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-2xl flex-col gap-3 overflow-y-auto pb-2">
      <div className="glass-silver p-4">
        <div className="mb-1 flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-full border border-[var(--line)] text-[#ff6b6b]"><RecIcon /></span>
          <span className="text-[10px] tracking-[0.24em] text-muted label-mono">SCREEN & AUDIO CAPTURE</span>
        </div>
        <h2 className="label-mono text-glow text-sm text-fg-strong">画面録画・録音</h2>
        <p className="mt-1 text-[11px] leading-relaxed text-muted">
          PCの画面や音声をこの場で録画・録音します。データは端末内で処理され、サーバーには送られません。
        </p>

        {/* Mode select */}
        <div className="mt-3 grid grid-cols-3 gap-1.5">
          {MODES.map((m) => {
            const disabled = m.video && !screenSupported;
            const active = mode === m.key;
            return (
              <button
                key={m.key}
                type="button"
                disabled={recording || disabled}
                onClick={() => setMode(m.key)}
                title={disabled ? "この端末は画面録画に未対応" : m.hint}
                className="rounded-forge border p-2 text-center transition disabled:opacity-30"
                style={{
                  borderColor: active ? "var(--accent)" : "var(--panel-bd)",
                  background: active ? "var(--btn-bg)" : "transparent",
                  boxShadow: active ? "0 0 10px var(--glow)" : "none",
                }}
              >
                <div className="text-[11px] text-fg-strong label-mono">{m.label}</div>
                <div className="mt-0.5 text-[9px] text-muted">{m.hint}</div>
              </button>
            );
          })}
        </div>

        {/* Control */}
        <div className="mt-3 flex items-center gap-3">
          {!recording ? (
            <button
              type="button"
              onClick={() => void start()}
              className="flex items-center gap-2 rounded-forge border border-[var(--line)] bg-[var(--btn-bg)] px-5 py-2.5 text-[11px] tracking-[0.16em] text-fg-strong shadow-glow transition hover:shadow-glow-strong label-mono"
            >
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#ff6b6b]" /> 録画開始
            </button>
          ) : (
            <button
              type="button"
              onClick={stop}
              className="flex items-center gap-2 rounded-forge border border-[#ff6b6b66] bg-[rgba(255,107,107,0.1)] px-5 py-2.5 text-[11px] tracking-[0.16em] text-[#ff8888] label-mono"
            >
              <span className="inline-block h-2.5 w-2.5 bg-[#ff8888]" /> 停止
            </button>
          )}
          {recording && (
            <span className="flex items-center gap-2 text-[12px] text-fg-strong label-mono">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-[#ff6b6b]" />
              REC {fmtTime(elapsed)}
            </span>
          )}
        </div>

        {error && <p className="mt-2 text-[11px] leading-relaxed text-[#ff9b9b]">⚠ {error}</p>}
        {!screenSupported && (
          <p className="mt-2 text-[10px] leading-relaxed text-muted">※ 画面録画はPCの Chrome / Edge / Firefox で利用できます（スマホは音声のみ）。</p>
        )}
      </div>

      {/* Live preview while recording (screen modes) */}
      {recording && mode !== "mic" && (
        <div className="glass-silver p-2">
          <div className="mb-1 text-[9px] tracking-[0.2em] text-muted label-mono">LIVE PREVIEW</div>
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <video ref={previewRef} className="w-full rounded-forge border border-panel bg-black" playsInline />
        </div>
      )}

      {/* Result */}
      {result && !recording && (
        <div className="glass-silver p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[10px] tracking-[0.2em] text-muted label-mono">録画結果 — {result.isVideo ? "VIDEO" : "AUDIO"} · {fmtSize(result.size)}</span>
            <button type="button" onClick={() => { if (lastUrlRef.current) URL.revokeObjectURL(lastUrlRef.current); setResult(null); }}
              className="text-[10px] text-muted transition hover:text-fg-strong label-mono">✕ 破棄</button>
          </div>
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          {result.isVideo
            ? <video src={result.url} controls className="w-full rounded-forge border border-panel bg-black" />
            : <audio src={result.url} controls className="w-full" />}
          <button
            type="button"
            onClick={download}
            className="mt-2 w-full rounded-forge border border-[var(--line)] bg-[var(--btn-bg)] py-2 text-[11px] tracking-[0.16em] text-fg-strong shadow-glow transition hover:shadow-glow-strong label-mono"
          >
            ⭳ ダウンロード（.webm）
          </button>
          <p className="mt-1.5 text-[9px] leading-relaxed text-muted">
            ※ WebM形式で保存されます。MP4が必要な場合は、保存後に変換ツールをご利用ください。
          </p>
        </div>
      )}
    </div>
  );
}

function RecIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7">
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3" fill="currentColor" />
    </svg>
  );
}
