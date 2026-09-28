# 模型选型 v2 · Nemotron 替换方案

> **部分作废（2026-09-20 节点实测）**：REASON=GGUF、EMBED=nv-embedqa 两项已否决，ASR 改专档 `nemotron-3.5-asr-streaming-0.6b`。以 `docs/PRD-MASTER-UEA-DELIVERY.md` v2.0 §1.2-F 实测表为准。

| 字段 | 内容 |
|------|------|
| 版本 | **v2.0-nemotron-replacement** |
| 日期 | 2026-09-20 |
| 变更 | 用户指定三款 Nemotron 替换原 Llama-8B/Qwen 主路径 |
| 约束 | GB10 · CUDA 13 · aarch64 · 无 sudo · 单节点演示 |
| 不变 | Embedding 仍用 **nv-embedqa**；价格仍 **Timo**；无证据不口播 N2+ |

---

## 1. 替换总览（我怎么改方案）

| 角色 | 原方案 | **新方案（Nemotron）** | 替换结论 |
|------|--------|------------------------|----------|
| LLM · FAST / 抽取 / 工具选择 | NIM Llama-3.1-8B / Qwen3-0.6B | **Nemotron 3 Nano 4B** | **主替换** |
| LLM · REASON / ReAct 规划 | Nemotron-8B 或与 FAST 合并 | **Nemotron 3.5 Lightning 30B-A3B（GGUF）** | **主替换**（质量档） |
| VLM · 图纸事实 | NIM VLM / mock | **Nemotron 3 Nano Omni**（主）；失败→mock | **主替换**（多模态） |
| ASR · 语音 | Parakeet / Qwen3-ASR / FunASR | **Omni 音频若可用**；否则 **FunASR/Qwen3-ASR 回退** | **条件替换** |
| Embedding · RAG | nv-embedqa-e5-v5 NIM | **保持 nv-embedqa** | **不替换** |
| Guardrails | NeMo + builtin | **保持** | 不替换 |
| OCR 独立模型 | RapidOCR 等 | Omni 视觉优先；独立 OCR 降为 T2 | 由 Omni 承接 |
| 报价/DFM | Timo | **Timo** | **永不替换** |
| 0.6B 既有权重 | 节点冒烟 | 降为 **仅 CI/链路冒烟** | 降级，不删 |

**一句话**：文本双档（Nano 4B + Lightning 30B-A3B）+ 多模态一档（Omni）+ 向量一档（nv-embedqa）+ 业务引擎（Timo）= **NVIDIA 叙事完整、GB10 可落地**。

---

## 2. 逐模型推理

### 2.1 Nemotron 3 Nano 4B —— 替换「8B 通用 LLM + 0.6B 现场模型」

| 维度 | 推理 |
|------|------|
| 为何替换 | 原首选 Llama-3.1-8B 虽是 NIM 常客，但品牌上仍是 Meta；赛题要 **多用 NVIDIA**，Nano 4B 直接对齐 Nemotron 家族 |
| 规模 | 4B：比 0.6B 质量更适合 RFQ 抽取/工具描述选择；比 8B **更省驻留**，给 Embedding/引擎/Workbench 留内存 |
| 算力匹配 | GB10 统一内存跑 4B 常驻合理；CPU 也能兜底演示 |
| 接口 | 仍走 OpenAI 兼容 `/v1`（NIM 若有镜像用容器；否则 llama.cpp/vLLM/transformers 进程级） |
| 职责 | **FAST + 多数 REASON 入门任务**：parse-rfq、tool_selection、摘要、翻译、reply 草稿 |
| 边界 | **不负责最终价格**；prompt 里保留 iron_rule |
| 风险 | 若节点/NIM 无该权重：用本地转换或 HF/ModelScope 镜像；装不上则临时 Qwen3-4B/0.6B，evidence 记回退 |

### 2.2 Nemotron 3 Nano Omni —— 替换「分离 VLM + 分离 ASR 主叙事」

| 维度 | 推理 |
|------|------|
| 为何替换 | Omni = NVIDIA 官方多模态入口，一张表覆盖 **图纸/VLM + 语音 + 文本**，全栈故事最干净 |
| 对业务 | intake：图片/扫描 PO → 视觉事实；语音约束 → 文本 claim；**都不定价** |
| 替换范围 | 主路径吃掉「NIM VLM」和「ASR 首选 Parakeet」的叙事位 |
| 为何仍留 FunASR | Blackwell 自托管音频栈不稳是已核验风险；Omni 若音频路径失败，**中文 ASR 必须有回退**，否则演示冷场 |
| 资源 | Omni 通常 > 纯文本 Nano 4B → **按需加载**，不与 Lightning 同时常驻 |
| 风险 | aarch64/权重可用性/显存；先探活再写 models.yaml，禁止假称 |

### 2.3 Nemotron 3.5 Lightning 30B-A3B GGUF —— 替换「8B REASON / 更大稠密模型」

| 维度 | 推理 |
|------|------|
| 命名解读 | **30B-A3B** ≈ MoE：总参约 30B、**激活约 3B** → 推理算力/延迟接近小模型，容量接近大模型；**Lightning** 面向快速生成；**GG** = GGUF，走 **llama.cpp / ollama** 用户级服务，**绕开无 sudo + NIM 镜像** |
| 为何替换 | REASON 要「说得清冲突/规划」，4B 不够撑答辩里复杂场景；30B-A3B GGUF 在 128GB 级统一内存上 **Q4/Q5 通常可放**，且 aarch64 llama.cpp 路径成熟度高于「强上 30B 稠密 NIM」 |
| 为何不用 8B 稠密 Nemotron 作 REASON | 可作备选，但用户点名 Lightning GGUF 后，**主 REASON 改为 MoE GGUF**：活跃算力低 → 更适合单机演示时延 |
| 服务化 | `llama-server --host 0.0.0.0 --port 9000`（或独立端口挂网关）→ `/v1/chat/completions`，livekernel 零架构改动 |
| 职责 | ReAct 规划、HITL 说明、多专家叙事草稿、英文回复深稿；**数字仍引擎出** |
| 风险 | ① GGUF 文件体积（节点内下载，禁 scp 大包）② aarch64+CUDA13 的 llama.cpp 需匹配编译 ③ 若显存/速度不达标 → **REASON 临时降到 Nano 4B**，档位写清 |

### 2.4 为何 Embedding 不跟着换成 Nemotron

- RAG 质量与「检索模型是否 NVIDIA 官方 **embedding**」绑定；**nv-embedqa-e5-v5** 已是 NVIDIA 对位，且 compose/agent.yaml 已写好。  
- Nemotron 三件套是 **生成/多模态**，不能在工程上替代专用 embedding NIM。  
- 换 embedding 只会拖慢 N2 闭环。

### 2.5 为何 Guardrails / Timo 不动

- NeMo Guardrails 是 NVIDIA 安全栈，与 Nemotron 推理栈并列，不是竞品。  
- Timo 是商业真相层；Nemotron 越强，越要展示 **「谁提议、谁裁决」**。

---

## 3. 新拓扑（驻留策略）

```
峰值常驻（推荐 3 重模块）
  ① Timo 引擎 :7862
  ② Nemotron 3 Nano 4B     → 网关 :9000/v1  (FAST)
  ③ nv-embedqa 或 Qwen3-Embed → :8011 或 :9000 (EMBED)

按需加载
  Lightning 30B-A3B GGUF   → REASON 请求时拉起（llama-server）
  Nemotron 3 Nano Omni     → 图纸/语音场景
  FunASR / Qwen3-ASR       → Omni 音频不可用时

公网
  Workbench 8888 → 8051
  Model Gateway 9000 → 9051
```

---

## 4. models.yaml / router 目标写法

```yaml
model_router:
  backend: local          # NIM 实跑绿再改 nvidia
  roles:
    FAST:
      endpoint: "http://127.0.0.1:9000/v1"
      model: "nemotron-3-nano-4b"
      family: nvidia-nemotron
    REASON:
      endpoint: "http://127.0.0.1:9000/v1"
      model: "nemotron-3.5-lightning-30b-a3b-gguf"
      family: nvidia-nemotron
      note: "资源不足时降级 nemotron-3-nano-4b"
    VISION:
      endpoint: "http://127.0.0.1:9000/v1"
      model: "nemotron-3-nano-omni"
      family: nvidia-nemotron
      enabled: "auto"     # 探活失败显式 mock
    EMBED:
      endpoint: "http://127.0.0.1:8011/v1"
      model: "nvidia/nv-embedqa-e5-v5"
      family: nvidia-nim
      fallback:
        endpoint: "http://127.0.0.1:9000/v1"
        model: "Qwen3-Embedding-0.6B"
    ASR:
      endpoint: "http://127.0.0.1:9000/v1"
      model: "nemotron-3-nano-omni"
      fallback:
        model: "Qwen3-ASR-0.6B"   # 或 funasr :8089
    DETERMINISTIC:
      endpoint: "http://127.0.0.1:7862"
      model: "calc_quote+ConflictChecker"
      locked: true
```

> 实际 `model` 字段以上游发布名为准；节点探活后 **以 `/v1/models` 返回 id 为准** 写入配置，禁止臆造 id 上台面。

---

## 5. 门禁 → 启用矩阵（Nemotron 版）

| 门禁结果 | FAST | REASON | VISION/ASR | EMBED | 口播 |
|----------|------|--------|------------|-------|------|
| NIM/权重 + GPU 绿 | Nano 4B | Lightning GGUF | Omni（探活） | nv-embedqa | N3 目标 |
| 仅进程 GPU | Nano 4B | Lightning 或 4B | Omni 或 mock | Qwen3-Embed | N1–N2 |
| 仅 smi | 冒烟 0.6B | 0.6B | mock | hash | N0 |

---

## 6. 明确调整后的「不选」

| 不选（相对 v1 收紧） | 原因 |
|----------------------|------|
| Llama-3.1-8B 作**主**叙事 | 被 Nemotron Nano 4B + Lightning 替换；仅作 NIM 镜像不可用时的历史备选 |
| Parakeet 作**主** ASR 叙事 | 被 Omni 接棒；Parakeet/中文 ASR 降为回退 |
| 同时常驻 4B + 30B + Omni | GB10 也吃紧，演示翻车 |
| 用 Lightning 直接出价格 | 违反铁律 |

---

## 7. 推理链（为什么这套替换「说得通」）

```
赛题要 NVIDIA 全栈
    → 生成模型统一 Nemotron 家族（4B 常驻 + 30B-A3B 质量档 + Omni 多模态）
    → 检索用 NVIDIA nv-embedqa（生成模型顶替不了）
    → 无 sudo/单机 → GGUF/llama.cpp + OpenAI 兼容网关
    → 业务可验证 → Timo 裁决 + NeMo 护栏 + Skills 负向/A-B
    → 证据分级 N0–N5，装不上就降级，不假称
```

---

## 8. 一句话

> **Nano 4B 顶掉通用 8B/0.6B 主路径，Lightning 30B-A3B-GGUF 顶掉 REASON 大模型，Omni 顶掉分散 VLM/ASR 叙事；Embedding 仍是 nv-embedqa，价格仍是 Timo——NVIDIA 更纯，GB10 仍能落。**
