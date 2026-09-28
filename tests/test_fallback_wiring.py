"""test_fallback_wiring.py — C4 A/B 降级链接线 (P1 巡检: 节点 Omni :8002 单点)。

_build_planner 必须把 models.yaml llm lane 的 fallback:{endpoint,model} 注入
LLMPlanner; 未配置时保持 None (显式 MOCK 降级路径不动)。
"""
from __future__ import annotations

from bootstrap import _build_planner

_SETTINGS = {"model_router": {"backend": "local",
                              "roles": {"REASON": {"endpoint": "http://unused/v1",
                                                   "model": "unused-model"}}}}


def _mcfg(fallback=None):
    llm = {"endpoint": "http://127.0.0.1:8002/v1", "model": "nemotron-omni-30b-a3b",
           "enabled": True}
    if fallback is not None:
        llm["fallback"] = fallback
    return {"models": {"llm": llm}}


def test_build_planner_injects_fallback_from_models_yaml():
    p = _build_planner(_SETTINGS, _mcfg({"endpoint": "http://127.0.0.1:8902/v1",
                                         "model": "qwen3-0.6b"}))
    assert p.endpoint == "http://127.0.0.1:8002/v1"       # primary 仍取 llm lane
    assert p.fallback_endpoint == "http://127.0.0.1:8902/v1"
    assert p.fallback_model == "qwen3-0.6b"


def test_build_planner_without_fallback_stays_none():
    p = _build_planner(_SETTINGS, _mcfg())
    assert p.fallback_endpoint is None and p.fallback_model is None


def test_build_planner_no_mcfg_still_constructs():
    p = _build_planner(_SETTINGS, None)                   # settings 回退路径不受影响
    assert p.endpoint == "http://unused/v1"
