# Union Export Agent LiveKernel — 项目全景摘要

> **⚠️ 已被取代（2026-09-20 晚）**：唯一权威框架为 `docs/PRD-MASTER-UEA-DELIVERY.md` **v2.0**（含 spark-51 节点实测模型栈）。本摘要保留仅供溯源；**下列结论已按节点实测作废/更新**，冲突处一律以主 PRD 为准。**仍有效的资产**（待并入主 PRD，勿删）：第 5 章用户画像、第 6 章行业问题对照表、黄金链 7 步阶段-职责-约束表、六铁律表、33 Skill 分类清单、N0 门禁→回退结构、节点 7 维仪表盘。

| # | 本摘要原结论（行号） | 实测勘误（2026-09-20） |
|---|------|------|
| 1 | `:151`/`:390`/`:413` EMBED = nv-embedqa-e5-v5（NIM，未部署）×3 处 | 换 **`nvidia/Nemotron-3-Embed-1B-BF16`**（2.3GB，hf-mirror 实测可下载） |
| 2 | `:154-156`/`:404-418` Nemotron 清单无仓库 ID/体积/NVFP4 格式、**无 ASR 角色**；`:150` 「规划中，未下载」 | 五件套仓库 ID/体积/文件数见主 PRD §1.2-F；ASR = `nvidia/nemotron-3.5-asr-streaming-0.6b`（5.7GB）；hf-mirror 已实测可下载 |
| 3 | `:194`/`:306`/`:367` ASR 规划为 Qwen3-ASR(:8089) | 实测栈 ASR = `nemotron-3.5-asr-streaming-0.6b`；FunASR(:8866/:8089) 仅为 N0 回退 |
| 4 | `:308` 部署资产 Dockerfile + docker-compose + k8s + hpa ✅（与 `:399` docker 无权限、`:98` 自相矛盾） | **NIM 容器路线已关闭**（docker daemon 无权限 + 无 root）；部署资产仅对「有 docker 权限的目标环境」有效，节点主路径 = pip + 裸进程（vLLM 进程级） |
| 5 | `:206`/`:315`/`:330` 测试 **701 passed** ×3 处 | 复跑实为 **725 passed / 0 failed**（`pytest tests/ -q`，2026-09-20） |
| 6 | `:145`/`:147`/`:166`/`:167` GPU bf16 **62.6 tok/s**、4.8× | 实测 **~77 tok/s** |
| 7 | `:4` 项目版本 v3.0.1（权威口径） | 版本三处分裂：`api_server.py:88`=6.1.0-livekernel、README 述及 v6.2、MANIFEST/git tag 止于 v3.0.1 |

> **文档定位**：英伟达比赛参赛项目「Union Export Agent LiveKernel」的一站式全景审计摘要。
> **文档版本**：v1.0 ｜ **生成日期**：2026-09-20 ｜ **项目版本**：v3.0.1 (2026-09-18, 双飞轮 v6.2 WIP)
> **文档作者**：项目文档工程师 ｜ **审计范围**：节点环境 7 维 + 项目架构 + agent/skill/部署/测试 + 用户画像 + 行业问题 + Nemotron 升级路径

---

## 0. 项目本质（一句话）

> **把制造业询盘邮件端到端变成可审计、可验证、可自动决策的商业对象。L3 条件性自动驾驶。**

| 维度 | 定位 |
|------|------|
| 自动驾驶等级 | **L3 条件性自动驾驶**（PASS 自动批准 / HITL 人工介入 / BLOCKED 阻断通知） |
| 商业对象 | 询盘邮件 → 可审计、可验证、可决策的结构化报价单 |
| 审计保证 | SHA-256 全链路哈希固化 |
| 决策闭环 | CEO/Reid 双 LLM 决策 + FleetCoordinator v4（3 专家 + Loop + Critic） |

---

## 1. 黄金链（Golden Chain）

```
Gmail IMAP
   │
   ▼
MailPuller (30s 轮询)
   │
   ▼
MailOrchestrator
   │
   ▼
CATController (黄金链 7 步)
   │
   ▼
① Intake → ② RFQ 提取 → ③ DFM 冲突 → ④ Timo v12 确定性报价
   │
   ▼
⑤ 五步验证（辟牟援推止）
   │
   ▼
FleetCoordinator v4 (3 专家 + Loop + Critic)
   │
   ▼
CEO / Reid 双 LLM 决策
   │
   ├── PASS → 自动批准
   ├── HITL → 人工审核
   └── BLOCKED → 人工通知
   │
   ▼
CRM + Memory
   │
   ▼
SHA-256 审计
```

| 阶段 | 职责 | 关键约束 |
|------|------|----------|
| Intake | 邮件接入与归一化 | Context 唯一（铁律③） |
| RFQ 提取 | 询盘字段结构化 | 多模态冲突升级（铁律⑤） |
| DFM 冲突 | 可制造性冲突检测 | 状态机不可绕（铁律②） |
| Timo v12 报价 | 确定性价格生成 | **LLM 不定价（铁律①）**，价格 100% 来自 Timo 引擎 |
| 五步验证 | 辟牟援推止 | Runtime ≠ 业务（铁律⑥） |
| FleetCoordinator v4 | 3 专家 + Loop + Critic | RAG 仅引用（铁律④） |
| CEO/Reid 决策 | 双 LLM 投票/裁决 | PASS / HITL / BLOCKED 三态 |

---

## 2. 节点环境 7 维（实测数据）

> 以下数据均为节点实测，非规划值。审计时间：2026-09-20。

### 2.1 维度一：设备信息 ✅

| 字段 | 实测值 |
|------|--------|
| hostname | `spark-388d`（公网映射 `spark-51`） |
| 操作系统 | Ubuntu 24.04.3 LTS (Noble Numbat) |
| 架构 | `aarch64` (ARM64) |
| glibc | 2.39 |
| 内核 | `6.11.0-1014-nvidia` (PREEMPT_DYNAMIC) |
| CPU | Cortex-X925 × **20 核** |
| 内存 | **121 GB** 统一内存（GB10 Grace-Blackwell 架构） |
| 磁盘 | 3.7 TB NVMe，1.5 TB 可用 |
| 权限 | Developer 用户，**无 sudo** |

### 2.2 维度二：基础软件 ✅

| 软件 | 版本 | 备注 |
|------|------|------|
| Python | 3.12.3 | 系统 Python，PEP 668 受保护 |
| pip | 24.0 | 需 `--break-system-packages` |
| gcc | 13.3.0 | — |
| git | 2.43.0 | — |
| tmux | 3.4 | — |
| Docker | 28.3.3 | ⚠️ **无权限**，Developer 不在 docker 组 |
| curl | 8.5.0 | — |

### 2.3 维度三：引擎 ✅

| 字段 | 实测值 |
|------|--------|
| 引擎 | **Timo v12** 确定性报价引擎 |
| 设计端口 | `:7862` |
| 当前状态 | ⚠️ 当前节点未在线 |
| 引擎源码 | `/workspace/_timo_engine/Timo_CNC-AI-Brain-v12.0-Fusion` |
| 兜底机制 | ✅ 离线 byte-identical 兜底 |
| 熔断器 | ✅ 三态（Closed / Open / Half-Open） |

### 2.4 维度四：驱动 ✅

| 字段 | 实测值 |
|------|--------|
| GPU | NVIDIA **GB10**（Grace-Blackwell / Jetson Thor 平台） |
| 驱动 | 580.82.09（Open Kernel Module for aarch64） |
| CUDA | **13.0** |
| 计算能力 | `sm_121` (Blackwell) |
| 显存 | 统一内存架构（`nvidia-smi` memory 字段 = N/A，与 CPU 共享 121 GB） |

### 2.5 维度五：Conda / Venv 环境 ✅

| 字段 | 实测值 |
|------|--------|
| Conda | ❌ 无 |
| 节点 venv | `~/inference/venv/`（Python 3.12.3） |
| 用户级 pip 包路径 | `~/.local/lib/python3.12/site-packages` |

**关键用户级包**：

| 包 | 版本 | 备注 |
|----|------|------|
| torch | 2.14.0+cu130 | CUDA 13.0 构建 |
| transformers | 5.17.0 | — |
| triton | 3.8.0 | ✅ **已修复**（双 CPATH 路径方案） |
| numpy | 2.5.3 | — |
| accelerate | 1.15.0 | — |

### 2.6 维度六：模型 ✅

| 字段 | 实测值 |
|------|--------|
| 节点现有模型 | **Qwen3-0.6B**（`model.safetensors`, BF16, 596M 参数） |
| GPU bf16 推理吞吐 | **62.6 tok/s** |
| CPU float32 推理吞吐 | 13.1 tok/s |
| 加速比 | **4.8×**（GPU vs CPU） |
| 已部署 API | `:8888`（Qwen3-0.6B GPU bf16） |
| 公网入口 | `:8051`，Bearer 鉴权 |
| Nemotron 全家族 | ⏳ 规划中，未下载 |
| Embedding | `nv-embedqa-e5-v5`（NIM，未部署） |

**Nemotron 全家族（规划中）**：
- `Nemotron-3-Nano-4B`
- `Nemotron-3.5-Lightning-30B-A3B`（MoE 30B 总参 / 3B 激活）
- `Nemotron-3-Nano-Omni`

### 2.7 维度七：硬件测评 ✅

| 场景 | 实测值 |
|------|--------|
| GPU 空闲态 | 0% 利用率，37 °C，11.62 W |
| bf16 matmul sanity | 0.36 s |
| 模型加载 | 5.1 s |
| 推理显存占用 | 1.23 GB |
| 推理吞吐（GPU bf16） | **62.6 tok/s** |
| 推理吞吐（CPU float32） | 13.1 tok/s |
| Jupyter | `:9000` 在线（组委会预装，token = `TimoSpark2026`） |
| Triton | ✅ **已修复**（`dpkg -x` 解包 `libpython3.12-dev` 头文件 + CPATH 双路径） |

### 2.8 七维环境总览仪表盘

| 维度 | 状态 | 关键指标 |
|------|------|----------|
| ① 设备 | ✅ | 20 核 / 121 GB / 3.7 TB NVMe |
| ② 基础软件 | ✅ | Python 3.12.3 / Docker 28.3.3（⚠️ 无权限） |
| ③ 引擎 | ⚠️ | Timo v12 设计 :7862，当前节点未在线，离线兜底就绪 |
| ④ 驱动 | ✅ | GB10 / CUDA 13.0 / sm_121 |
| ⑤ 环境 | ✅ | venv + torch 2.14.0+cu130 + triton 3.8.0 已修复 |
| ⑥ 模型 | ✅ | Qwen3-0.6B 已部署 :8888，62.6 tok/s |
| ⑦ 测评 | ✅ | GPU 4.8× 加速，Jupyter :9000 在线 |

---

## 3. 项目架构

### 3.1 技术栈

| 层 | 选型 | 备注 |
|----|------|------|
| 语言 | Python 3.11 | 标准库优先 |
| API | FastAPI `:8900` + uvicorn | — |
| 制造内核 | **Timo v12** `:7862` | 在线 + 离线 byte-identical |
| 多模态 | `qwen3.8-27b`(:1234) / `Qwen3-Embedding`(:1278) / `Qwen3-ASR`(:8089) | — |
| 数据库 | SQLite ×3 | `crm` / `suppliers` / `feedback` |
| 缓存 | AgentCache | LRU(100) + TTL(5min) |
| UI | `index.html` (v6 融合) + `webui/index.html` (v5 legacy) | — |
| 部署 | Dockerfile + compose + k8s + hpa | — |

### 3.2 项目规模（实测）

| 指标 | 实测值 | 说明 |
|------|--------|------|
| services | **55** 个核心 `.py` 文件 | 实测含辅助文件共 80 个 |
| skills | **33** 个 skill 目录 | 33/33 含 `tool.py` ✅ |
| tests | **83** 个测试文件 | 70+ ✅，**701 passed** |
| docs | **48** 个 `.md` 文档 | 40+ ✅ |
| 版本 | v3.0.1 (2026-09-18) | 双飞轮 v6.2 WIP |

### 3.3 6 条工程铁律

| # | 铁律 | 含义 |
|---|------|------|
| ① | **LLM 不定价** | 价格 100% 来自 Timo 引擎，LLM 永不介入价格生成 |
| ② | **状态机不可绕** | 黄金链 7 步必须顺序执行，禁止跳步 |
| ③ | **Context 唯一** | 全链路共享唯一 Context，禁止分叉上下文 |
| ④ | **RAG 仅引用** | RAG 只作引用增强，不作决策依据 |
| ⑤ | **多模态冲突升级** | 多模态输入冲突时升级人工，禁止静默吞并 |
| ⑥ | **Runtime ≠ 业务** | 运行时态与业务态隔离，禁止跨态污染 |

---

## 4. Agent / Skill / 部署 / 测试现状

### 4.1 Skill 清单（33 个，全部含 `tool.py`） ✅

> 33 个 skill 按 7 步黄金链 + 飞轮 + 工具类组织。

#### 4.1.1 黄金链核心 skill

| Skill | 职责 |
|-------|------|
| `golden-chain` | 黄金链编排 |
| `orchestrator` | 总编排器 |
| `parse-rfq` | RFQ 解析 |
| `rfq-extraction` | RFQ 字段提取 |
| `check-dfm` | DFM 冲突检测 |
| `dfm-conflict` | DFM 冲突裁决 |
| `calc-quote` | 报价计算（调用 Timo v12） |
| `cnc-quote` | CNC 报价专用 |
| `verify-gate` | 验证门禁 |
| `verification` | 五步验证（辟牟援推止） |
| `step-analysis` | 步骤分析 |

#### 4.1.2 决策与编排 skill

| Skill | 职责 |
|-------|------|
| `fleet-coordinator` | FleetCoordinator v4（3 专家 + Loop + Critic） |
| `ceo-decision` | CEO LLM 决策 |
| `reid-os` | Reid LLM 决策 |
| `quality-loop` | 质量循环 |
| `material-expert` | 材料专家 |
| `dfm-expert` | DFM 专家 |
| `price-expert` | 价格专家 |
| `feasibility-checker` | 可行性检查 |

#### 4.1.3 报价与回复 skill

| Skill | 职责 |
|-------|------|
| `quote-calibration` | 报价校准 |
| `quote-correction` | 报价修正 |
| `batch-quote` | 批量报价 |
| `reply-draft` | 回复草稿 |
| `write-reply` | 回复撰写 |
| `submit-feedback` | 反馈提交 |
| `extract-specs` | 规格提取 |
| `render-thumbnail` | 缩略图渲染 |
| `supplier-match` | 供应商匹配 |
| `freight-customs` | 运费 + 关税 |

#### 4.1.4 飞轮与工具 skill

| Skill | 职责 |
|-------|------|
| `customer-flywheel` | 客户飞轮 |
| `customer-health` | 客户健康度 |
| `retention-alert` | 留存预警 |
| `rag-ingest` | RAG 摄入 |

**Skill 完备性**：33/33 含 `tool.py` ✅，零空壳。

### 4.2 Agent 现状

| Agent | 角色 | 状态 |
|-------|------|------|
| MailPuller | 30s 轮询 Gmail IMAP | ✅ |
| MailOrchestrator | 邮件编排 | ✅ |
| CATController | 黄金链 7 步控制器 | ✅ |
| FleetCoordinator v4 | 3 专家 + Loop + Critic | ✅ |
| CEO | LLM 决策（PASS/HITL/BLOCKED） | ✅ |
| Reid | LLM 决策（双 LLM 裁决） | ✅ |

### 4.3 部署现状

| 组件 | 端口 | 状态 |
|------|------|------|
| FastAPI 主服务 | `:8900` | ✅ |
| Qwen3-0.6B GPU bf16 | `:8888` | ✅ 已部署 |
| 公网入口（Bearer 鉴权） | `:8051` | ✅ |
| Jupyter（组委会预装） | `:9000` | ✅ 在线 |
| Timo v12 引擎 | `:7862` | ⚠️ 设计端口，当前节点未在线，离线兜底就绪 |
| qwen3.8-27b 多模态 | `:1234` | 规划 |
| Qwen3-Embedding | `:1278` | 规划 |
| Qwen3-ASR | `:8089` | 规划 |

**部署资产**：Dockerfile + docker-compose + k8s + hpa ✅

### 4.4 测试现状

| 指标 | 实测值 |
|------|--------|
| 测试文件数 | **83** 个 |
| 通过用例 | **701 passed** ✅ |
| 测试覆盖 | services / skills / agents / 黄金链 / 验证门禁 |

---

## 5. 用户画像

### 5.1 给谁用

| 用户角色 | 痛点 | 使用方式 |
|----------|------|----------|
| **外贸制造业企业**（CNC 加工 / 钣金 / 注塑） | 询盘响应慢、报价不一致、多模态输入处理难 | 企业级接入，邮箱接单 → 自动报价 → 人工审核 → 客户回复 |
| **外贸业务员** | 手动回复询盘耗时长（~2h/封）、易遗漏 | Workbench UI `:8888` 监控全链路，L3 自动驾驶释放人力 |
| **工厂报价工程师** | 报价依赖个人经验、不一致、难审计 | Timo v12 确定性引擎兜底，DFM 冲突自动检测，HITL 介入仅处理异常 |

### 5.2 怎么用

```
① 邮箱接单        Gmail IMAP → MailPuller (30s 轮询)
       │
       ▼
② 自动报价        黄金链 7 步 → Timo v12 确定性报价 → 五步验证
       │
       ▼
③ 人工审核        Workbench UI :8888 → HITL 介入 / PASS 自动批准 / BLOCKED 通知
       │
       ▼
④ 客户回复        reply-draft + write-reply → CRM + Memory → SHA-256 审计
```

**主入口**：Workbench UI `:8888`（v6 融合版 `index.html`）

### 5.3 如何用户好（价值量化）

| 指标 | 优化前（手动） | 优化后（L3 自动驾驶） | 提升 |
|------|----------------|----------------------|------|
| 询盘响应时长 | ~2 h | ~3 min | **~40×** |
| 报价一致性 | 依赖个人经验（LLM 幻觉风险） | Timo v12 确定性引擎 | **消除幻觉** |
| 多模态输入 | 邮件 + 图纸 + 语音分散处理 | 统一管道 | **统一** |
| 人力释放 | 全人工 | L3 自动驾驶，仅异常 HITL | **大幅释放** |
| 审计能力 | 弱 | SHA-256 全链路固化 | **可审计** |

---

## 6. 行业问题（解决了什么）

### 6.1 外贸制造业三大行业痛点

| # | 行业痛点 | 本项目解决方案 | 量化效果 |
|---|----------|----------------|----------|
| ① | **询盘响应慢**（小时级） | 黄金链 7 步 + Timo v12 确定性引擎 + L3 自动驾驶 | 小时级 → **分钟级**（~3 min） |
| ② | **报价不一致**（LLM 幻觉 / 个人经验差异） | 铁律① LLM 不定价，价格 100% 来自 Timo v12 确定性引擎 | **消除幻觉**，byte-identical 兜底 |
| ③ | **多模态输入处理难**（邮件 + 图纸 + 语音） | 统一管道：qwen3.8-27b(:1234) + Qwen3-Embedding(:1278) + Qwen3-ASR(:8089) | **统一管道**，冲突升级人工（铁律⑤） |

### 6.2 工程保证

| 保证 | 机制 |
|------|------|
| 可审计 | SHA-256 全链路哈希固化 |
| 可验证 | 五步验证（辟牟援推止） + verify-gate |
| 可自动决策 | CEO/Reid 双 LLM 决策 → PASS / HITL / BLOCKED 三态 |
| 确定性 | Timo v12 引擎 + 离线 byte-identical 兜底 + 熔断器三态 |
| 状态机不可绕 | 铁律②，黄金链 7 步顺序执行 |

---

## 7. Nemotron 全家族升级路径（v2，刚建好地基）

### 7.1 五角色分工

| 角色 | 模型 | 端口 | 定位 |
|------|------|------|------|
| **FAST** | Nemotron-3-Nano-4B | `:8002` | 边缘极速 |
| **REASON** | Nemotron-3.5-Lightning-30B-A3B | `:8000` | MoE 30B 总参 / 3B 激活，推理主力 |
| **OMNI** | Nemotron-3-Nano-Omni | `:8020` | VLM + ASR + OCR 三合一 |
| **EMBED** | nv-embedqa-e5-v5 | `:8011` | Embedding |
| **DETERMINISTIC** | Timo 引擎 | `:7862` | **铁律①锁定，永不平替** |

### 7.2 N0 门禁（当前节点回退策略）

| 条件 | 状态 |
|------|------|
| 节点无 NIM | ⚠️ |
| 节点无 Nemotron 权重 | ⚠️ |
| 节点无 docker 权限 | ⚠️ |
| **回退方案** | 进程级回退 → `:8888` Qwen3-0.6B（已部署，62.6 tok/s） |

### 7.3 升级路径

```
当前态（N0 门禁）
  │  Qwen3-0.6B :8888 (62.6 tok/s, bf16)
  │  Timo v12 离线兜底
  ▼
Nemotron v2（地基已建）
  │  FAST  :8002  Nemotron-3-Nano-4B
  │  REASON:8000  Nemotron-3.5-Lightning-30B-A3B (MoE 3B 激活)
  │  OMNI  :8020  Nemotron-3-Nano-Omni (VLM+ASR+OCR)
  │  EMBED :8011  nv-embedqa-e5-v5
  │  DETERMINISTIC :7862  Timo v12（铁律①锁定）
  ▼
目标态
     全家族在线 + Timo v12 确定性锁定 + SHA-256 审计
```

**关键约束**：DETERMINISTIC 角色由 Timo 引擎永久锁定，**永不平替为 LLM**（铁律①）。

---

## 8. 审计结论

### 8.1 就绪度仪表盘

| 维度 | 状态 | 说明 |
|------|------|------|
| 节点环境 7 维 | ✅ 6/7 全绿 | ③ 引擎当前节点未在线（离线兜底就绪） |
| 项目架构 | ✅ | 黄金链 7 步 + 6 铁律 + 双飞轮 v6.2 WIP |
| Skill 完备性 | ✅ 33/33 | 零空壳，全部含 `tool.py` |
| 测试 | ✅ 701 passed | 83 个测试文件 |
| 部署资产 | ✅ | Dockerfile + compose + k8s + hpa |
| 模型部署 | ✅ Qwen3-0.6B :8888 | 62.6 tok/s，Nemotron 规划中 |
| Nemotron 升级 | ⏳ 地基已建 | N0 门禁回退就绪 |

### 8.2 一句话总结

> **Union Export Agent LiveKernel 是一个运行在 NVIDIA GB10 Grace-Blackwell 节点上的外贸制造业询盘 L3 条件性自动驾驶系统，以 Timo v12 确定性报价引擎为价格铁律、以黄金链 7 步状态机为流程骨架、以 FleetCoordinator v4 + CEO/Reid 双 LLM 为决策闭环、以 SHA-256 为审计保证，将制造业询盘邮件端到端变成可审计、可验证、可自动决策的商业对象，当前 Qwen3-0.6B 已部署就绪，Nemotron 全家族升级地基已建。**

---

*文档结束。*