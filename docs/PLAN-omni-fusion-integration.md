# 方案 · Omni 模式全项目联动融合（结论先行）

| 字段 | 内容 |
|------|------|
| 版本 | v1.0 · 2026-09-20 |
| 问题 | Nemotron **Omni 多模态**如何在整个项目（邮件 Agent + OpenClaw + V6 + NVIDIA/Spark + 赛题）里联动？ |
| 结论 | **可以融合；Omni = 感知/通道层，不是定价层**；邮件闭环生产路径约 **2–3 周**与外部评估一致，但**赛期主交付仍是 livekernel+证据**，Dify/n8n 作可选运维壳，不替换引擎与控制台 |
| 待确认 | §8 勾选表 |

---

## 1. 结论（三句话）

1. **Omni 进项目的位置是 Model Mesh 的 VISION + ASR + 多模态 Intake**，输出「结构化事实」；**价格永远 Timo**（与 rfq-quote-agent、铁律①同构）。  
2. **联动主轴不变**：邮件驱动 → OpenClaw Skills → livekernel 黄金链 → V6 控制台打标（Provenance）→ HITL → draft_only。  
3. **外部 Dify/rfq-quote-agent/email-quote-automation**：吸收其「确定性定价 + 人工门」原则与邮件层参考；**不把赛题主控换成 Dify**，除非你明确要「运营生产独立于比赛仓」。

---

## 2. Omni 在全链路中的「动线」

```
入站邮件/多渠道
  文本 | PDF/图片图纸 | 语音留言 | STEP（几何）
        │
        ▼
┌──────────────────────────────────────────┐
│  Omni 模式（Nemotron 3 Nano Omni）         │
│  VISION：图纸/PO 截图 → 尺寸/材料/文字事实   │
│  ASR：语音约束 → 文本 claim                │
│  TEXT：分类/抽取草稿（LLM 提议）            │
│  ❌ 禁止输出最终 unit_price                 │
└──────────────────────────────────────────┘
        │ facts + transcript + extracted RFQ
        ▼
┌──────────────────────────────────────────┐
│  OpenClaw Skills（编排）                    │
│  mail.* · parse-rfq · step-analysis        │
│  customer.wiki/rag · followup · notify     │
└──────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────┐
│  livekernel 黄金链（业务真相）               │
│  DFM / calc-quote(Timo) / verify / draft   │
└──────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────┐
│  V6 控制台（审计与人审）                     │
│  标签：MAIL-DRIVEN / AGENT / OMNI-FACT     │
│        / ENGINE / HITL / BLOCKED           │
└──────────────────────────────────────────┘
        │ 批准后
        ▼
  egress（默认 DENY）→ SMTP 草稿/发送
```

### Omni 能力映射到既有角色

| Omni 输出 | model_router 角色 | 替换/增强的旧件 | 降级 |
|-----------|-------------------|-----------------|------|
| 图纸/图片事实 | **VISION** | mock / 分离 VLM | 规则 OCR / 人工填参 |
| 语音转写 | **ASR** | FunASR / Qwen3-ASR / Parakeet 叙事 | 离线 MOCK 显式 |
| 文本理解/分类 | **FAST/REASON（或 Nano4B/Lightning）** | LM Studio qwen 等 | 规则 classify |
| 报价单 PDF 排版 | **非 Omni** | Playwright/ReportLab 模板 | — |
| 产品示意图 | OpenClaw image_generate **可选** | — | 不报价也可交付 |
| **最终价格** | **DETERMINISTIC Timo** | — | 离线 byte-identical |

---

## 3. 与外部「2–3 周邮件闭环」方案的融合判定

| 外部组件 | 是否采用 | 用法 | 不用的理由 |
|----------|----------|------|------------|
| **确定性定价引擎原则** | ✅ 必采 | 已是铁律①；schema 无价格字段 | — |
| **rfq-quote-agent 架构参考** | ✅ 采思想 | 取「引擎出价 + 人审 + 线程内回复」 | 不整仓替换 livekernel |
| **email-quote-automation** | ✅ 参考 | IMAP 细节/多语言模板 | livekernel 已有 mail_puller/orchestrator |
| **Dify Human Input** | 🟡 可选壳 | 若你要可视化工作流运营台 | 赛期主控用 V6 Workbench，避免双编排 |
| **n8n** | 🟡 可选 | 生产自动化替代 cron | 比赛仓不必强绑 |
| **RAGFlow** | 🟡 工具箱已有 | `tools/ragflow` 可作增强检索 | 主 RAG 仍 livekernel rag_layers |
| **OpenClaw infer image generate** | ✅ 技能 | 「画图」二选一见 §4 | 不定价 |
| **LangBot/Chatwoot 多渠道** | 🔵 生产扩展 | 路线 B | 赛期非必须 |
| **Langfuse** | 🔵 可观测 | 有精力再加 | 已有 observability + audit |

**时间口径（对外诚实）**：  
- **生产邮件客服闭环（单渠道）**：2–3 周（路线 A）→ 4–6 周生产加固。  
- **比赛可演示闭环**：以 livekernel 现网黄金链 + Spark/NVIDIA 证据为主，Omni 按门禁分级接入，**不承诺 2–3 周内替换整个架构**。

---

## 4. 「画图报价」澄清（必须拍板）

| 含义 | 技术路径 | 是否 Omni | 是否影响价格 |
|------|----------|-----------|--------------|
| **A. 报价单 PDF** | 引擎结果 + 模板渲染（Playwright/ReportLab） | 否 | 否（只展示引擎数字） |
| **B. 产品/工艺示意图** | OpenClaw `image_generate` 或 Omni 生图 | 可 | 否 |
| **C. 图纸读入** | **Omni VISION / STEP 引擎** | 是 | 否（只出几何事实→引擎） |

**推荐**：赛期主路径 = **C（读图）+ A（出 PDF）**；B 作加分演示。三者都 **禁止** LLM 算价。

---

## 5. 分层联动方案（全项目融合点）

### 5.1 通道层（邮件/语音/图文）

| 融合点 | 动作 |
|--------|------|
| mail.pull | 保持 IMAP；附件分流：文本/PDF/图/音频/STEP |
| Omni | 图+音 → `omni_facts.json` + transcript，写入 context |
| STEP | **仍走几何引擎/OCP**，不靠 Omni「看图估体积」定论 |

### 5.2 OpenClaw Skill 层

| Skill | Omni 相关行为 |
|-------|----------------|
| `mail.classify` | 可用 Omni 文本头；规则兜底 |
| `omni.vision_intake` | **新增薄封装**：调 Omni VISION → schema 事实 |
| `omni.asr_intake` | **新增**：音频 → 文本 claim |
| `parse-rfq` / `extract-specs` | 吃 Omni facts，补齐字段 |
| `calc-quote` | **无 Omni**；只吃结构化参数 |
| `reply-draft` | 可引用「图纸识别要点」，数字来自引擎 |
| `openshell.provenance` | 打标 `OMNI-FACT` + `OMNI-ASR` |

### 5.3 livekernel / 模型面

| 配置 | 目标 |
|------|------|
| `models.yaml` VISION | endpoint → Omni（节点 :9000/v1 或 NIM） |
| `models.yaml` ASR | Omni；失败 → FunASR |
| `settings.dgx-spark-nvidia.yaml` | roles 指向 Nemotron Omni / Nano4B / Lightning |
| Guardrails | 输出侧：若 VLM 试图给价格字段 → block |
| 审计 | `perception_source: omni|ocr|human|mock` |

### 5.4 V6 控制台

| UI | 内容 |
|----|------|
| Inbox 标签 | 增加 **OMNI** 徽章（本单是否用了多模态） |
| Inspector Provenance | Omni 调用链、附件类型、facts 摘要、与引擎参数 diff |
| 冲突提示 | Omni 抽的材料 vs 邮件正文不一致 → HITL |
| 不做什么 | 控制台不直接展示「Omni 建议价」 |

### 5.5 双记忆（RAG + Wiki）

| 层 | Omni 的作用 |
|----|-------------|
| RAG ingest | 图纸 OCR 文本、语音 transcript 入库 |
| Wiki compile | 客户页增加「常发图纸类型/语言/语音偏好」 |
| 检索回答 | 引用时标注来自 OMNI-FACT 或 ENGINE |

### 5.6 NVIDIA / Spark

| 项 | 说明 |
|----|------|
| 门禁 | Omni 权重/aarch64 可用性 ∈ `00-gates.txt` |
| 驻留 | 峰值：Timo + Nano4B + Embed；**Omni 按需加载**（多模态重） |
| 口播 | 未跑通 Omni 只宣称 N0–N1；跑通 VISION/ASR 再到 N2–N3 |
| 回退 | 无 Omni：mock VISION + FunASR，控制台标 degraded |

### 5.7 比赛叙事

> **Omni 让 Agent「看得见图纸、听得懂语音」，Timo 让 Agent「算得准生意」，OpenClaw+33 Skills 让能力可复用，V6 控制台让人敢授权。**  
> 对照 `email_receiver`：野生自动外发 = 有感知无治理；我们 = **有感知 + 有锁 + 有审计**。

---

## 6. 推荐实施序（融合后）

| 阶段 | 内容 | 周期感 | DoD |
|------|------|--------|-----|
| **O0 确认** | 本方案拍板 + 画图 A/B/C 选择 + 是否引入 Dify 壳 | 当天 | 确认记录 |
| **O1 感知契约** | `omni_facts` schema + guardrails 拒价 + provenance 字段 | 2–3 天 | 单测/文档 |
| **O2 本机模拟** | 无 GPU 时 mock Omni 链路全通（邮件夹图→事实→Timo→草稿） | 2–4 天 | 黄金链+附件 demo |
| **O3 控制台** | OMNI 徽章 + Inspector | 2–3 天 | UI 可筛 |
| **O4 Spark Omni** | 门禁绿则 VISION/ASR 实跑；否则回退标注 | 视硬件 | evidence |
| **O5 生产壳（可选）** | Dify/n8n 只做通知/审批表单，**回调 livekernel API** | 另计 2–3 周 | 与赛仓解耦 |

**与 MASTER PRD 关系**：O1–O3 并入 P3/P4（Skills/控制台/演示）；O4 并入 P2 NVIDIA；O5 不挡比赛交付。

---

## 7. 风险

| 风险 | 缓解 |
|------|------|
| Omni 抽错图纸尺寸 | 引擎/STEP 权威；Omni 仅提示；冲突 HITL |
| 双编排（Dify+OpenClaw+CAT）状态分裂 | 事实源仍 `context_id`+pending；Dify 仅 UI 壳 |
| 用 Omni「顺便报价」 | schema 无 price 字段 + 护栏 + 审计 |
| 显存被 Omni 打爆 | 按需加载；峰值三件套不含 Omni |
| 赛期按 2–3 周生产计划却耽误 Spark 证据 | 比赛主线证据优先，生产壳并行不占 P0 |

---

## 8. 确认清单（请直接回复）

| # | 项 | 选项 |
|---|-----|------|
| 1 | Omni 融合总方向：感知层进全链，价格仍 Timo | □同意 □改 |
| 2 | 编排主控：**OpenClaw + livekernel/V6**（Dify 仅可选壳） | □同意 □改用 Dify 主控 |
| 3 | 画图报价含义 | □C读图+A出PDF（推荐） □必须含B示意图 |
| 4 | 比赛窗口 vs 生产窗口 | □比赛优先证据 □并行生产闭环 |
| 5 | 新增 skill 名 | `omni.vision_intake` / `omni.asr_intake` 是否认可 |
| 6 | 是否现在把方案写入 `email-agent-plan/index.html` 与 MASTER PRD 附录 | □是 □否 |

**推荐默认（可直接打「按默认确认」）**：  
**1 同意 · 2 OpenClaw+V6 主控 · 3 C+A · 4 比赛优先 · 5 认可 · 6 是**

确认后我：① 更新可视化页 ② 在 MASTER PRD 附录挂接 Omni ③ 开 O1 schema/护栏任务。
