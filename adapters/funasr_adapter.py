"""FunASRAdapter — 多模态 Intake + RAG 记忆层 (双模: funasr-gui / 节点 Omni).

开发机 funasr-gui (server.py, 装机机本地服务):
  GET  /health
  POST /transcribe            语音转写 (funasr-gui 本地 ASR 进程)
  GET  /rag/search?q=&limit=  语义检索 (funasr-gui 本地 embedding + SQLite FTS5 + RRF)
  VLM  funasr-gui 本地 VLM (OpenAI 兼容, 图纸/图片理解)

节点 Omni 模式 (vLLM OpenAI 兼容, nemotron-omni-30b-a3b @ :8002, 实测口径):
  根 /health -> 200; /v1/health -> 404        → health 探测剥 /v1 后探根
  POST /v1/chat/completions                   → input_audio content part 收音频
                                                (实证: 带音频 52 vs 不带 30 prompt_tokens)
  由 funasr.asr_mode=omni + asr_model/vlm_model 配置开关, URL 归一化剥尾部 /v1。

ASR cli 模式 (asr_mode=cli, 节点中文语音唯一活链):
  scripts/asr_cli.py 子进程 (faster-whisper, 独立 vidproc 解释器) — omni 的
  input_audio 只吐英文音频场景描述, occ 解释器内无任何 ASR 引擎 (2026-09-25 实测)。

降级原则 (对齐冻结 PRD):
  服务未启动/调用失败 → 返回显式 MOCK 结果, _mock=True, 绝不冒充生产转写/检索。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.llm_planner import resolve_max_tokens

_ASR_PROMPT = ("请将以下音频中的语音内容完整转写为文本。"
               "只输出转写文本本身, 不要添加解释、翻译或格式。")

# upload/intake 路径的图纸感知默认提示词 (extract_rfq 要从中取 material/quantity/
# surface/tolerance → 数量/批量 必问, 否则图纸-only RFQ 恒缺 quantity → HITL)。
# 与 services/media_api._CHAT_IMG_PROMPT 是两份 (用途不同: 媒体入库含聊天截图转写),
# 各自独立演进 — 改任何一份都要同步回归 tests/test_b1_drawing_rfq.py。
VLM_IMG_PROMPT_DEFAULT = ("这是一张机械零件图纸/图片。请提取: 零件类型、可见尺寸、数量/批量、"
                          "材料线索、表面处理线索、公差/粗糙度标注、孔/螺纹特征。只描述可见事实, 不臆测。")


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
        self.asr_mode: str = str(f.get("asr_mode", "funasr"))     # funasr | omni | cli
        self.asr_model: str = str(f.get("asr_model", "nemotron-omni-30b-a3b"))
        # CLI 模式 (本地中文 ASR, scripts/asr_cli.py): occ 解释器内无 ASR 引擎
        # (faster_whisper/funasr/whisper 全 ModuleNotFound), 且 omni input_audio
        # 只吐英文音频场景描述 → 用独立解释器跑子进程。脚本路径相对仓库根。
        self.asr_cli: str = str(f.get("asr_cli", "scripts/asr_cli.py"))
        self.asr_cli_python: str = str(f.get("asr_cli_python", "") or os.environ.get(
            "LIVEKERNEL_ASR_PYTHON", "") or "/home/Developer/miniconda3/envs/vidproc/bin/python")
        # CLI 失败是否回落 omni: 默认 False。omni input_audio 只吐英文音频场景
        # 描述, 回落等于把英文 caption 当中文转写入库污染 RAG; 宁可显式 MOCK
        # 降级 (本仓铁律: 绝不冒充生产转写), 需要时由配置显式打开。
        self.asr_cli_fallback: bool = bool(f.get("asr_cli_fallback", False))
        # CLI 超时独立于 omni timeout_s: 实测 38.6s 音频含模型加载耗时 139s
        # (cold start), 复用 timeout_s(180) 会误杀长音频。
        self.asr_cli_timeout: int = int(f.get("asr_cli_timeout_s", 900))
        # ASR 关思考开关 (默认 True)。Omni nemotron_v3 是 reasoning 模型, 开思考会把
        # token 预算烧在 reasoning 上。节点实测同一段 15.07s 真实语音:
        #   max_tokens=4096 + 开思考 → 72.9s, 3406 tok, content 35 字, finish=stop
        #   max_tokens=8192 + 开思考 → 159.9s, 8192 tok, content=None, finish=length
        #   max_tokens=2048 + 关思考 →  1.3s,   36 tok, content 34 字, finish=stop
        # 即调大 max_tokens 反而更糟 (reasoning 无上限); 正解是显式关思考 (56x 提速)。
        # VLM 感知路径需要思考, 不受此开关影响 (只作用于 _transcribe_omni)。
        self.disable_thinking: bool = bool(f.get("asr_disable_thinking", True))
        self.vlm_url: str = _strip_v1(str(f.get("vlm_url", "http://127.0.0.1:8002")))
        self.vlm_model: str = str(f.get("vlm_model", "nemotron-omni-30b-a3b"))
        self.timeout: int = int(f.get("timeout_s", 30))
        # 推理模型 (Omni nemotron_v3) 会把预算烧在 reasoning 上: 2000 实测偶发
        # finish=length 空 content, 4096 实测两次 finish=stop — 预算可配, 但统一
        # 地板 600 (resolve_max_tokens): 小预算配置会造成转写/感知假阴性 (09-25 巡检)。
        self.max_tokens: int = resolve_max_tokens(int(f.get("max_tokens", 2000)))
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
        if self.asr_mode == "cli":
            return self._transcribe_cli(audio_path, mock_text)
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

    def _transcribe_cli(self, audio_path: str, mock_text: Optional[str] = None) -> Dict[str, Any]:
        """CLI 模式: 外部解释器跑 scripts/asr_cli.py (faster-whisper 中文 ASR).

        为什么要子进程 (节点实测 2026-09-25):
          - occ 解释器 (livekernel 运行时) 内 faster_whisper/funasr/whisper 全缺失,
            pip 装不进去 → 只能用独立解释器 (/home/Developer/miniconda3/envs/vidproc)
          - omni 的 input_audio 只吐英文音频场景描述 → 不能当中文转写源

        契约: stdout = 转写文本 (脚本保证只有文本), 非 0 exit = 明确失败。
        失败时按 asr_cli_fallback 决定回落 omni 还是显式 MOCK (默认不回落)。
        """
        script = self._resolve_asr_cli()
        if script is None:
            src = f"MOCK:asr-cli-missing({self.asr_cli})"
            if not self.allow_mock:
                raise RuntimeError(f"asr cli script not found: {self.asr_cli}")
            return {"text": mock_text or "", "_mock": True, "_source": src}
        py = self.asr_cli_python or sys.executable
        try:
            r = subprocess.run([py, str(script), audio_path],
                               capture_output=True, text=True,
                               timeout=self.asr_cli_timeout)
            if r.returncode != 0:
                raise RuntimeError(f"exit={r.returncode} stderr={(r.stderr or '').strip()[:200]}")
            text = (r.stdout or "").strip()
            if not text:
                raise RuntimeError("empty stdout")
            return {"text": text, "_mock": False,
                    "_source": f"live:asr-cli:{script.name}", "_raw": {"stderr": r.stderr[:400]}}
        except Exception as e:
            err = f"MOCK(asr-cli failed: {e!r})"
            if self.asr_cli_fallback:
                res = self._transcribe_omni(audio_path, mock_text)
                # 回落来源必须保留原始失败原因, 让上游知道这不是首选路径
                res["_source"] = f"{err}→omni-fallback:{res.get('_source', '?')}"
                return res
            if not self.allow_mock:
                raise
            return {"text": mock_text or "", "_mock": True, "_source": err}

    def _resolve_asr_cli(self) -> Optional[Path]:
        """解析 asr_cli 路径: 绝对路径直接用; 相对路径按仓库根 (adapters/ 的父级) 找。"""
        p = Path(self.asr_cli)
        if p.is_absolute():
            return p if p.exists() else None
        root = Path(__file__).resolve().parent.parent
        cand = root / self.asr_cli
        return cand if cand.exists() else None

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
                # 见 __init__ 实测口径: ASR 不需要 reasoning, 显式关思考否则
                # content 被 reasoning 吃空 → _extract_content 抛错 → 静默拿空转写。
                if self.disable_thinking:
                    payload["chat_template_kwargs"] = {"enable_thinking": False}
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
        prompt = prompt or VLM_IMG_PROMPT_DEFAULT
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
