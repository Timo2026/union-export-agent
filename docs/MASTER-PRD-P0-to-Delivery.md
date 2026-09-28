# MASTER PRD · 从硅片到生意 · 端到端作战总图

> **已取代（2026-09-20）**：唯一主 PRD 为 `docs/PRD-MASTER-UEA-DELIVERY.md` **v2.0**（含节点实测模型栈）。本文保留仅供溯源，冲突处以后者为准。

| 字段 | 内容 |
|------|------|
| 版本 | v1.0-master |
| 日期 | 2026-09-20 |
| 定位 | **唯一作战总图**：把项目里散落的 30+ 份 PRD/报告/计划，收敛成一张从基建到交付的执行表 |
| 基线 | 诚实口径来自 `PROJECT-SUMMARY-v6.0.0.md` 实测（综合 6.0-6.5，非声称 8.5） |
| 原则 | 不重复造轮子；每层只写「现状/缺口/P0 动作/验收/证据指针」 |
| 密级 | 公开 |

---

## 0. 一句话定位

> **把一封制造业询盘邮件，端到端变成一个可审计、可验证、可自动决策的商业对象；LLM 提议，确定性引擎裁决，DGX Spark 提供本地算力，Skills 管窄触发与行业能力。**

评分主线：**行业主叙事（Timo 填垂直空白）× 评委硬证据（Spark 实跑 + Nemotron 全栈 + negative trigger + A/B + 行为等价）= 双轮。**

---

## 1. 现有资产盘点（避免重复造轮子）

项目已有大量成熟资产，本 PRD 的任务是**接线与闭环**，不是从零建。

### 1.1 代码资产（已实证存在）

| 层 | 资产 | 规模 | 健康度 |
|----|------|------|--------|
| 引擎 | `adapters/timo_adapter.py` + `_kernel_bridge.py`（在线 HTTP + 离线 byte-identical） | — | 🟢 双通道齐 |
| Agent | `agents/cat_controller.py`（黄金链 7 步状态机） | 459 行 | 🟢 |
| Skills | 33 个 SKILL.md + tool.py，统一 `run(ctx)` 模板 | 33/33 | 🟢 结构 |
| 路由 | `services/skill_dispatcher.py`（规则+LLM 混合，auto/llm/rules_only） | — | 🟢 |
| 治理 | OpenShell 4 策略 + Guardrails 三段 + Egress Gate | — | 🟢 builtin |
| 评估 | `evaluation/metrics.py`（field_acc/ab_report/ablation/quote_deviation） | — | 🟢 函数在 |
| 部署 | `deploy/` Profile A/B/C/D + nim/docker-compose + Dockerfile + k8s + hpa + grafana | — | 🟢 清单齐 |
| 数据 | `data/artifacts/`（298 eml + 177 step + 94 wav）/ `golden_core/` / `eval_set.json` / `knowledge/` | 840 文件 | 🟢 语料在 |
| 测试 | `tests/` 82 py（515-517 业务绿 / 701 总） | 701 | 🟡 11-13 fail |
| 文档 | `docs/` 30+ md + 58 png | — | 🟢 丰富 |
| Notebooks | 14 个（00 环境自检 → 13 供应商） | 14 | 🟢 |

### 1.2 关键缺口（实测，来自 PROJECT-SUMMARY）

| 缺口 | 证据 | 本 PRD 对应层 |
|------|------|---------------|
| 4 个 P0 BUG（AgentCache deepcopy / 静态资源 / 版本三套 / Schema enum） | `PROJECT-SUMMARY` §4.1 | L7 测试层先行修 |
| Negative trigger 全缺 | 全仓搜索 0 命中 | L5 Skills 层 |
| A/B 无真实产物 | `metrics.ab_report` 无调用产物 | L7 评估层 |
| Windows 路径硬编码 10+ 处 | grep 实证 | L6 部署层 |
| NIM/Nemotron 0 进程实跑 | README 诚实标注 | L3 模型层 |
| `tools/` 6.3GB 未 gitignore | git status 实证 | L6 部署层 |

---

## 2. 八层作战图

每层四栏：**现状 → 缺口 → P0 动作 → 验收 / 证据指针**。

### L1 · 基建层（设备 / 驱动 / conda / CUDA / 硬件测评）

| 现状 | 缺口 | P0 动作 | 验收 / 证据 |
|------|------|---------|------------|
| Spark SSH 已通；GPU 全栈可跑（用户确认） | 无统一自检脚本与硬件测评报告 | 节点跑 `nvidia-smi --query-gpu=name,compute_cap,memory.total,memory.free` + `python3 -V` + `nvidia-smi` 完整 + `nvcc -V` + `df -h` + `free -h` | `docs/evidence/nvidia/00-nvidia-stack-selfcheck.txt`（模板已建） |
| conda/venv 本机有，节点未确认 | 节点引擎 venv 未建 | 节点建 `conda create -n uea python=3.11` 或 venv；`pip install -r requirements.txt` | 节点 `python -c "import fastapi,uvicorn"` 成功 |
| 无硬件测评 | 评委要看"算力是否够" | 跑一次 MoE 30B-A3B 推理 + 一次 4B 推理，记录延迟/token/显存占用 | `docs/evidence/nvidia/01-hardware-benchmark.txt`（含 latency/throughput/vram） |

**P0 命令清单**（节点执行，输出落 `docs/evidence/nvidia/`）：
```bash
nvidia-smi --query-gpu=name,compute_cap,memory.total,memory.free --format=csv > 00-gpu.csv
nvidia-smi > 00-nvidia-smi-full.txt
nvcc -V >> 00-nvidia-smi-full.txt
python3 -V && pip list | grep -iE "fastapi|uvicorn|torch|vllm" >> 00-env.txt
```

---

### L2 · 引擎层（Timo 内核 / 离线兜底 / 跨平台）

| 现状 | 缺口 | P0 动作 | 验收 / 证据 |
|------|------|---------|------------|
| `timo_adapter` 在线 `:7862` + 离线 byte-identical 双通道 | `settings.yaml` 引擎路径硬编码 Windows | 节点 rsync 引擎源码；填 `settings.dgx-spark-p0.yaml` 的 `engine_src`/`engine_python` 为 Linux 路径 | 节点 `curl :7862/api/health` 200 |
| 离线兜底可用 | 节点引擎 venv 未建 | 节点进引擎目录 `python -m venv .venv && pip install -r requirements.txt` | 离线模式 `run_demo.py --offline` 价格与在线 sha256 一致 |
| 熔断器三态 | — | — | 已有 |

**P0**：用户 SSH 上节点后，把引擎源码 rsync 到 `/workspace/_timo_engine/`，建 venv，起 `:7862`。证据 `docs/evidence/spark/01-service-health.txt`。

---

### L3 · 模型层（Nemotron 全栈 / NIM / 行为等价）

| 现状 | 缺口 | P0 动作 | 验收 / 证据 |
|------|------|---------|------------|
| `models.yaml` 全 local/LMStudio；`models.nvidia-fullstack.yaml` 已建 Nemotron 矩阵（端口 TODO） | 0 进程实跑；端口未确认 | 用户报端口表 → 我敲死 TODO → 逐角色冒烟 | 见 `PRD-NVIDIA-FullStack-Swap.md` 执行序 N0-N8 |
| Nemotron-3.5-Lightning-30B-A3B（MoE）+ Nano-4B + Omni（三合一） | 无行为等价证明 | 跑黄金链 local vs Nemotron 两遍，比引擎价格 sha256 | `docs/evidence/nvidia/behavior-parity-local-vs-nvidia.json` |
| `nim_smoke.py` 就绪 | — | `python services/nim_smoke.py --url <port>` | `nim-llm-smoke.txt` 等 |

**铁律**：DETERMINISTIC 角色（Timo）永不平替。换什么后端，价格 sha256 必须不变——这是 NVIDIA 全栈的最强证据。

**最终模型矩阵**（Nemotron 全家族）：

| 角色 | 模型 | 能效 |
|------|------|------|
| REASON | Nemotron-3.5-Lightning-30B-A3B | MoE 30B 总/3B 激活 |
| FAST | Nemotron-3-Nano-4B | 边缘极速 |
| OMNI (VLM+ASR+OCR) | Nemotron-3-Nano-Omni | 三合一，绕开 Parakeet 限制 |
| EMBED | nv-embedqa-e5-v5 | NIM 检索嵌入 |
| DETERMINISTIC | Timo cnc-ai-brain v12 | 锁定不平替 |

---

### L4 · Agent 层（CAT / 黄金链 / 状态机）

| 现状 | 缺口 | P0 动作 | 验收 / 证据 |
|------|------|---------|------------|
| `cat_controller.py` 黄金链 7 步状态机（INTAKE→...→DONE，BLOCKED/HITL 分支） | — | 已闭环，只需在 Spark 上跑通 | `scripts/run_demo.py` 输出 6/6 场景 |
| SHA-256 审计链 (`services/audit.py`) | — | 黄金链跑完 `audit.verify()` 通过 | `data/traces/` 落盘 + verify 绿 |
| LLM Planner opt-in | — | Spark 上接 Nemotron REASON | 引擎裁决优先，LLM 仅提议 |

**黄金链**（演示主路径）：
```
邮件/STEP/语音 → rfq-extraction/rag-ingest → Context
  → calc-quote(Timo 裁决) → dfm-conflict/verify-gate
  → HITL 或 PASS → reply-draft(draft_only) → SHA-256 审计
```

---

### L5 · Skills 层（33 skill / 路由 / negative trigger / A-B）

| 现状 | 缺口 | P0 动作 | 验收 / 证据 |
|------|------|---------|------------|
| 33/33 SKILL.md + tool.py 制式统一 | **negative trigger 全缺**（搜索 0 命中） | 填 `negative-trigger-matrix.md`（已建骨架）核心 8 skill；补 SKILL.md 的 `## Negative triggers` 段 | 矩阵填实 + 8 SKILL.md 补丁 |
| 规则+LLM 混合路由 | 无负向 pytest | 写 `tests/test_neg_*.py`：对无关输入断言目标 skill 未被选中 | pytest 负向绿 |
| A/B 函数在 (`ab_report`) | **无真实 A/B 产物** | 跑 A=完整 skills vs B=去关键 skills；复用 `ab_report` 输出 JSON | `docs/evidence/ab/ab-report-skills-on-off.json` + 一句话解读 |
| eval_set.json 在 | — | A/B 与评估都用它做输入 | — |

**这是得分主粮**——评委"和普通 Skill 包有何不同"靠 negative trigger + A/B 回答。

---

### L6 · 部署层（Profile A-D / Spark 上线 / 端口 / 跨平台）

| 现状 | 缺口 | P0 动作 | 验收 / 证据 |
|------|------|---------|------------|
| `deploy/profiles.yaml` A/B/C/D 齐 | Profile B 仅纸面验证 | 节点起 Profile B：engine `:7862` + api `:8888`（改自 8900）+ health | `docs/evidence/spark/01-service-health.txt` |
| 公网仅放行节点内 `0.0.0.0:8888`/`9000` | 多服务难暴露 | UI/API 绑 `8888`；其余 `ssh -L` 隧道 | `docs/evidence/spark/02-public-or-tunnel.md` |
| 全 `.bat` 锁 Windows | 无 Linux 启动 | 写 `scripts/start_all.sh`（引擎+API+health） | 节点 `bash start_all.sh` 成功 |
| `tools/` 6.3GB 未 gitignore | 误提交风险 | `.gitignore` 加 `tools/`；提交前扫描 | `git status` 无 tools/ |
| 凭据进仓风险 | 资格风险 | 提交前 grep 密码/密钥模式；演示用占位符 | 扫描无命中 |

---

### L7 · 测试评估层（pytest / E2E / 行为等价回归）

| 现状 | 缺口 | P0 动作 | 验收 / 证据 |
|------|------|---------|------------|
| 701 收集 / 515-517 绿 / 11-13 fail | 4 P0 BUG（PROJECT-SUMMARY §4.1） | 先修：AgentCache deepcopy / 静态资源 mount / 版本统一 / Schema enum | pytest 全绿 |
| 旧 UI 测试断言旧路由 | 10 测试红 | `test_mailbox_ui.py`/`test_models_api.py` 路由对齐 | 10 测试转绿 |
| 无行为等价回归 | NVIDIA 切换无证据 | local vs Nemotron 跑黄金链，比价格 sha256 | `behavior-parity-*.json` |
| E2E 在 (`e2e_l3.py`) | Spark 上未跑 | 节点跑一次 E2E 截图 | `docs/e2e_l3/` |

**赛前必须**：`pytest tests/ -q` 全绿（目标 528 passed）。不绿不上线。

---

### L8 · 业务交付层（给谁用 / 怎么用 / UX / 行业问题 / 最终报告 / 十日谈）

#### 给谁用（三类用户）

| 角色 | 痛点 | 系统行为 |
|------|------|---------|
| 外贸业务员 | 报低丢利润、报高丢单；靠老师傅经验 | 收询盘 → 黄金链 → 确定性报价 → 护栏 → HITL/PASS |
| 报价主管 | 过程不可审计、难复盘 | 审计链 + 冲突证据 + 人工批准推进 |
| 工厂老板 | 无法规模化、丢单原因不清 | 复盘 → 记忆回流 → 换数据换「厂格」 |

#### 怎么用（三条入口）

1. **邮件自动驱动**：Gmail IMAP 30s 轮询 → MailOrchestrator → CAT → 通知
2. **上传端口**：`POST /v1/upload/{email,step,audio,pdf,excel,image,auto}` 或 `POST /v1/rfq/intake`
3. **Workbench UI**：三栏（Inbox / Inspector 8 区 / Chat），评委可点

#### 如何让用户好（UX 优化点）

- 黄金链 8 步进度条可视化（UI 已有）
- PASS 自动批准 / HITL+BLOCKED 通知人工（不冷场）
- 离线降级显式标注（诚实）
- 一键启动 + 一键自检（已有）

#### 解决什么行业问题

> CNC/外贸报价依赖老师傅经验：报低丢利润、报高丢单；过程不可审计、难以复盘、无法规模化。
> 本系统把**隐性经验**变成**可审计的确定性决策**——价格由引擎裁决（非 LLM 猜），全过程 SHA-256 留痕，客户/报价双飞轮持续校准。

#### 最终交付报告（提交包）

```
union-export-agent-livekernel/
  README.md                     # 一句话 + Spark 实证入口 + 快速开始
  docs/
    MASTER-PRD-P0-to-Delivery.md  # 本文件（作战总图）
    PRD-NCPAAI-Spark-Submission.md
    PRD-NVIDIA-FullStack-Swap.md
    NCP-AAI-COVERAGE.md
    NVIDIA-MAPPING.md
    DEPLOYMENT.md
    evidence/                   # 全部实证落盘
      spark/ nvidia/ skills/ ab/
    十日谈.md                    # 历程叙事
  skills/                       # 33 + negative trigger
  deploy/nim/                   # Nemotron 编排
  evaluation/                   # metrics + ab 产物
  notebooks/                    # 14 演示
  scripts/run_demo.py e2e_l3.py
```

---

## 3. P0 → 交付 执行序（里程碑）

| 序 | 里程碑 | 依赖 | 证据 |
|----|--------|------|------|
| M0 | 节点自检 + 硬件测评 | SSH 通 | `evidence/nvidia/00*` |
| M1 | 引擎上节点 + Profile B 起服 + health | M0 | `evidence/spark/01*` |
| M2 | UI/API 绑 8888 + 公网/隧道证明 | M1 | `evidence/spark/02*` |
| M3 | Nemotron 全栈冒烟（逐角色）+ 端口敲死 | M1 | `evidence/nvidia/*smoke*` |
| M4 | 黄金链在 Spark 跑通 | M1-M3 | `evidence/spark/03-demo.log` |
| M5 | Negative trigger 矩阵 + 8 SKILL.md 补丁 + 负向 pytest | 可并行 | `evidence/skills/*` |
| M6 | A/B 真实报告 + 行为等价（local vs Nemotron sha256） | M4-M5 | `evidence/ab/*` + `behavior-parity*` |
| M7 | 4 P0 BUG 修复 + pytest 全绿 + 版本 pin + 脱敏扫描 | 独立 | pytest 528 绿 |
| M8 | 最终报告 + 十日谈 + 答辩稿 + 录屏 | M4-M6 | `docs/十日谈.md` + 视频 |

---

## 4. 验收 DoD（Definition of Done）

- [ ] Spark `nvidia-smi` + 硬件测评入证
- [ ] Profile B 在 Spark 起服 + health + 公网/隧道证明
- [ ] Nemotron 全栈 ≥4 角色冒烟 + `models.yaml` diff 入证
- [ ] 行为等价 JSON：引擎价格 sha256 local == nemotron
- [ ] 黄金链在 Spark（或声明的降级路径）跑通
- [ ] Negative trigger 矩阵填实 + 8 SKILL.md 补丁 + 负向 pytest 绿
- [ ] A/B JSON + 一句话连到"可验证商业价值"
- [ ] pytest 全绿（528）+ 版本三处统一 + 无凭据扫描通过
- [ ] 最终报告 + 十日谈 + 答辩口径与证据一致，无夸大

---

## 5. 提交前门禁（硬卡点）

提交主体**只**交 `union-export-agent-livekernel`。下列全绿才宣称"平台分已具备"：

- [ ] 仓库无节点密码 / 登录表 / NGC_API_KEY / 客户敏感数据
- [ ] `tools/` 不进仓；`credentials.json`/`*.env`/mailbox 不进提交包
- [ ] README 版本 == git tag == CHANGELOG
- [ ] 答辩口径与 `evidence/` 一一对应

---

## 6. 一句话 PRD

> **在已连通、GPU 全栈可跑的 DGX Spark 上，把 livekernel 的行业 Agent 用 Nemotron 全栈跑起来，用 negative trigger 与 A/B 证明 Skills 不是装饰，用确定性引擎价格 sha256 跨后端不变证明商业价值可验证——主叙事是 Timo2026 的垂直空白，得分手段是评委看得见的实证。**
