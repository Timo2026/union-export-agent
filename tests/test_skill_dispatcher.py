"""test_skill_dispatcher.py — 路由 / 编排 / OpenShell 拦截 / 设置 API."""
from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

from services import skill_config as sc
from services.skill_dispatcher import SkillDispatcher, rule_route, llm_route
from services.openshell import OpenShell
from skills import _runtime as rt


@pytest.fixture(scope="module")
def client():
    from services.api_server import app
    with TestClient(app) as c:
        yield c


def test_rule_route_quote_intent():
    r = rule_route("客户要 CNC 报价，50 件 6061", [])
    assert "calc_quote" in r["skills"]
    assert "parse_rfq" in r["skills"]
    assert r["source"] == "rules"


def test_rule_route_feedback_intent():
    r = rule_route("我要提交一个 bug 反馈", [])
    assert r["skills"] == ["submit_feedback"]


def test_rule_route_golden_chain():
    r = rule_route("跑一遍黄金链端到端", [])
    assert r["skills"] == ["golden_chain"]


def test_rule_route_adds_thumbnail_for_step():
    r = rule_route("帮我处理这个零件", ["data/samples/a.step"])
    assert "render_thumbnail" in r["skills"]


def test_llm_route_uses_reasoning_aware_token_budget():
    """llm_route 必须用 planner 的充足 max_tokens, 不能硬编码小预算。

    回归: 曾硬编码 max_tokens=400。推理模型 (如 nemotron-30b-a3b + nano_v3 reasoning
    parser) 会先耗 reasoning token, 预算不足则 message.content 为空 →
    _extract_json(None) → parse_failed → 退化规则路由 (丢失 LLM 驱动路由维度)。
    与 chat_json 对齐 (见 test_llm_planner: max_tokens >= 2000)。
    """
    from services.llm_planner import LLMPlanner

    class _FakePlanner(LLMPlanner):
        def __init__(self):
            super().__init__(endpoint="http://mock/v1",
                             model="nemotron-30b-a3b", backend="local")
            self.last_payload = None

        def online(self):
            return True

        def _post_chat(self, payload):
            self.last_payload = payload
            # 推理模型: reasoning 已在服务端分离, content 仅含最终 JSON
            content = '{"skills": ["golden_chain"], "thought": "full RFQ quote flow"}'
            return {"choices": [{"message": {"content": content}}]}

    p = _FakePlanner()
    r = llm_route("Quote 100 anodized aluminum 6061 CNC brackets IT7", [], p)
    # 主断言 (钉住生产改动): 预算充足, 不再硬编码 400
    assert p.last_payload["max_tokens"] >= 2000
    # 行为: LLM 路由成功, 不退化规则
    assert r["ok"] is True and r["source"] == "llm"
    assert r["skills"] == ["golden_chain"]


def test_llm_route_budget_floor_for_small_planner_budget():
    """BUG-2: 小 max_tokens 的 planner (如 max_tokens=200) 也必须地板 600。
    节点实测 (09-25 巡检): Reasoning 模型 reasoning token 先耗预算, max_tokens=200 时
    finish_reason=length 不吐 tool_calls/JSON → parse_failed → 退化规则路由。
    """
    from services.llm_planner import LLMPlanner

    class _FakePlanner(LLMPlanner):
        def __init__(self):
            super().__init__(endpoint="http://mock/v1", model="nemotron-30b-a3b",
                             backend="local", max_tokens=200)
            self.last_payload = None

        def online(self):
            return True

        def _post_chat(self, payload):
            self.last_payload = payload
            content = '{"skills": ["golden_chain"], "thought": "full RFQ quote flow"}'
            return {"choices": [{"message": {"content": content}}]}

    p = _FakePlanner()
    r = llm_route("Quote 100 anodized aluminum 6061 CNC brackets IT7", [], p)
    assert p.last_payload["max_tokens"] >= 600
    assert r["ok"] is True and r["skills"] == ["golden_chain"]


def test_llm_route_fallback_payload_uses_fallback_model_name(monkeypatch):
    """C4: planner 已切 fallback 时, payload/返回的 model 必须是 fallback 模型名。

    节点实测坑: llm_route 原来写死 planner.model — primary 离线时 _post_chat 把
    请求发到 fallback 端点 :8902, 模型名却还是 primary 的 omni-30b-a3b, vLLM
    :8902 只服务 qwen3-0.6b → 404, 降级链在 dispatcher 层断裂。
    """
    from services import llm_planner as _lp
    from services.llm_planner import LLMPlanner

    class _Resp:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def _fake_urlopen(url, timeout=None):
        if ":59997" in str(url):
            raise OSError("primary dead")
        if ":59998" in str(url):
            return _Resp()
        raise OSError("unexpected url " + str(url))

    monkeypatch.setattr(_lp.urllib.request, "urlopen", _fake_urlopen)
    p = LLMPlanner(endpoint="http://127.0.0.1:59997/v1", model="primary-model",
                   fallback_endpoint="http://127.0.0.1:59998/v1",
                   fallback_model="fallback-model")
    assert p.online() is True                       # primary 死 → fallback 在线
    canned = '{"skills": ["golden_chain"], "thought": "全文 RFQ 流程"}'
    p.payloads = []

    def _fake_post(payload):
        p.payloads.append(payload)
        return {"model": payload["model"], "choices": [{"message": {"content": canned}}]}

    p._post_chat = _fake_post                       # 实例级 seam, 不碰网络
    r = llm_route("跑黄金链端到端", [], p)
    assert r["ok"] is True and r["skills"] == ["golden_chain"]
    assert p.payloads[0]["model"] == "fallback-model"   # 请求必须用 fallback 模型名
    assert r["model"] == "fallback-model"               # 诚实标注实际模型


def test_runtime_discovers_skill_tools():
    reg = rt.discover(force=True)
    for sid in ("parse_rfq", "check_dfm", "calc_quote", "submit_feedback",
                "render_thumbnail", "golden_chain"):
        assert sid in reg, f"missing skill tool: {sid}"


def test_dispatch_feedback_skill_offline_friendly():
    cfg = sc.default_config()
    cfg["dispatcher"]["strategy"] = "rules_only"
    disp = SkillDispatcher(cfg=cfg)
    resp = disp.dispatch(intent="提交反馈：界面按钮错位", args={
        "type": "bug", "title": "按钮错位", "body": "保存按钮在 1080p 下被裁切",
    })
    assert resp["dispatch_id"]
    assert "submit_feedback" in resp["executed_skills"] or \
           any(t.get("skill") == "submit_feedback" for t in resp["trace"])
    # 不应因 LLM 离线而整体失败
    assert resp["route"]["source"] in ("rules", "explicit") or resp["route"].get("strategy", "").startswith("auto")


# ---- P0 driver 标记: dispatch 默认 console + 显式透传 + audit 落盘 ----
def test_dispatch_driver_marker_default_console():
    cfg = sc.default_config()
    cfg["dispatcher"]["strategy"] = "rules_only"
    disp = SkillDispatcher(cfg=cfg)
    resp = disp.dispatch(intent="提交反馈：driver 默认值测试", args={
        "type": "bug", "title": "t", "body": "xxxxx",
    })
    assert resp["driver"] == "console"  # 控制台发起默认 console


def test_dispatch_driver_marker_explicit_and_audit():
    import json
    from services.skill_dispatcher import _AUDIT_PATH
    cfg = sc.default_config()
    cfg["dispatcher"]["strategy"] = "rules_only"
    disp = SkillDispatcher(cfg=cfg)
    resp = disp.dispatch(intent="提交反馈：driver 显式测试", driver="email", args={
        "type": "bug", "title": "t", "body": "xxxxx",
    })
    assert resp["driver"] == "email"
    if _AUDIT_PATH.exists():
        lines = [l for l in _AUDIT_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
        last = json.loads(lines[-1])
        assert last.get("driver") == "email"
        assert last.get("dispatch_id") == resp["dispatch_id"]


def test_dispatch_blocks_disabled_skill():
    cfg = sc.default_config()
    cfg["dispatcher"]["strategy"] = "rules_only"
    cfg["skills"] = {"submit_feedback": {"enabled": False, "label": "反馈"}}
    disp = SkillDispatcher(cfg=cfg)
    resp = disp.dispatch(intent="提交反馈", args={"type": "bug", "title": "t", "body": "xxxxx"})
    assert "submit_feedback" not in resp["executed_skills"]
    assert any(s.get("skill") == "submit_feedback" for s in resp["skipped"])


# ---- MEDIA 富输出协议 (workshop 复刻): skill 输出 media → resp["media"] ----
def test_dispatch_aggregates_media(monkeypatch):
    """skill output 带 media 列表 → dispatch resp 聚合出 media + MEDIA: 行."""
    from skills import _runtime as rt
    monkeypatch.setattr(rt, "execute", lambda sid, args, ctx: {
        "ok": True, "skill": sid,
        "media": [{"kind": "svg", "path": "data/cache/thumb/abc.svg"}],
    })
    cfg = sc.default_config()
    cfg["dispatcher"]["strategy"] = "rules_only"
    disp = SkillDispatcher(cfg=cfg)
    resp = disp.dispatch(intent="生成缩略图", files=["data/samples/a.step"],
                         args={"path": "data/samples/a.step"})
    assert resp["media"] == [{"kind": "svg", "path": "data/cache/thumb/abc.svg"}]
    # MEDIA: 行供 agent 平面原样粘进回复 (workshop 协议)
    assert "MEDIA:data/cache/thumb/abc.svg" in resp["media_lines"]
    assert "MEDIA:" in resp["media_lines"][0]


def test_dispatch_media_empty_when_no_skill_outputs_media():
    cfg = sc.default_config()
    cfg["dispatcher"]["strategy"] = "rules_only"
    disp = SkillDispatcher(cfg=cfg)
    resp = disp.dispatch(intent="提交反馈：无 media 场景", args={
        "type": "bug", "title": "media 测试", "body": "xxxxx",
    })
    assert resp["media"] == []
    assert resp["media_lines"] == []


def test_dispatch_blocks_path_outside_sandbox():
    cfg = sc.default_config()
    cfg["dispatcher"]["strategy"] = "rules_only"
    disp = SkillDispatcher(cfg=cfg)
    resp = disp.dispatch(
        intent="生成缩略图",
        files=["C:/Windows/evil.step"],
        args={"path": "C:/Windows/evil.step"},
    )
    # render_thumbnail 应被 local-only 拦下
    assert any(
        (t.get("skill") == "render_thumbnail" and (t.get("skipped") or t.get("violations")))
        or (s.get("skill") == "render_thumbnail")
        for t in resp["trace"] for s in [t]
    ) or any(s.get("skill") == "render_thumbnail" for s in resp["skipped"]) or \
        any("local-only" in str(v) for v in resp["openshell_violations"])
    assert "render_thumbnail" not in resp["executed_skills"] or resp["openshell_violations"]


def test_dispatch_golden_chain_accepts_string_customer():
    """推理执行台把 customer 当自由文本传 ("Northwind"), 不得崩黄金链。

    回归: 2026-09-25 公网 :8051 实测 POST /v1/agent/task → golden_chain
    AttributeError("'str' object has no attribute 'get'") (CATController.run
    第 165 行 customer.get("name"); "Northwind" 是真值字符串逃过 `or {}`),
    0/1 skills, 回稿为空 — 页面呈现"假功能"。
    """
    cfg = sc.default_config()
    cfg["dispatcher"]["strategy"] = "rules_only"
    disp = SkillDispatcher(cfg=cfg)
    resp = disp.dispatch(
        intent="6061 铝件 阳极氧化 100 件 报价",
        skills=["golden_chain"],
        args={"email_text": "请报价: 铝合金6061 工件 100 件, 尺寸50x30x10mm, 阳极氧化",
              "customer": "Northwind", "use_llm": False},
        driver="console",
    )
    entry = next((t for t in resp["trace"] if t.get("skill") == "golden_chain"), None)
    assert entry is not None, "golden_chain 未进入 trace"
    out = entry.get("output") or {}
    assert "AttributeError" not in str(out.get("error") or ""), (
        f"字符串 customer 崩黄金链: {out.get('error')!r}")
    assert "golden_chain" in resp["executed_skills"], (
        f"golden_chain 未执行: trace={entry}")


def test_dispatch_openshell_violations_are_per_dispatch():
    """同一 dispatcher 连跑两轮: openshell_violations 只含本轮, 不得累积历史。

    契约演进 (2026-09-26 N1 巡检): 审计演示 (iron_rule_override_blocked,
    模拟 LLM 改写被锁拦) 不再进 openshell_violations — 健康轮次 0 条;
    演示明细只归 iron_rule_override_blocked (见
    test_dispatch_override_demo_not_in_openshell_violations)。
    """
    cfg = sc.default_config()
    cfg["dispatcher"]["strategy"] = "rules_only"
    disp = SkillDispatcher(cfg=cfg)
    args = {"email_text": "请报价: 铝合金6061 工件 100 件, 尺寸50x30x10mm, 阳极氧化",
            "customer": {"name": "Northwind"}, "use_llm": False}
    r1 = disp.dispatch(intent="黄金链 端到端 报价", skills=["golden_chain"],
                       args=dict(args), driver="console")
    r2 = disp.dispatch(intent="黄金链 端到端 报价", skills=["golden_chain"],
                       args=dict(args), driver="console")
    assert "golden_chain" in r1["executed_skills"], "第一轮 golden_chain 未执行"
    assert "golden_chain" in r2["executed_skills"], "第二轮 golden_chain 未执行"
    assert r1["openshell_violations"] == [], f"健康轮次应 0 条违规: {r1['openshell_violations']}"
    assert r2["openshell_violations"] == [], (
        f"第二轮应仍是 0 条 (每轮语义), 实得 {r2['openshell_violations']} — 跨轮累积")
    assert (r1.get("iron_rule_override_blocked") or {}).get("allowed") is False
    assert (r2.get("iron_rule_override_blocked") or {}).get("allowed") is False


def test_iron_rule_override_blocked_in_dispatch():
    """确定性 skill 输出锁定后, 篡改应被 OpenShell 拒绝."""
    cfg = sc.default_config()
    cfg["dispatcher"]["strategy"] = "rules_only"
    disp = SkillDispatcher(cfg=cfg)
    # 直接注入确定性输出锁
    shell = disp.shell
    original = {"unit_price": 222.8, "final_price": 9413.3, "ok": True, "skill": "calc_quote"}
    shell.postcheck("calc_quote", original, iron_rule="deterministic")
    tampered = dict(original)
    tampered["final_price"] = 1.0
    attempt = shell.attempt_override("calc_quote", tampered)
    assert attempt["allowed"] is False


def test_skills_config_api_get(client):
    d = client.get("/v1/skills/config").json()
    assert "summary" in d and "config" in d
    assert d.get("iron_rule_1_locked") is True
    ids = {s["id"] for s in d["summary"]["skills"]}
    assert "calc_quote" in ids and "parse_rfq" in ids
    pol = {p["id"]: p for p in d["summary"]["openshell"]}
    assert pol["iron-rule-1"]["locked"] is True
    assert pol["iron-rule-1"]["enabled"] is True


def test_skills_config_api_reject_disabling_iron_rule(client):
    payload = {
        "version": 3,
        "dispatcher": {"strategy": "rules_only", "llm_role": "llm",
                       "fallback_rules": True, "max_skills_per_task": 8, "audit_max": 50},
        "skills": {},
        "openshell": {"iron-rule-1": {"enabled": False, "locked": True}},
        "model_router": {"source": "rules_only"},
    }
    r = client.post("/v1/skills/config", json=payload)
    assert r.status_code == 400
    assert "iron-rule-1" in r.text


def test_skills_config_api_save_roundtrip(client, tmp_path, monkeypatch):
    # 重定向 _SKILLS_YAML 到临时副本: save() 会写 updated_at 时间戳,
    # 直写真实 config/skills.yaml 会弄脏仓库/节点工作树 (回归后 git status 不干净)
    from services import skill_config as sc
    tmp = tmp_path / "skills.yaml"
    tmp.write_text(sc._SKILLS_YAML.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(sc, "_SKILLS_YAML", tmp)
    # 先读再改 strategy 保存
    cur = client.get("/v1/skills/config").json()["config"]
    cfg = copy.deepcopy(cur)
    cfg.setdefault("dispatcher", {})["strategy"] = "rules_only"
    cfg.setdefault("openshell", {})["iron-rule-1"] = {"enabled": True, "locked": True}
    r = client.post("/v1/skills/config", json=cfg)
    assert r.status_code == 200
    body = r.json()
    assert body["saved"] is True
    assert body["config"]["dispatcher"]["strategy"] == "rules_only"
    # 恢复 auto
    cfg["dispatcher"]["strategy"] = "auto"
    client.post("/v1/skills/config", json=cfg)


def test_agent_task_api_feedback(client):
    r = client.post("/v1/agent/task", json={
        "intent": "提交反馈：测试 NemoClaw 调度",
        "args": {"type": "feature", "title": "skill panel", "body": "希望 Skill 面板可搜索过滤"},
    })
    assert r.status_code == 200
    d = r.json()
    assert d["dispatch_id"]
    assert "trace" in d
    assert "openshell_violations" in d


# ---- P0 driver 标记: /v1/agent/task 默认 agent + 显式透传 + 非法值 400 ----
def test_agent_task_api_driver_default_agent(client):
    r = client.post("/v1/agent/task", json={
        "intent": "提交反馈：driver 默认值",
        "args": {"type": "bug", "title": "t", "body": "xxxxx"},
    })
    assert r.status_code == 200
    assert r.json()["driver"] == "agent"


def test_agent_task_api_driver_explicit_console(client):
    r = client.post("/v1/agent/task", json={
        "intent": "提交反馈：driver 显式 console",
        "driver": "console",
        "args": {"type": "bug", "title": "t", "body": "xxxxx"},
    })
    assert r.status_code == 200
    assert r.json()["driver"] == "console"


def test_agent_task_api_invalid_driver_rejected(client):
    r = client.post("/v1/agent/task", json={
        "intent": "提交反馈：driver 非法值",
        "driver": "carrier-pigeon",
        "args": {"type": "bug", "title": "t", "body": "xxxxx"},
    })
    assert r.status_code == 400


def test_agent_task_api_requires_intent(client):
    r = client.post("/v1/agent/task", json={})
    assert r.status_code == 400


def test_agent_route_api(client):
    r = client.post("/v1/agent/route", json={"intent": "我要报价 50 件 6061"})
    assert r.status_code == 200
    d = r.json()
    assert "skills" in d
    assert "calc_quote" in d["skills"] or "golden_chain" in d["skills"]


def test_agent_openshell_api(client):
    r = client.get("/v1/agent/openshell")
    assert r.status_code == 200
    d = r.json()
    assert "openshell" in d and "policies" in d["openshell"]
    iron = next(p for p in d["openshell"]["policies"] if p["id"] == "iron-rule-1")
    assert iron["locked"] is True


# ---- N1 (2026-09-26 推理执行页巡检回归): use_llm=false 必须走规则路由 ----

def test_route_use_llm_false_forces_rule_routing(monkeypatch):
    """UI 推理执行台每个任务都发 use_llm=false 且标注"规则路由兜底"; 后端必须真的走规则。

    回归: 2026-09-25 公网 :8051 实测 — POST /v1/agent/task {use_llm:false} 仍
    strategy=auto:llm (Omni 路由往返, latency 8.2s)。route() 签名本就不收
    use_llm, dispatcher.strategy=auto 时调用方意图被静默忽略 — 前端开关失效。
    """
    cfg = sc.default_config()
    cfg["dispatcher"]["strategy"] = "auto"          # 默认 auto: 有 LLM 时走 llm
    disp = SkillDispatcher(cfg=cfg)

    def _no_planner():
        raise AssertionError("use_llm=false 不得构造/调用 LLM planner")

    monkeypatch.setattr(disp, "_ensure_planner", _no_planner)
    r = disp.route("6061 铝件 阳极氧化 100 件 报价", [], use_llm=False)
    assert r["source"] == "rules", f"use_llm=false 未走规则路由: {r}"
    assert r["strategy"] == "rules(use_llm=false)"
    assert "calc_quote" in r["skills"]


def test_dispatch_respects_use_llm_false(monkeypatch):
    """dispatch 层把 task_args.use_llm=false 透传到 route (调用方意图不丢)。"""
    cfg = sc.default_config()
    cfg["dispatcher"]["strategy"] = "auto"
    disp = SkillDispatcher(cfg=cfg)
    monkeypatch.setattr(
        disp, "_ensure_planner",
        lambda: (_ for _ in ()).throw(AssertionError("no planner expected")))
    resp = disp.dispatch(intent="6061 铝件 阳极氧化 100 件 报价",
                         args={"use_llm": False}, driver="console")
    assert resp["route"]["source"] == "rules"
    assert resp["route"]["strategy"] == "rules(use_llm=false)"


def test_route_use_llm_absent_or_true_keeps_llm_first(monkeypatch):
    """不传/传 true 时维持原行为 (auto: LLM 优先, 规则兜底) — 修 use_llm 不得误伤泛化路由。"""
    cfg = sc.default_config()
    cfg["dispatcher"]["strategy"] = "auto"
    disp = SkillDispatcher(cfg=cfg)

    class _FakePlanner:
        def online(self):
            return True

        def _active_model(self):
            return "fake-model"

        def _post_chat(self, payload):
            return {"choices": [{"message": {"content":
                    '{"skills": ["golden_chain"], "thought": "full flow"}'}}]}

    monkeypatch.setattr(disp, "_ensure_planner", lambda: _FakePlanner())
    r = disp.route("Quote 100 anodized 6061 brackets", [])
    assert r["strategy"] == "auto:llm" and r["skills"] == ["golden_chain"]
    r2 = disp.route("Quote 100 anodized 6061 brackets", [], use_llm=True)
    assert r2["strategy"] == "auto:llm"


# ---- N1: 审计演示违规不得冒充"OpenShell 违规" (狼来了) ----

def test_dispatch_override_demo_not_in_openshell_violations():
    """iron_rule_override_blocked 是设计内的"模拟 LLM 篡改已被锁拦截"审计演示;
    其 violation 不得再进 openshell_violations — 否则每轮响应都吐红字
    "OpenShell 违规: 确定性输出被改写" (2026-09-25 公网实测, 每次任务必现),
    真违规会被淹没 (狼来了)。演示结果只归 iron_rule_override_blocked。
    """
    cfg = sc.default_config()
    cfg["dispatcher"]["strategy"] = "rules_only"
    disp = SkillDispatcher(cfg=cfg)
    args = {"email_text": "请报价: 铝合金6061 工件 100 件, 尺寸50x30x10mm, 阳极氧化",
            "customer": {"name": "Northwind"}, "use_llm": False}
    r1 = disp.dispatch(intent="黄金链 端到端 报价", skills=["golden_chain"],
                       args=dict(args), driver="console")
    r2 = disp.dispatch(intent="黄金链 端到端 报价", skills=["golden_chain"],
                       args=dict(args), driver="console")
    assert "golden_chain" in r1["executed_skills"], "第一轮 golden_chain 未执行"
    assert "golden_chain" in r2["executed_skills"], "第二轮 golden_chain 未执行"
    assert r1["openshell_violations"] == [], (
        f"健康轮次不得有 OpenShell 违规: {r1['openshell_violations']}")
    assert r2["openshell_violations"] == [], "不得跨轮累积历史违规"
    demo = r1.get("iron_rule_override_blocked") or {}
    assert demo.get("allowed") is False, "篡改演示仍须被锁拦下"
    assert demo.get("violations"), "演示违规明细归 iron_rule_override_blocked"


def test_dispatch_real_violation_still_surfaces(monkeypatch):
    """真违规 (同输入二次执行输出被改) 仍必须进 openshell_violations 断红字 —
    收紧演示语义不得给铁律①开后门。"""
    cfg = sc.default_config()
    cfg["dispatcher"]["strategy"] = "rules_only"
    disp = SkillDispatcher(cfg=cfg)
    calls = {"n": 0}

    def _fake_execute(sid, args, ctx):
        calls["n"] += 1
        price = 222.65 if calls["n"] == 1 else 999.99     # 第二轮改价
        return {"ok": True, "skill": sid, "iron_rule": "deterministic",
                "unit_price": price, "final_price": price * 100}

    from services import skill_dispatcher as _sd
    monkeypatch.setattr(_sd.rt, "execute", _fake_execute)
    args = {"material": "6061", "quantity": 100}
    r1 = disp.dispatch(intent="calc_quote 6061", skills=["calc_quote"],
                       args=dict(args), driver="console")
    r2 = disp.dispatch(intent="calc_quote 6061", skills=["calc_quote"],
                       args=dict(args), driver="console")
    assert "calc_quote" in r1["executed_skills"]
    assert r1["openshell_violations"] == []
    assert r2["openshell_violations"], "同输入改价必须被铁律①拦下并上抛"
    assert r2["openshell_violations"][0]["reason"] == "确定性输出被改写"
    assert "calc_quote" not in r2["executed_skills"], "违规输出不得被采用"
