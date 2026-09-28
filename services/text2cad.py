"""text2cad — 参数 → CAD (STEP/STL) + 几何事实 (复刻 nl2cad 画图能力, 任务 #190).

铁律:
  - 几何由 cadquery 内核确定性生成, 无 LLM 编造坐标; cadquery 缺席 (开发机)
    → 显式 MOCK:cadquery-unavailable, 零落盘零冒充 (同 HybridEmbedder 降级语义)。
  - 缺必填参数 → ok False + missing 列表, 引擎不兜底默认值 (槽位填充由 Omni
    提议 + HITL 确认; 回填默认值等于按猜的尺寸出图 — 禁止)。
  - 产物指纹 sha256_16 为真实文件字节哈希 (防假事实); 结果可 json 序列化。
  - 同名参数 → 同名文件 (幂等覆盖), 便于链路复访。

窄 cadquery API 面 (节点 occ env 实测可用; 单测以替身注入同型 API):
  cq.Workplane("XY") / .box(l,w,h) / .circle(d) / .extrude(h) / .center(x,y)
  .union(w) / .cut(w) / .translate(v) / cq.exporters.export(obj, path)
  事实: solid.BoundingBox().xlen/ylen/zlen + solid.Volume()
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

log = logging.getLogger(__name__)

SKILL = "text2cad"
DEFAULT_OUT_DIR = "data/cad"
SUPPORTED_FORMATS = ("step", "stl")
MOCK_SOURCE = "MOCK:cadquery-unavailable"

SHAPES: Dict[str, Dict[str, Any]] = {
    "flange": {
        "label": "法兰盘",
        "doc": "中心孔 + 均布螺栓孔圆盘 (bore_dia=0 可省中心孔)",
        "params": {
            "outer_dia": {"type": "float", "required": True, "min": 5, "max": 2000,
                          "unit": "mm"},
            "thickness": {"type": "float", "required": True, "min": 1, "max": 500,
                          "unit": "mm"},
            "bore_dia": {"type": "float", "required": False, "min": 0, "max": 2000,
                         "unit": "mm", "default": 0},
            "bolt_circle_dia": {"type": "float", "required": True, "min": 5,
                                "max": 2000, "unit": "mm"},
            "hole_count": {"type": "int", "required": True, "min": 3, "max": 24},
            "hole_dia": {"type": "float", "required": True, "min": 1, "max": 500,
                         "unit": "mm"},
        },
    },
    "l_bracket": {
        "label": "L 型支架",
        "doc": "两腿互成直角的角码 (hole_dia>0 时底板中心开孔)",
        "params": {
            "leg_a": {"type": "float", "required": True, "min": 5, "max": 2000,
                      "unit": "mm"},
            "leg_b": {"type": "float", "required": True, "min": 5, "max": 2000,
                      "unit": "mm"},
            "width": {"type": "float", "required": True, "min": 3, "max": 1000,
                      "unit": "mm"},
            "thickness": {"type": "float", "required": True, "min": 1, "max": 200,
                          "unit": "mm"},
            "hole_dia": {"type": "float", "required": False, "min": 1, "max": 500,
                         "unit": "mm", "default": 0},
        },
    },
    "bushing": {
        "label": "轴套",
        "doc": "等径通孔套筒",
        "params": {
            "outer_dia": {"type": "float", "required": True, "min": 3, "max": 2000,
                          "unit": "mm"},
            "inner_dia": {"type": "float", "required": True, "min": 1, "max": 2000,
                          "unit": "mm"},
            "length": {"type": "float", "required": True, "min": 3, "max": 2000,
                       "unit": "mm"},
        },
    },
    "plate": {
        "label": "板类",
        "doc": "矩形板 (hole_dia>0 时中心开孔)",
        "params": {
            "length": {"type": "float", "required": True, "min": 5, "max": 5000,
                       "unit": "mm"},
            "width": {"type": "float", "required": True, "min": 5, "max": 5000,
                      "unit": "mm"},
            "thickness": {"type": "float", "required": True, "min": 1, "max": 500,
                          "unit": "mm"},
            "hole_dia": {"type": "float", "required": False, "min": 1, "max": 2000,
                         "unit": "mm", "default": 0},
        },
    },
    "pipe": {
        "label": "管件",
        "doc": "等径直管 (壁厚均匀)",
        "params": {
            "outer_dia": {"type": "float", "required": True, "min": 3, "max": 2000,
                          "unit": "mm"},
            "wall": {"type": "float", "required": True, "min": 0.5, "max": 200,
                     "unit": "mm"},
            "length": {"type": "float", "required": True, "min": 5, "max": 5000,
                       "unit": "mm"},
        },
    },
}


def _result(ok: bool, **kw: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": ok, "skill": SKILL}
    out.update(kw)
    return out


def _coerce(v: Any, typ: str) -> Optional[float]:
    """安全转数; None/空/非法 → None. hole_count 收 "4" (Omni/JSON 常见形态)."""
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if typ == "int":
        return float(int(f)) if float(f).is_integer() else None
    return f


def validate(shape: str, params: Optional[Dict[str, Any]]
             ) -> Tuple[Dict[str, float], List[str], Dict[str, str]]:
    """形状+参数校验 → (归一化参数, 缺失必填, 非法明细).

    缺必填 → missing (槽位填充/HITL); 类型/量程非法 → invalid (调用方错误)。
    两者都绝不静默兜底 — 按猜的尺寸出图比不出图更坏。

    可选参数 default=0 是"不开孔"哨兵 (非用户输入) — 原样采用, 不过量程;
    None/空串视作未提供; 非空非数字值一律 invalid (必填可缺不可错)。
    """
    params = dict(params or {})
    spec = SHAPES[shape]["params"]
    norm: Dict[str, float] = {}
    missing: List[str] = []
    invalid: Dict[str, str] = {}
    for pname, pspec in spec.items():
        v = params.get(pname)
        if v is None or v == "":
            if pspec["required"]:
                missing.append(pname)
            elif pspec.get("default") is not None:
                norm[pname] = float(pspec["default"])
            continue
        n = _coerce(v, pspec["type"])
        if n is None:
            invalid[pname] = f"not-a-number:{v!r}"
            continue
        lo, hi = pspec.get("min"), pspec.get("max")
        if (lo is not None and n < lo) or (hi is not None and n > hi):
            invalid[pname] = f"out-of-range[{lo},{hi}]:{v}"
            continue
        norm[pname] = n
    # 未知参数不回填 (防调用方把 size 当 outer_dia 传进来静默出错)
    return norm, missing, invalid


# ---------- 模板族 (窄 cadquery API; 替身注入同型) ----------
def _cyl(cq: Any, dia: float, h: float) -> Any:
    return cq.Workplane("XY").circle(dia / 2.0).extrude(h)


def _t_flange(cq: Any, p: Dict[str, float]) -> Any:
    t = p["thickness"]
    w = _cyl(cq, p["outer_dia"], t)
    if p.get("bore_dia", 0) > 0:
        w = w.cut(_cyl(cq, p["bore_dia"], t))
    n, r = int(p["hole_count"]), p["bolt_circle_dia"] / 2.0
    for i in range(n):
        a = 2.0 * math.pi * i / n
        hole = cq.Workplane("XY").center(r * math.cos(a), r * math.sin(a)) \
            .circle(p["hole_dia"] / 2.0).extrude(t)
        w = w.cut(hole)
    return w


def _t_l_bracket(cq: Any, p: Dict[str, float]) -> Any:
    t = p["thickness"]
    base = cq.Workplane("XY").box(p["leg_a"], p["width"], t)
    wall = cq.Workplane("XY").box(t, p["width"], p["leg_b"]).translate(
        (p["leg_a"] / 2.0 - t / 2.0, 0.0, p["leg_b"] / 2.0 + t / 2.0))
    w = base.union(wall)
    if p.get("hole_dia", 0) > 0:
        w = w.cut(_cyl(cq, p["hole_dia"], t).translate(
            (0.0, 0.0, -t)))  # 底板中心孔 (贯 trộc 厚度方向)
    return w


def _t_bushing(cq: Any, p: Dict[str, float]) -> Any:
    return _cyl(cq, p["outer_dia"], p["length"]).cut(
        _cyl(cq, p["inner_dia"], p["length"]))


def _t_plate(cq: Any, p: Dict[str, float]) -> Any:
    w = cq.Workplane("XY").box(p["length"], p["width"], p["thickness"])
    if p.get("hole_dia", 0) > 0:
        w = w.cut(_cyl(cq, p["hole_dia"], p["thickness"]))
    return w


def _t_pipe(cq: Any, p: Dict[str, float]) -> Any:
    inner = p["outer_dia"] - 2.0 * p["wall"]
    if inner <= 0:
        raise ValueError(f"wall {p['wall']} 超过外径一半 — 几何非法")
    return _cyl(cq, p["outer_dia"], p["length"]).cut(
        _cyl(cq, inner, p["length"]))


_TEMPLATES = {"flange": _t_flange, "l_bracket": _t_l_bracket,
              "bushing": _t_bushing, "plate": _t_plate, "pipe": _t_pipe}


def _resolve_cq(cq: Any = None) -> Any:
    """cq 注入优先 (单测替身); 否则惰性 import — 缺席则抛 (调用方转 MOCK 结果)."""
    if cq is not None:
        return cq
    import cadquery as _cq  # noqa: WPS433 惰性导入: 内核重, 且开发机常缺席
    return _cq


def _facts(w: Any) -> Dict[str, float]:
    solid = w.val()
    bb = solid.BoundingBox()
    vol = float(solid.Volume())
    return {"bbox_mm": [round(float(bb.xlen), 4), round(float(bb.ylen), 4),
                        round(float(bb.zlen), 4)],
            "volume_mm3": round(vol, 4),
            "volume_cm3": round(vol / 1000.0, 6)}


def build_part(shape: str, params: Optional[Dict[str, Any]],
               out_dir: str = DEFAULT_OUT_DIR,
               formats: Sequence[str] = SUPPORTED_FORMATS,
               cq: Any = None, name: str = "") -> Dict[str, Any]:
    """参数 → CAD 产物 + 几何事实. 契约见 tests/test_skill_text2cad.py (先红后绿)."""
    shape = (shape or "").strip()
    if not shape:
        return _result(False, error="shape-required")
    if shape not in SHAPES:
        return _result(False, error="unknown-shape",
                       available=sorted(SHAPES))
    bad_fmt = [f for f in formats if f not in SUPPORTED_FORMATS]
    if bad_fmt or not formats:
        return _result(False, error="unsupported-format",
                       supported=list(SUPPORTED_FORMATS), got=list(formats))
    norm, missing, invalid = validate(shape, params)
    if missing:
        return _result(False, error="missing-params", missing=missing)
    if invalid:
        return _result(False, error="invalid-params", invalid=invalid)
    try:
        cq_mod = _resolve_cq(cq)
    except Exception as e:  # cadquery 缺席 — 诚实 MOCK, 零落盘
        log.info("[text2cad] cadquery 不可用, 显式降级: %r", e)
        return _result(False, error="cadquery-unavailable",
                       _source=MOCK_SOURCE)
    try:
        w = _TEMPLATES[shape](cq_mod, norm)
        facts = _facts(w)
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        stem = name or (f"{shape}-" + hashlib.sha256(
            json.dumps(norm, sort_keys=True).encode("utf-8")).hexdigest()[:8])
        files: Dict[str, str] = {}
        for fmt in formats:
            fp = d / f"{stem}.{fmt}"
            cq_mod.exporters.export(w, str(fp))
            files[fmt] = str(fp)
    except Exception as e:
        log.warning("[text2cad] 几何生成失败 (%s): %r", shape, e)
        return _result(False, error="geometry-failed",
                       detail=repr(e), _source="services.text2cad")
    step = Path(files["step"]) if "step" in files else Path(files[formats[0]])
    sha16 = hashlib.sha256(step.read_bytes()).hexdigest()[:16]
    return _result(True, shape=shape, label=SHAPES[shape]["label"],
                   iron_rule="deterministic", _source="services.text2cad",
                   params=norm, files=files, geometry=facts, sha256_16=sha16)
