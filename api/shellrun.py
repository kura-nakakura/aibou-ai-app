# shellrun.py — CODEモードから実際のコマンドを走らせる（既定は無効）
# =====================================================================
# なぜ既定で無効なのか
#   ここで走るのは利用者（とAI）が書いたコードで、実行すれば任意コード実行に
#   なる。このバックエンドは暗号化キーチェーンやDBキーを持つプロセスなので、
#   何も考えずに開けてよい機能ではない。よって
#       ENABLE_SHELL=1
#   を明示的に設定した環境だけで動く。設定しなければ 403 相当で断る。
#
# 有効化した場合に、それでも被害を小さくするためにやっていること
#   ・環境変数を洗う：PATH/HOME/LANG 等だけを渡し、APIキーやDBキーは一切渡さない
#     （子プロセスから os.environ 経由で鍵を読まれるのを防ぐ）
#   ・作業ディレクトリは毎回作る一時ディレクトリ。渡されたファイルだけを置く
#   ・実行できるコマンドを allowlist で絞る（シェル経由では起動しない）
#   ・CPU時間・メモリ・出力ファイルサイズに上限（resource）
#   ・タイムアウトでプロセスグループごと停止（子孫が残らないように）
#   ・標準出力/エラーは上限で打ち切り、切ったことを明示する
#
# 正直に書いておく限界
#   コンテナではないので、ネットワーク送信や一時ディレクトリ外の読み取りは
#   防げない。共用のサーバーで他人のコードを走らせる用途には向かない。
#   自分専用/自ホスト運用でのみ有効化することを勧める。
# =====================================================================

import os
import shutil
import signal
import subprocess
import tempfile

# 走らせてよいコマンド（先頭の実行ファイル名のみで判定する）
ALLOWED = {
    "node", "npm", "npx", "yarn", "pnpm",
    "python", "python3", "pip", "pip3", "pytest",
    "ls", "cat", "echo", "pwd", "wc", "head", "tail", "grep", "find", "sed", "awk",
    "git", "make", "sh", "bash",
    "tsc", "eslint", "prettier", "jest", "vitest",
}

MAX_FILES = 200
MAX_FILE_CHARS = 200_000
MAX_OUTPUT = 20_000          # 標準出力/エラーの上限（各）
DEFAULT_TIMEOUT = 60
MAX_TIMEOUT = 300
CPU_SECONDS = 60             # 子プロセスのCPU時間上限
MEM_BYTES = 1_500_000_000    # アドレス空間の上限（約1.5GB）
FSIZE_BYTES = 50_000_000     # 作れるファイルサイズの上限（50MB）


def enabled() -> bool:
    """ENABLE_SHELL=1 が設定されているときだけ有効。"""
    return (os.environ.get("ENABLE_SHELL") or "").strip() in ("1", "true", "yes", "on")


def status() -> dict:
    """UIに出すための状態。鍵や環境の中身は返さない。"""
    return {
        "enabled": enabled(),
        "allowed": sorted(ALLOWED),
        "timeout_default": DEFAULT_TIMEOUT,
        "timeout_max": MAX_TIMEOUT,
        "note": ("サーバーで実際にコマンドを実行します。"
                 "自分専用/自ホスト運用でのみ有効にしてください。"),
    }


def _safe_rel(path: str):
    """ワークスペース内の相対パスとして安全か検査して正規化する。"""
    p = (path or "").strip().replace("\\", "/").lstrip("/")
    if not p or p.startswith(".."):
        return None
    parts = []
    for seg in p.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":            # 親へ抜ける指定は認めない
            return None
        parts.append(seg)
    return "/".join(parts) or None


def _clean_env() -> dict:
    """鍵を含まない最小の環境変数。子プロセスに秘密を渡さないための要。"""
    keep = ("PATH", "HOME", "LANG", "LC_ALL", "TZ", "TERM", "TMPDIR")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    env["HOME"] = env.get("TMPDIR") or "/tmp"
    # ツールが余計な通信や色付けをしないように
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["NO_COLOR"] = "1"
    env["CI"] = "1"
    return env


def _limits():
    """子プロセス側で資源上限を設定する（POSIXのみ）。"""
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
        resource.setrlimit(resource.RLIMIT_FSIZE, (FSIZE_BYTES, FSIZE_BYTES))
        try:
            resource.setrlimit(resource.RLIMIT_AS, (MEM_BYTES, MEM_BYTES))
        except Exception:
            pass          # 環境によってはAS制限が使えない
    except Exception:
        pass
    try:
        os.setsid()       # プロセスグループを分けて、まとめて止められるように
    except Exception:
        pass


def _cut(b: bytes) -> tuple:
    text = (b or b"").decode("utf-8", "replace")
    if len(text) <= MAX_OUTPUT:
        return text, False
    return text[:MAX_OUTPUT], True


def run(command: str, files=None, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """一時ディレクトリで1コマンド実行して結果を返す。絶対に raise しない。

    files: [{"path","content"}] をその場に書き出す（ワークスペースの再現）。
    戻り値 {ok, code, stdout, stderr, truncated, cmd, seconds} / {error}
    """
    if not enabled():
        return {"error": "サーバーでの実行は無効です（ENABLE_SHELL=1 を設定すると有効になります）"}

    cmd = (command or "").strip()
    if not cmd:
        return {"error": "コマンドが空です"}

    # シェル経由にしない（; や && で allowlist を回避されないように）
    try:
        import shlex
        argv = shlex.split(cmd)
    except Exception as e:
        return {"error": f"コマンドを解釈できません: {e}"}
    if not argv:
        return {"error": "コマンドが空です"}
    exe = os.path.basename(argv[0])
    if exe not in ALLOWED:
        return {"error": f"許可されていないコマンドです: {exe}（許可: {', '.join(sorted(ALLOWED))}）"}
    if shutil.which(argv[0]) is None and shutil.which(exe) is None:
        return {"error": f"{exe} がこのサーバーに入っていません"}

    try:
        timeout = max(1, min(int(timeout or DEFAULT_TIMEOUT), MAX_TIMEOUT))
    except Exception:
        timeout = DEFAULT_TIMEOUT

    work = tempfile.mkdtemp(prefix="forgerun_")
    written = 0
    try:
        for f in (files or [])[:MAX_FILES]:
            rel = _safe_rel((f or {}).get("path", ""))
            if not rel:
                continue
            dest = os.path.join(work, rel)
            os.makedirs(os.path.dirname(dest) or work, exist_ok=True)
            content = str((f or {}).get("content") or "")[:MAX_FILE_CHARS]
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(content)
            written += 1

        import time
        t0 = time.time()
        proc = subprocess.Popen(
            argv, cwd=work, env=_clean_env(),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            preexec_fn=_limits,
        )
        try:
            out, err = proc.communicate(timeout=timeout)
            code = proc.returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            # 子孫まで止める（プロセスグループごと）
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()
            out, err = proc.communicate()
            code = -1
            timed_out = True

        so, cut1 = _cut(out)
        se, cut2 = _cut(err)
        if timed_out:
            se = (se + f"\n[{timeout}秒で打ち切りました]").strip()
        return {
            "ok": code == 0,
            "code": code,
            "stdout": so,
            "stderr": se,
            "truncated": bool(cut1 or cut2),
            "timed_out": timed_out,
            "cmd": " ".join(argv),
            "files": written,
            "seconds": round(time.time() - t0, 2),
        }
    except Exception as e:
        return {"error": f"実行に失敗しました: {e}"}
    finally:
        shutil.rmtree(work, ignore_errors=True)
