# 解决方案 · Union Export Agent（v6 修复 → 可演示 → 可生产）

**状态**：**已确认（本轮不实施代码）**  
**确认时间**：2026-09-19  
| 决策 | 决议 |
|------|------|
| 执行包 | **本轮不实施**；方案文档为准，代码另候指令 |
| 入口合同（实施时锁定） | **A2-b**：`GET /` = legacy `webui`；v6 在 **`GET /v6`** |
| 实施方式 | **isolated worktree**（待你说「开始实施」） |
| 方案文档 | **保留** `docs/SOLUTION-roadmap.md` |  
**依据**：你的遍历摘要 + 专家实测 `docs/EVAL-REPORT-v6-expert.md`（**515 passed / 13 failed**，非「499 全绿」）  
**原则**：禁止绕过测试；诚实边界；铁律不破；先闭环再扩生产

---

## 0. 摘要（已理解）

| 层 | 现状一句话 |
|----|------------|
| 产品 | CNC 外贸 RFQ → 可审计报价/HITL/draft 回复；L3 条件自动驾驶 |
| 模型 | 本地 `qwen3.8-27b`（FAST/VLM/REASON）+ `Qwen3-Embedding-0.6B` + `Qwen3-ASR-0.6B` + **Timo 确定性内核**；NIM 仅清单 |
| 强项 | 铁律/OpenShell/状态机/CAT 黄金链/Skill 封装/NovaStudio 插件化思路 |
| 弱项 | **v6 回归未清**（UI 入口/css/schema/nimo 口径）；生产件（SMTP/队列/多副本/K8s 实跑）多为「有文件无闭环」 |
| 定位 | **工程原型 / 可演示系统**，不是已上线生产 |

**与你摘要的两处校正**

1. 测试：「499 passed / 0 failed」→ **实测 515+13F**（v6 改路由后旧 UI 测试红）。  
2. Skill：「25 = 20+5」→ 实测 **25 SKILL.md / 24 tool.py / 缺 `cnc-quote`**；`@register_function` **生产未用**。

---

## 1. 目标分层

```text
L0  修复可跑   → pytest 全绿 + :8900 入口/静态资源/版本一致
L1  比赛可演示 → Workbench 真数据 + HITL/PASS + 诚实 NVIDIA 口径 + 截图
L2  可试生产   → 发信/通知/队列/配置热载/备份/跨平台启动
L3  可上生产   → 蓝绿/K8s 实跑/凭据/履约闭环/NIM GPU
```

当前卡在 **L0 未完成**，却按 L1/L3 叙事——解决方案先 **钉死 L0**。

---

## 2. 解决方案（四条轨道）

### Track A · P0 修复（必须，约 4–8h）— 对应 EVAL P0

| ID | 动作 | 验收 |
|----|------|------|
| A1 | `api_server` **mount** `/css` `/js`（及 index 引用资源） | `GET /css/workbench.css` **200** |
| A2 | 入口合同写死：`GET /`=选定 UI；`GET /webui`=legacy；**改测试矩阵** | 对应 URL 断言全绿 |
| A3 | **重启** `:8900` 并对齐 health/UI/README **单一版本号** | `/health.version` = UI = README |
| A4 | 修 `schema_validator` 枚举（IT4–IT10、状态机）或 light 路径补 enum | `test_schema_validation` 全绿 |
| A5 | 修 `nim_health` **force_refresh / 缓存隔离** | `test_nim_health` 全绿 |
| A6 | 补 `cnc-quote/tool.py` 或文档/allowlist 明确委托 | 与 `scripts/count_skills.py` 输出一致 |
| A7 | 全量 `pytest tests/ -q` | **0 failed**（允许既有 skip） |

**入口合同选项（A2 二选一，实施前你定）**

- **A2-a 比赛/产品**：`/` = v6 Workbench（融合/真接线），legacy 测 `/webui`。  
- **A2-b 稳妥**：`/` = 现网 webui（能力全），v6 放 `/v6` 直至达标。

### Track B · 口径与工程诚实（与 A 并行，约 2–4h）

| ID | 动作 |
|----|------|
| B1 | `scripts/count_skills.py` → README/COVERAGE/UI 只引用脚本结果 |
| B2 | `register_function`：统一 skill_id（下划线）并在核心 skill 真装饰，或文档降为「可选」 |
| B3 | `nemo_soft`：要么 `check_*` 真调 rails，要么文档写「预留，不进检查路径」 |
| B4 | 环境变量 `UEA_USE_NEMO_GUARDRAILS` 实现或从 yaml 删除 |
| B5 | NVIDIA 状态表与 `/health` `source_label` 一致（offline/MOCK 必露出） |
| B6 | 所有「测试全绿」改为 **附 pytest 命令与数字**，禁止推理替代 |

### Track C · 比赛/演示包（A 全绿后，约 1 天）

| ID | 动作 |
|----|------|
| C1 | Demo Script：S2 HITL + S4 PASS + 铁律锁 + Skill 列表数字 |
| C2 | `docs/screenshots/v6/` ≥5 张（由实跑生成，不手搓） |
| C3 | 模型面板展示：本地 qwen/ASR/EMBED + Timo 锁 + NIM「需 GPU/key」 |
| C4 | 可选：`NVIDIA_API_KEY` 探活一次并截 trace（无 key 保持 mock） |
| C5 | 现场清单：一键启动脚本、离线兜底话术、Swagger |

### Track D · 生产化（L2/L3，分期，不在本轮一口气做完）

| 优先级 | 项 | 解决要点 |
|--------|-----|----------|
| D-P0 | 真实 SMTP / Telegram / Slack | `notify` + `external_send` 接真实通道；**审批后**才发；保留 draft_only 默认 |
| D-P0 | 任务队列 | 邮件编排出进程内循环 → **Redis/Celery 或至少文件队列 + 幂等键 + 单消费者锁** |
| D-P0 | 配置热加载 | watchdog 监听 `config/*.yaml`；加载失败回滚并审计 |
| D-P0 | 数据备份 | `data/*.sqlite3` / contexts / audit 定时备份 + 恢复演练脚本 |
| D-P1 | 跨平台启动 | `start_api.sh` / compose profile 替代仅 `.bat` |
| D-P1 | 可观测 | Prometheus 指标 + 现有 OTEL JSONL 对齐 Grafana |
| D-P1 | 凭据 | credentials 出库 → Vault/环境变量/CI secret |
| D-P1 | 供应商履约最小环 | PO → 状态机 → 收货；复用现有 supplier 模块测试 |
| D-P2 | K8s/HPA/NIM 实跑 | 有 GPU/集群再执行 `deploy/`；无则文档保持 🟡 |
| D-P2 | tools 1.2GB 外置 | submodule/镜像/下载脚本，CI 不再克隆全量 |

**生产化原则**

1. **不破铁律**：任何自动发信仍受 HITL/门禁/draft_only 约束。  
2. **可回滚**：新队列/新通知与旧路径并行开关。  
3. **先测后合**：每项带 pytest/脚本验收。

---

## 3. 模型方案（沿用 + 可切换）

| 角色 | 现网 | 方案 |
|------|------|------|
| REASON/VISION/FAST | `qwen3.8-27b` :1234 | 保留；UI 显示 latency/offline |
| EMBED | `Qwen3-Embedding-0.6B` :1278 | 保留；RAG 离线 mock 角标 |
| ASR | `Qwen3-ASR-0.6B` :8089 | 保留 |
| DETERMINISTIC | Timo :7862 / vendored | **永不替换** |
| NIM | 清单 | key/GPU 前 mock；有则 `model_router.backend=nvidia` 一条链路实证 |

---

## 4. 里程碑

| 里程碑 | 内容 | 出口标准 |
|--------|------|----------|
| **M0** | 确认本方案 + worktree + A2 入口合同 | 书面确认 |
| **M1 = Track A** | P0 修复 | **pytest 0 failed**；`:8900` css/health/UI 一致 |
| **M2 = Track B+C** | 口径 + 演示包 | README 数=脚本；截图与 Demo 可讲 |
| **M3 = Track D-P0** | 发信/队列/热载/备份 | 手工演练通过 + 测试 |
| **M4 = D-P1/P2** | 运维与 GPU | 按环境分期 |

---

## 5. 风险

| 风险 | 缓解 |
|------|------|
| 继续「推理测试」 | 强制 pytest 命令输出进报告 |
| UI 入口反复切换 | M0 锁死 A2-a 或 A2-b |
| 生产范围膨胀 | D 与 A/B/C 严格分期；无 GPU 不承诺 NIM 实跑 |
| main 冲突 | 实施 **isolated worktree**（待你确认） |

---

## 6. 请你确认（决策点）

1. **执行包**：只做 A+B（修复+口径） / **A+B+C（推荐）** / A–D 全量分期  
2. **入口合同**：A2-a `/`=v6 或 A2-b `/`=legacy、v6 在 `/v6`  
3. **worktree**：实施是否隔离  
4. **文档**：本方案落 `docs/SOLUTION-roadmap.md` 是否保留  

确认后顺序：**开 worktree → Track A → 全量 pytest → Track B/C**。
