"""llm_planner.py — LLM 提议、引擎裁决 (维度 1.1/1.4/2.1/2.2/2.3).

设计铁律 (守住"LLM 不碰价格"):
  LLM 只负责 [抽取 RFQ 字段 / ReAct 选技能 / 起草回复 / 摘要 / 翻译];
  数字、工艺冲突、状态推进仍由确定性引擎 + 护栏 + 状态机裁决。
  LLM 不可用 (离线/未配置/mock) → 显式降级, 调用方回退确定性实现, 绝不冒充。

能力:
  - 结构化提示模板 + few-shot (从 config/prompts/*.yaml 加载)
  - JSON-Schema 绑定输出 (function-calling 风格: 强约束 JSON + schema 校验)
  - ReAct 循环: Thought → Action → Observation → ... (select_tool / react_loop)
  - OpenAI 兼容 /v1/chat/completions (VLM/LLM :8002 或 NIM)
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent
_PROMPTS = _ROOT / "config" / "prompts"

# BUG-2 (09-25 巡检): 推理模型 (nemotron-omni-30b-a3b) 的 reasoning token 先于
# 输出消耗预算。节点实测 max_tokens=200 时 finish_reason=length, 不吐 tool_calls/
# JSON (假阴性); ≥600 正常。统一地板 + 截断重试, 防小预算调用方造成假阴性。
REASONING_MIN_TOKENS = 600
MAX_TOKENS_CAP = 8192


def resolve_max_tokens(budget: int) -> int:
    """token 预算统一入口: 地板 REASONING_MIN_TOKENS (推理链先耗预算, 禁小值截断)。"""
    return max(int(budget), REASONING_MIN_TOKENS)


def _load_yaml(path: Path) -> Dict[str, Any]:
    import yaml  # type: ignore
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_prompt(name: str) -> Dict[str, Any]:
    return _load_yaml(_PROMPTS / f"{name}.yaml")


def _extract_json(text: str) -> Optional[Any]:
    """从 LLM 文本里稳健抽出第一个 JSON 对象/数组 (容忍 ```json 围栏与前后噪声)。"""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    # 退而求其次: 抓第一个平衡的 {...} 或 [...]
    for opener, closer in (("{", "}"), ("[", "]")):
        i = t.find(opener)
        if i < 0:
            continue
        depth = 0
        for j in range(i, len(t)):
            if t[j] == opener:
                depth += 1
            elif t[j] == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(t[i:j + 1])
                    except Exception:
                        break
    return None


def _validate(instance: Any, schema: Dict[str, Any]) -> List[str]:
    """轻量 JSON-Schema 校验 (type/required), 无 jsonschema 依赖时的兜底。"""
    errs: List[str] = []
    if not isinstance(schema, dict):
        return errs
    try:
        import jsonschema  # type: ignore
        v = jsonschema.Draft7Validator(schema)
        return [e.message for e in v.iter_errors(instance)]
    except ModuleNotFoundError:
        pass
    t = schema.get("type")
    if t == "object" or isinstance(t, list) and "object" in t:
        if not isinstance(instance, dict):
            errs.append("expected object")
            return errs
        for req in schema.get("required", []):
            if req not in instance:
                errs.append(f"missing required: {req}")
    return errs


class LLMPlanner:
    def __init__(self, endpoint: str = "http://127.0.0.1:8002/v1", model: str = "nemotron-omni-30b-a3b",
                 backend: str = "local", timeout: int = 60, allow_mock: bool = True,
                 temperature: float = 0.1, max_tokens: int = 2000, probe_ttl_s: float = 10.0,
                 fallback_endpoint: Optional[str] = None, fallback_model: Optional[str] = None):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.backend = backend            # local | nvidia | mock
        self.timeout = timeout
        self.allow_mock = allow_mock
        self.temperature = temperature
        self.max_tokens = max_tokens      # 推理模型需充足预算, 否则 content 为空
        # 探针缓存 (ts, ok): 旧版 _online 一次性写死, 后端恢复/崩溃都不翻转
        # (节点实测: 30B 死后 dispatcher 反向冒充 offline) → TTL 到期重探。
        self._online: Optional[bool] = None
        self._online_ts: float = 0.0
        self._probe_ttl: float = probe_ttl_s
        self._prompt_cache: Dict[str, Dict[str, Any]] = {}
        # C4 A/B 降级链 (P1 巡检): primary (models.yaml llm.endpoint) 离线 → 切
        # fallback 端点 (节点 :8902 qwen3-0.6b); TTL 到期重探, primary 恢复自动切回。
        # 降级中 _source/source_label 带 @fallback 诚实标注, 不冒充 primary。
        self.fallback_endpoint = (fallback_endpoint or "").rstrip("/") or None
        self.fallback_model = fallback_model or None
        self._using_fallback = False

    # ---------- connectivity ----------
    def _probe_base(self, base: str) -> bool:
        try:
            with urllib.request.urlopen(f"{base}/v1/models", timeout=4) as r:
                return r.status == 200
        except Exception:
            return False

    def online(self) -> bool:
        if self.backend == "mock":
            return False
        if self._online is None or time.monotonic() - self._online_ts > self._probe_ttl:
            base = self.endpoint[:-3] if self.endpoint.endswith("/v1") else self.endpoint
            ok = self._probe_base(base)
            if ok:
                self._using_fallback = False
            elif self.fallback_endpoint:
                fb_base = (self.fallback_endpoint[:-3]
                           if self.fallback_endpoint.endswith("/v1") else self.fallback_endpoint)
                self._using_fallback = self._probe_base(fb_base)
                ok = self._using_fallback
            self._online = ok
            self._online_ts = time.monotonic()
        return bool(self._online)

    def _active_endpoint(self) -> str:
        return self.fallback_endpoint if (self._using_fallback and self.fallback_endpoint) else self.endpoint

    def _active_model(self) -> str:
        return self.fallback_model if (self._using_fallback and self.fallback_model) else self.model

    def source_label(self) -> str:
        if self.backend == "mock":
            return "MOCK:llm-planner"
        if self.online():
            suffix = "@fallback" if self._using_fallback else ""
            return f"live:llm:{self._active_model()}{suffix}"
        return "MOCK:llm-offline"

    # ---------- core chat ----------
    def _prompt(self, name: str) -> Dict[str, Any]:
        if name not in self._prompt_cache:
            self._prompt_cache[name] = load_prompt(name)
        return self._prompt_cache[name]

    def _messages(self, name: str, user_text: str) -> List[Dict[str, Any]]:
        p = self._prompt(name)
        msgs: List[Dict[str, Any]] = [{"role": "system", "content": p.get("system", "")}]
        # few-shot 注入 (维度2.1)
        for ex in p.get("few_shot", []) or []:
            inp = ex.get("input")
            inp_s = inp if isinstance(inp, str) else json.dumps(inp, ensure_ascii=False)
            msgs.append({"role": "user", "content": inp_s})
            msgs.append({"role": "assistant",
                         "content": json.dumps(ex.get("output"), ensure_ascii=False)})
        msgs.append({"role": "user", "content": user_text})
        return msgs

    def chat_json(self, name: str, user_text: str, schema: Optional[Dict[str, Any]] = None,
                  mock_return: Optional[Any] = None) -> Dict[str, Any]:
        """按命名提示模板请求 LLM, 强约束 JSON 输出 + schema 校验。离线→显式 MOCK。
        注: user_text 应为已填充模板变量的最终用户消息 (由高层技能负责填充)。"""
        if not self.online():
            if not self.allow_mock:
                raise RuntimeError("LLM offline and mock disabled")
            return {"ok": False, "_mock": True, "_source": "MOCK:llm-offline", "data": mock_return}
        p = self._prompt(name)
        payload = {
            "model": self._active_model(), "messages": self._messages(name, user_text),
            "temperature": self.temperature,
            # 推理模型(如 nemotron-omni-30b-a3b)会先耗 reasoning token, 预算需充足否则 content 为空
            "max_tokens": resolve_max_tokens(self.max_tokens),
            # 部分服务器(LMStudio)只认 text/json_schema, 不认 json_object → 用 text + 提示约束 + 稳健解析
            "response_format": {"type": "text"},
        }
        src_suffix = "@fallback" if self._using_fallback else ""
        try:
            j = self._post_chat(payload)
            content = j["choices"][0]["message"]["content"]
            parsed = _extract_json(content)
            if parsed is None:
                # BUG-2: content 空/不可解析多为 reasoning 阶段耗尽预算 (finish_reason=length)。
                # 预算翻倍重试一次 (有上限); 仍失败 → live:parse_failed 显式降级, 不无限加码。
                retry_budget = min(payload["max_tokens"] * 2, MAX_TOKENS_CAP)
                if retry_budget > payload["max_tokens"]:
                    payload["max_tokens"] = retry_budget
                    j = self._post_chat(payload)
                    content = j["choices"][0]["message"]["content"]
                    parsed = _extract_json(content)
                if parsed is None:
                    return {"ok": False, "_mock": False, "_source": "live:parse_failed",
                            "raw": content[:300], "data": mock_return}
            errs = _validate(parsed, schema or p.get("output_schema") or {})
            return {"ok": not errs, "_mock": False,
                    "_source": f"live:{self._active_model()}{src_suffix}",
                    "data": parsed, "schema_errors": errs, "model": j.get("model")}
        except Exception as e:
            if not self.allow_mock:
                raise
            return {"ok": False, "_mock": True, "_source": f"MOCK(llm failed: {e!r})", "data": mock_return}

    def _post_chat(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """HTTP seam: 向 OpenAI 兼容 /chat/completions 发请求 (测试可 monkeypatch)。
        健壮性: 若服务器拒绝 response_format (HTTP 400, 如部分 LMStudio/NIM), 去掉它重试一次。"""
        def _do(pl: Dict[str, Any]) -> Dict[str, Any]:
            data = json.dumps(pl).encode("utf-8")
            req = urllib.request.Request(f"{self._active_endpoint()}/chat/completions", data=data,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        try:
            return _do(payload)
        except urllib.error.HTTPError as e:
            if e.code == 400 and "response_format" in payload:
                pl2 = {k: v for k, v in payload.items() if k != "response_format"}
                return _do(pl2)
            raise

    # ---------- 高层技能 ----------
    def extract_rfq(self, email_text: str) -> Dict[str, Any]:
        p = self._prompt("rfq_extraction")
        user = p.get("user_template", "{email_text}").replace("{email_text}", email_text or "")
        return self.chat_json("rfq_extraction", user, schema=p.get("output_schema"))

    def chat_raw(self, system_prompt: str, user_text: str,
                 temperature: Optional[float] = None,
                 max_tokens: Optional[int] = None) -> Dict[str, Any]:
        """任意 system/user 的单轮对话 (reid 协议执行等); 离线→显式 MOCK, 不伪造文本。

        与 chat_json 共享降级语义 + 预算翻倍重试 (BUG-2: 推理模型 reasoning 阶段耗尽
        content 截断), 但不做 JSON 提取/schema 校验 — 返回原文 content 给高层技能解析。
        """
        if not self.online():
            if not self.allow_mock:
                raise RuntimeError("LLM offline and mock disabled")
            return {"ok": False, "_mock": True, "_source": "MOCK:llm-offline", "data": None}
        budget = resolve_max_tokens(max_tokens if max_tokens is not None else self.max_tokens)
        payload = {
            "model": self._active_model(),
            "messages": [{"role": "system", "content": system_prompt},
                         {"role": "user", "content": user_text}],
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": budget,
            "response_format": {"type": "text"},
        }
        src_suffix = "@fallback" if self._using_fallback else ""
        try:
            j = self._post_chat(payload)
            content = (j["choices"][0]["message"].get("content") or "")
            if not content:
                # 同 chat_json: 预算翻倍重试一次 (推理模型 reasoning 阶段耗尽)
                retry_budget = min(budget * 2, MAX_TOKENS_CAP)
                if retry_budget > budget:
                    payload["max_tokens"] = retry_budget
                    j = self._post_chat(payload)
                    content = (j["choices"][0]["message"].get("content") or "")
            return {"ok": bool(content), "_mock": False,
                    "_source": f"live:{self._active_model()}{src_suffix}",
                    "data": content, "model": j.get("model")}
        except Exception as e:
            if not self.allow_mock:
                raise
            return {"ok": False, "_mock": True, "_source": f"MOCK(llm failed: {e!r})", "data": None}

    def summarize(self, text: str) -> Dict[str, Any]:
        p = self._prompt("summarize")
        user = p.get("user_template", "{text}").replace("{text}", text or "")
        return self.chat_json("summarize", user)

    def translate(self, text: str, target_lang: str = "en") -> Dict[str, Any]:
        p = self._prompt("translate")
        user = p.get("user_template", "").replace("{text}", text or "").replace("{target_lang}", target_lang)
        return self.chat_json("translate", user)

    def draft_reply(self, context_json: Dict[str, Any]) -> Dict[str, Any]:
        p = self._prompt("reply_draft")
        user = p.get("user_template", "{context_json}").replace(
            "{context_json}", json.dumps(context_json, ensure_ascii=False))
        return self.chat_json("reply_draft", user)

    # ---------- ReAct: LLM 驱动工具选择 (维度2.2) ----------
    def select_tool(self, state: str, context_summary: str, history: List[str]) -> Dict[str, Any]:
        p = self._prompt("tool_selection")
        user = (p.get("user_template", "")
                .replace("{state}", state)
                .replace("{context_summary}", context_summary)
                .replace("{history}", json.dumps(history, ensure_ascii=False)))
        return self.chat_json("tool_selection", user)

    def react_loop(self, state: str, context_summary_fn: Callable[[List[str]], str],
                   execute: Callable[[str, Dict[str, Any]], Any],
                   allowed_tools: set, max_steps: int = 8,
                   fallback_sequence: Optional[List[str]] = None) -> Dict[str, Any]:
        """ReAct 循环: 每步 LLM 提议 Action → 校验 allow-list → execute → Observation 回灌。
        LLM 离线或越界 → 回退确定性 fallback_sequence (不阻断)。"""
        trace: List[Dict[str, Any]] = []
        history: List[str] = []
        if not self.online():
            seq = fallback_sequence or []
            for tool in seq:
                obs = execute(tool, {})
                trace.append({"thought": "MOCK/offline → 确定性回退", "action": tool,
                              "observation": _short(obs), "_mock": True})
                history.append(tool)
            return {"ok": True, "_mock": True, "_source": "MOCK:llm-offline",
                    "trace": trace, "history": history}
        for step in range(max_steps):
            r = self.select_tool(state, context_summary_fn(history), history)
            if not r.get("ok"):
                trace.append({"thought": "LLM 输出不合规 → 回退", "raw": r, "_mock": r.get("_mock")})
                break
            d = r["data"] or {}
            thought = d.get("thought", "")
            action = d.get("action", {}) or {}
            tool = action.get("tool")
            args = action.get("args", {}) or {}
            trace.append({"step": step, "thought": thought, "action": tool, "args": args})
            if tool == "finish":
                trace[-1]["observation"] = "finish"
                return {"ok": True, "_mock": False, "_source": f"live:{self.model}",
                        "trace": trace, "history": history, "finish": args}
            if tool not in allowed_tools:
                trace[-1]["observation"] = f"BLOCKED by allow-list: {tool}"
                history.append(f"{tool}(blocked)")
                continue
            obs = execute(tool, args)
            trace[-1]["observation"] = _short(obs)
            history.append(tool)
        return {"ok": True, "_mock": False, "_source": f"live:{self.model}",
                "trace": trace, "history": history, "finish": {"status": "HITL"}}


def _short(x: Any, n: int = 160) -> str:
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, default=str)
    return s if len(s) <= n else s[:n] + "…"


if __name__ == "__main__":
    p = LLMPlanner()
    print("online:", p.online(), "| source:", p.source_label())
    print(json.dumps(p.extract_rfq("Please quote 50 pcs 6061 aluminum brackets, anodizing, IT7."),
                     ensure_ascii=False)[:400])
