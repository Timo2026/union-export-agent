"""density_guard.py — 材料密度权威表 + 引擎回落侦测 (2026-09-23).

源起缺陷: 引擎 src/runtime/step_parser.get_material_density() 走
  src/runtime/step_generator.DENSITY (14 条) → **miss 时回落 2.8**。
实测 BOM 常用 4 个 key 全 miss:
  yg8 钨合金 真实 14.50 → 回落 2.8  → 重量算小 81% (材料费严重低估)
  440c       真实  7.85 → 回落 2.8  → 算小 64%
  abs        真实  1.04 → 回落 2.8  → 算大 169% (材料费高估)
  pom        真实  1.41 → 回落 2.8  → 算小 50%
这是静默错价: geometry.density=2.8 看起来像个正常数, 没人会怀疑。
凡密度未核实的材料, 重量就不该直接进价格。

本模块职责:
  1) 权威密度表 (PREPARED_BY 手工录入, 单位 g/cm³ = 1e-6 kg/mm³)
  2) resolve_density(material) → (密度, 来源说明, 引擎原值) 三分判定
  3) is_fallback(density) → 是否触发了引擎的 2.8 回落

原则: 引擎体积 (OCP B-rep) 是事实, 密度是常量 —— 谁错修谁,
不因引擎给了个数就照单全收, 也不因引擎没给就静默。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

# 引擎回落值 (硬编码于 step_generator.DENSITY.get(material, 2.8))
ENGINE_FALLBACK = 2.8

# 权威密度表 g/cm³。与 services/material_map.BOM_MATERIAL_MAP 保持一致;
# 此处额外收录引擎侧材料键, 供 adapter 直接核对 (引擎认 key 不认中文名)。
DENSITY: Dict[str, float] = {
    # ── 铝 (2.70~2.87) ──
    "6061": 2.70, "al6061": 2.70, "6063": 2.70, "5052": 2.68,
    "7075": 2.81, "2024": 2.78, "5083": 2.66,
    "铝": 2.70, "铝合金": 2.70, "6061铝合金": 2.70,
    # ── 钢 (7.75~8.10) ──
    "45钢": 7.85, "45#": 7.85, "q235": 7.85, "40cr": 7.85, "45crni": 7.85,
    "304": 7.93, "sus304": 7.93, "301": 7.93, "316l": 7.98, "316": 7.98,
    "sus316": 7.98, "17-4ph": 7.80, "440c": 7.85, "420": 7.75,
    "skd11": 7.85, "cr12": 7.85, "cr12mov": 7.85, "dc53": 7.75,
    "40cr13": 7.75, "3cr13": 7.75, "2cr13": 7.70, "201": 7.93,
    "不锈钢": 7.93, "不锈钢304": 7.93, "不锈钢316l": 7.98,
    "301不锈钢": 7.93, "不锈钢": 7.93, "不锈钢304": 7.93, "不锈钢316l": 7.98,
    "17-4ph不锈钢": 7.80, "304不锈钢": 7.93, "316l不锈钢": 7.98,
    "40cr13不锈钢": 7.75, "301不锈钢含图纸": 7.93,
    "301含图纸": 7.93, "304含图纸": 7.93, "316l含图纸": 7.98,
    # ── 铜 (8.40~8.90) ──
    "黄铜": 8.50, "h59": 8.50, "h62": 8.43, "h68": 8.50, "紫铜": 8.90,
    "t2": 8.90, "c110": 8.90, "铍铜": 8.25, "c17200": 8.25,
    # ── 钛 (4.43~4.51) ──
    "tc4": 4.43, "钛合金": 4.43, "ta1": 4.51, "ta2": 4.51,
    # ── 硬质合金 (14.0~15.0, 密度最大, 回落误差可达 5 倍) ──
    "yg8": 14.50, "yg6": 14.80, "yt15": 11.20, "yg15": 14.00,
    "钨合金": 14.50, "钨钢": 14.50, "yg8钨合金": 14.50, "硬质合金": 14.50,
    # ── 塑料 (0.90~1.60) ──
    "abs": 1.04, "abs pc": 1.12, "pom": 1.41, "pom 白色": 1.41,
    "pom 乙缩醛共聚物": 1.41, "赛钢": 1.41, "pmma": 1.18, "亚克力": 1.18,
    "有机玻璃": 1.18, "pc": 1.20, "聚碳酸酯": 1.20, "尼龙": 1.15,
    "pa66": 1.15, "mc尼龙": 1.15, "pp": 0.91, "pe": 0.95, "聚甲醛": 1.41,
    "pvc": 1.38, "ptfe": 2.20, "聚四氟乙烯": 2.20, "pbt": 1.30,
    # ── 工程塑料 (1.25~1.60, 高价材料) ──
    "peek": 1.30, "聚醚醚酮": 1.30, "颈椎聚醚醚酮 (peek)": 1.30,
    "pei": 1.27, "pai": 1.40, "pi": 1.43, "pps": 1.35, "lcp": 1.63,
    "pom-c": 1.41, "聚醚酰亚胺": 1.27, "聚醚醚酮(peek)": 1.30,
    # ── 弹性体 (0.85~1.40) ──
    "tpu": 1.15, "tup": 1.15, "pur": 1.10, "聚氨酯": 1.15,
    "硅橡胶": 1.15, "硅胶": 1.15, "医用硅胶": 1.15, "医用硅胶白色": 1.15,
    "氟橡胶": 1.85, "epdm": 1.15, "nbr": 1.25, "丁腈橡胶": 1.25,
    # ── 陶瓷/玻璃/其他 (1.5~4.0) ──
    "氧化铝陶瓷": 3.90, "al2o3": 3.90, "氧化锆": 6.05, "zro2": 6.05,
    "氮化硅": 3.20, "碳化硅": 3.20, "碳纤维": 1.55, "cfrp": 1.55,
    "玻璃": 2.50, "钢化玻璃": 2.50, "玻璃含图纸": 2.50, "石英玻璃": 2.20,
    # ── 复合材料/装配 (按 2.70 中值, 需人工核) ──
    "焊接件": 2.70, "组装件": 2.70, "组装件无需加工，仅组装喷漆": 2.70,
    "组装件无需加工，仅焊接喷漆": 2.70, "电木": 1.40, "酚醛": 1.40,
}


def is_fallback(density: Any) -> bool:
    """是否正是引擎的 2.8 回落值。None/不可解析 → False, 交由调用方显式处理。"""
    if density is None:
        return False
    try:
        d = float(density)
    except (TypeError, ValueError):
        return False
    return abs(d - ENGINE_FALLBACK) < 1e-6


def _authoritative(material: str) -> Optional[float]:
    """按全键查权威表 (精确 → 小写 → 归一化后小写)。"""
    if material in DENSITY:
        return DENSITY[material]
    low = material.strip().lower()
    if low in DENSITY:
        return DENSITY[low]
    # 由 material_map 先归一化 (BOM 名 → 引擎 key), 再用 key 查本表
    try:
        from services import material_map
        norm = material_map.normalize(material)
        k = (norm.get("key") or "").strip().lower()
        if k and k in DENSITY:
            return DENSITY[k]
        d = norm.get("density")
        if d:
            return float(d)
    except Exception:
        pass
    # 去空格 / 全半角归一
    squeezed = low.replace(" ", "")
    for k, v in DENSITY.items():
        if k.lower().replace(" ", "") == squeezed:
            return v
    return None


def _weight_from_volume(vol_mm3: float, density: float) -> float:
    """体积(mm³) × 密度(g/cm³) → 重量(kg), 保留 9 位有效数字。

    2026-09-23 缺陷11: 不能用固定小数位 round(x, 9) —— 对微小件
    (体积 3.36 mm³, 真重 4.87e-05 kg) 只保 4 位有效数字, 相对误差 4e-6;
    round(x, 4) 更会把 2.68e-05 kg 直接抹成 0.0, 再被上游 or 0.5 兜成半公斤,
    微小件单价虚高数十倍。按有效数字格式化, 毫克级与公斤级同精度。
    """
    if not vol_mm3 or vol_mm3 <= 0:
        return 0.0
    w = float(vol_mm3) * float(density) / 1e6
    return float(f"{w:.9g}")


def resolve_density(material: str) -> Tuple[Optional[float], str]:
    """材料 → (权威密度, 来源说明).

    返回 (None, reason) 表示本表未收录该材料 —— 调用方必须显式处理,
    不得沿用引擎回落值入价。
    """
    name = (material or "").strip()
    if not name:
        return None, "材料名为空"
    d = _authoritative(name)
    if d is not None:
        return d, "authoritative"
    return None, f"材料 {name!r} 未收录权威密度表 ({len(DENSITY)} 条), 需人工补"


def audit_geometry(geometry: Dict[str, Any], material: str) -> Dict[str, Any]:
    """校验引擎几何里的密度/重量, 需要时用权威密度重算重量。

    规则 (改重量不改体积):
      - 体积来自引擎 OCP B-rep, 是事实, 不动
      - 引擎密度命中权威值 → 原样通过
      - 引擎密度回落 2.8 而权威表有值 → 用权威密度重算重量, 记
        density_corrected=True 与两个密度值 (显式留痕, 不静默)
      - 权威表未收录 → 不猜。记 density_verified=False, 交由上游
        决定是否进价 (报价应标"几何可用, 密度待核")
    """
    g = geometry if isinstance(geometry, dict) else {}
    vol_mm3 = g.get("volume_mm3")
    try:
        vol = float(vol_mm3 or 0.0)
    except (TypeError, ValueError):
        vol = 0.0
    engine_d = g.get("density")
    auth, src = resolve_density(material)

    # 结果键: density_source 说明最终重量用哪个密度算
    out = dict(g)
    out["density_engine"] = engine_d
    out["density_source"] = src
    out["density_authoritative"] = auth
    out["density_verified"] = None

    if auth is None:
        out["density_verified"] = False
        out["density_warning"] = src
        return out

    if is_fallback(engine_d) or engine_d is None:
        # 引擎给不出可靠密度(回落2.8) → 权威值接管
        out["density_corrected"] = True
        out["density"] = auth
        if vol > 0:
            out["weight_kg"] = _weight_from_volume(vol, auth)
        return out

    # 引擎给了非回落值: 与权威值核对
    try:
        ed = float(engine_d)
    except (TypeError, ValueError):
        out["density_corrected"] = True
        out["density"] = auth
        if vol > 0:
            out["weight_kg"] = _weight_from_volume(vol, auth)
        return out

    if abs(ed - auth) / auth > 0.02:  # 偏差 >2% 视为口径分歧
        out["density_corrected"] = True
        out["density"] = auth
        out["density_disagreement"] = {"engine": ed, "authoritative": auth}
        if vol > 0:
            out["weight_kg"] = _weight_from_volume(vol, auth)
    else:
        out["density_verified"] = True
    return out


def coverage_report(materials) -> Dict[str, Any]:
    """批量审计: 哪些材料有权威密度、哪些没有。供报价单'待补'页引用。"""
    known, missing = [], []
    for m in materials:
        d, src = resolve_density(m)
        (known if d is not None else missing).append(
            {"material": m, "density": d, "source": src})
    return {"n": len(materials) or 0, "n_known": len(known), "n_missing": len(missing),
            "known": known, "missing": missing}
