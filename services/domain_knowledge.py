"""domain_knowledge.py — 策展领域知识层 (材料 / DFM 几何规则 / 工艺路由).

来源 (Item6 策展): 从 ~/Videos/skill/skill 源库蒸馏**事实性领域知识**
  - 304-stainless-deep-knowledge / 6061-aluminum-deep-knowledge
  - alloy-steel-material-knowledge / aluminum-7075-knowledge
  - stainless-steel-316-knowledge / titanium-alloy-ti6al4v-knowledge
  - carbon-steel-45-knowledge / copper-alloy-brass-knowledge
  - dfm-analysis / anodizing-knowledge / heat-treatment-quote / cnc-quote-*

铁律 (P0-B.4 脱敏 + 数据本地):
  - 只蒸馏事实知识, **不复制外部运行时**, 不引用作者本地路径 (/home/<user>/...)
  - **不写价格权威字段** (unit_price/final_price) — calc_quote / CalculationEngine 仍唯一权威
  - 100% 确定性离线; 与 services.fleet_v4.calculation.MATERIAL_DB 对 4 种共有材料数值一致
  - 知识层只供选型/DFM/工艺**建议** (evidence), 数字裁决仍归引擎

属性单位: density g/cm³; yield/tensile MPa; elongation %; hardness HB; temp_limit °C; price_kg 仅 cost_tier 参考非报价。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────────
# 材料知识 (9 种; 与 guardrails._VALID_MATERIALS + MATERIAL_DB 对齐)
# machinability/corrosion/weldability: excellent|good|moderate|low|poor
# cost_tier: lowest|low|mid|mid_high|high|very_high
# ─────────────────────────────────────────────────────────────
MATERIAL_KNOWLEDGE: Dict[str, Dict[str, Any]] = {
    "6061": {
        "name": "6061铝合金", "category": "aluminum", "standard": "GB/T 3190 / ASTM B209",
        "density_g_cm3": 2.70, "yield_mpa": 275, "tensile_mpa": 390,
        "elongation_pct": 8, "hardness_hb": 95, "temp_limit_c": 150,
        "anodizing_ok": True, "heat_treatable": True, "magnetic": False,
        "machinability": "excellent", "corrosion": "good", "weldability": "good",
        "cost_tier": "mid", "price_kg_ref": 25,
        "confusions": [
            "6061-T6 (热处理态, 屈服275) vs 6061-O (退火态, 屈服~145) 强度差异大, 报价/选材须确认 temper",
        ],
        "alternates": ["7075 (强度+75%但不可阳极氧化)", "5052 (钣金/深冲, 强度略低耐蚀更好)"],
        "process_notes": "可阳极氧化 (本色/黑色); 切削性优, 高速加工; 薄壁易变形需夹持补偿",
    },
    "7075": {
        "name": "7075铝合金", "category": "aluminum", "standard": "GB/T 3190 / ASTM B209",
        "density_g_cm3": 2.81, "yield_mpa": 503, "tensile_mpa": 572,
        "elongation_pct": 11, "hardness_hb": 150, "temp_limit_c": 120,
        "anodizing_ok": False, "heat_treatable": True, "magnetic": False,
        "machinability": "good", "corrosion": "moderate", "weldability": "poor",
        "cost_tier": "high", "price_kg_ref": 45,
        "confusions": [
            "7075 含锌, **不可常规阳极氧化**; 表面用喷涂/导电氧化 (化学氧化)",
            "7075 焊接性差 (T6 态易裂纹), 承力件优先整体加工而非焊接",
        ],
        "alternates": ["6061 (需阳极氧化外观/焊接)", "TC4 (更高强度或耐温)"],
        "process_notes": "航空承力件; 应力腐蚀敏感, 避免长期拉应力+腐蚀环境; 切削性好于钢",
    },
    "304": {
        "name": "304不锈钢", "category": "stainless", "standard": "GB/T 1220 / ASTM A240",
        "density_g_cm3": 7.93, "yield_mpa": 205, "tensile_mpa": 515,
        "elongation_pct": 40, "hardness_hb": 201, "temp_limit_c": 870,
        "anodizing_ok": False, "heat_treatable": False, "magnetic": False,
        "machinability": "low", "corrosion": "good", "weldability": "good",
        "cost_tier": "mid_high", "price_kg_ref": 35,
        "confusions": [
            "201/202 高锰低镍, 耐蚀明显低于 304, **不可仅凭'不锈钢'混用**, 须核对牌号",
            "304 奥氏体, **不可热处理强化**; 切削速度比碳钢低 30-50%, 需不锈钢专用刀具",
            "304 冷加工会硬化 (加工硬化), 深冲/切削须留余量",
        ],
        "alternates": ["316L (含Mo, 耐氯离子/海洋环境更好)", "430 (铁素体, 成本敏感无焊接)"],
        "process_notes": "通用耐蚀件; 焊接后建议钝化; 不可阳极; 抛光/拉丝/PVD 适用",
    },
    "316L": {
        "name": "316L不锈钢", "category": "stainless", "standard": "GB/T 1220 / ASTM A240",
        "density_g_cm3": 7.98, "yield_mpa": 170, "tensile_mpa": 485,
        "elongation_pct": 40, "hardness_hb": 150, "temp_limit_c": 870,
        "anodizing_ok": False, "heat_treatable": False, "magnetic": False,
        "machinability": "low", "corrosion": "excellent", "weldability": "excellent",
        "cost_tier": "high", "price_kg_ref": 45,
        "confusions": [
            "316 vs 316L: L 为低碳 (C≤0.03%), 抗晶间腐蚀, **焊接件优先 316L**",
            "316L 含 Mo 2-3%, 耐氯离子/点蚀优于 304, 海洋/医疗/化工首选",
            "屈服 (170) 略低于 304 (205), 但耐蚀显著更好; 不可仅按强度选材",
        ],
        "alternates": ["304 (无氯离子环境, 成本敏感)", "双相钢2205 (更高强度+耐蚀)"],
        "process_notes": "医疗/食品/海洋; 不可热处理强化; 切削性差需低速专用刀具; 不可阳极",
    },
    "TC4": {
        "name": "TC4钛合金 (Ti-6Al-4V)", "category": "titanium", "standard": "GB/T 3620 / ASTM B265 Grade 5",
        "density_g_cm3": 4.43, "yield_mpa": 830, "tensile_mpa": 950,
        "elongation_pct": 14, "hardness_hb": 320, "temp_limit_c": 400,
        "anodizing_ok": False, "heat_treatable": True, "magnetic": False,
        "machinability": "poor", "corrosion": "excellent", "weldability": "moderate",
        "cost_tier": "very_high", "price_kg_ref": 250,
        "confusions": [
            "TC4 (Ti-6Al-4V, α+β) **≠ 纯钛 TA1/TA2**, 强度更高可热处理; 不可按纯钛报价",
            "钛导热差 (~6.7 W/mK), 切削热集中刀尖, 易粘刀/加工硬化; 需大前角+高压冷却+低速",
            "比重 4.43 (钢的 56%), 减重首选; 但成本/加工难度远高于铝",
        ],
        "alternates": ["7075铝 (减重且成本敏感)", "316L (耐蚀但需更高强度时升级TC4)"],
        "process_notes": "航空/医疗植入; 可固溶+时效强化; 磨削/EDM 适合硬态; 避免卤素切削液 (应力腐蚀)",
    },
    "45钢": {
        "name": "45钢 (优质碳素结构钢 C45)", "category": "carbon_steel", "standard": "GB/T 699",
        "density_g_cm3": 7.85, "yield_mpa": 355, "tensile_mpa": 600,
        "elongation_pct": 16, "hardness_hb": 229, "temp_limit_c": 400,
        "anodizing_ok": False, "heat_treatable": True, "magnetic": True,
        "machinability": "good", "corrosion": "poor", "weldability": "moderate",
        "cost_tier": "low", "price_kg_ref": 7,
        "confusions": [
            "45钢 (碳素钢 GB/T 699) **≠ 40Cr (合金钢 GB/T 3077)**; 40Cr 淬透性/回火稳定性更好, 不可仅按强度等级互替",
            "调质 (淬火+高温回火) 后综合力学性能最佳; 热处理成本约占总成本 15-25%",
            "焊接性中等 (含碳量 0.45%), 厚件/拘束大需预热防裂",
            "易锈蚀, 须表面处理 (发黑/镀锌/喷涂)",
        ],
        "alternates": ["40Cr (交变载荷/更高淬透性)", "Q235 (焊接结构件, 无需热处理)"],
        "process_notes": "轴/齿轮/连接件; 可调质/表面淬火; 切削性好; 焊接需预热; 须防锈表面处理",
    },
    "Q235": {
        "name": "Q235碳素结构钢", "category": "carbon_steel", "standard": "GB/T 700",
        "density_g_cm3": 7.85, "yield_mpa": 235, "tensile_mpa": 400,
        "elongation_pct": 26, "hardness_hb": 120, "temp_limit_c": 400,
        "anodizing_ok": False, "heat_treatable": False, "magnetic": True,
        "machinability": "good", "corrosion": "poor", "weldability": "excellent",
        "cost_tier": "lowest", "price_kg_ref": 5,
        "confusions": [
            "Q235 低碳 (C≤0.22%), **不可淬火强化**; ≠ 45钢, 不可按强度互替",
            "焊接性优, 常用焊接结构件/钣金; 屈服 235MPa (Q+屈服值命名)",
            "易锈蚀, 须表面处理 (镀锌/喷涂/发黑)",
        ],
        "alternates": ["45钢 (需强度+热处理)", "Q345 (低合金高强度结构钢)"],
        "process_notes": "结构件/钣金/焊接件; 切削性好; 不可热处理强化; 须防锈表面处理",
    },
    "黄铜": {
        "name": "黄铜 (H62/H65 铜锌合金)", "category": "copper_alloy", "standard": "GB/T 5231",
        "density_g_cm3": 8.50, "yield_mpa": 275, "tensile_mpa": 410,
        "elongation_pct": 30, "hardness_hb": 100, "temp_limit_c": 300,
        "anodizing_ok": False, "heat_treatable": False, "magnetic": False,
        "machinability": "excellent", "corrosion": "good", "weldability": "moderate",
        "cost_tier": "mid_high", "price_kg_ref": 55,
        "confusions": [
            "黄铜 (铜锌合金 H62/H65) **≠ 紫铜 (纯铜 T2)**; 紫铜导电导热更好但更软更贵",
            "易切削 (含铅黄铜 HPb59-1 更优), 适合复杂小件/导电/装饰件",
            "不可热处理强化; 应力腐蚀开裂敏感 (季裂), 冷加工件需去应力退火",
        ],
        "alternates": ["紫铜T2 (纯导电/导热)", "磷青铜 (弹性/耐磨导电件)"],
        "process_notes": "导电/装饰/阀件; 易切削高速加工; 抛光/电镀/钝化适用; 不可阳极",
    },
    "carbon_steel": {
        "name": "碳钢 (通用)", "category": "carbon_steel", "standard": "GB/T 700 / GB/T 699",
        "density_g_cm3": 7.85, "yield_mpa": 235, "tensile_mpa": 400,
        "elongation_pct": 22, "hardness_hb": 131, "temp_limit_c": 400,
        "anodizing_ok": False, "heat_treatable": True, "magnetic": True,
        "machinability": "good", "corrosion": "poor", "weldability": "good",
        "cost_tier": "lowest", "price_kg_ref": 8,
        "confusions": ["通用碳钢条目 (与 MATERIAL_DB 一致); 具体牌号见 Q235/45钢"],
        "alternates": ["Q235 (焊接结构)", "45钢 (强度+热处理)"],
        "process_notes": "通用结构/机械件; 须防锈表面处理",
    },
}

# 类别 → 阳极氧化兼容性 (process-knowledge 用)
ANODIZING_CATEGORIES = {"aluminum"}
# 类别 → 可热处理强化 (奥氏体不锈钢/黄铜/低碳钢不可)
HEAT_TREATABLE_CATEGORIES = {"aluminum", "titanium", "carbon_steel", "alloy_steel"}


def material_category(material: str) -> str:
    m = MATERIAL_KNOWLEDGE.get(material)
    return m.get("category", "unknown") if m else "unknown"


def lookup_material(material: str) -> Optional[Dict[str, Any]]:
    """精确/别名查材料知识; 未收录返 None (诚实, 不假造)."""
    if not material:
        return None
    key = material.strip()
    if key in MATERIAL_KNOWLEDGE:
        return MATERIAL_KNOWLEDGE[key]
    low = key.lower()
    alias = {
        "sus304": "304", "0cr18ni9": "304", "304ss": "304",
        "sus316l": "316L", "316l": "316L", "00cr17ni14mo2": "316L",
        "ti-6al-4v": "TC4", "ti6al4v": "TC4", "tc4": "TC4", "grade5": "TC4",
        "c45": "45钢", "45#": "45钢", "45号钢": "45钢",
        "q235": "Q235", "a3钢": "Q235",
        "h62": "黄铜", "h65": "黄铜", "brass": "黄铜", "hp b59-1": "黄铜",
        "6061-t6": "6061", "6061铝": "6061", "7075铝": "7075",
    }
    return MATERIAL_KNOWLEDGE.get(alias.get(low, ""))


# ─────────────────────────────────────────────────────────────
# DFM 几何可制造性规则 (蒸馏自 dfm-analysis)
# 补充 check_dfm/dfm-conflict (仅材料×表面冲突); 本层是**几何**规则
# severity: violation (BLOCKED级) | warning (HITL级)
# ─────────────────────────────────────────────────────────────
# 最小壁厚 (mm) 按材料类别 — 低于此为 violation
THIN_WALL_MIN_MM: Dict[str, float] = {
    "aluminum": 1.5, "carbon_steel": 3.0, "alloy_steel": 3.0,
    "stainless": 3.0, "titanium": 4.0, "copper_alloy": 1.5, "unknown": 2.0,
}
# 孔深径比 depth/diameter
DEEP_HOLE_RATIO_WARN = 5.0      # > 5 warning
DEEP_HOLE_RATIO_RISK = 8.0      # > 8 violation (高风险)
# 内圆角半径 (mm)
INNER_RADIUS_WARN_MM = 1.0      # < 1.0 warning (刀具可达性)
# 紧公差 (mm)
TIGHT_TOLERANCE_WARN_MM = 0.02  # <= ±0.02 warning (需磨削/慢走丝)

DFM_RULES: Dict[str, Any] = {
    "thin_wall_min_mm": dict(THIN_WALL_MIN_MM),
    "deep_hole_ratio_warn": DEEP_HOLE_RATIO_WARN,
    "deep_hole_ratio_risk": DEEP_HOLE_RATIO_RISK,
    "inner_radius_warn_mm": INNER_RADIUS_WARN_MM,
    "tight_tolerance_warn_mm": TIGHT_TOLERANCE_WARN_MM,
    "surface_treatment_reminders": [
        "阳极/电镀前需遮蔽 (masking) 配合面/螺纹孔",
        "镀层/阳极有厚度, 配合尺寸需预留补偿 (阳极 ~5-25µm, 电镀 ~5-20µm)",
        "热处理后精加工面留磨削余量 (变形补偿)",
        "表面处理件需检验外观/膜厚/附着力",
    ],
}


def check_dfm_geometry(material: str = "", wall_thickness_mm: Optional[float] = None,
                       hole_depth_mm: Optional[float] = None,
                       hole_dia_mm: Optional[float] = None,
                       inner_radius_mm: Optional[float] = None,
                       tolerance_mm: Optional[float] = None,
                       surface: str = "") -> Dict[str, Any]:
    """确定性几何 DFM 检查 → violations/warnings/passes + 缺失字段.

    只依据已知输入判定; 缺失字段进 missing (提示补全), 不假造。
    """
    violations: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    passes: List[str] = []
    missing: List[str] = []
    cat = material_category(material) if material else "unknown"

    # 1. 薄壁
    if wall_thickness_mm is None:
        if material:
            missing.append("wall_thickness_mm")
    else:
        min_w = THIN_WALL_MIN_MM.get(cat, THIN_WALL_MIN_MM["unknown"])
        if wall_thickness_mm < min_w:
            violations.append({
                "rule": "thin_wall", "severity": "violation",
                "msg": f"壁厚 {wall_thickness_mm}mm < {cat or material} 最小 {min_w}mm",
                "value": wall_thickness_mm, "threshold": min_w})
        else:
            passes.append(f"thin_wall ok (≥{min_w}mm)")

    # 2. 深孔 (深径比)
    if hole_depth_mm is not None and hole_dia_mm not in (None, 0):
        ratio = hole_depth_mm / hole_dia_mm
        if ratio > DEEP_HOLE_RATIO_RISK:
            violations.append({
                "rule": "deep_hole", "severity": "violation",
                "msg": f"孔深径比 {ratio:.1f} > {DEEP_HOLE_RATIO_RISK} (高风险, 需枪钻/EDM/分段)",
                "value": round(ratio, 2), "threshold": DEEP_HOLE_RATIO_RISK})
        elif ratio > DEEP_HOLE_RATIO_WARN:
            warnings.append({
                "rule": "deep_hole", "severity": "warning",
                "msg": f"孔深径比 {ratio:.1f} > {DEEP_HOLE_RATIO_WARN} (排屑/让刀风险)",
                "value": round(ratio, 2), "threshold": DEEP_HOLE_RATIO_WARN})
        else:
            passes.append(f"deep_hole ok (ratio {ratio:.1f})")
    elif hole_depth_mm is not None or hole_dia_mm is not None:
        missing.append("hole_depth_mm+hole_dia_mm (需同时提供算深径比)")

    # 3. 内圆角
    if inner_radius_mm is None:
        pass  # 可选, 不强制 missing
    elif inner_radius_mm < INNER_RADIUS_WARN_MM:
        warnings.append({
            "rule": "inner_radius", "severity": "warning",
            "msg": f"内圆角 R{inner_radius_mm}mm < R{INNER_RADIUS_WARN_MM}mm (刀具可达性/应力集中)",
            "value": inner_radius_mm, "threshold": INNER_RADIUS_WARN_MM})
    else:
        passes.append(f"inner_radius ok (≥R{INNER_RADIUS_WARN_MM}mm)")

    # 4. 紧公差
    if tolerance_mm is None:
        pass
    elif abs(tolerance_mm) <= TIGHT_TOLERANCE_WARN_MM:
        warnings.append({
            "rule": "tight_tolerance", "severity": "warning",
            "msg": f"公差 ±{abs(tolerance_mm)}mm ≤ ±{TIGHT_TOLERANCE_WARN_MM}mm (需磨削/慢走丝, 成本上升)",
            "value": abs(tolerance_mm), "threshold": TIGHT_TOLERANCE_WARN_MM})
    else:
        passes.append("tolerance ok (常规加工可达)")

    # 5. 表面处理提醒 (有 surface 时附加)
    surface_reminders: List[str] = []
    if surface and surface != "none":
        surface_reminders = list(DFM_RULES["surface_treatment_reminders"])

    return {
        "violations": violations, "warnings": warnings, "passes": passes,
        "missing": missing, "surface_reminders": surface_reminders,
        "dfm_valid": not violations,
        "risk_level": "blocked" if violations else ("hitl" if warnings else "pass"),
        "material_category": cat,
    }


# ─────────────────────────────────────────────────────────────
# 工艺知识 (蒸馏自 cnc-quote-*/anodizing-knowledge/heat-treatment-quote/laser-cutting/edm/grinding)
# 工艺路由 + 参数 + 材料兼容
# ─────────────────────────────────────────────────────────────
PROCESS_KNOWLEDGE: Dict[str, Dict[str, Any]] = {
    "cnc_milling": {
        "name": "CNC铣削", "category": "subtractive",
        "applicable_materials": ["6061", "7075", "304", "316L", "TC4", "45钢", "Q235", "黄铜", "carbon_steel"],
        "applicable_geometry": ["prismatic", "complex_3d", "pockets", "slots"],
        "params": {"aluminum_speed_rel": 1.0, "steel_speed_rel": 0.5, "stainless_speed_rel": 0.35,
                   "titanium_speed_rel": 0.25, "brass_speed_rel": 1.2},
        "notes": "通用减材; 不锈钢/钛需低速+专用刀具+充分冷却; 黄铜高速易切削",
        "cost_tier": "mid",
    },
    "cnc_turning": {
        "name": "CNC车削", "category": "subtractive",
        "applicable_materials": ["6061", "7075", "304", "316L", "TC4", "45钢", "Q235", "黄铜", "carbon_steel"],
        "applicable_geometry": ["rotational", "shaft", "bushing", "flange"],
        "params": {"aluminum_speed_rel": 1.0, "steel_speed_rel": 0.55, "stainless_speed_rel": 0.4, "titanium_speed_rel": 0.3},
        "notes": "回转体零件首选; 长径比>5 需跟刀架/中心架防让刀",
        "cost_tier": "mid",
    },
    "laser_cutting": {
        "name": "激光切割", "category": "subtractive",
        "applicable_materials": ["6061", "304", "316L", "45钢", "Q235", "黄铜", "carbon_steel"],
        "applicable_geometry": ["sheet", "2d_profile", "thin_wall"],
        "params": {"max_thickness_steel_mm": 20, "max_thickness_aluminum_mm": 16, "max_thickness_brass_mm": 8},
        "notes": "钣金/2D轮廓; 高反材料 (铝/黄铜/紫铜) 需光纤激光器防反射损伤; 厚板断面粗糙度上升",
        "cost_tier": "low",
        "exclude_materials": ["TC4"],
    },
    "edm_wire_cut": {
        "name": "慢走丝线切割 (WEDM)", "category": "subtractive",
        "applicable_materials": ["304", "316L", "TC4", "45钢", "Q235", "黄铜", "carbon_steel", "6061", "7075"],
        "applicable_geometry": ["through_profile", "tight_tolerance", "hard_material", "sharp_inner_corner"],
        "params": {"tolerance_mm": 0.005, "surface_roughness_ra": 0.8},
        "notes": "导电材料均可; 硬态/淬火件/紧公差/尖内角首选; 无切削力不变形; 慢 (成本高)",
        "cost_tier": "high",
    },
    "grinding": {
        "name": "磨削", "category": "finishing",
        "applicable_materials": ["304", "316L", "TC4", "45钢", "Q235", "carbon_steel"],
        "applicable_geometry": ["flat_surface", "cylindrical", "tight_tolerance"],
        "params": {"tolerance_mm": 0.005, "surface_roughness_ra": 0.4},
        "notes": "淬硬件/紧公差/高光洁度精加工; 热处理后必工序; 铝/铜软材料易堵塞砂轮慎用",
        "cost_tier": "high",
        "exclude_materials": ["6061", "7075", "黄铜"],
    },
    "heat_treatment": {
        "name": "热处理 (调质/淬火/时效)", "category": "thermal",
        "applicable_materials": ["45钢", "TC4", "6061", "7075", "carbon_steel"],
        "applicable_geometry": ["any"],
        "params": {"45钢_quench_temp_c": 840, "temper_temp_c": 600, "tc4_solution_temp_c": 950,
                   "6061_solution_temp_c": 530, "aging_temp_c": 175,
                   "cost_pct_of_total": "15-25%"},
        "notes": "强化/改善综合力学性能; 奥氏体不锈钢(304/316L)/黄铜/Q235低碳钢**不可热处理强化**; 热处理后变形需留磨削余量; 成本约占 15-25%",
        "cost_tier": "mid_high",
        "exclude_materials": ["304", "316L", "Q235", "黄铜"],
    },
    "anodizing": {
        "name": "阳极氧化", "category": "surface",
        "applicable_materials": ["6061"],
        "applicable_geometry": ["any_aluminum"],
        "params": {"film_thickness_um": "5-25", "color": ["本色", "黑色", "彩色"], "voltage": 18},
        "notes": "**仅铝合金且优先 6061**; 7075 含锌常规阳极效果差/易发黑不均, 改用喷涂/导电氧化; 需遮蔽配合面; 膜厚需尺寸补偿",
        "cost_tier": "mid",
        "exclude_materials": ["7075", "304", "316L", "TC4", "45钢", "Q235", "黄铜", "carbon_steel"],
    },
    "electroplating": {
        "name": "电镀 (镀锌/镀镍/镀铬)", "category": "surface",
        "applicable_materials": ["45钢", "Q235", "黄铜", "carbon_steel", "304", "316L"],
        "applicable_geometry": ["any"],
        "params": {"film_thickness_um": "5-20", "zinc_for": "碳钢防锈", "nickel_for": "耐蚀装饰"},
        "notes": "碳钢防锈首选 (镀锌); 需前处理 (除油/酸洗); 氢脆敏感高强钢镀后去氢; 配合面遮蔽",
        "cost_tier": "mid",
    },
    "spray": {
        "name": "喷涂", "category": "surface",
        "applicable_materials": ["6061", "7075", "304", "316L", "TC4", "45钢", "Q235", "黄铜", "carbon_steel"],
        "applicable_geometry": ["any"],
        "params": {"film_thickness_um": "60-120"},
        "notes": "通用外观/防护; 7075 不可阳极时的表面替代方案; 需喷砂/底漆前处理",
        "cost_tier": "low",
    },
    "pvd": {
        "name": "PVD涂层", "category": "surface",
        "applicable_materials": ["304", "316L", "TC4", "45钢"],
        "applicable_geometry": ["any"],
        "params": {"film_thickness_um": "1-5", "hardness_hv": "2000-3500"},
        "notes": "高硬度耐磨装饰涂层; 真空环境; 不锈钢/钛适用; 膜薄不影响尺寸精度",
        "cost_tier": "high",
    },
    "casting": {
        "name": "铸造", "category": "forming",
        "applicable_materials": ["6061", "304", "316L", "Q235", "黄铜", "carbon_steel"],
        "applicable_geometry": ["complex_3d", "large_batch", "near_net_shape"],
        "params": {"min_batch": 100, "draft_angle_deg": 1.5, "min_wall_mm": 3.0},
        "notes": "复杂形状大批量近净成形; 需开模 (模具成本); 力学性能低于锻件/机加; 适合 >100 件",
        "cost_tier": "low",
    },
    "forging": {
        "name": "锻造", "category": "forming",
        "applicable_materials": ["45钢", "TC4", "6061", "7075", "carbon_steel"],
        "applicable_geometry": ["high_strength", "load_bearing"],
        "params": {"min_batch": 50},
        "notes": "承力件首选 (纤维流线完整, 力学性能最优); 需开模; 近净成形后机加工",
        "cost_tier": "mid",
    },
}


def compatible_processes(material: str, surface: str = "", need_heat_treat: bool = False,
                         tight_tolerance: bool = False, geometry: str = "") -> Dict[str, Any]:
    """确定性工艺路由: 给定材料/需求 → 推荐工艺 + 不兼容工艺 + 原因."""
    recommended: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    cat = material_category(material)

    for pid, p in PROCESS_KNOWLEDGE.items():
        exclude = p.get("exclude_materials") or []
        applicable = p.get("applicable_materials") or []
        # 材料兼容判定
        if material and material in exclude:
            excluded.append({"process": pid, "name": p["name"],
                             "reason": f"{material} 不适用{p['name']}"})
            continue
        if material and applicable and material not in applicable:
            excluded.append({"process": pid, "name": p["name"],
                             "reason": f"{material} 不在{p['name']}适用材料表"})
            continue
        # 需求匹配
        why = []
        if surface and surface != "none" and p.get("category") == "surface" and pid != surface:
            continue  # 表面处理按指定 surface 选
        if surface and pid == surface:
            why.append(f"指定表面处理 {surface}")
        if need_heat_treat and pid == "heat_treatment":
            why.append("需热处理强化")
        if tight_tolerance and pid in ("edm_wire_cut", "grinding"):
            why.append("紧公差精加工")
        if not why and p.get("category") == "subtractive":
            why.append("基础减材成形")
        if why:
            recommended.append({"process": pid, "name": p["name"],
                                "category": p.get("category"), "reason": "; ".join(why),
                                "cost_tier": p.get("cost_tier")})

    return {
        "material": material, "material_category": cat,
        "recommended": recommended, "excluded": excluded,
        "anodizing_ok": MATERIAL_KNOWLEDGE.get(material, {}).get("anodizing_ok", False),
        "heat_treatable": MATERIAL_KNOWLEDGE.get(material, {}).get("heat_treatable", False),
    }


def process_detail(process: str) -> Optional[Dict[str, Any]]:
    return PROCESS_KNOWLEDGE.get(process)
