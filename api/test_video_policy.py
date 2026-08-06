# test_video_policy.py — 動画の品質（ケン・バーンズ）とポリシーのオプトイン
# ※ この sandbox に ffmpeg は無いため、実レンダリングではなく
#   「組み立てられる ffmpeg コマンド／フィルタグラフ」を検証する。

import os
import sys

import compliance

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import renderer  # noqa: E402  (リポジトリ直下)


# ── ケン・バーンズ効果（映像品質） ───────────────────────────────────
def test_ken_burns_filter_uses_output_frame_number():
    """ループ入力でも破綻しないよう、ズームは on（出力フレーム番号）基準にする。"""
    vf = renderer._ken_burns_vf(seconds=60, fps=24, seed=0)
    assert "zoompan=" in vf
    assert "on/" in vf                 # on 基準
    assert "zoom+" not in vf           # 状態依存のインクリメント方式は使わない
    assert "s=1280x720" in vf and "fps=24" in vf
    assert vf.startswith("scale=2560:1440")   # 先に拡大 → ズームしても解像を保つ
    assert vf.endswith("format=yuv420p")


def test_ken_burns_direction_varies_by_seed():
    """seed によって寄り/引きとパンが変わる（同じseedなら同じ＝再現性あり）。"""
    a = renderer._ken_burns_vf(60, 24, seed=0)
    b = renderer._ken_burns_vf(60, 24, seed=1)
    c = renderer._ken_burns_vf(60, 24, seed=2)
    assert a != b and b != c
    assert renderer._ken_burns_vf(60, 24, seed=0) == a


def test_ken_burns_zoom_bounds():
    """ズーム量は控えめ（1.0〜1.12程度）に収める。"""
    zin = renderer._ken_burns_vf(60, 24, seed=0)   # 偶数 → 寄り
    zout = renderer._ken_burns_vf(60, 24, seed=1)  # 奇数 → 引き
    assert "1+0.1200*on" in zin
    assert "1.1200-0.1200*on" in zout


def test_build_cmd_motion_default_is_smooth():
    cmd = renderer._build_ffmpeg_cmd("ffmpeg", "i.png", "a.wav", "o.mp4", 60, fps=24, seed=0)
    vf = cmd[cmd.index("-vf") + 1]
    assert "zoompan" in vf
    assert "-shortest" in cmd            # 音声ループで伸び続けないようにする
    assert cmd[cmd.index("-r") + 1] == "24"
    assert "-tune" not in cmd            # stillimage チューニングは動きがある時は不適
    assert cmd[-1] == "o.mp4"


def test_build_cmd_motion_off_is_static_slide():
    cmd = renderer._build_ffmpeg_cmd("ffmpeg", "i.png", "a.wav", "o.mp4", 60, fps=2, motion=False)
    vf = cmd[cmd.index("-vf") + 1]
    assert "zoompan" not in vf and "pad=1280:720" in vf
    assert "-tune" in cmd


# ── ポリシーのオプトイン（アカウント所有者の判断） ───────────────────
def test_stock_ai_upload_blocked_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_AI_STOCK_UPLOAD", raising=False)
    import keychain
    monkeypatch.setattr(keychain, "get_key", lambda n: "")
    g = compliance.gate("shutterstock", ai_generated=True)
    assert g["ok"] is False
    assert "ALLOW_AI_STOCK_UPLOAD" in g["reason"]   # 解除方法を案内する


def test_stock_ai_upload_can_be_enabled_by_owner(monkeypatch):
    """利用者が明示的にフラグを立てたら通す（規約確認と責任は利用者）。"""
    import keychain
    monkeypatch.setattr(keychain, "get_key", lambda n: "1" if n == "ALLOW_AI_STOCK_UPLOAD" else "")
    g = compliance.gate("shutterstock", ai_generated=True)
    assert g["ok"] is True and g["overridden"] is True
    assert "利用者" in g["reason"]


def test_env_var_also_enables(monkeypatch):
    import keychain
    monkeypatch.setattr(keychain, "get_key", lambda n: "")
    monkeypatch.setenv("ALLOW_NOTE_AUTOPOST", "true")
    assert compliance.platform_policy("note")["overridden"] is True


def test_flag_off_values_do_not_enable(monkeypatch):
    import keychain
    monkeypatch.setattr(keychain, "get_key", lambda n: "0")
    monkeypatch.delenv("ALLOW_AI_STOCK_UPLOAD", raising=False)
    assert compliance.gate("shutterstock", True)["ok"] is False


def test_unknown_platform_has_no_override(monkeypatch):
    import keychain
    monkeypatch.setattr(keychain, "get_key", lambda n: "1")
    assert compliance.gate("tiktok", True)["ok"] is False


def test_policy_report_lists_all(monkeypatch):
    import keychain
    monkeypatch.setattr(keychain, "get_key", lambda n: "")
    rep = compliance.policy_report()
    assert set(rep) >= {"note", "youtube", "pseo", "shutterstock"}
    assert all("overridden" in v for v in rep.values())
