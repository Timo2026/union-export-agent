# NVIDIA-MAPPING.md — NVIDIA 栈映射与诚实边界（P2）

对齐冻结 PRD §3 与当前 NVIDIA 官方文档复核。原则：**NVIDIA 是本地 AI Runtime，不是业务逻辑**；
CNC 价格/毛利/客户主数据/法规/业务状态的"真相"永远在确定性系统里。

## 栈映射（组件 → Union 角色 → 本仓库落点 → 优先级）

| 层 | NVIDIA 组件 | Union 角色 | 本仓库落点 | 优先级 | 本机状态 |
|----|------------|-----------|-----------|--------|---------|
| Hardware | DGX Spark / GB10 / 128GB | 本地 AI 节点 | `deploy/profiles.yaml` B/C | P0 | 目标平台（本机为 CPU + 已运行本地服务） |
| Agent 契约 | `nemo-agents-spec-v1` / `agent.yaml` | 可部署契约 | `config/agent.yaml` + `services/agent_spec.py` | P1 | ✅ 契约模板 + 自洽校验 |
| Runtime | NeMo Fabric | 执行抽象 | `deploy/k8s.yaml`（Profile C） | P1 | 🚧 部署清单就绪，未接 Fabric |
| Inference | NIM | 受支持模型服务 | `services/model_router.py`（backend=nvidia） | P1 | 🚧 路由就绪；本机无 NIM → 探测失败显式降级 |
| RAG | NeMo Retriever | 多模态抽取/embed/rerank | `services/rag.py` + funasr（local 后端） | P1 | ✅ 本地 funasr RAG；Retriever 为 Profile C 后端 |
| Safety | NeMo Guardrails | 输入/工具/输出策略 | `services/guardrails.py`（builtin 强制）+ `config/guardrails/nemo/{config.yml,rails.co}`（colang 契约） | P1 | ✅ builtin 强制执行+测试；nemo colang 工件就绪，`backend` 可切换 |
| ASR | 本地 FunASR/Qwen3-ASR | P0 本地语音 | `adapters/funasr_adapter.py` | P0 | ✅ 在线命中 :8866/:8089；离线显式 MOCK |
| ASR | Parakeet NIM | 可选（需受支持 GPU） | `agent.yaml` nvidia_nim.ASR | P2 | ⛔ 见下方现实约束 |
| Optimisation | TensorRT-LLM | 加速路径 | Profile C 备注 | P2 | 🚧 未接 |
| Serving | Triton | 多模型服务 | Profile C 备注 | P2 | 🚧 未接 |
| Observability | OTEL / DCGM | 端到端 trace + GPU 指标 | `services/observability.py` | P1/P2 | ✅ OTEL 风格 trace/span/metrics（JSONL + 可选 OTLP） |

## 已核验的现实约束（不硬编码过时假设）

1. **CAT 非 NVIDIA 官方术语**：Context→Action→Test 是本项目自定义工程控制回路；ReAct 是 Agent 内部行动-观察循环。
   产品界面/审计**不暴露隐藏思维链**，只保留结构化 action/evidence/tool 结果/验证结论。
2. **Parakeet 自托管音频 NIM 不支持 Blackwell / compute capability 12.0**：因此 DGX Spark 上 **P0 本地 ASR 用
   FunASR/Qwen3-ASR**，Parakeet 仅作"有实际受支持 GPU"时的可选后端（Profile D）。
3. **单台 DGX Spark 不能全模型永久常驻**：模型按任务路由 + 生命周期管理（Model Mesh 角色化），避免"所有模型常驻"。
4. **旧 Triton `*-py3-trtllm` backend 容器已退出 PB6**：生产部署以当前受支持 NIM/Triton/vLLM 路径为准，不写死旧容器。
5. **NCP-AAI 考题数字各源不一**：不作为产品需求，仅作架构对齐语言。

## NVIDIA 不拥有的东西（确定性真相）

```
CNC price truth · margin policy truth · customer master truth · regulatory truth · business state truth
```
这些留在 Timo 内核 / policy.yaml / commercial.yaml / CRM(SQLite/Postgres) / 状态机里，**LLM 与 NIM 都不生成最终数字**。

## 切换 backend（不改架构）

`config/settings.yaml → model_router.backend`：`local`(funasr/ollama) | `nvidia`(NIM) | `mock`。
`config/settings.yaml → guardrails.backend`：`builtin` | `nemo`。
上层 Context / Skill / Agent / API 契约不变 —— 即冻结 PRD 的"Replace the adapters, not the architecture"。
