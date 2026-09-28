# PRD · v5.0.0 L3 邮件自动驱动 — Workbench

**方案代号**：`UEA-v5.0.0-L3` · **日期**：2026-09-19
**对齐**：NCP-AAI 工业 AI 协议 · NemoClaw 混合架构（Skills + Dispatcher + OpenShell） · 冻结架构 v1.0
**前置版本**：v4.0.0（462 passed · Workbench 三栏 UI · 18 个 skill）
**变更一句话**：从"按钮驱动 7 区堆叠"升级为"**邮件自动到达 → 黄金链 → 自动批准（L3）**"的端到端无人驾驶。

---

## 1. 目标 / 非目标

### 1.1 目标 (v5.0.0)
- **L3 邮件自动驱动**：Gmail IMAP → puller → orchestrator → CATController → FleetCoordinator v4 (3 专家 + Loop) → CEO Decision + Reid OS 双 LLM 背书 → verify_gate → auto_approve (PASS) → CRM sync → 审计落 `data/skill_audit.jsonl` + spark dashboard 实时注入
- **PASS 路径全自动**：`verification.status=PASS AND sha16_locked 一致` → 直接 approve + notify PASS；不阻断业务
- **HITL/BLOCKED 通知外发**：Telegram Bot API + Email SMTP (本地 mock) + Slack Webhook 三通道 fallback
- **NovaStudio 4 工具直接整合**：MinerU + ragflow + OmniVoice + SearXNG 全部 `tools/` 嵌入，无 adapters/ 桥接层
- **新增 12 个 skill**：fleet-coordinator + 3 专家 + quality-loop + orchestrator + ceo-decision + reid-os（覆盖 Skills_extracted 全部核心资产）

### 1.2 非目标（明确不做）
- ❌ L4 / L5 完全自动驾驶（保留 HITL/BLOCKED 人工兜底）
- ❌ 邮件状态机独立（与 RFQ 状态机冲突，统一用 CATController）
- ❌ supplier_module 履约 UI（后端有，UI 不接）
- ❌ 多用户协作 / 权限分级
- ❌ SMTP 真发信（铁律③ draft_only，notify 仅 mock + Telegram + Slack）

---

## 2. 架构分层

```
L5 应用层     index.html (Workbench 三栏 + 黄金链 + 3D + Ctrl+K)
              spark-output/dashboard.html (链路面板, 实时注入)
                ↓↑ WebSocket / REST
L4 编排层     MailPuller (30s 轮询) + MailOrchestrator (claim → run → notify)
              SkillDispatcher (rules_only/llm/auto) + Orchestrator skill (4 workflow YAML)
              CEO-Decision (5 证 + 投票) + Reid-OS (分诊 + 协议 + 拉闸)
                ↓↑
L3 业务层     CATController (黄金链) + FleetCoordinator v4 (3 专家 + Loop + Critic)
              5 Inspector tabs + 17 skills
                ↓↑
L2 计算层     Timo v12 (calc_quote + ConflictChecker) + CalculationEngine
              (Python 精确几何) + MATERIAL_DB / SURFACE_PRICE / MACHINING_RATE
                ↓↑
L1 感知层     Gmail IMAP / MinerU (PDF) / OmniVoice (ASR + TTS) / ragflow (RAG)
              / SearXNG (联网搜索) + funasr (Qwen3-ASR)
                ↓↑
L0 存储层     data/crm.sqlite3 + data/skill_audit.jsonl + data/drafts/{cid}.json
              data/contexts/{cid}.json + spark-output/context/*.json
```

---

## 3. L3 邮件自动驱动 CoT

```
[Gmail IMAP 30s 轮询]
   ↓ 拉新邮件
[MailPuller.poll_once]
   ↓ 写 .eml + .meta.json + enqueue pending.jsonl state=NEW
[MailPuller.claim_next_new]
   ↓ atomic file lock 防止重复
[MailOrchestrator.run_pipeline]
   ↓ 读 .eml → parse_rfq
   ├─ [FleetCoordinator v4] calculate_quote + 3 专家 (material/price/dfm)
   ├─ [QualityLoop] score >= 60 → done; < 60 → loop (召回 1 专家)
   ├─ [CEO-Decision] 5 证 (acceptance/history/margin/dfm/completeness) + 投票
   ├─ [Reid-OS] 分诊台 → 协议执行 → 价值观校准
   ↓
[CATController.verify_gate]
   ├─ PASS  → AuditChain.log("l3_auto_approved") + state=DONE
   ├─ HITL  → notify_external (Telegram/Email/Slack) + state=HITL
   └─ BLOCKED → notify_external + state=BLOCKED
   ↓
[data/skill_audit.jsonl 追加 audit_tag=l3-auto]
[data/notifications/{telegram,email}.* 追加]
[spark-output/context/{dispatch_id}.json + dashboard.html 更新]
```

---

## 4. Skill 全景（v5.0.0 共 30 个）

| Skill | iron_rule | 后端 | 用途 |
|---|---|---|---|
| parse_rfq / check_dfm / calc_quote / verify_gate / write_reply | deterministic | Timo v12 | 黄金链 5 步 |
| render_thumbnail / submit_feedback / supplier_match / golden_chain | deterministic | services | UI + 履约 |
| extract_specs / quality-loop / orchestrator / ceo-decision / reid-os | llm_proposal | LLMPlanner | 规划 / 决策 |
| fleet-coordinator | deterministic | services.fleet_v4 | CalculationEngine (4 材料 × 3 形状) |
| material-expert / price-expert / dfm-expert | llm_proposal | LLMPlanner | 3 领域专家 |
| approve_gate / hitl_explain | hitl_required | services | HITL 流程 |

每个 skill 都在 `services/guardrails.py:TOOL_ALLOWLIST` 注册，铁律②不允许绕过。

---

## 5. NovaStudio 4 工具整合（无桥接层）

| 工具 | 复制到 | 业务接入点 | 用途 |
|---|---|---|---|
| **MinerU** (PDF/Office 解析 76MB) | `tools/mineru/` (含 docker compose) | `services/intake_pdf.py` | PDF 附件深度版面抽取 |
| **ragflow** (RAG 引擎 Docker) | `tools/ragflow/` | `services/rag_search.py` | 行业经验库 Hybrid Search |
| **OmniVoice** (ASR + TTS, 1GB Python embedded) | `tools/omnivoice/engine/` | `services/asr_engine.py` | 语音附件 + TTS |
| **SearXNG** (本地 EXE 45M) | `tools/searxng/SearXNG.exe` | `services/web_search.py` | 联网搜索 (隐私本地) |

**一键启动**：`scripts/start_novastudio.bat` 后台拉起 4 工具 + 健康检查。

---

## 6. 铁律落点（v5.0.0）

| 铁律 | 工程化落点 | 可视化 |
|---|---|---|
| ① LLM 不可改写 quote | calc_quote 走 Timo + FleetCoordinator v4 CalculationEngine (deterministic)；3 专家 iron_rule=llm_proposal | Draft 锁图标 🔒 + 篡改红 banner |
| ② 不可绕过 OpenShell | 30 个 skill 全部 TOOL_ALLOWLIST 注册；dispatcher.precheck + postcheck 双重门禁 | Skill Console 4 策略开关 |
| ③ 草稿必须 draft_only | build_reply auto_send=False + MailOrchestrator.auto_approve 仅入 audit，不发 SMTP | Draft 顶部徽标 📝 |
| ④ 审计落 data/skill_audit.jsonl | MailOrchestrator._audit 写 audit_tag=l3-auto；LOOP/CEO/Reid 全部 audit.log | Skill Console 最近 5 条尾巴 |
| ⑤ 篡改拦截可视化 | locked=false → Approval tab 红 banner；`data/drafts/{cid}.json` 持久化 quote_sha16_locked | 顶部 toast "🚫 报价被篡改，已拒绝" |

---

## 7. 验收口径

### 7.1 pytest 全量
- 当前 **499 passed + 1 skipped + 0 failed**（v3 417 + M5-1 51 + T8-T17 32）
- 分布：
  - T1 (MailPuller): 8
  - T2 (MailOrchestrator): 8
  - T3 (FleetCoordinator v4): 6
  - T4 (3 专家): 10
  - T5 (QualityLoop): 5
  - T6 (Orchestrator): 7
  - T7 (M5-1 E2E): 6
  - T8 (CEO-Decision): 5
  - T9 (Reid-OS): 8
  - T10 (Notify): 6
  - T11 (Spark): 5
  - T12 (UI 升级): 8（含 workbench_three_columns_dom）
  - T14-T17 (NovaStudio): 7

### 7.2 E2E（Playwright headless）
- `scripts/e2e_l3.py` 跑 3 场景（PASS / HITL / BLOCKED）× 4 截图 = 12 张
- 报告 `docs/e2e_l3/e2e_l3_report.md`

### 7.3 离线降级（NovaStudio 4 工具未启动）
- MinerU: health() False → parse_pdf() 返 None + warning
- ragflow: health() False → search() fallback mock KB (6 案例)
- OmniVoice: health() False → asr() 返 None
- SearXNG: health() False → search() 返 empty + warning

---

## 8. 工作量与里程碑（已完成）

| 里程碑 | 范围 | 状态 |
|---|---|---|
| M5-1 | T1-T7 后端+编排 (30 用例 + 6 E2E) | ✅ 462 passed |
| M5-2a | T8-T12 决策+前端 (32 用例 + 6 截图) | ✅ 30 passed |
| M5-2b | T13 Playwright E2E (3 场景) | ✅ 12 截图 + 报告 |
| M5-3 | T14-T17 NovaStudio 4 工具整合 | ✅ 7 用例 + 4 工具嵌入 |
| M5-4 | T18-T20 全量回归 + 文档 + 演示视频 | ✅ |

**总进度：20/20 任务 · 100% 完成**

---

## 9. 与真实业务对齐

| 业务场景 | 覆盖模块 | E2E 验证 |
|----------|----------|----------|
| 客户来询盘 (S1 PASS) | T1+T2+T7 #1 | e2e_l3 01_pass |
| 客户要审批 (S2 HITL) | T1+T2+T7 #2 | e2e_l3 02_hitl |
| 工艺冲突 (S3 BLOCKED) | T1+T2+T7 #3 | e2e_l3 03_blocked |
| 批量报价 (6061 法兰/轴套/长方) | T3 (对齐方案 §5) | test_dgx_spark_doc_bushing_example |
| CEO 5 证决策 | T8 | test_full_pass_decision_accept |
| Reid-OS 拉闸检测 | T9 | test_intervention_danger_keyword |
| Notify 三通道 fallback | T10 | test_notify_priority_chain |
| Spark dashboard 实时 | T11 | test_multiple_dispatches_merge |
| NovaStudio 4 工具离线降级 | T14-T17 | test_*_offline |

---

## 10. GitHub 标准项目结构

```
union-export-agent-livekernel/
├── README.md                       # 入口 (已脱敏 NVIDIA 字)
├── LICENSE                         # MIT
├── CHANGELOG.md
├── MANIFEST.md
├── CONTRIBUTING.md
├── index.html                      # 架构参考图 (脱敏后)
├── webui/index.html                # Workbench 三栏 (2700 行)
├── bootstrap.py                    # 组装根
├── requirements.txt
├── 一键启动.bat / 一键自检.bat
│
├── adapters/                       # 真实后端接线
│   ├── timo_adapter.py             # 在线 :7862 / 离线 vendored kernel
│   ├── _kernel_bridge.py            # 离线 byte-identical 桥
│   └── funasr_adapter.py
├── agents/
│   └── cat_controller.py           # 黄金链编排
├── services/                       # 业务+平台层 (35+ 文件)
│   ├── api_server.py / mailbox_api.py / gmail_api.py
│   ├── cat / fleet_v4 / notify / ragflow / quality_scorer / spark_writer
│   ├── intake_pdf / asr_engine / web_search   # NovaStudio 接入点
│   └── ... (skill_dispatcher, mail_puller, mail_orchestrator, ...)
├── skills/                         # 30 个 Agent Skill
│   ├── parse-rfq / check-dfm / calc-quote / ...
│   ├── fleet-coordinator / material-expert / price-expert / dfm-expert
│   ├── quality-loop / orchestrator / ceo-decision / reid-os
│   └── ... + SKILL.md + tool.py + __init__.py
├── config/                         # YAML (settings / policy / models / agent / skills)
├── deploy/                         # Dockerfile / k8s / nim / hpa / grafana
├── tools/                          # NovaStudio 4 工具直接整合 (1GB)
│   ├── mineru/  (含 docker compose)
│   ├── ragflow/ (含 docker)
│   ├── omnivoice/engine/ (Python embedded)
│   └── searxng/ (本地 EXE)
├── scripts/                        # 启动 + 演示 + 验证
│   ├── start_novastudio.bat        # 一键 4 工具
│   ├── start_api.py / start_engine.py
│   ├── run_demo.py / demo_uploads.py
│   ├── screenshot_workbench.py / e2e_l3.py
│   └── verify_l3_demo.bat
├── docs/                           # 架构 / PRD / 验证 / NVIDIA 映射
├── tests/                          # 499 pytest + M5-1-REPORT.md
├── data/                           # 运行产物 (gitignore)
├── spark-output/                   # SparkSkillsHub dashboard
└── notebooks/                      # 14 个演示 notebook
```
