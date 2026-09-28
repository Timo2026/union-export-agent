"""test_media_api.py — /v1/rag/media 多模态入库 (显式 MOCK 语义 + 库管理).

转写/入库/存储路径全部打桩: 不依赖 :8089/:1234/:1278 存活, 不污染 data/。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import services.media_api as ma
from services.api_server import app, ctrl


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ma, "MEDIA_DIR", tmp_path / "media")
    monkeypatch.setattr(ma, "REGISTRY", tmp_path / "media_docs.json")
    c = ctrl()
    monkeypatch.setattr(c.funasr, "transcribe", lambda p: {
        "text": "客户语音: 这批 50 件 6061 法兰, 预算 8 万美元", "_mock": False,
        "_source": "live:fake-asr"})
    monkeypatch.setattr(c.funasr, "perceive_image", lambda p, prompt=None: {
        "ok": True, "perception": "Customer: hello price?\nSales: quote 500k",
        "_mock": False, "_source": "live:fake-vlm"})
    calls = {}

    def fake_ingest(doc_id, text, customer_id=None, tags=None):
        calls[doc_id] = {"text": text, "customer_id": customer_id, "tags": tags}
        return {"ok": True, "id": doc_id}

    assert c.rag_gateway is not None, "测试前提: rag_gateway 已构建"
    monkeypatch.setattr(c.rag_gateway, "ingest_document", fake_ingest)
    monkeypatch.setattr(c.rag_gateway, "delete_ingested_doc",
                        lambda did: calls.pop(did, None) is not None)
    monkeypatch.setattr(c.rag_gateway.embedder, "source", "live:fake-embed",
                        raising=False)
    return TestClient(app)


def _upload(client, name, content=b"fake-bytes"):
    return client.post("/v1/rag/media/ingest", files={"file": (name, content)},
                       data={"customer": "ACME"})


def test_ingest_audio_indexed(client):
    r = _upload(client, "call.wav")
    assert r.status_code == 200
    doc = r.json()["doc"]
    assert doc["modality"] == "audio" and doc["transcribe_mock"] is False
    assert doc["indexed"] is True and doc["customer_id"] == "ACME"
    key = next(iter(_doc_ids(client)))
    detail = client.get(f"/v1/rag/media/docs/{key}").json()
    assert "6061" in detail["transcript"]


def test_ingest_image_screen_transcript(client):
    doc = _upload(client, "wechat.png", b"pngbytes").json()["doc"]
    assert doc["modality"] == "image" and doc["indexed"] is True
    assert doc["transcribe_source"] == "live:fake-vlm"


def test_unsupported_ext_rejected(client):
    r = _upload(client, "notes.txt")
    assert r.status_code == 400 and "模态" in r.json()["detail"]


def test_video_without_ffmpeg_explicit_mock(client, monkeypatch):
    monkeypatch.setattr(ma.shutil, "which", lambda x: None)
    body = _upload(client, "demo.mp4", b"vid").json()
    doc = body["doc"]
    assert doc["indexed"] is False and doc["transcribe_mock"] is True
    assert "ffmpeg" in doc["transcribe_source"] or "ffmpeg" in doc["note"]


def test_list_filter_and_delete(client):
    _upload(client, "a.wav")
    _upload(client, "b.png")
    lst = client.get("/v1/rag/media/docs").json()
    assert lst["total"] == 2 and set(lst["modalities"]) == {"audio", "image"}
    assert client.get("/v1/rag/media/docs", params={"modality": "audio"}).json()["total"] == 1
    assert client.get("/v1/rag/media/docs", params={"customer": "nope"}).json()["total"] == 0
    one = lst["items"][0]["id"]
    assert client.delete(f"/v1/rag/media/docs/{one}").json()["ok"] is True
    assert client.get("/v1/rag/media/docs").json()["total"] == 1
    # %2F 会被 HTTP 栈做点段归一化 (404 拦在路由前); %5C 原样到达 handler 验证 _key_guard
    assert client.delete("/v1/rag/media/docs/..%5Cx").status_code == 400
    assert client.get("/v1/rag/media/docs/NOPE").status_code == 404


def test_status_shape(client):
    s = client.get("/v1/rag/media/status").json()
    for k in ("asr", "vlm", "embed", "ffmpeg", "docs"):
        assert k in s
    assert s["asr"]["mode"] in ("funasr", "omni", "cli")  # cli = 节点中文 ASR 活链 (settings asr_mode: cli)
    assert isinstance(s["asr"]["online"], bool) and s["asr"]["source"]


def _doc_ids(client):
    return [d["id"] for d in client.get("/v1/rag/media/docs").json()["items"]]
