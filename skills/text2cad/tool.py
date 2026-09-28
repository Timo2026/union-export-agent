"""text2cad — 参数 → CAD (STEP/STL) 薄桥 (复刻 nl2cad 画图能力, 任务 #193).

引擎在 services/text2cad.py (Q5-Q8 已筑: 5 模板族 + 几何三重校验 + 缺参 HITL);
skill 层只做转发 + envelope 定型, 不重造几何逻辑 (T6 薄桥纪律, 同 render-thumbnail)。

铁律:
  - 只画图不定价 — 报价永远由 Timo 引擎裁决 (铁律②)。
  - 缺必填参数 → 引擎 missing-params (槽位填充/HITL), 本层不兜底默认尺寸。
  - cadquery 缺席 → 引擎诚实降级 cadquery-unavailable (零落盘零冒充)。
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def run(ctx, shape: str = "", params: Optional[Dict[str, Any]] = None,
        formats: Any = None, name: str = "", **kwargs) -> Dict[str, Any]:
    kw: Dict[str, Any] = {}
    if formats:
        kw["formats"] = tuple(formats)
    from services import text2cad
    try:
        out = text2cad.build_part(shape, params or {},
                                  text2cad.DEFAULT_OUT_DIR, name=name, **kw)
    except Exception as e:  # noqa
        return {"ok": False, "skill": "text2cad", "error": repr(e),
                "iron_rule": "deterministic", "_source": "skills.text2cad"}
    if not isinstance(out, dict):
        out = {"result": out}
    out.setdefault("ok", True)
    out.setdefault("skill", "text2cad")
    out.setdefault("iron_rule", "deterministic")
    out.setdefault("_source", "services.text2cad")
    return out
