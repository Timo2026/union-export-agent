# 邮件 Agent 架构方案（收敛版 · 赛期决策）

| 字段 | 内容 |
|------|------|
| 版本 | v1.0-decision |
| 日期 | 2026-09-20 |
| 触发 | 用户提出"邮件驱动 + openclaw skill 化 + V6 控制台 + RAG/Wiki 双记忆" |
| 方法 | 基于代码库实证查证，非推测 |
| 结论 | **80% 想要的能力已存在，只需接线闭环 + 补一个 origin 标记；大整合与 Wiki 编译器列为赛期风险项，不建议作为代码扩展** |

---

## 1. 现状对照（先看清楚再决定做什么）

用户的核心诉求与代码库现状逐条对照：

| 用户诉求 | 代码库现状 | 结论 |
|---------|-----------|------|
| 邮件作为**驱动** | `mail_puller.py`(30s 轮询 pending.jsonl) + `mail_orchestrator.py`(pull → CAT 黄金链 → 审计) | ✅ **已有**，只需接线闭环 |
| V6 保留做**控制台** | `webui/index.html` 三栏(Inbox / Inspector 8区 / Chat) + 黄金链进度条 | ✅ **已有** |
| 标记来源（Agent处理 vs 邮件驱动） | 审计链 `audit.log(event, payload, actor="system")` 有 `actor` 但**无 `origin`** | ⚠️ **真实缺口**，低成本可补 |
| 收集邮件地址为 ID 做客户资料 | `crm_memory.customer_id_by_name` / `get_customer_profile`；RAG L1 customer 已按 customer_id | ✅ **已有**模式 |
| 历史记录推演回复 | RAG L2 quotes 向量锚点 + `quote_calibration` 校准 + `reply-draft` skill | ✅ **已有** |
| 调用 openclaw 里的 skill | `skill_pack_adapter.py`（剥离价格字段、catalog 不热调度、_mock 兜底） | ✅ **安全边界已在** |
| RAG 库 + 本地大知识库 | `rag_layers.py` 四层 + `data/knowledge/`(材料/工艺/零件) | ✅ **已有** |
| LLM Wiki v2 编译器模式 | 无 | ❌ **未实现**（赛期风险项） |

**一句话**：你描述的架构里，**只有"origin 来源标记"和"LLM Wiki 编译器"两个是真正的缺口**；其余全是 livekernel 已实现的——只是没串成"邮件驱动叙事"来讲。

---

## 2. 决策：做与不做

### 2.1 做（低成本高价值，对齐赛期得分路径）

| 序 | 动作 | 成本 | 证据/得分价值 |
|----|------|------|--------------|
| D1 | **补 `origin` 来源标记**：`audit.log` 增 `origin` 字段 (`mail_pull` / `upload` / `manual` / `scheduled`)；MailOrchestrator 落 `origin=mail_pull`；UI/上传端口落各自 origin | 30 min | 审计链可区分驱动来源；直接回应用户"标记来源"诉求 |
| D2 | **邮件驱动叙事接线**：跑一遍 `mail_orchestrator` → 留证黄金链从邮件驱动起步的证据 | 1 h | 答辩可指："评委看到的这单是邮件自动进来→黄金链→报价→HITL"，而非手动上传 |
| D3 | **email_receiver 负面对照入证**（已落到 `PRIOR-ART-v7.md` §5 + 交付报告 §3） | 已完成 | 行业痛点真实性 + "接口兼容≠行为等价"对照 |

### 2.2 边界内做（外部代码禁入仓体，只读元数据）

| 序 | 动作 | 边界 |
|----|------|------|
| D4 | openclaw 的 skill 若要接入，**只能走 `skill_pack_adapter`**：只读 SKILL.md 摘要、剥离价格字段、catalog 不热调度。**绝不整仓拷贝、绝不执行外部脚本** | 与已拍板边界一致；与本仓 egress DENY 不冲突 |

### 2.3 不做 / 后置（赛期风险，列为叙事而非代码）

| 序 | 不做项 | 理由 |
|----|--------|------|
| N1 | openclaw 大整合（把外部 daemon 代码搬进来） | 与"外部仓代码禁入 livekernel 仓体"边界冲突；稀释唯一提交主体；email_receiver 的 SMTP 直发与本仓 egress DENY 直接冲突 |
| N2 | LLM Wiki v2 编译器（摄入时编译 → Markdown 维基页） | 全新子系统，赛期时间不够；现有 RAG 四层 + 飞轮已覆盖"客户长期记忆"诉求；Wiki 的"跨文档综合"优势在单事实查询上不如 RAG，且 token 成本高 |
| N3 | 引入一堆 GitHub 邮件 Agent（haasonsaas/kikubot/mail-skill 等） | 引依赖违反离线铁律；且功能与 livekernel 已有重叠 |

**为什么 N1-N3 不做**：这三项的共同点是——做完会让提交主体不再清晰是 `union-export-agent-livekernel`，得分路径从已拍板的"Nemotron 全栈 + Spark 实证 + negative trigger + A/B"被稀释成"我们又整合了一堆外部项目"。**比赛要的是深度证据，不是广度拼装。**

---

## 3. 收敛后的邮件 Agent 架构（基于已有，只补缺口）

```
┌─────────────────────────────────────────────────────┐
│ 驱动层（已存在）                                       │
│  MailPuller(30s轮询) · /v1/upload/* · /v1/rfq/intake │
│  ↓ 每条都带 origin 标记 [D1 新增]                     │
├─────────────────────────────────────────────────────┤
│ 控制台（V6，已存在）                                   │
│  webui/index.html 三栏 · Inbox/Inspector8区/Chat     │
│  · 黄金链进度条 · origin 可见 [D1]                    │
├─────────────────────────────────────────────────────┤
│ 黄金链编排（已存在）                                    │
│  CATController: INTAKE→PARSE→DFM→QUOTE→VERIFY→REPLY  │
│  · 审计链每事件带 origin [D1]                         │
├─────────────────────────────────────────────────────┤
│ 推理层（Nemotron 全栈，待 N0-M3 实证）                 │
│  REASON:30B MoE · FAST:4B · OMNI三合一 · EMBED       │
│  DETERMINISTIC: Timo 引擎 (铁律①锁定，价格sha256)     │
├─────────────────────────────────────────────────────┤
│ 记忆层（已存在，RAG 四层，不做 Wiki）                   │
│  L1 customer(crm SQL 按customer_id)                  │
│  L2 quotes(向量锚点+校准) · L3 conversations · L4 craft│
│  · 飞轮(customer_flywheel 健康分/校准/沙箱)           │
├─────────────────────────────────────────────────────┤
│ 外部 skill 边界（已存在，安全接入）                     │
│  skill_pack_adapter: 只读SKILL.md · 剥离价格          │
│  · openclaw skill 经此桥进入，不入仓体 [D4]           │
├─────────────────────────────────────────────────────┤
│ 治理（已存在）                                          │
│  OpenShell4策略 · Guardrails三段 · egress DENY        │
│  · email_receiver 的 SMTP 直发模式 = 这里被拦的反面    │
└─────────────────────────────────────────────────────┘
```

---

## 4. RAG vs LLM Wiki 的明确决策

用户贴的 RAG/ Wiki 对比是对的（解释器 vs 编译器，互补不替代）。但落到**比赛**：

| 维度 | RAG（已有） | LLM Wiki（未实现） |
|------|------------|-------------------|
| 现状 | 四层已实证可用 | 0 代码 |
| 客户长期记忆 | 飞轮 + crm_memory 已做 | 需新建编译器子系统 |
| 赛期成本 | 已兑现 | 数日工程量 |
| 评委证据 | 可演示四层检索 | 需从零证明 |
| 风险 | 低 | 稀释主粮 |

**决策**：比赛期 **RAG 为主粮**（已实现，可演示可回归）。LLM Wiki 作为"飞轮记忆升级方向"在答辩**口头提及**（"我们的四层 RAG 已覆盖客户长期记忆；Wiki 的摄入时编译模式是下一阶段飞轮升级方向，本次未列入赛期范围"）——**叙事扩展，不做代码扩展**。

用户问的"邮件地址作 ID 做客户资料"——`crm.customer_id_by_name` + RAG L1 customer 层**已经是这个模式**，无需新建。

---

## 5. 与已拍板得分路径的对齐

已拍板（`MASTER-PRD-P0-to-Delivery.md`）：得分靠 **Nemotron 全栈 + Spark 实证 + negative trigger + A/B + 行为等价**。

本方案的三项"做"(D1-D3) 都**不偏离**这条路径：
- D1（origin 标记）让邮件驱动叙事可追溯，强化"可审计"主张
- D2（邮件驱动留证）给 Spark 实证多一个入口（邮件自动进→黄金链→报价）
- D3（负面对照）强化行业真实性与设计前提

三项"不做"(N1-N3) 都**保护**这条路径不被稀释。

---

## 6. 置信度

- **方案本身（基于实证查证）**：90%
- **D1-D3 可落地性**：85%（origin 标记是确定性工程改动）
- **诚实风险评估**：用户被多个新方向牵引，本方案的克制是刻意的——把广度拼装压回去，保住深度证据。若坚持做 N1-N3，置信度降到 50% 以下（赛期 + 提交主体清晰度双重风险）

---

## 7. 一句话

> 你想要的邮件 Agent 架构，80% 已经在 livekernel 里跑着了；剩下的 20%，origin 标记半小时补上，Wiki 编译器留作答辩口头提及。**别为了凑广度，把已经拍板的深度得分路径稀释了。**
