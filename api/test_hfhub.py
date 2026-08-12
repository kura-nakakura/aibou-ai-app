# test_hfhub.py — HuggingFaceのモデル台帳と、タスク別呼び出しの検証
#
# HFは外部サービスなので requests をモックする。ここで確かめたいのは
#   ・タスクごとに正しいURL・正しいbodyで叩いていること（音声は生バイト、画像はJSON）
#   ・HFの英語エラーを丸投げせず、原因を日本語で返すこと（401/404/429/503）
#   ・503のコールドスタートを「待てば動く」として区別すること
#   ・台帳の登録・重複拒否・削除で割り当てが外れること
#   ・画像生成と文字起こしが、割り当てたHFモデルで実際に走ること

import io

import hfhub
import imagegen
import transcribe as tr


class FakeResp:
    def __init__(self, status=200, *, json_data=None, content=b"", headers=None, text=""):
        self.status_code = status
        self._json = json_data
        self.content = content
        self.headers = headers or {}
        self.text = text or ("" if json_data is None else str(json_data))

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


def _reset():
    hfhub._mem_models.clear()
    hfhub._mem_images.clear()


def _with_token(monkeypatch, value="hf_testtoken"):
    monkeypatch.setattr(hfhub, "_kc", lambda name: value if name == "HUGGINGFACE_TOKEN" else "")


# ── トークン ───────────────────────────────────────────────────────
def test_calls_require_a_token(monkeypatch):
    monkeypatch.setattr(hfhub, "_kc", lambda name: "")
    res = hfhub.run_asr("openai/whisper-large-v3", b"audio")
    assert res.get("error") and "トークン" in res["error"]


def test_status_never_leaks_the_token(monkeypatch):
    _with_token(monkeypatch, "hf_supersecret")
    s = hfhub.status()
    assert s["token_ready"] is True
    assert "hf_supersecret" not in repr(s)


# ── エラーの日本語化 ───────────────────────────────────────────────
def test_unauthorized_says_check_the_token(monkeypatch):
    _with_token(monkeypatch)
    monkeypatch.setattr(hfhub, "_post",
                        lambda *a, **k: FakeResp(401, json_data={"error": "Invalid credentials"}))
    res = hfhub.run_image("some/model", "apple")
    assert "トークン" in res["error"]
    assert res["status"] == 401


def test_missing_model_says_so(monkeypatch):
    _with_token(monkeypatch)
    monkeypatch.setattr(hfhub, "_post",
                        lambda *a, **k: FakeResp(404, json_data={"error": "Not Found"}))
    res = hfhub.run_image("nope/nope", "apple")
    assert "見つかりません" in res["error"]


def test_rate_limit_is_explained(monkeypatch):
    _with_token(monkeypatch)
    monkeypatch.setattr(hfhub, "_post", lambda *a, **k: FakeResp(429, json_data={"error": "rate limit"}))
    res = hfhub.run_seq2seq("m/t", "translate", "こんにちは")
    assert "上限" in res["error"]


def test_cold_start_is_marked_retryable(monkeypatch):
    """503は失敗ではなく「起動待ち」。待てば動くことが伝わる必要がある。"""
    _with_token(monkeypatch)
    monkeypatch.setattr(hfhub, "_post", lambda *a, **k: FakeResp(
        503, json_data={"error": "Model is currently loading", "estimated_time": 42.7}))
    res = hfhub.run_asr("openai/whisper-large-v3", b"audio")
    assert res.get("retry") is True
    assert "起動中" in res["error"] and "42" in res["error"]


def test_falls_back_to_the_legacy_host_only_on_404(monkeypatch):
    """ルーターに無いモデルは旧ホストも試す。権限エラーで無駄打ちしない。"""
    _with_token(monkeypatch)
    urls = []

    def fake_post(url, **kw):
        urls.append(url)
        if hfhub.ROUTER_BASE in url:
            return FakeResp(404, json_data={"error": "not found"})
        return FakeResp(200, json_data={"text": "旧ホストで通った"})

    monkeypatch.setattr(hfhub, "_post", fake_post)
    res = hfhub.run_asr("openai/whisper-large-v3", b"audio")
    assert res["ok"] and res["text"] == "旧ホストで通った"
    assert len(urls) == 2 and hfhub.LEGACY_BASE in urls[1]

    urls.clear()
    monkeypatch.setattr(hfhub, "_post", lambda url, **kw: (urls.append(url), FakeResp(401, json_data={}))[1])
    hfhub.run_asr("x/y", b"a")
    assert len(urls) == 1          # 401で打ち切る


# ── タスクごとの送り方 ─────────────────────────────────────────────
def test_asr_sends_raw_audio_bytes(monkeypatch):
    """音声はJSONに詰めず、生バイトをbodyに載せる（HFの推論APIの作法）。"""
    _with_token(monkeypatch)
    seen = {}

    def fake_post(url, *, json_body=None, data=None, content_type=""):
        seen.update(url=url, json_body=json_body, data=data, content_type=content_type)
        return FakeResp(200, json_data={"text": "テスト音声です"})

    monkeypatch.setattr(hfhub, "_post", fake_post)
    res = hfhub.run_asr("openai/whisper-large-v3", b"\xff\xfbmp3bytes", "audio/mpeg")
    assert res["ok"] and res["text"] == "テスト音声です"
    assert seen["data"] == b"\xff\xfbmp3bytes"
    assert seen["json_body"] is None
    assert seen["content_type"] == "audio/mpeg"
    assert seen["url"].endswith("/models/openai/whisper-large-v3")


def test_asr_rejects_oversized_audio(monkeypatch):
    _with_token(monkeypatch)
    res = hfhub.run_asr("m/x", b"x" * (hfhub.MAX_AUDIO_BYTES + 1))
    assert "大きすぎ" in res["error"]


def test_image_asks_for_the_requested_size(monkeypatch):
    _with_token(monkeypatch)
    seen = {}

    def fake_post(url, *, json_body=None, data=None, content_type=""):
        seen.update(json_body=json_body)
        return FakeResp(200, content=b"\x89PNG....", headers={"content-type": "image/png"})

    monkeypatch.setattr(hfhub, "_post", fake_post)
    res = hfhub.run_image("black-forest-labs/FLUX.1-schnell", "a red apple", 512, 768)
    assert res["ok"] and res["mime"] == "image/png" and res["data"].startswith(b"\x89PNG")
    assert seen["json_body"]["inputs"] == "a red apple"
    assert seen["json_body"]["parameters"] == {"width": 512, "height": 768}


def test_image_task_mismatch_is_reported(monkeypatch):
    """画像のはずがJSONで返ってきたら、タスク違いだと分かるように言う。"""
    _with_token(monkeypatch)
    monkeypatch.setattr(hfhub, "_post", lambda *a, **k: FakeResp(
        200, content=b'[{"generated_text":"apple"}]', headers={"content-type": "application/json"}))
    res = hfhub.run_image("gpt2", "apple")
    assert "画像を返しませんでした" in res["error"]


def test_labels_handles_all_three_response_shapes(monkeypatch):
    _with_token(monkeypatch)
    shapes = [
        [[{"label": "POS", "score": 0.9}, {"label": "NEG", "score": 0.1}]],
        [{"label": "POS", "score": 0.9}],
        {"labels": ["POS", "NEG"], "scores": [0.8, 0.2]},
    ]
    for shape in shapes:
        monkeypatch.setattr(hfhub, "_post", lambda *a, **k: FakeResp(200, json_data=shape))
        res = hfhub.run_labels("m/x", "よい一日")
        assert res["ok"], shape
        assert res["labels"][0]["label"] == "POS"


def test_zero_shot_passes_candidate_labels(monkeypatch):
    _with_token(monkeypatch)
    seen = {}
    monkeypatch.setattr(hfhub, "_post", lambda url, *, json_body=None, data=None, content_type="":
                        (seen.update(b=json_body),
                         FakeResp(200, json_data={"labels": ["A"], "scores": [1.0]}))[1])
    hfhub.run_labels("facebook/bart-large-mnli", "文章", ["A", "B"])
    assert seen["b"]["parameters"]["candidate_labels"] == ["A", "B"]


def test_seq2seq_reads_translation_and_summary_keys(monkeypatch):
    _with_token(monkeypatch)
    monkeypatch.setattr(hfhub, "_post", lambda *a, **k: FakeResp(
        200, json_data=[{"translation_text": "Hello"}]))
    assert hfhub.run_seq2seq("m/x", "translate", "こんにちは")["text"] == "Hello"
    monkeypatch.setattr(hfhub, "_post", lambda *a, **k: FakeResp(
        200, json_data=[{"summary_text": "要点"}]))
    assert hfhub.run_seq2seq("m/x", "summarize", "長い文章")["text"] == "要点"


def test_embed_flattens_nested_vectors(monkeypatch):
    _with_token(monkeypatch)
    monkeypatch.setattr(hfhub, "_post", lambda *a, **k: FakeResp(
        200, json_data=[[[0.1, 0.2, 0.3, 0.4]]]))
    res = hfhub.run_embed("intfloat/multilingual-e5-large", "テスト")
    assert res["ok"] and res["dim"] == 4 and res["head"][0] == 0.1


def test_run_dispatches_by_task(monkeypatch):
    _with_token(monkeypatch)
    monkeypatch.setattr(hfhub, "run_image", lambda m, t, w=0, h=0: {"ok": True, "kind": "image"})
    assert hfhub.run("image", "m/x", text="a")["kind"] == "image"
    assert hfhub.run("nope", "m/x").get("error")
    assert hfhub.run("image", "").get("error")


# ── 台帳 ───────────────────────────────────────────────────────────
def test_model_id_validation():
    assert hfhub.valid_model_id("openai/whisper-large-v3")
    assert hfhub.valid_model_id("gpt2")
    assert not hfhub.valid_model_id("")
    assert not hfhub.valid_model_id("has space/x")
    assert not hfhub.valid_model_id("../../etc/passwd")


def test_add_list_and_reject_duplicates():
    _reset()
    res = hfhub.add_model("openai/whisper-large-v3", "asr")
    assert res["ok"] and res["model"]["label"] == "whisper-large-v3"
    assert res["model"]["verified"] is False          # 登録＝動作確認ではない
    assert len(hfhub.list_models()) == 1
    dup = hfhub.add_model("openai/whisper-large-v3", "asr")
    assert dup.get("error") and "既に登録" in dup["error"]
    # 同じモデルでも別タスクなら登録できる
    assert hfhub.add_model("openai/whisper-large-v3", "text").get("ok")


def test_add_rejects_bad_task_and_id():
    _reset()
    assert hfhub.add_model("openai/whisper-large-v3", "nope").get("error")
    assert hfhub.add_model("not a model", "asr").get("error")


def test_test_result_is_recorded_on_the_row():
    _reset()
    row = hfhub.add_model("m/x", "image")["model"]
    hfhub.update_check(row["id"], False, "モデルが見つかりません")
    after = hfhub.get_model(row["id"])
    assert after["verified"] is False and "見つかりません" in after["last_error"]
    hfhub.update_check(row["id"], True)
    assert hfhub.get_model(row["id"])["verified"] is True
    assert hfhub.get_model(row["id"])["last_error"] == ""


def test_deleting_a_model_clears_its_assignment(monkeypatch):
    """割り当て中のモデルを消したら役割も外す（動かない参照を残さない）。"""
    _reset()
    store = {}
    monkeypatch.setattr(hfhub.keychain, "set_key", lambda n, v: store.__setitem__(n, v))
    monkeypatch.setattr(hfhub, "_kc", lambda n: store.get(n, ""))
    row = hfhub.add_model("black-forest-labs/FLUX.1-schnell", "image")["model"]
    hfhub.assign("image", row["model"])
    assert store["HF_IMAGE_MODEL"] == "black-forest-labs/FLUX.1-schnell"
    res = hfhub.delete_model(row["id"])
    assert res["ok"] and "image" in res["cleared_roles"]
    assert store["HF_IMAGE_MODEL"] == ""


def test_assign_validates(monkeypatch):
    monkeypatch.setattr(hfhub.keychain, "set_key", lambda n, v: None)
    assert hfhub.assign("nope", "m/x").get("error")
    assert hfhub.assign("image", "bad id").get("error")


def test_assign_to_chat_uses_the_key_llm_already_reads(monkeypatch):
    """会話の割り当ては llm.py が読む HF_MODEL に入る（別名を作らない）。"""
    store = {}
    monkeypatch.setattr(hfhub.keychain, "set_key", lambda n, v: store.__setitem__(n, v))
    hfhub.assign("chat", "Qwen/Qwen2.5-72B-Instruct")
    assert store == {"HF_MODEL": "Qwen/Qwen2.5-72B-Instruct"}
    import llm
    assert llm.hf_model.__module__ == "llm"      # 参照先が変わっていないこと


# ── 動作テスト ─────────────────────────────────────────────────────
def test_probe_treats_silence_as_success(monkeypatch):
    """無音の確認音声で「文字が取れない」のは正常。失敗扱いにしない。"""
    _with_token(monkeypatch)
    monkeypatch.setattr(hfhub, "_probe_audio", lambda: b"\xff\xfbmp3")
    monkeypatch.setattr(hfhub, "run_asr", lambda m, a, mime="": {"error": "音声から文字を取り出せませんでした（無音の可能性があります）"})
    res = hfhub.test_model("openai/whisper-large-v3", "asr")
    assert res["ok"] is True


def test_probe_reports_failures_with_retry_flag(monkeypatch):
    _with_token(monkeypatch)
    monkeypatch.setattr(hfhub, "run_image", lambda m, p, w=0, h=0: {"error": "モデルの起動中です（約20秒）", "retry": True})
    res = hfhub.test_model("m/x", "image")
    assert res["ok"] is False and res["retry"] is True


def test_probe_needs_a_token(monkeypatch):
    monkeypatch.setattr(hfhub, "_kc", lambda n: "")
    assert hfhub.test_model("m/x", "image").get("error")


def test_probe_validates_inputs(monkeypatch):
    _with_token(monkeypatch)
    assert hfhub.test_model("bad id", "image").get("error")
    assert hfhub.test_model("m/x", "nope").get("error")


# ── Hub検索 ────────────────────────────────────────────────────────
def test_search_filters_by_task_and_normalizes(monkeypatch):
    seen = {}

    def fake_get(url, params=None, headers=None, timeout=0):
        seen.update(url=url, params=params)
        return FakeResp(200, json_data=[
            {"id": "openai/whisper-large-v3", "downloads": 1234567, "likes": 900,
             "pipeline_tag": "automatic-speech-recognition"},
            {"modelId": "no-id-field/x"},
        ])

    monkeypatch.setattr(hfhub.requests, "get", fake_get)
    res = hfhub.search("whisper", "asr")
    assert res["ok"]
    assert seen["params"]["filter"] == "automatic-speech-recognition"
    assert seen["params"]["search"] == "whisper"
    assert res["models"][0]["downloads"] == 1234567
    assert res["models"][1]["id"] == "no-id-field/x"


def test_search_failure_offers_builtin_suggestions(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("network unreachable")
    monkeypatch.setattr(hfhub.requests, "get", boom)
    res = hfhub.search("whisper", "asr")
    assert res.get("error") and res["suggested"]        # 繋がらなくても候補は出す


# ── 生成画像の保管 ─────────────────────────────────────────────────
def test_saved_images_come_back_by_id():
    _reset()
    img_id = hfhub.save_image(b"\x89PNGdata", "image/png", "apple")
    data, mime = hfhub.get_image(img_id)
    assert data == b"\x89PNGdata" and mime == "image/png"
    assert hfhub.get_image("nope") == (None, "")
    assert hfhub.get_image("") == (None, "")
    assert f"/hf/image/{img_id}" in hfhub.image_url(img_id)


def test_memory_store_is_bounded():
    _reset()
    ids = [hfhub.save_image(b"x", "image/png") for _ in range(hfhub.MEM_IMAGE_KEEP + 5)]
    assert len(hfhub._mem_images) == hfhub.MEM_IMAGE_KEEP
    assert hfhub.get_image(ids[-1])[0] == b"x"          # 新しいものは残る
    assert hfhub.get_image(ids[0])[0] is None           # 古いものは押し出される


# ── 画像生成への接続 ───────────────────────────────────────────────
def test_image_engine_falls_back_to_free_when_hf_is_unset(monkeypatch):
    monkeypatch.setattr(hfhub, "_kc", lambda n: "")
    res = imagegen.generate_variants("湖", n=2)
    assert res["ok"] and res["engine"] == "pollinations"
    assert all("pollinations" in i["url"] for i in res["images"])


def test_image_engine_uses_the_assigned_hf_model(monkeypatch):
    _reset()
    _with_token(monkeypatch)
    monkeypatch.setattr(hfhub, "assigned",
                        lambda role: "black-forest-labs/FLUX.1-schnell" if role == "image" else "")
    monkeypatch.setattr(hfhub, "run_image", lambda m, p, w=0, h=0: {
        "ok": True, "data": b"\x89PNGx", "mime": "image/png", "bytes": 5})
    res = imagegen.generate_variants("湖", n=4, aspect="16:9", engine="hf")
    assert res["ok"] and res["engine"] == "hf"
    assert len(res["images"]) == imagegen.HF_MAX_VARIANTS      # 遅いので枚数を絞る
    assert "/hf/image/" in res["images"][0]["url"]
    assert res["model"] == "black-forest-labs/FLUX.1-schnell"


def test_image_engine_hf_reports_why_it_failed(monkeypatch):
    """HFで失敗したとき、黙って無料エンジンにすり替えない。"""
    _reset()
    _with_token(monkeypatch)
    monkeypatch.setattr(hfhub, "assigned", lambda role: "m/x")
    monkeypatch.setattr(hfhub, "run_image", lambda m, p, w=0, h=0: {"error": "モデルの起動中です（約20秒）"})
    res = imagegen.generate_variants("湖", n=1, engine="hf")
    assert res.get("error") and "起動中" in res["error"]


def test_image_engine_hf_without_assignment_explains():
    _reset()
    res = imagegen._generate_hf("湖", 512, 512)
    assert res.get("error") and "未割り当て" in res["error"]


def test_image_engines_status(monkeypatch):
    monkeypatch.setattr(hfhub, "_kc", lambda n: "")
    e = imagegen.engines()
    assert e["pollinations"]["ready"] is True
    assert e["hf"]["ready"] is False and e["hf"]["hint"]


# ── 文字起こしへの接続 ─────────────────────────────────────────────
def test_capture_can_transcribe_with_hf_only(monkeypatch):
    """Geminiキーが無くても、HFのASRモデルがあれば文字起こしできる。"""
    monkeypatch.setattr(tr, "_gemini_ready", lambda: False)
    monkeypatch.setattr(tr, "_hf_asr", lambda: "openai/whisper-large-v3")
    monkeypatch.setattr(tr, "extract_audio", lambda d, n="rec", seconds=0: (b"\xff\xfbmp3", 12.0, False, None))
    monkeypatch.setattr(hfhub, "run_asr", lambda m, a, mime="": {"ok": True, "text": "HFで書き起こしました"})
    res = tr.transcribe(b"webmdata", "rec.webm")
    assert res["ok"] and res["engine"] == "hf"
    assert res["model"] == "openai/whisper-large-v3"
    assert res["seconds"] == 12.0


def test_capture_falls_back_to_gemini_when_hf_fails(monkeypatch):
    monkeypatch.setattr(tr, "_gemini_ready", lambda: True)
    monkeypatch.setattr(tr, "_hf_asr", lambda: "openai/whisper-large-v3")
    monkeypatch.setattr(tr, "extract_audio", lambda d, n="rec", seconds=0: (b"\xff\xfb", 3.0, False, None))
    monkeypatch.setattr(tr, "_transcribe_hf", lambda a: {"error": "モデルの起動中です"})
    monkeypatch.setattr(tr, "_transcribe_gemini", lambda a: {"ok": True, "text": "Geminiで書き起こし"})
    res = tr.transcribe(b"webm", "rec.webm")
    assert res["ok"] and res["engine"] == "gemini"


def test_capture_engine_can_be_forced(monkeypatch):
    monkeypatch.setattr(tr, "_gemini_ready", lambda: True)
    monkeypatch.setattr(tr, "_hf_asr", lambda: "openai/whisper-large-v3")
    monkeypatch.setattr(tr, "extract_audio", lambda d, n="rec", seconds=0: (b"\xff\xfb", 3.0, False, None))
    monkeypatch.setattr(tr, "_transcribe_gemini", lambda a: {"ok": True, "text": "gem"})
    monkeypatch.setattr(tr, "_transcribe_hf", lambda a: {"ok": True, "text": "hf"})
    assert tr.transcribe(b"x", "r.webm", engine="gemini")["engine"] == "gemini"
    assert tr.transcribe(b"x", "r.webm", engine="hf")["engine"] == "hf"


def test_capture_says_what_is_missing(monkeypatch):
    monkeypatch.setattr(tr, "_gemini_ready", lambda: False)
    monkeypatch.setattr(tr, "_hf_asr", lambda: "")
    res = tr.transcribe(b"webmdata", "rec.webm")
    assert res.get("error")
    assert "Gemini" in res["error"] and "HuggingFace" in res["error"]


def test_capture_status_reports_both_engines(monkeypatch):
    monkeypatch.setattr(tr, "_gemini_ready", lambda: False)
    monkeypatch.setattr(tr, "_hf_asr", lambda: "openai/whisper-large-v3")
    monkeypatch.setattr(tr, "ffmpeg_available", lambda: True)
    s = tr.status()
    assert s["transcribe"] is True                      # HFだけでも可
    assert s["engines"] == {"gemini": False, "hf": True}
    assert s["asr_model"] == "openai/whisper-large-v3"


# ── HTTP経路 ───────────────────────────────────────────────────────
def _client():
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


def test_endpoints_crud_and_assign(monkeypatch):
    _reset()
    client = _client()
    store = {}
    monkeypatch.setattr(hfhub.keychain, "set_key", lambda n, v: store.__setitem__(n, v))
    monkeypatch.setattr(hfhub, "_kc", lambda n: store.get(n, "hf_tok" if n == "HUGGINGFACE_TOKEN" else ""))

    r = client.get("/hf/status")
    assert r.status_code == 200
    st = r.json()
    assert st["token_ready"] is True
    assert any(t["key"] == "asr" for t in st["tasks"])
    assert any(role["key"] == "image" for role in st["roles"])

    r = client.post("/hf/models", json={"model": "openai/whisper-large-v3", "task": "asr"})
    assert r.status_code == 200
    row_id = r.json()["model"]["id"]
    assert len(client.get("/hf/models").json()["models"]) == 1

    # 不正な入力は 400
    assert client.post("/hf/models", json={"model": "bad id", "task": "asr"}).status_code == 400
    assert client.post("/hf/models", json={"model": "a/b", "task": "nope"}).status_code == 400

    r = client.post("/hf/assign", json={"role": "asr", "model": "openai/whisper-large-v3"})
    assert r.status_code == 200 and store["HF_ASR_MODEL"] == "openai/whisper-large-v3"
    assert client.post("/hf/assign", json={"role": "nope", "model": "a/b"}).status_code == 400

    r = client.request("DELETE", f"/hf/models/{row_id}")
    assert r.status_code == 200 and "asr" in r.json()["cleared_roles"]
    assert store["HF_ASR_MODEL"] == ""


def test_test_endpoint_reports_failure_as_502(monkeypatch):
    _reset()
    client = _client()
    _with_token(monkeypatch)
    monkeypatch.setattr(hfhub, "test_model", lambda m, t: {"ok": False, "error": "モデルが見つかりません"})
    r = client.post("/hf/test", json={"model": "nope/nope", "task": "image"})
    assert r.status_code == 502 and "見つかりません" in r.json()["error"]

    monkeypatch.setattr(hfhub, "test_model", lambda m, t: {"ok": True, "sample": "画像 30KB"})
    r = client.post("/hf/test", json={"model": "a/b", "task": "image"})
    assert r.status_code == 200 and r.json()["sample"] == "画像 30KB"


def test_row_test_endpoint_records_the_result(monkeypatch):
    _reset()
    client = _client()
    _with_token(monkeypatch)
    row_id = hfhub.add_model("a/b", "image")["model"]["id"]
    monkeypatch.setattr(hfhub, "test_model", lambda m, t: {"ok": False, "error": "起動中です"})
    r = client.post(f"/hf/models/{row_id}/test")
    assert r.status_code == 502
    assert "起動中" in hfhub.get_model(row_id)["last_error"]      # 台帳に残る
    assert client.post("/hf/models/does-not-exist/test").status_code == 404


def test_run_endpoint_returns_image_as_a_url(monkeypatch):
    """画像はbase64を丸ごと返さず、URLで配る（履歴や一覧を重くしない）。"""
    _reset()
    client = _client()
    _with_token(monkeypatch)
    monkeypatch.setattr(hfhub, "run", lambda task, model, **kw: {
        "ok": True, "kind": "image", "data": b"\x89PNGbytes", "mime": "image/png", "bytes": 9})
    r = client.post("/hf/run", json={"model": "a/b", "task": "image", "text": "apple"})
    assert r.status_code == 200
    d = r.json()
    assert d["kind"] == "image" and "/hf/image/" in d["url"]
    assert "data" not in d

    img_id = d["url"].rsplit("/", 1)[-1]
    img = client.get(f"/hf/image/{img_id}")
    assert img.status_code == 200
    assert img.content == b"\x89PNGbytes"
    assert img.headers["content-type"].startswith("image/png")
    assert client.get("/hf/image/nope").status_code == 404


def test_run_endpoint_returns_audio_as_base64(monkeypatch):
    import base64
    _reset()
    client = _client()
    _with_token(monkeypatch)
    monkeypatch.setattr(hfhub, "run", lambda task, model, **kw: {
        "ok": True, "kind": "audio", "data": b"fLaC..", "mime": "audio/flac", "bytes": 6})
    d = client.post("/hf/run", json={"model": "a/b", "task": "tts", "text": "こんにちは"}).json()
    assert base64.b64decode(d["audio_base64"]) == b"fLaC.."


def test_run_endpoint_failure_is_502(monkeypatch):
    _reset()
    client = _client()
    monkeypatch.setattr(hfhub, "run", lambda task, model, **kw: {"error": "トークンが未設定です"})
    assert client.post("/hf/run", json={"model": "a/b", "task": "text"}).status_code == 502


def test_search_endpoint(monkeypatch):
    client = _client()
    monkeypatch.setattr(hfhub, "search", lambda q, t, l: {"ok": True, "models": [{"id": "a/b", "downloads": 1, "likes": 0, "task": ""}]})
    r = client.get("/hf/search?q=whisper&task=asr")
    assert r.status_code == 200 and r.json()["models"][0]["id"] == "a/b"
    monkeypatch.setattr(hfhub, "search", lambda q, t, l: {"error": "接続できませんでした", "suggested": ["x/y"]})
    r = client.get("/hf/search?q=x&task=asr")
    assert r.status_code == 502 and r.json()["suggested"] == ["x/y"]


def test_registered_text_models_appear_in_ai_config(monkeypatch):
    """AI PROVIDER と HF MODELS で選択肢が食い違わないこと。"""
    _reset()
    client = _client()
    hfhub.add_model("my-org/my-llm", "text")
    hfhub.add_model("some/imagemodel", "image")
    chat = client.get("/ai/config").json()["presets"]["chat"]
    assert chat[0] == "my-org/my-llm"          # 自分で入れたものが先頭
    assert "some/imagemodel" not in chat       # 画像モデルは会話の候補に出さない


def test_image_engines_endpoint(monkeypatch):
    client = _client()
    monkeypatch.setattr(hfhub, "_kc", lambda n: "")
    r = client.get("/image/engines")
    assert r.status_code == 200 and r.json()["engines"]["pollinations"]["ready"] is True


def test_generated_image_urls_are_absolute(monkeypatch):
    """相対URLのままだとフロント(別オリジン)で画像が壊れる。必ず絶対にする。"""
    _reset()
    client = _client()
    _with_token(monkeypatch)
    monkeypatch.setattr(hfhub, "assigned", lambda role: "black-forest-labs/FLUX.1-schnell")
    monkeypatch.setattr(hfhub, "run_image", lambda m, p, w=0, h=0: {
        "ok": True, "data": b"\x89PNGx", "mime": "image/png", "bytes": 5})
    monkeypatch.delenv("PUBLIC_API_URL", raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)

    d = client.post("/image/generate", json={"prompt": "湖", "n": 1, "engine": "hf"}).json()
    url = d["images"][0]["url"]
    assert url.startswith("http://testserver/hf/image/"), url

    # 明示のURLがあればそれを使う（Renderの公開URL）
    monkeypatch.setenv("PUBLIC_API_URL", "https://api.example.com/")
    d = client.post("/image/generate", json={"prompt": "湖", "n": 1, "engine": "hf"}).json()
    assert d["images"][0]["url"].startswith("https://api.example.com/hf/image/")


def test_saved_image_artifact_keeps_an_absolute_url(monkeypatch):
    """「生成物」に残るURLも絶対（後から履歴を開いても表示できる）。"""
    _reset()
    client = _client()
    _with_token(monkeypatch)
    monkeypatch.setenv("PUBLIC_API_URL", "https://api.example.com")
    monkeypatch.setattr(hfhub, "assigned", lambda role: "m/x")
    monkeypatch.setattr(hfhub, "run_image", lambda m, p, w=0, h=0: {
        "ok": True, "data": b"\x89PNGx", "mime": "image/png", "bytes": 5})
    d = client.post("/image/generate",
                    json={"prompt": "湖", "n": 1, "engine": "hf", "save": True}).json()
    import artifacts
    art = artifacts.get(d["artifacts"][0]["id"])
    assert art["content"].startswith("https://api.example.com/hf/image/")


def test_free_engine_urls_are_left_alone(monkeypatch):
    """無料エンジンは元から絶対URL。書き換えて壊さないこと。"""
    _reset()
    client = _client()
    monkeypatch.setattr(hfhub, "_kc", lambda n: "")
    d = client.post("/image/generate", json={"prompt": "湖", "n": 1}).json()
    assert d["images"][0]["url"].startswith("https://image.pollinations.ai/")
