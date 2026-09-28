# 方案 · 邮件 Agent 全 Skill 化 + OpenClaw 驱动 + V6 控制台

| 字段 | 内容 |
|------|------|
| 版本 | v1.0 · 2026-09-20 |
| 输入 | `Downloads/email_receiver_20260920.zip`（只读清单）+ 邮件 Agent 开源调研 + RAG vs LLM Wiki 分析 + livekernel NemoClaw 现状 |
| 状态 | 方案稿 · 待拍板后进任务队列 |
| 可视化 | 工作目录 `email-agent-plan/index.html` |

---

## 1. 摘要：zip 是什么（只读结论）

`email_receiver_20260920.zip`（19 项，约 118KB 展开）= **已生产部署的 CNC 邮件自动报价守护进程**（openclaw 工作区 / systemd / 看门狗）。

| 组件 | 作用 |
|------|------|
| `email_receiver.py` (~37KB) | 主守护：IMAP 收信→附件/STEP→报价→SMTP 回复 |
| `quote_integration.py` | SQLite 报价引擎接线 |
| `daemon_monitor.py` / `*.service` | 生产运维 |
| `config/*` | 已脱敏邮件配置 + processed_ids |
| 测试脚本 | 3-round / fullflow / email flow |

**架构特征（负面对照）**：询盘→报价→**SMTP 直发**，无 HITL、无价格 sha 锁、无审计链、无状态机——与 livekernel 铁律①、`egress DENY`、`draft_only` **直接冲突**。

**融合纪律**：代码 **不入库、不拷贝进 livekernel**；只作 PRIOR-ART / 行业痛点证据与叙事对照。

---

## 2. 你的目标（重述）

1. **全部邮件能力 Skill 化**，装进 **OpenClaw**（主运行时）。  
2. **邮件是驱动源**（事件总线），不是又一个业务模块。  
3. **V6 livekernel Workbench = 控制台**，不是被替换的旧系统。  
4. 控制台必须**标记**：哪些邮件/任务是 **Agent 处理**，哪些是 **邮件驱动人工**，哪些是 **仅流水未决策**。  
5. 知识层二选一或混合：**按邮箱 ID 聚合客户 + RAG 历史推演回复** vs **LLM Wiki v2 编译记忆 + 本地 RAG 大库**。  
6. 处理邮件时 **调用 OpenClaw 内 Skill**（含报价黄金链）完成工作。

---

## 3. 推理：架构定案

### 3.1 分层（谁干什么）

```
[邮件通道] QQ/Gmail IMAP · (SMTP 默认关)
     │ 事件
     ▼
[OpenClaw Runtime]  ←—— 主 Agent 执行环境
  Orchestrator (邮件驱动状态机)
  Skill Registry (能力全量 Skill 化)
     │ 调用
     ├─► livekernel 黄金链 Skill 组 (报价/DFM/验证/草稿)
     ├─► 记忆 Skill (customer-profile / wiki-compile / rag-query)
     ├─► 运维 Skill (notify / followup / calendar)
     └─► 治理 OpenShell (iron-rule / hitl / egress)
     │ 回写 provenance
     ▼
[V6 Workbench 控制台]
  Inbox · Inspector · Chat · Skill Console
  标签: AGENT | MAIL-DRIVEN | HITL | BLOCKED | AUDIT
  只读审计 + 人工介入，不替代 OpenClaw 执行
```

### 3.2 关键决策

| 决策点 | 结论 | 理由 |
|--------|------|------|
| 谁跑编排？ | **OpenClaw** | 你要「邮件驱动 + skill 化」；OpenClaw 是技能运行时；livekernel 已是 NemoClaw 混合，可升格为 OpenClaw 侧 Skill 包 |
| V6 角色？ | **控制台 / 审计台 / HITL 台** | 已有 Workbench、mail_orchestrator、审计；保留 UI 资产，避免重做 |
| email_receiver 代码？ | **不集成** | 无 HITL/审计/锁价，与铁律冲突；只作 prior-art |
| 客户 ID？ | **规范化邮箱** = 主键 | 你已点名；RFC 大小写/别名规范化 + 可选域名层 |
| RAG vs Wiki？ | **混合，分层职责** | 见 §4；不是二选一 |
| 回复策略？ | **检索历史 + Wiki 事实 + 引擎数字 → 草稿** | 禁止裸 LLM 编价 |
| 外发？ | **永远 draft_only / HITL** | 对照 email_receiver 的事故面 |

### 3.3 与比赛叙事的关系

- 强化「垂直行业可验证商业价值」：邮件驱动工厂报价，但**可审计、可人审**。  
- 强化 Skills：邮件全链路 = 一组窄触发 Skill，而不是一个巨型 daemon。  
- 负面对照：野生 6 个月自动报价 daemon = 行业真实痛点证据。

---

## 4. 知识层：RAG vs LLM Wiki v2（评估结论）

| 维度 | RAG（查询时检索） | LLM Wiki（摄入时编译） | 本场景 |
|------|-------------------|------------------------|--------|
| 单事实（单价、工艺参数） | ✅ 强 | ❌ 易漂移 | **RAG + Timo 引擎** |
| 跨邮件综合（客户人格、项目史） | ❌ 碎片 | ✅ 强 | **Wiki 编译** |
| 实时新邮件 | ✅ 即索引 | 🟡 需增量编译 | 两者都要 |
| Token/延迟 | 查询重复做功 | 查询便宜、摄入贵 | 邮件高频摄入，Wiki 复利 |
| 可验证引用 | 🟡 chunk 级 | ✅ 页面级（若做好 schema） | 报价证据优先 RAG 锚点 + Wiki 链接 |
| 赛期可落地 | 已有 rag_layers | 需新增编译循环 | **P0 RAG，P1 Wiki** |

### 定案：双记忆（你要的「再结合」）

```
L1 LLM Wiki v2（编译态 · 长期语义）
   customers/<email_id>/profile.md
   customers/<email_id>/commitments.md
   projects/<topic>.md
   index.md + log.md（构建日志）
   —— 联系人偏好、历史谈判、常购物料、风险标签

L2 RAG（解释态 · 事实与长尾）
   原始邮件 / 附件 / PO / 报价历史向量+FTS
   livekernel rag_layers L1-L4 已存在 → OpenClaw Skill 暴露
   ——「三年前那单的单价」类问题 + quote_history 锚点

L0 DETERMINISTIC（真相）
   Timo calc_quote / ConflictChecker
   —— 最终数字永远在此，Wiki/RAG/LLM 均不可覆盖
```

**回信推演流程（不是纯 LLM 续写）**：

```
新邮件
  → mail.skill classify / extract
  → customer_id = normalize(from)
  → wiki.compile_delta(customer, email)     # 更新 L1
  → rag.retrieve(history, rfq_facts)        # L2
  → skills 黄金链: parse → dfm → calc_quote → verify
  → reply.skill draft(hits, quote, wiki_tone)
  → console 标记 AGENT-DRAFT · HITL 门禁
  → 人工确认后才允许 egress（默认 DENY）
```

---

## 5. Skill 目录（全量 Skill 化清单）

### 5.1 通道与驱动

| Skill ID | 触发 | 功能 | 依赖 |
|----------|------|------|------|
| `mail.pull` | cron/webhook | IMAP 拉信入 pending 队列 | mail_puller |
| `mail.normalize` | pull 后 | 邮箱 ID 规范化、线程 ID | — |
| `mail.classify` | 新邮件 | RFQ/跟进/垃圾/内部；置信度 | LLM/规则 |
| `mail.driver` | classified | 推进 OpenClaw 工作流状态 | orchestrator |

### 5.2 业务（复用 livekernel 33 中核心）

| Skill ID | 功能 |
|----------|------|
| `parse-rfq` / `extract-specs` | 结构化询盘 |
| `step-analysis` / `check-dfm` / `dfm-conflict` | 几何与工艺 |
| `calc-quote` / `cnc-quote` | **确定性报价** |
| `verify-gate` / `verification` | 门禁 HITL |
| `reply-draft` / `write-reply` | 草稿 only |
| `rag-ingest` / `batch-quote` | 历史与批量 |

### 5.3 记忆与客户

| Skill ID | 功能 |
|----------|------|
| `customer.profile` | 按 email_id 读写事实层（CRM） |
| `customer.wiki.compile` | 增量编译 Wiki 页 + 内链 |
| `customer.wiki.query` | 查编译页 |
| `memory.rag.query` | 查 L2 历史/附件/PO |
| `memory.rag.ingest` | 新邮件入向量库 |

### 5.4 跟进与通知

| Skill ID | 功能 |
|----------|------|
| `followup.track` | 承诺/待回复（Reply Zero 思路） |
| `followup.remind` | 定时进度通知 |
| `notify.telegram` / `notify.console` | HITL/BLOCKED 通知 + 控制台标记 |

### 5.5 治理

| Skill ID | 功能 |
|----------|------|
| `openshell.iron-rule` | 价格锁 |
| `openshell.hitl` | 人工门禁 |
| `openshell.egress` | 外发闸门 |
| `openshell.provenance` | **写 AGENT/MAIL 标记** |

**OpenClaw 安装形态**（概念）：

```text
~/.openclaw/skills/
  mail-pull/SKILL.md+tool.py
  mail-classify/...
  customer-wiki/...
  calc-quote/...          # 从 livekernel skills/ 暴露，不复制引擎逻辑
  ...
~/.openclaw/workspace/    # 状态、Wiki、队列（生产隔离）
```

**实现原则**：OpenClaw Skill = **薄封装** → HTTP 调 livekernel API（`:8888/8900`）或本地 engine venv；**禁止**把 Timo 引擎逻辑拆进 skill 目录。

---

## 6. V6 控制台：来源标记（必须做）

### 6.1 标记枚举

| 标签 | 含义 | 颜色建议 |
|------|------|----------|
| `AGENT` | OpenClaw Skill 自动完成步骤 | 紫 |
| `MAIL-DRIVEN` | 由邮件事件驱动进入，步骤仍自动 | 蓝 |
| `HUMAN` | 人工点击/批注 | 琥珀 |
| `HITL` | 等待人工批准 | 橙 |
| `BLOCKED` | 铁律/护栏拦截 | 红 |
| `ENGINE` | Timo 出价步骤 | 绿 |
| `AUDIT` | 仅审计/同步 | 灰 |
| `PRIOR-ART` | 对照系统引用（非本系统执行） | 黑/虚线 |

### 6.2 记录模型（建议字段）

每条邮件/任务/步骤：

```json
{
  "email_id": "user@qq.com",
  "message_id": "...",
  "context_id": "RFQ-...",
  "driver": "mail.pull",
  "pipeline": "openclaw://mail.driver → skills:parse-rfq → calc-quote → reply-draft",
  "agent_steps": ["mail.classify", "parse-rfq", "calc-quote"],
  "human_steps": ["approve"],
  "memory_refs": ["wiki://customers/user@qq.com/profile.md", "rag://quote_history#422"],
  "verdict": "HITL",
  "price_source": "timo:sha256:...",
  "egress": "draft_only",
  "tags": ["MAIL-DRIVEN", "AGENT", "HITL", "ENGINE"]
}
```

### 6.3 Workbench UI 增量

| 区域 | 改动 |
|------|------|
| Inbox 行 | 右侧标签胶囊 + 筛选器（AGENT / MAIL-DRIVEN / HITL…） |
| Inspector | 新 Tab **Provenance**：驱动源、Skill 调用链、memory_refs、价格来源 |
| Chat | 角色前缀 `[AGENT]` / `[HUMAN]`；Agent 草稿附引用 |
| Skill Console | 每次调度显示 `email_driver=true/false` |
| API | `GET /v1/mail/messages?tag=AGENT`；写入 pending/orchestrator |

`mail_orchestrator.py` 已有 pending→CAT→PASS/HITL/BLOCKED；**增量**是把 `driver=openclaw` 与 tags 写进状态与 UI。

---

## 7. 端到端时序（目标态）

```
QQ 新询盘邮件
  → [OpenClaw] mail.pull → pending
  → mail.normalize → customer_id
  → memory.rag.ingest + customer.wiki.compile_delta
  → mail.classify → RFQ?
  → mail.driver 激活黄金链 Skill 组
  → calc-quote (Timo) → verify-gate
  → PASS/HITL/BLOCKED
  → reply-draft（引用 Wiki 口吻 + RAG 历史 + 引擎数字）
  → V6 控制台：MAIL-DRIVEN+AGENT+[verdict] 标签 + Provenance
  → HITL 通知主管
  → 批准 → egress 显式开启 → SMTP（赛期默认关）
  → followup.track 入库
```

---

## 8. 实施路线（P0→P3）

| 阶段 | 内容 | DoD |
|------|------|-----|
| **P0 边界** | zip 入 PRIOR-ART；不复制代码；定 skill ID 表与 tags | 文档 + schema 草案 |
| **P1 控制台标记** | pending/orchestrator/webui 增加 provenance 字段与筛选 | Inbox 可筛 AGENT/MAIL-DRIVEN |
| **P2 OpenClaw 薄封装** | 5–8 个核心 skill 薄封装指向 livekernel API | 一封模拟邮件驱动报价草稿 |
| **P3 双记忆** | rag_layers 对外 skill + wiki compile MVP（单客户页） | customer_id 检索出 profile+历史锚点 |

**明确不做（赛期）**：email_receiver SMTP 直发并入；全量 1261 外部 skill；Wiki 无 schema 自由生长。

---

## 9. 风险

| 风险 | 处置 |
|------|------|
| 双系统状态分裂（OpenClaw vs livekernel） | 以 `context_id`/`pending.jsonl` 为单一事实源 |
| Wiki 编译错误污染回复 | 价格仍引擎；Wiki 只作语气/背景；冲突时以 RAG 事实+引擎为准 |
| 控制台标签被忽略 | 驾驶舱必须展示 verdict + tags，否则禁止合入 |
| 开源 zip 含生产痕迹 | 只引用不入库；答辩不展示未脱敏配置 |
| 与赛题「Skills」错位 | 邮件全链路 skill 化正是加分项 |

---

## 10. 一句话

> **邮件是驱动，OpenClaw 是技能运行时，livekernel V6 是带 Provenance 标记的控制台；记忆用 Wiki 编译客户语义、用 RAG 兜事实与历史，报价永远 Timo——email_receiver 只证明行业痛点，不证明我们的架构。**

---

## 11. 待你拍板

1. 是否按「OpenClaw 主执行 + V6 控制台」定案？  
2. P1 是否先做 **控制台标记**（不依赖 OpenClaw 装完）？  
3. Wiki MVP 范围：仅 `customers/<email_id>/profile.md` 是否够？  
4. zip 的 PRIOR-ART 落笔 `docs/PRIOR-ART-v7.md` 是否现在写入？  

可视化页面：`email-agent-plan/index.html`（浏览器打开）。
