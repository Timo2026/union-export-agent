---
name: process-knowledge
description: 工艺路由知识库 — 给定材料/需求 (表面处理/热处理/紧公差/几何) 确定性推荐加工工艺并标出不兼容工艺及原因。覆盖 12 工艺 (CNC铣/车、激光切割、慢走丝、磨削、热处理、阳极氧化、电镀、喷涂、PVD、铸造、锻造) 的适用材料/几何/参数/成本档。含材料兼容铁律 (阳极仅铝且优先6061 / 奥氏体不锈钢·黄铜·低碳钢不可热处理强化 / 304切削低速 / 钛导热差需高压冷却)。Use when 用户询问"某材料用什么工艺/能不能阳极/能不能热处理/某工艺适合什么材料", 或 RFQ/STEP 结构化后需工艺路线建议时。禁止：定价 (终价归 calc_quote)、认证最终工艺、推进状态机。确定性离线, 未收录工艺诚实返回。
version: 1
iron_rule: deterministic
backend: services.domain_knowledge.compatible_processes
openshell_policy: [local-only, skill-allowlist]
provenance: "external-catalog 蒸馏 (cnc-quote-*/anodizing-knowledge/heat-treatment-quote/laser-cutting-quote/edm-wire-cut-quote/grinding-quote-expert/casting/forging); 仅蒸馏工艺事实, 不执行外部运行时 (P0-B.4)"
tool_contract:
  openai_function:
    name: process_knowledge
    description: 工艺路由查询 — 输入材料+需求 (surface/need_heat_treat/tight_tolerance/geometry) 或工艺名, 输出推荐工艺+不兼容工艺+参数; 不定价不认证
    parameters:
      type: object
      properties:
        material: {type: string, description: "材料牌号"}
        process: {type: string, description: "指定工艺名查详情 (cnc_milling/anodizing/heat_treatment/...)"}
        surface: {type: string, description: "所需表面处理 (anodizing/electroplating/spray/pvd/none)"}
        need_heat_treat: {type: boolean, description: "是否需热处理强化"}
        tight_tolerance: {type: boolean, description: "是否紧公差 (≤±0.02mm)"}
        geometry: {type: string, description: "几何特征 (prismatic/rotational/sheet/complex_3d/...)"}
      required: []
---

# process-knowledge

Item6 策展 skill — 从 cnc/anodizing/heat-treatment/laser/edm/grinding 源蒸馏**工艺路由知识**为确定性本地查询。

## 职责

- **工艺路由** (`compatible_processes`)：给定材料 + 需求 → 推荐工艺 (含原因/成本档) + 不兼容工艺 (含原因)
- **工艺详情** (`process_detail`)：查单个工艺的适用材料/几何/参数/成本档
- **材料兼容铁律**：阳极仅铝 (优先 6061, 7075 效果差)；奥氏体不锈钢 (304/316L)/黄铜/Q235 不可热处理强化；304 切削低速 (-30~50%)；钛导热差需高压冷却

## 铁律

- iron_rule: **deterministic** (纯知识查询, 零 LLM, 离线可跑)
- **不定价**：工艺 cost_tier 仅相对档位提示, 非报价数字 — 终价归 `calc_quote` 唯一权威
- **不认证最终工艺**：路由建议 only, 复杂件需工艺师复核
- **诚实空转**：未收录工艺/材料返回 not-found, 不假造参数

## 输入输出

```
输入: {material:"304", need_heat_treat:true} → 推荐工艺 + heat_treatment 进 excluded (奥氏体不可强化)
输入: {material:"6061", surface:"anodizing"} → anodizing 进 recommended
输入: {process:"edm_wire_cut"} → 该工艺详情 (适用材料/公差/粗糙度/成本)
输出: {ok, skill:"process_knowledge", iron_rule:"deterministic", mode:"route|detail",
       recommended:[{process,name,reason,cost_tier}], excluded:[{process,name,reason}],
       anodizing_ok, heat_treatable} 或 {process_detail:{...}}
```

## 关联

- `material-knowledge` (材料属性) · `dfm-rules` (几何可制造性) · `check-dfm` (材料×表面冲突)
- 数据源：`services/domain_knowledge.py:PROCESS_KNOWLEDGE` / `compatible_processes` / `process_detail`
