# 方案 v3 · NVIDIA 全栈平替（Max-NVIDIA）

> **部分作废（2026-09-20）**：EMBED=nv-embedqa、ASR=Parakeet、NIM 容器路线均已关闭或否决；以 `docs/PRD-MASTER-UEA-DELIVERY.md` v2.0 §1.2-F 实测表为准。

| 字段 | 内容 |
|------|------|
| 版本 | **v3.0.0-nvidia-fullstack-replacement** |
| 日期 | 2026-09-20 |
| 相对 v2 | v2=GPU+模型栈跑通；**v3=在此之上把每一层尽量换成 NVIDIA 官方栈** |
| 上位方案 | `PLAN-gpu-nvidia-model-stack.md`（GPU/端口/铁律仍有效） |
| 节点 | spark-51 · GB10 · CUDA 13 · aarch64 · **无 sudo** |
| 主体 | livekernel 不改业务架构；**只平替 Runtime/Serving/RAG/Guardrails/Observability** |
| 铁律 | 价格仍 Timo 裁决；NVIDIA=AI Runtime；**禁止无实证口播「已上 NIM/NeMo」** |

---

## 1. 平替总原则

1. **对位优先**：每个「非 NVIDIA / 通用」组件，先找 NVIDIA 官方等价物（NIM / NeMo / TensorRT / Triton / DCGM / NGC / Agent Toolkit）。  
2. **配置级切换**：上层 `model_router` / `agent.yaml` / `models.yaml` 契约不变，只换 endpoint 与 backend。  
3. **门禁分级**：`装得上 → 探活绿 → 业务接入 → 行为等价`；未到的级别不得进答辩主句。  
4. **无 sudo 现实**：优先 **用户级 pip / 预编译 wheel / 节点预置**；Docker+NVIDIA Container Toolkit 不可用则 **NIM 降级为「契约+探活脚本已就绪」**，并启用下一档平替（见矩阵）。  
5. **全栈叙事完整**：即使个别二进制未跑通，提交包里必须有 **完整的 NVIDIA 对位地图 + 可复现切换命令 + evidence 骨架**。

---

## 2. 全栈平替对照表（核心交付）

| 层 | 现状（可跑基线） | **NVIDIA 全栈目标（平替）** | 落点/命令 | 装不上时的诚实回退 | 优先级 |
|----|------------------|------------------------------|-----------|---------------------|--------|
| 硬件/驱动 | 已是 GB10+Driver580+CUDA13 | **DGX Spark / Grace-Blackwell / CUDA**（已是 NVIDIA） | `nvidia-smi`；DCGM 用户级探针 | 保持；补 evidence | **T0** |
| 容器/GPU 运行时 | 无 sudo，可能无 docker | **NVIDIA Container Toolkit + Docker + NGC** | `docker info`；`nvcr.io` 拉镜像 | 用户级进程推理；文档写「容器路径 blocked」 | **T0** |
| LLM 推理引擎 | torch+transformers GPU（v2 基线） | **1) NIM LLM  2) vLLM(NGC生态)  3) TensorRT-LLM** | `deploy/nim/docker-compose.yml` → `:8000/v1`；或节点内 vllm serve | torch GPU + OpenAI 包装（仍 CUDA） | **T0** |
| LLM 权重 | Qwen3-0.6B | **NIM 预置模型**：`meta/llama-3.1-8b-instruct` 或 **nvidia/llama-3.1-nemotron** / NGC 可拉模型（以节点显存为准） | `agent.yaml` `nvidia_nim.FAST/REASON` | 继续 Qwen3-0.6B 但 endpoint 仍走 `/v1` 同构 | **T0/T1** |
| Embedding | Qwen3-Embedding-0.6B | **NIM Embedding `nvidia/nv-embedqa-e5-v5`**（compose 已有 `nim-embed`） | `:8011/v1`；`models.embedding` | Qwen3-Embedding GPU；接口仍是 embeddings | **T0** |
| ASR | Qwen3-ASR / FunASR | **NVIDIA Parakeet ASR NIM**（若节点/镜像支持） | `nvidia_nim.ASR` | **保持 FunASR**；书面说明 Blackwell 自托管约束（NVIDIA-MAPPING） | **T1** |
| OCR/文档 | Paddle/RapidOCR | **NVIDIA NIM 多模态/VLM OCR 路径** 或 **NeMo Retriever 文档**；TAO 视觉（超赛期则 T2） | intake → VLM NIM | RapidOCR CPU；`models.ocr` 显式状态 | **T1** |
| RAG 检索 | funasr 本地 + rag_layers | **NeMo Retriever / NIM embedding + NeMo RAG Blueprint 模式** | `agent.yaml` memory.semantic；embed 指 NIM | funasr/file vector；架构已预留 Retriever 后端 | **T1** |
| 护栏 | `services/guardrails.py` builtin | **NeMo Guardrails**（colang 已在 `config/guardrails/nemo/`） | `pip install nemoguardrails` 用户级；`guardrails.backend=nemo` | **builtin 继续强制**（不取消） | **T0** |
| Agent 契约 | `config/agent.yaml` 已对齐 | **NeMo Agent 规范 / NeMo Agent Toolkit 语言** | `services/agent_spec.py` 校验；文档对齐 NAT | 自实现等价控制面 | **T1** |
| 编排/技能 | livekernel 33 Skills + Dispatcher | **NVIDIA/skills 方法论 + skill-card/governance**；业务 Skill 仍自有 | 本机白名单参考；**不**官方全量上节点 | 33 业务 Skills 保持 | **T1** |
| 可观测 | `observability.py` OTEL 风格 | **OTEL + NVIDIA DCGM/GPU metrics** | GPU 利用率进 trace；evidence | JSONL trace | **T1** |
| 生产清单 | k8s/hpa/grafana YAML | **NVIDIA GPU Operator / NIM on K8s 叙事**（赛期单机不部署集群） | `deploy/k8s.yaml` 注释对齐 | 单机 compose/进程 | **T2** |
| 业务确定性 | Timo 引擎 | **不平替**（NVIDIA 不拥有价格真相） | `:7862` locked | 离线 byte-identical | **锁定** |

---

## 3. 目标拓扑（Max-NVIDIA 单机）

```
                    公网 :8051 / :9051
                           │
         ┌─────────────────┴─────────────────┐
         ▼                                   ▼
  livekernel :8888                    Model Plane :9000
  (Workbench/API/Skills)              OpenAI 兼容聚合 + 鉴权
         │                                   │
         │ models.yaml / agent.yaml          │
         │ backend: nvidia 优先              │
         ▼                                   ▼
  ┌──────────────┐              ┌─────────────────────────────┐
  │ Timo :7862   │              │ NVIDIA Inference Plane      │
  │ DETERMINISTIC│              │  NIM-LLM    :8000/v1        │
  │ calc_quote   │              │  NIM-Embed  :8011/v1        │
  └──────────────┘              │  NIM-ASR    :8002/v1 (T1)   │
                                │  VLM/OCR    :80xx (T1)      │
         Guardrails             │  fallback: vLLM/torch GPU   │
         builtin ⊕ nemo         └─────────────────────────────┘
                                   ▲
                                   │ nvcr.io / NGC_API_KEY / GPU
                                   │ GB10 CUDA13 (已具备驱动层)
```

---

## 4. 节点门禁探测（平替是否「真上」的前提）

| 门禁 | 命令（节点） | 绿 | 红则 |
|------|----------------|----|------|
| G-Docker | `docker info` | 可跑 NIM/容器 | 全部 NIM 改「进程级平替」 |
| G-NVIDIA-CT | `nvidia-container-cli info` 或 docker run --gpus | GPU 进容器 | 同上 |
| G-NGC | `curl -I https://nvcr.io`；本地 `.env` 有 `NGC_API_KEY`（**不入库**） | 可拉镜像 | 只用已缓存/用户级权重 |
| G-CUDA | `nvidia-smi`；torch CUDA | L1/L2 | 回 v2 G0 |
| G-Pip-Nemo | `pip install --user nemoguardrails` | 可切 nemo backend | 保持 builtin |
| G-VLLM | `pip index` / 试装 `vllm` aarch64 | 进程级 NVIDIA 生态服务 | torch+包装 |

**记录文件**：`docs/evidence/spark/nvidia/00-gates.txt`

---

## 5. 配置平替（仓库要改什么）

### 5.1 `config/settings.yaml` / `settings.dgx-spark-p0.yaml`

```yaml
profile: dgx-spark-p0
model_router:
  backend: nvidia          # 门禁绿后改；未绿保持 local 并写 evidence
  roles:
    FAST:   { endpoint: "http://127.0.0.1:8000/v1", model: "meta/llama-3.1-8b-instruct" }
    REASON: { endpoint: "http://127.0.0.1:8000/v1", model: "nvidia/llama-3.1-nemotron" }  # 显存不够则回 8b
    EMBED:  { endpoint: "http://127.0.0.1:8011/v1", model: "nvidia/nv-embedqa-e5-v5" }
    ASR:    { endpoint: "http://127.0.0.1:8002/v1", model: "nvidia/parakeet" }  # 仅门禁绿
    # DETERMINISTIC: Timo，永不改
guardrails:
  backend: nemo_soft       # 已有降级逻辑；装上 nemoguardrails 后启用
```

### 5.2 `config/models.yaml`（节点副本）

- `llm/vlm` endpoint → NIM 或 vLLM 网关  
- `embedding` → **nv-embedqa-e5-v5**（NVIDIA）  
- `asr` → 门禁绿则 Parakeet，否则保持 Qwen3-ASR  
- `deterministic.locked: true` 不动  

### 5.3 `config/agent.yaml`

- `spec.models.backend: nvidia`  
- `nvidia_nim.*` 端口与节点实际映射一致（8000/8011/8002）  
- 工具列表不变（Skills 仍是业务能力）

### 5.4 `deploy/nim/`

- 保留并扩：`nim-llm` / `nim-embed`；**节点无 docker 时不要假启动**  
- 增加 `deploy/spark/README-nvidia-fullstack.md`：门禁、启动序、降级表  
- `NGC_API_KEY` 仅节点 `.env` 或环境变量  

### 5.5 Guardrails

- 用户级 `pip install --user nemoguardrails`  
- `services/guardrails.py`：已支持 `nemo_soft` 检测；**builtin 规则不关**（双保险）  
- 验收：注入/外泄/无价格 用例双后端各跑一组  

---

## 6. 分档实施（「开始平替」的执行序）

| 批次 | 名称 | 动作 | 完成定义 |
|------|------|------|----------|
| **NG0** | 门禁盘点 | 节点探测 Docker/NGC/CUDA/pip；写 `00-gates.txt` | 知道 NIM 能不能真上 |
| **NG1** | NVIDIA Embedding 平替 | 优先 **nv-embedqa**（NIM 或 NGC 权重进程级）；切 `models.embedding` | RAG 走 NVIDIA embed 一次检索 |
| **NG2** | NVIDIA LLM 平替 | NIM LLM 或 **vLLM 拉 NGC/社区 NVIDIA 生态模型**；否则 torch+NVIDIA 模型权重 | `/v1/chat` 200 + device 日志 |
| **NG3** | NeMo Guardrails 平替 | pip 装 nemoguardrails；`backend=nemo_soft`；对照 builtin | 护栏用例绿；evidence |
| **NG4** | ASR/OCR NVIDIA 路径 | Parakeet/VLM NIM；不通则书面锁定 FunASR 原因 | asr/ocr 状态诚实写入 models.yaml |
| **NG5** | Agent 面全栈接线 | `model_router.backend=nvidia` + nim_smoke + 黄金链 | L4 业务日志 + 价格 sha256 不变 |
| **NG6** | 可观测与提交 | DCGM/OTEL GPU 指标；NVIDIA 对位文档进 README；脱敏 | 证据包 + 答辩分级 |

**与业务 Skills 并行**：negative trigger、A/B 不受平替阻塞，可穿插。

---

## 7. 平替优先级（资源紧时先换谁）

```
必须换（评委一眼能指认的 NVIDIA 名词）
  1. Embedding → nvidia/nv-embedqa-e5-v5
  2. LLM 服务 → NIM 或 vLLM(NGC 模型)
  3. Guardrails → NeMo Guardrails
  4. 驱动/CUDA evidence → nvidia-smi + DCgM/OTEL GPU

应换（全栈完整度）
  5. RAG → NeMo Retriever 模式
  6. ASR → Parakeet（支持则）
  7. agent.yaml → NeMo Agent 规范口径

可叙事（赛期单机）
  8. Triton/TensorRT-LLM/K8s GPU Operator → 架构页 + 就绪清单

永不换
  9. Timo 价格引擎 / HITL / 审计链 / Skills 业务语义
```

---

## 8. 证据包（NVIDIA 全栈专用）

```
docs/evidence/spark/nvidia/
  00-gates.txt                 # docker/ngc/cuda/pip 门禁
  01-nvidia-smi.txt
  02-torch-cuda-probe.log
  03-nim-or-vllm-health.txt    # /v1/models
  04-embed-nv-embedqa.log      # 或 blocked 原因
  05-llm-nvidia-model.log
  06-nemo-guardrails.txt       # 版本 + 用例
  07-asr-ocr-status.md
  08-golden-chain-price-sha256.json
  09-models-yaml-diff.md
  10-backend-nvidia-claim-level.md   # L0–L5 自评
```

**口播等级（强制）**

| 等级 | 允许说法 |
|------|----------|
| N0 | 驱动/CUDA 为 NVIDIA（已达成） |
| N1 | CUDA 上 torch/vLLM 推理（用户级） |
| N2 | **至少一个** NIM/NGC 官方模型或 NeMo 组件实跑 |
| N3 | LLM+Embed（+ASR 若可）均 NVIDIA 后端且 livekernel 在用 |
| N4 | 黄金链 + 护栏 NeMo + 价格等价全绿 |
| N5 | 可观测 GPU 指标 + 提交包全证据 |

未到的等级 **禁止**在标题/海报写「全栈 NIM」。

---

## 9. 风险与对策

| 风险 | 对策 |
|------|------|
| 无 docker/sudo → NIM 容器全灭 | NG1/NG2 进程级：NGC 权重 + vLLM/torch；文档保留 compose 为标准路径 |
| GB10/aarch64/cu130 无 vLLM wheel | N1 torch CUDA + OpenAI 包装；答辩称「NVIDIA GPU Runtime + 兼容接口」 |
| 8B/70B NIM 显存不够 | 先 embed + 小 NIM/小模型；REASON 可降级 |
| Parakeet Blackwell 不支持 | 固定 FunASR；引用 NVIDIA-MAPPING 已核验边界 |
| NGC_API_KEY 泄漏 | 只在节点 env；脚本读环境变量；仓内仅 `.env.example` |
| 价格被 LLM「抢戏」 | 答辩必背：DETERMINISTIC locked |
| 官方 NVIDIA/skills 全量安装 | **禁止**；只作方法论/skill-card |

---

## 10. 本机/节点分工

| 环境 | 做什么 |
|------|--------|
| 本机 | 平替配置稿、agent.yaml/models.yaml 对照、nim_smoke、护栏用例、文档与 evidence 模板、脱敏 |
| 节点 Spark-51 | 门禁探测、装用户级依赖、起 NIM/vLLM/torch 服务、绑 8888/9000、跑黄金链、写 evidence |
| 不做 | 重写业务 Skills；合并历史目录；无证据宣称 NeMo 生产集群 |

---

## 11. 确认后的第一刀（NG0）

我将准备（不进仓库明文密码）：

1. `deploy/spark/probe_nvidia_gates.sh` — 门禁探测  
2. `config/settings.dgx-spark-nvidia.yaml` — Max-NVIDIA 配置模板  
3. `docs/evidence/spark/nvidia/README.md` — 证据填写说明  
4. 启动序文档：`deploy/spark/README-nvidia-fullstack.md`  

你在节点跑探测或把 `00-gates.txt` 结果贴回后，按门禁选 **NIM 容器线** 或 **进程级 NVIDIA 线**，再动 NG1 Embedding。

---

## 12. 一句话

> **全栈平替 = 驱动已是 NVIDIA，推理尽量 NIM/vLLM/NGC 模型，检索尽量 nv-embedqa/NeMo Retriever，护栏尽量 NeMo Guardrails，契约保持 agent.yaml；装不上的每一层都有门禁、有回退、有证据等级——业务价格引擎永不平替。**
