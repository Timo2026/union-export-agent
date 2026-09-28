---
name: sop-router
description: SOP 流程联动路由器 — 给定 RFQ 当前状态 (或 context_id) 确定性返回 SOP 阶段、合法下一状态 (allowed_next)、该阶段应调度的 skill 序列、是否触发 reid 协议分诊。把 Item3 的 RFQ 状态机 (NEW→INTAKE→STRUCTURING→DFM→QUOTING→VERIFY→REPLY→CRM_MEM→DONE + HITL/BLOCKED) 与 Item5 的 reid 分诊联动成一等可调度可复用 skill。Use when 调度器/邮件驱动/UI 需要"现在该走哪一步、调哪些 skill、要不要 reid 介入"时, 或 RFQ 推进前需确认合法转移与下游 skill 映射时。禁止：推进/改写状态 (状态机权威不可绕过, 本 skill 只读 TRANSITIONS)、定价、发送外部邮件。确定性离线, 非法状态诚实报错。
version: 1
iron_rule: deterministic
backend: services.rfq_state_machine.TRANSITIONS
openshell_policy: [local-only, skill-allowlist]
provenance: "新授权 (Item6 SOP×reid 联动); 只读 services/rfq_state_machine.TRANSITIONS + services/domain_knowledge; 不复制外部运行时"
tool_contract:
  openai_function:
    name: sop_router
    description: SOP 路由 — 输入 state (或 context_id), 输出当前阶段/allowed_next/next_skills/reid 联动; 只读不推进状态机
    parameters:
      type: object
      properties:
        state: {type: string, description: "RFQ 当前状态 (NEW/INTAKE/STRUCTURING/DFM/QUOTING/VERIFY/REPLY/CRM_MEM/HITL/HUMAN_APPROVAL/BLOCKED/DONE/ARCHIVED)"}
        context_id: {type: string, description: "业务 context_id (无 state 时尝试从 CRM 读取当前状态)"}
        target: {type: string, description: "可选: 校验 state→target 是否合法转移"}
      required: []
---

# sop-router

Item6 新授权 skill — 把 RFQ SOP 状态机 (Item3) 与 reid 协议分诊 (Item5) 联动为可调度可复用能力。

## 职责

给定当前状态 (或 context_id)，确定性返回：
- **stage**：当前 SOP 阶段 + 中文说明
- **allowed_next**：合法下一状态集合 (只读 `rfq_state_machine.TRANSITIONS`)
- **next_skills**：该阶段应调度的 skill 序列 (映射到已注册 skill id)
- **reid**：是否触发 reid 协议分诊 + 联动 skill (`reid_triage`) + 原因
- **is_terminal**：是否终态 (DONE/ARCHIVED)
- **transition_check**：给定 target 时校验 state→target 合法性 (不执行转移)

## 阶段 → skill 映射 (SOP 联动表)

| 阶段 | next_skills | reid |
|------|-------------|------|
| NEW | parse_rfq | ✓ 分诊来信复杂度 |
| INTAKE | rfq_extraction, parse_rfq, material_knowledge | ✓ |
| STRUCTURING | extract_specs, material_knowledge | ✓ 路由协议模板 |
| DFM | check_dfm, dfm_rules, dfm_conflict, step_analysis, process_knowledge | — |
| QUOTING | calc_quote, cnc_quote, batch_quote, quote_correction | — |
| VERIFY | verify_gate, verification | — |
| REPLY | write_reply, reply_draft (draft_only) | — |
| CRM_MEM | crm_sync, submit_feedback, customer_flywheel, customer_health | — |
| HITL | human_review, reid_triage | ✓ 人工+干预块 |
| BLOCKED | human_review, reid_triage | ✓ |
| DONE/ARCHIVED | (终态) | — |

## 铁律

- iron_rule: **deterministic** (只读 TRANSITIONS, 零 LLM, 离线可跑)
- **状态机权威不可绕过**：本 skill **只读不写** — 绝不调用 `transition()`, 不推进/改写状态 (只有 RFQStateMachine 能推进)
- **不定价 / 不发送外部邮件** (draft_only 铁律①)
- **诚实**：非法 state 返回 `ok=false, reason=invalid_state` + 合法状态清单; context_id 查不到状态时诚实降级 default+note

## 输入输出

```
输入: {state:"DFM"} → {stage, allowed_next:["QUOTING","BLOCKED","HITL"], next_skills:[check_dfm,dfm_rules,...], reid:{applicable:false}, is_terminal:false}
输入: {state:"STRUCTURING", target:"QUOTING"} → transition_check:{legal:false, reason:"非法转移"}
输入: {context_id:"RFQ-..."} → 从 CRM 读 state (读不到则 default NEW + note)
输出: {ok, skill:"sop_router", iron_rule:"deterministic", state, state_source, stage, allowed_next, next_skills, reid, is_terminal, transition_check?}
```

## 关联

- `rfq_state_machine` (状态权威) · `reid-triage` (reid 分诊) · 全链 skill (parse_rfq/calc_quote/verify_gate/write_reply)
- 数据源：`services/rfq_state_machine.py:TRANSITIONS` + 本 skill 内 STAGE_MAP
