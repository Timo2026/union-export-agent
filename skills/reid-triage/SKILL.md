---
name: reid-triage
description: Reid 决策操作系统分诊 (确定性决策层) — 对输入文本做 7 维复杂度评分→本地/云端路由→领域分诊 (domain/type)→协议模板选择→拉闸干预块生成。把 Item5 内联于 RAG analyze 端点的 reid 逻辑提升为一等可调度可复用 skill, 供 SOP 联动 (sop-router 在 NEW/INTAKE/STRUCTURING/HITL/BLOCKED 阶段引用) 与邮件/文档分诊复用。Use when 需要对来信/文档/RFQ 文本做复杂度分诊以路由处理协议、生成干预提示、或判断走本地还是云端模型时。禁止：定价、推进状态机、发送外部邮件。决策层 (复杂度/分诊/模板/干预) 全确定性离线; LLM 协议执行仅在 ollama 可达时附加, 否则 degraded=true 如实标注不伪造分析文本。
version: 1
iron_rule: deterministic
backend: reid_engine (importlib by REID_SCRIPT; 决策层离线确定性)
openshell_policy: [local-only, skill-allowlist]
provenance: "新授权 (Item6 SOP×reid 联动); 经 importlib 按绝对路径加载 reid-operating-system v1.5 决策层 (env REID_SCRIPT, 节点指向 staged 副本); 与 Item5 /v1/rag/docs/{id}/analyze 逻辑一致"
tool_contract:
  openai_function:
    name: reid_triage
    description: Reid 分诊 — 输入文本, 输出复杂度评分/路由/领域分诊/协议模板/干预块; LLM 协议执行离线时诚实 degraded
    parameters:
      type: object
      properties:
        text: {type: string, description: "待分诊文本 (来信/文档/RFQ); 截取前 4000 字"}
        run_protocol: {type: boolean, description: "是否尝试 LLM 协议执行 (默认 false, 仅决策层; true 且 ollama 可达才附 analysis)"}
      required: [text]
---

# reid-triage

Item6 新授权 skill — 把 reid-operating-system 决策层封装为可调度可复用分诊原语 (SOP×reid 联动)。

## 职责

给定文本，确定性产出 reid 决策层结果：
- **complexity**：7 维复杂度评分 + 路由依据 + 本地/云端 + 目标模型
- **triage**：领域 (domain) / 类型 (type) / 复杂度档 / 协议模板名 / 命中 flags
- **intervention**：拉闸干预块 (有 flags 时生成)
- **protocol_template** + **system_prompt_preview**：选中的协议模板及其 system prompt 摘要
- **analysis** (可选)：仅 `run_protocol=true` 且 ollama 可达时附加 LLM 协议执行结果

## 铁律

- iron_rule: **deterministic** (决策层 = 复杂度/分诊/模板/干预, 纯规则离线可跑)
- **LLM 协议执行诚实降级**：ollama 不可达 → `degraded=true`, `analysis=null`, **绝不伪造分析文本**
- **不定价 / 不改状态机 / 不发外部邮件** (draft_only 铁律①)
- **reid 引擎缺失诚实报错**：返回 `ok=false, reason=reid_not_installed` + 期望脚本路径 (REID_SCRIPT), 不静默冒充
- 桥必收**绝对路径** (相对路径→段错误); 节点部署用 `REID_SCRIPT` 指向 staged 副本

## 输入输出

```
输入: {text:"请报 50 件 6061 阳极氧化", run_protocol:false}
输出: {ok, skill:"reid_triage", iron_rule:"deterministic",
       reid:{complexity:{score,reason,cloud,model}, triage:{domain,type,complexity,template,flags},
             intervention, protocol_template, system_prompt_preview, analysis, degraded, provider, engine}}
reid 缺失: {ok:false, reason:"reid_not_installed", reid_script:"<绝对路径>"}
```

## 关联

- `sop-router` (NEW/INTAKE/STRUCTURING/HITL/BLOCKED 阶段引用本 skill) · Item5 `/v1/rag/docs/{id}/analyze` (同逻辑)
- 引擎：`reid-operating-system v1.5` (env `REID_SCRIPT`, 默认装机机路径; 节点 `~/nvidia-skills/...`)
