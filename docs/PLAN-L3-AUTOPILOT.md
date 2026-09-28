# 方案：邮件自动驱动的 L3 无人驾驶制造出口 Agent

**代号**：`UEA-L3-AUTOPILOT` · **日期**：2026-09-19
**目标**：在冻结架构（六条铁律不破）上，把现有"手动上传 → 全程 HITL"升级为
**「邮件自动拉取 → 自动跑黄金链 → 自治裁决 → 仅异常升级人工」** 的 L3 级自治 Agent，
并把 6 个外部能力（MinerU / ragflow / OmniVoice / SearXNG / 21 个制造技能 / DFM-Quote 多Agent）接线成可切换后端。

> 状态：**初步方案，待确认后再动手实现。** 下面是推理（CoT）+ 落地拆解。

---

## 一、上下文联动摘要（现状盘点）

| 层 | 现有能力 | 文件 | 与 L3 的差距 |
|----|---------|------|-------------|
| 收件 | Gmail IMAP **手动 sync()** | `services/gmail_imap.py` | 无定时轮询守护进程 |
| 解析 | stdlib email / OCP B-rep / funasr / pypdf | `services/file_intake.py` | PDF 弱（pypdf 缺库跳过） |
| 编排 | CAT 黄金链（手动触发） | `agents/cat_controller.py` | 不被新邮件事件自动触发 |
| 报价 | Timo 确定性内核（铁律①） | `adapters/timo_adapter.py` | 已就绪 |
| DFM | ConflictChecker（辟） | `services/intake.py` | 已就绪 |
| 商业 | freight/customs/landed cost（牟） | `services/commercial.py` | 已就绪 |
| RAG | 本地词频检索（援，弱） | `services/rag.py` | 召回弱，无联网证据 |
| 验收 | 辟牟援推止 + HITL（推/止） | `services/verification.py` | 已就绪，是 L3 裁决核心 |
| 记忆 | CRM + Postmortem（闭环） | `services/crm_memory.py` | 已就绪 |
| 回复 | draft_only（铁律①） | `services/reply.py` | 草稿止步，无发送闭环 |
| 平台 | Guardrails / Tracer / Router | `services/*.py` | 已就绪 |
| 技能 | 11 个本地技能 + dispatcher | `services/skill_dispatcher.py` | 未纳入外部 21 技能 |

**一句话结论**：内核黄金链已闭环且铁律坚固，**唯一缺的是"发动机"（无人值守的事件循环）+ "传感器升级"（外部工具）+ "油门分级"（L3 自治策略）**。

---

## 二、自动驾驶分级映射（L0–L5 → 本系统）

| 级别 | 含义 | 本系统对应 | 现状 |
|------|------|-----------|------|
| L1 辅助 | 人工上传，系统出数，全程人工 | 手动 `/v1/rfq/intake` | 已有 |
| L2 部分 | 自动跑链，每步都等人工确认 | HITL 全量 | 已有 |
| **L3 条件自治** | **邮件自动入站→自动跑链→绿灯放行到 CRM→仅红灯/黄灯升级人工** | **本方案目标** | 要做 |
| L4 高度自治 | 白名单客户/场景**自动发送**回复 | L3 达成后可解锁 | 后续 |
| L5 全自治 | 零人工 | — | 不在本期 |

**L3 的本质**：人"眼睛离开"（eyes-off）——对高置信绿灯（PASS + margin 达标 + 无冲突 + 非新客 + 无护栏告警）的询盘，Agent 自动跑完并落 CRM，**只在黄灯（HITL）/红灯（BLOCKED）时才叫人**。这恰好复用现有 `Verification` 的三态输出作为"交通灯"。

---

## 三、推理链（CoT：为什么这么设计，铁律不破）

**P1 —— 事件循环是"发动机"，不是新架构。**
> 现有黄金链是同步函数 `CATController.run()`；L3 只需在它**外面包一个 loop**：
> `定时拉信 → 对每封新信调 run() → 把三态结果分流`。黄金链内部一行不改，铁律②（状态机是业务真相）得以保留。

**P2 —— 自治 ≠ 自动发送。**
> L3 的"自动"指**自动推进到 CRM/DONE**，不是自动发邮件。回复始终 `draft_only`（铁律①：LLM 不定价格、不替你承诺）。
> 绿灯件只意味着"系统已算完并入库，你随时可一键发送草稿"；真正的对外发送留给 L4（白名单）或人工。
> 这保证**L3 不触碰对外承诺风险**。

**P3 —— 交通灯复用现有裁决，不引入新的"自治模型"。**
> `Verification.run()` 已输出 `PASS / HITL / BLOCKED` + reasons。
> L3 分流策略只是：
> - `PASS` + (margin≥floor & 无冲突 & 非护栏升级) → **AUTO_DONE**（自动写 CRM，标记 `auto_completed=true`）
> - `HITL` → 进人工待办队列（不静默）
> - `BLOCKED` → 自动生成澄清草稿，标记待人工复核
> 即"无人驾驶"的判断逻辑**已经是确定性的**，不让 LLM 决定是否放行（铁律①守护）。

**P4 —— 外部工具是"可切换传感器"，不动主干。**
> 6 个外部能力都走 **OpenAI 兼容 / 子进程 / HTTP** 的现有适配器边界模式：
> - MinerU：替换 `file_intake.parse_pdf`（弱→强 OCR/版式）
> - ragflow：替换 `rag.search`（词频→向量召回），走 HTTP
> - OmniVoice：作为 `model_router` 的 ASR 角色 `backend=omnivoice` 备选
> - SearXNG：新增"联网证据"（援的增强），补 RAG 召回不足
> - 21 技能包：注册进 `skill_registry`，受 OpenShell allow-list 约束
> - DFM-Quote-Agent（fleet）：作为 `calc_quote` 的对照/增强（仍以确定性内核为唯一权威）
> 每个都 **opt-in、可降级、显式标注**，符合现有"诚实边界"原则。

**P5 —— 多模态冲突仍强制升级（铁律⑤不破）。**
> M1 场景（语音放宽公差 vs 邮件）在 L3 下**依然命中 HITL**，绝不静默采纳——这是现有 Hero moment，自治等级不削弱它。

---

## 四、核心模块联动总图（目标态）

```
┌─────────────────────────────────────────────────────────────┐
│  Autopilot Loop (新增 · 发动机)                              │
│  每 N 秒: gmail.sync() → 新信入 mailbox → 触发 run()         │
└───────┬─────────────────────────────────────────────────────┘
        │ 新邮件事件 (context_id)
        ▼
┌──────────────────────────────────────────────────────┐
│  Multimodal Intake (升级传感器)                       │
│  email ← stdlib · pdf ← MinerU · audio ← OmniVoice   │
│  image ← VLM · step ← OCP · excel ← openpyxl        │
└───────┬──────────────────────────────────────────────┘
        ▼
┌──────────────────────────────────────────────────────┐
│  CAT 黄金链 (不变 · 业务真相)                          │
│  Context → RFQ → DFM(辟) → Quote → Commercial(牟)    │
│         → RAG(援: 本地+ragflow+SearXNG) → Verify(推止)│
└───────┬──────────────────────────────────────────────┘
        ▼ 输出三态交通灯
┌──────────────────────────────────────────────────────┐
│  L3 自治分流 (新增 · 油门分级)                         │
│  PASS+稳 → AUTO_DONE (写CRM, auto_completed=true)     │
│  HITL    → 人工待办队列 (eyes-on)                     │
│  BLOCKED → 澄清草稿 (待复核)                          │
└───────┬──────────────────────────────────────────────┘
        ▼
┌──────────────────────────────────────────────────────┐
│  Memory + Postmortem (不变 · 闭环)                    │
│  记结果偏差 → 反哺下次报价 (援的风险信号)             │
└──────────────────────────────────────────────────────┘
        全程: Guardrails(三段) · Tracer · Audit(SHA-256) · 铁律①锁定
```

---

## 五、落地拆解（5 个工作包，按依赖排序）

### WP1 · Autopilot Loop（发动机）— 核心，必做
- **新增** `services/autopilot.py`：守护进程
  - `loop_once()`：gmail.sync() → 扫 `data/mailbox` 新 `.eml`（按 meta.json 的 `context_id is None` 判新）→ 逐封调 `CATController.run()` → 写回 meta 的 `context_id / status`
  - 幂等：已处理的邮件不重复跑（meta.badges 去重）
  - 优雅降级：无凭据/IMAP 不可达 → 返回 error 不崩；本地 `data/mailbox` 已有信也能离线跑
- **新增** `scripts/start_autopilot.py`：`--interval 60 --once/--watch`
- **配置** `config/settings.yaml`：`autopilot.{enabled, interval_s, auto_done_policy}`
- **API**：`POST /v1/autopilot/run`（触发一轮）、`GET /v1/autopilot/status`

### WP2 · L3 自治分流策略（油门）— 核心，必做
- **新增** `services/autonomy.py`：纯函数 `classify_autonomy(verification, ctx, policy) -> {level, action}`
  - 输入现有 `verification` 结果 + context 风险信号 + policy 阈值
  - 输出 `AUTO_DONE / HITL_QUEUE / BLOCKED_REVIEW` + 理由
  - **绿灯条件全部确定性**：margin≥floor & 无多模态冲突 & 无护栏升级 & 非首次新客（可配）& schema 合法
  - 不改 `verification` 本身，只在其上叠加"是否可自动放行"判断
- **接线** `cat_controller.run()` 末尾：绿灯件自动 `crm.upsert/write` 并标 `auto_completed`；黄/红仅入队
- **策略可配**：`policy.yaml` 加 `autonomy.l3.{auto_done_enabled, require_known_customer, min_margin_pct}`

### WP3 · 外部传感器接入（6 个，可降级）
| 模块 | 文件 | 接入方式 | 降级 |
|------|------|---------|------|
| MinerU | `adapters/mineru_adapter.py` | 子进程调本地 `MinerU` 解析 PDF→markdown | 退回 pypdf |
| ragflow | `adapters/ragflow_adapter.py` | HTTP 调本地 ragflow `/v1/retrieval` | 退回本地词频 RAG |
| OmniVoice | `adapters/omnivoice_adapter.py` | HTTP/子进程，注册到 `model_router` ASR 角色 | 退回 funasr/MOCK |
| SearXNG | `adapters/searxng_adapter.py` | HTTP 调本地 `:8080` 元搜索→"联网证据" | 离线则跳过（援可空） |
| 21 技能 | `skills/` + `skill_registry` | 选高价值 6–8 个注册（见下），受 allow-list | 规则路由兜底 |
| DFM-Quote fleet | `adapters/fleet_adapter.py` | 作为 `calc_quote` 对照增强（非权威） | 退回确定性内核 |

**建议优先注册的外部技能**（与黄金链互补、不重复）：
`nl2cad`（自然语言→CAD）、`opc-quote-engine-v2`（报价引擎 v2 对照）、`dynamic-pricing`（动态定价）、`feasibility-checker`（可行性增强）、`quote-doc-generator`（报价文档生成）、`knowledge-querier`（知识查询）、`orchestrator`（编排器）、`step-factory`（STEP 生成）。

> 注：技能包源在 `C:\Users\<user>\Videos\skill\2026822\skills_extracted\skills\` 与 `UnionSkill-DFM-Quote-Agent-v1.0\`，将以**拷贝/软链**方式纳入 `skills/`，统一受现有 OpenShell 门禁。

### WP4 · 模块联动收口（让上下文全链路串联）
- Autopilot 把 `context_id` 回写邮件 meta（`mailbox_api` 7 区就能按信→上下文联动）
- 每轮跑完落 Trace + Audit + Postmortem 钩子（复用现有）
- WebUI 加"自治驾驶仪表盘"：当前模式（L1/L3）、本轮处理数、PASS/HITL/BLOCKED 分布、待办队列

### WP5 · 验证与自检
- **新增** `tests/test_autopilot.py`：本地 mailbox 喂样例信 → 断言绿灯自动 DONE、黄灯入队、红灯生成澄清、幂等不重复
- **新增** `tests/test_autonomy.py`：classify_autonomy 各边界
- **新增** `tests/test_external_adapters.py`：各外部工具不可达时显式降级不崩
- `一键自检.bat` 增 `autopilot --once` 离线冒烟

---

## 六、铁律守护检查（实现时强约束）

| 铁律 | 如何守住 |
|------|---------|
| ① LLM 不定最终价格 | L3 自治判断**纯确定性函数**；外部 fleet 只对照不权威 |
| ② 状态机是业务真相 | Autopilot 只触发 `run()`，不绕过状态机 |
| ③ context 全链路唯一 | 每封信→一个 context_id，回写 meta 联动 |
| ④ RAG 只提供证据不改事实 | MinerU/ragflow/SearXNG 全走"证据"通道，不进报价 |
| ⑤ 多模态冲突必升级 | autonomy 看到冲突恒返回 HITL，不放过 |
| ⑥ 本地是 Runtime 不是业务 | 外部工具都是传感器/证据源 |

---

## 七、风险与诚实边界

1. **Gmail 凭据**：IMAP 需应用专用密码，未配置则离线跑本地 `data/mailbox` 已有信（不阻断）。
2. **外部服务未启动**：MinerU/ragflow/SearXNG/OmniVoice 默认不假设在线，每个都探活→失败显式降级，绝不冒充。
3. **L3 自动放行范围**：默认保守——首次新客、低 margin、有冲突、命中护栏者**全部不自动放行**，仅老客+稳件绿灯才 AUTO_DONE。范围可在 `policy.yaml` 放宽（朝 L4 演进）。
4. **范围克制**：本方案不重写任何已就绪模块（CAT/内核/商业/记忆/平台），只**加发动机+传感器+油门**。

---

## 八、实施顺序与产出清单（确认后按此执行）

1. **WP1** `services/autopilot.py` + `scripts/start_autopilot.py` + settings 配置 + API
2. **WP2** `services/autonomy.py` + cat_controller 接线 + policy 配置
3. **WP3** 6 个 `adapters/*.py` + 技能注册（先接 MinerU/SearXNG/ragflow 三个证据类，再 OmniVoice/技能/fleet）
4. **WP4** mailbox meta 回写 + WebUI 仪表盘
5. **WP5** 3 个测试文件 + 自检脚本更新
6. 跑 `pytest` + `autopilot --once` 离线冒烟，出验收小结

**预计改动**：新增 ~9 文件（adapters×6 + autopilot + autonomy + start 脚本），改 ~4 文件（cat_controller / settings / policy / skill_registry / webui），不删不改已就绪内核。

---

## 待确认（确认后立即按 WP1→WP5 执行）

1. **L3 绿灯自动放行门槛**：是否同意"仅老客 + margin≥15% + 无冲突 + 无护栏告警 + schema 合法"才 AUTO_DONE？（更宽请说）
2. **自动发送回复**：本期 L3 **不自动发邮件**（只自动跑链+落CRM+生成草稿），发送留 L4/人工——同意吗？
3. **外部工具优先级**：6 个全接，还是先接证据三件套（MinerU + ragflow + SearXNG）？
4. **Gmail 轮询**：是否现在就配 IMAP 凭据跑真拉信？还是先离线喂 `data/mailbox` 样例验证？
5. **外部技能纳入方式**：拷贝进项目 `skills/`（自包含）还是软链到原路径（依赖外部目录）？
