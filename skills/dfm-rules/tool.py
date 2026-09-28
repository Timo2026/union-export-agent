"""dfm-rules skill tool — 确定性几何可制造性规则检查 (Item6 策展).

被 skills._runtime 自动发现注册; 规则源 services.domain_knowledge.check_dfm_geometry。
铁律: deterministic / 规则分诊 only 不认证 / 缺失字段诚实 / 不定价 / 不改状态机。
补充 check_dfm (材料×表面冲突); 本 skill 专管几何尺寸规则。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

SKILL_META = {"skill": "dfm_rules", "iron_rule": "deterministic",
              "source": "domain_knowledge", "cannot_override_price": True,
              "certifies": False}


def _num(v: Any) -> Optional[float]:
    """安全转 float; None/空/非法 → None (不假造)."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def run(ctx, material: str = "", surface: str = "",
        wall_thickness_mm: Any = None, hole_depth_mm: Any = None,
        hole_dia_mm: Any = None, inner_radius_mm: Any = None,
        tolerance_mm: Any = None, rfq: Optional[Dict[str, Any]] = None,
        **kwargs) -> Dict[str, Any]:
    """几何 DFM 规则检查. 缺 material 且无几何输入 → 诚实报错."""
    from services import domain_knowledge as dk

    # 允许从 rfq / scratch 兜底取材料 (与 check_dfm 一致的便利)
    rfq = dict(rfq or (ctx.scratch.get("rfq") if hasattr(ctx, "scratch") and isinstance(getattr(ctx, "scratch", None), dict) else {}) or {})
    material = material or rfq.get("material") or ""
    surface = surface or rfq.get("surface") or ""

    wall = _num(wall_thickness_mm)
    hd = _num(hole_depth_mm)
    hdia = _num(hole_dia_mm)
    ir = _num(inner_radius_mm)
    tol = _num(tolerance_mm)

    has_geometry = any(v is not None for v in (wall, hd, hdia, ir, tol))
    if not material and not has_geometry:
        return {**SKILL_META, "ok": False,
                "reason": "no_input",
                "error": "需提供 material 和/或几何参数 (wall_thickness_mm/hole_depth_mm/hole_dia_mm/inner_radius_mm/tolerance_mm)",
                "required_fields": ["material", "wall_thickness_mm", "hole_depth_mm",
                                    "hole_dia_mm", "inner_radius_mm", "tolerance_mm"]}

    res = dk.check_dfm_geometry(
        material=material, wall_thickness_mm=wall, hole_depth_mm=hd,
        hole_dia_mm=hdia, inner_radius_mm=ir, tolerance_mm=tol, surface=surface)

    out = {**SKILL_META, "ok": True, **res}
    # 便利汇总 (供调度器/SOP 读)
    out["n_violations"] = len(res.get("violations", []))
    out["n_warnings"] = len(res.get("warnings", []))
    # 写入 scratch 供黄金链下游复用 (不覆盖 dfm 权威字段, 用独立 key)
    try:
        if hasattr(ctx, "scratch") and isinstance(ctx.scratch, dict):
            ctx.scratch["dfm_geometry"] = out
    except Exception:
        pass
    return out
