"""test_funasr_adapter.py — FunASRAdapter 双模 (funasr-gui / Omni) 测试.

节点 Omni :8002 实测口径 (vLLM OpenAI 兼容):
  根 /health -> 200; /v1/health -> 404 (health 探测必须剥 /v1)
  POST /v1/chat/completions 接受 input_audio content part (200, finish=stop,
  52 vs 30 prompt_tokens 证明音频真被感知 —— 详见节点 audio probe 实证).

用 http.server 假服务捕获真实 urllib 请求, 断言 URL 构造 + payload schema +
离线显式 MOCK 降级; 不碰网络外真实服务。
"""
from __future__ import annotations

import base64
import json
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple

import pytest

from adapters.funasr_adapter import FunASRAdapter


class _FakeState:
    def __init__(self) -> None:
        self.requests: List[Tuple[str, str, Dict[str, Any]]] = []
        self.chat_response: Optional[Dict[str, Any]] = None

    def reset(self, chat_response: Optional[Dict[str, Any]] = None) -> None:
        self.requests.clear()
        self.chat_response = chat_response


class FakeAdapter:
    """把网络调用换成记录式假服务器; base_url 指向它。"""
    def __init__(self, response: Optional[Dict[str, Any]] = None) -> None:
        self.state = _FakeState()
        handler = self._make_handler()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def _make_handler(self):
        state = self.state

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):  # 静默
                pass

            def _record(self, method: str) -> None:
                body: Dict[str, Any] = {}
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    try:
                        body = json.loads(self.rfile.read(n).decode("utf-8"))
                    except Exception:
                        body = {"_unparsed": True}
                state.requests.append((method, self.path, body))

            def _json(self, obj: Dict[str, Any], code: int = 200) -> None:
                data = json.dumps(obj).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._record("GET")
                # /v1/health 故意 404 —— 复刻节点 Omni 实测 (仅根 /health 可用)
                if self.path == "/v1/health":
                    self._json({"detail": "Not Found"}, code=404)
                elif self.path in ("/health", "/v1/models"):
                    self._json({"status": "ok", "data": [{"id": "fake-model"}]})
                else:
                    self._json({"results": [], "hits": []})

            def do_POST(self):
                self._record("POST")
                if self.path == "/api/rag/search":
                    # 复刻 Timo 引擎真实契约 (节点 openapi 实证 2026-09-22):
                    # POST /api/rag/search body {"query","limit"} -> {"query","results","total"}
                    self._json({"query": "", "results": [
                        {"doc": "6061 阳极氧化案例", "score": 0.91}], "total": 1})
                elif state.chat_response is None:
                    self._json({"detail": "no response configured"}, code=500)
                else:
                    self._json(state.chat_response)

        return H

    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@pytest.fixture
def fake() -> FakeAdapter:
    srv = FakeAdapter()
    yield srv
    srv.close()


@pytest.fixture
def wav_file(tmp_path):
    p = tmp_path / "tone.wav"
    p.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00")
    return p


def _chat_ok(content: str, model: str = "nemotron-omni-30b-a3b") -> Dict[str, Any]:
    return {"model": model,
            "choices": [{"finish_reason": "stop",
                         "message": {"role": "assistant", "content": content}}]}


# ---------------- health / source_label ----------------
def test_health_probe_strips_v1_and_label_uses_netloc(fake: FakeAdapter):
    a = FunASRAdapter({"funasr": {"base_url": f"{fake.url()}/v1"}})
    assert a.health() is True
    paths = [p for m, p, b in fake.state.requests if m == "GET"]
    assert paths == ["/health"]                       # 剥 /v1 后探根 health
    assert a.source_label() == f"live:127.0.0.1:{fake.port}"


def test_health_probe_plain_base_url_unchanged(fake: FakeAdapter):
    a = FunASRAdapter({"funasr": {"base_url": fake.url()}})
    assert a.health() is True
    assert [p for m, p, b in fake.state.requests] == ["/health"]


def test_offline_source_label_is_mock():
    a = FunASRAdapter({"funasr": {"base_url": "http://127.0.0.1:59997/v1"}})
    assert a.health() is False
    assert a.source_label() == "MOCK:funasr-offline"


# ---------------- ASR omni 模式 ----------------
def test_transcribe_omni_posts_input_audio_part(fake: FakeAdapter, wav_file):
    fake.state.reset(_chat_ok("客户要求 6061 铝件 50 件"))
    a = FunASRAdapter({"funasr": {
        "base_url": f"{fake.url()}/v1", "asr_url": f"{fake.url()}/v1",
        "asr_mode": "omni", "asr_model": "nemotron-omni-30b-a3b"}})
    r = a.transcribe(str(wav_file))
    assert r["_mock"] is False and r["text"] == "客户要求 6061 铝件 50 件"
    posts = [r for r in fake.state.requests if r[0] == "POST"]
    assert len(posts) == 1
    m, path, body = posts[0]
    assert (m, path) == ("POST", "/v1/chat/completions")
    assert body["model"] == "nemotron-omni-30b-a3b"
    assert body["max_tokens"] == 2000                 # 默认预算
    content = body["messages"][0]["content"]
    parts = {p["type"]: p for p in content}
    assert "text" in parts and "input_audio" in parts
    aud = parts["input_audio"]["input_audio"]
    assert aud["format"] == "wav"
    assert aud["data"] == base64.b64encode(wav_file.read_bytes()).decode()
    assert r["_source"] == f"live:omni-asr:127.0.0.1:{fake.port}"


def test_max_tokens_configurable_for_reasoning_model(fake: FakeAdapter, wav_file):
    # 推理模型会把预算烧在 reasoning 上: 2000 实测偶发 finish=length 空 content,
    # 4096 实测两次 finish=stop (节点 budget probe) — 预算必须可配。
    fake.state.reset(_chat_ok("ok"))
    a = FunASRAdapter({"funasr": {"base_url": f"{fake.url()}/v1",
                                  "asr_mode": "omni", "asr_model": "m",
                                  "max_tokens": 4096}})
    a.transcribe(str(wav_file))
    posts = [r for r in fake.state.requests if r[0] == "POST"]
    assert posts[0][2]["max_tokens"] == 4096


def test_max_tokens_floor_for_reasoning_model(fake: FakeAdapter, wav_file):
    # BUG-2 (09-25 巡检): 小 max_tokens 配置必须被地板 600 提起。
    # 节点实测 max_tokens=200 → finish_reason=length 空 content (转写假阴性)。
    fake.state.reset(_chat_ok("ok"))
    a = FunASRAdapter({"funasr": {"base_url": f"{fake.url()}/v1",
                                  "asr_mode": "omni", "asr_model": "m",
                                  "max_tokens": 200}})
    a.transcribe(str(wav_file))
    posts = [r for r in fake.state.requests if r[0] == "POST"]
    assert posts[0][2]["max_tokens"] >= 600


def test_transcribe_omni_audio_format_follows_extension(fake: FakeAdapter, tmp_path):
    mp3 = tmp_path / "voice.mp3"
    mp3.write_bytes(b"ID3fake-bytes")
    fake.state.reset(_chat_ok("ok"))
    a = FunASRAdapter({"funasr": {"base_url": f"{fake.url()}/v1",
                                  "asr_mode": "omni", "asr_model": "m"}})
    a.transcribe(str(mp3))
    posts = [r for r in fake.state.requests if r[0] == "POST"]
    assert len(posts) == 1
    _, _, body = posts[0]
    parts = {p["type"]: p for p in body["messages"][0]["content"]}
    assert parts["input_audio"]["input_audio"]["format"] == "mp3"


def test_transcribe_funasr_mode_default_unchanged(fake: FakeAdapter, wav_file):
    fake.state.reset({"text": "关键尺寸可以放宽到 0.05 毫米"})
    a = FunASRAdapter({"funasr": {"base_url": fake.url()}})
    r = a.transcribe(str(wav_file))
    assert r["_mock"] is False and r["text"] == "关键尺寸可以放宽到 0.05 毫米"
    posts = [r for r in fake.state.requests if r[0] == "POST"]
    assert len(posts) == 1
    m, path, body = posts[0]
    assert (m, path) == ("POST", "/transcribe")
    assert body["audio_b64"] == base64.b64encode(wav_file.read_bytes()).decode()
    assert r["_source"] == "live:/transcribe"


def test_transcribe_omni_empty_content_degrades_explicit_mock(fake: FakeAdapter, wav_file):
    fake.state.reset({"model": "nemotron-omni-30b-a3b",
                      "choices": [{"finish_reason": "length",
                                   "message": {"role": "assistant", "content": "",
                                               "reasoning_content": "..."}}]})
    a = FunASRAdapter({"funasr": {"base_url": f"{fake.url()}/v1",
                                  "asr_mode": "omni", "asr_model": "m"}})
    r = a.transcribe(str(wav_file), mock_text="占位转写")
    assert r["_mock"] is True
    assert "MOCK(transcribe failed" in r["_source"]
    assert "content" in r["_source"]                 # 原因如实可查
    assert r["text"] == "占位转写"


def test_transcribe_offline_explicit_mock(wav_file):
    a = FunASRAdapter({"funasr": {"base_url": "http://127.0.0.1:59997/v1",
                                  "asr_mode": "omni", "asr_model": "m"}})
    r = a.transcribe(str(wav_file), mock_text="离线占位")
    assert r["_mock"] is True and r["_source"] == "MOCK:funasr-offline"
    assert r["text"] == "离线占位"


def test_transcribe_allow_mock_false_offline_raises(wav_file):
    a = FunASRAdapter({"funasr": {"base_url": "http://127.0.0.1:59997/v1",
                                  "asr_mode": "omni", "asr_model": "m",
                                  "allow_mock": False}})
    with pytest.raises(RuntimeError):
        a.transcribe(str(wav_file))


def test_transcribe_read_error_degrades_mock_not_crash(fake: FakeAdapter, tmp_path):
    fake.state.reset(_chat_ok("x"))
    a = FunASRAdapter({"funasr": {"base_url": f"{fake.url()}/v1",
                                  "asr_mode": "omni", "asr_model": "m"}})
    r = a.transcribe(str(tmp_path / "missing.wav"), mock_text="占位")
    assert r["_mock"] is True and "MOCK(transcribe failed" in r["_source"]


# ---------------- VLM 感知 ----------------
def test_perceive_image_configured_model_and_single_v1(fake: FakeAdapter, tmp_path):
    img = tmp_path / "drawing.png"
    img.write_bytes(b"\x89PNG fake")
    fake.state.reset(_chat_ok("可见 2 个 M6 螺纹孔"))
    a = FunASRAdapter({"funasr": {
        "vlm_url": f"{fake.url()}/v1", "vlm_model": "nemotron-omni-30b-a3b"}})
    r = a.perceive_image(str(img))
    assert r["ok"] is True and r["perception"] == "可见 2 个 M6 螺纹孔"
    posts = [r for r in fake.state.requests if r[0] == "POST"]
    assert len(posts) == 1
    m, path, body = posts[0]
    assert (m, path) == ("POST", "/v1/chat/completions")   # /v1 只拼一次
    assert body["model"] == "nemotron-omni-30b-a3b"
    assert r["_source"] == f"live:vlm:127.0.0.1:{fake.port}"


def test_perceive_image_vlm_url_without_v1(fake: FakeAdapter, tmp_path):
    img = tmp_path / "d.jpg"
    img.write_bytes(b"\xff\xd8 fake")
    fake.state.reset(_chat_ok("ok"))
    a = FunASRAdapter({"funasr": {"vlm_url": fake.url(), "vlm_model": "m"}})
    r = a.perceive_image(str(img))
    assert r["ok"] is True
    posts = [r for r in fake.state.requests if r[0] == "POST"]
    assert len(posts) == 1
    assert posts[0][1] == "/v1/chat/completions"


def test_perceive_image_offline_explicit_mock(tmp_path):
    a = FunASRAdapter({"funasr": {"vlm_url": "http://127.0.0.1:59997",
                                  "vlm_model": "m"}})
    r = a.perceive_image(str(tmp_path / "x.png"))
    assert r["ok"] is False and r["_mock"] is True
    assert r["_source"] == "MOCK:vlm-offline"


# ---------------- content: null (节点实测: Omni 音频路径偶发 null content) ----------------
def test_transcribe_omni_null_content_degrades_with_honest_reason(fake: FakeAdapter, wav_file):
    fake.state.reset({"model": "m", "choices": [{"finish_reason": "stop",
                                                 "message": {"role": "assistant", "content": None}}]})
    a = FunASRAdapter({"funasr": {"base_url": f"{fake.url()}/v1",
                                  "asr_mode": "omni", "asr_model": "m"}})
    r = a.transcribe(str(wav_file), mock_text="占位")
    assert r["_mock"] is True
    assert "content" in r["_source"]                 # 原因是 "content 为空", 不是 AttributeError
    assert "AttributeError" not in r["_source"]


def test_perceive_image_null_content_degrades_with_honest_reason(fake: FakeAdapter, tmp_path):
    img = tmp_path / "d.png"
    img.write_bytes(b"\x89PNG fake")
    fake.state.reset({"model": "m", "choices": [{"finish_reason": "stop",
                                                 "message": {"role": "assistant", "content": None}}]})
    a = FunASRAdapter({"funasr": {"vlm_url": fake.url(), "vlm_model": "m"}})
    r = a.perceive_image(str(img))
    assert r["ok"] is False and r["_mock"] is True
    assert "content" in r["_source"] and "AttributeError" not in r["_source"]


def test_perceive_image_vlm_online_probes_models(fake: FakeAdapter):
    a = FunASRAdapter({"funasr": {"vlm_url": f"{fake.url()}/v1", "vlm_model": "m"}})
    assert a.vlm_online() is True
    assert [p for m, p, b in fake.state.requests] == ["/v1/models"]


# ---------------- RAG: 引擎真实契约 (节点实测 2026-09-22) ----------------
def test_rag_search_posts_api_path_with_query_field(fake: FakeAdapter):
    """节点 openapi 实证: Timo 引擎 RAG = POST /api/rag/search, body {"query","limit"}.

    旧实现 GET /rag/search?q=… 在节点 404 → 假 MOCK 降级 (引擎实际在线).
    customer_id 透传保持 (test_b3_quote_anchor 契约).
    """
    a = FunASRAdapter({"funasr": {"base_url": fake.url()}})
    r = a.rag_search("6061 anodizing", limit=3, customer_id="CUST-0001")
    posts = [(m, p, b) for m, p, b in fake.state.requests if m == "POST"]
    assert posts, f"no POST recorded: {fake.state.requests}"
    _, path, body = posts[0]
    assert path == "/api/rag/search"
    assert body.get("query") == "6061 anodizing"
    assert body.get("limit") == 3
    assert body.get("customer_id") == "CUST-0001"
    assert r["_mock"] is False
    assert r["_source"] == "live:/api/rag/search"
    assert r["hits"] and r["hits"][0]["score"] == 0.91


def test_rag_search_offline_explicit_mock(fake: FakeAdapter, monkeypatch):
    """离线仍显式 MOCK, 不冒充在线 (铁律)."""
    a = FunASRAdapter({"funasr": {"base_url": fake.url()}})
    monkeypatch.setattr(FunASRAdapter, "health", lambda self: False)
    a._online = None
    r = a.rag_search("x", mock_hits=[{"case": "S3"}])
    assert r["_mock"] is True and r["_source"] == "MOCK:funasr-offline"
