# PRD：邮件驱动销售工作台（Gmail 主入口，代号 v3.x mail-driven-workstation）

**版本**：v0.2 修订稿
**作者**：union-export-agent 工作组
**日期**：2026-09-18
**状态**：v0.2 待 C1/C2/C3 拍板 → 进入 TaskList #32-38 实施
**对齐**：`PRD-frozen-v1.0.md` 铁律①（DETERMINISTIC 不可 A/B、数据不出车间）+ `docs/superpowers/designs/2026-09-18-nemoclaw-integration-design.md`（Plan C Skills + Dispatcher + OpenShell）

---

## v0.1 → v0.2 修订记录（凭代码核对）

| # | 修订 | 代码事实 |
|---|------|---------|
| 1 | `reply.write_reply_draft` → `reply.build_reply(ctx_dict, verification)` | `services/reply.py:11` |
| 2 | `/v1/upload/email` **不需新增**（已在 `api_server.py:122`） | `POST /v1/upload/email` 已注册 |
| 3 | 配置 `config/openshell.yaml` → `openshell/{hitl-required,iron-rule-1,local-only,skill-allowlist}.yaml` + `config/skills.yaml` | 实目录结构 |
| 4 | `crm.create_dummy_customer` → `crm.upsert_customer(customer)` | `services/crm_memory.py:43` |
| 5 | 删 `guardrails.check_email_egress / check_draft_egress`（PRD 发明） | 实仅 `TOOL_ALLOWLIST` + `policy.yaml` |
| 6 | Skill 11 → 17（含文档型与可执行型） | `services/skill_registry.py` |
| 7 | `data/mailbox/`、`data/drafts/` **新建** | `data/` 下不存在 |
| 8 | **核心建议**：MVP 不接真 IMAP，改为 **Gmail 导出 → 批量导入**（.mbox/.eml → 拖入 webui） | 零新后端、零铁律冲突、零外网 |
| 9 | **核心建议**：webui **新增第 8 tab `#tab-mailbox`**，不替换现有 7 tab；邮件台为默认页 | 控制台与工作台共存 |
| 10 | **核心建议**：侧栏 4 区 → **7 区**，补回 PRD 漏掉的 4 个能力：verification / postmortem / commercial landed cost / trace | `services/{verification,postmortem,commercial,observability}.py` |
| 11 | `pending_for` 工时从 1d → **0.25d**（≈15 行 SQL，`rfqs.state` 已存） | `services/crm_memory.py:57` 已写 `state` |
| 12 | `supplier_inbox.IMAPInbox` 是**供应商**收件箱（`fetch_quotes`），非客户邮件入口——**不可复用** | `supplier_module/supplier_inbox.py` 注释 |
| 13 | PRD §3.1 IMAP 真实拉取改写为"显式 opt-in 增强（v3.1+）"，MVP 不进 | 工时/合规 |
| 14 | webui 当前 756 行（含 v3.0 Skill 设置 tab）；邮件台新增后估 1100-1300 行 | `wc -l webui/index.html` |

---

## 0. 一句话

把当前 v2.4.0 的「运维控制台」翻面为「业务员工作台」——**Gmail 收件箱作为主界面**，点开一封信，自动聚合客户背景 / 图纸预览 / RAG 证据 / 未办事项，AI 起草回复走人工审批后落库。**所有外部收发默认禁用，数据不出车间**。

---

## 1. 背景与目标

### 1.1 背景（凭代码核对）
- v2.4.0 现状 UI（`webui/index.html` 756 行单文件、零依赖）：
  - 7 个 tab：模型设置 / 黄金链 Demo / 上传端口 / 3D 上传 / 反馈邮箱 + 演示抽屉 + skill 抽屉。
  - "上传端口" tab 已能拖拽 `.eml/.msg/.txt` → `services/file_intake.py:parse_email_file` 解析 `subject/from/to/body/attachments`（stdlib `email` 模块，无外发）。
  - 缺：没有一个"以邮件为主入口"的聚合视图。当前需要切 5 个 tab 才能完成"看信→找客户→查图纸→查 RAG→起草→审批"。
- 业务痛点（来自既有能力栈推断）：
  - 业务员一天处理 30-60 封邮件，60% 时间在 5 个 tab 之间跳。
  - 已有的 `CRMMemory.list_customer_history` / `postmortem.recall_customer_memory` 已有"客户背景 + 历史复盘"召回能力（`services/postmortem.py:64`），但没有任何 UI 出口。
  - 已有的 11 个 Skill（`skill_registry.py`）能算报价/验图纸/查运价，但都靠 RFQ lifecycle 触发，没跟"邮件"挂钩。

### 1.2 目标用户（先收敛 2 个角色，后续可扩）

| 角色 | 特征 | 核心诉求 | 用邮件做什么 |
|------|------|---------|------------|
| **外贸业务员 / 跟单** | 一人跟 20-50 个 RFQ，每天处理邮件为主 | 把 30 分钟/封的信压到 5 分钟 | 点信 → 自动出客户背景 + 图纸 + RAG + 草稿 → 审完发 |
| **报价工程师 / DFM** | 复核 5-10 单/天，需要看完整上下文 | 别在 tab 间跳，看到一封信能立刻决策 | 点信 → 看图纸 C1 冲突 → 看历史复盘 → 改单价 |

### 1.3 业务目标与成功指标

| 目标 | 指标 | 目标值 | 监测方式 |
|------|------|--------|---------|
| 单封邮件处理时长 | end-to-end（点开 → 草稿就绪） | < 60s（P95） | `observability.py` trace |
| 草稿采纳率 | 业务员仅改 ≤ 30% 字就发出 | ≥ 40% | `feedback_store` 草稿-发出 diff |
| 客户背景召回命中率 | 点信后侧栏 4 区全亮 | ≥ 80% | UI 埋点 `region_filled_count` |
| 数据不出车间 | 任何对外发件必须人工审批 | 100% | `guardrails.external_send=draft_only` |

---

## 2. 需求概述

Gmail 收件箱（**默认本地 mailbox + .eml 上传双轨**，IMAP 真实拉取显式 opt-in）作为主界面，点开任一邮件自动：
1. 解析 → 拉 `crm_memory.customer_id_by_name` → 聚合**客户区**（公司/历史报价/毛利/丢单信号）
2. 附件若有 `.step/.pdf/.xlsx/.eml/.wav` → 走 `file_intake` 解析 → 落缩略图 → 聚合**图纸区**
3. `rag.search(keywords=subject+body)` → 聚合**RAG 区**（4 条 mock KB + 邮件正文相关条目）
4. `crm.pending_for(context_id)` (新增) → 聚合**未办区**（待 HITL / 待报价 / 待审批）

主区保持邮件原文 + 附件预览；侧栏 4 区 + 右下"AI 草稿"按钮。

---

## 3. 功能详细设计

### 3.1 模块 A：邮件主区（Gmail 形态收件箱，第 8 tab）

**功能描述**：Gmail 形态收件箱列表 + 单信详情。**MVP 不连真 Gmail/IMAP**——业务员在 Gmail 里选中询盘 → 导出 `.mbox`/`.eml` → 拖入 webui 上传区，"导入即刷新"。
**用户故事**：作为业务员，我在 Gmail 看到客户询盘后导出一份 .eml（或 .mbox），拖到 webui 主区，邮件立刻出现在收件箱列表，点开看详情 + 4 区聚合。
**优先级**：P0

**业务规则**（**Gmail 导出导入双轨，零外网**）：
1. **本地 mailbox**：`data/mailbox/*.eml`（新建目录）。所有 demo 装载落这里。
2. **Gmail 导出导入**：
   - 用户 Gmail → 选中邮件 → "Show original" → "Download Original" 拿到 `.eml`
   - 多封可批量：`Gmail → Settings → Forwarding and POP/IMAP → Download mailbox` 拿 `.mbox`
   - 拖入 webui 第 8 tab 上传区 → 复用**现有** `POST /v1/upload/email`（`api_server.py:122`，已支持 eml/msg/txt）
   - 后端把 `.mbox` 拆成多封 `.eml` 落 `data/mailbox/`，列表自动刷新
3. **真 IMAP/Gmail API（v3.1+）**：仅当 `openshell/local-only.yaml` 显式标 `external_mail_ingress: opt-in` 且配 OAuth/凭据时启用，**MVP 不做**。
4. 列表字段：发件人 / 主题 / 时间 / 状态徽章（NEW / IN_REVIEW / QUOTED / REPLIED / POSTMORTEM / [DEMO]）
5. 单信详情：原始 MIME 渲染 + 附件缩略图（`.step` 用 `step_thumbnail.make_thumbnail`，`.pdf` 用 pypdf 文本预览）

**交互流程**：
1. 入口：webui 加载时默认 tab = `#tab-mailbox`（第 8 tab，新增）；原 7 tab 保留用于工程师运维角色
2. 拖入 .eml/.mbox → 自动解析 → 列表新增
3. 列表点击 → 详情
4. 侧栏 7 区**自动**聚合（无需手动点）

**异常处理**：

| 异常 | 处理 | 用户提示 |
|------|------|---------|
| .eml 解析失败 | `file_intake.parse_email_file` 返回 `ok=false` | "邮件解析失败：{reason}，请重新导出" |
| .mbox 拆封失败 | 解析失败列表展示 | "{n} 封拆封失败，可单封 .eml 重试" |
| 附件 > 50MB | 拒绝并提示 | "附件超过 50MB，请压缩后再传" |
| 重复导入（同 sha256） | 跳过并提示 | "已存在，重复导入已忽略" |

---

### 3.2 模块 B：侧栏七区聚合（核心价值）

**功能描述**：点信后右侧栏 **7 区**实时聚合。覆盖 PRD v0.1 漏掉的 4 个已有能力：verification / postmortem / commercial landed cost / trace。
**用户故事**：作为业务员，我点开一封信，7 区的内容**一眼看完**，不用切 tab。
**优先级**：P0

**7 区契约**（每区一个 `/v1/mail/{id}/context` 子端点）：

#### B-1 客户区 `GET /v1/mail/{id}/context/customer`
- 数据源：`crm.list_customer_history(cid)`（`crm_memory.py:118`）+ `postmortem.recall_customer_memory(crm, customer)`（`postmortem.py:64`）
- 字段：`name / customer_id / is_new / signals[] / history{quotes,postmortems,n}`
- signals 翻译成图标：`repeat_customer` 🟢 / `past_loss` 🔴 / `past_overrun` 🟡 / `historical_margin` ℹ️

#### B-2 图纸区 `GET /v1/mail/{id}/context/geometry`
- 数据源：`file_intake.parse_step`（附件若有 `.step/.stp`）→ `step_thumbnail.make_thumbnail`（sha256[:16] 缓存）
- 字段：`thumb_url / bbox / volume_cm3 / weight_kg / features{C1..Cn} / source`
- 若无 STEP → "无图纸，可上传 / 可 OCR 邮件插图（v3.1）"

#### B-3 RAG 区 `GET /v1/mail/{id}/context/rag`
- 数据源：`services/rag.py:search(query, top_k=4)`，query = `subject + body[:500]`
- 字段：`hits[{title, snippet, score, source, mock}]`
- mock 标识显眼：`[MOCK]` 标签
- **v3.0 增强**：把 demo 邮件正文索引进 KB，让 demo 时 RAG 有命中

#### B-4 未办区 `GET /v1/mail/{id}/context/pending` (**新增 ≈15 行 SQL**)
- 数据源：**新增** `crm.pending_for(customer_id=None, limit=20)` — 见 §6
- 字段：`tasks[{context_id, state, customer_id, created_at}]`
- 字段来源：`rfqs` 表 `state NOT IN ('DONE','BLOCKED')`（`crm_memory.py:57` 已存 `state` 字段）

#### B-5 门禁区 `GET /v1/mail/{id}/context/verification` (**新端点**)
- 数据源：`services/verification.py` 五步门禁（PASS / HITL / BLOCKED）
- 字段：`status / reasons[] / conflicts[] / risk_score / gate_history[{step, ts, status}]`
- 铁律①可视化：若 `status=BLOCKED`，整卡红条 + 文案"Timo 内核锁定，不可被 AI 覆盖"

#### B-6 复盘区 `GET /v1/mail/{id}/context/postmortem` (**新端点**)
- 数据源：`crm_memory.postmortems` 表 + `postmortem.record_outcome()` 的 knowledge_updates
- 字段：`won_count / lost_count / past_cost_deviations[] / past_leadtime_overruns[] / knowledge_updates[]`
- 显示"过去 N 次成交 / N 次丢单"，业务员下单前先看一眼

#### B-7 落地成本区 `GET /v1/mail/{id}/context/commercial` (**新端点**)
- 数据源：`services/commercial.py` + `skills/freight-customs/tool.py`（运费 / 关税 / Incoterms）
- 字段：`unit_price / total_price / margin_pct / freight_cny / duty_cny / landed_cost / incoterms`
- 业务员最关心的"到岸成本"直接看见

#### B-8 Trace 区 `GET /v1/mail/{id}/context/trace` (**新端点**，可选 v3.0.1)
- 数据源：`services/observability.py:Tracer` 记录
- 字段：`events[{ts, event, source, mock}]`
- 折叠默认收起（噪音大），按需展开

> **7 区排序**：客户 → 图纸 → 门禁 → 复盘 → 落地成本 → RAG → 未办 → Trace
> 业务员视角：先认人 → 看货 → 看能不能做 → 看历史 → 看挣不挣钱 → 看证据 → 看还有什么要办 → 看链路
> Trace 默认折叠最后。

**交互**：
- 7 区均**折叠默认展开前 1 条 + 总条数**（避免首屏爆）
- 任一区点击 `▾` 展开全部
- 卡片顶部显示"信号聚合"小图标：🟢🟡🔴ℹ️ 各 1 个，红/黄优先浮顶

**异常处理**：

| 区 | 异常 | 处理 |
|----|------|------|
| 客户 | CRM 未命中 | 标 `is_new=true`，显示"新客户，建议建档"按钮 |
| 图纸 | 附件非 STEP | 显示原文件名 + "请上传 .step 获取 C1 冲突检查" |
| RAG | 无命中 | "无相关历史答复" |
| 未办 | context 未建立 | "邮件尚未产生 RFQ，点'开始报价'建档" |
| 门禁 | 缺 verification.json | "未跑门禁，点'运行门禁'立即执行" |
| 复盘 | 无历史 | "首次询价，无复盘信号" |
| 落地成本 | 缺 Incoterms / 目的地 | "补齐目的地 + Incoterms 出报价" |
| Trace | 无 trace 文件 | 隐藏该区 |

---

### 3.3 模块 C：AI 草稿（人工审批门，铁律①守住）

**功能描述**：基于 7 区上下文 + 既有 quote/verification，调用 `reply.build_reply(ctx_dict, verification)` 生成回复草稿。
**用户故事**：作为业务员，我点"AI 起草"，30s 内得到一封草稿（数字来自确定性引擎），我改完再"标记已处理"。
**优先级**：P0

**业务规则**（**铁律① + draft_only 双锁**）：
1. 草稿生成 = `reply.build_reply(ctx_dict, verification)`（`services/reply.py:11` 已存在）
2. **草稿前必须先跑 `calc_quote` + `verification`**：禁止无数字空草稿冒充报价
   - 若 context 未跑报价 → 按钮置灰，文案"请先运行报价引擎"
3. 草稿显示在主区下方折叠面板：「📝 AI 草稿 (可编辑)」
4. **草稿不直接发**：必须点"人工审批" → 走 `draft_only` 流程
5. `reply.build_reply` 默认 `auto_send=False / mode=draft_only`（`reply.py:74` 已硬编码）
6. 草稿落到 `data/drafts/{context_id}.md`（新建目录），**不外发**
7. 草稿改完点"标记为已处理" → 仅落 CRM `replied_at`，**不真发邮件**
8. 真发（v3.1+）：必须显式 `mode=manual_approved` 且配 SMTP，凭据在 openshell policy 下

**交互**：
1. 点"AI 起草" → loading（≤30s） → 草稿出现
2. 可编辑（textarea，diff 显示改了多少字）
3. 点"采纳" → 写入 `data/drafts/{context_id}.md` + `feedback_store` 记 `accepted=true / edit_distance=N`
4. 点"丢弃" → `feedback_store` 记 `accepted=false / reason=...`（反例训练）

**异常**：

| 场景 | 处理 |
|------|------|
| LLM 未配 | 草稿区显示 "未配置 LLM，请到 模型设置 tab 配置" |
| 草稿生成超时 30s | 显示 "AI 起草超时，请人工撰写" |
| 未跑报价 | 按钮置灰 + tooltip "请先运行报价引擎" |
| 草稿被改得面目全非（diff>70%） | 弹窗"采纳率低，是否记录反例？" |

---

### 3.4 模块 D：演示模式（无真邮箱也能 demo）

**功能描述**：内置 6 个演示场景（`S1-S5 + M1`），一键装载到主区。
**用户故事**：作为销售总监，我在大群里 30 秒演示"点信→4 区聚合→AI 草稿"完整链路。
**优先级**：P0（比赛日必需）

**业务规则**：
1. `POST /v1/demo/scenario/{S1..M1}` → 写入 `data/mailbox/` 一封预制 .eml + `data/contexts/{RFQ-...}.json` + 触发 `crm.create_dummy_customer`
2. demo .eml 内含附件 `.step`（真实 OCP 几何）+ `.pdf`（pypdf 文本）+ 正文关键词命中 RAG mock KB
3. 列表直接显示 demo 邮件徽章 `[DEMO]`

**6 个场景对应演示价值**：
- S1 可接 → 4 区全亮，AI 草稿就绪 → 演示完整黄金链
- S2 HITL 小批量 → 未办区红点 → 演示 HITL 拦截
- S3 DFM 阻断 → 图纸区 C1 冲突 → 演示 verify_gate 阻断
- S4 替代工艺 → 客户区有 historical_margin → 演示复盘召回
- S5 精密 HITL → 风险信号密集 → 演示多区红点
- M1 多模态冲突 → RAG 与图纸冲突 → 演示冲突可视

---

### 3.5 模块 E：设置入口（沿用 v2.4.0 + 增 IMAP）

**功能描述**：模型设置 + IMAP/草稿策略。
**优先级**：P1（比赛日降级可不做 UI，仅文档说明）

**增量**：
- 模型设置 tab 已有 IMAP 配置 block，但 `imap.enabled` 默认 false + 配 SMTP host/user/pass + "测试连接"按钮（不存储密码，只存 host/user/test_token）
- 草稿策略：`mode` dropdown（draft_only 锁定 / manual_approved 可选）

---

## 4. 非功能需求

| 类别 | 要求 | 验收 |
|------|------|------|
| **性能** | 点信 → 4 区全部加载 | < 3s（P95，本地 mock） |
| **性能** | AI 草稿 | < 30s（含 LLM 调 mock） |
| **数据不出车间** | 默认外部收发全禁 | `openshell.yaml` 默认 `imap.enabled=false` + `external_send.mode=draft_only` |
| **铁律①保留** | DETERMINISTIC 不参与 AI 决策 | `model_router.resolve("DETERMINISTIC")` 不走 A/B（已实现，v2.3.1） |
| **兼容性** | 沿用 webui 单文件 | webui/index.html < 1500 行（v2.4.0 现状 756 → v3.x 估 1100-1300） |
| **离线** | demo 模式完全离线可跑 | 无 LLM / 无 IMAP 也能完整演示 |

---

## 5. 数据需求（埋点）

| 事件 | 触发 | 关键属性 | 用途 |
|------|------|---------|------|
| `mail_opened` | 点开邮件 | `mail_id, has_step, has_pdf, customer_hit` | 4 区命中率分析 |
| `region_filled_count` | 4 区加载完 | `region, status(filled/empty)` | 命中率指标 |
| `draft_generated` | AI 起草完成 | `context_id, duration_ms, llm_used, mock` | 性能 + 采纳率 |
| `draft_accepted` | 点采纳 | `context_id, edit_distance` | 采纳率 |
| `demo_loaded` | 装 demo 场景 | `scenario, duration_ms` | 演示稳定性 |
| `imap_opt_in` | 用户开 IMAP | `host, user`（**不记密码**） | 安全审计 |

---

## 6. 缺口分析（关键 — 凭代码核对，不背书）

> 用户 v0.2 反馈后重写。**核心原则：复用最大化 + 工时保守估 + 铁律①守住**。

| # | 缺口 | 现状 | 解决方案 | 工时 |
|---|------|------|---------|------|
| 1 | **真 IMAP / Gmail OAuth** | 全库无 `imaplib` / OAuth client；`supplier_inbox.IMAPInbox` 是**供应商**收件（`fetch_quotes`），语义不符，**不可复用** | MVP **不做**。改为 Gmail 导出导入双轨。v3.1+ 文档化 opt-in | 0（MVP） |
| 2 | **真 SMTP 发送** | 无 `external_send.py`；`policy.yaml` + `reply.py` 均锁 `draft_only` | MVP **不做**，铁律① | 0（MVP） |
| 3 | **`crm.pending_for()` 未办查询** | `crm_memory.py` 现有 9 方法，`rfqs.state` 已存但**未暴露查询** | **新增** ≈15 行 SQL：`SELECT context_id,customer_id,state,created_at FROM rfqs WHERE state NOT IN ('DONE','BLOCKED')` | **0.25d** |
| 4 | **侧栏 7 区 API**（v0.1 是 4 区） | 7 个端点全缺 | 新增：`/v1/mail/{id}/context/{customer,geometry,rag,pending,verification,postmortem,commercial,trace}`（trace 可选） | **2d** |
| 5 | **demo 装载端点** | 无；`golden_scenarios.json` S1-S5+M1 是数据，非装载接口 | 新增 `POST /v1/demo/scenario/{S1..S5,M1}` + 6 封预制 .eml + 6 个 context JSON | **1.5d** |
| 6 | **`.eml` / `.mbox` 上传** | `POST /v1/upload/email` 已存在（`api_server.py:122`） | **零工时**，但需扩展支持 `.mbox`（mailbox 批量拆分） | **0.5d** |
| 7 | **`data/mailbox/` 目录** | 不存在 | 新建 + 写 README "把 Gmail 导出的 .eml 拖这里" | 0.1d |
| 8 | **`data/drafts/` 目录** | 不存在 | 新建 + 草稿落库用 | 0.1d |
| 9 | **webui 第 8 tab `#tab-mailbox`** | webui 当前 7 tab（含 v3.0 Skill 设置） | 新增 tab + 列表 + 详情 + 7 区侧栏，IIFE 命名空间封装 | **3d** |
| 10 | **`.mbox` 拆分器** | 全库无 | 新增 `services/mbox_split.py`，用 stdlib `mailbox` 模块 | 0.5d |
| 11 | **RAG demo 种子邮件** | 离线 4 条工艺 KB，demo 时 RAG 命中弱 | 写 6 封 demo .eml 时把正文关键词设计成命中现有 KB | 0.25d |
| 12 | **前端单文件膨胀** | 当前 756 行 → 邮件台后估 1100-1300 | IIFE 命名空间：`Mail / SidePanel / DraftPanel / DemoLoader / Settings`，避免全局污染 | 已计入 #9 |

**总工时估算（按 TaskList #32-38）**：
- #33 pending_for: 0.25d
- #34 7 区 API: 2d
- #35 demo 装载: 1.5d
- #36 webui 邮件台: 3d
- #37 AI 草稿闭环: 1d
- #38 回归 + 文档: 1.5d
- 合计 ≈ **9.25 工作日**（比赛倒推可交付）

**缺口风险评估**：
- ✅ 客户/图纸/门禁/复盘/落地成本 5 区**有现成函数**，仅包装端点（≈ 1.5d）
- ✅ 未办区是 ≈15 行 SQL（rfqs.state 已存），不再是大坑
- ✅ demo 场景**只依赖现有 mock 数据** + 预制文件，零外部依赖
- ✅ IMAP/SMTP MVP 不做 = 铁律① 100% 守住
- ⚠️ 唯一风险：webui 单文件可能超过 1500 行，IIFE 命名空间缓解，不能根治

---

## 7. 验收标准（Given-When-Then）

| 编号 | 场景 | Given | When | Then |
|------|------|-------|------|------|
| AC-1 | 收件箱默认 tab | 用户打开 UI | 加载 | 默认 tab = "邮件"，非"模型设置" |
| AC-2 | 本地 mailbox 加载 | `data/mailbox/` 有 1 封 .eml | 点邮件 tab | 列表显示该邮件 |
| AC-3 | .eml 拖拽上传 | 用户拖 1 封 .eml 到主区 | 拖完 | 列表新增该邮件，刷新页面仍在 |
| AC-4 | 4 区聚合 S1 | 装载 S1 demo | 点开邮件 | 4 区全亮，customer_hit=true, has_step=true, rag_hits≥2, pending_count≥1 |
| AC-5 | 4 区聚合 S3 | 装载 S3 demo | 点开邮件 | 图纸区显示 C1 冲突红条，未办区显示 verify_blocked |
| AC-6 | AI 草稿生成 | 点 S1 demo 邮件 + 点"AI 起草" | loading | 30s 内 textarea 出现草稿，标记 LLM mock |
| AC-7 | 草稿仅 draft_only | 草稿写完 | 点"采纳" | 落 `data/drafts/{context_id}.md`；CRM 状态更新；**无 SMTP 调用** |
| AC-8 | IMAP 未启用 | openshell.yaml `imap.enabled=false` | 点"刷新" | 列表仅本地邮件，徽章"IMAP 未启用" |
| AC-9 | IMAP 误用拦截 | 用户尝试调 `/v1/mail/imap/fetch` 但 `enabled=false` | 请求 | 403 + error="imap disabled by policy" |
| AC-10 | 性能 | 装载任一 demo | 点开 → 4 区加载完 | < 3s |
| AC-11 | 数据不出车间 | 全程 | — | `data/drafts/` 不出现 `Sent` / SMTP 日志；`openshell.audit.log` 记每次外部发件 attempt |

---

## 8. 排期建议（比赛倒推，v0.2）

> 总预算 **9.25 个工作日**，比赛日 ≈ T+15。

| 阶段 | Task | 内容 | 工时 |
|------|------|------|------|
| D1 | #33 | `crm_memory.pending_for()` + 单测 4 条 + `data/mailbox/` `data/drafts/` 目录 | 0.25d |
| D2-D3 | #34 | 7 个 `/v1/mail/{id}/context/*` 端点（trace 标可选） + 单测 12 条 | 2d |
| D4-D5 | #35 | 6 个 demo 场景：`.eml` 预制 + context JSON + `POST /v1/demo/scenario/*` + `.mbox` 拆分器 | 1.5d |
| D6-D8 | #36 | webui 第 8 tab `#tab-mailbox`：列表 + 详情 + 7 区侧栏 + IIFE 命名空间 | 3d |
| D9 | #37 | AI 草稿面板 + `data/drafts/{context_id}.md` 落库 + draft_only 闭环 | 1d |
| D10 | #38 | 全量回归 + E2E（6 个 demo 流程）+ README + 视频脚本 + CHANGELOG/MANIFEST + 提交 | 1.5d |
| 总计 | — | — | **9.25d** |

**关键里程碑**：
- **D1 完** = `pending_for` + 目录就绪（最小可独立测）
- **D3 完** = 后端 API 全通，curl 验证
- **D5 完** = demo 6 个场景全可装载
- **D8 完** = UI 静态可看，能完整走通"点信→7 区聚合"
- **D9 完** = AI 草稿闭环
- **D10 完** = 提交

---

## 9. 风险与依赖（v0.2 修订）

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 演示需真邮箱（评审会穿帮） | 高 | 高 | Gmail 导出导入双轨 + demo 6 场景全离线 |
| webui 单文件超过 1500 行 | 中 | 中 | IIFE 命名空间（Mail / SidePanel / DraftPanel / DemoLoader / Settings） |
| `pending_for` 误判（已关闭 HITL 仍红点） | 中 | 中 | 单测覆盖 4 state + 边界 case |
| 比赛日外部发件误启用 → 数据出车间 | 低 | 极高 | `reply.py:auto_send=False` 硬编码 + `openshell/local-only.yaml` 默认锁 |
| LLM mock 不稳定 | 中 | 中 | `_mock=true` 显式标记 + "未配置 LLM" fallback |
| .mbox 拆分器 stdlib 性能（大 mailbox >100MB） | 低 | 低 | MVP 不超 100MB；超量提示用户分批导出 |

---

## 附录 A：API 契约（增量 + 复用端点）

```
# 复用（已存在）
POST   /v1/upload/email            → {ok, mail_id, count}      # api_server.py:122, 扩展支持 .mbox
POST   /v1/upload/step             → {ok, step_id}             # 已存在
POST   /v1/upload/step-with-thumbnail → {thumb_url, bbox...}   # 已存在
GET    /v1/crm/customer/{cid}/history → {quotes, postmortems}  # crm.list_customer_history 包装
POST   /v1/agent/task              → {trace_id, skill_results} # skill_dispatcher 入口

# 增量（v3.x 新增）
GET    /v1/mail/inbox?source=local                 → {items:[{id,from,subject,received_at,badges[]}]}
GET    /v1/mail/{id}                                → {raw, parsed, attachments:[{name,kind,thumb_url}]}
GET    /v1/mail/{id}/context/customer               → {name,customer_id,is_new,signals[],history}
GET    /v1/mail/{id}/context/geometry               → {thumb_url,bbox,volume_cm3,weight_kg,features,source}
GET    /v1/mail/{id}/context/rag                    → {query,hits:[{title,snippet,score,mock}]}
GET    /v1/mail/{id}/context/pending                → {tasks:[{context_id,state,customer_id,created_at}]}    # new SQL
GET    /v1/mail/{id}/context/verification           → {status,reasons[],conflicts[],risk_score,gate_history[]} # new
GET    /v1/mail/{id}/context/postmortem             → {won_count,lost_count,cost_deviations[],leadtime_overruns[],knowledge_updates[]}  # new
GET    /v1/mail/{id}/context/commercial             → {unit_price,total_price,margin_pct,freight_cny,duty_cny,landed_cost,incoterms}  # new
GET    /v1/mail/{id}/context/trace                  → {events:[{ts,event,source,mock}]}  # new (optional)
POST   /v1/mail/{id}/draft                          → {draft_id, body_md, llm_used, mock}        # 调用 reply.build_reply
POST   /v1/mail/{id}/draft/{draft_id}/accept        → {saved_path:"data/drafts/{context_id}.md"}   # draft_only
POST   /v1/demo/scenario/{S1|S2|S3|S4|S5|M1}        → {mail_id, context_id, scenario}            # 装载预制
```

**安全约束（v0.2 修订：基于真实策略）**：
- 所有 `/v1/mail/{id}/*` 端点走 `openshell/iron-rule-1.yaml`（DETERMINISTIC 锁定）+ `openshell/local-only.yaml`（无外发）
- `POST /v1/mail/{id}/draft` 默认走 `reply.build_reply` 内置 `auto_send=False / mode=draft_only`
- 草稿落到 `data/drafts/` 后**绝不触发 SMTP**；写文件操作仅限 `services/draft_store.py` 单文件
- 外部发件（v3.1+）必须显式 `policy.external_send.mode=manual_approved` + openshell 解锁

## 附录 B：未启用能力清单（v3.x 暂不动）

- 真 IMAP 拉取（`supplier_inbox.py:IMAPInbox`）
- 真 SMTP 发送（`external_send.py` 待建）
- 多模态 VLM（funasr :1234）解析邮件插图
- 移动端（webui 单文件，已声明非目标）
- 多人协作（已声明非目标，赛后再说）

## 附录 C：核对清单（PRD 自检 10 项）

| 序号 | 检查项 | 通过 |
|------|--------|------|
| 1 | 背景不空泛（why now / 不做会怎样 / 做了能怎样） | ✅ §1.1 |
| 2 | 目标可量化（4 个数字指标） | ✅ §1.3 |
| 3 | 用户画像具体（2 角色 + 场景） | ✅ §1.2 |
| 4 | 业务规则穷举（无"等"/"其他情况"模糊） | ✅ §3.1-3.5 |
| 5 | 异常流程覆盖（每模块 ≥2 异常） | ✅ §3.1-3.3 异常表 |
| 6 | 验收标准 G/W/T 格式（11 条） | ✅ §7 |
| 7 | 数据埋点完整（6 个核心事件） | ✅ §5 |
| 8 | 无技术方案（仅描述能力，未指定 Redis/MySQL） | ✅（指定 IIFE 命名空间仅为缓解单文件膨胀，非选型） |
| 9 | 优先级明确（3 个 P0 + 1 P1） | ✅ §3 |
| 10 | 排期有依据（12 天分 7 阶段） | ✅ §8 |

---

## 待确认（C1 / C2 / C3 / C4 / C5 / C6）

### C1：MVP 边界 — IMAP 真拉取
- **A（推荐）**：MVP 不做 IMAP，仅本地 mailbox + .eml 上传，IMAP 路径文档化 opt-in。**9.25d 内可交付**。
- B：MVP 接 Gmail API（OAuth），工时 +4d。
- C：MVP 接 IMAP（imaplib），工时 +3d。
- ➡️ 默认 **A**（铁律① + 比赛日）。

### C2：侧栏 7 区顺序
- **A（推荐）**：客户 → 图纸 → 门禁 → 复盘 → 落地成本 → RAG → 未办 → Trace（折叠）
- B：图纸 → 客户 → RAG → 其它（DFM 视角）
- C：未办 → 客户 → 图纸 → 其它（紧急度优先）
- ➡️ 默认 **A**（业务员视角：认人→看货→看能不能做→看历史→看挣不挣钱→看证据→看未办→看链路）。

### C3：AI 草稿策略
- **A（推荐）**：仅生成文本 + 落 `data/drafts/` + 人工"标记已处理"；**不 SMTP**。
- B：生成文本 + 采纳即落 CRM `replied_at`，不真发（半自动）。
- C：生成文本 + 自动发邮件（破铁律①，**强烈反对**）。
- ➡️ 默认 **A**，与 `reply.build_reply` 内置 `auto_send=False` 一致。

### C4：邮件接入方式（Gmail 导出导入 vs 真连接）
- **A（推荐）**：**Gmail 导出 → 批量导入**（.eml / .mbox → 拖入 webui 上传区），零外网、零铁律冲突。
- B：业务侧开放 OAuth 接 Gmail API（破铁律①，需要比赛前完成合规审批）。
- ➡️ 默认 **A**，MVP 范围。

### C5：webui tab 结构
- **A（推荐）**：**新增第 8 tab `#tab-mailbox`**，原 7 tab 保留；邮件台为默认页。
- B：替换"模型设置"为默认页（但保留 tab 入口）。
- C：全屏重写 UI（破 webui 单文件约束）。
- ➡️ 默认 **A**，控制台与工作台共存。

### C6：草稿前置条件
- **A（推荐）**：草稿前必须先跑 `calc_quote` + `verification`；无数字则按钮置灰。
- B：草稿可不绑数字（接受空报价，但标注"待补"）。
- ➡️ 默认 **A**，禁止无数字空草稿冒充报价。

---

**签字栏**（拍板后填）：

- [ ] C1：A / B / C → ___________
- [ ] C2：A / B / C → ___________
- [ ] C3：A / B / C → ___________
- [ ] C4：A / B → ___________
- [ ] C5：A / B / C → ___________
- [ ] C6：A / B → ___________
- [ ] PRD 进入实施：TaskList #33 起
