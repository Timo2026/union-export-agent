"""media_api.py — /v1/rag/media 多模态情报库 (v7.0, 移植 funasr-gui 已验证范式).

模态 → 转写路径 (全部经 FunASRAdapter, 服务未启动显式 MOCK, 绝不冒充):
  音频 wav/mp3/m4a/flac/ogg → adapter.transcribe (funasr-gui /transcribe 或 omni input_audio)
  图片 png/jpg/jpeg/webp    → adapter.perceive_image (VLM image_url; 聊天截图/图纸两用)
  视频 mp4/mov/avi/mkv      → ffmpeg 抽音轨+3帧 → 上述两路合并; 无 ffmpeg → 显式拒绝标注

转写文本经 LayeredRAGGateway.ingest_document 入 ingest_docs(L2.5),
tags 带 modality/媒体 id, 检索复用现有 /v1/rag/search。

  POST   /v1/rag/media/ingest      multipart file + customer
  GET    /v1/rag/media/docs        清单 (元数据)
  GET    /v1/rag/media/docs/{id}   详情 (含转写全文)
  DELETE /v1/rag/media/docs/{id}   删记录 + 向量 + 原始文件
  GET    /v1/rag/media/status      ASR/VLM/Embed 三服务探活 + 降级来源
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

router = APIRouter(prefix="/v1/rag/media", tags=["media-rag"])

_ROOT = Path(__file__).resolve().parent.parent
MEDIA_DIR = _ROOT / "data" / "media"
REGISTRY = _ROOT / "data" / "media_docs.json"
MAX_BYTES = 64 * 1024 * 1024

AUDIO_EXT = {"wav", "mp3", "m4a", "flac", "ogg", "wave", "mp4a"}
IMAGE_EXT = {"png", "jpg", "jpeg", "webp", "bmp"}
VIDEO_EXT = {"mp4", "mov", "avi", "mkv", "webm"}

_CHAT_IMG_PROMPT = ("请完整转写图片中的全部可见文字 (聊天截图逐条: 发送人: 内容)。"
                    "若为机械图纸/照片, 提取零件类型、可见尺寸、材料/表面处理线索、"
                    "公差标注、数量/批量与特征。只写可见事实, 不臆测, 不解释。")


def classify_kind(filename: str) -> str:
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext in AUDIO_EXT:
        return "audio"
    if ext in IMAGE_EXT:
        return "image"
    if ext in VIDEO_EXT:
        return "video"
    return "unsupported"


# ---------------- registry ----------------

def _load() -> List[Dict[str, Any]]:
    if REGISTRY.exists():
        try:
            return json.loads(REGISTRY.read_text(encoding="utf-8")).get("docs", [])
        except Exception:
            return []
    return []


def _save(docs: List[Dict[str, Any]]) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"docs": docs, "updated_at": time.strftime(
        "%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        tmp.replace(REGISTRY)
    except PermissionError:  # Windows 瞬时占用
        time.sleep(0.2)
        tmp.replace(REGISTRY)


# ---------------- 转写 ----------------

def _transcribe_media(path: str, kind: str, ctrl) -> Dict[str, Any]:
    """→ {ok, text, mock, source, note?}"""
    adapter = ctrl.funasr
    if kind == "audio":
        r = adapter.transcribe(path)
        return {"ok": bool(r.get("text")), "text": r.get("text", ""),
                "mock": bool(r.get("_mock")), "source": r.get("_source", "?")}
    if kind == "image":
        r = adapter.perceive_image(path, prompt=_CHAT_IMG_PROMPT)
        text = r.get("perception") if isinstance(r.get("perception"), str) else \
            json.dumps(r.get("perception"), ensure_ascii=False) if r.get("perception") else ""
        return {"ok": bool(text), "text": text,
                "mock": bool(r.get("_mock")), "source": r.get("_source", "?")}
    # video: 需 ffmpeg (audio 轨 + 3 帧)
    if shutil.which("ffmpeg") is None:
        return {"ok": False, "text": "", "mock": True,
                "source": "MOCK:video-needs-ffmpeg",
                "note": "本机无 ffmpeg, 视频链路需先安装 (不冒充)"}
    tmp = Path(path).with_suffix("") .parent / f"_{uuid.uuid4().hex[:6]}"
    tmp.mkdir(parents=True, exist_ok=True)
    parts: List[str] = []
    mock = False
    sources: List[str] = []
    wav = tmp / "audio.wav"
    if _run_ff(["-i", path, "-vn", "-ac", "1", "-ar", "16000", str(wav), "-y"]) and wav.exists():
        a = _transcribe_media(str(wav), "audio", ctrl)
        if a["ok"]:
            parts.append(f"[音频转写] {a['text']}")
        mock = mock or a["mock"]
        sources.append(a["source"])
    for i, frac in enumerate((0.2, 0.5, 0.8)):
        frame = tmp / f"frame{i}.png"
        if _run_ff(["-ss", _video_time(path, frac), "-i", path,
                    "-frames:v", "1", str(frame), "-y"]) and frame.exists():
            v = _transcribe_media(str(frame), "image", ctrl)
            if v["ok"]:
                parts.append(f"[画面@{int(frac * 100)}%] {v['text']}")
            mock = mock or v["mock"]
            sources.append(v["source"])
    shutil.rmtree(tmp, ignore_errors=True)
    text = "\n".join(parts)
    return {"ok": bool(text), "text": text, "mock": mock,
            "source": "+".join(dict.fromkeys(sources)) or "MOCK:video-empty"}


def _run_ff(args: List[str]) -> bool:
    try:
        r = subprocess_run_ff(args)
        return r.returncode == 0
    except Exception:
        return False


def subprocess_run_ff(args: List[str]):
    import subprocess
    return subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", *args],
                          capture_output=True, text=True, timeout=120)


def _video_time(path: str, frac: float) -> str:
    import subprocess
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=20)
        dur = float(r.stdout.strip() or 0)
    except Exception:
        dur = 0.0
    return f"{max(0.1, dur * frac):.2f}" if dur > 0 else "0.1"


# ---------------- endpoints ----------------

@router.post("/ingest")
async def ingest_media(file: UploadFile = File(...), customer: str = Form("")):
    from services.api_server import ctrl
    from services.customer_id import derive_customer_id
    name = file.filename or "media.bin"
    kind = classify_kind(name)
    if kind == "unsupported":
        raise HTTPException(400, f"不支持的模态: {name} (支持 音频/图片/视频)")
    # BUG-3: 自由文本 customer 串归一 — 邮件地址/'Name <addr>' → 规范 CUST-<hash8>,
    # 与 customers 表同一口径; 非地址的自定义标签 (JIEVO 等) 原样保留
    customer = (customer or "").strip()
    if customer and ("@" in customer or "<" in customer):
        customer = derive_customer_id({"email": customer})
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch for ch in name if ch.isalnum() or ch in "._-")[:80] or "media.bin"
    dest = MEDIA_DIR / f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}_{safe}"
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    if dest.stat().st_size > MAX_BYTES:
        dest.unlink(missing_ok=True)
        raise HTTPException(413, "媒体超过 64MB 上限")

    c = ctrl()
    tr = _transcribe_media(str(dest), kind, c)
    gw = c.rag_gateway
    doc_id = f"media:{dest.stem}"
    indexed = False
    embed_source = gw.embedder.source if gw is not None else "no-gateway"
    if tr["ok"] and gw is not None:
        r = gw.ingest_document(doc_id, tr["text"], customer_id=customer or None,
                               tags=[f"modality:{kind}", "media"])
        indexed = bool(r.get("ok"))
        embed_source = gw.embedder.source
    doc = {"id": dest.stem, "filename": name, "modality": kind,
           "customer_id": customer, "size_bytes": dest.stat().st_size,
           "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "transcribe_mock": tr["mock"], "transcribe_source": tr["source"],
           "indexed": indexed, "embed_source": embed_source,
           "transcript_chars": len(tr["text"]), "doc_id": doc_id,
           "note": tr.get("note", "")}
    docs = _load()
    docs.insert(0, doc)
    _save(docs)
    (MEDIA_DIR / f"{dest.stem}.txt").write_text(tr["text"], encoding="utf-8")
    if not tr["ok"] and kind != "video":
        # 显式 MOCK 不算失败: 记录保留, 响应带 mock 标注供 UI 展示
        doc["indexed"] = False
    return {"ok": True, "doc": doc, "transcript_preview": tr["text"][:400]}


@router.get("/docs")
def list_media_docs(customer: str = "", modality: str = "") -> Dict[str, Any]:
    out = _load()
    if customer:
        out = [d for d in out if customer.lower() in str(d.get("customer_id", "")).lower()]
    if modality:
        out = [d for d in out if d.get("modality") == modality]
    return {"items": out, "total": len(out),
            "modalities": sorted({d.get("modality", "") for d in _load()})}


@router.get("/docs/{doc_key}")
def get_media_doc(doc_key: str) -> Dict[str, Any]:
    _key_guard(doc_key)
    d = next((x for x in _load() if x.get("id") == doc_key), None)
    if d is None:
        raise HTTPException(404, f"媒体记录不存在: {doc_key}")
    txt = MEDIA_DIR / f"{doc_key}.txt"
    return {**d, "transcript": txt.read_text(encoding="utf-8") if txt.exists() else ""}


def _key_guard(key: str) -> None:
    if not key or any(ch in key for ch in '/\\:*?"<>|') or ".." in key:
        raise HTTPException(400, "bad id")


@router.delete("/docs/{doc_key}")
def delete_media_doc(doc_key: str) -> Dict[str, Any]:
    _key_guard(doc_key)
    docs = _load()
    rest = [x for x in docs if x.get("id") != doc_key]
    if len(rest) == len(docs):
        raise HTTPException(404, f"媒体记录不存在: {doc_key}")
    _save(rest)
    from services.api_server import ctrl
    gw = ctrl().rag_gateway
    removed_vec = bool(gw and gw.delete_ingested_doc(f"media:{doc_key}"))
    for p in list(MEDIA_DIR.glob(f"{doc_key}.*")):  # 原始媒体 + .txt 转写稿
        if p.is_file():
            p.unlink()
    return {"ok": True, "id": doc_key, "vector_removed": removed_vec}


@router.get("/status")
def media_status() -> Dict[str, Any]:
    from services.api_server import ctrl
    c = ctrl()
    a = c.funasr
    gw = c.rag_gateway
    embed = None
    if gw is not None:
        e = gw.embedder
        embed = {"url": e.url, "live": bool(e.degraded is False),
                 "degraded": bool(e.degraded), "source": e.source, "dim": e.dim}
    return {"asr": {"mode": a.asr_mode, "url": a.asr_url or a.base_url,
                    "online": a.online, "source": a.source_label()},
            "vlm": {"url": a.vlm_url, "online": a.vlm_online(),
                    "model": a.vlm_model},
            "embed": embed, "ffmpeg": shutil.which("ffmpeg") is not None,
            "docs": len(_load())}
