"""test_llm_planner.py — LLM Planner (ReAct + 提示工程 + JSON-Schema 绑定) 测试.

用 MockLLM (monkeypatch online()+_post_chat) 做确定性测试, 不依赖 :1234 是否在线;
另含一条 online-conditional 真实测试 (离线自动 skip)。
核心断言: LLM 只"提议", 输出经 JSON 解析 + schema 校验; 离线显式 MOCK 降级; ReAct 受 allow-list 约束。
"""
from __future__ import annotations

import json

import pytest

from services import llm_planner
from services.llm_planner import LLMPlanner, _extract_json, _validate


# ---------------- 纯函数 ----------------
def test_extract_json_variants():
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json('sure! {"material": "6061"} hope that helps') == {"material": "6061"}
    assert _extract_json('[1,2,3]') == [1, 2, 3]
    assert _extract_json("no json here") is None
    assert _extract_json("") is None


def test_validate_required_and_type():
    schema = {"type": "object", "required": ["material"], "properties": {"material": {"type": "string"}}}
    assert _validate({"material": "6061"}, schema) == []
    errs = _validate({"quantity": 5}, schema)
    assert errs and "material" in errs[0]


# ---------------- MockLLM ----------------
class MockPlanner(LLMPlanner):
    """把 _post_chat 替换为按队列返回的 canned 响应; online 恒 True。
    队列元素为 str 时包装成标准 chat 响应; 为 dict 时原样返回 (可带 finish_reason
    等字段模拟截断)。**kwargs 透传给 LLMPlanner (如 max_tokens=200 测预算地板)。"""
    def __init__(self, responses, **kwargs):
        super().__init__(endpoint="http://mock/v1", model="mock-llm", backend="local", **kwargs)
        self._responses = list(responses)
        self._calls = 0
        self.payloads = []

    def online(self):
        return True

    def _post_chat(self, payload):
        # 记录全部 payload 快照供断言 (提示模板/few-shot/response_format/重试预算递增)
        self.payloads.append(dict(payload))
        self.last_payload = payload
        content = self._responses[min(self._calls, len(self._responses) - 1)]
        self._calls += 1
        if isinstance(content, dict):
            return content
        return {"model": "mock-llm", "choices": [{"message": {"content": content}}]}


def test_chat_json_parses_and_validates():
    p = MockPlanner(['{"material":"6061","surface":"阳极氧化","quantity":50,"process":"CNC","missing_information":[]}'])
    r = p.extract_rfq("quote 50 pcs 6061 anodizing")
    assert r["ok"] is True and r["_mock"] is False
    assert r["data"]["material"] == "6061" and r["data"]["quantity"] == 50
    # 提示工程: response_format 约束 + 充足 token 预算(推理模型) + few-shot 注入
    assert p.last_payload["response_format"] == {"type": "text"}
    assert p.last_payload["max_tokens"] >= 2000
    roles = [m["role"] for m in p.last_payload["messages"]]
    assert roles.count("assistant") >= 1        # few-shot 示例已注入


def test_chat_json_schema_error_flagged():
    p = MockPlanner(['{"quantity": 5}'])         # 缺 required material
    r = p.extract_rfq("x")
    assert r["ok"] is False and r["schema_errors"]


def test_chat_json_unparseable_falls_back():
    p = MockPlanner(["sorry I cannot output json"])
    r = p.extract_rfq("x")
    assert r["ok"] is False and r["_source"] == "live:parse_failed"


# ---------------- BUG-2: 推理模型 token 预算 (09-25 巡检) ----------------
# 节点实测: Omni :8002 推理链先耗 reasoning token; max_tokens=200 时
# finish_reason=length 且不吐 tool_calls/JSON (假阴性); ≥600 正常。
def test_chat_json_budget_floor_for_reasoning_model():
    p = MockPlanner(['{"material":"6061","surface":"x","quantity":1,"process":"CNC","missing_information":[]}'],
                    max_tokens=200)
    r = p.extract_rfq("x")
    assert r["ok"] is True
    assert p.last_payload["max_tokens"] >= 600     # 地板: 小预算调用方不可造成截断假阴性


def test_chat_json_retries_with_larger_budget_on_truncation():
    truncated = {"model": "mock-llm",
                 "choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
    p = MockPlanner([truncated, '{"material":"6061","surface":"x","quantity":1,"process":"CNC","missing_information":[]}'])
    r = p.extract_rfq("x")
    assert r["ok"] is True and p._calls == 2
    b1, b2 = p.payloads[0]["max_tokens"], p.payloads[1]["max_tokens"]
    assert b2 > b1 and b2 <= 8192                  # 预算翻倍且有上限


def test_chat_json_truncation_retry_is_bounded():
    truncated = {"model": "mock-llm",
                 "choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
    p = MockPlanner([truncated])                   # 队列耗尽 → 永远截断
    r = p.extract_rfq("x")
    assert r["ok"] is False and r["_source"] == "live:parse_failed"
    assert p._calls == 2                           # 只重试一次, 不无限加码


def test_chat_json_no_retry_when_output_parses():
    fine = {"model": "mock-llm",
            "choices": [{"message": {"content": '{"material":"6061","surface":"x","quantity":1,"process":"CNC","missing_information":[]}'},
                         "finish_reason": "stop"}]}
    p = MockPlanner([fine])
    r = p.extract_rfq("x")
    assert r["ok"] is True and p._calls == 1       # 正常输出不多花一次请求


def test_offline_degrades_to_explicit_mock():
    p = LLMPlanner(endpoint="http://127.0.0.1:59997/v1", backend="local")
    assert p.online() is False
    r = p.extract_rfq("quote 6061")
    assert r["_mock"] is True and r["_source"] == "MOCK:llm-offline"


def test_online_probe_cache_expires_by_ttl(monkeypatch):
    """task #102: online() 探针缓存必须带 TTL。节点实测: livekernel 启动时 LLM
    离线 → _online=False 永不过期; 后端恢复后 dispatcher route() 仍报 llm_offline
    走 auto:rules (反向状态冒充), 必须重启进程才翻转。"""
    calls = {"n": 0}
    state = {"ok": True}

    class _Resp:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def _fake_urlopen(url, timeout=None):
        calls["n"] += 1
        if not state["ok"]:
            raise OSError("llm dead")
        return _Resp()

    monkeypatch.setattr(llm_planner.urllib.request, "urlopen", _fake_urlopen)
    now = {"t": 500.0}
    monkeypatch.setattr(llm_planner.time, "monotonic", lambda: now["t"])

    p = LLMPlanner(endpoint="http://127.0.0.1:9/v1", model="m", backend="local")
    assert p.online() is True
    assert calls["n"] == 1
    assert p.online() is True                    # TTL 内命中缓存
    assert calls["n"] == 1

    now["t"] += 11.0                              # 超过默认 10s TTL
    state["ok"] = False                           # 后端进程此刻已死
    assert p.online() is False                    # 过期 → 重探 → 如实离线
    assert calls["n"] == 2


def test_mock_backend_never_calls_network():
    p = LLMPlanner(backend="mock")
    assert p.online() is False and p.source_label() == "MOCK:llm-planner"


# ---------------- C4: primary 离线 → fallback 端点 (P1 A/B 降级链) ----------------
def _probe_router(monkeypatch, primary_ok: bool, fallback_ok: bool):
    """monkeypatch urlopen: primary(:59997) 与 fallback(:59998) 探活按参数成败。"""
    class _Resp:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def _fake_urlopen(url, timeout=None):
        if ":59997" in str(url):
            if not primary_ok:
                raise OSError("primary dead")
            return _Resp()
        if ":59998" in str(url):
            if not fallback_ok:
                raise OSError("fallback dead")
            return _Resp()
        raise OSError("unexpected url " + str(url))

    monkeypatch.setattr(llm_planner.urllib.request, "urlopen", _fake_urlopen)


def _fb_planner(monkeypatch, primary_ok=True, fallback_ok=True):
    _probe_router(monkeypatch, primary_ok, fallback_ok)
    p = LLMPlanner(endpoint="http://127.0.0.1:59997/v1", model="primary-model",
                   fallback_endpoint="http://127.0.0.1:59998/v1",
                   fallback_model="fallback-model")
    canned = '{"material":"6061","surface":"x","quantity":1,"process":"CNC","missing_information":[]}'
    p.payloads = []

    def _fake_post(payload):
        p.payloads.append(payload)
        return {"model": payload["model"], "choices": [{"message": {"content": canned}}]}

    p._post_chat = _fake_post          # 实例级 seam, 不碰网络
    return p


def test_chat_json_uses_fallback_when_primary_offline(monkeypatch):
    p = _fb_planner(monkeypatch, primary_ok=False, fallback_ok=True)
    assert p.online() is True
    r = p.extract_rfq("quote 6061")
    assert r["_mock"] is False and r["ok"] is True
    assert "fallback" in str(r["_source"])          # 诚实标注走了降级端点
    assert p.payloads[0]["model"] == "fallback-model"   # 请求真发到 fallback 模型


def test_source_label_marks_fallback_route(monkeypatch):
    p = _fb_planner(monkeypatch, primary_ok=False, fallback_ok=True)
    assert "fallback" in p.source_label()


def test_primary_recovery_leaves_fallback(monkeypatch):
    p = _fb_planner(monkeypatch, primary_ok=False, fallback_ok=True)
    assert p.online() is True
    assert "fallback" in p.source_label()
    _probe_router(monkeypatch, primary_ok=True, fallback_ok=True)   # primary 恢复
    p._online = None; p._online_ts = 0.0        # TTL 过期 → 重探
    assert p.online() is True
    assert "fallback" not in p.source_label()   # 自动切回 primary


def test_both_endpoints_down_degrades_to_explicit_mock(monkeypatch):
    p = _fb_planner(monkeypatch, primary_ok=False, fallback_ok=False)
    assert p.online() is False
    r = p.extract_rfq("quote 6061")
    assert r["_mock"] is True and r["_source"] == "MOCK:llm-offline"


# ---------------- ReAct 工具选择 ----------------
def test_react_loop_selects_then_finishes():
    responses = [
        '{"thought":"先抽 RFQ","action":{"tool":"rfq-extraction","args":{}}}',
        '{"thought":"做 DFM","action":{"tool":"dfm-conflict","args":{"material":"6061"}}}',
        '{"thought":"信息足够","action":{"tool":"finish","args":{"status":"PASS"}}}',
    ]
    p = MockPlanner(responses)
    executed = []

    def execute(tool, args):
        executed.append(tool)
        return {"ok": True, "tool": tool}

    allowed = {"rfq-extraction", "dfm-conflict", "cnc-quote", "finish"}
    out = p.react_loop("STRUCTURING", lambda h: "summary", execute, allowed, max_steps=6)
    assert out["ok"] and out["_mock"] is False
    assert executed == ["rfq-extraction", "dfm-conflict"]      # finish 不执行工具
    assert out["finish"]["status"] == "PASS"
    assert len(out["trace"]) == 3


def test_react_loop_blocks_tool_outside_allowlist():
    responses = [
        '{"thought":"越权","action":{"tool":"rm-rf","args":{}}}',
        '{"thought":"结束","action":{"tool":"finish","args":{"status":"HITL"}}}',
    ]
    p = MockPlanner(responses)
    executed = []
    out = p.react_loop("DFM", lambda h: "s", lambda t, a: executed.append(t) or {},
                       {"dfm-conflict", "finish"}, max_steps=5)
    assert "rm-rf" not in executed                              # 越权工具未执行
    assert any("BLOCKED by allow-list" in str(s.get("observation", "")) for s in out["trace"])


def test_react_loop_offline_uses_fallback_sequence():
    p = LLMPlanner(endpoint="http://127.0.0.1:59997/v1")
    executed = []
    out = p.react_loop("NEW", lambda h: "s", lambda t, a: executed.append(t) or {},
                       {"rfq-extraction", "dfm-conflict"},
                       fallback_sequence=["rfq-extraction", "dfm-conflict"])
    assert out["_mock"] is True
    assert executed == ["rfq-extraction", "dfm-conflict"]       # 离线确定性回退


def test_summarize_and_translate_shapes():
    p = MockPlanner(['{"summary":"s","key_points":["a"],"open_questions":[],"risks":[]}'])
    r = p.summarize("need 50 pcs 6061")
    assert r["ok"] and r["data"]["summary"] == "s"
    p2 = MockPlanner(['{"translated":"Please quote 50 pcs","target_lang":"en"}'])
    r2 = p2.translate("请报50件", "en")
    assert r2["ok"] and r2["data"]["target_lang"] == "en"


# ---------------- 在线条件测试 (离线自动 skip) ----------------
def test_live_extract_rfq_if_online():
    p = LLMPlanner()
    if not p.online():
        pytest.skip("LLM :1234 离线, 跳过真实调用")
    r = p.extract_rfq("Please quote 50 pcs 6061 aluminum brackets, anodizing, IT7.")
    src = str(r.get("_source", ""))
    if "llm failed" in src:
        # :1234 活着但模型未驻留 (LM Studio 按需加载失败/进行中) = 环境态, 非代码回归
        pytest.skip(f"模型未就绪, 跳过真实调用: {src[:80]}")
    assert r["_mock"] is False
    assert r["data"].get("material") in ("6061", None)
