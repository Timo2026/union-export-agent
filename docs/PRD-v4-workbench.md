# PRD · v4.0.0 Workbench — 三栏智能体协作台

**方案代号**：`UEA-NCPAAI-v4.0.0-workbench` · **日期**：2026-09-18
**对齐**：NCP-AAI 工业 AI 协议 · NemoClaw 混合架构（Skills + Dispatcher + OpenShell） · 冻结架构 v1.0
**前置版本**：v3.0.1（417 passed · 8 tab · Gmail IMAP · HITL · V12 仪表板 · 7 区聚合）
**变更一句话**：把"按钮驱动 7 区堆叠"升级为"对话驱动三栏协作"，能力封装为可复用 Agent Skills。

---

## 0. 为什么做这个版本（用户原话 + 现状痛点）

> 用户原话：**"目前人机交互效果太差了"**；要求"左边邮件、中间预览、右边流程/客户信息 rag 对话"；"能力都封装成 agent skills，交付"。

| 现状痛点（凭代码核对）                                                                 | 来源                                                                  | 严重度 |
|---------------------------------------------------------------------------------------|-----------------------------------------------------------------------|--------|
| 右栏是**只读 region 卡片堆叠**，不是对话，无输入框、无流式响应、无上下文记忆、无追问          | `webui/index.html:1288 buildRegionCard` · `services/mailbox_api.py`   | 高     |
| `services/rag.py` 是 1.5 KB 薄封装，无 chat / 无 conversational retrieval                | `services/rag.py`                                                     | 高     |
| `/v1/demo/scenario/{S1-S5,M1}` 端点**完全没实现**，6 个 Demo 按钮全是死的                  | `webui/index.html:1380` → 后端路由缺失                                  | 高     |
| 跨线程 SQLite bug：`sqlite3.ProgrammingError: created in thread X used in thread Y`    | `data/api_8900.log` · `services/crm_memory.py:44`                    | 高     |
| `crm_memory.list_customer_history` 的 `postmortems` 没按 cid 过滤 → 误召回                 | `services/crm_memory.py:130`                                          | 中     |
| 10 个 Skill 全部已封装 `tool.py`，但默认 tab=mailbox，**没有任何 chat UI 调用 dispatcher**  | `webui/index.html` · `services/skill_dispatcher.py`                   | 中     |
| 三个 panel 之间无交互联动：右栏 region 不能被引用为左邮件的批注/草稿输入                        | 整个 UI                                                                | 中     |
| LLM Planner 离线时静默降级，用户看不到"走的是规则路由而非 LLM"                                  | `services/llm_planner.py` · UI 无角标                                   | 低     |

---

## 1. 目标 / 非目标

### 1.1 目标 (v4.0.0)
- **三栏 IA**：左 Inbox · 中 Inspector(5 tabs) · 右 Chat + Skill Console；1080p 单屏可达。
- **对话驱动**：右栏 Chat 输入自然语言 → 后端 `chat_understand → rag_recall → context_lookup → skill_dispatch → cite_evidence → suggest_reply` 流水线 → Agent bubble 渲染 + skill badge + cite chip + trace 折叠。
- **能力全部封装为 Agent Skills**：复用 9 + 新增 8 = **17 个**；每个 skill 都有 SKILL.md frontmatter + `tool.py:run(ctx, **kwargs)`，由 `skills/_runtime.py:discover()` 自动注册。
- **跨栏联动**：点左邮件 → 中栏加载 + 右栏自动 bind context；右栏调用 skill → 中栏相应 tab 高亮 + 草稿/审批自动激活。
- **铁律全部可视化**：iron-rule-1 sha16 锁图标 + 篡改拦截红 banner + OpenShell 4 策略状态 + 审计尾巴 + 离线降级角标。
- **零发明后端**：复用现有 dispatcher / openshell / mailbox_api / verification / reply / crm_memory / rag / postmortem；只在 `services/chat_api.py` 新增 5 个端点 + 在 `services/chat/` 新增 4 个内部模块 + 在 `skills/` 新增 8 个 skill 目录。

### 1.2 非目标（明确不做）
- ❌ Gmail SMTP 自动发信（铁律① draft_only + IMAP 默认 disabled）
- ❌ 邮件独立状态机 / Kanban 拖拽（与 RFQ 状态机冲突）
- ❌ supplier_module 履约 UI 入口（后端有，UI 不接）
- ❌ 真 OAuth 流程（保留 App Password 默认禁）
- ❌ 多用户协作 / 权限分级
- ❌ 用真 NIM / NeMo Fabric（无 GPU，留 P9 Post-MVP）

---

## 2. 信息架构 — 三栏布局

### 2.1 栅格（CSS Grid）

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Topbar: tabs + Workbench 子工具条 (preset / reset / 🎙 voice)                │
├──────────────┬─────────────────────────────────────┬─────────────────────────┤
│  左 26%       │  中 42%                              │  右 32%                 │
│  Inbox        │  Inspector (5 tabs)                  │  Chat + Skill Console  │
│  min 280px    │  min 520px                           │  min 380px              │
│              │                                     │                         │
│  · 搜索框     │  [Mail][Draft][Hist][Approval][HITL]│  · Bind Context pill    │
│  · 状态筛选   │  ─────────────────────────────────  │  · Chat thread          │
│  · 邮件列表   │  <tab-content>                       │  · Skill Console 切换   │
│  · 选中状态栏 │                                     │  · 输入框 + 按钮         │
└──────────────┴─────────────────────────────────────┴─────────────────────────┘
                  Footer statusbar: engine · API · LLM · dispatcher · audit · 🔒
```

```css
.wb-shell{ display:grid; grid-template-columns:minmax(280px,26%) minmax(520px,42%) minmax(380px,32%); height:calc(100vh - 56px - 28px); }
@media (max-width:1280px){ .wb-shell{ grid-template-columns:240px 1fr 320px; } }
@media (max-width:960px){ .wb-shell{ grid-template-columns:1fr; grid-auto-rows:auto; } }
```

### 2.2 各栏内容

#### 左栏 — Inbox
- 工具条：搜索框 (subject/from 实时) · 状态下拉 (新/HITL/BLOCKED/PASS) · ↻ 刷新 · ⬆ 上传 .eml
- 列表项：`.mail-item` + 三枚徽标 `🔒` (quote 锁存在) / `🛡 HITL` / `🚫 BLOCKED` / `✅ PASS` / `💬 N` (未读对话轮)
- 跨栏联动：点击 → 中栏切 Mail tab 并加载 8 区数据 + 右栏 bind context 并注入 system turn

#### 中栏 — Inspector (5 tabs)
| Tab       | 内容                                                                                | 触发刷新                                  |
|-----------|-------------------------------------------------------------------------------------|-------------------------------------------|
| Mail      | 邮件正文 + 附件 + 面包屑 (👤/📐/🛡/💰/🔬) + cite chip 内联                              | 点左栏邮件                                |
| Draft     | subject/body/状态 (draft_only)/sha16 锁；操作：采纳 / 重生成 / 编辑 / 丢弃                | 邮件切换 / write_reply 后 / approve 后    |
| DraftHist | `data/drafts/{cid}.audit.json` 时间线 (按 ts 倒序)，每条 hash/status/操作员           | 任何写 draft 行为                         |
| Approval  | 复用 `renderHITLPanel` + locked banner + 批准/打回 + iron-rule-1 红字                  | verification=HITL 时显示 / sha 失锁时     |
| HITL      | 本客户所有 HITL 事件 + 升级原因 + 关联 context_id                                       | 客户历史加载 / hitl_explain 后            |

#### 右栏 — Chat + Skill Console
- **Chat 气泡**：
  - 用户气泡：右对齐 · 蓝色
  - Agent 气泡：左对齐 · 暗灰 + **Skill Badge Strip**（每个 skill 一枚 chip：`✓` ok / `🔒` locked / `⚠` violation / `⏭` skipped）+ **Cite Chip**（`[[cite:customer|cid=...|sha=...]]` 渲染为可点击蓝色 chip）+ **Trace 折叠**（点 🔬 trace 展开 dispatch_id / executed_skills / output_sha256 / latency_ms）
- **Skill Console 抽屉**：dispatcher 策略 (`auto/rules_only/llm`) + OpenShell 4 策略开关 + 17 个 skill 启停列表 + `data/skill_audit.jsonl` 最近 5 条
- **输入区**：多行 textarea（Enter 发 / Shift+Enter 换行）+ `▶ 发送` / `🧹 清空` / `⚙ 预设`（弹意图下拉：报价/DFM/草稿/批准/反馈）+ `Ctrl+K` 命令面板

### 2.3 跨栏联动矩阵

| 触发源                | 中栏响应                                                                          | 右栏响应                                                              |
|-----------------------|-----------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| 点左栏邮件            | Mail tab；渲染正文；拉 8 区数据进 Inspector 缓存                                  | system turn "📧 已加载 mail_id=X, context_id=Y"；bind context         |
| 点中栏 Approval 批准  | `/v1/rfq/{cid}/approve` → 切回 Mail tab 并刷新面包屑                              | 系统消息 "✅ 已批准 · state=DONE · sha=ab12" + cite → HITL 面板        |
| 右栏调用 calc_quote   | Draft tab 高亮 0.8s；面包屑 💰 pill 更新 unit_price                                | Chat bubble 挂 `[calc_quote 🔒]` badge + 🔬 trace                     |
| 右栏调用 verify_gate  | Approval tab 若 HITL 自动激活；iron-rule 触发时 banner                            | Chat bubble 挂 `[verify_gate ✓ HITL]` badge                            |
| 右栏调用 rag_recall   | Mail tab 顶部追加 "📚 召回 N 条"                                                   | Chat bubble `[[cite:rag|case_id=KB-304-ANOD]]` chip                  |
| Chat cite chip 点击   | 切到对应 region tab + `focusRegion(name)` + 1.2s 黄框高亮                         | —                                                                     |

---

## 3. 后端 — 新增模块与 API

### 3.1 新增 5 个 API（`services/chat_api.py` 注册 router）

| Method | Path                                  | 用途                                                                                              | 后端实现                                                                                                |
|--------|---------------------------------------|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------|
| POST   | `/v1/chat/turn`                       | 单轮对话：自然语言 → Skill 编排 → Agent bubble payload                                             | `chat_understand → rag_recall → context_lookup → skill_dispatch → cite_evidence → suggest_reply`     |
| GET    | `/v1/chat/history?session_id&limit`   | 拉历史轮次                                                                                        | 读 `data/chat_sessions/{sid}.jsonl`                                                                     |
| POST   | `/v1/chat/reset`                      | 清空当前 session                                                                                  | 截断 jsonl                                                                                              |
| POST   | `/v1/chat/explain`                    | 单点解释：`kind=hitl|calc_quote|trace` + key → 自然语言说明                                       | 调 `hitl_explain` / 拼装 trace 摘要                                                                      |
| GET    | `/v1/chat/skills`                     | 列出 dispatcher 可用 skill + 启用状态 + iron_rule                                                 | 复用 `rt.list_skills()` + workbench-only 过滤                                                            |

**session_id**：首次 `?mail_id=X` 不存在则自动创建 `workbench-{mail_id_short}-{uuid6}`，落 `data/chat_sessions/`。单 session 强绑一个 mail；顶部下拉可切"无绑定"模式。

### 3.2 复用端点（零修改）

`/v1/mail/inbox`、`/v1/mail/{mid}`、`/v1/mail/{mid}/context/{customer,geometry,rag,pending,verification,postmortem,commercial,trace,hitl}`、`/v1/agent/task`、`/v1/rfq/{cid}/approve`、`/v1/feedback`、`/v1/v12/status|audit|dfm`、`/v1/skills/config`、`/v1/gmail/*`、`/health` —— 全部沿用。

### 3.3 一次性 Chat 回合数据流

```
[UI] 输入"做方案PRD，交付让我确认"
   │ POST /v1/chat/turn  {session_id, intent, bound_mail_id, bound_context_id}
   ▼
[chat_api.chat_turn]
   1) chat_understand  → intent=plan_prd, slots={deliverable:prd}, needs_context=true
   2) rag_recall       → 3 条相关案例 (postmortem/rag/crm_history)
   3) context_lookup   → 一次拉 8 区 (若 bound_mail_id)
   4) skill_dispatch   → seq=[parse_rfq, calc_quote, verify_gate, suggest_reply]
   5) cite_evidence    → 注入 [[cite:customer|...]] [[cite:rag|...]]
   6) suggest_reply    → 调 write_reply (若命中草稿意图)
   ▼
返回 {turn_id, agent_text, skill_calls[], citations[], sha_locks{}, hitl_required, trace_summary}
   ▼
[UI] Workbench 渲染：Agent bubble + Badge + Cite + Trace · 中栏 Draft/Approval 自动激活 · audit jsonl +1
```

---

## 4. Agent Skills — 9 复用 + 8 新增 = 17 个

### 4.1 复用（不发明，零修改）
| skill_id          | iron_rule      | 右栏调用形态                        |
|-------------------|----------------|-------------------------------------|
| `parse_rfq`       | deterministic  | "📧 帮我解析这封邮件"               |
| `extract_specs`   | llm_proposal   | 内部由 chat_understand 触发          |
| `check_dfm`       | deterministic  | "🔍 查 DFM 冲突"                    |
| `calc_quote`      | deterministic  | "💰 算一下报价"  🔒 铁律①           |
| `verify_gate`     | deterministic  | "🛡 跑门禁"                          |
| `write_reply`     | draft_only     | "📝 起草回复" 内部由 suggest_reply   |
| `render_thumbnail`| deterministic  | STEP 自动                           |
| `supplier_match`  | none           | "🏭 找供应商"                        |
| `submit_feedback` | deterministic  | "🆘 反馈 bug"                        |
| `golden_chain`    | deterministic  | "🔗 跑黄金链" 一键端到端             |

### 4.2 新增 8 个（每个目录含 SKILL.md frontmatter + tool.py）

| skill_id          | name (展示) | iron_rule       | backend                                            | 右栏能力                          | 关键说明                                                                                       |
|-------------------|-------------|-----------------|----------------------------------------------------|-----------------------------------|------------------------------------------------------------------------------------------------|
| `chat_understand` | 💬 意图理解 | llm_proposal    | `services/chat/intent_classifier.py:classify`     | 自然语言 → intent + slots + skill_hint | 独立模块不依赖 dispatcher；LLM 离线 → 复用 dispatcher `_RULE_ROUTES` 关键词（提取为 `services/chat/rule_routes.py`） |
| `rag_recall`      | 🔍 RAG 召回 | none            | `services/chat/rag_recall_skill.py:recall`         | "📚 查历史经验" / 自动触发         | 组合 `crm.list_customer_history` + `rag.search` + `postmortem.recall_customer_memory`         |
| `context_lookup`  | 🗂 上下文聚合 | none          | `services/mailbox_api.py:_load_context_bundle`    | "📊 拉这封邮件 8 区"               | 把 8 个 GET 合并为 1 次，60s 内存缓存                                                          |
| `skill_dispatch`  | 🎯 编排调度 | none            | `services/skill_dispatcher.py:SkillDispatcher.dispatch` | Chat 内部唯一入口               | 包装 dispatch()：强制 `bound_context_id` + `audit_tag=workbench_chat` + 返回结构化 envelope    |
| `cite_evidence`   | 🔗 引用证据 | none            | `services/chat/cite_evidence.py:attach_cites`     | 给回复加证据                      | 双轨：规则匹配 + LLM 提议限已知 key 集；**绝不**改写数字，只在数字前后加 🔒；含 integrity_check |
| `suggest_reply`   | 📝 草稿建议 | draft_only      | `services/reply.py:build_reply` + 微调             | 自动 use_llm=true + sha16 锁       | 区别 write_reply：返回 subject/body/status/locked/can_send 结构化 envelope                       |
| `approve_gate`    | ✅ 批准门禁 | hitl_required   | `/v1/rfq/{cid}/approve` 服务端封装                  | "👤 批准" → 双确认 + 展示 sha16    | 新增 skill 形态（不新写后端）；locked=false 时返回 400                                          |
| `hitl_explain`    | 📖 HITL 解释 | none           | `verification.run` + 解释模板                      | "🤔 为什么需要 HITL"               | reasons/conflicts/risk_score 转中文 + 命中 hitl-required.yaml 触发器名                          |
| `audit_tail`      | 📜 审计尾巴 | none            | `services/audit.py:tail` (新)                     | "📜 看最近审计"                    | 读 `data/skill_audit.jsonl` 最近 N 条，按 dispatch_id 聚合                                       |

合计 **17 个**，落在区间内。

### 4.3 同时修的 3 个现有 Bug（写新代码时一并修）
1. `services/crm_memory.py:44` 加 `check_same_thread=False` + 用 `threading.local()` 或每请求 new conn（解 sqlite3.ProgrammingError）
2. `services/crm_memory.py:130` `list_customer_history` 修 SQL：`postmortems` 加 `WHERE context_id IN (SELECT context_id FROM rfqs WHERE customer_id=?)` 过滤
3. 后端补 `/v1/demo/scenario/{S1-S5,M1}` 6 个端点（或改为"Demo 按钮=自动上传预置 .eml"），让 UI 6 个 Demo 按钮活起来

---

## 5. 前端 — `#tab-workbench` 默认 active

### 5.1 DOM 节点

```html
<li data-tab="workbench" class="active">🧰 Workbench</li>
<section id="tab-workbench">
  <div class="wb-statusbar">…</div>
  <div class="wb-shell">
    <aside class="wb-inbox"  id="wbInbox"></aside>
    <main  class="wb-inspect" id="wbInspect"></main>
    <aside class="wb-chat"   id="wbChat"></aside>
  </div>
  <div class="wb-footbar">…</div>
</section>
```
旧 `tab-mailbox` 改为 hidden 兼容（demo 按钮仍可触发上传 .eml）。

### 5.2 IIFE 命名空间
```js
window.Workbench = (function(){
  const state = { session_id:null, bound_mail_id:null, bound_context_id:null,
                  activeRegion:'mail', messages:[], pending:false };
  return { refresh, openMail, send, jumpCite, highlightRegion, switchInspectTab,
           toggleSkillConsole, openCommandPalette };
})();
```
保留 `window.Mail` 向后兼容。

### 5.3 渲染关键点
- **Skill Badge Strip**：`[🔧 {skill_id} {state_icon}]`，state_icon = `✓ | 🔒 | ⚠ | ⏭`，颜色 `var(--ok)/var(--warn)/var(--err)/var(--mut)`
- **Cite Chip 渲染**：`text.replace(/\[\[cite:([^|]+)\|([^|]+)\|?([^\]]*)\]\]/g, (_,k,key) => `<a class="cite-chip" onclick="Workbench.jumpCite('${k}','${key}')">📎 ${key}</a>`)`
- **Trace 折叠**：`<details><summary>🔬 trace</summary><pre>${JSON.stringify(trace,null,2)}</pre></details>`
- **高亮 API**：`Workbench.highlightRegion(name)` → 中栏切 tab + `box-shadow:0 0 0 2px var(--acc)` + 1.2s

### 5.4 键盘快捷键 (`window` 监听)
| 键                | 行为                                        |
|-------------------|---------------------------------------------|
| Enter (chat)      | 发送                                        |
| Shift+Enter       | 换行                                        |
| Ctrl+K            | 命令面板（批准 / 算报价 / 打开 Skills）     |
| Ctrl+1/2/3/4/5    | 中栏 Inspector 切 tab                      |
| Ctrl+B            | 切换 Chat 与左栏 Inbox 焦点                 |
| Esc               | 关闭 Skill Console / 命令面板              |

### 5.5 状态栏（sticky bottom，22px）
`engine: Timo live | API ok | LLM: auto | dispatcher: auto | skill_audit: 12 (5min) | iron-rule-1 🔒`
数据源：`GET /health` + `GET /v1/v12/audit?limit=5` + `GET /v1/agent/openshell`

---

## 6. 铁律落点（Iron-Rule Enforcement）

| 铁律                       | 工程化落点                                                                                                                                                                                              | 可视化                                                                                       |
|---------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| ① LLM 不可改写 quote      | `openshell.py:lock_deterministic_output` dispatcher 每步 postcheck 计算 `sha256_obj(output)`；`verify_locked_output` 比对；Chat 走 `skill_dispatch → calc_quote` 同样强制经这两步                       | Draft tab 🔒/🔓；Approval tab sha16；篡改红 banner "iron-rule-1 violation"；状态栏永久 🔒    |
| ② 不可绕过 OpenShell      | 所有 skill 必经 `dispatcher.dispatch(intent,...)`；`chat_api.py` 不允许直接 `rt.execute`；新增 skill 必须在 `openshell/skill-allowlist.yaml` 内                                                         | Skill Console 列出 4 策略开关；越权 trace 标红 `⚠ violation`                                    |
| ③ 草稿必须 draft_only     | `reply.build_reply` 永远 `auto_send=False, mode='draft_only'`；`suggest_reply` 只暴露"采纳/重生成/丢弃"，无 send 按钮                                                                                  | Draft tab 顶部徽标 "📝 draft_only · 铁律①"；状态栏发送按钮 disabled "由人工发送"               |
| ④ 审计落 `data/skill_audit.jsonl` | `skill_dispatcher._write_audit` 每 dispatch +1 行；Chat 加 `audit_tag=workbench_chat`                                                                                                              | Skill Console 底部"最近 5 条"实时滚动；右键 bubble 看完整 trace                                |
| ⑤ 篡改拦截可视化          | `mail_context_hitl` 算 `quote_sha16_locked` vs `quote_sha16` → `locked:bool`；`cite_evidence.integrity_check` 比较 trace sha vs locks                                                                  | 红 banner + 锁变红 + toast "🚫 报价被篡改，已拒绝"；approve 需勾"我已确认锁状态"双确认         |

---

## 7. 验收口径

### 7.1 pytest（新增 ≥ 25 用例，目标总 ≥ 442）

| 模块                              | 目标数 | 覆盖                                                                                  |
|-----------------------------------|--------|---------------------------------------------------------------------------------------|
| `test_chat_understand.py`         | 4      | 关键词→intent；LLM 离线→rules；slots 抽取；空输入容错                                  |
| `test_chat_rag_recall.py`         | 3      | 客户历史召回；mock KB；cite_key 唯一性                                                  |
| `test_chat_context_lookup.py`     | 3      | 一次拉 8 区；60s 缓存；缺文件容错                                                       |
| `test_chat_skill_dispatch.py`     | 3      | bound_context_id 注入；audit_tag；iron-rule-1 拦截走 chat                              |
| `test_chat_cite_evidence.py`      | 3      | LLM 文本 → cite；数字不被改写；malformed 不抛                                          |
| `test_chat_suggest_reply.py`      | 3      | draft_only；sha16 一致；HITL 写原因不写数字                                            |
| `test_chat_approve_gate.py`       | 2      | 二次确认；locked=false → 400；落 audit                                                  |
| `test_chat_hitl_explain.py`       | 2      | 中文输出；含触发器名；含 risk_score                                                    |
| `test_workbench_api.py`           | 4      | 5 端点契约；session 持久化；reset；explain 三种 kind                                   |
| `test_workbench_ui.py`            | 6      | 默认 tab=workbench；三栏 id；cite-chip 渲染；快捷键监听                                |
| `test_mailbox_ui.py` (改)         | 2      | 旧 mailbox tab hidden 但可达                                                           |
| `test_crm_memory_fix.py` (新)     | 3      | check_same_thread=False；postmortems 按 cid 过滤；pending_for 不抛                     |

### 7.2 浏览器 E2E（Playwright headless / 手动）

| 路径                                                                      | 期望                                                                                          |
|---------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|
| `127.0.0.1:8900/` 加载                                                    | 默认 active tab=workbench；三栏可见；statusbar `iron-rule-1 🔒`                              |
| `Demo: S2 HITL` → 自动选邮件                                              | 中栏 Approval；sha16 锁亮；cite chip "HITL" 可点；Chat bind 显示 cid                          |
| Chat 输入"做方案PRD，交付让我确认" → 发送                                 | 1-2s 内 Agent bubble；badge 含 `parse_rfq` `verify_gate`；草稿 tab 自动填；audit +1            |
| Chat cite chip "📎 KB-6061-ANOD" 点击                                    | 中栏切 Mail tab + 1.2s 黄框高亮                                                               |
| `POST /v1/skills/config` 关 `iron-rule-1`                                 | 400 "iron-rule-1 不可禁用"；UI 仍 🔒                                                          |
| LLM 离线重发同一句                                                         | Chat 仍返回（rules 路由）；bubble 角标 `🤖 rules_only`                                        |
| `Ctrl+K` 命令面板                                                          | 浮层显示 3 条；ESC 关闭                                                                         |
| Chat "✅ 批准" → 双确认 → 二次点击                                         | toast "✓ 批准成功"；Draft tab 状态 done；audit +1                                              |
| 手动 `os.replace('data/contexts/X.json')` 后刷新                          | Approval tab 红 banner "报价被篡改"；"批准" disabled                                          |
| Gmail 拉信按钮（仍可用）                                                   | 不破坏；新邮件自动出现在左栏                                                                   |

### 7.3 离线降级

| 故障       | 行为                                                                       | UI 提示                          |
|------------|----------------------------------------------------------------------------|----------------------------------|
| LLM 离线   | `chat_understand`/`extract_specs` 走 rules；`write_reply` use_llm=false    | 气泡角标 `🤖 rules_only`         |
| Timo 离线  | `calc_quote` MOCK；`verify_gate` 仍跑本地；`step_geometry` 本地模拟         | 面包屑 `📐 source=MOCK`         |
| RAG 离线   | `rag_recall` 内置 fallback KB；cite chip 带 `[MOCK]` 角标                   | cite 文案加 `(mock)`            |
| Gmail 离线 | 拉信按钮 "⚠ Gmail 不可达"；左栏只显示本地 .eml                               | 顶部 Gmail pill 红              |
| CRM 关闭   | `customer_id_by_name` 返回 None；Chat cite 改 rag 兜底                       | 客户区 "新客户 · CRM 关闭"      |

---

## 8. 工作量与里程碑（单兵 1 人）

| 阶段                                            | 工时(人天) | 交付物                                                                                                                |
|-------------------------------------------------|------------|-----------------------------------------------------------------------------------------------------------------------|
| **P0** 设计 & 脚手架（本 PRD + API 契约）        | 0.5        | `docs/PRD-v4-workbench.md`（本文件）；`services/chat_api.py` 路由骨架                                                  |
| **P1** 后端 chat_api + 8 个新 skill             | 3.0        | `services/chat/{intent_classifier,rag_recall_skill,cite_evidence,rule_routes}.py`；8 个 `skills/<name>/{SKILL.md,tool.py}` |
| **P2** chat session 持久化 + 3 个现有 bug 修复    | 1.0        | `data/chat_sessions/*.jsonl` + crm_memory check_same_thread + postmortems 按 cid 过滤 + Demo 端点                     |
| **P3** 前端三栏 Workbench（默认 active）         | 4.0        | `#tab-workbench` section；CSS Grid；Inbox/Inspector/Chat IIFE；快捷键；状态栏                                          |
| **P4** 跨栏联动 + cite chip + 高亮               | 1.5        | `Workbench.jumpCite/highlightRegion/switchInspectTab`；事件总线                                                       |
| **P5** Skill Console 抽屉                         | 1.0        | 设置面板 + 审计尾巴 + OpenShell 开关                                                                                   |
| **P6** pytest 35 个新用例                          | 1.5        | 见 §7.1 表                                                                                                            |
| **P7** 浏览器 E2E + 离线降级手测                  | 1.5        | Playwright / 手动清单                                                                                                  |
| **P8** 文档 + 演示                                | 0.5        | 更新 README/CHANGELOG/MANIFEST；5 min 演示                                                                            |
| **合计**                                          | **14.0**   | ≈ 3 周（单兵 / 双周末冲）                                                                                              |

### 8.1 里程碑

| Milestone | 范围                                          | 验收                                                                       |
|-----------|-----------------------------------------------|----------------------------------------------------------------------------|
| **M1 周末 1** | P0 + P1 + P2                                  | pytest 35 个新用例全绿；`curl /v1/chat/turn` 手动跑通                        |
| **M2 周末 2** | P3 + P4                                       | Playwright 走通 "Demo S2 → Chat 批准" E2E；三栏截图对齐                      |
| **M3 周末 3** | P5 + P6 + P7                                  | 全部 442+ 测试通过；离线/篡改/越权 3 个 demo 评委面前 30 秒复现               |
| **M4 Demo**   | P8 + 修补                                     | README/CHANGELOG/MANIFEST 完整；`data/skill_audit.jsonl` 实战 ≥ 20 新行     |

---

## 9. 风险与缓解

| #  | 风险                                                                    | 等级 | 缓解                                                                                                                          |
|----|-------------------------------------------------------------------------|------|-------------------------------------------------------------------------------------------------------------------------------|
| 1  | LLM 输出引用词与 cite_key 不可靠匹配 → cite 错位                          | 高   | `cite_evidence` 双轨：规则 + LLM 限已知 key 集；UI 角标"提议未确认"可人工删                                                       |
| 2  | Chat 与左栏邮件切换的 race → 草稿写到错的 cid                              | 高   | `state.bound_context_id` 写入前 200ms 节流；Chat 显式显示绑定 cid；切换时停发未发输入                                              |
| 3  | session jsonl 体积爆炸                                                    | 中   | LRU cap 200 条/会话 + token 上限；旧会话自动归档 `_archive/`                                                                      |
| 4  | webui/index.html 突破 2300 行                                            | 中   | Chat Pane + Skill Console 抽离为 `<script type="module">webui/workbench.js`，HTML 只留骨架                                          |
| 5  | dispatcher `attempt_override` 仅模拟，未在真实 Chat 路径拦截              | 中   | `skill_dispatch` 包装强制 `shell._shadow=True` 让 override 真实运行；unit test 覆盖                                                |
| 6  | `chat_understand` 与 `skill_dispatcher._RULE_ROUTES` 关键词表不一致       | 中   | 提取 `_RULE_ROUTES` 为 `services/chat/rule_routes.py`，两处 import                                                                |
| 7  | funasr-gui 未接 → RAG 离线演示"假"                                       | 低   | UI 加 mock 角标；接通留 P9                                                                                                       |
| 8  | cite chip 点击若 region 数据未加载 → 高亮失败                             | 低   | `jumpCite` 先 `await context_lookup`，超时 3s toast                                                                              |
| 9  | 铁律① 篡改拦截 demo 只在 hitl 端，Chat 路径未做 → 评委挑刺                | 中   | `cite_evidence.integrity_check`：trace sha ≠ locks → 红色 violation 标签 + 禁后续 suggest_reply/approve_gate                     |
| 10 | 跨线程 SQLite bug 不修 → 跑负载后崩                                       | 高   | P2 一并修：crm_memory 用 `check_same_thread=False` + `threading.local()`                                                          |

---

## 10. 关键文件路径

| 类别         | 路径                                                                                                |
|--------------|-----------------------------------------------------------------------------------------------------|
| Web UI       | `C:\Users\<user>\Desktop\比赛\英伟达第三\union-export-agent-livekernel\webui\index.html` (+ `workbench.js`) |
| API 服务     | `C:\Users\<user>\Desktop\比赛\英伟达第三\union-export-agent-livekernel\services\api_server.py`         |
| **新增**     | `services/chat_api.py` · `services/chat/{intent_classifier,rag_recall_skill,cite_evidence,rule_routes}.py` |
| **新增 skills** | `skills/{chat-understand,rag-recall,context-lookup,skill-dispatch,cite-evidence,suggest-reply,approve-gate,hitl-explain,audit-tail}/SKILL.md` + `tool.py` |
| 邮件台 7 区  | `services/mailbox_api.py`                                                                           |
| Skill 调度器 | `services/skill_dispatcher.py`                                                                       |
| Skill 注册表 | `services/skill_registry.py`                                                                         |
| OpenShell    | `services/openshell.py` + `openshell/*.yaml`                                                         |
| CRM          | `services/crm_memory.py`（P2 修 bug）                                                                |
| RAG          | `services/rag.py`                                                                                    |
| 评估         | `evaluation/{metrics,rag_eval}.py`                                                                   |

---

## 11. 不破坏（向后兼容承诺）

- `tab-mailbox` 仍可达（hidden 但可点 nav 切换）；6 个 Demo 按钮在 mailbox tab 仍工作（P2 补端点后）。
- 所有现有 API 路径不变；现有 417 个测试不动；新增测试在独立模块下。
- 现有 11 个 skill 全部继续工作；新增 8 个走相同 `skills/_runtime.py` 自动发现。
- Iron-rule-1 锁定在 validate / UI / router.resolve / dispatcher.postcheck / chat_api.integrity_check 五处继续生效。
- `data/skill_audit.jsonl` 格式追加 `audit_tag=workbench_chat` 字段（向后兼容）。
- 状态栏 `iron-rule-1 🔒` 永远显示；`POST /v1/skills/config` 关 iron-rule-1 仍返回 400。
