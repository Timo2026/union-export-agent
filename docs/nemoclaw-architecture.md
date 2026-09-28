# NemoClaw 混合架构（v3.0.0 · 方案 C）

**状态**：已实施 · **验收**：`pytest 354 passed, 1 skipped`

## 一句话

后端能力 Skill 化 + 轻量 Dispatcher（LLM 意图 / 规则兜底）+ OpenShell 强制铁律① + webui 第 6 tab 设置面板。

## 分层

```text
Frontend (v3 webui 6 tabs / 可选 Chat UI)
    │  POST /v1/agent/task {intent, files, args}
    ▼
Skill Dispatcher (services/skill_dispatcher.py)
    │  strategy: auto | rules_only | llm
    │  路由只决定调用哪些 Skill, 不改输出
    ▼
Skills (skills/*/tool.py + SKILL.md)
    │  parse_rfq · extract_specs · check_dfm · calc_quote
    │  verify_gate · write_reply · submit_feedback · render_thumbnail
    │  supplier_match · golden_chain
    ▼
OpenShell (openshell/*.yaml + services/openshell.py)
    │  iron-rule-1 (locked) · hitl-required · local-only · skill-allowlist
    ▼
Engine (Timo :7862 · FunASR · SQLite)  — 不变
```

## 铁律①工程化

1. `config/skills.yaml` → `openshell.iron-rule-1.locked=true`（save 强制）
2. Dispatcher 对 `iron_rule=deterministic` 的 Skill 输出做 sha256 锁定
3. `OpenShell.attempt_override()` 模拟 LLM 改写 → **拒绝** 并记 violation
4. webui 设置面板 iron-rule-1 开关 `disabled` + 文案「不可关闭」
5. API `POST /v1/skills/config` 关闭 iron-rule-1 → **400**

## 设置功能

| 项 | 位置 | 说明 |
|----|------|------|
| Dispatcher 策略 | webui Skill 设置 / `skills.yaml` | auto / rules_only / llm |
| LLM 来源 | 同上 | models.yaml llm（含 A/B）或不用模型 |
| OpenShell 开关 | 同上 | iron-rule-1 锁定 |
| Skill 启停 | 同上 | 逐个 enable/disable |
| 试调度 | webui | intent → route/trace/审计 |
| 审计 | `data/skill_audit.jsonl` + `GET /v1/agent/openshell` | 只读 |

## API

| 方法 | 路径 | 用途 |
|------|------|------|
| GET/POST | `/v1/skills/config` | 读/写 Skill 设置 |
| POST | `/v1/agent/task` | 执行调度 |
| POST | `/v1/agent/route` | 仅预览路由 |
| GET | `/v1/agent/openshell` | 策略状态 + 审计 |

## 降级

- LLM 离线 → 规则路由（关键词 + 文件扩展名），**不阻断**
- Timo 离线 → 既有 byte-identical 离线内核
- 现场比赛建议 `dispatcher.strategy=rules_only`

## 设计文档

完整 spec：`docs/superpowers/designs/2026-09-18-nemoclaw-integration-design.md`
