"""FunASRAdapter — 多模态 Intake + RAG 记忆层 (双模: funasr-gui / 节点 Omni).

开发机 funasr-gui (server.py, 装机机本地服务):
  GET  /health
  POST /transcribe            语音转写 (Qwen3-ASR-0.6B @ :8089)
  GET  /rag/search?q=&limit=  语义检索 (embedding @ :1278 + SQLite FTS5 + RRF)
  GET  /rag/ask?q=            RAG 问答
  VLM  qwen3.8-27b @ :1234 (OpenAI 兼容, 图纸/图片理解)

节点 Omni 模式 (vLLM OpenAI 兼容, nemotron-omni-30b-a3b @ :8002, 实测口径):
  根 /health -> 200; /v1/health -> 404        → health 探测剥 /v1 后探根
  POST /v1/chat/completions                   → input_audio content part 收音频
                                                (实证: 带音频 52 vs 不带 30 prompt_tokens)
  由 funasr.asr_mode=omni + asr_model/vlm_model 配置开关, URL 归一化剥尾部 /v1。

降级原则 (对齐冻结 PRD):
  服务未启动/调用失败 → 返回显式 MOCK 结果, _mock=True, 绝不冒充生产转写/检索。
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

_ASR_PROMPT = ("请将以下音频中的语音内容完整转写为文本。"
               "只输出转写文本本身, 不要添加解释、翻译或格式。")


def _strip_v1(url: str) -> str:
    """剥掉尾部 /v1 — 调用方自行拼 /v1/chat/completions, 避免双 /v1。"""
    u = url.rstrip("/")
    return u[:-3].rstrip("/") if u.endswith("/v1") else u


def _netloc(url: str) -> str:
    return urllib.parse.urlparse(url).netloc or url


class FunASRAdapter:
    def __init__(self, cfg: Dict[str, Any]):
        f = cfg.get("funasr", cfg)
        self.base_url: str = str(f.get("base_url", "http://127.0.0.1:8866")).rstrip("/")
        self.asr_url: str = _strip_v1(str(f.get("asr_url", self.base_url)))
        self.asr_mode: str = str(f.get("asr_mode", "funasr"))     # funasr | omni
        self.asr_model: str = str(f.get("asr_model", "Qwen3-ASR-0.6B"))
        self.vlm_url: str = _strip_v1(str(f.get("vlm_url", "http://127.0.0.1:1234")))
        self.vlm_model: str = str(f.get("vlm_model", "qwen3.8-27b"))
        self.timeout: int = int(f.get("timeout_s", 30))
        # 推理模型 (Omni nemotron_v3) 会把预算烧在 reasoning 上: 2000 实测偶发
        # finish=length 空 content, 4096 实测两次 finish=stop — 预算可配。
        self.max_tokens: int = int(f.get("max_tokens", 2000))
        self.allow_mock: bool = bool(f.get("allow_mock", True))
        self._online: Optional[bool] = None
        self._vlm_online: Optional[bool] = None

    def health(self) -> bool:
        try:
            with urllib.request.urlopen(f"{_strip_v1(self.base_url)}/health", timeout=4) as r:
                self._online = r.status == 200
        except Exception:
            self._online = False
        return bool(self._online)

    @property
    def online(self) -> bool:
        if self._online is None:
            self.health()
        return bool(self._online)

    def source_label(self) -> str:
        return f"live:{_netloc(self.base_url)}" if self.online else "MOCK:funasr-offline"

    # ---------- ASR ----------
    def transcribe(self, audio_path: str, mock_text: Optional[str] = None) -> Dict[str, Any]:
        """语音 → 文本证据. 离线时若提供 mock_text 则显式标注 MOCK。"""
        if self.asr_mode == "omni":
            return self._transcribe_omni(audio_path, mock_text)
        if self.online:
            try:
                import base64
                with open(audio_path, "rb") as fh:
                    b64 = base64.b64encode(fh.read()).decode()
                data = json.dumps({"audio_b64": b64}).encode("utf-8")
                req = urllib.request.Request(f"{self.base_url}/transcribe", data=data,
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    j = json.loads(r.read().decode("utf-8"))
                return {"text": j.get("text", j.get("transcript", "")), "_mock": False,
                        "_source": "live:/transcribe", "_raw": j}
            except Exception as e:
                if not self.allow_mock:
                    raise
                return {"text": mock_text or "", "_mock": True, "_source": f"MOCK(transcribe failed: {e!r})"}
        if not self.allow_mock:
            raise RuntimeError("funasr offline and mock disabled")
        return {"text": mock_text or "", "_mock": True, "_source": "MOCK:funasr-offline"}

    def _transcribe_omni(self, audio_path: str, mock_text: Optional[str] = None) -> Dict[str, Any]:
        """Omni ASR: POST {asr_url}/v1/chat/completions, input_audio content part。"""
        if self.online:
            try:
                import base64
                with open(audio_path, "rb") as fh:
                    b64 = base64.b64encode(fh.read()).decode()
                ext = audio_path.rsplit(".", 1)[-1].lower() if "." in audio_path else "wav"
                fmt = "wav" if ext == "wave" else ext
                payload = {
                    "model": self.asr_model,
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": _ASR_PROMPT},
                        {"type": "input_audio", "input_audio": {"data": b64, "format": fmt}}]}],
                    "max_tokens": self.max_tokens, "temperature": 0.1,
                }
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(f"{self.asr_url}/v1/chat/completions", data=data,
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    j = json.loads(r.read().decode("utf-8"))
                return {"text": self._extract_content(j), "_mock": False,
                        "_source": f"live:omni-asr:{_netloc(self.asr_url)}", "_raw": j}
            except Exception as e:
                if not self.allow_mock:
                    raise
                return {"text": mock_text or "", "_mock": True, "_source": f"MOCK(transcribe failed: {e!r})"}
        if not self.allow_mock:
            raise RuntimeError("omni asr offline and mock disabled")
        return {"text": mock_text or "", "_mock": True, "_source": "MOCK:funasr-offline"}

    @staticmethod
    def _extract_content(j: Dict[str, Any]) -> str:
        """OpenAI chat completion → content; 无 choices / 空 content 显式抛错 (调用方降级 MOCK)。"""
        choices = j.get("choices")
        if not choices:
            err = j.get("error")
            if isinstance(err, dict):
                err = err.get("message", str(err))
            raise RuntimeError(f"响应无 choices: {err or json.dumps(j)[:200]}")
        msg = choices[0].get("message", {})
        # OpenAI 兼容服务对空回复可能给 content: null (节点 Omni 音频路径实测偶发) — None 视同空
        text = msg.get("content") or ""
        # 推理模型: content 可能空 (reasoning_content 耗尽 token 预算)
        if not text.strip():
            rc_len = len(msg.get("reasoning_content", ""))
            raise RuntimeError(f"content 为空 (推理模型 token 预算不足; "
                               f"reasoning={rc_len} chars, finish={choices[0].get('finish_reason')})")
        return text

    # ---------- RAG ----------
    def rag_search(self, query: str, limit: int = 5, mock_hits: Optional[List[Dict]] = None,
                   customer_id: Optional[str] = None) -> Dict[str, Any]:
        if self.online:
            try:
                # Timo 引擎契约 (节点 openapi 实证 2026-09-22): POST /api/rag/search,
                # body {"query","limit"}; 响应 {"query","results","total"}
                payload: Dict[str, Any] = {"query": query, "limit": limit}
                if customer_id:
                    payload["customer_id"] = customer_id
                req = urllib.request.Request(
                    f"{self.base_url}/api/rag/search",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    j = json.loads(r.read().decode("utf-8"))
                hits = j.get("results", j.get("hits", j if isinstance(j, list) else []))
                return {"hits": hits, "_mock": False, "_source": "live:/api/rag/search"}
            except Exception as e:
                if not self.allow_mock:
                    raise
                return {"hits": mock_hits or [], "_mock": True, "_source": f"MOCK(rag failed: {e!r})"}
        if not self.allow_mock:
            raise RuntimeError("funasr offline and mock disabled")
        return {"hits": mock_hits or [], "_mock": True, "_source": "MOCK:funasr-offline"}

    # ---------- VLM 图纸/图片感知 (OpenAI 兼容, 模型由 vlm_model 配置) ----------
    def vlm_online(self) -> bool:
        if self._vlm_online is None:
            try:
                with urllib.request.urlopen(f"{self.vlm_url}/v1/models", timeout=4) as r:
                    self._vlm_online = r.status == 200
            except Exception:
                self._vlm_online = False
        return bool(self._vlm_online)

    def perceive_image(self, image_path: str, prompt: Optional[str] = None,
                       mock_perception: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """图纸/图片 → 结构化感知结果 (只出感知, 不决定价格)。离线显式 MOCK。"""
        prompt = prompt or ("这是一张机械零件图纸/图片。请提取: 零件类型、可见尺寸、材料线索、"
                            "表面处理线索、公差/粗糙度标注、孔/螺纹特征。只描述可见事实, 不臆测。")
        if self.vlm_online():
            try:
                import base64
                with open(image_path, "rb") as fh:
                    b64 = base64.b64encode(fh.read()).decode()
                ext = image_path.rsplit(".", 1)[-1].lower()
                mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
                payload = {
                    "model": self.vlm_model,
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]}],
                    "max_tokens": self.max_tokens, "temperature": 0.1,
                }
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(f"{self.vlm_url}/v1/chat/completions", data=data,
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    j = json.loads(r.read().decode("utf-8"))
                return {"ok": True, "perception": self._extract_content(j), "_mock": False,
                        "_source": f"live:vlm:{_netloc(self.vlm_url)}", "_raw_model": j.get("model")}
            except Exception as e:
                if not self.allow_mock:
                    raise
                return {"ok": False, "perception": mock_perception, "_mock": True,
                        "_source": f"MOCK(vlm failed: {e!r})"}
        if not self.allow_mock:
            raise RuntimeError("vlm offline and mock disabled")
        return {"ok": False, "perception": mock_perception, "_mock": True,
                "_source": "MOCK:vlm-offline"}


if __name__ == "__main__":
    a = FunASRAdapter({"funasr": {}})
    print("funasr online:", a.online, "| source:", a.source_label(), "| vlm:", a.vlm_online())
    print(json.dumps(a.transcribe("nonexistent.wav", mock_text="关键尺寸可以放宽到 0.05 毫米"), ensure_ascii=False))
    print(json.dumps(a.rag_search("304 阳极氧化 冲突", mock_hits=[{"case": "S3", "note": "304 不阳极氧化"}]), ensure_ascii=False))
    print(json.dumps(a.perceive_image("nonexistent.png"), ensure_ascii=False))
