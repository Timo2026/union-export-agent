# 收敛方案 · 最小闭环 + 窄跑马 + v0 接口冻结

| 字段 | 内容 |
|------|------|
| 版本 | v1.0-converge · 2026-09-21 |
| 诊断 | 可分解性低 · 耦合高 · 接口不稳 · 底层半定 · **可用闭环验证收敛** |
| 原则 | **停新模块** → 盘点（已完成）→ **窄跑马** → **选主架构** → **冻 v0** → 集成骨架 mock → **再分工** |
| 进度事实 | `docs/PROJECT-PROGRESS-BOARD.md` |
| 权威 | `PRD-MASTER-UEA-DELIVERY.md` v2.0 |

---

## 0. 结论先行

**现在最优策略不是多 Agent 继续拼模块，而是：**

1. 选定 **唯一最小闭环 Loop-M1**（见 §2）  
2. 只让 **2–3 个方案**在「同一接口约束」下各交可运行闭环（§3）  
3. 用评分表选出主方案后 **立刻冻结 IFACE-v0**（§4）  
4. 搭 **集成骨架 + mock**（§5）  
5. 才按强/中/弱分层开发；后续只做 **模块级跑马**（§6）  
6. 资源比：**25% 跑马闭环 · 20% 冻接口/骨架 · 50% 模块 · 5% 集成替换**（§7）

**禁止**：全项目跑马、投票选架构、弱 Agent 碰核心链路、无评分标准开跑、接口未冻就大规模并行。

---

## 1. 盘点结论（驱动收敛，不再展开）

| 事实 | 含义 |
|------|------|
| 本机：33 skills + 黄金链 + mail_* + 演示脚本 + 测试绿 | **不要从零建编排** |
| 节点：GPU/OCC 有，**无 livekernel** | 闭环必须包含「代码上节点」这一跳 |
| 邮件 Agent 80% 已有，缺 origin/Wiki | 新模块优先级极低 |
| 配置/方案/版本多线 | **接口债是主债** |
| 465+ 未提交 | 冻接口前至少 **配置与 schema 单源** |

---

## 2. 最小闭环定义（只选一个主闭环）

### Loop-M1（主闭环 · 必须端到端）

**场景**：一封**结构化询盘邮件**（本机 `data/mailbox/*.eml` 或手工 .eml）→ 系统产出 **可审计报价对象 + 草稿 + 审计/origin**，在**本机**与**节点离线路径**各跑通一次。

```
输入 .eml
  → MailPuller/pending（或 API 模拟 mail origin）
  → CAT/黄金链：parse-rfq → check-dfm → calc-quote(Timo) → verify-gate
  → write/reply-draft（draft_only）
  → audit + origin + context_id
  → 输出：golden JSON / 证据文件（PASS/HITL/BLOCKED 至少 1 种可复现）
```

**明确排除（M1 不做）**：Wiki 编译器 · Omni 多模态 · OpenClaw 全量 · Dify · 真 SMTP 外发 · Nemotron 全家桶 · 多渠道。

**通过标准（DoD）**

| # | 标准 |
|---|------|
| 1 | 同一 schema 入参出参（见 §4） |
| 2 | 本机：`run_golden_core` 或等价 **3/3** 或邮件场景脚本绿 |
| 3 | 节点：脱敏包 + **同一脚本** 离线路径绿（允许 degraded 标注） |
| 4 | 输出含 `origin`、`context_id`、`price_source=timo`、verdict |
| 5 | 集成改动量可陈述（文件列表 + 是否破坏 725 测试） |

### Loop-M2（可选第二闭环，**不并行开发**，仅跑马备选验证）

Spark **进程级** `/v1` 起一个**已下载**小模型（如 Nano-4B 或已有 Qwen3-0.6B），黄金链里 **仅 FAST 角色** 用它，价格仍 Timo。  
仅在 M1 双端绿后启动。

---

## 3. 窄架构跑马（2–3 方案 · 非全项目）

### 约束（所有选手必须遵守）

- 必须 **复用** 现有 adapters/agents/skills/services，禁止重写引擎  
- 必须跑通 **Loop-M1**  
- 必须交付：分层图、IO schema、配置键、状态存储、日志字段、演示命令  
- 必须是 **可运行**，不是纯文档  
- 限时：建议 **各 0.5–1 人日** 或等价；产出后停投

### 选手方案

| ID | 方案名 | 架构一句话 | 增量改动 | 风险 |
|----|--------|------------|----------|------|
| **A** | **Canonical LiveKernel** | 保持 mail_orchestrator→CAT→skills；**只加 origin + 配置单源 overlay**；OpenClaw/后置 | **最小**（决策文档已指向此路径） | 「不够炫」但最稳 |
| **B** | **API-First 契约壳** | livekernel 降为 **工具 API**（`/v1/rfq`…）；薄 Orchestrator（可 OpenClaw/自研）只调度；UI 只读 | 中：冻结 HTTP 契约，orchestrator 变薄 | 双编排风险，须状态仍以 context_id 为准 |
| **C** | **Node-First 部署形态** | 同 A 代码，但 **打包/路径/conda/离线引擎** 为一等公民；配置仅 `profile=dgx-spark-p0` | 中：打包与 profile，不改业务语义 | 不解决 UI/邮件叙事；作 A/B 的**部署插件**更合理 |

**建议裁决预读（仍以跑马成绩为准，不投票）**：

- 若 A 在双端 Loop-M1 用最小 diff 绿 → **主方案 = A**，C 作为 A 的部署 profile，B 的 HTTP 契约 **并入 IFACE-v0** 而不替换编排。  
- 禁止「三个方案同时继续加功能」。

### 评分表（闭环跑完再填，禁止先写结论）

| 准则 | 权重 | A | B | C |
|------|------|---|---|---|
| Loop-M1 本机跑通 | 25 | | | |
| Loop-M1 节点离线跑通 | 25 | | | |
| 集成改动量（越小越好） | 15 | | | |
| 接口清晰（schema 可冻结） | 15 | | | |
| 配置统一（单源/overlay） | 10 | | | |
| 可观测（origin/audit/trace） | 5 | | | |
| 后续 Agent 接入成本 | 5 | | | |
| **总分** | 100 | | | |

---

## 4. v0 接口冻结（选定后 24h 内落 `docs/IFACE-v0.md`）

### 4.1 必须冻结

| 类别 | 内容 |
|------|------|
| **模块边界** | adapter / agent(CAT) / skill / service(api) / config / runtime(模型) / console(UI) |
| **进程内调用** | skill `tool.run(args) -> result` 统一返回 |
| **HTTP（若采 B 契约）** | `/v1/rfq/{cid}/*` `/v1/agent/task` `/v1/skills/config` health |
| **IO Schema** | RFQ、Quote、Verdict、AuditEvent、Origin、Provenance |
| **状态** | `context_id` 唯一；pending.jsonl 状态机；禁双事实源 |
| **存储** | sqlite 路径约定、gitignore、节点路径 overlay |
| **错误** | 引擎失败→fallback 显式；LLM 失败→规则；禁止静默 |
| **配置** | 基座 `settings.yaml` + `profile` overlay（demo / dgx-spark-p0）；**禁止**并行第四份无主配置 |
| **日志/trace** | 字段：`context_id, origin, skill, actor, verdict, price_source, degraded` |
| **版本** | 单一 release marker；文档不得各说各话 |

### 4.2 Origin 枚举（v0 一并冻）

```
origin ∈ { mail_pull, upload, manual, scheduled, demo, node_deploy }
tags   ⊇ { AGENT, MAIL_DRIVEN, HUMAN, HITL, BLOCKED, ENGINE, OMNI_FACT, DEGRADED }
```

### 4.3 示例：Skill 契约（冻结级）

```json
{
  "skill_id": "calc_quote",
  "args": {"material": "6061", "quantity": 100, "context_id": "RFQ-..."},
  "result": {
    "unit_price": 0,
    "currency": "CNY",
    "price_source": "timo:sha256:...",
    "iron_rule": "deterministic",
    "degraded": false
  },
  "meta": {"origin": "mail_pull", "trace_id": "..."}
}
```

### 4.4 冻结后变更规则

- 破坏性变更 →  bump `IFACE-v1` + 迁移说明  
- 模块级跑马实现可换，**不得改已冻字段名**  
- 新 Agent 只准依赖 IFACE-v0，不准旁路直连内部私有函数（评审红线）

---

## 5. 集成骨架 + Mock（冻结后的第一工程动作）

**不是新业务模块**，是骨架：

| 组件 | 职责 | M1 可用现成 |
|------|------|-------------|
| 入口 | CLI/API 触发 Loop-M1 | `run_golden_core` / mail API |
| 路由 | skill dispatcher | `skill_dispatcher` |
| 注册表 | skills.yaml + allowlist | 已有 |
| 消息/队列 | pending.jsonl | mail_puller |
| 存储 | context/audit sqlite | 已有 |
| 日志 | observability + audit origin | **补 origin 字段** |
| **Mock 层** | mock LLM / mock funasr / mock SMTP；**Timo 可真可离线 vendored** | settings mock + offline kernel |
| 测试桩 | `tests/test_loop_m1_*.py` | **只加这一个门禁测试** |

**原则**：集成路径先通；真实模型/Nemotron 用 **同一 IFACE** 替换，不改调用方。

---

## 6. 分层分工（接口冻结之后）

| 能力层 | 做什么 | 不做什么 |
|--------|--------|----------|
| **强** | IFACE-v0 起草与评审、Loop-M1 双端、CAT/adapter、集成门禁、节点打包 | 不写营销向长文替代实现 |
| **中** | 边界清晰的 service/skill 增强（origin、negative trigger、A/B 脚本） | 不改 schema 字段名 |
| **弱** | 文档勘误、evidence 整理、样本数据、测试用例、脱敏扫描 | **不碰** CAT/引擎/接口定义 |
| **流程** | 每阶段一次集成（M1 后）；失败开 **模块级跑马**（同 IFACE 重做，胜者替换） | 禁止最后大爆炸集成 |

---

## 7. 比例与阶段门

| 阶段 | 占比 | 产出 | 门禁 |
|------|------|------|------|
| 架构窄跑马 + 垂直切片 | 20–30% | 评分表 + 选主 | Loop-M1 报告 |
| 接口冻结 + 骨架 + 配置单源 | 20% | IFACE-v0 + origin + 路径测试 | 门禁测试绿 |
| 模块开发（按层） | 50–60% | 负向触发/A-B/节点服务/演示 | 阶段集成 |
| 集成验收与模块替换 | 10% | evidence 收口、版本 pin | 提交包 DoD |

---

## 8. 明确不做（赛期收敛清单）

- ❌ 新起第二套 Agent 运行时并与 CAT 双写业务状态  
- ❌ Wiki 编译器、Dify 主控、Omni 全家桶 **进入 M1**  
- ❌ 在节点未跑通 M1 前批量下 60GB 权重「占坑叙事」  
- ❌ 继续产出互斥 PRD 而不更新 MASTER/看板  
- ❌ 无 IFACE 就让多 Agent 并行改 services  

---

## 9. 建议执行序（收敛后）

| 序 | 动作 | 完成定义 |
|----|------|----------|
| 1 | 确认 Loop-M1 + 三选手约束 | 你书面确认 |
| 2 | A/B/C 按同一规范各出 M1 运行包（或 A 先行 + C 部署插件并行验证节点） | 评分表可填 |
| 3 | 选主 → 写 `docs/IFACE-v0.md` | 字段/枚举/配置键冻结 |
| 4 | origin + 配置 overlay + `tests/test_loop_m1.py` | 双端证据 |
| 5 | 节点脱敏部署同一 Loop-M1 | node golden + nvidia-smi 入 evidence |
| 6 | 再开 Skills 深度/A-B/模型服务（模块跑马） | 不破坏 IFACE |
| 7 | 版本 pin + 提交包 | MASTER DoD |

---

## 10. 请你确认（3 个决定）

| # | 决定 | 推荐默认 |
|---|------|----------|
| 1 | 主闭环是否采用 **Loop-M1（邮件/黄金链双端离线）** | **是** |
| 2 | 跑马是否采用 **A 主案 + C 作部署 profile + B 仅冻 HTTP 契约** | **是**（减少并行浪费） |
| 3 | 是否授权：选定后立即产出 `IFACE-v0.md` 并 **冻结配置单源** | **是** |

回复示例：`默认三项确认` 或改某一项。

确认后我**不再加新业务模块**，只做：评分表落地、IFACE-v0 草稿、origin 最小补丁清单、Loop-M1 双端命令清单。
