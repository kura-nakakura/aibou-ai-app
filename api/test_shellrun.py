# test_shellrun.py — サーバー実行（CODEのターミナル）の検証
#
# ここは「有効にすると任意コード実行になる」場所なので、
#   ・既定で無効であること
#   ・有効時も allowlist / 上限 / 環境変数の遮断が効いていること
# を重点的に確かめる。

import os

from fastapi.testclient import TestClient

import shellrun
from main import app

client = TestClient(app)


def _on(monkeypatch):
    monkeypatch.setenv("ENABLE_SHELL", "1")


# ── 既定は無効 ───────────────────────────────────────────────────────
def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_SHELL", raising=False)
    assert shellrun.enabled() is False
    res = shellrun.run("echo hello")
    assert res.get("error") and "ENABLE_SHELL" in res["error"]


def test_endpoint_refuses_when_disabled(monkeypatch):
    monkeypatch.delenv("ENABLE_SHELL", raising=False)
    r = client.post("/code/shell", json={"command": "echo hi"})
    assert r.status_code == 403
    assert r.json()["enabled"] is False


def test_status_never_leaks_the_environment(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-KEY-123")
    s = shellrun.status()
    assert "SECRET-KEY-123" not in repr(s)
    assert "allowed" in s and "enabled" in s


# ── allowlist ────────────────────────────────────────────────────────
def test_only_allowed_commands_run(monkeypatch):
    _on(monkeypatch)
    res = shellrun.run("rm -rf /")
    assert res.get("error") and "許可されていない" in res["error"]


def test_shell_metacharacters_cannot_chain_commands(monkeypatch):
    """; や && で allowlist をすり抜けられないこと（shell=False で起動する）。"""
    _on(monkeypatch)
    res = shellrun.run("echo ok; rm -rf /tmp/should-not-exist")
    # shell を経由しないので、";" 以降は echo の引数として扱われるだけ
    assert res.get("ok") is True
    assert "rm" in res["stdout"]          # 実行されず文字として出る


def test_unknown_binary_is_reported(monkeypatch):
    _on(monkeypatch)
    monkeypatch.setattr(shellrun, "ALLOWED", shellrun.ALLOWED | {"definitely-not-installed"})
    res = shellrun.run("definitely-not-installed --version")
    assert res.get("error") and "入っていません" in res["error"]


# ── 実行 ─────────────────────────────────────────────────────────────
def test_runs_a_command_and_returns_output(monkeypatch):
    _on(monkeypatch)
    res = shellrun.run("echo こんにちは")
    assert res["ok"] is True and res["code"] == 0
    assert "こんにちは" in res["stdout"]
    assert res["seconds"] >= 0


def test_files_are_materialized_in_the_workspace(monkeypatch):
    _on(monkeypatch)
    res = shellrun.run("python3 -c \"print(open('app.py').read().strip())\"",
                       files=[{"path": "app.py", "content": "print('hi')"}])
    assert res["ok"] is True
    assert "print('hi')" in res["stdout"]
    assert res["files"] == 1


def test_nested_paths_are_created(monkeypatch):
    _on(monkeypatch)
    res = shellrun.run("cat src/lib/util.js",
                       files=[{"path": "src/lib/util.js", "content": "export const a = 1;"}])
    assert res["ok"] is True and "export const a" in res["stdout"]


def test_real_test_run_reports_failure(monkeypatch):
    """本物のテストランナーを回して、失敗が失敗として返ること。"""
    _on(monkeypatch)
    files = [
        {"path": "calc.py", "content": "def add(a, b):\n    return a + b - 1\n"},
        {"path": "test_calc.py", "content": "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"},
    ]
    res = shellrun.run("python3 -m pytest -q", files=files, timeout=120)
    if res.get("error"):
        return                      # pytest が無い環境ではスキップ
    assert res["ok"] is False       # わざと壊してあるので失敗する
    out = res["stdout"] + res["stderr"]
    assert "1 failed" in out or "failed" in out


def test_nonzero_exit_is_not_ok(monkeypatch):
    _on(monkeypatch)
    res = shellrun.run("python3 -c \"import sys; sys.exit(3)\"")
    assert res["ok"] is False and res["code"] == 3


# ── 遮断・上限 ───────────────────────────────────────────────────────
def test_secrets_are_not_visible_to_the_child(monkeypatch):
    """子プロセスに鍵を渡さない（ここが一番大事）。"""
    _on(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-KEY-123")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "SECRET-DB-456")
    monkeypatch.setenv("KEYCHAIN_SECRET", "SECRET-VAULT-789")
    res = shellrun.run("python3 -c \"import os,json; print(json.dumps(dict(os.environ)))\"")
    assert res["ok"] is True
    dump = res["stdout"]
    assert "SECRET-KEY-123" not in dump
    assert "SECRET-DB-456" not in dump
    assert "SECRET-VAULT-789" not in dump
    assert "GEMINI_API_KEY" not in dump


def test_cwd_is_a_fresh_directory_each_time(monkeypatch):
    _on(monkeypatch)
    a = shellrun.run("pwd")
    b = shellrun.run("pwd")
    assert a["stdout"].strip() != b["stdout"].strip()
    # 前回のファイルが残らない
    shellrun.run("echo x", files=[{"path": "left.txt", "content": "x"}])
    res = shellrun.run("ls")
    assert "left.txt" not in res["stdout"]


def test_workspace_is_cleaned_up(monkeypatch):
    _on(monkeypatch)
    res = shellrun.run("pwd", files=[{"path": "a.txt", "content": "x"}])
    path = res["stdout"].strip()
    assert path and not os.path.exists(path)     # 実行後に消える


def test_timeout_kills_the_process(monkeypatch):
    _on(monkeypatch)
    res = shellrun.run("python3 -c \"import time; time.sleep(30)\"", timeout=2)
    assert res["timed_out"] is True and res["ok"] is False
    assert "打ち切りました" in res["stderr"]


def test_output_is_capped_and_says_so(monkeypatch):
    _on(monkeypatch)
    res = shellrun.run("python3 -c \"print('x' * 100000)\"")
    assert res["truncated"] is True
    assert len(res["stdout"]) <= shellrun.MAX_OUTPUT


def test_escaping_the_workspace_is_rejected(monkeypatch):
    _on(monkeypatch)
    res = shellrun.run("ls", files=[
        {"path": "../outside.txt", "content": "x"},
        {"path": "/etc/passwd", "content": "x"},
        {"path": "ok.txt", "content": "x"},
    ])
    assert res["files"] == 2          # ../ は却下、/etc/passwd は先頭スラッシュを剥いで相対化
    assert "outside.txt" not in res["stdout"]


def test_timeout_is_clamped(monkeypatch):
    _on(monkeypatch)
    res = shellrun.run("echo hi", timeout=99999)
    assert res["ok"] is True          # 上限に丸めて実行される（拒否ではない）


# ── エンドポイント ───────────────────────────────────────────────────
def test_endpoint_runs_when_enabled(monkeypatch):
    _on(monkeypatch)
    r = client.post("/code/shell", json={"command": "echo from-endpoint", "files": []})
    assert r.status_code == 200 and "from-endpoint" in r.json()["stdout"]


def test_endpoint_rejects_disallowed_command(monkeypatch):
    _on(monkeypatch)
    r = client.post("/code/shell", json={"command": "curl http://example.com"})
    assert r.status_code == 400 and "許可されていない" in r.json()["error"]


def test_status_endpoint(monkeypatch):
    _on(monkeypatch)
    r = client.get("/code/shell")
    assert r.status_code == 200
    d = r.json()
    assert d["enabled"] is True and "pytest" in d["allowed"]
