"""material-knowledge skill tool — 确定性材料知识查询 (Item6 策展).

被 skills._runtime 自动发现注册; 数据源 services.domain_knowledge.MATERIAL_KNOWLEDGE。
铁律: deterministic / 不定价 / 不改状态机 / 未收录诚实 not-found。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

SKILL_META = {"skill": "material_knowledge", "iron_rule": "deterministic",
              "source": "domain_knowledge", "cannot_override_price": True}

# 牌号识别用 (query 无显式 material 时从文本扫描)
_IDENTIFIABLE = ["316L", "304", "6061", "7075", "TC4", "45钢", "Q235", "黄铜",
                 "SUS304", "SUS316L", "Ti-6Al-4V", "Ti6Al4V", "C45", "H62", "H65",
                 "carbon_steel", "碳钢", "不锈钢", "铝合金", "钛合金", "紫铜"]


def _extract_material_from_text(text: str) -> Optional[str]:
    """从自然语言里识别材料牌号 (确定性关键词扫描, 长牌优先)."""
    if not text:
        return None
    for tok in sorted(_IDENTIFIABLE, key=len, reverse=True):
        if tok.lower() in text.lower():
            return tok
    return None


def _material_payload(dk, material: str) -> Dict[str, Any]:
    info = dk.lookup_material(material)
    if info is None:
        return {"requested": material, "found": False}
    out = dict(info)
    out["requested"] = material
    out["found"] = True
    # 工艺兼容提示 (阳极/热处理) — 只读知识, 不定价
    out["anodizing_ok"] = bool(info.get("anodizing_ok"))
    out["heat_treatable"] = bool(info.get("heat_treatable"))
    return out


def run(ctx, material: str = "", query: str = "",
        compare: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
    """材料知识查询: 单材料 / 自然语言识别 / 多材料对比."""
    from services import domain_knowledge as dk

    catalog = sorted(dk.MATERIAL_KNOWLEDGE.keys())

    # 对比模式
    if compare:
        rows = [_material_payload(dk, m) for m in compare]
        found = [r for r in rows if r.get("found")]
        return {**SKILL_META, "ok": bool(found), "mode": "compare",
                "comparison": rows,
                "reason": None if found else "no material resolved",
                "catalog": catalog}

    # 单材料: 显式 material 优先, 否则从 query 识别
    target = (material or "").strip()
    identified_from = "explicit"
    if not target and query:
        target = _extract_material_from_text(query) or ""
        identified_from = "query" if target else "none"

    if not target:
        # 无任何材料线索 → 返回目录 (诚实, 不假造)
        return {**SKILL_META, "ok": True, "mode": "catalog",
                "material": None, "catalog": catalog,
                "note": "未指定材料; 返回已收录牌号目录。提供 material 或含牌号的 query 以查属性。"}

    info = dk.lookup_material(target)
    if info is None:
        return {**SKILL_META, "ok": False, "mode": "lookup",
                "reason": "material_not_found", "requested": target,
                "identified_from": identified_from, "catalog": catalog,
                "note": "未收录该材料; 不假造属性。已收录见 catalog。"}

    payload = _material_payload(dk, target)
    return {**SKILL_META, "ok": True, "mode": "lookup",
            "material": payload, "identified_from": identified_from,
            "query": query or None}
