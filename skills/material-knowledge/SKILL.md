---
name: material-knowledge
description: 材料知识库 — 查询 9 种工业材料 (6061/7075/304/316L/TC4/45钢/Q235/黄铜/碳钢) 的确定性属性 (密度/屈服/抗拉/延伸率/硬度/耐蚀/可加工性/可热处理/阳极兼容/温度上限/成本档) + 选型建议 + 替代材料 + 易混淆点 (201≠304 / 40Cr≠45钢 / TC4≠纯钛 / 316L低碳抗晶间腐蚀)。Use when 用户询问材料属性、选材对比、牌号混淆、材料与表面/工艺兼容性, 或 RFQ/STEP/邮件提到材质需要知识支撑时。禁止：定价 (终价归 calc_quote 唯一权威)、推进 SOP 状态机、非金属材料咨询。确定性离线, 未收录材料诚实返回 not-found 不假造。
version: 1
iron_rule: deterministic
backend: services.domain_knowledge.lookup_material
openshell_policy: [local-only, skill-allowlist]
provenance: "external-catalog 蒸馏 (304-stainless/6061-aluminum/alloy-steel/aluminum-7075/stainless-steel-316/titanium-ti6al4v/carbon-steel-45/copper-brass deep-knowledge); 仅蒸馏事实知识, 不执行外部运行时, 不引用作者本地路径 (P0-B.4)"
tool_contract:
  openai_function:
    name: material_knowledge
    description: 材料知识查询 — 输入材料牌号 (或自然语言 query), 输出确定性属性/选型/替代/混淆点; 不定价, 不改状态机
    parameters:
      type: object
      properties:
        material: {type: string, description: "材料牌号 (6061/7075/304/316L/TC4/45钢/Q235/黄铜/carbon_steel 或别名 SUS304/Ti-6Al-4V/C45 等)"}
        query: {type: string, description: "自然语言材料问题 (可选; 无 material 时尝试从中识别牌号)"}
        compare: {type: array, items: {type: string}, description: "对比材料牌号列表 (可选)"}
      required: []
---

# material-knowledge

Item6 策展 skill — 从 Videos/skill 源材料知识库蒸馏**事实性领域知识**为确定性本地查询能力。

## 职责

给定材料牌号 (或自然语言 query)，返回：
- **属性**：密度 / 屈服 / 抗拉 / 延伸率 / 硬度 / 温度上限 / 成本档 / 标准牌号
- **工艺兼容**：可加工性 / 耐蚀 / 焊接性 / 可热处理 / 阳极氧化兼容 / 磁性
- **选型**：易混淆点 (牌号误用警示) + 替代材料建议
- **对比**：多材料并排属性表 (compare 参数)

## 铁律

- iron_rule: **deterministic** (纯知识查询, 零 LLM, 离线可跑)
- **不定价**：不写 unit_price/final_price/total — 终价归 `calc_quote` / CalculationEngine 唯一权威
- **不改状态机**：只读知识, 不推进 RFQ SOP
- **诚实空转**：未收录材料返回 `ok=false, reason=material_not_found` + 已收录清单, 不假造属性
- 与 `services.fleet_v4.calculation.MATERIAL_DB` 对 4 种共有材料 (6061/7075/304/carbon_steel) 数值**逐项一致**

## 输入输出

```
输入: {material: "304"} 或 {query: "SUS304 和 316L 区别"} 或 {compare: ["6061","7075"]}
输出: {ok, skill: "material_knowledge", iron_rule: "deterministic",
       material: {...属性+confusions+alternates+process_notes},
       comparison?: [...], source: "domain_knowledge", catalog?: [已收录牌号]}
```

## 关联

- `process-knowledge` (工艺路由) · `dfm-rules` (几何可制造性) · `material-expert` (LLM 选型推理, llm_proposal)
- 数据源：`services/domain_knowledge.py:MATERIAL_KNOWLEDGE`
