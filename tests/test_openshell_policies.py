"""test_openshell_policies.py — OpenShell YAML 加载 + 铁律① + HITL + 路径沙箱."""
from __future__ import annotations

import copy
from typing import Any, Dict

import pytest

from services import skill_config as sc
from services.openshell import (
    OpenShell, check_hitl, check_local_paths, check_skill_allowed,
    load_policies, sha256_obj,
)


@pytest.fixture
def policies():
    return load_policies()


def test_load_policies_all_present(policies):
    for pid in ("iron-rule-1", "hitl-required", "local-only", "skill-allowlist"):
        assert pid in policies
    assert policies["iron-rule-1"].get("locked") is True
    assert "calc_quote" in (policies["iron-rule-1"].get("applies_to") or [])
    assert "parse_rfq" in (policies["skill-allowlist"].get("allowed") or [])


def test_iron_rule_1_cannot_be_disabled_in_config(tmp_path):
    cfg = sc.default_config()
    cfg["openshell"]["iron-rule-1"]["enabled"] = False
    errs = sc.validate(cfg)
    assert any("iron-rule-1" in e for e in errs)
    with pytest.raises(ValueError):
        sc.save(cfg, path=tmp_path / "skills.yaml")


def test_save_forces_iron_rule_locked(tmp_path):
    cfg = sc.default_config()
    cfg["openshell"]["iron-rule-1"] = {"enabled": False, "locked": False}
    # validate 会先失败; 用合法配置再强制 locked
    cfg["openshell"]["iron-rule-1"] = {"enabled": True, "locked": False}
    # locked=false 也非法
    with pytest.raises(ValueError):
        sc.save(cfg, path=tmp_path / "skills.yaml")
    cfg["openshell"]["iron-rule-1"] = {"enabled": True, "locked": True}
    saved = sc.save(cfg, path=tmp_path / "skills.yaml")
    assert saved["openshell"]["iron-rule-1"]["locked"] is True
    assert saved["openshell"]["iron-rule-1"]["enabled"] is True


def test_skill_allowlist_blocks_unknown(policies):
    cfg = sc.default_config()
    ok, viols = check_skill_allowed("not_a_skill", policies, cfg)
    assert not ok
    assert viols and viols[0]["policy"] == "skill-allowlist"


def test_skill_allowlist_blocks_disabled(policies):
    cfg = sc.default_config()
    cfg["skills"] = {"calc_quote": {"enabled": False}}
    ok, viols = check_skill_allowed("calc_quote", policies, cfg)
    assert not ok


def test_local_only_blocks_outside_sandbox(policies):
    args = {"path": "C:/Windows/System32/evil.step"}
    viols = check_local_paths(args, policies, sc.default_config())
    assert viols
    assert viols[0]["policy"] == "local-only"


def test_local_only_allows_data_path(policies):
    args = {"path": "data/samples/bracket.step"}
    viols = check_local_paths(args, policies, sc.default_config())
    assert viols == []


def test_hitl_triggers_on_high_total(policies):
    out = {"quote_total_cny": 200000, "unit_price_cny": 100}
    hitl, reasons = check_hitl(out, policies, sc.default_config())
    assert hitl
    assert any(r["field"] == "quote_total_cny" for r in reasons)


def test_hitl_no_trigger_when_normal(policies):
    out = {"quote_total_cny": 5000, "unit_price_cny": 100, "risk_score": 0.2,
           "verification_status": "PASS", "dfm_valid": True}
    hitl, reasons = check_hitl(out, policies, sc.default_config())
    assert not hitl


def test_openshell_blocks_deterministic_override(policies):
    shell = OpenShell(cfg=sc.default_config(), policies=policies)
    original = {"unit_price": 100, "final_price": 5000, "ok": True}
    post = shell.postcheck("calc_quote", original, iron_rule="deterministic")
    assert post["ok"]
    assert post["iron_locked"]
    assert post["output_sha256"] == sha256_obj(original)
    tampered = dict(original)
    tampered["unit_price"] = 999999
    attempt = shell.attempt_override("calc_quote", tampered)
    assert not attempt["allowed"]
    assert attempt["violations"]


def test_openshell_status_lists_policies(policies):
    shell = OpenShell(cfg=sc.default_config(), policies=policies)
    st = shell.status()
    ids = {p["id"] for p in st["policies"]}
    assert {"iron-rule-1", "hitl-required", "local-only", "skill-allowlist"} <= ids
    iron = next(p for p in st["policies"] if p["id"] == "iron-rule-1")
    assert iron["locked"] is True


# --- A6: iron-rule-1 哈希只覆盖确定性载荷 (节点实测: 两轮 golden_chain 仅 9 处易变标识不同) ---

def _golden_chain_output(context_id: str, latency_ms: float) -> Dict[str, Any]:
    """复刻节点实测 golden_chain 输出形态; 每轮易变字段与实证一致:
    context_id (顶层+raw) / audit_head / audit_path / trace_id / export_path /
    _latency_ms / reply.subject (内嵌 context_id)。"""
    return {
        "ok": True,
        "skill": "golden_chain",
        "iron_rule": "deterministic",
        "context_id": context_id,
        "state": "HITL",
        "verification_status": "HITL",
        "quote": {"unit_price": 281.25, "final_price": 365.62, "profit": 84.38,
                  "lead_time_days": 5, "_source": "live:/api/quote"},
        "unit_price": 281.25,
        "final_price": 365.62,
        "quote_total_cny": 365.62,
        "dfm_valid": True,
        "multimodal_conflicts": [],
        "reply": {"subject": f"Re: RFQ {context_id} — under review",
                  "auto_send": False, "mode": "draft_only",
                  "guardrail_output": {"pass": True, "flags": []}},
        "hitl_required": True,
        "_source": "live:cnc-ai-brain:7862",
        "engine_source": "live:cnc-ai-brain:7862",
        "raw": {
            "context_id": context_id,
            "audit_head": f"audit-head-{context_id}",
            "audit_path": f"data/contexts/{context_id}.audit.json",
            "state_history": [{"from": None, "to": "NEW", "reason": "init"}],
            "observability": {
                "trace_id": f"trace-{context_id}",
                "export_path": f"data/traces/{context_id}.jsonl",
                "metrics": {"tool_calls": 5, "tool_errors": 0, "hitl_triggers": 1},
            },
        },
        "state_history": [{"from": None, "to": "NEW", "reason": "init"}],
        "flywheel": {"_skipped": "no customer_id"},
        "driver": "email",
        "_latency_ms": latency_ms,
    }


_ARGS_6061 = {"material": "6061", "quantity": 100, "surface": "anodized",
              "tolerance_grade": "IT7", "destination_country": "Germany",
              "incoterm": "FOB", "shipping_mode": "sea"}


def test_iron_rule_allows_rerun_when_only_volatile_ids_differ(policies):
    """A6 break: 同一输入重跑, 仅 context_id/audit_head/trace_id/_latency_ms 等
    每轮易变标识不同, 不得判"确定性输出被改写" (现场曾误拦: expected 0b219b0b vs actual fe0a…)。"""
    shell = OpenShell(cfg=sc.default_config(), policies=policies)
    post1 = shell.postcheck("golden_chain",
                            _golden_chain_output("RFQ-20260921-22C005", 74.1),
                            iron_rule="deterministic", args=_ARGS_6061)
    assert post1["ok"]
    post2 = shell.postcheck("golden_chain",
                            _golden_chain_output("RFQ-20260921-342F80", 67.5),
                            iron_rule="deterministic", args=_ARGS_6061)
    assert post2["ok"], f"同参重放被误拦: {post2['violations']}"
    assert post2["output_sha256"] == post1["output_sha256"]


def test_iron_rule_allows_cache_hit_rerun_with_runtime_envelope(policies):
    """A6 break #2 (节点实测): 同参第二次执行命中 AgentCache —
    skills/_runtime.py:218-223 把缓存输出的运行时信封覆写为
    _source=agent_cache / _cache=hit / _latency_ms 重算, 载荷本身逐字节相同
    (cache.set 存的就是首次输出)。不得判"确定性输出被改写"。
    现场实证: 同 daemon 重放 expected 9e75c7e8 vs actual 3cd0ac8a, 深 diff 仅
    /_cache /_latency_ms /_source 三处, 价格 281.25/365.62 两轮一致。"""
    shell = OpenShell(cfg=sc.default_config(), policies=policies)
    live = _golden_chain_output("RFQ-20260921-22C005", 74.1)
    live["_cache"] = "miss"
    post1 = shell.postcheck("golden_chain", live,
                            iron_rule="deterministic", args=_ARGS_6061)
    assert post1["ok"]
    hit = _golden_chain_output("RFQ-20260921-22C005", 74.1)  # 缓存即首次输出
    hit["_source"] = "agent_cache"
    hit["_cache"] = "hit"
    hit["_latency_ms"] = 0.1
    post2 = shell.postcheck("golden_chain", hit,
                            iron_rule="deterministic", args=_ARGS_6061)
    assert post2["ok"], f"缓存命中重放被误拦: {post2['violations']}"
    assert post2["output_sha256"] == post1["output_sha256"]


def test_iron_rule_still_blocks_price_tamper_despite_volatile_keys(policies):
    """剥离易变标识不得开后门: LLM 改价仍必须被拦。"""
    shell = OpenShell(cfg=sc.default_config(), policies=policies)
    assert shell.postcheck(
        "golden_chain", _golden_chain_output("RFQ-20260921-22C005", 74.1),
        iron_rule="deterministic", args=_ARGS_6061)["ok"]
    tampered = _golden_chain_output("RFQ-20260921-342F80", 67.5)
    tampered["unit_price"] = 562.50
    tampered["quote"]["unit_price"] = 562.50
    post = shell.postcheck("golden_chain", tampered,
                           iron_rule="deterministic", args=_ARGS_6061)
    assert not post["ok"]
    assert post["violations"][0]["reason"] == "确定性输出被改写"


def test_iron_rule_still_blocks_nested_source_tamper_despite_envelope_strip(policies):
    """运行时信封 (顶层 _source/_cache/_latency_ms) 可剥; 载荷内的引擎出处
    (quote._source: live:/api/quote) 被改写仍必须拦 — 剥信封不得把载荷出处
    也剥出锁外 (防"全局剥 _source"式的过度实现)。"""
    shell = OpenShell(cfg=sc.default_config(), policies=policies)
    assert shell.postcheck(
        "golden_chain", _golden_chain_output("RFQ-20260921-22C005", 74.1),
        iron_rule="deterministic", args=_ARGS_6061)["ok"]
    tampered = _golden_chain_output("RFQ-20260921-22C005", 74.1)
    tampered["quote"]["_source"] = "mock"
    post = shell.postcheck("golden_chain", tampered,
                           iron_rule="deterministic", args=_ARGS_6061)
    assert not post["ok"]
    assert post["violations"][0]["reason"] == "确定性输出被改写"


def test_iron_rule_still_blocks_autosend_flip_despite_volatile_keys(policies):
    """铁律① egress 字段 (draft_only/auto_send:false) 被翻面仍必须被拦。"""
    shell = OpenShell(cfg=sc.default_config(), policies=policies)
    assert shell.postcheck(
        "golden_chain", _golden_chain_output("RFQ-20260921-22C005", 74.1),
        iron_rule="deterministic", args=_ARGS_6061)["ok"]
    tampered = _golden_chain_output("RFQ-20260921-342F80", 67.5)
    tampered["reply"]["auto_send"] = True
    tampered["reply"]["mode"] = "auto"
    post = shell.postcheck("golden_chain", tampered,
                           iron_rule="deterministic", args=_ARGS_6061)
    assert not post["ok"]
