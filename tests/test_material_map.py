"""test_material_map.py — 材料归一化的三分法契约 (exact / approx / unknown).

核心契约 (2026-09-23 缺陷9): 24/27 种 BOM 材料曾被引擎静默按默认料计价
(PEI 按 6061 的 200元/kg 出价)。本测试锁死不回归:
  exact   → 有 key, 无 approx_note
  approx  → 有 key, **必须**有 approx_note (报价单上可见)
  unknown → 无 key, 无价格, 上游留空进 HITL (绝不静默给价)
"""
from __future__ import annotations

import pytest

from services import material_map as mm


# ---------- exact ----------
@pytest.mark.parametrize("name,key", [
    ("6061铝合金", "6061"),
    ("304不锈钢", "304"),
    ("316L不锈钢", "316l"),
    ("ABS", "abs"),
    ("POM 白色", "pom"),
    ("YG8钨合金", "yg8"),
    ("440C", "440c"),
    ("黄铜", "黄铜"),
])
def test_exact_materials(name, key):
    r = mm.normalize(name)
    assert r["kind"] == mm.EXACT, r
    assert r["key"] == key, r
    assert not r.get("approx_note"), "exact 不得带近似标注"


# ---------- approx: 有价但必须可见 ----------
@pytest.mark.parametrize("name,key", [
    ("17-4PH", "304"),
    ("SKD11", "45钢"),
    ("40Cr13", "45钢"),
    ("301不锈钢", "304"),
    ("ABS PC", "abs"),
    ("POM 乙缩醛共聚物", "pom"),
])
def test_approx_materials_have_key_and_note(name, key):
    r = mm.normalize(name)
    assert r["kind"] == mm.APPROX, r
    assert r["key"] == key, r
    assert r.get("approx_note"), "近似计价必须带 approx_note, 否则调用方看不见"


def test_approx_note_names_the_substitution():
    """近似说明必须点明'用什么代替', 不能只说'近似'。"""
    r = mm.normalize("17-4PH")
    assert "304" in r["approx_note"], r
    r2 = mm.normalize("SKD11")
    assert "45钢" in r2["approx_note"], r2


# ---------- unknown: 拒绝静默计价 ----------
@pytest.mark.parametrize("name", [
    "PEI",                       # 引擎无项, 近似 6061 会低估 4 倍
    "焊接件",                     # 非纯切削件
    "玻璃含图纸",                 # CNC 不适用
    "组装件无需加工，仅组装喷漆",     # 无切削工时
    "组装件无需加工，仅焊接喷漆",
    "ZZZ完全不存在的材料",         # 拼错/新材料
    "",
])
def test_unknown_materials_get_no_key(name):
    r = mm.normalize(name)
    assert r["kind"] == mm.UNKNOWN, r
    assert r["key"] is None, "unknown 不得给出引擎 key"
    assert r.get("reason"), "unknown 必须说明原因"


def test_pei_explicitly_refused():
    """PEI 是高危近似, 必须显式拒绝 (而非悄悄按 6061 出价)。"""
    r = mm.normalize("PEI")
    assert r["kind"] == mm.UNKNOWN
    assert "PEI" in r["reason"], r


def test_unknown_reason_is_actionable():
    r = mm.normalize("焊接件")
    assert "焊接" in r["reason"] or "人工" in r["reason"], r


# ---------- 大小写不敏感 (BOM 表里 17-4ph/440c 混用) ----------
@pytest.mark.parametrize("name,key", [
    ("17-4ph", "304"),
    ("17-4PH", "304"),
    ("316l不锈钢", "316l"),
])
def test_case_insensitive_hit(name, key):
    r = mm.normalize(name)
    assert r["key"] == key, r
    assert r["kind"] in (mm.EXACT, mm.APPROX), r


# ---------- 已知高价材料不得落入低价近似 (PEEK/TU P 语义保留) ----------
def test_high_value_materials_flagged_for_hitl():
    """PEEK/TUP/PUR/陶瓷/硅胶 都按 6061 近似, note 必须点明需人工/HITL 介入。"""
    for n in ("PEEK", "颈椎聚醚醚酮 (PEEK)", "TUP", "PUR", "氧化铝陶瓷", "医用硅胶白色", "硅橡胶"):
        r = mm.normalize(n)
        if r["kind"] == mm.APPROX:
            note = r.get("approx_note") or ""
            assert any(w in note for w in ("人工", "核", "HITL")), \
                f"{n} 的近似未标注需人工核: {note}"


# ---------- 风险判定 ----------
def test_is_risky_approx_density_gap():
    assert mm.is_risky_approx(1.30, "6061") is True     # PEEK 1.30 vs 6061 2.70 → 52% 差
    assert mm.is_risky_approx(2.70, "6061") is False     # 完全一致
    assert mm.is_risky_approx(7.80, "304") is False      # 17-4PH 7.80 vs 304 7.93 → 2% 差
    assert mm.is_risky_approx(None, "6061") is False     # 无密度不判定
    assert mm.is_risky_approx(1.30, "不存在的key") is True  # 无参照 → 视为风险


# ---------- 审计报告 ----------
def test_unknown_report_lists_refusals():
    rep = mm.unknown_report(["6061铝合金", "PEI", "焊接件", "ZZZ"])
    assert rep["n_unknown"] == 3
    names = {u["material"] for u in rep["unknown"]}
    assert names == {"PEI", "焊接件", "ZZZ"}
    assert all(u.get("reason") for u in rep["unknown"]), "每项都要有原因"


def test_unknown_report_empty_when_all_known():
    rep = mm.unknown_report(["6061铝合金", "304不锈钢", "YG8钨合金"])
    assert rep["n_unknown"] == 0 and rep["unknown"] == []


# ---------- 全 BOM 材料族覆盖 (锁死 410 项那份 BOM 的 27 种) ----------
ALL_BOM_MATERIALS = [
    "6061铝合金", "ABS", "304不锈钢", "PEI", "17-4PH", "316L不锈钢", "SKD11",
    "POM 白色", "组装件无需加工，仅组装喷漆", "医用硅胶白色", "ABS PC", "焊接件",
    "POM 乙缩醛共聚物", "玻璃含图纸", "黄铜", "YG8钨合金", "TUP", "40Cr13",
    "PMMA", "PUR", "440C", "组装件无需加工，仅焊接喷漆", "氧化铝陶瓷", "301不锈钢",
    "颈椎聚醚醚酮 (PEEK)", "硅橡胶", "301不锈钢含图纸",
]


def test_every_bom_material_gets_a_verdict():
    """27 种材料无一漏判: 每种都必须有明确结论 (exact/approx/unknown)。"""
    for n in ALL_BOM_MATERIALS:
        r = mm.normalize(n)
        assert r["kind"] in (mm.EXACT, mm.APPROX, mm.UNKNOWN), (n, r)
        if r["kind"] == mm.UNKNOWN:
            assert r["key"] is None and r.get("reason"), (n, r)
        if r["kind"] == mm.APPROX:
            assert r["key"] and r.get("approx_note"), (n, r)


def test_bom_coverage_summary():
    n_exact = n_approx = n_unknown = 0
    for n in ALL_BOM_MATERIALS:
        k = mm.normalize(n)["kind"]
        if k == mm.EXACT: n_exact += 1
        elif k == mm.APPROX: n_approx += 1
        else: n_unknown += 1
    # 预期: 精确 8 种; 近似 13 种; 拒绝 6 种 (PEI/焊接件/玻璃/两种组装件/301含图纸)
    assert n_exact >= 8, (n_exact, n_approx, n_unknown)
    assert n_unknown >= 5, (n_exact, n_approx, n_unknown)
    assert n_exact + n_approx + n_unknown == len(ALL_BOM_MATERIALS)
