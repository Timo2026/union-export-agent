# ARCHITECTURE.md — L0–L10 到代码的可追溯映射（Live-Kernel Edition）

> 冻结架构（L0–L10 + 双控制回路 + 五层记忆 + 辟牟援推止）来自 `新建文件夹.zip/ARCHITECTURE.md`（v1.0），
> 本文档**不改架构**，只补充「每一层落在本主干哪个文件」，实现规格↔代码可追溯。

## 分层 → 实现映射

| 层 | 冻结规格 | 本主干实现 | 状态 |
|----|----------|-----------|------|
| L10 UX/Ops | RFQ Cockpit / HITL / CRM | `scripts/run_demo.py`（CLI 驾驶舱）· `data/crm.sqlite3` | ✅ 演示级 |
| L9 Channels | Email/CRM/ERP | `services/intake.py`（email）· `services/crm_memory.py` | ✅ Email+CRM |
| L8 Control Plane | Context + CAT + State Machine + Policy | `services/context_engine.py` · `agents/cat_controller.py` · `services/rfq_state_machine.py` · `config/policy.yaml` | ✅ |
| L7 Agent Layer | Supervisor/Sales/Mfg/Commercial/Verification | `agents/cat_controller.py`（Supervisor 编排）· `services/reply.py`（Sales）· `services/verification.py`（Verification） | ✅ 编排级 |
| L6 Skill Layer | rfq/dfm/quote/freight/crm/memory… | `services/intake.py`(rfq-extraction) · `adapters/timo_adapter.py`(dfm+cnc-quote) · `services/rag.py`(historical) · `services/crm_memory.py`(crm-sync) | ✅ 核心技能 |
| L5 Memory Fabric | Working/Fact/Semantic/Artifact/Episodic | Working=`Context` · Fact=`crm.sqlite3` · Semantic=`services/rag.py`(funasr) · Artifact=`data/contexts/*.json` · Episodic=`services/audit.py` | ✅ |
| L4 Multimodal | Email/OCR/VLM/STEP/ASR/Embed | `adapters/funasr_adapter.py`(ASR/RAG) · `services/intake.py`(email/voice/step 归一) | ✅ ASR+Email+STEP接口 |
| L3 Model Mesh | FAST/VISION/REASON/EMBED/ASR/DETERMINISTIC | `config/settings.yaml → model_router` · DETERMINISTIC=Timo 内核 | ✅ 配置就绪 |
| L2  Runtime | NeMo/NIM/Retriever/Guardrails | 见 `docs/-MAPPING`（Profile C，P2）· Guardrails=`services/verification.py`+policy | 🚧 P2 |
| L1 GPU/Container | DGX OS/CUDA | `scripts/start_engine.py` · 引擎 docker-compose.*.yml | 🚧 部署支持 |
| L0 Hardware | DGX Spark/GB10/128GB | 目标平台；本机为 CPU+已运行的本地服务 | 🚧 目标 |

## 双控制回路

- **Loop A — CAT**（`agents/cat_controller.py`）：`Context → Action(_action 落审计) → Test(Verification) → Context`。
  Action 内部即 ReAct（推理-行动-观察），但**不对外暴露隐藏思维链**，只保留结构化 action/evidence/tool 结果/验证结论。
- **Loop B — 业务状态机**（`services/rfq_state_machine.py`）：
  `NEW→INTAKE→STRUCTURING→DFM→QUOTING→VERIFY→REPLY→CRM_MEM→DONE`，分支 `→BLOCKED/HITL`，非法转移抛异常。

## 六条工程铁律（写死）

1. LLM 不负责最终价格 → 报价只来自 `TimoAdapter`（真实 `calc_quote`）。
2. State Machine 是业务真相 → Agent 不能绕过 policy 标 DONE。
3. Context 是全链路唯一业务上下文 → `context_id` 贯穿证据/审计/CRM。
4. RAG 提供证据不改事实 → `services/rag.py` 只产出 evidence。
5. 多模态冲突必须升级 → `intake.detect_multimodal_conflict` → HITL，不静默覆盖。
6. GPU/本地模型是 AI Runtime，不是业务逻辑。

## 数据流（黄金链）

```
email_text ─┐
voice ──ASR─┤→ intake.extract_rfq / extract_voice_claims → canonical RFQ + claims
step ───────┘                                              │
                                          detect_multimodal_conflict
                                                            ↓
Context(context_id) ── State Machine ── TimoAdapter.conflict_check(辟) ──┐
                                                          TimoAdapter.quote(数字)
                                                            ↓
RAG evidence(援) → Verification(辟牟援推止) → {PASS|HITL|BLOCKED}
                                                            ↓
                          reply.build_reply(draft_only) → CRM+Memory → AuditChain(SHA-256)
```
