"""test_skill_text2cad_registration.py — #193 Q9: text2cad skill 注册契约.

注册三层面 (缺一不可, 每条均有 file:line 实证):
  1. skills/text2cad/{SKILL.md,tool.py} — 自动发现 (skills/_runtime + services.skill_registry),
     tool.py 薄桥只转 services.text2cad.build_part, 引擎逻辑不拆进 skill 目录
     (同 skills/render-thumbnail/tool.py 模式, T6 薄桥纪律)。
  2. config/skills.yaml — dispatcher 可达 + OpenShell 策略 (local-only + skill-allowlist)。
  3. openclaw-skills/text2cad/SKILL.md — OpenClaw 侧薄桥 (同 test_openclaw_bridges.py 纪律:
     只 Read + curl, 坐标走 env UEA_LIVEKERNEL_URL, 无公网 IP 字面量)。

铁律:
  - text2cad 只画图不定价 — 报价永远由 Timo 引擎裁决 (铁律②), 几何确定性生成。
  - 缺参 → ok False + missing (槽位填充/HITL), 引擎不兜底默认尺寸。
  - cadquery 缺席 → 诚实 MOCK (cadquery-unavailable), 零落盘零冒充。
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
import yaml

import services.skill_registry as sr
from services import skill_config as sc
from services.openshell import check_skill_allowed, load_policies

ROOT = Path(__file__).resolve().parent.parent


def _load_cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "skills.yaml").read_text(encoding="utf-8"))


# ---- 层面 1: skills/ 自动发现 ----

def test_text2cad_discovered_with_contract():
    found = {s.get("name"): s for s in sr.discover()}
    assert "text2cad" in found, "skills/text2cad/SKILL.md 未注册到 skill_registry"
    s = found["text2cad"]
    assert s.get("iron_rule") == "deterministic"
    contract = (s.get("tool_contract") or {}).get("openai_function") or {}
    assert contract.get("name") == "text2cad"
    props = (contract.get("parameters") or {}).get("properties") or {}
    assert "shape" in props, "tool_contract 缺 shape 参数"
    assert "params" in props, "tool_contract 缺 params 参数"


def test_text2cad_runtime_discover():
    from skills import _runtime
    reg = _runtime.discover(force=True)
    assert "text2cad" in reg, "skills/_runtime 未发现 text2cad tool.py"


# ---- 层面 2: skills.yaml 注册 + OpenShell 门禁 ----

def test_text2cad_registered_in_skills_yaml():
    cfg = _load_cfg()
    entry = (cfg.get("skills") or {}).get("text2cad")
    assert entry is not None, "config/skills.yaml 缺 text2cad 条目 (dispatcher 不可达)"
    assert entry.get("enabled") is True
    assert entry.get("label"), "缺 label"
    assert entry.get("iron_rule") == "deterministic"
    openshell = set(entry.get("openshell") or [])
    assert {"local-only", "skill-allowlist"} <= openshell, \
        f"text2cad openshell 策略不足: {openshell}"


def test_text2cad_allowed_by_openshell_allowlist():
    ok, viols = check_skill_allowed("text2cad", load_policies(), sc.load())
    assert ok, f"OpenShell skill-allowlist 拦截 text2cad: {viols}"


# ---- 层面 1b: tool.py 薄桥行为 (不重造引擎, 只转发) ----

def _load_tool():
    p = ROOT / "skills" / "text2cad" / "tool.py"
    assert p.exists(), "skills/text2cad/tool.py 不存在"
    spec = importlib.util.spec_from_file_location("skill_tool_text2cad", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _SpyCtx:
    """不用真实 controller — 薄桥不该摸 controller (render-thumbnail 模式验证过)."""


def test_tool_passthrough_envelope(monkeypatch):
    from services import text2cad
    calls = {}

    def spy(shape, params, out_dir, formats=None, cq=None, name=""):
        calls.update(shape=shape, params=params, out_dir=out_dir,
                     formats=formats, name=name)
        return {"ok": True, "skill": "text2cad", "shape": shape,
                "sha256_16": "deadbeefcafe0001", "files": {"step": "x.step"},
                "geometry": {"bbox_mm": [1, 1, 1]}, "_source": "services.text2cad"}

    monkeypatch.setattr(text2cad, "build_part", spy)
    tool = _load_tool()
    out = tool.run(_SpyCtx(), shape="flange",
                   params={"outer_dia": 60, "thickness": 10, "bore_dia": 20,
                           "bolt_circle_dia": 44, "hole_count": 4, "hole_dia": 6})
    assert calls["shape"] == "flange"
    assert calls["params"]["hole_count"] == 4
    assert calls["name"] == ""
    # 薄桥原样透传引擎 envelope, 不篡改
    assert out["ok"] is True
    assert out["sha256_16"] == "deadbeefcafe0001"
    assert out["iron_rule"] == "deterministic"
    assert out["skill"] == "text2cad"


def test_tool_error_envelope_gets_iron_rule(monkeypatch):
    from services import text2cad

    def boom(*a, **kw):
        raise RuntimeError("kernel exploded")

    monkeypatch.setattr(text2cad, "build_part", boom)
    tool = _load_tool()
    out = tool.run(_SpyCtx(), shape="pipe", params={"outer_dia": 60, "wall": 3, "length": 70})
    assert out["ok"] is False
    assert out["skill"] == "text2cad"
    assert "kernel exploded" in out["error"]
    assert out["iron_rule"] == "deterministic"


def test_tool_missing_shape_passthrough(monkeypatch):
    """空 shape → 引擎 shape-required, 薄桥不自己兜底 (契约边界在引擎)。"""
    from services import text2cad
    seen = {}

    def spy(shape, params, out_dir, formats=None, cq=None, name=""):
        seen["shape"] = shape
        return text2cad._result(False, error="shape-required")

    monkeypatch.setattr(text2cad, "build_part", spy)
    tool = _load_tool()
    out = tool.run(_SpyCtx(), shape="", params=None)
    assert seen["shape"] == ""
    assert out["ok"] is False
    assert out["error"] == "shape-required"
