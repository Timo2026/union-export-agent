# AUDIT-REPORT v7 — 全量审计扫描（任务 #20 / Track A1）

> **日期**: 2026-09-20 · **基线**: HEAD `741cb64`（工作树含 v6.2 飞轮 + QQ 收信未提交改动）
> **测试基线**: `python -m pytest tests/ -q` → **599 passed, 1 skipped** (175.98s)
> **方法**: 3 路并行只读扫描（死代码/重复 · 硬编码 · 联动断链）+ 主代理 grep 抽查复核
> **修复归口**: 每条 finding 标注既有任务 ID（#23-#36），不新开计划

---

## 0. 结论速览

| 维度 | 计数 | 最严重项 |
|---|---|---|
| 死代码/重复轮子 | 7 组 (F1-F7) | **整个 v6.2 flywheel 包零生产接线** (F5) |
| 硬编码 | A=9文件14行 · B=12端点 · C=1 · D=3模式 | settings.yaml 自身违反"禁止硬编码"头注 (A1) |
| 无反应/断链 | 8 条 (LINK-1~8) | **邮件队列有生产者语义但无消费者接线** (LINK-3) |
| 死循环 | 0 | 仅 bounded 文件锁循环，未发现失控环 |

---

## 1. 死代码 / 重复轮子（已抽查复核）

| ID | Finding | 证据 | 状态 | 归口 |
|---|---|---|---|---|
| F1 | `quote_calibration.py` 同文件 **5 组方法遮蔽**（不止 calibrate）：`calibrate :102/:260`、`_get_model :139/:392`、`predict_accuracy :150/:336`、`_calc_margin :173/:357`、`_get_target_margin :181/:373` → 前一份全死（~150行） | grep 复核 | CONFIRMED | #34 E1 删前份 |
| F2 | `services/flywheel_api.py` router **从未 include**（api_server.py:58-65 仅 mailbox/gmail/v12 三路由本审计复核） | 复核 `include_router` ×3 | CONFIRMED | #34 E1 mount 或删 |
| F3 | 双 MOCK 知识库重叠 3 个 case_id（`rag.py:11` vs `rag_search.py:68`）；rag_search 自身无生产导入方 | 前轮 grep 证 | PARTIAL | #23 B1 统一底座 |
| F4 | 另 3 组同文件重复 def：`crm_memory.get_calibrations :357/:573`；`customer_health.should_escalate :20/:122` + `escalate_reason :25/:130`（复核 count=2） | 复核 | CONFIRMED | #34 E1 |
| F5 | **孤儿模块清单**（生产零导入，仅测试引用）：`asr_engine, config_reload, customer_context(+customer_sandbox 传递死), customer_lifecycle, customer_profile, flywheel_api, flywheel_followup, flywheel_pricing, flywheel_retention, intake_pdf, mail_orchestrator, mail_puller, rag_search, web_search, services/flywheel/*(7文件), services/notify/*(4文件, 连带 egress_gate 只被 notify 引用)` | 复核 puller/orchestrator 生产零引用 | CONFIRMED | 分批：#25 B3、#34 E1、LINK-3 |
| F6 | skills 注册错位：4 目录未注册 core（customer-flywheel/customer-health/quote-calibration/retention-alert）；packs `knowledge-router` 无目录；pack source 指向仓外 `C:/Users/<user>/Videos/skill/...` | config/skill_registry.yaml | CONFIRMED | #34 E1 + F1 池策展(待拍板) |
| F7 | 套娃透传：`sandbox.get_sandbox :236` vs `customer_sandbox.get_sandbox :314`（同引擎两代复制）；`context_engine.get :156` 纯透传。`tools/omnivoice/engine/Lib/site-packages` numpy 1.26.2+1.26.4 双 wheel | | CONFIRMED | #34 E1 |

> ⚠️ **F5 与既有决策的张力**：memory 记录"两代并存，v6.2 做 RAG/矫正底座"——现证实 v6.2 整包**未接线**（cat_controller.py:59 仍走 v6.1 QuoteCalibration）。#25 B3 接线时须同时决定 v6.2 底座何时转正，避免"并存"变成"双死"。

## 2. 硬编码（A 类=可移植性断裂）

| 类 | 位置 | 归口 |
|---|---|---|
| A | settings.yaml:16-17（timo 引擎绝对路径——**配置源头自己违规**）；skill_registry packs/scan roots → 仓外 zip 路径；scripts/export_demo.py:20、run_golden_core.py:29、run_flywheel_demo.py:27、inventory_skills.py:22-23（导出目录写死） | #26 B4 / F1 池策展 / #36 E3 |
| B | api_server.py:684-686 端口 8900 无 settings 来源 → 被 7 个 scripts 复制；imap 主机名在 mail_puller/gmail_imap 双份（本次 QQ 接入再加 `QQ_HOST` 常量，已是单一来源） | #26 B4 一并收编 |
| C | credentials.py:21 Fernet pepper 盐为代码常量（建议 env `UEA_CREDENTIALS_PEPPER`）；**运行时凭据均在 gitignored 文件，export_demo.py:44,49 已正确排除** | 低风险，记录 |
| D | 毛利底线 25 在 `customer_flywheel.py:223-224` 与 `flywheel_retention.py:137-138,155` 三份复制，policy.yaml:63 才是 truth | #34 E1 |
| E | ~26 处合规"config-first + 显式默认"（funasr/timo adapter、NIM defaults、probe 端口等） | 不动 |

## 3. 无反应功能 / 联动断链

| ID | 症状（用户视角） | 证据 | 归口 |
|---|---|---|---|
| LINK-1 | Demo-bar "装载"按钮永远 404：`webui/index.html:1700` 调 `POST /v1/demo/scenario/{name}`，全仓无此路由（UI 自己都 toast "端点未实现,见 #35"） | | #34 E1 补路由或撤按钮 |
| LINK-2 | 飞轮统计/沙箱 API 整模块休眠（=F2） | | #34 E1 |
| LINK-3 | **邮件自动流转从未发生**：puller/orchestrator 只有测试调用，uvicorn 入口无 lifespan 钩子；`/v1/gmail/sync` 写 .eml 但不入 pending 队列。→ 本次 QQ 实拉的 21 条 pending 也来自我手工脚本 poll_once，服务重启后无人续跑 | 复核：生产零引用 | #25 B3 接线时挂 lifespan；#34 E1 |
| LINK-4 | skills 面板 5 个 pack 桥接 skill 显示 enabled 但派发即 `unknown skill`：注册在 `skills/_pack_bridge.py`，而 `_runtime.discover()` 跳过 `_` 前缀且无任何导入方 | 复核：零引用 | #34 E1 + F1 |
| LINK-5 | 30 个 skill 目录仅 ~10 个进路由目录；~18 个只能靠手工 `skills=[...]` 触发（UI 从不发）——两代重叠 | | F2/F3 路由池（待拍板） |
| LINK-6 | 上传 `audio/pdf/excel/image/email` 落 `data/artifacts/` 后**无人消费**（不进 RAG、不进黄金链）；UI 实际只调 step-with-thumbnail 与 upload/email | | **#28 C2**（upload→RAG 入口）正是修它 |
| LINK-7 | RAG 无写路径：`ingest_document` 零调用方、无 /v1/rag 端点 | | **#28 C2 / #29 C3** |
| LINK-8 | 已挂载但 UI 不调的端点 16+（spark/cache/nim/agent-spec/guardrails/traces + rfq 分步 7/8）——非死代码，属演示覆盖缺口 | | #36 E3 验收报告标注 |

## 4. 本轮复核声明

- 三条最高影响论断（LINK-3 puller 生产零引用 / LINK-4 _pack_bridge 零引用 / F2 flywheel 未挂载）由主代理 grep 独立复核通过；F1/F4 重复 def 复核 count 匹配。
- 死循环维度：未发现（唯一循环为 mail_puller 有界文件锁重试）。
- 本报告全部为**只读结论**，未改任何生产代码。

## 5. 与批准计划的映射（不新增范围）

- #34 E1 吸收：F1/F2/F4/F7/LINK-1/LINK-2/LINK-4/D 类三份毛利常量
- #25 B3 + #34 吸收：LINK-3 lifespan 接线（QQ 收信依赖它实现"无人值守拉取"）
- #28 C2 / #29 C3 吸收：LINK-6 / LINK-7
- #26 B4 吸收：A/B 类硬编码收编（含 settings.yaml 自身两行）
- F1 skill 池策展（待拍板）吸收：F6 pack source 仓外路径
