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
