# SER-清单 — 服务/工程需求清单（任务 #22 / A3，滚动更新）

> 日期 2026-09-20 · 基线 599 passed, 1 skipped（`python -m pytest tests/ -q`）· 审计依据 [AUDIT-REPORT-v7](AUDIT-REPORT-v7.md) · 先例依据 [PRIOR-ART-v7](PRIOR-ART-v7.md)
> 状态图例：✅ 已实现已测 · 🟡 半成品（有实现无接线/无数据） · 🔴 缺失（挂任务号）

## 一、业务服务需求

| # | 需求 | 实现证据 | pytest 证据 | 状态 |
|---|---|---|---|---|
| R-01 | 黄金链 CAT 全流程（intake→analyze→quote→verify→approve→reply） | agents/cat_controller.py + api_server 路由 /v1/rfq/{cid}/* | test_golden_regression.py, test_l3_e2e.py | ✅ |
| R-02 | 报价必须确定性引擎出最终价，LLM 只提参 | timo_adapter + skills/cnc-quote（proposal-only, cannot_override_price） | test_experts.py, test_commercial.py | ✅ |
| R-03 | 历史报价"相似工况定价锚点"（L2 层） | services/rag_layers.py LayeredRAGGateway.list_similar_quotes/_layer_quotes + index_all_quotes；杰沃 500 有价行项已入 quote_history | test_rag_layers.py, test_jievo_pipeline.py | ✅ #24 B2 |
| R-04 | 报价自动矫正（分级上限+审计链） | scripts/quote_correction.py 接线完成：L2 召回 (零价锚点过滤) → v6.2 PriceCorrector (hot±15% 封顶+sha 审计链) → LOO 防泄漏。**真实 8-PO/11 行项精度实证: engine MAPE 51.12%, 矫正后 52.58% (无改善)**；引擎价系统性低于 PO 真值 ~38% (几何成本价 vs 客户成交价口径差)，±15% 召回信号不足以弥合 → 维持 proposal-only 人工核价，自动应用挂账后续 (需几何特征信号) | test_quote_correction.py×10 | ✅ #33 D4 (报告为负向结论) |
| R-05 | 391 杰沃 PO 历史价格入库 | services/po_parser.py + scripts/jievo_po_scan.py；全量实证 129/129 文件解析 ok (100%)、608 行项、500 有价 → 去重 ("(1)" 副本) 后 **422 唯一锚点入 quote_history + 108 份 PO 摘要入 ingest_docs** (file 后端落盘) | test_po_parser.py×7, test_jievo_pipeline.py×5（含真实语料端到端） | ✅ #30-31 D1/D2 |
| R-06 | 400+ 批量报价（BOM+STEP） | scripts/batch_quote.py 全量实证 **410/410 行报价成功 (quote_rate 100%)、234 行有 STEP 几何定价、176 行文本估算、unit_price 零空值、sum_total ¥920,054.82、全部 state=HITL（人工复核闸门）**；报告落 data/batch_quote_report.json (gitignored) | test_batch_quote.py×9（含真实 STEP e2e） | ✅ #32 D3 |
| R-07 | 客户信息层/对话层/工艺层分层 RAG 网关 | 四套记忆各自为政（核查报告 2026-09-19）；rag_layers.py 不存在 | — | 🔴 #23 B1 + #26 B4 |
| R-08 | 用户上传文件→RAG 入库闭环 | /v1/rag/ingest+/search+/docs+DELETE (api_server) + webui tab-rag + JsonFileBackend 重启持久 + ingest_document/delete_ingested_doc 增量 | test_rag_ingest.py×14 | ✅ #28 C2 + #29 C3 |
| R-09 | 邮件工作台（QQ/Gmail IMAP 收信） | services/gmail_imap.py service 泛化 + mail_puller service 配置 | test_qq_mailbox.py×8, test_gmail_imap_api.py×8 | ✅（收信实连 14 封验证） |
| R-10 | 邮件→队列→黄金链无人值守 | api_server lifespan 挂 puller+orchestrator (双层门禁: env UEA_MAIL_AUTOSTART + puller.is_enabled 凭据); /v1/gmail/sync 补入 pending 队列; /v1/mail/puller/status 可观测 | test_link3_lifespan.py×5 | ✅ #34 E1 (LINK-3 闭合) |
| R-11 | 发信 HITL：SMTP/IMAP 默认 OFF + draft_only + egress DENY 门 | services/egress_gate.py + settings.yaml egress.allow:false；QQ 仅接收信，SMTP 仍关 | test_egress_gate.py×11, test_hitl_endpoint.py, test_desensitize.py | ✅ |
| R-12 | 供应商闭环状态机 | services/supplier_*.py | test_supplier_db/inbox/pipeline/state_machine.py ×4 | ✅ |
| R-13 | 质量复盘闭环 (postmortem→knowledge) | agents postmortem 路由 | test_postmortem.py, test_quality_loop.py | ✅ |

## 二、工程/平台需求

| # | 需求 | 实现证据 | pytest 证据 | 状态 |
|---|---|---|---|---|
| E-01 | 凭据 Fernet 加密本地存储（0600） | services/credentials.py（pepper 常量→建议 env，AUDIT C 类） | test_credentials.py×7 | ✅ |
| E-02 | 队列 retry/死信/租约 | mail_puller claim_batch/fail_with_retry/reclaim_stale | test_queue_hardening.py×6 | ✅ |
| E-03 | 配置热载（mtime+校验回滚） | services/config_reload.py 生产接线: api_server POST /v1/config/reload + GET /v1/config/status (坏配置回滚+如实上报) | test_config_reload.py×5, test_config_reload_wiring.py×3 | ✅ #34 E1 |
| E-04 | sqlite 在线备份 + retention | services/backup.py | test_backup.py×5 | ✅ |
| E-05 | 跨平台（POSIX 兼容） | credentials O_BINARY 回退修复 | test_cross_platform.py×2 | ✅ |
| E-06 | 可观测（traces JSONL + metrics） | services/observability.py | test_observability.py | ✅ |
| E-07 | 技能注册/派发/目录 | skill_dispatcher + skill_registry + 33 目录（E2 新增 rag-ingest/batch-quote/quote-correction 薄封装已注册 skills.yaml+TOOL_ALLOWLIST；yaml enabled 19, LINK-5；pack 桥休眠, LINK-4；余目录未注册, F6） | test_e2_skills.py×9 + test_skill_dispatcher/registry/registry_p0.py（-k skill/registry/dispatcher/guardrail 93 passed） | 🟡 #35 E2 主项落地 |
| E-08 | 外部 1261-skill 池策展+路由（待拍板） | 见 skill-pool-moe 方案 F1-F4；SkillRouter/R3-Skill 先例 | — | 🔴 待拍板 |
| E-09 | 死代码/双份定义清零 | #34 E1 已清: quote_calibration 双 `def calibrate` 删死份 (守卫断言 count==1)、flywheel_api 挂载、rag_search MOCK_KB 并入 rag._FALLBACK_CASES 单源+Path bug 修、config_reload/mail 链路接线；F5 余量孤儿 (asr_engine/customer_lifecycle/intake_pdf/web_search 等) 挂账后续 | test_e1_cleanup.py×6, test_flywheel_mount.py×2 | 🟡 #34 主项清完, 余量挂账 |
| E-10 | 硬编码清零（路径/端点/魔法数） | B4 端点段 + margin=25 三份收敛 settings.yaml pricing.target_margin_pct (单源 helper target_margin_pct)；余: 端口 8900 被 scripts 复制 (AUDIT B 类) 挂账 | test_e1_cleanup.py (配置 30.0 注入/真实 25.0/字面量清除断言) | 🟡 主体完成 (margin+B4) |
| E-11 | 部署代码化 K8s/NIM | deploy/k8s.yaml + hpa.yaml + Dockerfile + grafana + nim/（compose+env 模板）；#36 修复 .env.example UTF-16 混编码；真机 GPU 起服验证需硬件, 挂账 | test_deploy_manifests.py×6 (manifest 结构/HPA 联动/GPU 预留/凭据只走 env 引用) | ✅ 代码化 (硬件验证挂账) |
| E-12 | 演示包可导出可离线 | scripts/export_demo.py（含敏感文件排除 :44,:49；路径硬编码 A 类）；#36 E3 重导: 33 skills · leaks 0 · 包内 run_golden_core 3/3 PASS (offline:calc_quote) | test_v6_root_index.py + 导出自检 | ✅ #36 E3 |
| E-13 | Guardrails（Nemo soft + 规则） | config/guardrails + services/guardrails* | test_guardrails.py, test_guardrails_nemo_soft.py | ✅ |
| E-14 | Release marker 三处同步 | CHANGELOG/MANIFEST/webui 副标题 | test_v3 marker 断言（741cb64） | ✅（每次 release 执行） |

## 三、缺口汇总（按任务归口）

- ✅ #23–#36 + #8 全批闭环（RAG 分层/入库/矫正数据链 + E1/E2/E3 + D-P2 部署验证）；全量基线 **701 passed, 1 skipped, 0 failed**；验收报告 `docs/ACCEPTANCE-REPORT-v7.md`
- 🟡 接线余量：F5 孤儿模块批（E-09）、8900 端口复制（E-10）、v6.2 底座转正细节、E-11→#8（需硬件）
- 待拍板：F1-F4 skill 池路线（E-08）、v6.1/v6.2 转正细节、版本 pin + commit 策略 + QQ 授权码轮换（决策者动作）
