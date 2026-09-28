"""test_skill_text2cad.py — text2cad 契约测试 (任务 #189, 复刻 nl2cad 画图能力).

契约先行 (未实现 — 全红):
  1. shape 缺失/未知 → ok False + 显式错误 + 可用族列表, 绝不回退假几何
  2. 必填参数缺/非法 (负数/非数/hole_count 越界) → ok False + missing/invalid
     (槽位填充交 Omni + HITL, 引擎不兜底造假 — 铁律)
  3. cadquery 不可用 (开发机实况) → ok False + _source "MOCK:cadquery-unavailable"
     显式 MOCK 标注, 不冒充在线几何 (离线铁律, 同 HybridEmbedder 降级语义)
  4. 注入 cadquery 替身 (kernel 缺席开发机的标准注入缝, 同 transport/MockCAT 先例)
     → 落盘 STEP/STL + 几何事实 (bbox/volume) + sha256_16 + iron_rule deterministic
  5. SHAPES 规格表五族自洽: flange/l_bracket/bushing/plate/pipe, 参数带类型/量纲/边界
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from services.text2cad import SHAPES, build_part


# ---------- cadquery 替身 (仅覆盖 GREEN 模板所用的窄 API 面) ----------
class _BB:
    def __init__(self, x: float, y: float, z: float) -> None:
        self.xlen, self.ylen, self.zlen = x, y, z


class _Solid:
    def __init__(self, bbox: _BB, volume: float, faces: int = 6) -> None:
        self._bb, self._vol, self._faces = bbox, volume, faces

    def BoundingBox(self) -> _BB:
        return self._bb

    def Volume(self) -> float:
        return self._vol

    def Faces(self) -> List[Any]:
        return [None] * self._faces


class _WP:
    """Fake cadquery Workplane: box / circle+extrude / union / cut / center / translate 链式."""

    def __init__(self, solid: Optional[_Solid] = None, plane: str = "XY") -> None:
        self._s = solid
        self._d = 0.0
        self._cx = 0.0
        self._cy = 0.0

    def val(self) -> _Solid:
        assert self._s is not None, "fake workplane 无实体 (操作顺序错)"
        return self._s

    def box(self, l: float, w: float, h: float) -> "_WP":
        return _WP(_Solid(_BB(l, w, h), l * w * h))

    def circle(self, r: float) -> "_WP":
        """真实 cadquery .circle() 收半径 — 服务传 dia/2, 直径=2r。"""
        self._d = r
        return self

    def center(self, x: float, y: float) -> "_WP":
        """真实 cadquery: 后续圆/拉伸相对平移后的原点 — 只改空间位置, 尺寸/体积不变
        (法兰均布孔定位用; 体积断言仍是外筒-孔, bbox 仍是外圆)。"""
        self._cx, self._cy = x, y
        return self

    def translate(self, v: Any) -> "_WP":
        """平移实体 (L 支架立板定位用) — 同上只改位置。"""
        return self

    def extrude(self, h: float) -> "_WP":
        r = self._d
        return _WP(_Solid(_BB(2 * r, 2 * r, h),
                          math.pi * r ** 2 * h, faces=3))

    def _other(self, o: Any) -> _Solid:
        return o._s if isinstance(o, _WP) else o

    def union(self, other: Any) -> "_WP":
        a, b = self._s, self._other(other)
        return _WP(_Solid(_BB(max(a._bb.xlen, b._bb.xlen),
                              max(a._bb.ylen, b._bb.ylen),
                              max(a._bb.zlen, b._bb.zlen)),
                          a._vol + b._vol))

    def cut(self, other: Any) -> "_WP":
        a, b = self._s, self._other(other)
        return _WP(_Solid(a._bb, a._vol - b._vol))


class _Exporters:
    @staticmethod
    def export(obj: Any, path: str) -> None:
        Path(path).write_text(f"FAKE-EXPORT {path}\n", encoding="utf-8")


class _CQ:
    Workplane = _WP
    exporters = _Exporters


@pytest.fixture
def fake_cq() -> Any:
    return _CQ


@pytest.fixture
def out_dir(tmp_path: Path) -> Path:
    return tmp_path / "cad"


# ---------- 1. shape 缺失/未知 ----------
def test_shape_required_and_unknown(fake_cq, out_dir):
    r = build_part("", {"outer_dia": 50}, str(out_dir), cq=fake_cq)
    assert r["ok"] is False and r["skill"] == "text2cad"
    assert r["error"] == "shape-required"

    r = build_part("wobbly_blob", {"outer_dia": 50}, str(out_dir), cq=fake_cq)
    assert r["ok"] is False and r["error"] == "unknown-shape"
    assert set(r["available"]) == set(SHAPES)      # 错误里回带可用族, 引导而非静默


# ---------- 2. 参数契约: 缺必填 / 非法 → 槽位填充, 不兜底 ----------
def test_missing_required_params_listed_not_guessed(fake_cq, out_dir):
    r = build_part("flange", {}, str(out_dir), cq=fake_cq)
    assert r["ok"] is False and r["error"] == "missing-params"
    assert set(r["missing"]) == {"outer_dia", "thickness", "bolt_circle_dia",
                                 "hole_count", "hole_dia"}   # bore_dia 可选不在列

    # 部分缺失也如实报 (不因其余齐全就放行)
    r = build_part("bushing", {"outer_dia": 20}, str(out_dir), cq=fake_cq)
    assert r["ok"] is False and set(r["missing"]) == {"inner_dia", "length"}


def test_invalid_params_rejected_with_reasons(fake_cq, out_dir):
    r = build_part("plate", {"length": -5, "width": 50, "thickness": 10},
                   str(out_dir), cq=fake_cq)
    assert r["ok"] is False and r["error"] == "invalid-params"
    assert "length" in r["invalid"]

    r = build_part("flange", {"outer_dia": 60, "thickness": 10,
                              "bolt_circle_dia": 48, "hole_count": 2,
                              "hole_dia": 6}, str(out_dir), cq=fake_cq)
    assert r["ok"] is False and "hole_count" in r["invalid"]   # 3 孔起, 2 孔拒收

    r = build_part("plate", {"length": "abc", "width": 50, "thickness": 10},
                   str(out_dir), cq=fake_cq)
    assert r["ok"] is False and "length" in r["invalid"]


def test_hole_count_int_coerced(fake_cq, out_dir):
    """hole_count 收字符串 "4" (Omni/JSON 常见) — 合法 coerced, 不属 invalid."""
    r = build_part("flange", {"outer_dia": 60, "thickness": 10,
                              "bolt_circle_dia": 48, "hole_count": "4",
                              "hole_dia": 6}, str(out_dir), cq=fake_cq)
    assert r["ok"] is True
    assert r["params"]["hole_count"] == 4


# ---------- 3. cadquery 不可用 → 诚实降级 ----------
def test_cadquery_unavailable_honest_mock(out_dir, monkeypatch):
    """sys.modules['cadquery']=None 模拟内核缺席 (开发机实况; 确定性不依赖装机):
    ok False + 显式 MOCK 标注 + 零落盘 — 绝不回退假几何 (离线铁律)."""
    monkeypatch.setitem(sys.modules, "cadquery", None)
    r = build_part("plate", {"length": 100, "width": 60, "thickness": 10},
                   str(out_dir))
    assert r["ok"] is False
    assert r["error"] == "cadquery-unavailable"
    assert r["_source"] == "MOCK:cadquery-unavailable"
    assert not out_dir.exists() or not any(out_dir.iterdir())


# ---------- 4. 注入替身 → 落盘 + 几何事实 + sha256 ----------
def test_plate_roundtrip_files_geometry_sha(fake_cq, out_dir):
    r = build_part("plate", {"length": 100, "width": 60, "thickness": 10},
                   str(out_dir), formats=("step", "stl"), cq=fake_cq)
    assert r["ok"] is True, r
    assert r["skill"] == "text2cad" and r["shape"] == "plate"
    assert r["iron_rule"] == "deterministic"
    assert r["_source"] == "services.text2cad"
    step = Path(r["files"]["step"])
    assert step.exists() and step.suffix == ".step"
    assert Path(r["files"]["stl"]).exists()
    geo = r["geometry"]
    assert geo["bbox_mm"] == [100.0, 60.0, 10.0]
    assert geo["volume_mm3"] == pytest.approx(60000.0)
    assert geo["volume_cm3"] == pytest.approx(60.0)
    # sha256_16 必须等于真实文件哈希 (可信指纹, 防假事实)
    assert r["sha256_16"] == hashlib.sha256(
        step.read_bytes()).hexdigest()[:16]


def test_flange_holes_cut_volume_consistent(fake_cq, out_dir):
    """法兰 = 圆柱 - 中心孔 - bolt 孔; 假替身下 volume = 外筒 - 内孔."""
    params = {"outer_dia": 60, "thickness": 10, "bore_dia": 20,
              "bolt_circle_dia": 48, "hole_count": 4, "hole_dia": 6}
    r = build_part("flange", params, str(out_dir), cq=fake_cq)
    assert r["ok"] is True, r
    geo = r["geometry"]
    assert geo["bbox_mm"] == [60.0, 60.0, 10.0]
    outer = math.pi * 30 ** 2 * 10
    bore = math.pi * 10 ** 2 * 10
    holes = 4 * math.pi * 3 ** 2 * 10
    assert geo["volume_mm3"] == pytest.approx(outer - bore - holes, rel=1e-6)


def test_step_only_format_when_requested(fake_cq, out_dir):
    r = build_part("bushing", {"outer_dia": 20, "inner_dia": 10, "length": 30},
                   str(out_dir), formats=("step",), cq=fake_cq)
    assert r["ok"] is True
    assert set(r["files"]) == {"step"}          # 不给的格式不落盘, 不虚报


# ---------- 5. SHAPES 规格表自洽 ----------
def test_shapes_spec_self_consistent():
    assert set(SHAPES) == {"flange", "l_bracket", "bushing", "plate", "pipe"}
    for sid, spec in SHAPES.items():
        assert spec.get("label"), f"{sid} 缺 label"
        assert spec.get("params") and isinstance(spec["params"], dict)
        for pname, pspec in spec["params"].items():
            assert pspec.get("type") in ("float", "int"), f"{sid}.{pname} type 缺失"
            assert isinstance(pspec.get("required"), bool)
            assert pspec.get("min", 0) < pspec.get("max", 1), f"{sid}.{pname} 量程反了"
            if pspec.get("unit"):
                assert pspec["unit"] == "mm"
        req = {k for k, v in spec["params"].items() if v["required"]}
        assert req, f"{sid} 无必填参数 — 无法定义槽位填充契约"


def test_build_part_result_json_serializable(fake_cq, out_dir):
    """端点/前端要直接 json.dumps — 契约要求结果可序列化 (禁 numpy/Path 裸漏)."""
    r = build_part("plate", {"length": 30, "width": 20, "thickness": 5},
                   str(out_dir), cq=fake_cq)
    assert r["ok"] is True
    assert json.loads(json.dumps(r, ensure_ascii=False))["shape"] == "plate"


def test_build_part_rejects_non_dict_params(fake_cq, out_dir):
    r = build_part("plate", None, str(out_dir), cq=fake_cq)
    assert r["ok"] is False and r["error"] == "missing-params"
    assert set(r["missing"]) == set(
        k for k, v in SHAPES["plate"]["params"].items() if v["required"])


# ---------- 6. 几何三重校验: 五族逐族 bbox/体积参数化期望 (Q8) ----------
def test_family_geometry_triple_flange(fake_cq, out_dir):
    """法兰 = 外筒 - 中心孔 - 均布螺栓孔 (孔位只改位置不改尺寸)."""
    params = {"outer_dia": 60, "thickness": 10, "bore_dia": 20,
              "bolt_circle_dia": 48, "hole_count": 4, "hole_dia": 6}
    r = build_part("flange", params, str(out_dir), cq=fake_cq)
    geo = r["geometry"]
    assert geo["bbox_mm"] == [60.0, 60.0, 10.0]
    outer = math.pi * 30 ** 2 * 10
    bore = math.pi * 10 ** 2 * 10
    holes = 4 * math.pi * 3 ** 2 * 10
    assert geo["volume_mm3"] == pytest.approx(outer - bore - holes, rel=1e-6)


def test_family_geometry_triple_l_bracket(fake_cq, out_dir):
    """L 支架 = 底板 + 立板 union (bbox 取各轴最大, 体积相加; 中心孔再减)."""
    r = build_part("l_bracket", {"leg_a": 80, "leg_b": 40, "width": 50,
                                 "thickness": 8}, str(out_dir), cq=fake_cq)
    geo = r["geometry"]
    assert geo["bbox_mm"] == [80.0, 50.0, 40.0]
    assert geo["volume_mm3"] == pytest.approx(80 * 50 * 8 + 8 * 50 * 40, rel=1e-6)

    r2 = build_part("l_bracket", {"leg_a": 80, "leg_b": 40, "width": 50,
                                  "thickness": 8, "hole_dia": 6},
                    str(out_dir), cq=fake_cq)
    assert r2["geometry"]["volume_mm3"] == pytest.approx(
        80 * 50 * 8 + 8 * 50 * 40 - math.pi * 3 ** 2 * 8, rel=1e-6)


def test_family_geometry_triple_bushing(fake_cq, out_dir):
    r = build_part("bushing", {"outer_dia": 20, "inner_dia": 10, "length": 30},
                   str(out_dir), cq=fake_cq)
    geo = r["geometry"]
    assert geo["bbox_mm"] == [20.0, 20.0, 30.0]
    assert geo["volume_mm3"] == pytest.approx(
        math.pi * 10 ** 2 * 30 - math.pi * 5 ** 2 * 30, rel=1e-6)


def test_family_geometry_triple_pipe(fake_cq, out_dir):
    r = build_part("pipe", {"outer_dia": 60, "wall": 5, "length": 70},
                   str(out_dir), cq=fake_cq)
    geo = r["geometry"]
    assert geo["bbox_mm"] == [60.0, 60.0, 70.0]
    assert geo["volume_mm3"] == pytest.approx(
        math.pi * 30 ** 2 * 70 - math.pi * 25 ** 2 * 70, rel=1e-6)


def test_family_geometry_triple_plate_with_hole(fake_cq, out_dir):
    r = build_part("plate", {"length": 100, "width": 60, "thickness": 10,
                             "hole_dia": 12}, str(out_dir), cq=fake_cq)
    geo = r["geometry"]
    assert geo["bbox_mm"] == [100.0, 60.0, 10.0]
    assert geo["volume_mm3"] == pytest.approx(60000 - math.pi * 6 ** 2 * 10,
                                              rel=1e-6)


# ---------- 7. BLOCKED 路径: 几何非法 → 显式失败, 零落盘 (Q8) ----------
def test_pipe_wall_exceeds_radius_blocked_no_files(fake_cq, out_dir):
    """壁厚 ≥ 外径一半 → 内径非正 → BLOCKED; 诚实报错, 不落任何文件。"""
    r = build_part("pipe", {"outer_dia": 60, "wall": 31, "length": 70},
                   str(out_dir), cq=fake_cq)
    assert r["ok"] is False and r["error"] == "geometry-failed"
    assert "wall" in r["detail"]
    assert not out_dir.exists() or not any(out_dir.iterdir())


def test_flange_hole_count_bounds_blocked(fake_cq, out_dir):
    """hole_count=2 (<3 均布起) 在参数层即 BLOCKED — 到不了几何生成。"""
    r = build_part("flange", {"outer_dia": 60, "thickness": 10,
                              "bolt_circle_dia": 48, "hole_count": 2,
                              "hole_dia": 6}, str(out_dir), cq=fake_cq)
    assert r["ok"] is False and r["error"] == "invalid-params"


# ---------- 8. 确定性: 同参数两次 → 同指纹 (可复访, 铁律) ----------
def test_same_params_same_sha_deterministic(fake_cq, out_dir):
    p = {"length": 40, "width": 30, "thickness": 6}
    r1 = build_part("plate", p, str(out_dir), cq=fake_cq)
    r2 = build_part("plate", p, str(out_dir), cq=fake_cq)
    assert r1["sha256_16"] == r2["sha256_16"]
    assert r1["iron_rule"] == "deterministic"
