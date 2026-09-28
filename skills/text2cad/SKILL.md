---
name: text2cad
description: 参数化形状 → STEP/STL 确定性 CAD 生成 (法兰/L支架/轴套/板类/管件五族) + 几何事实; 缺参 HITL 不兜底, cadquery 缺席诚实降级; 只画图不定价。
version: 1
iron_rule: deterministic
backend: services/text2cad.py:build_part
openshell_policy: [local-only, skill-allowlist]
tool_contract:
  openai_function:
    name: text2cad
    description: 文字/参数生成 CAD 产物 (STEP/STL) + 几何事实
    parameters:
      type: object
      properties:
        shape: {type: string, description: "flange|l_bracket|bushing|plate|pipe"}
        params:
          type: object
          description: "形状参数 (mm); 缺必填 → missing 列表 (槽位填充/HITL), 引擎不兜底默认值"
        formats:
          type: array
          items: {type: string, enum: [step, stl]}
          description: "产物格式子集, 默认 step+stl"
        name:
          type: string
          description: "产物文件名白名单 (字母数字-_), 空=参数哈希派生"
      required: [shape, params]
---
# text2cad

参数 → CAD (STEP/STL)。复刻 nl2cad 画图能力: shape + params 进, 确定性几何 +
sha256_16 真实文件指纹出。

## 铁律

- **只画图不定价** (铁律②): 报价永远由 Timo 确定性引擎裁决, 本 skill 不碰价格。
- **缺参不兜底**: 缺必填参数 → `missing-params` + missing 列表, 由 Omni 提议 +
  HITL 确认; 按猜的尺寸出图比不出图更坏。
- **诚实降级**: cadquery 缺席 (开发机) → `cadquery-unavailable`, 零落盘零冒充;
  节点 occ env 有 cadquery 2.8.0, 真实内核出图。
- **本地闭环**: 产物只落 data/cad (OpenShell local-only), 无任何外发。

## 契约边界

- shape 未知 → `unknown-shape` + available 列表。
- 参数类型/量程非法 → `invalid-params` + invalid 明细 (调用方错误, 非缺参)。
- 几何非法 (如管件壁厚超外径一半) → `geometry-failed`, 零落盘。
