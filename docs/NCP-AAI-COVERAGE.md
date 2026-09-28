# NCP-AAI 考点覆盖矩阵 — 本系统的  技术存量（据实盘点）

> 逐条映射 NCP-AAI 7 大模块 → 本仓库**具体产物 + 落地状态**。
> 状态图例：🟢 实跑(有测试/可执行) · 🟡 契约/适配器就绪(配置即生效) · 🔴 受本机无 GPU 限制未实跑(部署清单已给)。
> 本机事实：`nvidia-smi` 无 → 无 GPU；:8000 是引擎自带的**摩尔线程 MUSA vLLM**（非 NIM）。所有"运行时"用 OpenAI 兼容本地模型，NIM/TensorRT-LLM 为**同接口可切换后端**。

## 模块一 · Agent 与多 Agent 架构
| 考点 | 要求 | 本系统产物 | 状态 |
|---|---|---|---|
| 自主 Agent vs 工作流 | 目标+环境反馈+动态决策 | `cat_controller.py`(CAT) + `llm_planner.react_loop`(ReAct 动态选技能) + 状态机反馈路由 | 🟢 |
| 工具集成架构 | 标准化微服务, 非硬编码 | `adapters/`(Timo/FunASR 解耦) + `skill_registry` 标准工具描述 + allow-list | 🟢 |
| 多 Agent 协作 | 分层委派/异步共享内存 | Supervisor + Sales/Mfg/Commercial/Verification 角色 + Context 共享内存 | 🟡(单进程多角色,未拆分布式 broker) |
| 图式编排 | 顺序+并行+条件分支 | 控制回路 A(CAT)+回路 B(状态机含 BLOCKED/HITL 分支) | 🟢 |
| 故障定位 | 分布式追踪/时序 | `observability.py` trace/span + `audit.py` SHA-256 链 | 🟢 |
| ReAct 循环 | Thought→Action→Observation | `llm_planner.react_loop` + `config/prompts/tool_selection.yaml` | 🟢(测试: allow-list 约束/离线回退) |
| Reflexion/CoT | 自省/任务分解 | 辟牟援推止验证循环即"输出矛盾修正"; CoT 分步在 planner | 🟡 |

## 模块二 · 提示工程 & 工具调用
| 考点 | 本系统产物 | 状态 |
|---|---|---|
| 结构化提示+Few-shot+Schema绑定 | `config/prompts/*.yaml`(5套 system+few_shot) + `llm_planner` response_format + `output_schema` 校验 | 🟢 |
| LLM 驱动工具选择(标准化描述) | `llm_planner.select_tool` + `tool_selection.yaml`(带工具标准化描述) + allow-list 约束 | 🟢 |
| 专项提示(摘要/回复/翻译) | `summarize/reply_draft/translate.yaml` 各带 few-shot | 🟢 |
| 一致性(约束非temperature) | 确定性引擎+状态机+schema+护栏; LLM 不碰数字 | 🟢 |
| Agent Skills 封装 | `skills/*/SKILL.md`(4 标准技能) + `skill_registry`→function-calling | 🟢(新增) |

## 模块三 · 记忆分层与状态管理
| 考点 | 本系统产物 | 状态 |
|---|---|---|
| 分层混合记忆(短期+长期向量) | 五层 Memory Fabric: Working(Context)/Fact(SQLite)/Semantic(funasr RAG)/Artifact/Episodic(审计链) | 🟢 |
| 状态持久化(会话ID+选择性) | `context_id` 检查点 + `context_engine.compile_for(task)` 选择性裁剪 + SQLite | 🟢 |
| 记忆故障(上下文丢失/偏好遗忘) | `postmortem.recall_customer_memory` 客户历史召回 + 离线 MOCK 显式降级 | 🟢(部分) |

## 模块四 · RAG 体系
| 考点 | 本系统产物 | 状态 |
|---|---|---|
| RAG 核心价值(过时/幻觉) | `rag.py`(援) + funasr `/rag/search` embedding+FTS5+RRF 混合检索 | 🟢 |
| 检索质量(查询扩充/微服务拆分) | funasr 侧 embedding 解耦 + `rag_eval` 排序敏感 context_precision | 🟡(查询扩充未做) |
| RAG 评测 RAGAS | `evaluation/rag_eval.py`: faithfulness/context_precision/context_recall/answer_relevancy(词法代理+LLM judge) | 🟢 |
| NeMo Retriever | `settings.yaml`/`agent.yaml` Retriever 后端边界 + funasr 为 local 后端 | 🔴(无 GPU, 接口已定义) |

## 模块五 ·  专属技术栈 ★占比关键
| 组件 | 要求 | 本系统落点 | 状态 |
|---|---|---|---|
| NIM | 容器化 OpenAI 兼容推理微服务 | `model_router(backend=nvidia)` + `deploy/nim/docker-compose.yml` + `services/nim_smoke.py` + `models.yaml` endpoint 可指向 NIM | 🟡(代码/部署就绪; 本机无GPU未实跑 🔴) |
| TensorRT-LLM | 量化加速 | `agent.yaml`/`-MAPPING.md` 标注加速路径 + NIM 内含 TRT 优化 | 🔴(无 GPU) |
| Triton | 多模型调度/动态批 | `-MAPPING.md` 边界(P2) | 🔴 |
| NeMo Agent Toolkit | 评测/性能/编排 | `agent.yaml`+`evaluation/metrics.py`(任务完成率/工具准确率/消融/AB)+`observability` | 🟡(自实现等价, 未直接调 NAT CLI) |
| NeMo Guardrails | 全链路语义护栏 | `guardrails.py`(builtin 强制🟢) + `config/guardrails/nemo/{config.yml,rails.co}` colang(🟡 可切 backend=nemo) | 🟢/🟡 |
| NeMo-RL | 强化学习训练 Agent | 路线图(`ROADMAP`) | 🔴(超 48h) |
| NGC | 模型仓库/版本 | `models.yaml` 模型版本字段 + NIM 镜像 from NGC | 🟡 |
| 标准生产架构 | Guardrails+NIM+TRT+Triton+K8s+Prom/OTEL | `deploy/{k8s,hpa,grafana,docker-compose,nim}` + `observability(OTEL)` + `guardrails` | 🟡(清单全, 实跑需GPU集群) |

## 模块六 · 生产部署 / 弹性 / 可靠性
| 考点 | 本系统产物 | 状态 |
|---|---|---|
| K8s+HPA 弹性伸缩 | `deploy/k8s.yaml` + `deploy/hpa.yaml`(HPA+ServiceMonitor+PrometheusRule) + Grafana dashboard | 🟡(清单就绪) |
| 指数退避重试+熔断 | `resilience.py`(三态熔断/退避/fallback) 包裹 TimoAdapter | 🟢(10 测试) |
| 超时+Schema校验+故障注入 | `timeout` + `schema_validator`(运行时 jsonschema) + `resilience` 测试含故障 | 🟢 |
| 全链路时延瀑布/分层采样 | `observability` span duration + `scripts/latency_report.py`(P50/P95/瓶颈) | 🟢 |
| CI/CD+镜像+审计留存 | `.github/workflows/ci.yml` + `Dockerfile` + `audit.py` 全链路 | 🟢 |

## 模块七 · 评测 / 安全 / 合规 / 人在回路
| 考点 | 本系统产物 | 状态 |
|---|---|---|
| 工具调用准确率+任务完成率 | `evaluation/metrics.py`(field/tool accuracy, completion, deviation) | 🟢 |
| 消融 + A/B | `metrics.ablation_report`(去RAG/去护栏) + `ab_report`(LLM vs 正则) | 🟢 |
| 多层护栏(输入/生成/行为) | `guardrails.py` 三段 + 注入/外泄/凭证/禁止承诺/外发 | 🟢(15 测试) |
| 完整审计日志+可追溯推理链 | `audit.py` SHA-256 链 + `observability` trace 关联 | 🟢 |
| 人在回路(透明+干预入口+反馈闭环) | HITL 门禁 + `/approve` 真实推进状态机 + `postmortem` 反馈回流 | 🟢 |
| 医疗/金融式合规(禁自主无监督决策) | external_send=draft_only, BLOCKED/HITL 永不自动发, 铁律① | 🟢 |

##  技术存量结论（据实）
- **架构/契约/适配层： 原生对齐度高** — nemo-agents-spec agent.yaml、NIM 后端(OpenAI 兼容同接口)、NeMo Guardrails colang、NeMo Retriever 边界、K8s+HPA+DCGM/OTEL/Prometheus 部署清单、TensorRT/Triton 标注。**"改配置即切 "是代码级事实**(planner/funasr/router 全走 OpenAI-compat，NIM 正是该接口)。
- **本机实跑： 二进制 0**（无 GPU）；运行的是本地 OpenAI-compat 模型(:1234/:1278/:8089) 与 MUSA vLLM(:8000)。
- **要提升"占比"到演示级**：按比赛建议 48h 内 ① NIM 起 1 个模型环节 ② Agent Skills 已封装 4 个 ③ NeMo Guardrails 接 backend=nemo。**已在 `deploy/nim/` 与 `PRD-NCPAAI.md` 给出可执行路径**。
