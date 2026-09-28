# PRD · NCP-AAI 黑客松提交方案（Spark 实证版）

| 字段 | 内容 |
|------|------|
| 版本 | v1.0.0-spark-evidence |
| 日期 | 2026-09-20 |
| 提交主体 | `union-export-agent-livekernel`（唯一） |
| 赛题 | Mega DEX 黑客松 · Agent Skills 开发挑战赛（NCP-AAI 语境） |
| 状态 | 已拍板：主叙事保留，得分路径改为 Spark 可核验证据 |
| 密级 | 公开文档；**禁止**写入节点密码 / 登录表 / API Key |

---

## 1. 判断（结论先行）

**战略定案：行业主叙事 × 评委 signals 实证 —— 双轮，不是二选一。**

| 维度 | 定案 |
|------|------|
| 提交主体 | 只交 `union-export-agent-livekernel`；其余 14 目录仅作史料/素材，不参赛 |
| 主叙事 | Timo2026 填补 Omarchy / NVIDIA/skills 未覆盖的空白：**垂直行业中可验证的商业价值**（询盘 → 可审计报价决策） |
| 得分重心 | 商业故事只能建立在 **DGX Spark 实跑 + Skills 窄/negative trigger + with/without Skill A/B + 演示留证** 上 |
| Omarchy / NVIDIA/skills | 作为「系统底座 / 工具链方法」一页带过，**不占主标题** |
| 不做什么 | 不把提交收缩成单个 skill demo；不删 33 skills 叙事；不把无实跑的平台声明写进答辩 |

**触发条件（已满足）**：Spark 一键 SSH 已连通 → 反方「平台 15 分拿不到」的最强论据失效；支持方「垂直商业价值」主叙事可以保留，但必须用 Spark 上的证据兑现「可验证」三字。

---

## 2. 问题与机会

### 2.1 真实问题（行业）

CNC/外贸报价依赖老师傅经验：报低丢利润、报高丢单；过程不可审计、难以复盘、无法规模化。

### 2.2 赛题要求（据 `比赛要求/901b261c6695.txt` 转写）

- 以 **Agent 应用** 为核心，用 **Skills** 扩展专业能力
- 依托 **DGX Spark** 本地算力，做出**完整可运行**的应用
- 深入行业、有**实用价值**
- 技术信号：窄触发、**negative trigger**、A/B 对照、接口兼容≠行为等价、治理/信任、StepFun/NIM 等模型适配

### 2.3 空白定位（叙事层，答辩用一页）

```
Omarchy          → Agent 住在系统里
NVIDIA/skills    → Agent 会用硬件与工具链
Union / Timo2026 → Agent 做成可验证的生意（确定性报价 + 审计链 + HITL）
```

底层原理：**LLM 提议，引擎裁决**。价格/毛利/工艺冲突真相永远在 Timo 确定性内核；NVIDIA 是本地 AI Runtime，不是业务逻辑（见 `docs/NVIDIA-MAPPING.md`）。

---

## 3. 目标与非目标

### 3.1 目标（按评分杠杆）

| 优先级 | 目标 | 对应分值面 | 验收 |
|--------|------|------------|------|
| P0 | livekernel 在 **DGX Spark** 上 Profile B 可运行并留证 | 平台适配 ~15 | 节点内 `nvidia-smi` + 服务 health + 公网/隧道可访问截图或日志 |
| P0 | 至少 **1 个** NVIDIA 推理环节（优先 LLM 或 Embedding）经 NIM/OpenAI-compat 实跑 | 平台适配 | `nim_smoke` 或 `/v1/models` 探活日志 + `models.yaml` 切换记录 |
| P0 | 核心 Skills 补齐 **negative trigger** + 路由负向用例 | Skills ~25 | 每个核心 skill 的 SKILL.md 含「不触发」段；pytest 负向用例绿 |
| P0 | 真实 **A/B**：with Skill vs without Skill（或 LLM 抽取 vs 正则） | Skills + 评测 | 复用 `evaluation/metrics.py:ab_report`，产出 `docs/evidence/ab-report-*.json` |
| P1 | 端到端行业 Demo 在 Spark 上可演示 | 实用性 + Demo ~10 | `run_demo` / 上传端口黄金链 + 录屏或逐步截图 |
| P1 | 版本 pin + 开源脱敏 | 合规/完整 | README/CHANGELOG/三处 release marker 一致；`credentials`/mailbox 不进提交包 |
| P2 | 十日谈/历程、答辩稿、视频成片 | Demo/加分 | 按正式细则是否必交再决定投入 |

### 3.2 非目标

- 不在赛期重写 Agent 架构或合并 14 个历史目录
- 不把 Omarchy 做成第二套可提交产品
- 不宣称「已在 Spark 完成全模型常驻/Parakeet 自托管」（Blackwell 约束见 NVIDIA-MAPPING）
- 不在文档/仓库中粘贴 Timo 登录表、节点密码、NGC_API_KEY
- 不用无证据的「95%+ / 129 PO」当赛时主证据；历史数字仅在「可复现实验后」引用

---

## 4. 用户与场景（Demo 主路径）

| 角色 | 场景 | 系统行为 |
|------|------|----------|
| 外贸业务员 | 收到询盘邮件/语音/图纸 | Intake 抽取 → Skills 路由 → 确定性报价 → 护栏 → HITL/PASS |
| 报价主管 | 审核 BLOCKED/冲突 | 审计链 + 冲突证据 + 人工批准推进状态机 |
| 工厂老板 | 复盘成交/丢单 | postmortem → 记忆回流（换数据换「厂格」） |
| 评委 | 现场验证「是否只会聊天」 | 明确：**禁止 LLM 生成价格**；看 negative trigger 不误触发；看 A/B 数字 |

**黄金链（演示脚本）**：

```
输入(邮件/STEP/语音)
  → rfq-extraction / rag-ingest   [Skills · 窄触发]
  → Context / 状态机
  → calc-quote (Timo :7862 或 byte-identical 离线)  [引擎裁决]
  → dfm-conflict / verification / guardrails
  → HITL 或 PASS
  → reply-draft (draft_only)
  → SHA-256 审计链
```

**Negative demo（必演）**：对无关输入（闲聊/纯天气/与报价无关指令）系统**不得**触发 `calc-quote` 等业务 skill，并留下路由日志。

---

## 5. 评分映射与证据包

| 评分面 | 主张 | 必须存在的证据（缺一则该面降级） |
|--------|------|----------------------------------|
| Agent + Skills 融合 | 33/33 SKILL.md + tool.py，制式统一，OpenShell 治理 | skills 清单、skill_registry、openshell/*.yaml、negative trigger 文段、负向测试 |
| 实用性/行业 | 确定性引擎 + 真实语料路径 + 可审计商业对象 | `adapters/timo_adapter.py` 铁律、golden 样例、审计链 demo、可复现报价 trace |
| 完整性 | API + Workbench + 测试 + 部署清单 | pytest 全量绿（赛前复跑）、run_demo/e2e、deploy/* |
| 平台适配 | DGX Spark Profile B + NIM/OpenAI-compat 配置级切换 | **Spark SSH 会话日志、nvidia-smi、服务 health、公网端口/隧道截图、models.yaml 切换前后对照** |
| Skills 工程深度 | 窄触发 + negative + A/B + 行为等价回归 | SKILL.md 触发/不触发、`ab_report` JSON、换端点回归结论 |
| Demo | 可讲述、可回放、不冷场 | 录屏或分步截图；降级路径（NIM 不可用→local）仍可演示 |
| 开源合规 | MIT，脱敏，版本一致 | 无凭据扫描、git tag 与 README 一致 |

**证据落盘约定**：

```
docs/evidence/
  spark/
    00-env-selfcheck.txt      # nvidia-smi / python / docker / df
    01-service-health.txt     # :7862 :8866 :8900 / NIM /v1/models
    02-public-or-tunnel.md    # 端口映射或 ssh -L 说明（无密码）
    03-demo-run.log
  skills/
    negative-trigger-matrix.md
    negative-pytest.txt
  ab/
    ab-report-skills-on-off.json
    ab-report-llm-vs-regex.json
  nvidia/
    nim-smoke.txt
    models-yaml-diff.md
```

---

## 6. 平台方案（DGX Spark）

### 6.1 官方节点约束（手册已核，执行时遵守）

- 每队 1 台 Spark 云节点；公网跳板统一入口（手册示例 IP `203.0.113.10`）
- 端口规律：节点 `spark-NN` → SSH `60NN`，业务映射 `80NN` / `90NN`
- 对外仅 **节点内 `0.0.0.0:8888`** 与 **`0.0.0.0:9000`** 可被公网映射；其余端口用 `ssh -L` 隧道
- 长任务进 `tmux`；禁止改系统级配置、禁止扫内网、禁止外传账密
- 本队节点号与密码：**仅存本地 `比赛要求/../Timo/登录信息表.xlsx`，不进 git、不进 PRD、不进答辩材料**

### 6.2 服务端口策略（映射到公网或隧道）

| 组件 | 节点内监听 | 对外方式 | 用途 |
|------|------------|----------|------|
| Workbench / 上传 API | `0.0.0.0:8888`（改自默认 8900）或 8888 反代 | 公网 `:80NN` | 评委可点 UI |
| 可选辅助服务 | `0.0.0.0:9000` | 公网 `:90NN` | health/演示附属 |
| Timo 内核 `:7862` | `0.0.0.0:7862`（内网） | `ssh -L 7862:localhost:7862` | 报价引擎，不暴露公网 |
| NIM `:8000`/`:8011` | 按容器映射，避免与占用冲突 | 隧道 | 模型切换实证 |
| funasr 多模态 | 节点内网 | 隧道/内网 | ASR/RAG；资源不够则 P0 显式 MOCK 并标注 |

### 6.3 Profile B（DGX Spark P0）启动序列

对齐 `docs/DEPLOYMENT.md` Profile B，并按 Spark 实际环境调整路径：

```text
1) SSH 登录 → tmux new -s uea
2) 环境自检：nvidia-smi; python3 -V; docker info; df -h; free -h
3) 同步代码与依赖（rsync -avzP；引擎/venv 按节点重建，禁止假设 Windows 路径）
   - 注意：settings.yaml 中 engine_src 为本机 Windows 路径，上节点必须改为 Linux 路径或容器内路径
4) 启动确定性内核（:7862）→ curl /api/health
5) （资源允许）funasr-gui / 本地 OpenAI-compat；否则 mock 显式化
6) 启动 API/Workbench，host=0.0.0.0，port=8888
7) 采集 evidence/spark/*
```

### 6.4 NVIDIA 接入（配置级，禁止重写）

现状：模型调用全 OpenAI-compat（`config/models.yaml`）；`model_router.backend`：`local | nvidia(NIM) | mock`。

| 步骤 | 动作 | 证据 |
|------|------|------|
| N1 | 节点 `nvidia-smi` 确认 GPU/驱动 | 00-env-selfcheck |
| N2 | 优先使用节点预置模型或轻量 NIM/本地推理，避免盲目拉超大镜像 | 磁盘/显存日志 |
| N3 | 将 **Embedding 或 FAST LLM** 其一 endpoint 切到节点推理服务 `/v1` | models.yaml diff |
| N4 | `python services/nim_smoke.py` 或 curl `/v1/models` | nim-smoke.txt |
| N5 | 跑黄金链对比 local vs spark-runtime 一次 | trace/字段一致性说明 |
| N6 | 若 GPU/镜像受限：保持 local 可演示，并在答辩**如实**说「契约/配置已接，现场算力路径为 X」 | NVIDIA-MAPPING 边界 |

**明确不做**：Parakeet 自托管（Blackwell/compute 12.0 约束）；「所有模型常驻」；用 MUSA vLLM 冒充 NIM。

### 6.5 与「可验证商业价值」的绑法

平台分不是贴 logo，而是证明：

> **同一套 Skill 契约与确定性引擎，在 DGX Spark 本地算力上，仍能产出可审计的行业商业对象。**

---

## 7. Skills 工程方案（评分主粮）

### 7.1 现状缺口（已实证）

- 33/33 SKILL.md + tool.py：结构达标
- **negative trigger 几乎全缺**（仅 reply-draft 发送门禁类表述，非路由负向）
- tests 中无「应正确不触发 skill」用例
- `evaluation/metrics.py` 的 `ab_report` / `ablation_report` 已存在，**无真实实验产物**

### 7.2 必做交付

1. **《Negative Trigger 矩阵》**（`docs/evidence/skills/negative-trigger-matrix.md`）  
   对核心技能（建议首批）：`calc-quote` `dfm-conflict` `rfq-extraction` `reply-draft` `verify-gate` `rag-ingest` `orchestrator` `ceo-decision`  
   每条 skill 写清：何时触发 / **何时禁止触发** / 误触发后果 / 对应负向测试。

2. **SKILL.md 制式补丁**（至少核心 8 个，力争全量 33）  
   Frontmatter 或正文增加：

   ```markdown
   ## Triggers
   - （正向）…
   ## Negative triggers（不触发）
   - 与报价/DFM/审计无关的闲聊、翻译闲谈、纯代码问答
   - 用户明确要求「编一个价格」而无引擎输入
   - …
   ```

3. **负向 pytest**  
   路由层对 negative 样例断言：目标 skill 未被选中，或被选中但被 guardrails/allowlist 拒绝。

4. **A/B 真实实验（不得只留单测）**  
   - A：完整 skills + 引擎  
   - B：去掉关键 skills（或仅正则抽取）  
   - 调用 `ab_report` / `ablation_report`，输出 JSON + 一页解读（字段准确率、任务完成率、HITL/BLOCKED 率、时延）  
   - 至少 1 组在 **Spark 环境**跑；本机可先跑通流水线

5. **行为等价**  
   同一黄金样例：local runtime vs Spark/NIM 端点各跑一次，比较结构化字段与**引擎价格 sha256**（价格必须一致；LLM 字段允许统计差异并写明）。

---

## 8. 治理与合规（OpenShell）

保留并演示四件套：`iron-rule-1`（LLM 不生成价格）、`hitl-required`、`local-only`/egress 默认 DENY、`skill-allowlist`。

| 规则 | 赛时口径 |
|------|----------|
| 铁律① | unit_price/final_price 与 Timo 返回 sha256 一致 |
| HITL | BLOCKED 永不自动外发；PASS 亦 draft_only |
| data-stays-local | 客户文件/图纸/语音默认不出节点；egress allow-list |
| 凭据 | 登录表/xlsx/`.env` 密钥仅本地；提交包与演示录屏打码 |

---

## 9. 里程碑与执行顺序

> 你已确认 Spark SSH 连通。下列顺序按「先闭环平台证据，再填 Skills 硬缺口，最后做演示与合规」。

| 序号 | 里程碑 | 主要产出 | 依赖 |
|------|--------|----------|------|
| M0 | 节点自检 | evidence `00-env-selfcheck` | SSH 已通 |
| M1 | 代码/引擎上节点 + Profile B 起服 | health 截图/日志；tmux 会话 | M0；路径改造 |
| M2 | Workbench/API 绑 `0.0.0.0:8888` | 公网或隧道可访问证明 | M1 |
| M3 | NIM/本地推理接一条链路 | nim-smoke + models.yaml diff | M1–M2；NGC/预置模型 |
| M4 | 黄金链 Spark 上跑通 | demo-run.log | M1–M3 |
| M5 | Negative trigger 文档 + 核心 SKILL 补丁 + 负向测试 | matrix + pytest 绿 | 可与 M1–M4 并行 |
| M6 | A/B 报告（本机 + Spark） | ab-*.json + 解读 | M4–M5 |
| M7 | 版本 pin + 脱敏扫描 | tag 一致、无密钥 | 提交前 |
| M8 | 录屏/答辩提纲（按细则） | 视频或分步脚本 | M4–M6 |

**提交前门禁（全部满足才宣称「平台分已具备」）**：

- [ ] Spark 上 `nvidia-smi` 与至少一个模型/服务 health 证据入 `docs/evidence/spark/`
- [ ] 公网端口或 SSH 隧道可访问 Workbench 的证明（无密码）
- [ ] 核心 skill negative trigger 文段 + 负向测试结果
- [ ] 至少一份 A/B JSON + 对「商业可验证性」的一句话解读
- [ ] 离线降级路径仍可演示（Spark 异常不冷场）
- [ ] 仓库无节点密码/登录表/API Key
- [ ] 全量 pytest 赛前复跑通过

---

## 10. 风险与降级

| 风险 | 概率 | 影响 | 降级 |
|------|------|------|------|
| 节点显存/磁盘不足拉不起 NIM | 中高 | 平台实证变薄 | 用预置模型/更小模型；仍保留 OpenAI-compat 切换日志；答辩诚实说明 |
| 内核 Windows 路径无法在节点使用 | 高 | Profile B 起不来 | 节点内重装引擎 venv 或 Docker；优先保证 `:7862` health 或高质量离线 byte-identical + 明确标注 |
| 公网仅 8888/9000 | 确定 | 多服务难暴露 | 只把 UI/API 绑 8888；其余隧道 |
| A/B 无显著差异 | 中 | 「Skills 必要性」叙事弱 | 扩大负向场景与字段级指标；展示「误触发率/违规外发拦截」而非只看准确率 |
| 凭据进仓/进视频 | 中 | 资格风险 | 提交前扫描；演示用占位符 |
| 版本叙事与 git 不一致 | 高（已存在） | 完整性/可信度 | M7 强制 pin |
| 赛程压缩 | 中 | 视频/十日谈缺失 | 先保 P0 证据包；加分项后置 |

---

## 11. 提交包结构（建议）

```
union-export-agent-livekernel/          # 唯一代码主体
  README.md                             # 一句话 + Spark 实证入口 + 快速开始
  docs/
    PRD-NCPAAI-Spark-Submission.md      # 本文件
    NCP-AAI-COVERAGE.md                 # 考点覆盖（状态以 evidence 为准刷新）
    NVIDIA-MAPPING.md
    DEPLOYMENT.md
    evidence/                           # 见 §5
  skills/                               # 33 skills + negative trigger
  deploy/nim/                           # NIM 配置级接入
  evaluation/                           # metrics + ab 产物入口
  scripts/run_demo.py e2e_l3.py ...
外部素材（不并入代码仓也可）：
  00_FINAL_DELIVERABLE/04_答辩与Demo脚本.md   # 文档结构范本
  Union-Export-Agent-20260917-NCP-AAI/        # 讲解 notebook
  Timo/                                        # 仅本地凭据，严禁公开
```

---

## 12. 答辩口径（30 秒 / 2 分钟）

**30 秒**：

> 我们不是又一个聊天 Agent。Union Export Agent 把一封 CNC 询盘变成可审计的商业决策：LLM 提议，确定性引擎裁决价格，Skills 管窄触发与业务能力，DGX Spark 提供本地算力。Omarchy 让 Agent 住进系统，NVIDIA/skills 让 Agent 用好硬件，我们让 Agent **做成可验证的生意**。

**2 分钟必答三刀**：

1. **价格谁生成？** → 永远是 Timo 引擎；LLM 被铁律禁止；现场比对 sha256。  
2. **和普通 Skill 包有何不同？** → 行业闭环 + 审计链 + HITL + negative trigger 不误触发 + A/B 可复现。  
3. **在哪跑的 Spark？** → 指 `docs/evidence/spark/` 与现场 health/端口；接口兼容已接 NIM/本地推理，行为等价看回归报告。

---

## 13. 验收标准（Definition of Done）

- [ ] livekernel 为唯一提交主体，README 版本与 git tag 一致
- [ ] Spark 环境自检 + 服务 health + 访问路径证据齐全
- [ ] 至少一条 NVIDIA/OpenAI-compat 模型链路在节点上有探活/调用记录
- [ ] 核心 Skills 含 negative trigger；负向测试通过
- [ ] 真实 A/B 报告落盘，并用一句话连到「可验证商业价值」
- [ ] 黄金链 Demo 可在 Spark（或已声明的降级路径）复现
- [ ] 开源脱敏完成；无节点账密、无客户敏感数据
- [ ] 答辩口径与证据包一致，无夸大实跑状态

---

## 14. 一句话 PRD

> **在已连通的 DGX Spark 上，把 livekernel 的行业 Agent 跑起来，用 negative trigger 与 A/B 证明 Skills 不是装饰，用确定性引擎与审计链证明商业价值可验证——主叙事是 Timo2026 的垂直空白，得分手段是评委看得见的实证。**
