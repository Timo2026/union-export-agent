# PRIOR-ART v8 — 外部「邮件驱动 AI 报价客服」方案对照与 omni 融合判定

> 日期 2026-09-21 · 输入: 决策者转贴的外部 AI 技术方案（组件栈 Dify + n8n + OpenClaw + RAGFlow + Python IMAP/SMTP；4 个 GitHub 参考项目；路线 A 2-3 周 / 路线 B 4-6 周）
> 方法: 逐环对照 livekernel 现有实现（下表每条均带 file:line，已 Read/Grep 验证）
> 结论口径: **融合边界**（只融叙事/证据/素材，禁接外部仓代码）下的缺口补齐清单

---

## 1. 外部方案骨架（原文归纳）

核心链路：**收邮件 → 解析需求 → 调本地知识库 → 调 OpenClaw skill（画图/报价）→ 人工审核 → 回复邮件**

| 参考项目 | 架构要点 | 与本仓重合度 |
|---|---|---|
| **gourav-shokeen/rfq-quote-agent**（自评最匹配） | n8n 自托管；LLM 提取需求 → SKU 匹配 → **确定性定价引擎** → 生成 PDF 报价单；Telegram 发草稿+摘要，一键批准/驳回；审核通过后原邮件线程回复；关键设计：**LLM 只提取和匹配，价格永远由确定性引擎计算**，schema 不含价格字段 | ★★★★★ 链路同构。我们已有确定性定价 + 审批 + 审计，缺 PDF 附件（G2） |
| **fankcoder/email-quote-automation**（中文文档） | Python；IMAP 自动收取未读询价；自动翻译非目标语言邮件；按定价规则计算；生成中英文回复模板；定时后台运行 | ★★★★ 邮件层同构。我们缺翻译接线（G4） |
| **Agentic MailBot**（学术项目） | LangChain + LangGraph；邮件分类「客服查询 / 订单生命周期查询」；Type A 走 RAG 回答，Type B 走 ReAct Agent + SQL 工具查动态数据 | ★★★ 分类路由思想 ≈ 我们的 Dispatcher（rules_only/llm/auto）+ 33 skill 池 |
| **FlowPilot / Distill AI** | FlowPilot：多模型 triage → 专业子 Agent，高风险操作走人工审批门；Distill AI：RFQ 邮件/PDF 七阶段解析，异常路由人工审核队列 | ★★★★ 审批门 + 状态机路由同构 |

两条路线：**A 快速原型 2-3 周**（Dify Human Input 节点做邮件审批）；**B 生产级 4-6 周**（n8n 编排 + LangBot/Chatwoot 接微信/飞书/钉钉 + Langfuse 可观测 + Docker Compose/Nginx/SSL）。

三个风险：① 报价准确性 → 确定性定价引擎规避；② 人工审核延迟 → **2 小时未审自动通知备用审核人**；③ OpenClaw「画图」语义二义（AI 生图 vs 排版 PDF）。

---

## 2. 逐环对照（外部组件 → livekernel 实现）

| 外部环节 | livekernel 对应物 | 证据（file:line） | 判定 |
|---|---|---|---|
| Python IMAP 收邮件 | MailPuller 租约认领 + pending.jsonl 队列；QQ/Gmail 双服务 | `services/mail_puller.py:317` `_enqueue_pending_from_mailbox`；`:348` `mark_state`；`:433` 租约回收；`services/gmail_imap.py` | ✅ 已实现且更深（幂等/租约/双服务/claim race 修复） |
| 邮件多模态解析（Dify workflow） | 多入口 intake + FunASR 语音 + 图纸/PDF 解析 | `services/intake.py`、`services/intake_pdf.py`、`services/file_intake.py`、`services/asr_engine.py`；skills `parse-rfq`/`rfq-extraction` | ✅ 已实现（PDF/语音/图纸三模态） |
| RAG 知识库（RAGFlow / Dify KB） | 四层本地 RAG 网关 + ingestion | `services/rag_layers.py:4-7`（L1 客户/L2 历史报价/L3 对话/L4 工艺）；`:91` `LayeredRAGGateway`；`services/rag.py`、`services/rag_search.py`；skill `rag-ingest` | ✅ 已实现且**无云调用面**（离线铁律） |
| OpenClaw skill 调用（`openclaw infer`） | 33 个 NemoClaw skill（SKILL.md + `tool.py:run()` + OpenAI function contract，33/33 全带 tool.py）+ Dispatcher + OpenShell 4 策略 | `skills/` 33 目录（`scripts/count_skills.py --json` 单一数字源）；`services/skill_dispatcher.py`（rules_only/llm/auto）；`openshell/*.yaml`（iron-rule-1/hitl-required/local-only/skill-allowlist） | ✅ 已实现（本地运行时，无外部 CLI 依赖） |
| 确定性定价（外部头号设计原则） | 铁律①：Timo 引擎裁决 + sha256 锁；LLM 响应 schema 无价格字段 | `skills/calc-quote`、`skills/price-expert`；`services/commercial.py`；审计链 `services/audit.py` | ✅ 已实现且是**架构级锁定**（非节点约定） |
| HITL 人工审核（Dify Human Input / Telegram 审批） | verify-gate + approve 端点 + 3 渠道通知 + **超时升级** | `services/verification.py`；`services/api_server.py:569` verify、`:575-593` approve（HITL→HUMAN_APPROVAL→REPLY，落审计）；`services/notify/__init__.py:1-16`（Telegram/Email/Slack，draft_only）；`services/hitl_escalation.py`（G1 超时升级/备用审核人，只通知不代审）；skill `verify-gate` | ✅ 已实现；**G1 于 v6.3.1 补齐**（对照外部风险②） |
| 报价单 PDF（rfq-quote-agent 核心交付物） | **G2 已补齐**：write-reply 草稿携带确定性报价 PDF 附件（content sha256 锁） | `services/quote_pdf.py`（`data/artifacts/{cid}/quote-{cid}-{sha8}.pdf`）；`skills/write-reply/tool.py` 接线；仍 draft_only | ✅ **v6.3.1 补齐**（reportlab 可选依赖，缺库显式降级） |
| SMTP 回复邮件 | write-reply / reply-draft 草稿 + egress 默认 DENY | `services/reply.py`；`services/egress_gate.py:4`（默认 DENY，fail-safe）、`:66` `check()` | ✅ 已实现（草稿态；DENY 是刻意安全设计，非缺失） |
| 多渠道（微信/飞书/钉钉） | notify 3 渠道（email/slack/telegram） | `services/notify/{telegram,email_notifier,slack}.py` | ❌ **缺口 G3**（路线 B 范围） |
| 自动翻译 | `config/models.yaml:11` 仅 usage 字符串提及，未接线 | — | ❌ **缺口 G4**（增强项，非阻塞） |
| 可观测（Langfuse） | 本地 trace + ops 诊断端点 | `services/observability.py`；/v1/ops 14 端点 | ✅ 已实现（本地，无外发） |
| 部署（Docker Compose + Nginx + SSL） | Dockerfile + k8s manifests + GB10 节点 pip 化路径 | `deploy/Dockerfile` 等 8 个入库干净文件；`docs/NODE-DIFF.md` | ✅ 已实现且节点实测 |

---

## 3. 四个缺口（G1–G4）：G1/G2 已补齐，G3/G4 为 backlog

**G1 · HITL 审批超时升级 / 备用审核人** — 外部风险②的直接对照。**v6.3.1 已补齐**：`services/hitl_escalation.py` 按 `config/policy.yaml` `hitl.timeout_hours`（默认 2h）/`backup_approvers` 扫描 pending HITL，超时只通知备用审核人、**绝不代审**（状态机仍须人工 approve）；去重窗口 = 一个 timeout 防通知风暴；审计落 `data/audit/hitl_escalations.jsonl`；MailOrchestrator loop 每周期扫描。测试 `tests/test_hitl_escalation.py`（12）。旧对照（补齐前）：notify 3 渠道仅发送，无超时/升级逻辑（`services/notify/base.py:41,44` 仅 `send`/`send_safe`）。

**G2 · 报价单 PDF 附件闭环** — rfq-quote-agent 的核心交付物。**v6.3.1 已补齐**：`services/quote_pdf.py` 以 reportlab（可选依赖）渲染确定性报价 PDF 至 `data/artifacts/{cid}/quote-{cid}-{sha8}.pdf`，`skills/write-reply/tool.py` 把附件挂进回复草稿，**仍 draft_only**；铁律①延伸 —— `content_sha256` 锁 canonical 报价载荷（不锁 PDF 字节，避开 reportlab 内嵌时间戳）；缺库时显式 `attachment_error` 不静默。测试 `tests/test_quote_pdf.py`（8）。

**G3 · 多渠道（微信/飞书/钉钉）** — 路线 B 范围。记录 backlog，不阻塞交付。

**G4 · 自动翻译** — email-quote-automation 已有；我们仅 usage 字符串（`config/models.yaml:11`）。记录 backlog：L3 链已能处理英文 RFQ，翻译是增强非阻塞。

---

## 4. 边界判定：为何 Dify/n8n 不作系统本体

1. **铁律①冲突**：Dify 工作流内 LLM 节点可被编排产出价格 → 破坏「LLM 永不定价」的架构级锁定。我们的锁定在引擎层（Timo 裁决 + sha256），不依赖节点配置约定。
2. **双系统真相**：状态机/审计链/哈希校验在 livekernel，业务流程在 Dify → 审计断裂，无法回答「这封报价谁批准的、依据哪一版价格」。
3. **环境约束**：RAGFlow/Dify 需常驻服务栈；比赛节点实测无 docker 权限（`docs/NODE-DIFF.md`），pip 化部署路径已通。
4. **结论**：外部方案只作叙事/证据/方法学引用；**代码禁入 livekernel 仓体**（融合边界，同 v7 §5）。

---

## 5. omni 联动融合方案（已拍板：叙事证据 + 补 G1/G2；v6.3.1 已交付）

- **Route 1 · 叙事证据（零代码）**：本文件 + README「生态定位」节 — 答辩时证明「方法学与主流一致，且我们已交付」。
- **Route 2 · 补缺口（TDD 增量）**：G1 + G2 已于 **v6.3.1** 落地（20 个新测试），全量回归守护。
- **G3/G4**：backlog 记录在案，不阻塞。
- **时间账**：外部评估「2-3 周跑通 / 4-6 周生产」；livekernel 现状 = 778 测试全绿 + GB10/aarch64 节点实测（700 passed / 45 skipped）+ 13 标签 UI 全端点接线 + G1/G2 缺口补齐。**外部方案描述的是我们已交付系统的子集。**

---

## 6. 总裁定

1. 外部 4 项目 + Dify/n8n 栈与我们逐环同构；差异化在：确定性定价的**架构级锁定**、SHA-256 审计链、egress DENY、ARM 节点实测。
2. 不引入任何外部代码/依赖（融合边界）；G1/G2 以 TDD 自建补齐。
3. 本文件 + README 生态定位 = 交付叙事的「行业对照」证据链，与 v7 §5 负面对照互补：**v7 是野生生产系统反面（证明痛点真实），v8 是开源生态正面（证明路线主流且我们超前）**。
