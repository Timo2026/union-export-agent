"""process-knowledge skill tool — 确定性工艺路由查询 (Item6 策展).

被 skills._runtime 自动发现注册; 数据源 services.domain_knowledge.PROCESS_KNOWLEDGE。
铁律: deterministic / 不定价 (cost_tier 仅相对档) / 不认证最终工艺 / 诚实 not-found。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

SKILL_META = {"skill": "process_knowledge", "iron_rule": "deterministic",
              "source": "domain_knowledge", "cannot_override_price": True,
              "certifies": False}


def run(ctx, material: str = "", process: str = "", surface: str = "",
        need_heat_treat: bool = False, tight_tolerance: bool = False,
        geometry: str = "", **kwargs) -> Dict[str, Any]:
    """工艺路由 / 工艺详情 / 工艺目录."""
    from services import domain_knowledge as dk

    catalog = sorted(dk.PROCESS_KNOWLEDGE.keys())

    # 模式 1: 指定工艺名 → 详情
    if process:
        detail = dk.process_detail(process)
        if detail is None:
            return {**SKILL_META, "ok": False, "mode": "detail",
                    "reason": "process_not_found", "requested": process,
                    "catalog": catalog}
        return {**SKILL_META, "ok": True, "mode": "detail",
                "process": process, "process_detail": detail}

    # 模式 2: 材料 (+需求) → 路由
    if material:
        info = dk.lookup_material(material)
        route = dk.compatible_processes(
            material, surface=surface, need_heat_treat=bool(need_heat_treat),
            tight_tolerance=bool(tight_tolerance), geometry=geometry)
        return {**SKILL_META, "ok": True, "mode": "route", **route,
                "material_found": info is not None,
                "request": {"material": material, "surface": surface or None,
                            "need_heat_treat": bool(need_heat_treat),
                            "tight_tolerance": bool(tight_tolerance),
                            "geometry": geometry or None}}

    # 模式 3: 无线索 → 工艺目录 (诚实, 不假造)
    return {**SKILL_META, "ok": True, "mode": "catalog",
            "processes": [{"id": pid, "name": p["name"], "category": p.get("category"),
                           "cost_tier": p.get("cost_tier")}
                          for pid, p in dk.PROCESS_KNOWLEDGE.items()],
            "catalog": catalog,
            "note": "未指定材料/工艺; 返回工艺目录。提供 material (路由) 或 process (详情) 以查询。"}
