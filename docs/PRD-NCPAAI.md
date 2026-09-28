# PRD · 中客松 AI Agent 赛道 — Union CNC 智能外贸报价 Agent
**版本 v2.1.0-livekernel · 2026-09-17 · 对齐 NCP-AAI 工业 AI 协议（Agentic AI）7 大模块**
**一句话**：把一封外贸询盘变成"可审计、可验证、可复盘"的制造业商业决策——**换数据即换人格，越用越像该厂老师傅**。

---

## 0. 为什么要这份 PRD（回应评审意见）
外部评估指出：**核心逻辑契合赛题、可行性高，但  技术占比偏低**。本 PRD 正视该短板：
① 诚实盘点当前  存量（见 `docs/NCP-AAI-COVERAGE.md`）；② 给出 **48 小时内可落地的 NIM + Agent Skills + NeMo Guardrails 接入方案**；③ 用"数据决定行为差异 + 去掉测试/对照组"的对照演示放大护城河。

---

## 1. 赛题契合（未定信号 / 真实问题 / 独有数据 / 个体差异 / 长期价值）
| 赛题维度 | 本方案落点 |
|---|---|
| 真实问题 | CNC 报价凭老师傅感觉：报低丢利润、报高丢单 |
| 独有数据 | A厂/B厂**私有报价台账**→不同输出（Fact+Semantic memory） |
| 个体差异 | 同一系统换数据即换"人格"，回填越多越准 |
| 长期价值 | postmortem 闭环：Won/Lost→实际成本→偏差→知识回流 |
| 去掉测试/对照 | 确定性引擎+黄金集回归(S1–S5+M1)+A/B(正则vs LLM)+消融(去RAG/去护栏) |

---

## 2. 产品架构（已实现，见主干代码）
```
Email/Voice/STEP/PDF/Excel  →  全模态上传端口 (:8900)
  → 模型设置工具(LLM/VLM/Embedding/OCR/ASR, config/models.yaml, UI 可改即生效)
  → LLM Planner: ReAct 抽取/选技能/起草   [LLM 提议]
  → Context Engine(context_id) → RFQ 状态机(业务真相)
  → cnc-ai-brain 确定性内核(:7862, 在线/离线 byte-identical)  [引擎裁决数字/冲突]
  → 辟牟援推止 验证 + Guardrails(三段护栏,强制) + HITL 门禁
  → 英文回复草稿(draft_only) → CRM/Memory → SHA-256 审计链 → Postmortem 闭环
```
六条工程铁律不破：LLM 不生成价格 / 状态机是真相 / Context 唯一 / RAG 供证据 / 冲突必升级 / NVIDIA·本地模型是 AI Runtime 不是业务逻辑。

**现状规模**：pytest 150 passed / 13 notebooks / ~107 文件 git 跟踪 / 全模态上传端口 + P0 LLM Planner + P1 容错 + P2 评估(RAGAS) + P3 平台化。

---

## 3.  技术地图与占比（据实）
> 详见 `docs/NCP-AAI-COVERAGE.md`。本机无 GPU，`nvidia-smi` 无；:8000 为 MUSA vLLM（非 NIM）。

| 组件 | 现状 | 落地方式 |
|---|---|---|
| **NIM**（OpenAI 兼容推理微服务） | 🟡 代码/部署就绪，未实跑 | `model_router backend=nvidia` + `deploy/nim/docker-compose.yml`；`config/models.yaml` 里把 `llm/vlm/embedding` 的 `endpoint` 填成 NIM 的 `/v1` URL **即切换**（planner/funasr/router 全走 OpenAI-compat，NIM 正是该接口） |
| **Agent Skills** | 🟢 已封装 4 个 | `skills/{rfq-extraction,cnc-quote,dfm-conflict,step-analysis}/SKILL.md` + `skill_registry`→OpenAI function-calling 工具描述，喂给 ReAct 工具选择 |
| **NeMo Guardrails** | 🟢 builtin 强制 / 🟡 nemo 后端 | `guardrails.py`(输入/工具/输出) 已强制+测试；`config/guardrails/nemo/{config.yml,rails.co}` colang 就绪，`backend=nemo` 可接真 NeMo |
| **TensorRT-LLM / Triton** | 🔴 无 GPU | NIM 内置 TRT 优化；`-MAPPING.md` 标注加速路径 |
| **K8s+HPA+Prometheus+DCGM+OTEL** | 🟡 清单就绪 | `deploy/{k8s,hpa,grafana}` + `observability.py`(OTEL 风格 trace) |
| **NeMo Retriever** | 🔴→🟡 边界 | funasr RAG 为 local 后端，Retriever 为生产后端（`agent.yaml`） |

**关键事实**：因为我的**全部模型调用都是 OpenAI 兼容**（:1234 LMStudio / :1278 embedding / :8089 ASR），接入 NIM 是**配置级一行 base_url 替换**，不是重写——这正是 NIM 的设计目的。占比"低"的根因是本机无 GPU 可演示，而非架构未接。

---

## 4. 48 小时  接入方案（对齐评审建议 + 赛事时间线 9/11–9/13）
| 时段 | 交付 | 可演示证据 |
|---|---|---|
| **9/10 晚（赛前）** | 拉 NIM 容器镜像（meta-llama/llama-3.1 / nvidia/llama-3.1-nemotron / nv-embedqa / rerank）；确认本地 GPU 可跑；选定 1 个模型环节用 NIM | `docker compose -f deploy/nim/docker-compose.yml up -d`；`python services/nim_smoke.py` 探活 OpenAI-compat |
| **9/11 晚** | NIM 跑通 → `config/models.yaml` 把 `llm` 端点改指 NIM（UI 或直接改）→ ReAct Planner 走 NIM；写第 1 个 Agent Skill（报价区间生成，已具雏形） | UI「模型设置」卡片 endpoint 改指 NIM +「测试连接」绿；intake 带 `use_llm` 走 NIM |
| **9/12** | 接入 Gradio/Streamlit 前端调 NIM；封装 2–3 个技能（图纸参数/历史检索/工艺冲突）；NeMo Guardrails `backend=nemo` 接 1 条语义护栏；有余力用 NeMo Agent Toolkit YAML 重构工作流 | 端到端 Demo：邮件→NIM 抽取→内核报价→护栏→HITL→英文回复；审计链/trace 可看 |
| **9/13 上午** | 只做稳定性验证，不加新功能；确保  部分可演示、可解释 | `python 一键自检.bat`；`docs/NCP-AAI-COVERAGE.md` 逐点讲 |

**降级保底**：现场无 GPU/NIM → 自动回落本地 OpenAI-compat(:1234)+离线 byte-identical 内核，**演示不冷场**，占比说明用覆盖矩阵讲清"接口/契约全绿、运行时随硬件"。

---

## 5. 技术完成度自评（对齐评审 6 维）
| 维度 | 现状 |  补强后 |
|---|---|---|
| 可行性 | 高（已落地并测试） | 不变 |
| 创新性 | 高（换数据换人格） | 不变 |
| 项目价值 | 高 | 不变 |
| 技术完成度 | 中 | NIM+AgentSkills+NeMo护栏 → 高 |
| 路演答辩 | 高 | +覆盖矩阵佐证 |
| ** 占比** | 低（本机无 GPU 实跑） | 接口/契约/适配器/技能/护栏/部署清单全绿；有 GPU 即配置切换实跑 |

---

## 6. 验收标准（Definition of Done）
- [x] 全模态上传端口 + 模型设置工具（LLM/VLM/Embedding/OCR/ASR）可改即生效
- [x] LLM Planner：ReAct + 提示工程 + Schema 绑定 + LLM 工具选择（引擎裁决数字）
- [x] Agent Skills 封装 4 个 + function-calling 工具描述注册表
- [x] 三段 Guardrails 强制 + OTEL trace + SHA-256 审计 + HITL + 闭环
- [x] 评估体系（RAGAS + 准确率 + 消融 + A/B）+ CI + HPA/Prometheus 部署清单
- [x] NIM 部署清单 + 探活脚本 + OpenAI-compat 配置级切换
- [ ] 有 GPU 时：NIM 实跑替换 1 模型环节 + NeMo Guardrails backend=nemo（48h 现场完成）

---

## 7. 一句话
> **"LLM 提议、引擎裁决"的制造业外贸 Agent**：确定性内核守住报价/工艺/毛利真相， 栈（NIM 推理 + Agent Skills + NeMo Guardrails + K8s/OTEL）以 OpenAI 兼容接口**配置级可切换**接入，私有报价台账决定"越用越像该厂老师傅"——真实问题 + 独有数据 + 个体差异 + 长期价值，全维契合 NCP-AAI。
