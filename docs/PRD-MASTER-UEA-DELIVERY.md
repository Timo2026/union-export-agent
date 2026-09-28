# MASTER PRD · Union Export Agent 参赛交付全框架（P0 → 交付报告 + 十日谈）

| 字段 | 内容 |
|------|------|
| 文档编号 | **PRD-MASTER-UEA-DELIVERY-v2.0** |
| 日期 | 2026-09-20 |
| 状态 | **交审稿 v2** — 模型栈经节点实测改写；待你勾选/批注后进入 W1 |
| v2.0 变更 | ① 模型表全部改为 hf-mirror 实测仓库 ID/体积（GGUF 与 nv-embedqa 两项作废，见 §1.2-F）② 节点门禁结果落定（docker 无权限 → 全进程级；GPU JIT 已破解，Qwen3-0.6B GPU ~77 tok/s）③ 新增本机 pytest 收集坑与版本三处分裂事实 ④ 十日谈日志源补今日探针 ⑤ `test_deploy_manifests` 旧断言已修，全量 **725 passed / 0 failed**；D 批次 10 份文档全部打上作废/勘误 banner 并挂十日谈指针，本文为唯一权威 |
| 提交主体 | `union-export-agent-livekernel`（唯一） |
| 分支 | `feature/skills-p0-flywheel` |
| 产品一句话 | 把一封 CNC/外贸询盘变成**可审计、可验证、可复盘**的制造业商业对象 |
| 战略 | NVIDIA 全栈平替 + Spark 实证 + Skills 负向/A-B；**价格永远 Timo 引擎裁决** |
| 上位文档 | `PRD-NCPAAI-Spark-Submission.md` · `PLAN-full-pipeline-P0-to-delivery.md`（施工图） |
| 十日谈 | **长卷** `DECAMERON.md`（十日全史 + 每日 commit 索引；正文数字为当日时点，当前口径以本文为准）· **简版** `十日谈.md`（里程碑叙事 M0-M8） |
| 交付报告 | `FINAL-DELIVERY-REPORT.md`（已打勘误 banner，溯源用）· 全景摘要 `PROJECT-AUDIT-SUMMARY.md`（已打勘误 banner；其第 5/6 章用户画像与行业问题待并入本文） |
| 已作废结论 | 以下文档中 REASON=GGUF / EMBED=nv-embedqa / ASR=Parakeet 主路径 / NIM 容器可部署 的结论**一律以本文 §1.2-F 实测为准**：`MODEL-SELECTION-nemotron-v2.md` `MODEL-SELECTION-nvidia-stack.md` `PLAN-nvidia-fullstack-replacement.md` `PRD-NVIDIA-FullStack-Swap.md` `MASTER-PRD-P0-to-Delivery.md` `PRD-P0-DELIVERY.md` `NVIDIA-FULLSTACK-FRAMEWORK.md` `FINAL-DELIVERY-REPORT.md` `PROJECT-AUDIT-SUMMARY.md` |

---

## 0. 本 PRD 回答什么（审核入口）

你要求：**设备→软件→引擎→驱动→conda→模型→测评→Agent→部署→测试→Skill→评估→给谁用→怎么用→行业问题→交付报告→十日谈**。  
本文 = **总框架 + 可行 P0 PRD + 交付报告目录 + 十日谈骨架**（基于仓内日志线索，**未编造未发生的实跑**）。

```
硬件/驱动 → 基础软件/环境 → 引擎与模型 → Agent 建立
    → 部署(本地/Spark) → 测试 → Skill 安装与负向 → 评估
    → 用户与行业价值 → 交付报告 → 十日谈(从日志生长)
```

**v2.0 增量（2026-09-20 晚）**：模型层不再是「选型提案」，而是**经 spark-51 + hf-mirror API 逐一实测的仓库清单**（含体积/文件数/可达性/否决记录）；v1 中「Lightning-30B-A3B-GGUF（REASON）」与「nv-embedqa（EMBED）」两项无实证且与节点现实冲突，已作废；发布口径、时间估算、门禁矩阵同步刷新。同日新增两条工程事实：① 本机 `pytest` 裸跑会误收集 `tools/omnivoice` 内置 venv 的 matplotlib 测试而报 collection error，canonical 命令必须是 `pytest tests/ -q`；② 版本标记三处分裂（`api_server.py:88`=6.1.0-livekernel、README 述及 v6.2、MANIFEST/git tag 止于 v3.0.1），P0-4 须钉死。

---

# 第一部分 · 现状摘要（遍历结论）

## 1.1 资产盘点（仓内已核实）

| 层 | 现状 | 证据锚点 |
|----|------|----------|
| **产品定位** | L3 邮件驱动制造业外贸 Agent；Workbench 三栏；双飞轮；33 Skills | `README.md` |
| **代码结构** | adapters / agents / services / skills / config / deploy / scripts / tests / webui | README 结构树 |
| **Skills** | **33** 个 `SKILL.md`（rfq/calc-quote/dfm/orchestrator/ceo-decision/rag-ingest/batch-quote…） | `skills/*/SKILL.md` glob |
| **测试** | **2026-09-20 晚复跑：725 passed / 0 failed**（`pytest tests/ -q`，7m10s；曾失败项 `test_deploy_manifests.py::test_compose_services_present` 已修——compose 早已更新为 Nemotron 服务名 `nim-nano-4b/nim-lightning/nim-omni/nim-embed`，测试断言仍为旧 `nim-llm`，现改为四服务 GPU 预留校验）；坑：裸 `pytest` 会误收集 `tools/omnivoice` 内置 venv 的 matplotlib 测试 → collection error，canonical = `pytest tests/ -q` | 复跑日志 + ACCEPTANCE-v7 |
| **演示** | `run_demo` / `run_golden_core` / `e2e_l3` / `export_demo`（导出自检 leaks 0） | scripts + ACCEPTANCE |
| **业务实证** | 杰沃 PO 129/129 解析；BOM 410/410 报价；矫正 MAPE 负向结论（诚实） | `docs/SER-清单.md` R-04~R-06 |
| **NVIDIA 契约** | agent.yaml `nemo.agents/v1`；NIM compose；NeMo Guardrails colang；NVIDIA-MAPPING | `config/agent.yaml` `deploy/nim/` |
| **Spark** | SSH 已通；GB10 / sm_(12,1) / 驱动 580.82.09 / CUDA 13.0 实测；121GB 统一内存、20 核、1.5T 空闲；Qwen3-0.6B **GPU ~77 tok/s**（triton JIT 需用户态 `libpython3.12-dev` 头文件 + CPATH，已破解）；**docker daemon 无权限 → NIM 容器路线关闭，全 pip+裸进程**；hf-mirror.com 1.25MB/s 权重通道；8888 空闲、9000 曾被并发会话占用（起服前必须探活） | 今日节点自检 + §1.2 各表 |
| **模型选型** | Nemotron Nano4B-BF16 + Omni-NVFP4 + Lightning-NVFP4 + Embed-1B + ASR-streaming-0.6b，**全部经节点 hf-mirror API 实测可下载**（仓库 ID/体积/文件数见 §1.2-F）；GGUF 与 nv-embedqa 两项**已否决** | 本文 §1.2-F |
| **治理** | openshell 四件套；egress DENY；draft_only；iron-rule-1 | openshell/ settings.yaml |
| **缺口** | Spark 上 livekernel 未跑通；negative trigger 弱；A/B 无正式报告；版本未 pin；工作树大量未提交；仓库面有明文密码风险 | ACCEPTANCE §五 + git status |

## 1.2 运行环境矩阵（设备 / 软件 / 引擎 / 驱动 / conda / 模型 / 测评）

### A. 设备与硬件

| 环境 | 角色 | 已知信息 | 待采集字段（P0-A） |
|------|------|----------|-------------------|
| **本机 Windows** | 开发/测试/文档/演示录制 | Python 3.11 口径（README）；GPU 状态历史文档称本机无 GPU 或非目标 | `nvidia-smi` / CPU / RAM / 磁盘 / OS 版本 |
| **DGX Spark 节点** | 比赛平台实证与演示 | spark-51（内网 spark-388d）· **GB10** · Ubuntu 24.04 aarch64 · 驱动 **580.82.09** · **CUDA 13.0** · compute_cap **sm_(12,1)** · **121GB 统一内存** · 20 核 · NVMe 3.7T（可用 1.5T）· **无 sudo** · docker daemon socket 无权限 · 公网映射仅 **8888→8051、9000→9051**（**主 UI 入口 = `http://203.0.113.10:8051/`**；2026-09-20 探活 = 401 token 门（非本仓服务占居 :8888），上台前须起 workbench 本体，见 §2.2；9000 曾被并发会话占用） | 补：`nvidia-smi` 原始输出归档 W1；内网其余端口走 `ssh -L` |

### B. 基础软件（目标态）

| 组件 | 本机目标 | 节点目标 | 状态 |
|------|----------|----------|------|
| Python | 3.11+（主干） | 3.12.3 系统；**conda/venv 推荐** | 节点 PEP668 |
| pip 源 | 默认/镜像 | **清华/阿里实测可用**（清华 PyPI 2.3MB/s；pypi.org 仅 ~30KB/s） | 节点已配清华 |
| 模型权重通道 | — | **hf-mirror.com 200 @1.25MB/s**（唯一通道；huggingface.co 直连超时；GitHub 200 但 ~80KB/s；ModelScope CDN 9.1MB/s 但无这些 Nemotron 权重） | 已实测 |
| Docker | 可选（NovaStudio） | **门禁结果 = 无权限**：daemon socket permission denied（无 docker 组、无 root）→ NIM 容器 / MinerU 容器 / 引擎 compose 全部关闭，改 **pip + 裸进程 + tmux** | 00-gates 已出结论 |
| NVIDIA Container Toolkit | 可选 | NIM 容器前置 | 待探测 |
| Node.js | 可选 E2E 截图 | 可选 | — |
| tmux | — | **必须**（长任务） | 手册红线 |
| Git / rsync | 有 | 代码上节点 | 禁 scp >1GB |

### C. 引擎（业务真相层）

| 引擎 | 作用 | 端口 | 状态 |
|------|------|------|------|
| **Timo cnc-ai-brain v12** | 确定性报价 + DFM 冲突 | `:7862` | 本机路径在 settings；**节点需 Linux venv 重建**；离线 byte-identical 兜底 |
| Workbench/API | 业务 UI + 上传/黄金链 | 本机 `:8900` / **节点 `:8888`** | 节点未跑通 |
| funasr-gui（可选） | ASR/RAG/多模态网关 | `:8866` 等 | 节点按需/降级 |
| NovaStudio 4 工具 | MinerU/ragflow/OmniVoice/SearXNG | 本机 tools/ | 节点非 P0 |
| Model Gateway | OpenAI 兼容模型面 | **节点 `:9000`** | 方案已写，待部署 |

### D. 驱动与 NVIDIA 栈

| 项 | 本机 | 节点 |
|----|------|------|
| NVIDIA 驱动 | 待采集 | **580.82.09（有）** |
| CUDA | 待采集 | **13.0（有）** |
| torch CUDA | 待采集 | **2.14.0+cu130 已装，`available=True`**；Qwen3-0.6B bf16 GPU 生成 **~77 tok/s**；triton JIT 需用户态 `libpython3.12-dev` 头文件 + `CPATH`（无 sudo 已破解，属已验证坑） |
| NIM / vLLM / NeMo | 契约/清单在仓 | **NIM 容器路线已关闭**（docker 无权限）；vLLM **0.22–0.29 有 cp38-abi3 aarch64 wheel**（清华源，Py3.12 可用）；NeMo Guardrails 0.24.1 / aiqtoolkit / nemo-toolkit 清华源均有 | 清华源已核 |
| 口播等级 | — | **N1+**：GPU 推理已实证（0.6B）；Nemotron/vLLM 全栈未起 → 不越级口播 N2+ | evidence 为准 |

### E. Conda / Python 环境策略（P0 规范）

| 环境 | 用途 | 规范 |
|------|------|------|
| **本机主干** | pytest / skills / API | `venv` 或系统 Python + `requirements.txt`；引擎用 `_timo_engine` 自带 `.venv` |
| **节点 `uea` conda** | GPU 推理 + 模型服务 | Miniconda 用户级；`python=3.12`；torch cu130；**与系统 pip 隔离** |
| **节点引擎 venv** | Timo :7862 | `/workspace/_timo_engine/.../.venv`；**禁止** `Windows Scripts/python.exe` |
| **禁止** | — | 把节点密码写入环境 yaml 提交；系统级 `pip install` 覆盖 PEP668 无 `--user` |

### F. 模型（**全部经 spark-51 + hf-mirror API 实测 · 2026-09-20**）

| 角色 | 模型（仓库 ID） | 体积/文件 | 实测状态 | 回退链 |
|------|----------------|-----------|----------|--------|
| LLM · FAST | `nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16` | 8.0GB / 18f | **200 可下载** | Qwen3-0.6B（节点已有） |
| LLM · REASON | `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4` | 21.6GB / 70f | **200 可下载**（NVFP4 = Blackwell 原生 FP4） | Nano-4B 兼 REASON（档位写清） |
| 多模态 · VISION | `nvidia/Nemotron-3-Nano-Omni-30B-A3B-Reasoning-NVFP4` | 22.4GB / 26f | **200 可下载**（any-to-any，256K ctx，文本/图/音/视频输入） | Omni-BF16 66.1GB（同 200，资源允许再上） |
| ASR | `nvidia/nemotron-3.5-asr-streaming-0.6b` | 5.7GB / 22f | **200 可下载**（流式） | Omni 音频 → Qwen3-ASR-0.6B → FunASR |
| EMBED | `nvidia/Nemotron-3-Embed-1B-BF16` | 2.3GB / 15f | **200 可下载**（sentence-transformers + vllm tag，多语含中文） | 现配置 bge-m3(:1278) → HashEmbedder 显式降级 |
| OCR | MinerU（pip 装，清华源）+ 可选 `page-elements-v3` | ~2GB | pip 路线可用（docker 版已废） | RapidOCR |
| Guardrails | NeMo Guardrails + builtin | — | 清华源 0.24.1 可装 | builtin 默认强制 |
| DETERMINISTIC | Timo `calc_quote` + ConflictChecker | — | 引擎不变（铁律①） | 离线 byte-identical |

**否决记录（v2.0 关键变更，禁止回流）**：

| 否决项 | 实测依据 |
|--------|----------|
| Lightning **GGUF**（原 v1/v2 选型主 REASON） | unsloth 仓库 501GB 是全量化档堆叠；单文件 Q4_K_M=25.27GB > NVFP4 21.6GB；GGUF 在 vLLM/Blackwell 上无 FP4 tensor core 路径，llama.cpp 路线本节点未验证 → 主链改 **NVFP4** |
| Lightning **NVFP4-DSpark** | 仅 6 文件，`model.safetensors` 单文件 1.35GB，装不下 30B-A3B 的 NVFP4（应 ~16–21GB）→ 疑为激活参数 delta 包，非自包含部署 |
| **nv-embedqa-e5-v5** 作 EMBED 首选 | NIM 容器路线已关闭（docker 无权限），进程级无官方权重证据；换 **Nemotron-3-Embed-1B-BF16**（同 NVIDIA 家族、已验证可下、带 vllm tag） |
| Parakeet 主 ASR 叙事 | Blackwell/compute 12.0 自托管约束（NVIDIA-MAPPING 已核）→ 改 nemotron-3.5-asr-streaming-0.6b + FunASR 回退 |

**下载账**：权重合计 **~60GB**（+MinerU ~2GB）@1.25MB/s ≈ **13.3h（按 14h 保守）** → 分两批 tmux 过夜：批次① always-on 栈（4B 8.0 + Embed 2.3 + ASR 5.7 = **16GB ≈ 3.6h，按 4h 保守**）先行；批次② Omni 22.4 + Lightning 21.6（**44GB ≈ 9.8h**）随后。远端目录一律 `timo_` 前缀（并发会话覆盖风险）。驻留策略：Timo + 4B + Embed + ASR 常驻（~30GB），Omni/Lightning 按需拉起，峰值仍在 121GB 内。

### G. 硬件/性能测评（必须落 evidence 的指标）

| 指标 | 采集命令 | 用途 |
|------|----------|------|
| GPU 名/CUDA/利用率 | `nvidia-smi` | 平台证明 |
| 显存/统一内存峰值 | `nvidia-smi` / `free -h` | 驻留策略 |
| CPU tok/s（LLM） | 节点推理脚本日志 | 基线对比 |
| GPU tok/s（LLM） | 同 prompt GPU 日志 | L2 证明 |
| Nemotron 4B GPU tok/s | vLLM 起服后同 prompt 复测（**目标 ≥30，未测**） | FAST 档可用性 |
| Omni 多模态时延 | 图纸/语音样本 TTFT + 生成（未测） | VISION 档可用性 |
| vLLM × sm_121 探针 | `nemotron_h` 架构 + NVFP4 量化能否 serve（未测） | P2 一号风险 |
| Embedding 延迟 | gateway `/v1/embeddings` RTT | RAG 可用性 |
| 黄金链端到端 | `run_golden_core` / demo 日志 | 业务可用性 |
| pytest | `pytest tests/ -q` | 完整性 |
| 报价一致性 | local vs spark `sha256(unit_price)` | 行为等价 |

---

## 1.3 Agent 建立 → 部署 → 测试 → Skill → 评估（链路图）

```
[建立] bootstrap.py + config(agent/skills/settings/models)
          → CATController + SkillDispatcher + Guardrails
[部署]  Profile A 本机离线/demo
        Profile B DGX Spark :8888 + 模型面 :9000 + Timo :7862
[测试]  pytest 701 · golden 3/3 · e2e L3 · export leaks0
        + 节点 health · GPU 门禁 · nim/gateway smoke
[Skill] 33 目录随仓安装（非官方 npx 全量）
        + negative trigger 文段 + 负向 pytest + allowlist
[评估]  evaluation/metrics.py: task_completion / field_accuracy
        ab_report / ablation_report
        + 商业：报价可审计、HITL 率、HITL vs PASS 质量
[证据]  docs/evidence/**  口播等级 N0–N5 / L0–L5 不越级
```

---

# 第二部分 · 给谁用 · 怎么用 · 用户好不好用

## 2.1 用户画像（谁用）

| 角色 | 诉求 | 主要界面/入口 | 成功标准 |
|------|------|---------------|----------|
| **外贸业务员** | 快速报价、少漏单、少背锅 | Workbench Inbox / Chat / 邮件自动进入 | 5 分钟内看到可解释报价草稿 |
| **报价/工艺主管** | 审核冲突与利润底线 | HITL 审批面板 / DFM 报告 / 审计链 | 一眼看懂为何 BLOCKED/HITL |
| **工厂老板** | 决策留痕、复盘、知识沉淀 | postmortem / 客户健康 / 飞轮报告 | 成交/丢单可追溯 |
| **IT/平台** | 本地部署、权限、模型可换 | settings/models/egress/openshell | 换模型不改架构 |
| **评委** | 是否真 Agent、真行业、真 NVIDIA | Demo + evidence + 答辩 | 5 分钟讲清价值与铁律 |
| **开发者（开源）** | 可复现、可二次开发 | README + skills + tests | 一键 demo + pytest |

## 2.2 怎么用（标准作业流）

### 业务员日常

1. 邮件/文件进入：Gmail/QQ IMAP 或手动上传（STEP/PDF/Excel/语音）  
2. 系统抽取 RFQ → 选 Skill（parse-rfq / extract-specs / step-analysis…）  
3. Timo 引擎算价 + DFM → 验证门禁  
4. **PASS**：自动进审批策略/草稿；**HITL**：主管点批准；**BLOCKED**：禁止外发+原因  
5. `reply-draft` 英文草稿 → 人工确认后发送（默认 draft_only）  
6. 审计链可回放每一步工具与证据  

### 主管审核

- 打开对应 `context_id` → 看黄金链步骤、冲突矩阵、价格来源（引擎/锚点）  
- 批准/驳回 → 状态机推进 → 通知  

### 评委 Demo（Spark）

1. **主 UI 入口（2026-09-20 指定）**：`http://203.0.113.10:8051/`（节点 `:8888` workbench 公网映射，token 门控）  
   ⚠️ 实证状态（2026-09-20 11:09 UTC+8 探活）：该 URL 返回 **HTTP 401 `{"error":"unauthorized"}`**，服务端 `BaseHTTP/0.6 Python/3.12.3`（裸 Python 服务，**非本仓 FastAPI workbench**）——即当前占着 :8888 的不是 livekernel。  
   上台前必须：① 节点 tmux 起 `python3 scripts/start_api.py --port 8888 --host 0.0.0.0`（workbench 本体）；② 确认 8051 令牌门对评委放行（或改用 `ssh -L` 隧道）；③ 复探 `curl -s -o /dev/null -w "%{http_code}" http://203.0.113.10:8051/` 出 200 + 页面标题为 Workbench。  
2. 跑黄金链 PASS/HITL/BLOCKED + 一条 **negative（不触发报价）**  
3. 展示 `nvidia-smi` + `/v1/models` + 报价 sha256 等价  
4. 打开 Skill Console：为何触发 calc-quote、为何不触发  

### 开源开发者

```bash
python scripts/run_demo.py --offline
python -m pytest tests/ -q
python scripts/export_demo.py
```

## 2.3 「用户好」体验原则（可验收）

| 原则 | 落点 | 验收 |
|------|------|------|
| **5 分钟可见价值** | 一键启动 + 黄金链 demo | 新用户无需读完整 PRD |
| **数字可解释** | UI 显示 unit_price 来源=引擎/锚点/批注 | 禁止只甩一个总价 |
| **失败可理解** | BLOCKED/HITL 给原因与下一步 | 演示脚本含三态 |
| **不吓到用户** | 默认不外发、可撤销、本地数据 | egress DENY 可展示 |
| **技能可预期** | Skill Console 显示触发/negative | 负向用例可演示 |
| **模型可换不改心智** | 模型设置页 + 状态探活 | 切 endpoint 不重装业务 |
| **移动端/简模** | 非 P0；Web 可读即可 | 不阻塞赛期 |

---

# 第三部分 · 行业问题（解决什么）

## 3.1 问题陈述

CNC/精密制造外贸报价长期依赖**老师傅经验**：

| 痛点 | 后果 |
|------|------|
| 报价慢 | 询盘响应输给同行，丢单 |
| 报价黑盒 | 低了亏本、高了丢单，过程不可审计 |
| 工艺冲突靠人盯 | 材料×表面处理×公差禁忌漏检 → 批废/索赔 |
| 历史价用不上 | 报价员离职知识流失 |
| 人机协作不清 | 全自动乱报、全自动又不敢上线 |

## 3.2 本方案怎么解（可验证）

| 问题 | 机制 | 可验证点 |
|------|------|----------|
| 黑盒报价 | **LLM 提议，引擎裁决** + 审计链 | sha256(unit_price) 可对账 |
| 工艺漏检 | DFM 冲突 Skill + BLOCKED | 黄金链 S-BLOCKED 场景 |
| 响应慢 | 黄金链自动化 + 批量 BOM | 410/410 批量实证（历史） |
| 知识流失 | RAG 分层 + postmortem 飞轮 | 检索到相似工况锚点 |
| 不敢全自动 | HITL + draft_only + egress 闸 | 默认不自动外发 |
| 平台可信 | NVIDIA 本地 Runtime + 本地算力 | Spark GPU/NIM evidence |

## 3.3 不做什么（边界）

- 不宣称全自动替代报价员签字权  
- 不宣称飞轮矫正已提高 MAPE（仓内结论为负向，proposal-only）  
- 不用客户邮箱真实凭据进演示  
- 不把 LLM 生成数字当成卖点  

---

# 第四部分 · 可行 PRD · 从 P0 开始（执行规格）

## 4.0 目标与非目标

**目标**：在截止前完成「**证据闭环的可提交 Agent**」——本地完整 + Spark 平台实证 + Skills 可验证 + 交付报告 + 十日谈。  
**非目标**：重写架构；全量官方 NVIDIA/skills；生产 SaaS 上线；赛期调 MAPE。

## 4.1 P0 地基（必须先做）

| ID | 任务 | 产出 | DoD |
|----|------|------|-----|
| P0-1 | **设备/环境档案** | `docs/ENV-INVENTORY.md` | 本机+节点硬件/软件/驱动/conda/端口表填完 |
| P0-2 | **密钥清污** | 密码移出 `Timo-SSH*.md`、`deploy/*spark*.py` 等交付面 | 仓内交付路径无明文节点密码 |
| P0-3 | **本机基线复跑** | pytest/golden/export 日志贴 evidence | ✅ **已完成（2026-09-20 晚）**：断言改为四服务 GPU 预留校验，全量 **725 passed / 0 failed**（7m10s） |
| P0-4 | **版本策略** | pin 决策记录 | README/CHANGELOG/MANIFEST 口径一致 |
| P0-5 | **evidence 骨架** | `docs/evidence/**` 按既有 README | 目录+说明就位 |
| P0-6 | **节点门禁** | `00-gates.txt` | docker/cuda/ngc/vllm/nemo 结果 |

## 4.2 P1 平台（Spark 主体）

| ID | 任务 | DoD |
|----|------|-----|
| P1-1 | 引擎 Linux 路径 + Timo venv | `:7862` health 或离线 golden 标注 |
| P1-2 | livekernel 同步节点 + settings.dgx-spark | 路径无 Windows 盘符 |
| P1-3 | API/Workbench `0.0.0.0:8888` + token | 公网 8051 或隧道可访问 |
| P1-4 | tmux 托管 | 进程存活 |
| P1-5 | 节点黄金链日志 | `evidence/spark/03-demo-run.log` |

## 4.3 P2 NVIDIA 模型栈（v2.0 · vLLM 进程级；NIM 容器路线已废）

| ID | 任务 | DoD |
|----|------|-----|
| P2-1 | 环境：清华源装 vLLM（0.22–0.29 cp38-abi3 aarch64 wheel，Py3.12 可用），复用已装 torch 2.14.0+cu130 | `import vllm` 绿 + 版本入 evidence |
| P2-2 | 下载批次①：4B-BF16 + Embed-1B + ASR-0.6b（16GB；tmux 过夜；hf-mirror；`timo_` 前缀） | `du -sh` + sha 校验日志 |
| P2-3 | **一号探针**：vLLM serve Nano-4B-BF16 on sm_(12,1)，chat 一次成功 | `/v1/models` 真 id + tok/s |
| P2-4 | Embed-1B `/v1/embeddings` + RAG 回归（替换 bge-m3 必须出 diff） | 检索冒烟 + `09-models-yaml-diff.md` |
| P2-5 | ASR-streaming-0.6b serving 探针（vLLM 或 transformers，流式） | 一次转写日志 |
| P2-6 | 下载批次②：Omni-NVFP4 + Lightning-NVFP4（44GB）；Omni `trust_remote_code`（custom_code tag）探活 | 两模型 `/v1/models` + latency |
| P2-7 | Model Gateway `:9000` 汇总多模型 `/v1` + 鉴权；Timo `:7862` 常驻 | curl 200 ×N |
| P2-8 | Guardrails：nemo_soft（pip 清华 0.24.1）或 builtin 证明 | 用例日志 |
| P2-9 | models.yaml / router 切换 diff（每角色一次真切换） | diff 落盘 |
| P2-10 | **铁律①回归（每次模型栈切换后必跑）**：价格 sha256 行为等价测试 | `python -m pytest tests/test_price_sha256_regression.py -q` **13 项全绿** + 日志入 evidence |

## 4.4 P3 Skills 与评估

| ID | 任务 | DoD |
|----|------|-----|
| P3-1 | 核心 8 skill negative trigger 文段 | SKILL.md + 矩阵 md |
| P3-2 | 负向 pytest | 绿或如实红灯清单 |
| P3-3 | A/B with/without skills | `ab-report-*.json` + 一句话解读 |
| P3-4 | local vs spark 价格 sha256 | 等价 json |
| P3-5 | 技能安装说明（业务 33 随仓） | INSTALL-SKILLS.md |
| P3-6 | 评估报告段落 | 指标表+命令复现 |

## 4.4b 邮件驱动 × Skill 化 × 控制台标记（方案 D · 2026-09-20 晚批准）

**背景**：user 拍板「所有功能 skill 化进主 OpenClaw + 邮件驱动 + V6 保留做控制台但必须标记来源」。四方案评审收敛于**方案 D**（79/100，"实证陡坡"胜出：站在实证优先的 C 上，补其漏掉的 email-as-ID bug，把 Wiki 从全否降格为 T3 编译索引），5 个决策点全按推荐拍板。口述方案中两处计数有误，以本节实测为准。

**计数勘误（2026-09-20 实测；口述版 35/20 作废）**：

| 层 | 实测 | 证据 |
|----|------|------|
| skills/ 文件夹 | **33**（33 SKILL.md + 33 tool.py；`__pycache__` 不计） | `ls skills/*/SKILL.md \| wc -l` |
| skills.yaml 注册 ID | **19**（14 按名映射文件夹 + ceo-decision-cb-bridge/reid-os-bridge 两桥接 + 3 个纯 pack 桥无文件夹） | yaml.safe_load 解析 |
| Dispatcher LLM catalog | **10**（硬编码） | skill_dispatcher.py:82-86 |
| 零注册文件夹 | **17**：cnc-quote / customer-flywheel / customer-health / dfm-conflict / dfm-expert / fleet-coordinator / freight-customs / material-expert / orchestrator / price-expert / quality-loop / quote-calibration / reply-draft / retention-alert / rfq-extraction / step-analysis / verification | 集合差 |

**5 拍板**：① driver+actor 双轴（driver 答"谁触发"，actor 答"谁执行"）② agent 自主任务进同一 pending.jsonl ledger（控制台一个视图）③ seed 翻转 email-first（只影响新客户；显式 customer_id 优先逻辑不变，老数据不动）④ Wiki v2 先材料+表面处理两域试点 ⑤ P0 先行、P1 紧跟（P1 的 driver 落点依赖 P0 字段）。

**回复策略定论（三层检索，LMVK 否决）**：T1 确定性事实（Timo 报价/DFM + CRM SQL 画像直查，不嵌入）＋ T2 客户历史 RAG（email 为 ID，复用 L2 点 id `{customer_id}:{context_id}`）＋ T3 全局知识 Wiki v2 编译索引（index.md 符号表做术语归一，补向量检索跨语言弱点；log.md 构建日志保可回放）；LLM 仅措辞不定价（planner.draft_reply 现有 guard 门，cat_controller.py:442-467）。LMVK 否决理由：无可审计性、context 成本不可控、与"LLM 不生成最终价格"铁律冲突、现场离线即趴窝。

| ID | 任务 | DoD |
|----|------|-----|
| D-0（P0） | driver 标记全链透传：mail_puller `PendingEntry`＋`from_dict` / mail_orchestrator `OrchestratorResult`＋`run_pipeline`＋`_audit` / skill_dispatcher `dispatch()`＋`_write_audit` / cat_controller `run()`＋audit＋return / mailbox_api inbox 合并 pending 状态 / webui 徽标 | **✅ 完成（2026-09-20）**：旧数据缺字段默认 email 向后兼容；email/console/agent 三入口各打标（`/v1/agent/task` 新增 driver 校验四值域）；audit 落字段（context_created payload.driver 进哈希链）；`pending_index()` 供 inbox 合并；webui 收件箱 state+driver 徽标；修 production bug：`cat.run()` 早期无 driver 参数被 MockCAT `**kwargs` 掩盖，真控制器回归测试钉死；全量回归 **739 passed 0 failed**（新增 14 条：puller 3 / orchestrator 3 / dispatcher 5 / inbox 1 / golden 2） |
| D-1（P1） | email-as-ID：crm_memory.py:142 seed 翻转 email 优先＋新增 `customer_id_by_email` | 同邮不同名→同 ID；同名不同邮→不同 ID；老数据不动 |
| D-2（P2） | Dispatcher catalog 从硬编码改 skills.yaml summary 动态生成；`_RULE_ROUTES` 补 flywheel/health/retention/batch 路由；17 个零注册文件夹补注册 | 每条新路由单测；catalog 动态性测试 |
| D-3（P3） | Wiki v2 编译器 `services/knowledge_compile.py` → index.md 符号表＋chunks＋log.md，材料+表面两域试点 | 同义词归一（6061-T6≡AL6061）；构建日志可回放；离线可用 |

## 4.5 P4 演示与用户体验验收

| ID | 任务 | DoD |
|----|------|-----|
| P4-1 | 5 分钟 Demo 脚本（业务员路径） | `DEMO-5MIN.md` |
| P4-2 | 评委路径（Spark+negative+sha256） | `DEMO-JUDGE.md` |
| P4-3 | 截图/录屏 | 脱敏帧或 mp4 |
| P4-4 | UX 验收清单 | §2.3 勾选 |

## 4.6 P5 交付报告 + 十日谈 + 提交包

| ID | 任务 | DoD |
|----|------|-----|
| P5-1 | **交付报告** 按 §5 目录写满 | `docs/DELIVERY-REPORT.md` |
| P5-2 | **十日谈** 按 §6 从日志生长 | `docs/十日谈.md` |
| P5-3 | 开源包 export + 脱敏扫描 | leaks 0 |
| P5-4 | 答辩口径 N 级不越级 | `DEFENSE.md` |
| P5-5 | 最终 checklist | 全勾或挂账诚实 |

## 4.7 里程碑依赖（简化甘特）

```
P0 环境档案/清污/基线 ─┬─ P1 Spark Agent 立起 ─ P2 NVIDIA 模型 ─ P3 Skills/AB ─ P4 演示 ─ P5 报告/十日谈
                       └─（并行）negative 文档 / 交付报告骨架 / 十日谈框架
```

## 4.8 验收门禁（提交前）

- [ ] `ENV-INVENTORY.md` 完整  
- [ ] 无明文节点密码/NGC key/邮箱授权进交付包 → 只读核查报告 `docs/evidence/secret-scan-2026-09-20.md`（git 历史已验干净；5 个 deploy 脚本含 spark-51 口令明文待轮换+改环境变量；真实 QQ 邮件/credentials 打包排除；打包只用 `git archive`）  
- [ ] 本机 pytest + golden + export 有日志  
- [ ] 节点 `nvidia-smi` + 至少一条模型或引擎 health  
- [ ] Workbench 8888 可达（或诚实写未达）  
- [ ] negative + A/B 至少骨架+一份 JSON  
- [ ] 价格 sha256 等价有记录 → **`python -m pytest tests/test_price_sha256_regression.py -q` 13 项全绿**（铁律①行为等价：DETERMINISTIC 任意 backend 均路由 timo-kernel 不走 LLM；同一 RFQ 价格 sha256 跨 local/nvidia/mock 一致；LLM 篡改价格可被 sha256 检测；DETERMINISTIC 不受 A/B 路由影响；Timo 离线显式标注不冒充）；日志贴 evidence  
- [ ] DELIVERY-REPORT + 十日谈初稿可读  
- [ ] 口播等级与 evidence 一致  

---

# 第五部分 · 最终交付报告框架（目录即模板）

**路径**：`docs/DELIVERY-REPORT.md`（P5 填写）

```
0. 执行摘要（500字：问题/方案/证据/边界）
1. 赛题对齐（Agent Skills + DGX Spark + 行业）
2. 产品是什么（架构一页 + 黄金链）
3. 环境与平台
   3.1 本机设备/软件
   3.2 Spark 节点设备/驱动/CUDA
   3.3 conda/venv/引擎布局
   3.4 模型栈与门禁结果
   3.5 硬件测评表（tok/s、显存、端到端时延）
4. Agent 建立与部署
   4.1 bootstrap/config 契约
   4.2 Profile A/B 启动步骤
   4.3 端口/安全/token
5. 测试
   5.1 单测/回归（命令+数字）
   5.2 黄金链/E2E
   5.3 节点实跑
   5.4 导出包自检
6. Skills
   6.1 安装方式（随仓33；官方NVIDIA/skills策略）
   6.2 注册与 allowlist
   6.3 negative trigger 矩阵
   6.4 负向测试结果
7. 评估
   7.1 技术指标（completion/accuracy/latency）
   7.2 A/B 与消融
   7.3 业务指标（可审计性、HITL、批量）
   7.4 NVIDIA 口播等级 N0–N5
8. 用户与行业价值（§2/§3 压缩）
9. 风险与挂账（诚实缺口）
10. 复现手册（命令列表）
11. 附件索引（evidence 路径列表）
```

---

# 第六部分 · 十日谈框架（根据日志写，不空想）

**路径**：`docs/十日谈.md`  
**原则**：每日 = **日志/命令/数字/挫折/决策/行业含义**；有则写满，无则写「未发生」，禁止虚构 Spark 成功。

## 6.1 可用日志源（遍历已定位）

| 源 | 内容 | 十日谈用途 |
|----|------|------------|
| `Timo-SSH推理报告.md` | SSH 成功、GB10、CPU 13.1 tok/s、GPU 阻断 | 节点接入日 |
| **2026-09-20 节点 hf-mirror API 探针**（`/tmp/timo_probe2/3/4.py`，结果已抄录 §1.2-F） | 五个仓库 200 实测 + DSpark/GGUF/nv-embedqa 否决全过程 | **第八谈核心证据** |
| **2026-09-20 节点自检** | 驱动 580.82.09 / CUDA 13.0 / sm_(12,1) / 121GB / docker 无权限 / 端口占用 | 第七谈 |
| `services/api_server.py:88` + README v6.2 段 + MANIFEST v3.0.1 | 版本标记三处分裂实证 | 第十谈挂账 |
| `CHANGELOG.md` | v3→v6.2 功能演进、701 测试 | 产品成熟叙事 |
| `docs/ACCEPTANCE-REPORT-v7.md` | 验收命令、数字、挂账 | 工程诚实日 |
| `docs/SER-清单.md` | R-01~R-14 / E-01~E-14 | 需求闭环日 |
| `docs/AUDIT-REPORT-v7.md` `PRIOR-ART-v7.md` | 审计与先例 | 研究日 |
| `docs/evidence/**`（待填） | 节点/GPU/A-B | 实证日 |
| git log（`741cb64` 等） | 版本节点 | 里程碑日 |
| `data/golden_core/` `docs/e2e_l3/` | 演示痕迹 | Demo 日 |

## 6.2 十日结构（模板 · 日号可按真实赛期重排）

| 谈 | 主题 | 日志证据钩子 | 行业句 |
|----|------|--------------|--------|
| **第一谈 · 缘起** | 老师傅报价黑盒与丢单 | 立项/PRD-frozen/赛题转写 | 不解决慢与黑盒，数字化只是摆设 |
| **第二谈 · 铁律** | LLM 提议、引擎裁决 | iron-rule / timo_adapter / calc-quote SKILL | 商业信任来自可复核数字 |
| **第三谈 · 黄金链** | 询盘→报价→门禁→草稿 | cat_controller / run_golden_core 3/3 | 流程即竞争力 |
| **第四谈 · 技能化** | 33 Skills + dispatcher | skills glob / test_e2_skills / SER E-07 | 能力资产化才能复用 |
| **第五谈 · 数据与工厂** | 杰沃 PO/BOM/批量 | SER R-04~06 数字 | 没有行业数据就没有行业智能 |
| **第六谈 · 治理** | HITL/egress/审计/openshell | guardrails / egress_gate / audit | 能自动≠敢自动 |
| **第七谈 · 节点与硬件** | Spark GB10 接入与 GPU 阻断 | Timo-SSH 推理报告 | 算力在本地，数据在车间 |
| **第八谈 · NVIDIA 全栈** | 驱动/CUDA/模型选型/门禁 | MODEL-SELECTION / PLAN-nvidia / gates | Runtime 可替换，真相不可替换 |
| **第九谈 · 验证** | pytest/导出/A-B/negative | ACCEPTANCE / evidence | 可验证才有商业价值 |
| **第十谈 · 交付与未竟** | 交付包、挂账、下一季 | DELIVERY-REPORT §9 / SER 缺口 | 诚实的未完成比虚假的完成更专业 |

## 6.3 每谈写作规格（1–2 页）

1. **开篇一句**（行业洞察）  
2. **当日命令/日志摘录**（可复制）  
3. **发生了什么**（事实）  
4. **卡住什么 / 如何绕开**  
5. **决策与代价**  
6. **对用户的含义**  
7. **明日/后续**  

## 6.4 与评分关系

- 十日谈 = **过程真实性 + 行业思考深度**  
- 必须与 evidence **交叉引用**；无日志的一谈标 `PENDING-EVIDENCE`  

---

# 第七部分 · 执行顺序（审核通过后）

| 批次 | 内容 | 产出 |
|------|------|------|
| **W0** | 你审核本 PRD；批注范围/截止/十日谈日号 | 确认记录 |
| **W1** | P0-1~P0-6 | ENV-INVENTORY + 清污 + 基线日志 |
| **W2** | P1 Spark Agent | 8888 + golden on node |
| **W3** | P2 NVIDIA 模型 | gates + gateway + embed/llm |
| **W4** | P3 Skills/AB + P4 Demo | 证据与脚本 |
| **W5** | P5 交付报告 + 十日谈 + 提交包 | 终包 |

---

# 第八部分 · 风险与挂账（写入交付报告 §9 的种子）

| 风险 | 等级 | 处置 |
|------|------|------|
| 明文密码在仓 | 高 | P0 立即 |
| GPU/头文件未解 | 高 | 等级如实 N0–N1 |
| Nemotron 权重不可得 | 中 | 回退矩阵已定义 |
| 工作树未提交/版本裂 | 高 | P0 pin |
| A/B 无差异 | 中 | 加误触发/拦截指标 |
| 十日谈缺日志 | 中 | PENDING 标记，不编造 |
| 邮箱数据进包 | 高 | export 扫描 |

---

# 第九部分 · 审核清单（请你逐条批）

| # | 审核项 | 同意 | 修改意见 |
|---|--------|------|----------|
| 1 | 提交主体仅 livekernel；**本文为唯一主 PRD**，其余 7 份同题文档打「已取代」标 | □ | |
| 2 | 模型栈按 §1.2-F 实测表执行：NVFP4 主链（GGUF 否决）、Embed 换 Nemotron-3-Embed-1B（nv-embedqa 否决）、ASR 专档 0.6b | □ | |
| 3 | 下载分批：**今晚 tmux 起批次① 16GB（≈4h）**，批次② 44GB（≈10h）随后 | □ | |
| 4 | P0 从环境档案 + 密钥清污 + 基线复跑开始（canonical `pytest tests/ -q`） | □ | |
| 5 | Spark 端口策略 8888/9000 + token；9000 起服前探活（曾被并发占用） | □ | |
| 6 | 交付报告目录（第五部分） | □ | |
| 7 | 十日谈十谈结构（第六部分）；无日志的谈标 PENDING-EVIDENCE | □ | |
| 8 | 截止日期：________ | □ | |
| 9 | 视频/十日谈是否必交：□必交 □加分 □不做 | □ | |
| 10 | 官方 NVIDIA/skills：仅参考不全量上节点 | □ | |
| 11 | 批准进入 W1 执行 | □ | |

---

## 一句话 PRD

> **在 NVIDIA GB10 上用可验证的模型 Runtime，跑一个「LLM 提议、引擎裁决」的制造业 Agent：33 Skills 管能力，HITL 管风险，证据包管诚实，十日谈管故事——交付给评委、工厂与开发者三类读者都能五分钟读懂、五分钟复现的产品。**

---

**请审核第九部分清单。** 回复例如：「1–6、9、10 通过；截止 9/30；十日谈必交」或指出需改条款。通过后我立即开工 **W1 / P0**。
