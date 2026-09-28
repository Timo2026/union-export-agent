---
name: dfm-rules
description: 几何可制造性 (DFM) 确定性规则检查 — 薄壁 (铝≥1.5/钢≥3/钛≥4mm)、深孔深径比 (>5 警示 / >8 高风险)、内圆角 (R<1mm 警示)、紧公差 (≤±0.02mm 需磨削/慢走丝)、表面处理遮蔽与膜厚补偿提醒。Use when 用户上传 STEP/图纸或描述零件几何 (壁厚/孔径孔深/圆角/公差) 需要可制造性体检, 或 RFQ 结构化后需几何 DFM 把关时。补充 check-dfm/dfm-conflict (仅材料×表面冲突), 本 skill 专管**几何**规则。禁止：定价、认证最终可制造性 (规则分诊 only, 复杂件需几何提取+人工复核)、推进状态机。确定性离线, 缺失字段诚实提示不假造。
version: 1
iron_rule: deterministic
backend: services.domain_knowledge.check_dfm_geometry
openshell_policy: [local-only, skill-allowlist]
provenance: "external-catalog 蒸馏 (dfm-analysis: thin-wall/deep-hole/inner-radius/tight-tolerance 阈值); 仅蒸馏规则阈值, 不执行外部脚本 (作者本地 /home/<user> 路径已剔除, P0-B.4)"
tool_contract:
  openai_function:
    name: dfm_rules
    description: 几何 DFM 规则检查 — 输入材料+几何参数 (壁厚/孔径孔深/内圆角/公差/表面), 输出 violations/warnings/passes + 风险级 (blocked/hitl/pass); 不定价不认证
    parameters:
      type: object
      properties:
        material: {type: string, description: "材料牌号 (决定薄壁阈值类别)"}
        wall_thickness_mm: {type: number, description: "最小壁厚 mm"}
        hole_depth_mm: {type: number, description: "孔深 mm"}
        hole_dia_mm: {type: number, description: "孔径 mm"}
        inner_radius_mm: {type: number, description: "内圆角半径 mm"}
        tolerance_mm: {type: number, description: "公差 ±mm"}
        surface: {type: string, description: "表面处理 (附加遮蔽/膜厚补偿提醒)"}
      required: []
---

# dfm-rules

Item6 策展 skill — 从 dfm-analysis 源蒸馏**几何可制造性规则**为确定性本地检查。

## 职责

给定材料 + 几何参数，确定性判定：
- **薄壁**：壁厚 < 材料类别最小值 → violation (铝 1.5 / 钢·不锈钢 3.0 / 钛 4.0 mm)
- **深孔**：深径比 > 8 → violation (高风险)；> 5 → warning (排屑/让刀)
- **内圆角**：R < 1.0mm → warning (刀具可达性/应力集中)
- **紧公差**：≤ ±0.02mm → warning (需磨削/慢走丝, 成本上升)
- **表面处理**：有 surface 时附加遮蔽/膜厚补偿/检验提醒

输出 `risk_level`: blocked (有 violation) / hitl (仅 warning) / pass。

## 铁律

- iron_rule: **deterministic** (纯规则, 零 LLM, 离线可跑)
- **规则分诊 only, 不认证最终可制造性** — 复杂件需结合几何提取 (step-analysis) + 人工复核
- **缺失字段诚实提示** (进 `missing` 列表), 不假造几何参数
- **不定价 / 不改状态机**
- 与 `check_dfm` (Timo 材料×表面×公差冲突) **互补不重叠**：本 skill 专管几何尺寸规则

## 输入输出

```
输入: {material:"6061", wall_thickness_mm:1.0, hole_depth_mm:90, hole_dia_mm:10, tolerance_mm:0.02}
输出: {ok, skill:"dfm_rules", iron_rule:"deterministic", dfm_valid:false, risk_level:"blocked",
       violations:[{rule,severity,msg,value,threshold}], warnings:[...], passes:[...],
       missing:[...], surface_reminders:[...], material_category:"aluminum"}
```

## 关联

- `check-dfm` / `dfm-conflict` (材料×表面冲突) · `step-analysis` (几何提取) · `material-knowledge` (材料属性)
- 数据源：`services/domain_knowledge.py:check_dfm_geometry` / `DFM_RULES`
