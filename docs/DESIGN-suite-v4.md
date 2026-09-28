# DESIGN.md · Union Export Agent UI Design Suite

**方案代号**：`UEA-NCPAAI-design-suite` · **日期**：2026-09-18  
**状态**：主线已收敛为 **C′ 融合工作台**（本轮仍不改业务代码）  
**对齐**：NCP-AAI 工业 AI 协议 · NemoClaw 混合架构 · 冻结架构 v1.0 · PRD-v4-workbench  
**最终设计图**：`docs/design-previews/ui-final-C-prime-workbench.png`

---

## Identity

Product UI Designer + Information Designer — 先回答「业务员 90% 时间在看哪一栏、锁在哪一步」，再回答「评委 30 秒能看懂哪条铁律」。

## Grounding

Junior Designer 假设：本产品是 **制造业外贸 RFQ 决策台**，不是通用 chat。视觉锚点取  企业控制台 + Linear/Bloomberg 操作台密度；主强调色 `#76B900`（ green），铁律红 `#EF4444`，HITL 琥珀 `#F59E0B`。刻意不做紫蓝渐变英雄区、不做 emoji 装饰列表。

---

## 1. Objective

把「按钮驱动 7 区堆叠」升级为可演示、可审计的三栏协作 UI；三款候选供用户择一落地；所有设计请求经 `design-suite-router` 智能路由到对应 skill。

## 2. Product Context

| 资产 | 角色 |
|------|------|
| `127.0.0.1:8900` v3.0.1 | 现场可跑：8 tab 邮件台 + V12 + HITL + Skills 后端已封装 |
| `docs/UI-REDESIGN-PRD.md` | 驾驶舱路线：Skill Palette + 三栏 + 黄金链可视化，API 近零新增 |
| `docs/PRD-v4-workbench.md` | 对话协作台：Chat 流水线 + 17 Skills + cite/trace + 跨栏联动 |
| 项目根 `英伟达第三` | Timo v12 内核 + funasr 多模态 + 冻结 PRD/架构 + 比赛交付包 |

**痛点（已核对）**：右栏只读堆叠无对话；Demo 按钮缺 `/v1/demo/scenario/*`；Skill 无 UI 入口；跨线程 SQLite；铁律可见性不足。

## 3. Visual Foundations

| Token | 值 | 用途 |
|-------|-----|------|
| `--bg` | `#0A0E12`（方案 C/B）/ `#F7F8FA`（方案 A） | 页面底 |
| `--panel` | `#121820` / `#FFFFFF` | 栏卡片 |
| `--ink` | `#D1D5DB` / `#0F172A` | 正文 |
| `--acc` | `#76B900` | Skill / 当前步 / 主操作 |
| `--chat` | `#3B82F6` | 用户气泡 / cite |
| `--warn` | `#F59E0B` | HITL |
| `--err` | `#EF4444` | iron-rule violation / 篡改 |
| `--mut` | `#6B7280` | 次级信息 / 禁用 |

**字体**：Latin `Inter` / `JetBrains Mono`（hash、trace）；CJK `PingFang SC` / `Microsoft YaHei`。  
**字号**：11 / 12 / 13 / 14 / 18 / 24。  
**圆角**：4–6px（工具感，拒绝 16px 卡片 slop）。  
**描边**：0.5–1px hairline，无阴影堆叠。

## 4. Accessibility

- 铁律/HITL 状态不单靠颜色：锁图标 + 文案 + 可访问标签  
- 对比度：正文 ≥ 4.5:1；禁用态仍可读  
- 键盘：Ctrl+K / Ctrl+1-5 / Enter / Esc（v4 PRD §5.4）  
- 最低演示宽度 1280px；&lt;960px 降级单列 tab

## 5. Voice & Tone

工程、克制、可审计。按钮动词化（「跑门禁」「算报价」），不用「赋能/无缝」。失败态直说原因（`iron-rule-1 violation`、`rules_only 路由`）。

## 6. Implementation Practices

- 优先单文件 ESM（~150KB），不引入 React/Vue/Vite（UI-REDESIGN §1.4 / Non-Goals）  
- 后端零发明：能复用 `/v1/agent/route|dispatch`、`/v1/mail/*`、`/v1/rfq/*` 就不新增  
- Chat 最小集（若选 B/C）：`/v1/chat/turn` · `/v1/chat/skills` · `/v1/chat/history`  
- 所有 Skill 经 dispatcher + OpenShell；UI 不直连 `rt.execute`  
- 预览文件：`docs/design-previews/*.png`（设计图，非代码）

## 7. Anti-Patterns（拒绝清单）

- U1 紫蓝渐变 hero · U2 圆角 16 阴影卡片网格 · U3 emoji 装饰标题  
- U5 悬浮大数字 stat 三连 · U6 所有按钮都是实心主按钮  
- 把 iron-rule-1 做成可关闭开关  
- 把 LLM 裁决价格（铁律①）  
- 移动端优先（本产品桌面决策台）

## 8. Decision-Making（方案分叉）

**收敛结论（2026-09-18）**：采用 **C′ = NanoQuote 作业台主骨架 + Hybrid 模块嵌入**。  
- 默认 **单工作台态**，右栏默认 Chat，输入框常驻。  
- **不做** 整屏 Chat|Pipeline 二选一；Pipeline/Golden Chain/STEP/RAG 降级为检视器顶条、几何 tab、右栏可折叠「证据」抽屉。  
- 对比结论：NanoQuote 更适合日常 HITL 闭环；Hybrid 更适合路演能力总览，故主从倒置。

| 维度 | A Ops Cockpit | B Workbench Chat | C Hybrid Deck | **C′ 融合（主线）** |
|------|---------------|------------------|---------------|---------------------|
| 对话驱动 | 5 | 10 | 9（双模） | 9（默认 Chat） |
| Skill 可达 | 9 | 8 | 9 | 9（chips + console） |
| 跨栏联动 | 8 | 9 | 9 | 9 |
| 铁律可视化 | 7 | 9 | 9 | 9（决策面） |
| IA 清晰 | 8 | 8 | 8 | 9（单态） |
| 落地就绪 | 6 | 4 | 5 | 6（最小 chat + 模块嵌入） |
| 演示叙事 | 8 | 9 | 9 | 8 |
| 人机效率 | 7 | 9 | 8 | 9 |
| 后端改动 | 近 0 | 大（+5 API +8 skill） | 中 | 中偏小（chat 最小集 + 修 bug） |

## 9. Workflow（design-suite-router）

```text
用户意图
   │
   ▼
design-suite-router
   ├─ 对比/评分/雷达     → data-analytics + visualizer
   ├─ UI 蓝图/三方案     → design-blueprint（本文件）
   ├─ UI 实现/改样式     → frontend-design
   ├─ Agent Skill 扩展   → skill-creator + mimo-skill-authoring
   ├─ 浏览器验收/截图    → playwright
   ├─ 演示 PPT           → pptx-official（先 DESIGN.md）
   ├─ 正式 Word/PDF      → docx-official / pdf-official
   └─ 概念图/背景素材    → imagegen
执行约束：
- 铁律与 OpenShell 契约由业务 skill 层保证，设计层只可视化
- 写 main worktree 前先问隔离
- 用户未确认主线前不改 webui/index.html
```

### Router 伪契约

```yaml
design-suite-router:
  version: 1.0.0
  routes:
    - match: [雷达, 对比, 维度评分, radar]
      skills: [data-analytics, visualizer]
    - match: [设计图, UI方案, 蓝图, design blueprint]
      skills: [design-blueprint, imagegen]   # 先蓝图，预览图可选
    - match: [实现, 改前端, workbench, cockpit, 改样式]
      skills: [frontend-design, pptx-official?no]
      guard: require_user_confirmed_direction
    - match: [skill封装, 新skill, dispatcher技能]
      skills: [skill-creator, mimo-skill-authoring]
    - match: [截图验收, e2e, playwright]
      skills: [playwright]
  postcheck:
    - iron_rule_visible: true
    - no_llm_price_authority: true
    - main_worktree_write: ask_first
```

---

## Decision Trace（摘要）

1. **三栏 IA 而非 8 tab 堆叠** — 用户原话「左边邮件、中间预览、右边流程/客户信息」；代价：小屏更挤，&lt;960 须降级。  
2. **主强调 项目品牌色 (工业绿 #76B900)而非企业蓝** — 赛题对齐 NCP-AAI，绿作单一 accent 可识别；代价：与常见 SaaS 蓝不同，需保证对比度。  
3. **铁律永久可见 sticky statusbar** — 评委与合规核心差异点；代价：底部 22px 常驻占用。  
4. **方案 C 右栏双模 Chat|Pipeline** — 兼顾演示叙事与日常点选；代价：状态机比单模复杂，需明确默认态。  
5. **本轮只出方案 + 设计图，不改代码** — 用户明确选择；代价：落地延后到确认后。  
6. **Router 先于实现** — 设计请求可复用、可审计；代价：多一层约定要维护。

## Anti-slop self-check

`clean` — 无渐变 hero / 无 emoji 装饰列表 / 无「无缝赋能」文案；色板单一 accent；工具圆角 ≤6px。

## 预览资产

| 文件 | 内容 |
|------|------|
| `docs/design-previews/ui-A-ops-cockpit.png` | 方案 A 高保真设计图 |
| `docs/design-previews/ui-B-workbench-chat.png` | 方案 B 高保真设计图 |
| `docs/design-previews/ui-C-hybrid-command-deck.png` | 方案 C 高保真设计图 |
| `docs/design-previews/radar-compare.png` | 雷达对比（生成图，以本文 SVG/表为准） |
| `docs/design-previews/ui-final-C-prime-workbench.png` | **最终设计图 · C′ 融合工作台** |

## C′ 结构规格（最终）

```
Top: 工作台 | 邮件台 | Skills | 设置 · health · skill chips
┌──────────┬────────────────────────────┬──────────────────┐
│ Inbox    │ 检视器（决策面）            │ 对话 Agent（默认）│
│ 选中HITL │ 顶部：黄金链步骤条          │ badge+explain    │
│          │ 审批HITL: banner/sha/双确认 │ cite chip        │
│          │ 几何 tab: STEP 摘要         │ 证据抽屉(折叠)    │
│          │ 客户历史时间线              │ 输入框常驻        │
└──────────┴────────────────────────────┴──────────────────┘
Bottom: iron-rule-1 🔒 · audit · engine/API/LLM
```

## 下一步（待执行指令）

1. 按 C′ 产出独立 HTML 高保真 mock（不接真 API）— 可选  
2. 隔离 worktree 后再改 `webui/index.html` — 等你明确  
3. design-suite-router 已支持后续「实现」路由到 frontend-design
