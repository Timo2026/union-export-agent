"""material_map.py — BOM/客户材料名 → 引擎材料键归一化 (显式判定, 零静默).

背景 (2026-09-23): 实测 410 项 BOM 的 27 种材料里, 24 种喂给引擎后
`material_recognized=False`, 且单价一律回落默认值 (431.25)。例: PEI/17-4PH/
YG8钨合金/40Cr13/301/316L 全被当成 6061 计价 —— 钨合金 800元/kg、TC4 6267元/kg
的材料按 200元/kg 报, 系统性低估。这与缺陷8(STEP 静默回落 fallback_all_failed)
是同一类病: **解析失败不报错, 只是安静地给你一个错的答案**。

本模块把归一化变成显式的三分法:
  exact     材料键即引擎 key, 无需近似 → 正常计价
  approx    BOM 名在引擎 MATERIAL_MAP 里有近似对应 → 计价, 但必须携带
            `approx_note`, 供报价单/HITL 标注"用 X 近似计价"
  unknown   引擎无对应 → 不猜、不回落。上游据此标 "材料价格待补",
            单价留空, 进 HITL, 而不是给一个错数

铁律: 宁可在表里留空标"待补", 绝不静默伪造价格。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# 判定结果常量
EXACT = "exact"
APPROX = "approx"
UNKNOWN = "unknown"

# 引擎合法材料键 (来自 app/main_lite.MAT_COEFS ∪ MAT_PRICE_PER_KG, 2026-09-23 实测)
ENGINE_KEYS = {
    "304", "316l", "45#", "45钢", "6061", "7075", "al6061", "h59", "q235",
    "sus304", "sus316", "tc4", "钛合金", "黄铜",
    # MAT_PRICE_PER_KG 独有
    "440c", "abs", "pom", "yg8",
}

# BOM 规格列实际出现的材料 → (引擎 key, 近似说明)。
# 只收录能在引擎里找到"可得价格"的目标; 找不到的一律不放进来 (落入 UNKNOWN)。
#
# 价格风险分级依据: 两料每公斤单价差越大, 近似越危险。
#   PEI 无引擎项 → 若近似 6061 (200元/kg) 属高风险, 故不收
#   17-4PH 近似 304 (575) 有据可依 (两者都是不锈钢, 切削性近) → 收, 但标注
BOM_MATERIAL_MAP: Dict[str, Dict[str, Any]] = {
    # ---- 精确对应: BOM 名 → 引擎 key (合金牌号本身就在引擎键里) ----
    "6061铝合金": {"key": "6061", "kind": EXACT, "density": 2.70},
    "304不锈钢":  {"key": "304",  "kind": EXACT, "density": 7.93},
    "316L不锈钢": {"key": "316l", "kind": EXACT, "density": 7.98},
    "ABS":        {"key": "abs",  "kind": EXACT, "density": 1.04},
    "POM 白色":   {"key": "pom",  "kind": EXACT, "density": 1.41},
    "POM 乙缩醛共聚物": {"key": "pom", "kind": APPROX, "density": 1.41,
                       "approx_note": "POM 共聚物 → 引擎 pom 项"},
    "Y G8钨合金": None,  # 占位防误用, 真正条目在下面 (大小写键)
    "YG8钨合金":  {"key": "yg8",  "kind": EXACT, "density": 14.50},
    "440C":       {"key": "440c", "kind": EXACT, "density": 7.85},
    "黄铜":       {"key": "黄铜", "kind": EXACT, "density": 8.50},
    "PMMA":       {"key": "6061", "kind": APPROX, "density": 1.18,
                 "approx_note": "PMMA 无独立项, 按 6061 计价仅作加工费基准, 材料费需人工核"},
    # ---- 近似对应: 必须带 approx_note, 报价单上可见 ----
    "17-4PH":     {"key": "304",  "kind": APPROX, "density": 7.80,
                 "approx_note": "17-4PH 沉淀硬化不锈钢, 近似 304 (同属不锈, 切削性接近)"},
    "SKD11":      {"key": "45钢", "kind": APPROX, "density": 7.85,
                 "approx_note": "SKD11 冷作模具钢近似 45钢, 实际耐磨性更高, 工时可能偏低"},
    "40Cr13":     {"key": "45钢", "kind": APPROX, "density": 7.75,
                 "approx_note": "40Cr13 马氏体不锈钢近似 45钢"},
    "301不锈钢":  {"key": "304",  "kind": APPROX, "density": 7.93,
                 "approx_note": "301 近似 304 (奥氏体不锈, 加工性近)"},
    "ABS PC":     {"key": "abs",  "kind": APPROX, "density": 1.10,
                 "approx_note": "ABS+PC 合金近似 abs"},
    "TUP":        {"key": "6061", "kind": APPROX, "density": 2.70,
                 "approx_note": "TUP(热塑性聚氨酯) 按 6061 计价仅作加工基准, 材料费需人工核"},
    "PUR":        {"key": "6061", "kind": APPROX, "density": 2.70,
                 "approx_note": "PUR(聚氨酯) 按 6061 计价仅作加工基准, 材料费需人工核"},
    "PEEK":       {"key": "6061", "kind": APPROX, "density": 1.30,
                 "approx_note": "PEEK 无引擎项, 按 6061 计价严重偏低 (PEEK 约 800元/kg), 必须 HITL"},
    "颈椎聚醚醚酮 (PEEK)": {"key": "6061", "kind": APPROX, "density": 1.30,
                       "approx_note": "PEEK 无引擎项, 按 6061 计价严重偏低, 必须 HITL"},
    "氧化铝陶瓷":  {"key": "6061", "kind": APPROX, "density": 3.90,
                 "approx_note": "氧化铝陶瓷按 6061 计价仅作加工基准, 材料费需人工核"},
    "医用硅胶白色": {"key": "6061", "kind": APPROX, "density": 1.15,
                 "approx_note": "医用硅胶按 6061 计价仅作加工基准, 材料费需人工核"},
    "硅橡胶":     {"key": "6061", "kind": APPROX, "density": 1.15,
                 "approx_note": "硅橡胶按 6061 计价仅作加工基准, 材料费需人工核"},
}
# 上面 "Y G8钨合金": None 是防拼写误用的空条目, 从映射中剔除 (不参与查询)
BOM_MATERIAL_MAP.pop("Y G8钨合金", None)

# 明确"不适用机械加工计价"的物料类型: 非加工件, 报价应标"无需加工"
NON_MACHINED = {
    "组装件无需加工，仅组装喷漆": "组装件, 仅表面处理, 无切削工时",
    "组装件无需加工，仅焊接喷漆": "组装件, 仅焊接+表面处理",
    "焊接件": "焊接件, 工时与焊后加工需人工核",
    "玻璃含图纸": "非金属玻璃件, CNC 不适用, 需人工核",
}

# 已知无引擎价格且近似会严重失真的材料: 一律 UNKNOWN, 不得计价
KNOWN_NO_PRICE = {
    "PEI":     "PEI(聚醚酰亚胺) 引擎无项; 近似 6061 会低估约 4 倍, 不猜价",
    "17-4PH_keep": None,
}
KNOWN_NO_PRICE.pop("17-4PH_keep", None)   # 占位符清理


def normalize(bom_material: str) -> Dict[str, Any]:
    """BOM/客户材料名 → 归一化判定。

    返回 {kind, key, density, approx_note, reason}:
      kind=exact   → key 可直接喂引擎
      kind=approx  → key 可喂引擎, **必须**携带 approx_note 供上层标注
      kind=unknown → 无 key, 无价格, 上层应留空并进 HITL
    """
    name = (bom_material or "").strip()
    if not name:
        return {"kind": UNKNOWN, "key": None, "reason": "材料名为空"}

    if name in NON_MACHINED:
        return {"kind": UNKNOWN, "key": None, "reason": NON_MACHINED[name]}

    if name in KNOWN_NO_PRICE:
        return {"kind": UNKNOWN, "key": None, "reason": KNOWN_NO_PRICE[name]}

    hit = BOM_MATERIAL_MAP.get(name)
    if hit:
        return {"kind": hit["kind"], "key": hit["key"],
                "density": hit.get("density"),
                "approx_note": hit.get("approx_note"), "reason": "map hit"}

    # 未收录: 尝试大小写不敏感匹配 (bom 表里 17-4ph / 440c 大小写混乱)
    low = name.lower()
    for k, v in BOM_MATERIAL_MAP.items():
        if k.lower() == low:
            return {"kind": v["kind"], "key": v["key"],
                    "density": v.get("density"),
                    "approx_note": v.get("approx_note"),
                    "reason": f"case-insensitive hit on {k!r}"}

    # 名字本身就是引擎 key
    if low in ENGINE_KEYS or name in ENGINE_KEYS:
        return {"kind": EXACT, "key": name if name in ENGINE_KEYS else low,
                "reason": "name is engine key"}

    return {"kind": UNKNOWN, "key": None,
            "reason": f"材料 {name!r} 未收录且引擎不认识, 拒绝静默计价"}


# 引擎 WEIGHT_DENSITY_TABLE (app/main_lite) 精确密度, 供近似风险判定
ENGINE_DENSITY = {
    "6061": 2.70, "6063": 2.69, "7075": 2.81, "5052": 2.68,
    "304": 7.93, "303": 7.93, "316l": 7.98, "316": 7.98,
    "45钢": 7.85, "q235": 7.85, "skd11": 7.85, "cr12": 7.85,
    "黄铜": 8.50, "tc4": 4.51,
    "abs": 1.04, "pom": 1.41, "pmma": 1.18,
    "yg8": 14.50, "440c": 7.85,
}


def is_risky_approx(density_bom: Optional[float], key: str) -> bool:
    """密度差 > 25% 视为高风险近似 (单价随密度走, 差得多猜得离谱)。"""
    if not density_bom or not key:
        return False
    ref = ENGINE_DENSITY.get(key.lower())
    if not ref:
        return True
    return abs(density_bom - ref) / ref > 0.25


def unknown_report(table_names: List[str]) -> Dict[str, Any]:
    """给调用方一份审计: 哪些材料没价、为什么。报价单/日志可直接引用。"""
    out: List[Dict[str, Any]] = []
    for n in table_names:
        r = normalize(n)
        if r["kind"] == UNKNOWN:
            out.append({"material": n, "reason": r["reason"]})
    return {"n_unknown": len(out), "unknown": out}
