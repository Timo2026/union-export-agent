# PRD v6.0.0 — NVIDIA 栈实证 + UI 合一 + 诚实性修正

> 状态：**待确认（DRAFT）** · 输入源：`测试1.txt`（前三轮对话记录）+ `index.html`（融合版壳）+ 仓库实测
> 目标：把"契约对齐 3.5/5"提升到"实证对齐 4.0+/5"，消除 UI 口径分裂，修正营销措辞

---

## 0. 输入摘要（三份证据合一）

| 来源 | 关键事实 | 判定 |
|---|---|---|
| `index.html`（融合版壳，160 行） | 关注点分离架构（HTML/CSS/JS 拆分）；标 `v3.0.2 · Mock`；7 skill chips + 5 Inspector tabs + Ctrl+K + 证据链；**无 3D、无真实 fetch** | 工程纪律优、功能回退 |
| `webui/index.html`（线上，169KB 单文件） | v5.1.0 服务；**30 个 fetch** 真接 mailbox/rfq/cache/spark；3D 预览；残标 `v2.4.0` | 功能全、纪律差 |
| NVIDIA 栈评估（两套打分） | 契约层 8/10、运行时实证 5/10；25 目录/18 独立 tool.py；NIM 仅清单无实跑 | 架构高、实证中 |

**三组矛盾必须同时解决，不能只动一处。**

---

## 1. 推理：三个核心矛盾

### 矛盾 A — UI 双轨分裂（最高优先）
- 线上 `:8900` 能跑真业务但 IA 混杂（运维台+业务台叠床架屋）
- 融合版 IA 清晰但标 Mock、无 3D、无真实接线
- **风险**：答辩时评委问"演示哪个？" → 口径分裂直接扣分
- **解**：融合版 IA 作壳，吞掉 :8900 的 30 个 fetch + 3D，**单轨对外**

### 矛盾 B — NVIDIA 栈"说有 vs 实跑"
- README 称"30 skills + NIM 接入"，实测 25 目录/18 独立、NIM 0 进程
- `NCP-AAI-COVERAGE.md` 已诚实标 🔴，但 README 没同步
- **风险**：评委按 README 字面找证据 → 诚实性翻车
- **解**：数字校正 + 起至少 1 个 NIM 链路实证

### 矛盾 C — 工程纪律缺件
- 缺 `@register_function` 装饰器（NeMo Toolkit 原生加载不了）
- 缺 Pydantic schema（args 强校验靠手写）
- 缺 OTel trace span（audit 是自实现 jsonl）
- 缺 DAG 编排（Orchestrator 线性）
- 缺运行时 content 扫描（Guardrails 只静态 allowlist）
- **解**：W1-W3 三周冲刺补齐（见 §3）

---

## 2. 方案目标（一句话）

**把融合版 IA 升级为 v6.0.0 单轨主界面（吞 :8900 真实接线 + 3D），同时起 1 条 NIM 实证链路 + 补 5 件工程纪律缺件 + 校正 README 诚实措辞，使 NVIDIA 栈契合度从 3.5 → 4.2+。**

### 量化验收
| 指标 | 当前 | 目标 |
|---|---|---|
| NVIDIA 栈契合度 | 3.5/5 | ≥4.2/5 |
| UI 对外入口数 | 2（分裂） | 1（合一） |
| README ↔ 实测一致性 | 70% | 100% |
| 独立 tool.py skill 数 | 18/25 | 23/25 |
| NIM 实跑链路 | 0 | ≥1 |
| 真实 fetch 接线数 | 30（webui 独有） | 30（迁入主壳） |

---

## 3. 工作分解（W1-W3，总 ~60h）

### W1 · UI 合一 + 诚实修正（~18h）— **比赛前必做**
| 任务 | 产物 | 估时 |
|---|---|---|
| W1-1 把 webui 的 30 个 fetch + 3D canvas 迁入融合版壳（HTML/CSS/JS 分离保留） | `webui/index.html` v6.0.0 + `css/`+`js/` | 10h |
| W1-2 README 数字校正：30→"25 Skill（18 独立+7 委托）"；NIM 加"(profile 就绪，需 GPU 实跑)" | `README.md` | 1h |
| W1-3 webui 残标 v2.4.0 → v6.0.0；融合版 Mock 标记改成真健康检查 | 两处版本号 | 1h |
| W1-4 E2E 截图重跑（PASS/HITL/BLOCKED 3 场景 × 4 张） | `docs/screenshots/v60/` | 4h |
| W1-5 pytest 回归确保 499 仍绿 | 测试报告 | 2h |

### W2 · NVIDIA 实证 + 工程纪律（~24h）— **有 GPU 才能做 W2-1**
| 任务 | 产物 | 估时 |
|---|---|---|
| W2-1 起 1 个 NIM 容器（llama-3.1-8b），model_router 切 backend=nvidia，截 trace | NIM 探活证据 + trace 截图 | 6h |
| W2-2 Guardrails backend 切 nemo，跑通 `rails.co` colang（运行时 content 扫描） | guardrails nemo 模式绿 | 4h |
| W2-3 加 `@register_function` 装饰器 + Pydantic schema 自动生成（NeMo Toolkit 兼容） | `skills/_decorators.py` | 8h |
| W2-4 OpenTelemetry 集成：audit jsonl → OTel span exporter | `services/otel_exporter.py` | 6h |

### W3 · 编排升级 + 收尾（~18h）
| 任务 | 产物 | 估时 |
|---|---|---|
| W3-1 Orchestrator 线性 → DAG（networkx，支持并行/条件分支） | `skills/orchestrator/tool.py` v2 | 8h |
| W3-2 补齐 5 个无 tool.py 的 skill（cnc-quote/dfm-conflict/reply-draft/rfq-extraction/step-analysis） | 5 × tool.py | 5h |
| W3-3 NeMo Agent Toolkit 适配层（cat_controller 支持 NeMo Runner） | `agents/nemo_adapter.py` | 3h |
| W3-4 demo 视频 + 答辩口径统一稿 | `docs/DEMO-v6.md` | 2h |

---

## 4. 不足与风险（诚实自评）

| 等级 | 不足 | 影响 | 缓解 |
|---|---|---|---|
| 🔴 高 | **本机无 GPU**，W2-1/W2-2 NIM 实证做不了 | 契合度卡在 3.5 | 需 GPU 环境；或退而求其次用云端 NIM API key 跑探活 |
| 🟡 中 | UI 合一改动面大（webui 169KB 内联 → 拆分），易引入回归 | W1 工期风险 | 隔离 worktree；保留 webui 原件作回退；增量迁移 fetch |
| 🟡 中 | `@register_function` 改造触及 25 个 skill | W2-3 可能延期 | 先做 3 个核心 skill 试水，验证后再铺 |
| 🟢 低 | OTel exporter 与现有 audit 双轨期 | 短期重复 | 设 feature flag，默认走 audit，OTel 可选 |
| 🟢 低 | DAG 编排改变执行语义 | 既有测试可能挂 | 保留线性模式作 fallback，DAG 作 opt-in |

**最大不确定性**：W2 全部依赖 GPU。若无 GPU，方案降级为"只做 W1+W3"，契合度上限约 3.9（NIM 实证缺口无法闭合）。

---

## 5. 降级方案（无 GPU 场景）

若比赛前拿不到 GPU：
- **只做 W1 + W3**（UI 合一 + 工程纪律 + 诚实修正），跳过 W2-1/W2-2
- NIM 部分改用 **NVIDIA云端 API（integrate.api.nvidia.com）** 跑 1 次探活截图作证据（需 API key）
- 答辩口径调整为："NIM 后端已验证端到端联通（附云端探活 trace），本机因无 GPU 走 local 兜底，切换是 `backend=nvidia` 一行配置"

---

## 6. 需要你确认的 5 个决策点

| # | 决策 | 选项 | 我的建议 |
|---|---|---|---|
| D1 | UI 合一方向 | (a) 融合版壳吞 :8900 接线 / (b) webui 直接改用分离架构 / (c) 维持双轨 | **(a)** — 融合版 IA 更优，且保留分离架构利于演进 |
| D2 | 是否动 webui 原件 | (a) 原地改 / (b) 新建 webui/v6/ 保留原件 | **(b)** — 零风险回退，比赛现场可切 |
| D3 | README 数字口径 | (a) "25 Skill (18 独立+7 委托)" / (b) 维持 30 但加注 / (c) 不改 | **(a)** — 最诚实，评委不会抓把柄 |
| D4 | NIM 实证路径 | (a) 等本地 GPU / (b) 云端 NIM API 探活 / (c) 只放部署清单 | **(b)** — 最快拿证据，无需硬件 |
| D5 | 执行范围 | (a) 全量 W1-W3 / (b) 只 W1+W3 / (c) 只 W1 | 取决于 D4 + 你给的时间窗 |

---

## 7. 我建议的最小可行方案（若你只想最稳的一档）

**只做 W1（18h）+ D4 云端 NIM 探活（2h）= 20h**，即可：
- 消除 UI 双轨分裂（最大答辩风险）
- 拿到 1 条 NIM 实证 trace（补最大短板）
- README 诚实校正（防翻车）

契合度从 3.5 → ~3.9，但**风险最低、工期最确定**。

---

**请确认 D1-D5，或告诉我时间窗 + 是否有 GPU/API key，我据此定执行范围并开工。**
