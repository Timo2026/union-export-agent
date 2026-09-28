# PRD · v6.0.0 Unified Workbench + NVIDIA 口径

**方案代号**：`UEA-NCPAAI-v6.0.0-unified-workbench`  
**日期**：2026-09-19  
**状态**：**最终确认（W1–W3 全量）** · 实施前须 **隔离 worktree**  
**对齐**：NVIDIA NCP-AAI · NeMo Agent Toolkit / Guardrails / NIM · NemoClaw Skills/Dispatcher/OpenShell · livekernel v5.1 API  
**主线**：UI 统一 + NVIDIA 实证/口径（吸收 `PRD-v6-NVIDIA-Alignment` V1–V8 与 `PRD-v6.0.0-CONFIRM` W1–W3）  
**执行范围（用户 2026-09-19 终选）**：**W1–W3 全量**（约 60h 级，可分期交付）  
**NIM 证据**：**mock fallback 优先**，`NVIDIA_API_KEY` 后补；无 key/无 GPU 不阻塞  
**文档收敛**：以 **本文件为唯一执行 PRD**；Alignment / CONFIRM 作附录参考，不再另立口径

---

## 0. 输入摘要

| 来源 | 关键发现 |
|------|----------|
| `比赛/英伟达第三/测试1.txt` | 根 `index.html` 为 **160 行 Mock 三件套**（v3.0.2 A+B 融合）；`webui/index.html` 为 **单文件真接线**（约 30 fetch、3D、Ctrl+K）；v5.1.0 抽测 endpoint PASS；NVIDIA 对齐约 **7.9/10**（契约强、NIM 未实跑）；README「30 skills」与目录/`tool.py` 可能不一致 |
| `比赛/英伟达第三/index.html` | 同上 Mock 壳：Inbox/Inspector 5tab/Agent Console、iron-rule 底栏、**API:demo / Mock** |
| 本仓库文档 | `NCP-AAI-COVERAGE.md` / `NVIDIA-MAPPING.md` 诚实标注 🟢🟡🔴；agent.yaml 对齐 `nemo-agents-spec-v1` |
| 会话结论 | 现场演示用 `:8900`；形态用融合壳；**正确方向 = 融合壳包住真 API**；Agent Skills 对齐考点，短板是 GPU/NVIDIA 运行时实证 |

---

## 1. 为什么做 v6（痛点）

1. **双 UI 口径分裂**：Mock 壳形态好但不碰真业务；webui 能干活但版本标记混乱（文件 v2.4.0 / health v5.1.0 / 根目录 v3.0.2）、入口仍是「运维控制台 + 业务台」堆叠。  
2. **答辩风险**：只演示 Mock 会被问「数是不是真的」；只演示旧 webui 会回到「人机交互差」。  
3. **NVIDIA 口径风险**：Skill 数量、NIM「已接入」措辞若与磁盘/进程不一致，评委按字面找证据会翻车。  
4. **缺验收**：「迁移架构」未绑定 HITL 闭环 DoD 与截图证据。

---

## 2. 目标 / 非目标

### 2.1 目标（终选范围）

1. **唯一演示入口**：`http://127.0.0.1:8900/` → **Workbench v6.0.0**（真 API；由 FastAPI 提供 `webui/v6/`，同源打接口）。  
2. **前端工程化**：融合 IA（三栏 + 5tab + 黄金链 + 3D + Ctrl+K + Console）迁入分离/模块化 `webui/v6`；运维收进非默认「设置」。  
3. **业务闭环 DoD**：HITL + PASS 可复现；iron-rule-1 LOCKED；audit 非死数。  
4. **NVIDIA 全量对齐包（W2/W3）**：Skill 补齐与口径、装饰器/Pydantic、Guardrails nemo **可切换**（默认策略见 §5）、OTel、DAG orchestrator、NeMo 适配层（尽力）、NIM 探活 **mock-first**。  
5. **版本唯一**：health / UI / README / CHANGELOG = **v6.0.0**。

### 2.2 非目标

- 无 GPU 时 **不承诺** 本地 NIM/TRT/Triton 进程实跑；云端探活成功 ≠ GPU 实证。  
- 不重写 Timo；不破坏铁律①；不做多用户/OAuth/Skill 市场。  
- 比赛根目录 Mock **不作为**主演示入口。

---

## 3. 用户与场景

| 角色 | 主路径 |
|------|--------|
| 业务员 | 选信 → 证据/审批 → 批/拒或 draft_only 采纳 |
| 评委 | S2 HITL → 解释原因 → sha/铁律 → Skill/审计 |
| 工程 | 设置里模型探针、OpenShell、Swagger、skill_audit |

---

## 4. 信息架构（目标态）

```text
:8900/ → Workbench（默认）
┌ Top: Union Export Agent · v6.0.0 · 真健康值 · [运维] 折叠入口 ┐
│ Skill chips（可映射 /v1/skills）                              │
├ Inbox(真 mail) ─┬─ Inspector 5tab + 黄金链 + 3D ─┬─ Agent ─┤
│ 筛选/HITL 徽标  │ 邮件/草稿/历史/审批/HITL        │ 对话/Console │
│                 │ 批准双确认 · iron-rule          │ 证据链/快捷  │
└ statusbar: engine/API/LLM/dispatcher/audit + iron-rule-1 LOCKED ┘
运维（非默认）: 模型设置 · Skill/OpenShell · 上传 · Gmail · 反馈 · V12 · Swagger
```

**Mock 处置**：`比赛/英伟达第三/index.html` + `css/js` 保留为 **design-preview**；README 标明「勿用于现场数据演示」。

---

## 5. 执行分解（终选：W1–W3 全量）

> 来源：`PRD-v6.0.0-CONFIRM` W 表 + `PRD-v6-NVIDIA-Alignment` V 表；**以本表为准**。  
> 流水线原则：**W1 先交可演示**；W2/W3 可并行，但不得阻塞 W1 DoD。  
> 实施位置：**isolated worktree**；UI 落在 `webui/v6/`，保留 `webui/` legacy。

### W1 · UI 合一 + 诚实口径（必做，~18h）— 先交付

| ID | 任务 | 验收 |
|----|------|------|
| W1-1 / V6 | 新建 `webui/v6/`：融合 IA + 迁入真 fetch（inbox/rfq/skills/health/openshell/models/v12/cache 等）+ 3D + Ctrl+K | `:8900/` 默认 Workbench；抽测 ≥5 端点真数据；legacy 可回退 |
| W1-2 / V7 | README + COVERAGE + `/v1/skills` 数字一致：**25 Skill（18 独立 tool.py + 7 委托/声明）**；NIM 措辞「契约/profile 就绪 + runtime 视环境」 | 三处文案一致；无「已实跑 GPU NIM」虚假表述 |
| W1-3 | 版本对齐 **v6.0.0**（health / UI 品牌 / README / CHANGELOG）；Mock 退出主演示 | `/health.version` 含 v6.0.0 或明确迁移说明 |
| W1-4 / V1 | 补齐无 `tool.py` 的 skill **或** 文档/接口明确委托关系（禁止仍写「30 独立」） | 统计脚本或文档与 `GET /v1/skills` 一致 |
| W1-5 | Demo Script + `docs/screenshots/v6/`（Workbench / HITL / PASS / 模型或 OpenShell / 审计） | ≥5 张；与 DoD 场景一致 |
| W1-6 | pytest 回归（基线 508±）不因 UI 接线破坏 | 全绿或仅已知失败列表 |

### W2 · NVIDIA 实证 + 工程纪律（~24h）

| ID | 任务 | 验收 | 约束 |
|----|------|------|------|
| W2-1 / V5 | **NIM 探活**：`services/nim_health.py`（或等价）探配置端点；**无 key → mock/503 显式**；AgentCache 键 `nvidia:health`（TTL，失败也可见） | cache stats 含键；UI/接口标注 `NIM: mock` 或真实 latency；**不假装 GPU 在跑** | key 后补 |
| W2-2 / V4 | Guardrails：**生产默认仍 `builtin`**；增加 `backend=nemo` 可切换 + colang 测试路径；失败回退 builtin | 配置可切；测试记录 nemo 结果或 skip 原因 | 不因 nemo 失败阻断主链路 |
| W2-3 / V2+V3 | `@register_function` + Pydantic schema：**先核心 skill**（calc_quote/verify_gate/parse_rfq/golden_chain 等）再铺全量 | 装饰器可发现；抽样 SKILL.md parameters 更完整 | 允许分两批 |
| W2-4 | OpenTelemetry：audit jsonl **+** 可选 OTel exporter（feature flag，默认 audit） | 开关可测；默认路径不改既有审计语义 | 双轨期允许 |

### W3 · 编排升级 + 收尾（~18h）

| ID | 任务 | 验收 | 约束 |
|----|------|------|------|
| W3-1 | Orchestrator **DAG**（networkx 并行/条件）+ **线性 fallback** | DAG opt-in；既有黄金链/测试可回退 | 不默认破坏语义 |
| W3-2 | 剩余委托 skill 的 tool.py/契约补全 | 与 W1-4 口径闭环 | 与 README 一致 |
| W3-3 | NeMo Agent Toolkit 适配层（`agents/nemo_adapter` 或等价） | 契约可加载/文档可演示；无 NeMo 时 skip | 尽力项 |
| W3-4 | `docs/DEMO-v6.md` 答辩口径统一稿 + CHANGELOG | 口径与 README/COVERAGE 一致 | — |

**工期**：约 **60h** 量级；建议 **W1 单独可验收合并**，W2/W3 按表推进。

---

## 5b. NVIDIA 口径（终选）

| 项 | 终选 |
|----|------|
| Skill 对外数字 | **25（18 独立 + 7 委托/声明）**，以仓库实测为准动态修正 |
| NIM | **mock fallback 优先**；有 `NVIDIA_API_KEY` 再切真探活；文档写「API 可达性证据」≠「本机 GPU 实跑」 |
| Guardrails | 默认 **builtin**；nemo 为可选 backend |
| UI 状态 | 与 `/health` `source_label` 一致（offline vendored / MOCK 必须露出） |
| 运行时 | 现状 health：`engine=offline:vendored-kernel` · `multimodal=MOCK` — 演示话术必须包含降级说明 |

---

## 7. API 契约原则

1. **复用优先**：以 livekernel 已实现端点为准，禁止为「看起来像 NVIDIA」而空造 API。  
2. **UI 只经 Dispatcher/OpenShell 语义调用能力**（与铁律②一致）；前端不直连改写报价。  
3. 若需最小新增：仅 UI 强依赖且后端未有（例如聚合只读）——单独列变更表，默认 **0 新增**。

---

## 8. 验收 DoD

- [ ] `:8900/` 默认 Workbench，品牌 **Union Export Agent · v6.0.0**，无「Mock 主演示」字样  
- [ ] Inbox 列表来自 `/v1/mail/inbox`（或等价真实源）；选信后中栏数据非写死假 JSON（演示数据须角标）  
- [ ] 至少 **1× HITL** 与 **1× PASS** 场景 UI 全链路可复现  
- [ ] 批准需确认动作；`iron-rule-1` 状态栏 LOCKED；非法关闭有拒绝反馈（API 400 可测）  
- [ ] 黄金链步骤名正确且随状态变化  
- [ ] `/health` version 与 UI/README 一致  
- [ ] Skill 数量表述与磁盘/接口一致  
- [ ] `docs/screenshots/v6/` ≥5 张；含 Workbench、HITL、3D/报价、模型或 OpenShell、审计  
- [ ] 回滚：legacy webui 或 git 还原路径写明  
- [ ] 实施在 **isolated worktree**，不直接污染 main 未约定改动  

---

## 9. 里程碑（对应 W1–W3）

| 阶段 | 内容 | 产出 |
|------|------|------|
| **M0** | 开 **worktree** + 端点/skill 实测清单 | 可开工基线 |
| **M1 = W1** | `webui/v6` 真接线 + 口径 + 版本 + 截图 + 回归 | **可演示单轨 UI** |
| **M2 = W2** | NIM mock-first 探活/缓存 + Guardrails 可切 + 装饰器/Pydantic + OTel flag | NVIDIA 纪律包 |
| **M3 = W3** | DAG + 剩余 skill 契约 + NeMo 适配（尽力）+ DEMO-v6 | 收尾 |
| **M4** | 全量测试 + CHANGELOG v6.0.0 + 口径终检 | **v6.0.0 可交** |

---

## 10. 风险与缓解

| 风险 | 等级 | 缓解 |
|------|------|------|
| W2/W3 触及 skill/编排面广，回归炸 | 高 | worktree；DAG/装饰器 **opt-in**；每批跑 pytest |
| 无 GPU/key，NIM 实证仍弱 | 高 | **mock-first + 诚实 UI 角标**；答辩话术按 health 真值 |
| UI 合一回归 | 高 | `webui/v6` 新建；legacy 保留；先 W1 后 W2 |
| README/接口数字再分裂 | 高 | 统计进 W1 DoD；禁止营销「30 独立」 |
| OTel/DAG 改变语义 | 中 | feature flag + 线性 fallback |
| main 写入冲突 | 中 | **实施 worktree（已确认）** |

---

## 11. Demo Script（答辩 60s）

1. 打开 `:8900/` → Workbench v6.0.0，状态栏 iron-rule-1 LOCKED  
2. 选 HITL 邮件 → 中栏风险/sha/门禁 → 右栏 Skill 解释  
3. 双确认批准（或展示 FAIL 禁止批准）  
4. 打开运维：模型 6 角色 + OpenShell；强调 NIM=`backend=nvidia` 可切、本机 local  
5. Skill 列表数字与 README 一致 → 审计/trace  

---

## 12. 关键路径

| 类别 | 路径 |
|------|------|
| 生产 UI | `union-export-agent-livekernel/webui/`（目标：分离或等价模块） |
| API | `services/api_server.py` 等 |
| NVIDIA 文档 | `docs/NCP-AAI-COVERAGE.md` `docs/NVIDIA-MAPPING.md` |
| 本 PRD | `docs/PRD-v6-unified-workbench.md` |
| Mock 对照 | `比赛/英伟达第三/index.html` + `css/` + `js/` |
| 截图 | `docs/screenshots/v6/` |
| 输入笔记 | `比赛/英伟达第三/测试1.txt` |

---

## 13. 确认记录（最终）

| 项 | 决议 |
|----|------|
| 主线 | UI 统一 + NVIDIA 实证/口径 |
| **执行范围** | **W1–W3 全量**（非核心包/非仅 W1） |
| **NIM** | **mock fallback 优先**，API key 后补 |
| **文档** | **收敛进本 unified PRD**；Alignment/CONFIRM 为参考 |
| PRD 路径 | `docs/PRD-v6-unified-workbench.md` |
| 生产 UI 路径 | `:8900` + **`webui/v6/`**（legacy `webui/` 保留） |
| 实施 | **isolated worktree**；待用户下令「开始实施」 |
| 输入 | `测试1.txt` `测试2.txt` · health 实测 offline/MOCK |

---

## Decision Trace（终选）

1. **W1–W3 全量** — 用户明确选择，接受工期与回归成本；用 worktree + fallback 控险。  
2. **NIM mock-first** — 与本机 `engine=offline` / 无 GPU 一致，避免假绿。  
3. **Guardrails 默认 builtin** — 修正「nemo 默认开」的不可控项，nemo 作可切换实证。  
4. **唯一执行 PRD = 本文件** — 消灭多 PRD 口径分裂。  
5. **UI 必须挂 :8900/webui/v6** — 真 API 同源；根目录 Mock 不主演示。
