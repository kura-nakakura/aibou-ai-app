# test_notify_line.py — LINE通知の検証
#
# LINE Notify は 2025年3月31日でサービス終了した。旧トークンのまま送ると
# 必ず失敗するのに、以前のコードは例外を握って {"ok": False} を返すだけで、
# 「なぜ届かないのか」がどこにも出なかった。設定したのに届かない、しかも
# 理由が分からない、が一番きつい。
#
# 確かめること:
#   ・いまの方式（Messaging API）で送れること
#   ・宛先の有無で push / broadcast を正しく使い分けること
#   ・旧トークンしか無い人に、理由が伝わること
#   ・未設定なら通信しないこと

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import keychain
import notify


@pytest.fixture
def keys(monkeypatch):
    """keychain を辞書で置き換える。実際の鍵も通信も使わない。"""
    store = {}
    monkeypatch.setattr(keychain, "get_key", lambda n: store.get(n, ""))
    monkeypatch.setattr(notify.keychain, "get_key", lambda n: store.get(n, ""))
    return store


@pytest.fixture
def sent(monkeypatch):
    """送信を記録するだけの偽の送信口。ネットワークには出ない。"""
    calls = []

    def fake_post_json(url, payload, headers=None):
        calls.append({"url": url, "payload": payload, "headers": headers or {}})
        return True

    monkeypatch.setattr(notify, "_post_json", fake_post_json)

    def boom(*a, **k):                      # 旧APIを叩いたら気づけるようにする
        raise AssertionError("終了したLINE Notifyへ送信しようとした")

    monkeypatch.setattr(notify, "_post_form", boom)
    return calls


def test_nothing_configured_sends_nothing(keys, sent):
    r = notify.send_line("こんにちは")
    assert r["skipped"] is True
    assert r["ok"] is False
    assert sent == []                        # 通信もしない


def test_channel_token_alone_broadcasts(keys, sent):
    """宛先を書かない人が大半。友だち全員へ送れば1人運用では十分。"""
    keys["LINE_CHANNEL_TOKEN"] = "channel-token"
    r = notify.send_line("できました")

    assert r["ok"] is True
    assert len(sent) == 1
    assert sent[0]["url"].endswith("/message/broadcast")
    assert "to" not in sent[0]["payload"]
    assert sent[0]["headers"]["Authorization"] == "Bearer channel-token"
    assert sent[0]["payload"]["messages"][0]["text"] == "できました"


def test_user_id_switches_to_push(keys, sent):
    keys["LINE_CHANNEL_TOKEN"] = "channel-token"
    keys["LINE_TO_USER_ID"] = "U123"
    notify.send_line("やあ")

    assert sent[0]["url"].endswith("/message/push")
    assert sent[0]["payload"]["to"] == "U123"


def test_old_notify_token_explains_instead_of_failing_silently(keys, sent):
    """旧トークンしか無い人に、黙って失敗せず理由を返す。"""
    keys["LINE_NOTIFY_TOKEN"] = "old-token"
    r = notify.send_line("届くはずのメッセージ")

    assert r["ok"] is False
    assert r.get("skipped") is not True       # 設定はしているので「未設定」ではない
    assert "終了" in r["error"]
    assert "LINE_CHANNEL_TOKEN" in r["error"]
    assert sent == []                         # 無駄な送信もしない


def test_new_token_wins_over_the_old_one(keys, sent):
    keys["LINE_NOTIFY_TOKEN"] = "old-token"
    keys["LINE_CHANNEL_TOKEN"] = "channel-token"
    assert notify.send_line("両方ある")["ok"] is True
    assert len(sent) == 1


def test_long_messages_are_trimmed(keys, sent):
    """LINEの上限（5000字）を超えるとAPIが丸ごと拒否する。手前で切る。"""
    keys["LINE_CHANNEL_TOKEN"] = "channel-token"
    notify.send_line("あ" * 9000)
    assert len(sent[0]["payload"]["messages"][0]["text"]) <= 5000


def test_a_broken_line_never_breaks_the_others(keys, monkeypatch):
    """1つのチャンネルの失敗で、通知全体が落ちてはいけない。"""
    keys["LINE_CHANNEL_TOKEN"] = "channel-token"
    keys["SLACK_WEBHOOK"] = "https://hooks.slack.com/services/x"

    def half_broken(url, payload, headers=None):
        if "line.me" in url:
            raise RuntimeError("LINE側が落ちている")
        return True

    monkeypatch.setattr(notify, "_post_json", half_broken)
    monkeypatch.setattr(notify, "log_internal", lambda *a, **k: {})

    out = notify.notify_all("結果です")
    assert out["ok"] is True                  # Slackには届いた
    assert "slack" in out["sent"]
    assert "line" not in out["sent"]
