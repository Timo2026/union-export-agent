"""test_cad_text2step.py — /v1/cad/text2step + /v1/cad/shapes 端点契约 (Q7).

设计口径 (诚实优先):
  - 所有契约级结果 (missing-params/invalid-params/unknown-shape/cadquery-unavailable)
    一律 200 + ok:false + 结构化字段 — 前端要渲染 HITL 槽位填充/诚实降级, 不是吞错。
  - cadquery 缺席 (开发机) → MOCK:cadquery-unavailable 显式标注, 零落盘。
  - 注入 cadquery 替身 (sys.modules 标准注入缝) → 真落盘 STEP + 几何事实 + sha256_16。
  - name 参数走文件名白名单 (防路径穿越写穿 data/cad)。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from services import api_server
from services import text2cad
from services.api_server import app


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

    def Faces(self) -> list:
        return [None] * self._faces


class _WP:
    def __init__(self, solid: Any = None, plane: str = "XY") -> None:
        self._s = solid
        self._r = 0.0

    def val(self) -> _Solid:
        return self._s

    def box(self, l: float, w: float, h: float) -> "_WP":
        return _WP(_Solid(_BB(l, w, h), l * w * h))

    def circle(self, r: float) -> "_WP":
        self._r = r
        return self

    def center(self, x: float, y: float) -> "_WP":
        return self

    def translate(self, v: Any) -> "_WP":
        return self

    def extrude(self, h: float) -> "_WP":
        r = self._r
        return _WP(_Solid(_BB(2 * r, 2 * r, h), math.pi * r * r * h, faces=3))

    def union(self, other: Any) -> "_WP":
        a, b = self._s, (other._s if isinstance(other, _WP) else other)
        return _WP(_Solid(_BB(max(a._bb.xlen, b._bb.xlen),
                              max(a._bb.ylen, b._bb.ylen),
                              max(a._bb.zlen, b._bb.zlen)), a._vol + b._vol))

    def cut(self, other: Any) -> "_WP":
        a, b = self._s, (other._s if isinstance(other, _WP) else other)
        return _WP(_Solid(a._bb, a._vol - b._vol))


class _Exporters:
    @staticmethod
    def export(obj: Any, path: str) -> None:
        Path(path).write_text(f"FAKE-EXPORT {path}\n", encoding="utf-8")


class _CQ:
    Workplane = _WP
    exporters = _Exporters


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(text2cad, "DEFAULT_OUT_DIR", str(tmp_path / "cad"))
    return TestClient(app)


@pytest.fixture()
def fake_cq(monkeypatch):
    """sys.modules 注入 cadquery 替身 (端点不接 cq 参数, 走真实 import 路径)。"""
    monkeypatch.setitem(sys.modules, "cadquery", _CQ)
    return _CQ


# ---------- 规格表: 前端动态渲染参数表单的唯一权威 ----------
def test_shapes_endpoint_lists_five_families(client):
    r = client.get("/v1/cad/shapes")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert set(body["shapes"]) == {"flange", "l_bracket", "bushing", "plate", "pipe"}
    plate = body["shapes"]["plate"]
    assert plate["label"] and set(plate["params"]) == {
        "length", "width", "thickness", "hole_dia"}
    assert plate["params"]["length"]["required"] is True
    assert plate["params"]["hole_dia"]["required"] is False


# ---------- 成功路径 (注入替身 = 节点 occ 真内核的同构验证) ----------
def test_text2step_ok_with_fake_cq(client, fake_cq, tmp_path):
    r = client.post("/v1/cad/text2step", json={
        "shape": "plate", "params": {"length": 100, "width": 60, "thickness": 10},
        "formats": ["step", "stl"], "name": "demo-plate"})
    assert r.status_code == 200
    b = r.json()
    assert b["ok"] is True and b["skill"] == "text2cad"
    assert b["iron_rule"] == "deterministic"
    assert b["geometry"]["bbox_mm"] == [100.0, 60.0, 10.0]
    step = Path(b["files"]["step"])
    assert step.exists() and step.parent == tmp_path / "cad"
    assert step.name == "demo-plate.step"
    import hashlib
    assert b["sha256_16"] == hashlib.sha256(step.read_bytes()).hexdigest()[:16]


def test_text2step_step_only(client, fake_cq):
    r = client.post("/v1/cad/text2step", json={
        "shape": "bushing",
        "params": {"outer_dia": 20, "inner_dia": 10, "length": 30},
        "formats": ["step"]})
    b = r.json()
    assert b["ok"] is True and set(b["files"]) == {"step"}


# ---------- 诚实失败: HITL 槽位而不是兜底 ----------
def test_text2step_missing_params_returns_slots(client, fake_cq):
    r = client.post("/v1/cad/text2step", json={"shape": "flange", "params": {}})
    assert r.status_code == 200
    b = r.json()
    assert b["ok"] is False and b["error"] == "missing-params"
    assert set(b["missing"]) == {"outer_dia", "thickness", "bolt_circle_dia",
                                 "hole_count", "hole_dia"}


def test_text2step_invalid_params_returns_reasons(client, fake_cq):
    r = client.post("/v1/cad/text2step", json={
        "shape": "plate", "params": {"length": "abc", "width": 50, "thickness": 10}})
    assert r.status_code == 200
    b = r.json()
    assert b["ok"] is False and b["error"] == "invalid-params"
    assert "length" in b["invalid"]


def test_text2step_unknown_shape(client, fake_cq):
    r = client.post("/v1/cad/text2step", json={"shape": "wobbly_blob", "params": {}})
    b = r.json()
    assert b["ok"] is False and b["error"] == "unknown-shape"
    assert set(b["available"]) == {"flange", "l_bracket", "bushing", "plate", "pipe"}


def test_text2step_shape_required(client, fake_cq):
    r = client.post("/v1/cad/text2step", json={"params": {}})
    b = r.json()
    assert b["ok"] is False and b["error"] == "shape-required"


# ---------- cadquery 缺席 → 显式 MOCK, 零落盘 ----------
def test_text2step_cadquery_unavailable_honest_mock(client, monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "cadquery", None)
    r = client.post("/v1/cad/text2step", json={
        "shape": "plate", "params": {"length": 100, "width": 60, "thickness": 10},
        "name": "should-not-land"})
    b = r.json()
    assert b["ok"] is False and b["error"] == "cadquery-unavailable"
    assert b["_source"] == "MOCK:cadquery-unavailable"
    assert not (tmp_path / "cad").exists() or not any((tmp_path / "cad").iterdir())


# ---------- 文件名安全: name 禁路径穿越 ----------
def test_text2step_rejects_unsafe_name(client, fake_cq):
    r = client.post("/v1/cad/text2step", json={
        "shape": "plate", "params": {"length": 50, "width": 50, "thickness": 5},
        "name": "../../evil"})
    b = r.json()
    assert b["ok"] is False and b["error"] == "invalid-name"


# ---------- /v1/cad/mesh — text2cad 产物 3D 网格预览 (three.js) ----------
_MESH_OK = {
    "ok": True, "vertex_count": 8, "tri_count": 12,
    "positions_b64": "AAAA", "indices_b64": "AAAA",
    "bbox": {"min": [0, 0, 0], "max": [1, 1, 1]}, "deflection": 0.1,
    "sha256_16": "0123456789abcdef",
}


def test_cad_mesh_ok(client, monkeypatch):
    """产物 STEP 在盘 + 网格构建成功 → 透传 mesh JSON (three.js 预览数据源)。"""
    import services.step_mesh as sm
    cad_dir = Path(text2cad.DEFAULT_OUT_DIR)
    cad_dir.mkdir(parents=True, exist_ok=True)
    (cad_dir / "mesh-demo.step").write_text("ISO-10303-21;\n", encoding="utf-8")
    seen = {}

    def spy(p: str):
        seen["path"] = p
        return dict(_MESH_OK)

    monkeypatch.setattr(sm, "get_or_build_mesh", spy)
    r = client.get("/v1/cad/mesh", params={"name": "mesh-demo"})
    assert r.status_code == 200
    b = r.json()
    assert b["ok"] is True and b["vertex_count"] == 8 and b["tri_count"] == 12
    assert b["sha256_16"] == "0123456789abcdef"
    assert seen["path"] == str(cad_dir / "mesh-demo.step")


def test_cad_mesh_not_found_404(client):
    r = client.get("/v1/cad/mesh", params={"name": "nope"})
    assert r.status_code == 404


def test_cad_mesh_build_failure_400(client, monkeypatch):
    """OCP 解析失败 → 400 + reason (前端回退几何事实卡, 不冒充预览)。"""
    import services.step_mesh as sm
    cad_dir = Path(text2cad.DEFAULT_OUT_DIR)
    cad_dir.mkdir(parents=True, exist_ok=True)
    (cad_dir / "bad.step").write_text("garbage", encoding="utf-8")
    monkeypatch.setattr(sm, "get_or_build_mesh",
                        lambda p: {"ok": False, "reason": "ocp-parse-failed"})
    r = client.get("/v1/cad/mesh", params={"name": "bad"})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["ok"] is False and detail["reason"] == "ocp-parse-failed"


def test_cad_mesh_rejects_unsafe_name(client):
    """name 白名单同 text2step — 禁路径穿越读穿 data/cad。"""
    r = client.get("/v1/cad/mesh", params={"name": "../../etc/passwd"})
    b = r.json()
    assert b["ok"] is False and b["error"] == "invalid-name"


# ---------- /v1/cad/file — 产物下载 (STEP/STL, 交付闭环) ----------
def test_cad_file_download_ok(client):
    cad_dir = Path(text2cad.DEFAULT_OUT_DIR)
    cad_dir.mkdir(parents=True, exist_ok=True)
    (cad_dir / "dl.step").write_text("ISO-10303-21;FAKE;", encoding="utf-8")
    r = client.get("/v1/cad/file", params={"name": "dl", "fmt": "step"})
    assert r.status_code == 200
    assert r.text == "ISO-10303-21;FAKE;"


def test_cad_file_download_stl(client):
    cad_dir = Path(text2cad.DEFAULT_OUT_DIR)
    cad_dir.mkdir(parents=True, exist_ok=True)
    (cad_dir / "dl.stl").write_text("solid fake", encoding="utf-8")
    r = client.get("/v1/cad/file", params={"name": "dl", "fmt": "stl"})
    assert r.status_code == 200 and r.text == "solid fake"


def test_cad_file_rejects_unsafe_name(client):
    r = client.get("/v1/cad/file", params={"name": "../secret", "fmt": "step"})
    assert r.json()["error"] == "invalid-name"


def test_cad_file_unsupported_fmt(client):
    r = client.get("/v1/cad/file", params={"name": "dl", "fmt": "exe"})
    b = r.json()
    assert b["ok"] is False and b["error"] == "unsupported-format"
    assert b["supported"] == ["step", "stl"]


def test_cad_file_not_found_404(client):
    r = client.get("/v1/cad/file", params={"name": "nope", "fmt": "step"})
    assert r.status_code == 404
