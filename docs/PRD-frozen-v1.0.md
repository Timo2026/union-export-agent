# Union Manufacturing Export Agent
## PRD + Final Architecture + Golden Path Notebook

**版本：v1.0 / 2026-09-17**  
**产品定位：Manufacturing B2B Export Agent — From RFQ to Revenue**

### 冻结方案

```text
Email / Voice / PDF / STEP / Excel
                ↓
        Multimodal Intake
                ↓
          Context Engine
                ↓
       CAT Controller
 Context → Action → Test
                ↓
  Sales / Manufacturing / Commercial
                ↓
       Timo2026 Core
                ↓
 RAG Evidence + Verification
                ↓
      辟·牟·援·推·止
                ↓
          HITL Gate
                ↓
       English Reply
                ↓
       CRM + Memory
                ↓
    Postmortem / Learning
```

> **重要边界**：CAT 是本项目自定义的工程控制回路，不是 NVIDIA 官方产品术语。ReAct 作为 Agent 内部的行动-观察循环；不在产品界面或审计中暴露隐藏思维链，仅保留结构化行动、证据、工具结果和验证结论。


## 0. 来源、证据边界与本版本的处理原则

本 PRD 以以下材料为设计基线：

1. **用户提供的 Union Export Agent 合成方案**：Email / Voice / PDF / STEP → Context → RFQ → DFM → Quote → 验证 → HITL → Email → CRM/Memory；Timo2026 制造内核；FunASR / Qwen3-ASR；五层记忆；FAST / VISION / REASON / EMBED / ASR 路由；SHA-256 审计链；S1-S5 回归。
2. **NVIDIA NCP-AAI 认证知识材料**：自主 Agent、多 Agent、ReAct、分层记忆、RAG、NeMo Agent Toolkit、Guardrails、NIM、Triton、评测、观测、HITL 等作为架构对齐语言。该材料中的“考试标准答案”“真题覆盖率”等表述不视为 NVIDIA 官方产品要求。
3. **现有 Timo2026 / Union 工程资产**：`cnc-ai-brain`、`openclaw-cnc-core`、`cnc-quote-rag-system`、`cnc-smart-quote-system` 等作为制造能力来源。
4. **当前 NVIDIA 官方文档复核**：本版本对 DGX Spark、NeMo Platform / Fabric、NeMo Retriever、当前音频支持矩阵等做了额外校验。

### 关键现实修正

- 当前 NVIDIA NeMo Platform 新 Agent 推荐使用 `nemo-agents-spec-v1` 的 `agent.yaml`，Fabric 是执行层；legacy NAT workflow 仍可兼容。 
- 当前 NeMo Retriever 文档显示 Parakeet 自托管音频 NIM 在当前版本有受支持 GPU 限制，Blackwell / compute capability 12.0 不在自托管 Parakeet 支持范围内。因此 **DGX Spark 上不把 Parakeet NIM 作为 P0 本地 ASR**；P0 使用本地 FunASR / Qwen3-ASR，Parakeet 作为可选后端，仅在实际硬件支持时启用。
- 当前 NVIDIA 生命周期文档指出 Production Branch 6 已移除旧的 Triton `*-py3-trtllm` backend 容器变体，因此不要把该旧容器形式写死进生产部署；以当前受支持 NIM / Triton / vLLM 路径为准。


# 1. Product PRD

## 1.1 Problem

制造业外贸业务把工程事实、商业规则、客户沟通和历史经验散落在邮件、图纸、语音、报价单、ERP/CRM 和工程师脑中。

普通外贸 Agent 可以读邮件、写邮件，但无法可靠完成：

- RFQ 参数结构化
- 图纸 / STEP 理解
- DFM / 工艺冲突判断
- 确定性报价
- 交期与物流约束
- 毛利红线控制
- 证据回溯
- 客户长期记忆
- 成交/丢单后复盘

## 1.2 Product goal

把“一个询盘”变成“一个可审计、可验证、可复盘的业务决策对象”。

## 1.3 Non-goals

第一阶段不做：

- 自主 CAD 创作
- 自主 CAM / G-code 生产
- 无人值守自动发送高风险报价
- 把 LLM 当价格数据库
- 为了展示 NVIDIA 而重写已有制造内核

## 1.4 Target users

**Primary**：制造业外贸业务员 / Sales Engineer  
**Secondary**：工艺工程师 / 报价工程师 / 管理者  
**Admin**：AI/IT 运维人员

## 1.5 Core use cases

### UC-01 正常询盘
Email + Drawing + STEP → 自动解析 → DFM → Quote → Reply Draft

### UC-02 询盘信息缺失
Agent 识别材料、数量、表面处理、精度、交期等缺失项 → 生成补问

### UC-03 多模态冲突
Email 写 ±0.02 mm，Voice 写/说 0.05 mm → 不静默覆盖 → HITL

### UC-04 工艺硬冲突
304 + anodizing → BLOCKED + 给出可行替代方案

### UC-05 高风险精密订单
TC4 + IT5 → HITL，不自动发送

### UC-06 业务闭环
Quote → Won/Lost → Actual cost → Postmortem → Memory → 下次报价


# 2. System Architecture: L0-L10 + 2 control loops

```text
L10  UX / Ops
     RFQ Cockpit / HITL / Approval / CRM
                ↑
L9   Business Channels & Integrations
     Email / CRM / ERP / Freight / Customs
                ↑
L8   Control Plane
     Context + CAT + State Machine + Policy
                ↑
L7   Agent Layer
     Supervisor / Sales / Manufacturing / Commercial / Verification
                ↑
L6   Skill Layer
     RFQ / PDF / STEP / DFM / Quote / Freight / Customs / CRM / Memory
                ↑
L5   Memory Fabric
     Working / Fact / Semantic / Artifact / Episodic
                ↑
L4   Multimodal Intelligence
     Email parser / OCR / VLM / STEP parser / ASR / Embed / Rerank
                ↑
L3   Model Mesh
     FAST / VISION / REASON / EMBED / ASR
                ↑
L2   NVIDIA AI Runtime
     NeMo Platform/Fabric / NIM / Retriever / Guardrails / observability
                ↑
L1   GPU / Container Runtime
     DGX OS / CUDA / Container Runtime
                ↑
L0   Hardware
     DGX Spark / GB10 / 128GB unified memory / network
```

### Control Loop A — CAT

```text
Context → Action → Test → Context
```

### Control Loop B — Business State Machine

```text
NEW → INTAKE → STRUCTURING → DFM → QUOTING → VERIFY
                                      ↘ BLOCKED
                                      ↘ HITL
VERIFY → REPLY → CRM_MEM → DONE
HITL → HUMAN_APPROVAL → REPLY / BLOCKED
BLOCKED → ARCHIVED
```


# 3. NVIDIA architecture and configuration

## 3.1 Hardware policy

### P0: Single DGX Spark first

DGX Spark 是本地 AI 节点，不把它当作业务逻辑层。128GB unified memory 用于多模型、RAG、VLM 和 Agent 开发/推理；模型按任务路由与生命周期管理，避免“所有模型永久常驻”。

### P1: Optional second GPU / external accelerator

当特定 NIM（尤其 ASR）有硬件支持限制时，通过独立 ASR 服务、第二 GPU 或受支持的服务器承载，不破坏上层 Context / Skill / Agent API。

## 3.2 Current NVIDIA stack mapping

| Layer | NVIDIA component | Union role | Priority |
|---|---|---|---|
| Hardware | DGX Spark | local AI node | P0 |
| Agent config | `nemo-agents-spec-v1` / `agent.yaml` | deployable contract | P1 |
| Runtime | NeMo Fabric | execution abstraction | P1 |
| Agent tooling | NeMo Agent Toolkit / legacy NAT | evaluation / compatibility | P1 |
| Inference | NIM | supported model serving | P1 |
| RAG | NeMo Retriever | multimodal extraction/embed/rerank | P1 |
| Safety | NeMo Guardrails | input/tool/output policy | P1 |
| ASR | local FunASR/Qwen3-ASR on Spark | P0 local speech path | P0 |
| ASR | Parakeet NIM | optional if hardware-supported | P2 |
| Optimisation | TensorRT-LLM | supported acceleration path | P2 |
| Serving | Triton | multi-model serving when justified | P2 |
| Observability | OTEL / DCGM | end-to-end tracing + GPU metrics | P1/P2 |

## 3.3 What NVIDIA should NOT own

- CNC price truth
- margin policy truth
- customer master truth
- regulatory truth
- business state truth

These stay in deterministic systems / policy / enterprise data.


# 4. Model Mesh and Model Router

## FAST

邮件分类、字段抽取、CRM 草稿、简单改写。

## VISION

PDF、图纸截图、图片和版面结构；模型只输出感知结果和引用，不直接决定价格。

## ASR

语音 / 视频中的客户约束、承诺、变更。

## EMBED / RERANK

历史 RFQ、案例、邮件、语音 transcript、技术经验的检索。

## REASON

复杂 DFM、冲突分析、证据综合、商业风险判断。

## DETERMINISTIC

报价、状态机、毛利红线、工艺硬规则、金额计算、CRM 主数据约束。

### Routing principle

```text
LLM/VLM/ASR = 感知 + 理解 + 规划
RAG          = 证据
Rules        = 约束
Geometry     = 事实
Quote Engine = 数字
Agent        = 决策协调
Human        = 最终授权
```


# 5. Multimodal Intake + ASR Multimodal RAG

```text
Email ───────┐
PDF ─────────┤
Image ───────┤
STEP ────────┤→ Normalizer → Context
Excel ───────┤
Voice ── ASR ┤
Video ───────┘
```

## 5.1 Canonical evidence object

```json
{
  "evidence_id": "EV-...",
  "source_type": "email|pdf|step|audio|video|crm",
  "source_ref": "artifact://...",
  "customer": "...",
  "context_id": "RFQ-...",
  "content": "...",
  "timestamp": "...",
  "confidence": 0.95,
  "claims": [],
  "checksum": "sha256:..."
}
```

## 5.2 Voice → RAG

```text
Audio / Video
    ↓
ASR
    ↓
Timestamped segments
    ↓
Semantic chunks
    ↓
Embedding
    ↓
Vector / Hybrid retrieval
    ↓
Rerank
    ↓
Evidence
    ↓
Context
```

**关键规则**：语音只是证据源之一。它不能静默覆盖邮件或图纸中的 canonical field；冲突进入 verification/HITL。

## 5.3 Local ASR decision

P0：FunASR / Qwen3-ASR 本地服务。  
P2：若部署环境有受支持 GPU，再启用 Parakeet NIM。  
P2：视频走 audio + OCR/fusion；不要求一次性把所有模态放进一个模型。


# 6. Context Engine

每个业务实例拥有一个 `context_id`，全链路共享：

```text
Customer
RFQ
Conversation Summary
Documents
Geometry
Manufacturing
Commercial
Retrieved Evidence
Risk
Decision
Human Actions
Events
```

### Context assembly policy

只把“当前决策需要的信息”注入模型：

1. 当前状态
2. 当前任务
3. canonical RFQ
4. 最近对话摘要
5. 必需 evidence
6. 相关历史案例
7. 规则 / policy
8. 工具结果

不要把所有历史全文无差别塞进 prompt。


# 7. Memory Fabric

| Memory | Store | 保存什么 | 是否进入默认 Context |
|---|---|---|---|
| Working | session/checkpoint | 当前任务状态 | 是 |
| Fact | PostgreSQL | RFQ/Quote/Order/Customer | 按需 |
| Semantic | Vector DB / Retriever | 案例/邮件/技术经验 | 按检索 |
| Artifact | filesystem/object storage | PDF/STEP/audio/video | 按引用 |
| Episodic | event store | Tool/Agent/HITL/action trace | 按需 |

### 不允许的做法

“把所有历史消息拼成长字符串，再交给模型。”

### 正确做法

```text
SQL facts
+ semantic retrieval
+ artifacts by reference
+ summarized working memory
+ episodic trace
→ Context Compiler
```


# 8. Agent Layer / Skill Layer

## Agents

- **Supervisor Agent**：任务拆解、路由、状态推进，不负责业务数字。
- **Sales Agent**：Email、RFQ、客户补问、回复草稿、CRM。
- **Manufacturing Agent**：STEP、DFM、工艺、报价准备。
- **Commercial Agent**：运费、Incoterms、交期、毛利。
- **Verification Agent**：证据、冲突、政策、风险、HITL。

## Skills

```text
email-intake
rfq-extraction
pdf-understanding
step-analysis
dfm
cnc-quote
freight
customs
incoterms
margin-check
historical-rag
voice-evidence
verification
human-review
crm-sync
postmortem
```

Skill 必须具备：

- 输入 Schema
- 输出 Schema
- tool contract
- failure policy
- evidence requirement
- test cases
- timeout / retry / circuit breaker policy


# 9. Deterministic business core

## Quote

```text
Material
+ Machining
+ Setup
+ Tooling
+ Surface
+ Inspection
+ Labor
+ Packaging
+ Freight
+ Customs / duties (when applicable)
+ Risk allowance
+ Margin
= Commercial Quote
```

**LLM 不生成最终数字。**

## Policy

```text
IF DFM hard conflict → BLOCKED
IF unresolved multimodal conflict → HITL
IF margin < floor → BLOCKED
IF precision risk high → HITL
IF evidence insufficient → HITL
IF customer approval required → HITL
```

## Business state is authoritative

只有 State Machine 能推进：`NEW → ... → DONE`；Agent 不能绕过 policy 直接标记完成。


# 10. “辟·牟·援·推·止” Verification Loop

这是业务验收循环，不让模型自由发挥。

| 步骤 | 含义 | 强制检查 |
|---|---|---|
| 辟 | DFM 冲突 | 材料/表面/公差/工艺硬冲突 |
| 牟 | 商业风险 | 历史利润、客户风险、异常订单 |
| 援 | 证据支撑 | RAG / 图纸 / 客户沟通是否支持结论 |
| 推 | 承诺一致性 | 原材料、产能、交期、物流是否支持承诺 |
| 止 | 红线熔断 | 毛利低于门槛 / 无法可靠报价 |

### Output

```json
{
  "status": "PASS|HITL|BLOCKED",
  "checks": [],
  "reasons": [],
  "evidence": [],
  "next_action": "..."
}
```


# 11. Human-in-the-loop / Guardrails / Audit

## HITL policy

```text
Low risk + complete evidence      → draft / optional auto flow
Medium risk                       → human review recommended
High risk / conflict              → mandatory HITL
Hard block                         → BLOCKED; no send
```

### Never auto-send when

- DFM hard conflict
- multimodal source conflict
- margin redline
- critical tolerance ambiguity
- high-value RFQ without policy approval
- customs / regulatory uncertainty beyond policy threshold

## Guardrails

输入前：prompt injection / dangerous content / data policy  
工具中：tool allow-list / parameter schema / rate / timeout  
输出后：quote schema / forbidden promises / external send policy

## Audit

SHA-256 chained event log only guarantees **tamper-evident record integrity**. It does not prove the decision was correct.


# 12. Data model

Core tables:

```text
customers
contacts
rfqs
rfq_items
requirements
documents
manufacturing_analysis
dfm_results
quotes
quote_items
freight_quotes
customs_records
emails
conversations
agent_runs
agent_actions
tool_calls
orders
actual_costs
actual_leadtime
postmortems
knowledge_updates
```

## Canonical RFQ

```json
{
  "rfq_id": "RFQ-...",
  "customer_id": "CUST-...",
  "part": {},
  "quantity": 500,
  "material": "AL6061",
  "process": "CNC",
  "tolerance": "±0.02mm",
  "surface_finish": "anodizing",
  "inspection": {},
  "delivery": {},
  "shipping": {},
  "incoterms": "FOB",
  "missing_information": [],
  "conflicts": []
}
```


# 13. API contracts

## `POST /v1/rfq/intake`

```json
{
  "customer": {...},
  "email": {...},
  "attachments": [...],
  "audio": [...]
}
```

## `POST /v1/rfq/{id}/analyze`

Returns RFQ, DFM, evidence and missing information.

## `POST /v1/rfq/{id}/quote`

Returns deterministic quote engine result.

## `POST /v1/rfq/{id}/verify`

Runs `辟·牟·援·推·止` and produces PASS / HITL / BLOCKED.

## `POST /v1/rfq/{id}/approve`

Human approval is explicit and audited.

## `POST /v1/rfq/{id}/reply-draft`

Generates external communication draft.

## `POST /v1/rfq/{id}/crm-sync`

Writes business facts and memory references.


# 14. Reliability and observability

Tool failures follow:

```text
Timeout → exponential backoff → limited retry
Persistent failure → circuit breaker
Schema mismatch → fail fast
Repeated agent failure → HITL / incident
```

Track:

### Business
- RFQ field accuracy
- missing-information recall
- DFM conflict recall
- quote deviation
- gross margin deviation
- hit-rate / response time
- HITL trigger accuracy

### Agent
- tool-call accuracy
- task completion
- unsupported-claim rate
- evidence coverage
- state-transition correctness

### System
- TTFT
- E2E latency
- retrieval latency
- queue latency
- GPU utilization
- VRAM / unified-memory pressure
- error rate
- circuit-breaker trips

OTEL traces should correlate:

```text
context_id
 → agent_run
 → skill
 → tool_call
 → model request
 → retrieval
 → verification
 → human action
```


# 15. Security / data residency

产品承诺可以定义为：

> **业务主数据、客户文件、图纸、语音和 Agent memory 默认本地处理；外部 API 必须显式授权。**

## Policy layers

```text
Network egress allow-list
Secrets manager
PII / credential redaction
Tool allow-list
External-send approval
Artifact checksum
Audit chain
Local model preference
```

“数据不出车间”是部署策略，而不是单靠 Prompt 实现；必须从网络出口、模型 endpoint、对象存储、日志与第三方 API 一起控制。


# 16. Deployment profiles

## Profile A — Demo / Laptop

```text
Python + fallback
SQLite / local vector
Mock ASR
No GPU dependency
```

## Profile B — DGX Spark P0

```text
DGX Spark
+ local model server
+ FunASR/Qwen3-ASR
+ Timo2026 HTTP adapter
+ local vector DB
+ PostgreSQL
+ object storage
+ OTEL
```

## Profile C — NVIDIA production / lab

```text
NeMo Platform / Fabric
+ agent.yaml
+ NIM for supported models
+ Retriever
+ Guardrails
+ OTEL / DCGM
+ Docker / K8s
```

## Profile D — scaled ASR

ASR 服务独立部署在**实际支持 Parakeet 的 GPU**或其他本地 ASR 服务上；上层协议保持不变。


# 17. Repository consolidation

不要继续增加孤立仓库。把现有资产收敛成一个产品主干：

```text
union-export-agent/
├── agents/
├── skills/
├── services/
│   ├── context/
│   ├── rfq/
│   ├── manufacturing/
│   ├── commercial/
│   ├── memory/
│   └── crm/
├── adapters/
│   ├── timo2026/
│   ├── funasr/
│   ├── nemo/
│   └── openclaw/
├── policies/
├── schemas/
├── evaluation/
├── config/
└── notebooks/
```

### Timo2026 mapping

| Existing asset | Target role |
|---|---|
| `cnc-ai-brain` | deterministic manufacturing / quote / audit core |
| `openclaw-cnc-core` | STEP + CNC skill / adapter |
| `cnc-quote-rag-system` | historical manufacturing retrieval |
| `cnc-smart-quote-system` | probing / adversarial verification concepts |
| `dashuai-coach` | manufacturing analysis / human guidance |
| `UniSkill` | generic skill conventions where reusable |


# 18. Roadmap

## P0 — Golden Path

**Email → RFQ → DFM → Quote → Verify → HITL → Reply → Memory**

Deliverables:

- Context Engine
- State Machine
- Timo adapter
- deterministic policy
- audit chain
- 5 golden tests

## P0.5 — Multimodal

- local ASR
- PDF/image/STEP ingestion
- evidence object
- hybrid retrieval
- Email/Voice conflict

## P1 — Business extension

- freight
- customs
- Incoterms
- margin policy
- CRM sync
- customer memory

## P2 — NVIDIA platformization

- `agent.yaml`
- NeMo Fabric
- NIM for supported models
- NeMo Retriever
- Guardrails
- OTEL/DCGM
- Docker/K8s

## P3 — Closed loop

- Win/Loss
- actual cost
- lead-time deviation
- postmortem
- retrieval updates
- controlled model/agent evaluation


# 19. Acceptance criteria

## Golden scenarios

| ID | Input | Expected |
|---|---|---|
| S1 | 6061 × 50 + anodizing | DONE |
| S2 | TC4 × 10 | DONE |
| S3 | 304 + anodizing | BLOCKED |
| S4 | 304 + passivation | DONE |
| S5 | TC4 + IT5 | HITL |
| M1 | Email ±0.02 + Voice 0.05 | HITL / `VOICE_EMAIL_CONFLICT` |

## Structural acceptance

- Every RFQ has a unique `context_id`.
- No illegal state transition is possible.
- No external email is auto-sent unless policy allows it.
- Every tool call is schema validated.
- Every external claim has evidence or explicit uncertainty.
- Every quote is traceable to deterministic inputs.
- Audit chain verifies successfully.
- Offline mode is clearly labeled and cannot masquerade as production output.


# 20. Competition Demo Script

### Input

Customer sends:

- Email
- PDF drawing
- STEP
- Voice note

### On screen

```text
1. Intake                  ✓
2. Context ID              RFQ-YYYYMMDD-xxxxxx
3. Email parse             ✓
4. ASR evidence            ✓
5. Drawing/STEP facts      ✓
6. RFQ normalization       ✓
7. DFM                     ✓
8. Timo quote              ✓
9. RAG evidence            ✓
10. 辟·牟·援·推·止         ✓
11. HITL policy            REVIEW / BLOCKED
12. English reply          ✓
13. CRM                    ✓
14. Audit                  ✓
15. Memory                 ✓
```

### The “hero moment”

Email says `±0.02 mm`. Voice says the critical dimension can be relaxed to `0.05 mm`.

Agent must **surface the conflict**, not pick one silently.

The winning technical story is:

> **The system does not merely generate an answer. It turns heterogeneous customer evidence into a controlled manufacturing business decision.**


# 21. Current-source links used for NVIDIA verification

- NVIDIA NeMo Platform Agents: https://docs.nvidia.com/nemo-platform/latest/documentation/studio/agents
- NVIDIA NeMo Platform deployment: https://docs.nvidia.com/nemo-platform/latest/documentation/agents/deploy-agents
- NVIDIA NeMo Fabric: https://docs.nvidia.com/nemo/fabric/about-nemo-fabric/overview/
- NVIDIA DGX Spark system overview: https://docs.nvidia.com/dgx/dgx-spark/system-overview.html
- NVIDIA NeMo Retriever: https://docs.nvidia.com/nemo/retriever/
- NeMo Retriever audio/video ingestion: https://docs.nvidia.com/nemo/retriever/latest/extraction/audio/
- NeMo Retriever support matrix: https://docs.nvidia.com/nemo/retriever/latest/extraction/support-matrix/


# 22. Executable Golden Path — local, deterministic, backend-aware

The following cells implement the acceptance harness.  They deliberately:

- prefer a real Timo HTTP endpoint when present;
- use an explicit `DEMO_FALLBACK` otherwise;
- use an explicit local-ASR adapter boundary;
- enforce state transitions, verification and HITL;
- demonstrate multimodal conflict handling;
- generate a compact machine-readable result.


# 23. Golden Regression

The notebook reproduces the existing S1-S5 acceptance set and adds the multimodal voice conflict case.


# 24. Result summary

The acceptance harness is intentionally a **structural regression test**, not a production accuracy benchmark.  A real deployment benchmark must use representative historical RFQs, real local models, actual Timo2026 service, and measured cost/latency/quality.


# 25. Production configuration templates

The following configuration is intentionally conservative. Exact field names for a given installed NeMo Platform release must be validated by that release's CLI / schema before production registration.


# 26. Definition of Done

本版本进入工程实施的 DoD：

- [x] Product scope frozen
- [x] L0-L10 architecture frozen
- [x] Context Engine defined
- [x] CAT + ReAct relationship defined
- [x] five-layer Memory defined
- [x] Multimodal ASR-RAG defined
- [x] NVIDIA mapping defined
- [x] current Parakeet / Blackwell constraint handled
- [x] deterministic quote principle frozen
- [x] HITL / Guardrails / Audit defined
- [x] S1-S5 regression harness implemented
- [x] multimodal conflict gate implemented
- [x] production configuration template included

### Next engineering task

**Replace the adapters, not the architecture.**

```text
TimoAdapter      → real cnc-ai-brain / openclaw-cnc-core API
LocalASRAdapter  → real FunASR/Qwen3-ASR service
HybridRAG        → real NeMo Retriever / local vector backend
Model Router     → actual DGX Spark model endpoints
CRM              → actual CRM connector
Email            → actual mailbox connector
```
