# 模型选型清单 · Union × NVIDIA 全栈（v1）

> **已作废（2026-09-20）**：NIM 容器路线因 docker 无权限关闭；模型栈以 `docs/PRD-MASTER-UEA-DELIVERY.md` v2.0 §1.2-F 实测表为准（Nemotron NVFP4 全栈 + vLLM 进程级）。

| 版本 | 2026-09-20 · 对应 `PLAN-nvidia-fullstack-replacement.md` |
|------|------|
| 约束 | GB10 · CUDA 13 · aarch64 · 无 sudo · 单节点 · 比赛演示优先「稳、可留证」 |
| 原则 | NVIDIA 优先 → 已在节点/易装 → 业务够用；**价格不进 LLM** |

---

## 1. 总表（我选的模型）

| 角色 | **首选（NVIDIA 全栈）** | **备选（进程级/回退）** | **节点已有** | 显存/磁盘档位 | 选它做什么 |
|------|-------------------------|-------------------------|--------------|---------------|------------|
| LLM · FAST/抽取 | **meta/llama-3.1-8b-instruct**（NIM） | Qwen3-4B / Qwen3-0.6B（torch GPU） | Qwen3-0.6B | 8B≈中；0.6B≈轻 | RFQ 字段、工具选择、摘要、翻译 |
| LLM · REASON/规划 | **nvidia/llama-3.1-nemotron-8b**（NIM） | 同 8b-instruct；显存紧则与 FAST 合用同一 8B | — | 中 | ReAct 规划、冲突说明草稿（仍引擎裁决数字） |
| VLM · 图纸 | **NIM VLM**（如 Llama-3.2-Vision 类，镜像可得时） | 暂 `mock` / 不启用 | 无专用 VLM | 中高 | 只出几何/文字事实，不定价 |
| **Embedding** | **nvidia/nv-embedqa-e5-v5**（NIM） | **Qwen3-Embedding-0.6B** | 计划中 | 轻 | RAG 向量：历史 RFQ/工艺/PO |
| **ASR** | **nvidia/parakeet**（NIM，Blackwell 或受限） | **Qwen3-ASR-0.6B** / FunASR 中文 | 计划中 | 轻 | 语音约束进 intake |
| OCR | 无独立 NVIDIA OCR 时：**VLM OCR 路径** | RapidOCR / PaddleOCR | — | 轻 | PO/图纸文字 |
| 安全护栏模型 | **NeMo Guardrails**（语义/规则，非大模型） | builtin 规则（强制保留） | colang 已就绪 | 极轻 | 注入/外泄/禁止编价格 |
| Embedding 生产增强 | NeMo Retriever 模式（检索工程） | funasr/file vector | 有 rag_layers | — | 分层 RAG |
| **DETERMINISTIC** | **Timo calc_quote + ConflictChecker** | 离线 vendored 同引擎 | 仓内/引擎 | 无 GPU 依赖 | **唯一价格/DFM 真相** |

---

## 2. 逐项推理

### 2.1 LLM 为何是 Llama-3.1-8B（NIM）而不是更大/更炫

| 考量 | 推理 |
|------|------|
| NVIDIA 叙事 | 仓内 `deploy/nim/docker-compose.yml` 已默认 `nvcr.io/nim/meta/llama-3.1-8b-instruct`，与 NIM/NGC 路径一致，答辩「NIM」有物可指 |
| 单机 GB10 | 统一内存虽可观，但还要跑 Workbench、RAG、引擎、可能的 Embed/ASR；**8B 是演示稳定甜点**，70B 级不适合赛期常驻 |
| aarch64/无 sudo | NIM 容器一条路；进程级则 8B 未必装得动 → 必须保留 **0.6B/4B torch 回退**，保证 `/v1` 不冷场 |
| 业务负荷 | 抽取/规划/草稿用 8B 够用；**0.6B 只证明链路**，质量靠规则+引擎+RAG，不赌小模型智力 |
| REASON 用 Nemotron | 强化「NVIDIA 模型」表象；若显存/镜像吃紧，**REASON 与 FAST 合并为同一 8B**，少驻留一个权重 |

### 2.2 Embedding 为何是 nv-embedqa-e5-v5

| 考量 | 推理 |
|------|------|
| 全栈最硬的一环 | Embedding 对「是否 NVIDIA」极敏感、又相对轻；compose 已有 `nim-embed`，**最先能落地的 N2 证据** |
| 检索质量 | e5 系在中英工程文本上稳定，适合 RFQ/工艺 chunk |
| 回退 | Qwen3-Embedding-0.6B 与 models.yaml 一致，接口都是 `/v1/embeddings`，换后端不改 Agent 架构 |
| 不选 bge-m3 作首选 | 本机曾用 bge，但赛题要 **多用 NVIDIA**，bge 仅作历史兼容，不进主叙事 |

### 2.3 ASR 为何 Parakeet 首选、FunASR 必备

| 考量 | 推理 |
|------|------|
| NVIDIA 对位 | Parakeet 是官方音频 NIM，叙事完整 |
| 现实约束 | `docs/NVIDIA-MAPPING.md` 已写：**Parakeet 自托管对 Blackwell/compute 12.0 可能不支持** |
| 比赛策略 | 门禁绿则上 Parakeet 记 N3；红则 **Qwen3-ASR/FunASR**，evidence 写清原因，禁止假称 |
| 业务 | 报价 Agent 只要「语音约束进结构化」，中文 ASR 实用性 > 品牌 |

### 2.4 VLM/OCR 为何克制

| 考量 | 推理 |
|------|------|
| 分值结构 | 图纸感知有演示价值，但 **不在「必须 NVIDIA」的最短路径** |
| 资源 | VLM 再吃显存，易拖垮 LLM+Embed 演示 |
| 策略 | P0：`vlm/ocr` 诚实 disabled 或 mock；有余力再上 NIM VLM；**价格永不依赖 VLM** |

### 2.5 为何保留 NeMo Guardrails + builtin 双轨

| 考量 | 推理 |
|------|------|
| NVIDIA 全栈 | NeMo 是官方安全栈，colang 工件已在 `config/guardrails/nemo/` |
| 可靠性 | 装不上或 LLM 不稳时 **builtin 仍强制**，避免演示被护栏打穿 |
| 口径 | 护栏证明「可验证商业」，不是装个包就算分 |

### 2.6 为何 DETERMINISTIC 不是「模型」却必须在表里

评委最常问：数字谁生成？  
答案只能是 **Timo 引擎**；LLM/NIM/vLLM 一律 `llm_proposal`。全栈越 NVIDIA，越要用这张表钉死边界。

---

## 3. 优先驻留策略（单节点）

```
演示峰值建议同时驻留（≤3 个重模块）:
  ① Timo 引擎 :7862     —— 始终
  ② Embedding（NVIDIA 或 Qwen3-Embed） :8011 或 :9000
  ③ LLM 8B NIM 或 回退小模型 :8000 或 :9000

按需加载/释放:
  VLM → 仅图纸场景
  ASR  → 仅语音场景
  70B/超大 Nemotron → 赛期不默认
```

网关仍绑 `0.0.0.0:9000`（公网 9051），Workbench `8888`（8051）。

---

## 4. 门禁 → 实际启用表（执行时勾选）

| 角色 | docker+NGC 绿 | 仅 torch GPU 绿 | 仅 smi |
|------|---------------|-----------------|--------|
| LLM | NIM 8B / Nemotron | torch 上 Qwen3-0.6B/4B | 离线+本地故事 |
| Embed | **nv-embedqa NIM** | Qwen3-Embedding GPU | hash 降级 |
| ASR | Parakeet 尝试 | Qwen3-ASR | MOCK |
| Guardrails | NeMo + builtin | NeMo 若 pip 成功 | builtin |
| 价格 | Timo | Timo | Timo |

**N2 最小充分集**：Embedding 用上 **nv-embedqa** 或 Guardrails 实跑 NeMo 之一 + GPU 探针绿。

---

## 5. 明确不选（及原因）

| 不选 | 原因 |
|------|------|
| 70B/405B 作赛期默认 | 驻留与失败面过大，演示风险高 |
| 仅用 Qwen 全家桶 | 违背「必须多用 NVIDIA 全栈」 |
| Parakeet 作为唯一 ASR | Blackwell/节点约束，无回退会翻车 |
| 用 LLM 出厂报价 | 违反铁律与审计叙事 |
| 官方 NVIDIA/skills 全量模型化 | skills≠模型；且节点装不动、路由乱 |
| MUSA/非 NVIDIA 服务冒充 NIM | 证据造假风险 |

---

## 6. 一句话

> **首选：NIM Llama-3.1-8B（+ 可选 Nemotron REASON）+ nv-embedqa-e5-v5 +（条件允许）Parakeet + NeMo Guardrails；回退：节点已有 Qwen3-0.6B / Qwen3-Embedding / FunASR + torch GPU；价格永远 Timo。**
