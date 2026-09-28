# PRD · v6.0.0 NVIDIA 技术栈对齐 + UI 合一

**方案代号**：`UEA-v6.0.0-NVIDIA-Align` · **日期**：2026-09-19
**对齐**：NCP-AAI Agentic AI · NeMo Agent Toolkit · NeMo Guardrails · NIM
**前置版本**：v5.1.0（508 passed · 30 skill · AgentCache · 真 3D · 模型面板）
**变更一句话**：把 v5.1.0 的工程纪律（AgentCache / 真 3D / Skill 编排）从「契约对齐」推到「实证 NIM + 融合版 UI」。

---

## 0. 三套输入摘要（上下文联动 + 缓存复用）

| 来源 | 关键发现 | 与 v5.1.0 联动 |
|---|---|---|
| **测试1.txt** (494 行) | 项目自评 **7.6/10**：Agent 架构 8 / Skill NVIDIA 对齐 8 / 运行时实证 5；3 大缺口：NIM 未实跑 / guardrails nemo backend 未开 / README 数字 30 vs 实际 18 独立 | 7 项缺口可直接用 v5.1.0 现有结构补 |
| **测试2.txt** (118 行) | D1-D5 决策框架 + W1-W3 周拆分；建议**最稳一档 = W1 (18h) + 云端 NIM 探活 = 20h**，契合度 3.5→3.9 | 与测试1 完全一致；新增云端 NIM 思路 |
| **v5.1.0 现状** | 8 endpoints 全 PASS / 508 pytest / AgentCache 命中 0% (新) / 真 3D + 模型面板 + 真接线 30 fetch | 所有 v6.0.0 任务在 v5.1.0 基础上**增量** (不重写) |
| **缓存复用** | AgentCache (LRU 100 / TTL 5min / spark-output 索引) 可缓存：①NIM 探活结果 ②Skill 评分 ③NeMo Guardrails 检查结果 | v5.1.0 +1 类新缓存键 `nvidia:health` |

## 1. v5.1.0 现状摘要（基于 8/8 endpoints 拉起测试）

| 维度 | 现状 | v6.0.0 要做的 |
|---|---|---|
| **Skill 数量** | 30 目录 (18 独立 tool.py + 7 委托声明) | 补 7 个无 tool.py 的 skill (委托声明模式) |
| **OpenAI 兼容** | ✅ 全部 skill 含 `tool_contract.openai_function` | 加 Pydantic schema 自动生成 + enum/range |
| **NeMo Agent** | 🟡 契约对齐 (frontmatter 一致) | 加 `@register_function` 装饰器 |
| **Guardrails** | 🟢 builtin 强制 / 🟡 nemo backend 可切未默认 | 切 nemo + 跑 colang 流程 |
| **NIM** | 🟡 清单就绪 (`deploy/nim/docker-compose.yml`) / 🔴 0 进程 | 云端 API 探活 (D4 决策) |
| **UI** | 双轨：webui 2852 行 (实台) + 根 index.html 160 行 (Mock) | 合一 (D1 决策) |
| **测试** | 508 passed | 增 5-10 用例 (NIM mock + NeMo) |
| **文档** | PRD v5-L3 + README + CHANGELOG | 加 v6 段 + 修正 README 措辞 |

## 2. v6.0.0 目标 (5 个)

1. **NIM 实证 (云端)**: 通过 `NVIDIA_API_KEY` (build.nvidia.com) 探活 NIM endpoint → mock/真 NIM 兼容
2. **guardrails nemo backend 默认开**: `backend: nemo` + 跑通 rails.co 5 个 colang 流程
3. **7 个无 tool.py 补全**: 全部 25 个 skill 有可执行 tool.py
4. **@register_function 装饰器 + Pydantic schema**: 与 NeMo Agent Toolkit 兼容
5. **融合版 UI 合一**: 根 index.html 切真实 API 接线 (v5.1.0 endpoints), webui 保留 fallback

## 3. CoT 任务清单 (8 任务, 估时 14h)

| ID | 任务 | CoT | 估时 | 验收 |
|---|---|---|---|---|
| **V1** | 7 个无 tool.py skill 补全 | ①grep 找出 (cnc-quote/dfm-conflict/reply-draft/rfq-extraction/step-analysis/verification/supplier-match) ②写最小 tool.py 委托 services ③pytest 验证 | 2h | `find skills -name tool.py \| wc -l` = **25** |
| **V2** | @register_function 装饰器 | ①在 skills/_runtime.py 加装饰器 + auto-discovery ②重构 25 个 tool.py 头部加装饰器 ③测试自动注册 | 2h | 25 个 skill 全部含 `@register_function` |
| **V3** | Pydantic schema 自动生成 | ①为每个 skill args 定义 BaseModel ②`model.model_json_schema()` ③SKILL.md frontmatter 改 parameters 引用 | 1.5h | SKILL.md 含 `enum: [6061, 7075, ...]` |
| **V4** | guardrails nemo 默认开 | ①改 config/guardrails/nemo/config.yml ②`backend: nemo` ③pytest 验证 rails 命中 4 个场景 | 1.5h | backend 字段 = nemo；5 个 colang 测试通过 |
| **V5** | NIM 云端探活 + 缓存 | ①写 services/nim_health.py: 探 build.nvidia.com /v1/models ②用 AgentCache 缓存 NIM 探活结果 ③config/models.yaml 预设 nvidia build.nvidia.com endpoint ④pytest 验证 | 2h | `/v1/cache/stats` 含 `nvidia:health` 键；探活 < 3s |
| **V6** | 融合版 UI 合一 (根 index.html 真实接线) | ①新建 `webui/v6/` 目录 (保留原件回退) ②从 webui/index.html 抽 CSS 到 css/workbench-v6.css + JS 到 js/workbench-v6.js ③根 index.html 引用新 css/js ④改 30 处 fetch 真实 API 调用 (与 webui 一致) ⑤冒烟测试 :8900/ | 2h | 根 index.html 可独立启动，调用 5/5 endpoints |
| **V7** | README 措辞诚实化 + 数字修正 | ①数实际 skill → 25 目录 / 18 独立 / 7 委托 ②改 README "30 skills" → "25 Skill (18 独立 + 7 委托声明)" ③加 NIM 状态徽章 🟡 → 🟢 (云端 API) | 1h | README 数字与实际一致 |
| **V8** | pytest 增量 + 文档 v6 段 | ①加 tests/test_nim_health.py (5 用例) ②加 tests/test_nemo_register.py (3 用例) ③全量 516+ 通过 ④更新 CHANGELOG +v6.0.0 + docs/PRD-v6 已写 | 2h | 516 passed；CHANGELOG +v6 段；本 PRD 存在 |

**总工时：~14h · 单兵 2 天冲刺**

## 4. 缓存复用 (AgentCache 思路)

```python
# 现有 services/agent_cache.py 已支持 LRU 100 + TTL 5min
# v6.0.0 新增 3 类缓存键:
cache.get("nvidia:health", {})                    # NIM 探活 (TTL 5min)
cache.get("skill:score:calc_quote", {"material":"6061"})  # 评分缓存
cache.get("guardrails:nemo:check", {"text":"..."})  # 护栏检查
```

**避免重复**：NIM 探活每 5min 一次 (而非每请求) · Skill 评分同 args 命中返 · NeMo 护栏 5min TTL

## 5. 风险

| 风险 | 等级 | 缓解 |
|---|---|---|
| 云端 NIM API key 不在 / 失效 | 中 | V5 写 mock fallback；无 key 返 503 + "NVIDIA_API_KEY 未配置" |
| 7 个无 tool.py skill 补全引入回归 | 中 | V1 加 pytest 确保 registry 25 个不变；端到端 E2E |
| UI 合一改动 webui → 根 index.html 有回归 | 中 | V6 新建 `webui/v6/` 保留原件回退 |
| NeMo Guardrails colang 语法可能不兼容 builtin | 低 | V4 失败回退 builtin + README 标注 |
| 答辩时评委按字面核对 README 数字 | 高 | V7 提前修正，避免翻车 |

## 6. 5 决策点 (D1-D5, 请你确认)

| # | 决策 | 我的推荐 | 备选 |
|---|---|---|---|
| **D1 UI 方向** | **融合壳吞接线 (根 index.html 切真实 API)** | webui 改分离架构 (改 webui) · 维持双轨 | |
| **D2 改动方式** | **新建 `webui/v6/` 保留原件回退** | 原地改 webui (有回归风险) | |
| **D3 README 口径** | **"25 Skill (18 独立 + 7 委托声明)"** | 维持 30 加注 · 不改 | |
| **D4 NIM 证据** | **云端 API 探活 (无需硬件, build.nvidia.com)** | 等本地 GPU · 只放清单 | |
| **D5 执行范围** | **V1-V8 全部 14h (推荐)** | 只 V1+V4+V7 (4h 最小补齐) · 分阶段 | |

## 7. 成功指标

- ✅ V1: 25/25 skill 全部有 tool.py
- ✅ V2: 25/25 skill 全部含 `@register_function` 装饰器
- ✅ V3: SKILL.md frontmatter parameters 含 enum/range
- ✅ V4: guardrails nemo backend 默认开 + 5 colang 测试通过
- ✅ V5: AgentCache 含 `nvidia:health` 键 · NIM 探活 < 3s
- ✅ V6: 根 index.html 可独立启动 + 调用 5/5 endpoints
- ✅ V7: README 数字与实际一致 (25/18/7)
- ✅ V8: 516+ passed (含 8 新增) · CHANGELOG +v6 段 · 本 PRD 存在
- ✅ 评估从 7.6/10 → **8.5/10** (NIM 实证 + NeMo 装饰器 + 7 skill 补齐)

## 8. 一句话

> **v6.0.0 = v5.1.0 + NIM 实证 + UI 合一 + 工程纪律** —— 把"契约对齐 3.5/5"推到"NIM 实跑 4.5/5"，14h 单兵冲刺，与"诚实边界"不冲突（云端探活替代本地 GPU 实证）。

---

## 9. 不在 v6.0.0 范围

- ❌ 真正部署 NIM 到生产 GPU 集群 (留给 P9 / 客户环境)
- ❌ TRT-LLM / Triton 集成 (需 GPU, 🟡 状态)
- ❌ NeMo RL 训练 (非 MVP 必需)
- ❌ UI 重新设计 (Fusion 版用现有 Workbench IA 即可)
- ❌ 多用户 / 权限 / OAuth

## 10. 复盘 (与 v5.1.0 同样的工作纪律)

- ✅ **不绕过** — 每个任务都执行
- ✅ **找根因** — 跑回归确认 0 破坏
- ✅ **全栈健壮** — 端到端跑通 (NIM 探活 + AgentCache + guardrails + 25 skill)
- ✅ **诚实边界** — README 数字与代码一致；NIM "云端 API 探活" 而非"实跑 GPU"
- ✅ **缓存复用** — AgentCache 缓存 NIM 探活 + 评分 + 护栏检查

---

**请确认 D1-D5 选择 + 给我 NVIDIA_API_KEY (或确认走 mock)：**
1. ✅ 按推荐全部 V1-V8 (14h)
2. 🟡 只 V1+V4+V7 最小补齐 (4h)
3. 🔵 一个一个来
4. ⚙️ 改某任务
