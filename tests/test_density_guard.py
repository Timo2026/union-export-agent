"""test_density_guard.py — 密度权威表 + 引擎回落侦测契约 (缺陷: YG8 重量算小 81%).

2026-09-23 起: 引擎 get_material_density 对 yg8/440c/abs/pom 键 miss 时静默
回落 2.8。YG8 真实 14.5 g/cm³ → 回落后重量 = 13029.195×2.8/1e6 = 0.0365 kg,
真值应为 0.1889 kg, 差 5.18 倍 → 材料费严重低估。这是"静默错价":
geometry.density=2.8 看起来正常, 没人会怀疑。

本测试锁死:
  1. 权威表与引擎 DENSITY 表 14 键零分歧 (我们补的是引擎缺的)
  2. yg8/440c/abs/pom 回落被侦测并纠正, 体积不变
  3. 未收录材料 → density_verified=False (不猜, 交给上游)
  4. audit_geometry 只改密度/重量, 绝不动 B-rep 体积
"""
from __future__ import annotations

import pytest

from services import density_guard as dg


# ---------- 与引擎表一致性 ----------
@pytest.mark.parametrize("mat,eng", [
    ("45钢", 7.85), ("45#", 7.85), ("q235", 7.85), ("6061", 2.7), ("al6061", 2.7),
    ("7075", 2.81), ("304", 7.93), ("sus304", 7.93), ("316l", 7.98),
    ("sus316", 7.98), ("tc4", 4.43), ("钛合金", 4.43), ("h59", 8.5), ("黄铜", 8.5),
])
def test_authoritative_matches_engine(mat, eng):
    d, src = dg.resolve_density(mat)
    assert d == pytest.approx(eng), (mat, d, eng, src)
    assert src == "authoritative"


# ---------- 回落值侦测 ----------
@pytest.mark.parametrize("v", [2.8, "2.8", 2.8000000001])
def test_is_fallback_true(v):
    assert dg.is_fallback(v) is True


@pytest.mark.parametrize("v", [2.7, 1.04, 14.5, 7.85])
def test_is_fallback_false(v):
    assert dg.is_fallback(v) is False


def test_is_fallback_none_is_not_fallback():
    """None 表示引擎没给密度, 不是回落值 — 语义分开 (缺陷11)。"""
    assert dg.is_fallback(None) is False
    assert dg.is_fallback("abc") is False


def test_is_fallback_only_matches_2_8():
    """只有恰好 2.8 才算回落; 2.7/1.04/14.5 都是合法密度。"""
    assert dg.is_fallback(2.7) is False
    assert dg.is_fallback(14.5) is False


def test_is_fallback_only_matches_2_8():
    """只有恰好 2.8 才算回落; 2.7/1.04/14.5 都是合法密度。"""
    assert dg.is_fallback(2.7) is False
    assert dg.is_fallback(14.5) is False


# ---------- 引擎缺的 4 个键, 必须被纠正 (BOM 实际踩中) ----------
@pytest.mark.parametrize("mat,truth,engine_fb", [
    ("yg8", 14.50, 2.8), ("440c", 7.85, 2.8),
    ("abs", 1.04, 2.8), ("pom", 1.41, 2.8),
])
def test_missing_keys_are_corrected(mat, truth, engine_fb):
    d, src = dg.resolve_density(mat)
    assert d is not None, f"{mat} 未收录 → 不得信任引擎回落 {engine_fb}"
    assert d == pytest.approx(truth)
    # 与回落值差距 > 25% 才算高危 (abs/pom 方向相反: 引擎高估)
    assert abs(d - engine_fb) / truth > 0.25, "回落误差必须显著, 否则不值得纠正"


def test_bom_chinese_names_resolve():
    """BOM 规格列里的中文名也必须解析 (不能只认引擎 key)。"""
    assert dg.resolve_density("YG8钨合金")[0] == pytest.approx(14.5)
    assert dg.resolve_density("440C")[0] == pytest.approx(7.85)
    assert dg.resolve_density("POM 白色")[0] == pytest.approx(1.41)
    assert dg.resolve_density("301不锈钢含图纸")[0] == pytest.approx(7.93)


def test_unknown_material_returns_no_density():
    d, src = dg.resolve_density("ZZZ未来材料")
    assert d is None
    assert "未收录" in src


# ---------- audit_geometry: 只改密度/重量, 不动体积 ----------
VOL = 13029.195147661916   # 1010001-戳卡夹外壳 的真实 OCP B-rep 体积


def test_audit_corrects_weight_and_keeps_volume():
    """yg8 回落 → 重量 0.0365 纠正为 0.1889, 体积必须原样。"""
    out = dg.audit_geometry({"volume_mm3": VOL, "weight_kg": 0.0365, "density": 2.8}, "yg8")
    assert out["volume_mm3"] == pytest.approx(VOL), "B-rep 体积是事实, 不得改动"
    assert out["density"] == pytest.approx(14.5)
    assert out["density_corrected"] is True
    assert out["density_engine"] == 2.8, "必须留痕引擎原值"
    # audit_geometry 把重量保留到 9 位小数 (缺陷11: 微小件 2.68e-05 kg 不许抹零)
    assert out["weight_kg"] == pytest.approx(round(VOL * 14.5 / 1e6, 9))


def test_audit_keeps_matching_engine_density():
    """6061 引擎给 2.7 与权威一致 → 标记 verified, 不误伤。"""
    out = dg.audit_geometry({"volume_mm3": VOL, "weight_kg": 0.0352, "density": 2.7}, "6061")
    assert out["density_verified"] is True
    assert not out.get("density_corrected")
    assert out["density"] == pytest.approx(2.7)
    assert out["weight_kg"] == pytest.approx(0.0352)


def test_audit_disagreement_over_2pct():
    """非回落但偏差 >2% → 仍以权威为准并记录分歧。"""
    out = dg.audit_geometry({"volume_mm3": VOL, "density": 3.0}, "6061")  # 3.0 vs 2.7
    assert out["density_corrected"] is True
    assert out["density"] == pytest.approx(2.7)
    dis = out.get("density_disagreement")
    assert dis and dis["engine"] == 3.0 and dis["authoritative"] == 2.7


def test_audit_unknown_material_not_verified():
    """未收录 → 不猜密度, 显式标 density_verified=False 交给上游。"""
    out = dg.audit_geometry({"volume_mm3": VOL, "density": 2.8}, "ZZZ未来材料")
    assert out["density_verified"] is False
    assert "未收录" in (out.get("density_warning") or "")
    assert not out.get("density_corrected"), "没有权威值不得假装纠正"


def test_audit_survives_broken_input():
    """坏输入不得抛异常 (几何解析失败时调用方仍要拿到结构)。"""
    for g in ({}, None, {"volume_mm3": None}, {"volume_mm3": "abc"}, []):
        out = dg.audit_geometry(g if isinstance(g, dict) else {}, "6061")
        assert isinstance(out, dict)
    out = dg.audit_geometry({"volume_mm3": 1000, "density": 2.8}, "yg8")
    assert out["weight_kg"] == pytest.approx(1000 * 14.5 / 1e6)


# ---------- 覆盖报告 ----------
def test_coverage_report():
    rep = dg.coverage_report(["6061铝合金", "yg8", "ZZZ未来材料"])
    assert rep["n"] == 3 and rep["n_known"] == 2 and rep["n_missing"] == 1
    assert rep["missing"][0]["material"] == "ZZZ未来材料"
    assert all(x["density"] for x in rep["known"])


def test_coverage_report_empty():
    rep = dg.coverage_report([])
    assert rep["n"] == 0 and rep["n_known"] == 0 and rep["n_missing"] == 0
