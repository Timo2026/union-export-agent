# 方案 v2 · GPU 优先：NVIDIA 架构上的模型栈跑通

| 字段 | 内容 |
|------|------|
| 版本 | **v2.0.0-gpu-model-stack**（取代以“泛化 P0→P5”为主的旧总图作为**执行主方案**） |
| 日期 | 2026-09-20 |
| 核心目标 | **在 DGX Spark（GB10）上用 NVIDIA 驱动/运行时把 GPU 与模型栈跑通**，再接到 livekernel |
| 节点 | spark-51（内网 spark-388d）· 已 SSH 连通 |
| 提交主体 | 仍为 `union-export-agent-livekernel`；本方案决定**平台层怎么盖** |
| 战略不变 | LLM 只提议；**价格永远 Timo 引擎裁决**；GPU 是 AI Runtime，不是业务真相 |
| 密级 | 节点密码只在本地登录表；**禁止**写入本文/仓库/视频 |

> 旧文 `PLAN-full-pipeline-P0-to-delivery.md` 降为阶段管理附录；**冲突时以本文为准**。

---

## 1. 修订后的核心命题

你要求的主线不是「文档层讲 NVIDIA」，而是：

> **底层逻辑用 NVIDIA 架构（驱动 → CUDA → 推理运行时 → OpenAI 兼容服务）跑通 LLM / vLLM / ASR / OCR / Qwen3-Embedding-0.6B，再由 livekernel 的 Model Router 接入同一套业务 Skills。**

评分与答辩含义：

- 平台适配分 = **节点上真实 GPU/模型调用日志**，不是 yaml 占位  
- 「接口兼容 ≠ 行为等价」= 同一黄金链在 **NVIDIA 运行时端点** 与本地端点各跑一遍，**报价 sha256 一致**  
- 商业价值叙事不改，但**证据锚点改为 GPU 模型栈上的 Agent 闭环**

---

## 2. 节点实测基线（不可假设的部分）

| 项 | 实测 | 对方案的约束 |
|----|------|----------------|
| GPU | **NVIDIA GB10**（Grace-Blackwell） | 服务器级 iGPU/DGX Spark 形态；算力 **sm_(12,1)** |
| 驱动 / CUDA | **580.82.09 / CUDA 13.0** | 用户态 CUDA 栈已就绪；`torch.cuda.is_available()==True` |
| 系统 | Ubuntu 24.04 · **aarch64** · glibc 2.39 | 包必须是 **linux-aarch64**，不是 x86 wheel |
| 权限 | **Developer，无 sudo** | 不能 apt；一切用户级（`~/.local`、conda、源码前缀） |
| Python | 3.12.3 · PEP668 | `pip install --user` 或 venv/conda |
| 已装 | torch **2.14.0+cu130** + transformers 等（用户级） | 推理依赖主体已在 |
| 已有模型 | `~/inference/models/Qwen3-0.6B`（1.5GB BF16） | LLM 冒烟已通过 |
| 阻断 | GPU 推理时 **Triton JIT 失败：缺 `Python.h`**（无 python3-dev） | **G0 必破**；否则只能 CPU 演示 |
| 网络 | pypi.org/HF 官方源差；**清华/阿里/PyTorch 源可达** | 模型与 wheel 走镜像 |
| 磁盘 | ~1.5T 可用 | 可放多模型；仍禁止 scp 超大包 |
| 对外 | 仅节点内 `0.0.0.0:8888` / `9000` 映射公网 | 模型网关与 Workbench 绑这两口 |
| 已知坑 | 僵尸 ollama 404 下载已清理 | 长任务进 tmux；下载用节点内 wget/ModelScope |

**结论**：地基是「NVIDIA 驱动 + CUDA 13 已在」；缺的是 **GPU 可用的推理内核（头文件/兼容路径）+ 完整模型服务化 + livekernel 接线**。

---

## 3. 底层逻辑：NVIDIA 架构分层（必须讲清、按此部署）

```
┌─────────────────────────────────────────────────────────────────┐
│  L4  业务 Agent（livekernel）                                     │
│      Skills 33 · CAT/状态机 · Guardrails · HITL · 审计链          │
│      报价数字 → Timo 确定性引擎（DETERMINISTIC，永不走 LLM）        │
├─────────────────────────────────────────────────────────────────┤
│  L3  统一模型面（OpenAI 兼容 /v1）                                 │
│      model_router / models.yaml / settings.dgx-spark-p0.yaml     │
│      roles: FAST · VISION · REASON · EMBED · ASR · OCR           │
│      backend: local(spark-runtime) | nvidia(NIM) | mock          │
├─────────────────────────────────────────────────────────────────┤
│  L2  NVIDIA/本地推理运行时（GPU 优先，CPU 显式降级）                 │
│      LLM: vLLM(目标) / transformers+torch(基线) / llama.cpp(备)   │
│      Embed: Qwen3-Embedding-0.6B (GPU/CPU)                       │
│      ASR: Qwen3-ASR / FunASR（不用 Parakeet 自托管）               │
│      OCR: RapidOCR/Paddle 路径（GPU 可选）                         │
│      （可选）NIM 容器：nvcr.io … —— 有镜像/权限再切 backend=nvidia │
├─────────────────────────────────────────────────────────────────┤
│  L1  NVIDIA 平台层（节点现状）                                      │
│      GB10 · Driver 580.82.09 · CUDA 13.0 · sm_12,1               │
│      aarch64 · 无 sudo · 用户级 Python/torch+cu130                │
└─────────────────────────────────────────────────────────────────┘
```

**工程铁律（底层逻辑一句话）**：

1. **Replace the adapters, not the architecture** — 只换 L2/L3 端点，L4 契约不变。  
2. **LLM 提议，引擎裁决** — GPU 再强也不生成 `unit_price`。  
3. **接口兼容 ≠ 行为等价** — 换到 NVIDIA 运行时必须做黄金链回归（结构字段 + 价格 sha256）。  
4. **降级必须显式** — GPU/模型不可用时 `mock`/CPU/离线引擎，日志写清 `_source`，禁止冒充。  
5. **单机不常驻全家桶** — Model Mesh 按任务加载/卸载，避免 128GB 级节点被无用权重占满。

---

## 4. 模型栈目标矩阵（跑通定义）

| 角色 | 目标模型 | 目标运行时 | GPU 跑通判据 | livekernel 接线 | 降级 |
|------|----------|------------|--------------|-----------------|------|
| **LLM / REASON / FAST** | Qwen3-0.6B（已有）→ 可选 1.7B/4B 级 | **优先 vLLM**；基线 transformers+torch | `torch.cuda.is_available` 且生成日志含 device=cuda；tok/s 明显优于 CPU | `models.llm/vlm.endpoint` → 网关 `/v1` | CPU 13 tok/s 已验证 |
| **VLM（图纸感知）** | 可先与 LLM 同权重的小 VLM 或显式跳过 | 同 LLM 服务或 mock | 有则探活 `/v1/models`；无则 `enabled` 诚实关闭 | `models.vlm` | MOCK 标注，不定价格 |
| **Embedding** | **Qwen3-Embedding-0.6B** | transformers / optimum / 向量服务包 `/v1/embeddings` | 向量维度稳定；同句相似度 > 异句 | `models.embedding` + `rag_layers.embed_url` | HashEmbedder 确定性降级（已有） |
| **ASR** | Qwen3-ASR-0.6B 或 FunASR 中文模型 | FunASR/自研 engine（节点网关） | 短音频→文本；在线才标 online | `models.asr` + funasr adapter | 离线 MOCK |
| **OCR** | PaddleOCR 或 RapidOCR（ONNX） | CPU 可接受；GPU 可选 | 图纸/PO 截图出文本 | `models.ocr` + intake | 引擎/规则兜底，显式 offline |
| **vLLM 本身** | 作为 **LLM 服务化引擎** | `vllm serve` 或等价 | `/v1/models` + chat/completion 200 | 网关端口进 models.yaml | 无 vLLM 则 transformers 起 OpenAI 包装 |
| **NIM（可选）** | 官方 NIM 镜像 | docker（节点若可用） | `/v1/models` 探活 | `model_router.backend=nvidia` | 镜像/权限不够则不宣称 |
| **DETERMINISTIC** | Timo calc_quote + ConflictChecker | FastAPI :7862 或离线 vendored | `/api/health` + 报价 JSON + sha256 | `models.deterministic` **locked** | byte-identical 离线 |

**「跑通」分级（答辩口径必须用分级，禁止混称）**：

| 级 | 含义 | 证据 |
|----|------|------|
| **L0 识别** | `nvidia-smi` 看到 GB10/CUDA | env-selfcheck |
| **L1 可用** | torch CUDA available；分配 tensor 上 GPU | python 片段日志 |
| **L2 推理** | 至少 LLM 或 Embedding 在 **GPU** 上前向/生成 | device=cuda 日志 + 耗时 |
| **L3 服务化** | OpenAI 兼容 `/v1` 对外（0.0.0.0:9000 或网关） | curl 200 + 公网/隧道 |
| **L4 业务接入** | livekernel 走该端点完成黄金链 | demo log + 报价一致 |
| **L5 行为等价** | local vs spark-runtime 报价 sha256 一致 | ab/等价报告 |

---

## 5. GPU 阻断与破解路径（P0 专章）

**现象**：CUDA 可见，GPU 推理 Triton JIT 编译失败，缺 `Python.h`（无 sudo 装不了 `python3.12-dev`）。

### 路径 G-A · 用户级 Python 带头文件（优先）

```text
1) 节点安装 Miniconda/Micromamba（用户目录，无需 sudo）
2) conda create -n uea python=3.12
3) 在该环境内 pip 装 torch+cu130（aarch64 源）与 transformers
4) 用 conda python 跑 GPU 推理 —— 通常自带头文件，绕过系统 dev 包
```

### 路径 G-B · 仅补头文件 include（次优）

```text
下载 CPython 3.12.x 源码，解压到 ~/pyinclude/
导出 CPLUS_INCLUDE_PATH / CPATH 含 Include 路径后重试 GPU 推理
不保证 Triton 全绿，但成本低于重装整套 Python
```

### 路径 G-C · 关闭 Triton 依赖的 attention 路径

```text
transformers: attn_implementation="eager"（或 sdpa 若不走 Triton）
验证: 同 prompt GPU vs CPU 输出/耗时
能 L2 即可；不追求 FlashAttention
```

### 路径 G-D · 非 Triton 推理引擎

| 引擎 | 用途 | 备注 |
|------|------|------|
| **llama.cpp / llama-cpp-python** | LLM GPU | aarch64+CUDA 需匹配构建；节点内编译或找 wheel |
| **onnxruntime-gpu** | Embedding/OCR/部分 ASR | 若 aarch64 wheel 可用 |
| **vLLM** | LLM 服务化目标 | aarch64+GB10+cu130 需实测 wheel；失败不硬扛，记 L2 基线+服务包装 |

### 路径 G-E · 组委会/运维（干净解）

申请安装 `python3.12-dev` 或开放容器运行时；**赛期不把胜负押在这条**。

### 门禁

- **G0-DoD**：至少一条路径使 **L1→L2**（GPU 上完成一次 LLM 或 Embedding 计算）并写入 `docs/evidence/spark/gpu/`。  
- 未过 G0：允许继续 CPU+引擎演示，但平台叙事降为「驱动已识别 + CPU 运行时 + 配置级 NVIDIA 接口」，**禁止**口播「GPU 已跑通模型」。

---

## 6. 服务化架构（节点端口与进程）

```
公网 203.0.113.10:8051  →  节点 0.0.0.0:8888
    [livekernel Workbench / 上传 API]  ← 业务与评委主入口
              │ models.yaml / settings.dgx-spark-p0.yaml
              ▼
节点 0.0.0.0:9000  →  公网 :9051
    [Model Gateway · OpenAI 兼容聚合]
      /v1/models  /v1/chat/completions  /v1/embeddings
      /v1/audio/transcriptions   /ocr（自定义，文档化）
              │
    ┌─────────┼─────────┬──────────┬─────────┐
    ▼         ▼         ▼          ▼         ▼
  LLM/vLLM  Embed    ASR        OCR      (可选NIM)
  Qwen3-*   Qwen3-   Qwen3-ASR  Rapid/   nvcr.io
  transformers Embed  /FunASR    Paddle
  或 vLLM   -0.6B
              │
              ▼  (不经过 LLM)
        Timo :7862 / offline kernel  DETERMINISTIC
```

| 进程 | 监听 | 启动要点 | tmux |
|------|------|----------|------|
| Model Gateway | `0.0.0.0:9000` | FastAPI 包装各模型；统一 `/v1`；token 鉴权（官方红线） | `uea-gw` |
| livekernel API/UI | `0.0.0.0:8888` | `start_api` 改端口；读 dgx-spark settings | `uea-api` |
| Timo 引擎 | `127.0.0.1:7862` | 内网即可；公网走 ssh -L | `uea-engine` |
| 可选 NIM | 容器端口映射 | 仅 docker 可用且镜像拉得动时 | `uea-nim` |

**配置接线（节点）**：

```yaml
# config/settings.dgx-spark-p0.yaml（方向）
profile: dgx-spark-p0
model_router:
  backend: local          # 有 NIM 实跑证据后再改 nvidia
  roles:
    FAST:   { endpoint: "http://127.0.0.1:9000/v1", model: "Qwen3-0.6B" }
    REASON: { endpoint: "http://127.0.0.1:9000/v1", model: "Qwen3-0.6B" }
    EMBED:  { endpoint: "http://127.0.0.1:9000/v1", model: "Qwen3-Embedding-0.6B" }
    ASR:    { endpoint: "http://127.0.0.1:9000/v1", model: "Qwen3-ASR-0.6B" }
    # DETERMINISTIC 永远 Timo
server:
  host: "0.0.0.0"
  workbench_port: 8888
```

Gateway 实现建议落在：`deploy/spark/model_gateway/`（节点脚本）或 `services/spark_model_gateway.py`（可测），**OpenAI schema 对齐**，避免 livekernel 改架构。

---

## 7. 分模型实施卡（怎么做）

### 7.1 LLM + vLLM（GPU 门面）

| 步 | 动作 | 验收 |
|----|------|------|
| 1 | G0 破 Triton/头文件（G-A/C 优先） | GPU generate 一次 |
| 2 | 评估 `pip install vllm`（aarch64+cu130） | import 与 `vllm --help` |
| 3 | 成功：`vllm serve Qwen3-0.6B --host 0.0.0.0 --port …`（挂到 gateway 后端） | `/v1/chat/completions` |
| 4 | 失败：transformers GPU + **自写 OpenAI 兼容层**（chat/completions） | 同上；evidence 写「vLLM 未在本平台装上，基线为 torch」 |
| 5 | 可选加大模型 | 显存/磁盘允许再拉；**演示质量优先小而稳** |

**提示词**：RFQ 抽取/schema 用现成 `config/prompts/*.yaml`；0.6B 只保证链路，**不把抽取质量赌在 0.6B**——质量路径仍是规则+引擎+RAG。

### 7.2 Qwen3-Embedding-0.6B（RAG 检索，优先第二条 GPU 链）

| 步 | 动作 | 验收 |
|----|------|------|
| 1 | 节点内 ModelScope/镜像下载权重（勿 scp） | 目录完整 |
| 2 | transformers 前向，`device=cuda` | 向量维度日志 |
| 3 | Gateway `/v1/embeddings` | curl 与 livekernel `rag_layers.embed_url` |
| 4 | 与 file 后端向量持久化联调 | 检索命中 golden case |

### 7.3 ASR

| 步 | 动作 | 验收 |
|----|------|------|
| 1 | 选用 Qwen3-ASR-0.6B 或 FunASR 中文模型（节点内下载） | 权重就位 |
| 2 | 本地推理 API（可并入 gateway） | 短 wav→文本 |
| 3 | **明确不用 Parakeet 自托管**（Blackwell 自托管约束，见 NVIDIA-MAPPING） | 文档一致 |
| 4 | livekernel funasr adapter 指到节点端点 | intake 语音路径 |

### 7.4 OCR

| 步 | 动作 | 验收 |
|----|------|------|
| 1 | RapidOCR(ONNX) 或 Paddle 用户级安装 | import |
| 2 | PO/图纸样例出字 | 截图+json |
| 3 | `models.ocr.enabled` 按实测开关 | 不冒充 |

### 7.5 Timo 确定性引擎（与 GPU 并行）

| 步 | 动作 | 验收 |
|----|------|------|
| 1 | 引擎源码进 `/workspace/_timo_engine/...`，用户级 venv | Linux 路径 |
| 2 | `:7862` 或离线 vendored | health / golden 3/3 |
| 3 | 黄金链证明：有无 GPU，**价格 sha256 不变** | evidence |

---

## 8. 与 livekernel / 比分的衔接（盖完 GPU 房子之后）

| 阶段代号 | 内容 | 相对旧总图 |
|----------|------|------------|
| **G0** | GPU 破阻（L1→L2） | 新的真正 P0 |
| **G1** | Model Gateway + LLM/Embed 服务化（L3） | 替代泛化「P1 水电」前半 |
| **G2** | ASR/OCR 接入 + models.yaml 切换 | 原 P2 模型项 |
| **G3** | livekernel 上节点：8888 + skills 整包 + 黄金链（L4） | 原 P1 主体，时序后置但并行可做 |
| **G4** | A/B + 行为等价 + negative trigger（L5 + Skills 分） | 原 P2/P3 |
| **G5** | 证据包/脱敏/版本 pin/提交答辩 | 原 P4/P5 |

**可并行**：G0/G1 与「本机 negative trigger 文档」「密钥清理」并行；**不可并行替代**的是：未过 G2 前不要在答辩称「模型栈已 NVIDIA 化」。

---

## 9. 证据目录（GPU 方案专用）

```
docs/evidence/spark/
  gpu/
    00-nvidia-smi.txt
    01-cuda-torch-probe.py.log      # is_available, device name, sm
    02-llm-gpu-generate.log         # device=cuda, tok/s
    03-vllm-or-torch-service.log    # /v1 探活
    04-embedding-gpu.log
    05-asr.log
    06-ocr.log
  00-env-selfcheck.txt
  01-gateway-health.txt
  02-workbench-8888.md
  03-golden-chain-on-spark.log
  nvidia/
    models-yaml-diff.md
    backend-local-vs-nvidia.md
  ab/
    golden-price-sha256-local-vs-spark.json
    ab-report-skills-on-off.json
skills/
  negative-trigger-matrix.md
  negative-pytest.txt
```

---

## 10. 执行顺序（确认后的开工队列）

| 序 | 批次 | 内容 | 完成定义 |
|----|------|------|----------|
| 1 | **G0-GPU** | 路径 G-A/C 实测；L2 证据落盘 | GPU 上至少 LLM 或 Embed 一次 |
| 2 | **G1-GW** | 用户级服务包装 `/v1`；绑 `0.0.0.0:9000`；token | curl 公网/隧道 200 |
| 3 | **G2-ASR-OCR** | 节点内下载权重；网关扩展 | 各角色探活或诚实 disabled |
| 4 | **G3-AGENT** | rsync livekernel + dgx-spark settings + 8888 | Workbench 可达 + golden |
| 5 | **G4-EVID** | 等价 sha256 + A/B + negative trigger | 证据包齐 |
| 6 | **G5-SHIP** | 脱敏、版本 pin、提交/答辩口径含分级 L0–L5 | 可交付 |

**本机并行小队列**：明文密码脚本移出交付面 · pytest 复跑 · SKILL negative 文段 · 答辩「GPU 分级」话术。

---

## 11. 风险（GPU 特化）

| 风险 | 等级 | 处置 |
|------|------|------|
| vLLM 在 aarch64/GB10/cu130 装不上 | **高** | 基线 transformers GPU + 自研 OpenAI 包装；evidence 写明；不硬吹 vLLM |
| Triton 头文件仍无法用户级解决 | 高 | G-C eager / G-D llama.cpp/ORT；L2 保住一条 |
| 0.6B 质量差 | 中 | 链路验证用 0.6B；业务质量靠规则引擎+RAG+Skills |
| 公网 9000/8888 无鉴权 | 高 | gateway 与 Workbench 加 token（官方红线） |
| 密码进仓 | 高 | 执行时用本地凭据/环境变量，脚本不入库 |
| 单机显存/带宽被多模型打满 | 中 | 按需加载；演示只驻留 LLM+Embed |
| 把 GPU 服务当业务真相 | 中 | 答辩固定句：价格引擎裁决 |

---

## 12. 答辩口径（GPU 版）

**30 秒**：

> 在 DGX Spark 的 GB10 与 CUDA 13 上，我们把 LLM、Embedding（Qwen3-Embedding-0.6B）、ASR/OCR 收成 OpenAI 兼容模型面，用 NVIDIA 驱动作为本地 AI Runtime；Union Agent 的 Skills 在其上编排，但报价数字始终由确定性引擎裁决。

**被问「是不是 GPU 跑的」**：

> 请看 `evidence/spark/gpu/`：`nvidia-smi`（L0）→ torch CUDA（L1）→ device=cuda 生成/向量（L2）→ `/v1` 服务（L3）→ 黄金链（L4）→ 价格 sha256 等价（L5）。当前现场达到 ____ 级，不足处已标明，不冒充。

**被问「vLLM 还是 NIM」**：

> 目标运行时是 vLLM/NIM；本节点无 sudo + aarch64，以实测为准：____。接口全部 OpenAI 兼容，`model_router` 配置级切换，架构未改。

---

## 13. 确认项

- [ ] 接受 **GPU/模型栈为执行主线**（G0–G2 优先于泛化文档工作）  
- [ ] 接受 vLLM/NIM **装得上则用、装不上则 torch 基线 + 诚实分级**  
- [ ] 接受 Timo 引擎与报价铁律不变  
- [ ] 接受端口策略：Workbench **8888**、模型网关 **9000**、公网映射 8051/9051  
- [ ] 接受官方 NVIDIA/skills 仍非全量部署对象  
- [ ] 确认开工队列：**G0-GPU → G1-GW → …**

---

## 14. 一句话

> **在 GB10 + CUDA 13 的 NVIDIA 底座上，先让 GPU 真正算起来，再把 LLM/vLLM/Embedding/ASR/OCR 收成一层 OpenAI 兼容模型面供 livekernel 调用；业务数字仍归引擎——平台分来自 L0–L5 实证，不来自口号。**
