PLACEHOLDER

## 0. 现状盘点
PLACEHOLDER2
PLACEHOLDER_REMOVED

## 1. 设计原则

### 1.1 三栏即三种心智
- 左 邮件: 用户读信的位置 — 邮件列表 + 单信正文/附件
- 中 预览: 用户决策的位置 — 产物 + 锁定 + HITL + 草稿
- 右 流程/RAG/对话: 用户问与改的位置 — 流程图 + RAG 证据 + 客户记忆 + Skill 对话

### 1.2 Skill 即一等公民
- 每个 Skill 是可点击、可单跑、可入链的卡片
- 顶部 Skill Palette (横向): 10 个 Skill 按钮 + 状态徽章
- 右栏底部 Skill Chat: 自然语言 → dispatcher.route → 可视化选中的 Skill 链 → 一键执行

### 1.3 状态可视化
- 顶部 sticky: 引擎/Timo/LLM/RAG/模型端点在线状态
- 中栏 sticky: 当前 context_id + state machine 状态 + 报价锁定 sha16
- 右栏顶部: 黄金链步骤图 (Intake→RFQ→DFM→Quote→Verify→Reply→CRM), 实时高亮当前步骤

### 1.4 不重写后端
- 仅替换 webui/index.html (单文件 89KB → 重写为模块化但单文件 ESM, 目标 ~150KB)
- 复用现有所有 API 端点, 0 新增 endpoint 优先
- 保留所有 iron-rule, OpenShell 审计, sha256 锁定语义

---

## 2. 信息架构 (三栏 Cockpit)

### 2.1 整体布局

`
┌─────────────────────────────────────────────────────────────────────────────┐
│ TopBar: Timo内核 FunASR LLM RAG  Dispatcher: auto ctx #                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ SkillPalette: [parse_rfq] [extract_specs] [check_dfm] [calc_quote]           │
│               [verify_gate] [write_reply] [render_thumbnail]               │
│               [supplier_match] [submit_feedback] [golden_chain 一键]         │
├──────────────────┬───────────────────────────┬──────────────────────────┤
│ LEFT (28%)       │ MIDDLE (38%)              │ RIGHT (34%)              │
│ 邮件 Inbox       │ 产物预览 + 决策           │ 流程 + RAG + Skill对话   │
│                  │                           │                          │
│ 邮件列表         │ [产物][报价][回复]         │ [流程图][RAG]            │
│ 邮件详情         │ STEP缩略图/几何/DFM       │ 黄金链 7 步可视化        │
│ 附件列表         │ 报价(锁定)+商业           │ RAG Top-K 证据卡         │
│                  │ 回复草稿 + HITL 横幅       │ 客户记忆                  │
│                  │ 审计 / Trace              │ Skill 对话                │
├──────────────────┴───────────────────────────┴──────────────────────────┤
│ BottomBar: 12s  2 flags  6 audit  [冻结][重派][设置]                  │
└─────────────────────────────────────────────────────────────────────────────┘
`

### 2.2 区域责任
| 区域 | 职责 | 主要 API |
|------|------|----------|
| TopBar | 全局健康 + 当前 ctx + dispatcher 策略 | /health /v1/v12/status /v1/agent/openshell |
| SkillPalette | 一键召唤单 Skill 或一键黄金链 | /v1/agent/route /v1/agent/dispatch |
| LEFT 邮件 | 邮件台 + 详情 + 附件 + 黄金链触发 | /v1/mail/inbox /v1/mail/{id} /v1/mail/{id}/context/customer |
| MIDDLE 预览 | 产物 + 报价 + 商业 + 回复 + HITL + 审计 | /v1/mail/{id}/context/{geometry|pending|verification|commercial|hitl} /v1/v12/{status|dfm} /v1/traces/{cid} |
| RIGHT 流程/RAG/对话 | 黄金链步骤图 + RAG Top-K + 客户记忆 + Skill 对话 | /v1/mail/{id}/context/{rag|postmortem|customer} /v1/agent/route /v1/agent/dispatch /v1/v12/audit |
| BottomBar | 摘要 + 全局动作 | (前端聚合) |

### 2.3 三栏交互闭环
1. 左选邮件 → 中自动加载该邮件的产物/报价/回复 → 右自动加载流程/RAG/客户
2. 任一栏点 Skill 按钮 → 右栏对话窗新增一轮 (route → 可执行) → 执行 → 中栏实时刷新锁定值
3. 中栏 HITL 批准 → 触发 /v1/rfq/{cid}/approve → 全链路 sha16 锁定 → BottomBar 显示审计

---

## 3. Skill 化封装 (能力 → Agent Skills)

### 3.1 现有 10 个 Skill (UI 暴露)
| Skill ID | 标签 | 按钮色 | 触发场景 |
|----------|------|--------|----------|
| parse_rfq | 解析询盘 | 蓝 | 邮件/PDF/文本 → canonical RFQ |
| extract_specs | LLM补参 | 青 | 缺失字段推断 (LLM, 不覆盖确定性值) |
| check_dfm | DFM冲突 | 黄 | 工艺/材料硬冲突 |
| calc_quote | 确定性报价 | 绿 | Timo 内核报价 (锁定) |
| verify_gate | 辟牟援推止 | 紫 | 验收 → PASS/HITL/BLOCKED |
| write_reply | 英文回复 | 粉 | draft_only |
| render_thumbnail | STEP缩略图 | 灰 | OCP B-rep → SVG |
| supplier_match | 供应商匹配 | 橙 | 7 维打分 TopN |
| submit_feedback | 提交反馈 | 灰 | 写 feedback_store |
| golden_chain | 黄金链 | 金 | 一键 S1-S5+M1 |

### 3.2 新增 UI 复合 Skill
- skill_compose_reply (UI 复合): 引用当前 ctx, 调 write_reply + 渲染到中栏回复 tab
- skill_hitl_approve (UI 复合): 引用 sha16 锁 + 调 /v1/rfq/{cid}/approve + 落审计

---

## 4. API 契约 (复用 + 最小新增)

### 4.1 完全复用 (已有)
- GET /health
- GET /v1/mail/inbox?limit=50
- GET /v1/mail/{mail_id}
- GET /v1/mail/{mail_id}/context/{customer|geometry|rag|pending|verification|postmortem|commercial|trace|hitl}
- GET /v1/v12/{status|audit|dfm}
- POST /v1/agent/route (意图路由预览)
- POST /v1/agent/dispatch (实际派发 + 执行)
- POST /v1/upload/{email|step|audio|pdf|excel|image|auto}
- POST /v1/rfq/{cid}/{analyze|quote|verify|approve|reply-draft|crm-sync}
- GET /v1/traces/{cid}
- GET/POST /v1/models/config, POST /v1/models/probe

### 4.2 最小新增 (≤3 个)
| Method | Path | 用途 |
|--------|------|------|
| GET | /v1/skills | 列 Skill 元数据 (UI 渲染 Palette) |
| POST | /v1/agent/dispatch/stream | SSE 流式执行 + 边执行边回调 |
| POST | /v1/mail/{mail_id}/lock | 显式锁定报价 (HITL 批准前的再确认) |

### 4.3 后端改动列表
| 文件 | 改动 |
|------|------|
| services/skill_dispatcher.py | +1 个 SSE handler + GET /v1/skills |
| services/api_server.py | +3 行 include_router |
| services/mailbox_api.py | +POST /lock |
| webui/index.html | **重写** (89KB → ~150KB 单文件 ESM) |
| 其余 | **0 改动** |

---

## 5. 验收口径

### 5.1 功能验收 (对齐冻结 PRD S1-S5+M1)
| 场景 | 操作 | 期望 |
|------|------|------|
| S1 6061×50 anodizing | 左选 ACME 邮件 → 一键黄金链 | 中栏 DONE 报价锁定 右栏流程 7 节点全绿 |
| S2 TC4×10 | 一键黄金链 | DONE + HITL 横幅 (TC4+精密) |
| S3 304+anodizing | 一键黄金链 | BLOCKED 中栏显示 DFM 冲突 右栏 RAG 给替代方案 |
| S4 304+passivation | 一键黄金链 | DONE |
| S5 TC4+IT5 | 一键黄金链 | HITL 锁定 sha16 |
| M1 邮件±0.02 + 语音0.05 | 一键黄金链 | HITL + 冲突横幅 VOICE_EMAIL_CONFLICT + RAG 给证据 |
| Skill 单跑 | 点 calc_quote | 仅中栏报价 tab 刷新, 不影响其他 |
| HITL 批准 | 中栏点 批准 | 落审计 锁定 sha16 变绿 BottomBar +1 audit |
| 自然语言对话 | 右栏输入 重新算 DFM | 路由到 check_dfm, 列出待执行, [执行] 触发 |

### 5.2 性能验收
- 首屏 < 1.5s (单文件)
- 三栏切换 < 200ms (本地缓存)
- 黄金链执行 (离线) < 3s; (在线 Timo) < 6s
- HITL 锁定态变更 5s 内可见

### 5.3 兼容验收
- 旧 dark mode 保留 (toggle)
- 旧设置/模型配置/V12 内核/Dispatch 仪表板 tab 全部可达 (放在 设置抽屉)
- 现有 .eml mailbox 文件直接可见
- 不破坏现有 95 个测试

### 5.4 设计验收
- 任意时刻三栏中至少一栏显示当前 ctx 的关键信息 (无空栏)
- HITL 状态 3 栏至少 1 栏可见
- 锁定 sha16 任意栏可一键复制
- 流程图 hover 显示 span 名 + 耗时

---

## 6. 交付物 (DoD)

- [ ] webui/index.html 重写 (~150KB, 单文件 ESM, 三栏)
- [ ] services/skill_dispatcher.py +SSE handler + GET /v1/skills
- [ ] services/mailbox_api.py +POST /lock
- [ ] services/api_server.py +3 行 router 注册
- [ ] docs/UI-REDESIGN-PRD.md (本文件)
- [ ] docs/UI-REDESIGN-NOTES.md (设计意图 + 关键交互时序图)
- [ ] tests/test_ui_smoke.py (Playwright 截图, 3 栏可见, 一键黄金链可见)
- [ ] 手动回归 S1-S5+M1 全绿
- [ ] 不破坏 95 个旧测试

---

## 7. 不做什么 (Non-Goals 本轮)

- 不重写后端架构
- 不引入 React/Vue/Webpack/Vite
- 不做邮件外发 (写回 mailbox 即可)
- 不做多用户/权限/审计前端 (后端已有 audit)
- 不做移动端适配 (桌面 1440+ 优先)
- 不做 Skill marketplace (Skill 已注册)

---

## 8. 风险与回滚

| 风险 | 缓解 |
|------|------|
| 单文件 150KB 加载慢 | gzip 后 ~35KB; 关键 CSS 内联, JS defer |
| SSE 跨域/缓冲 | fetch+ReadableStream 替代 EventSource |
| 三栏在小屏挤压 | <1280px 自动切 tab 模式 (保留) |
| Skill palette 阻塞误触 | 单跑需双击或右键 confirm |
| 旧测试回归 | 重写只动 webui/index.html + 3 个后端 router 行, 不触碰业务逻辑 |

回滚: git checkout HEAD~1 -- webui/index.html services/api_server.py 即可.

---

## 9. 待你确认的 4 个决策点

1. **风格**: 浅色专业版 (推荐, 制造业商务感强) vs 保留暗色?
2. **HITL 锁定**: UI 层加 POST /lock 显式再确认 (推荐, 防误点) vs 仅靠前端 disabled?
3. **流式执行**: SSE 边执行边高亮流程图 (推荐, 体验好) vs 一次性返回?
4. **暗色保留**: dark mode toggle 保留 (推荐, 现场演示两种风格可切) vs 强制浅色?

> 确认后 1 个工作日内交付 DoD 全部条目, 并用现有测试 + 新增 Playwright 截图回归.

---

## 附录 A: 推理依据 (遍历结论)

### A.1 项目体量
- 22 个 Python 服务文件 (services/)
- 16 个 Skill 包 (skills/)
- 6 份 PRD/架构文档 (docs/)
- 1 个 89KB 单文件 UI (webui/index.html)
- 95+ 个测试 (tests/)
- 已冻结 PRD v1.0 + 真实 Timo v12 内核接线

### A.2 关键不变量 (不能动)
- 黄金链 S1-S5+M1 (冻结 PRD §19)
- 铁律①: LLM 不决定最终价格 (iron-rule-1)
- 报价 sha16 锁定 + HITL can_approve 门禁
- OpenShell 审计 (策略 + 最近 audit)
- 7 个邮件区 B-1..B-9 (customer/geometry/rag/pending/verification/postmortem/commercial/trace/hitl)
- Timo v12 内核 + FunASR + LLM Planner 三端点

### A.3 主要瓶颈
- 现有 UI 是 " tab 全景\, 没主线, 业务人员进不去主线
- 10 个 Skill 注册了, 但 UI 没召唤入口, 业务人员感受不到
- HITL 风险藏在 B-9, 没全局 banner, 误发风险高
- 黄金链 6 步不可视, 演示时评委看不到 流程亮点
