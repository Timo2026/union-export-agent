# MANIFEST.md — Union Export Agent 标注包清单（annotated package manifest）

**唯一交付主干（canonical）**：`union-export-agent-livekernel/`
**方案代号**：`UEA-NCPAAI-v7.1.0-livekernel` · **版本**：7.1.0 · **日期**：2026-09-24
**对齐**：NCP-AAI 工业 AI 协议（Agentic AI）· NemoClaw 混合（Skills + Dispatcher + OpenShell）· 冻结架构 v1.0
**验收**：本地 `pytest 896 passed / 2 failed / 1 skipped`（2 例失败 = `webui-dist` 未跟踪 React 构建产物标题断言，v7.0 起既存债，与 Item6 无关，Q1 决议仅报告不动 webui）· demo live/offline · S1–S5+M1 经 SkillDispatcher 6/6 全绿 · Item6 五 Skill 经 6 触点注册 + 5/5 调度全绿 · 铁律① OpenShell 复合锁

> 本文件是包的"标注索引"：每个模块/文件的角色、依赖、是否确定性、降级行为。
> 六条工程铁律见 README； 边界见 docs/GPU-PLATFORM-MAPPING.md。


---

## 1. 入口 / 组装

| 文件 | 角色 | 备注 |
|------|------|------|
| `bootstrap.py` | 组装根：从 config 构建 CATController | `build_controller()` / `status()` |
| `requirements.txt` | 依赖（主干极简 + API + 可选解析） | 重依赖由引擎 .venv 提供 |
| `scripts/start_engine.py` | 启动制造内核 :7862 | 用引擎 .venv 跑 `app.main:app` |
| `scripts/start_api.py` | 启动上传端口 API :8900 | `uvicorn services.api_server:app` |
| `scripts/run_demo.py` | 黄金链 S1–S5+M1 演示 | `--offline` 强制离线内核 |
| `scripts/demo_uploads.py` | 全模态上传端口演示 | 无服务则用 TestClient |
| `scripts/build_notebooks.py` | 生成 9 个 notebook | 避免手写 JSON |
| `scripts/verify_notebooks.py` | exec 逐格验证 notebook | 本机无 ipykernel |
| `scripts/asr_cli.py` | 中文 ASR CLI (faster-whisper 子进程, vidproc 独立解释器) | `FunASRAdapter` cli 模式唯一活链: occ 内无 ASR 引擎 + omni 只吐英文 caption | exit 0=转写; 2 参数错/3 引擎缺/4 转写失败/5 空 |
| `一键启动.bat` / `一键自检.bat` | Windows 一键脚本 | 见 §6 |

## 2. adapters/ — 真实后端接线（Replace the adapters, not the architecture）

| 文件 | 角色 | 确定性 | 降级 |
|------|------|--------|------|
| `timo_adapter.py` | 制造内核：在线 :7862 / 离线 vendored kernel | ✅ byte-identical | 离线子进程 import 真实 calc_quote+ConflictChecker |
| `_kernel_bridge.py` | 离线桥：引擎 .venv 跑 conflict_check/calc_quote/step_geometry/step_features | ✅ | 只用真实代码，无示意系数 |
| `funasr_adapter.py` | 多模态：ASR/RAG/VLM(节点 :8002 Omni + :8011 Embed; ASR 另走 scripts/asr_cli.py cli 子进程) | 感知层 | 离线/失败显式 MOCK，不冒充 |

## 3. agents/ — 控制回路 A（CAT）

| 文件 | 角色 |
|------|------|
| `cat_controller.py` | Supervisor 编排：Email/Voice/STEP→Intake→Context→RFQ→DFM→Quote→Commercial→Verify→HITL/Reply→CRM→Audit；接入 Guardrails+Tracer |

## 4. services/ — 业务/平台层

| 文件 | 角色 | 确定性 |
|------|------|--------|
| `context_engine.py` | L8 全链路唯一上下文 + canonical evidence | ✅ |
| `rfq_state_machine.py` | 控制回路 B：业务状态机（非法转移拦截） | ✅ |
| `intake.py` | 结构化 RFQ 抽取 + 语音 claim + 多模态冲突检测 | ✅ 规则 |
| `file_intake.py` | 全模态解析器（.eml/STEP/音频/PDF/Excel/图片） | ✅ |
| `verification.py` | 辟·牟·援·推·止 + HITL 门禁 | ✅ policy |
| `commercial.py` | P1 freight/customs/Incoterms→landed cost | ✅ 费率表 |
| `postmortem.py` | P3 闭环复盘 + 客户记忆召回 | ✅ |
| `guardrails.py` | P2 输入/工具/输出三段护栏（强制执行） | ✅ 规则 |
| `observability.py` | P2 OTEL 风格 trace/span + metrics | ✅ |
| `model_router.py` | P2 Model Mesh 角色→local/NIM/mock | ✅ |
| `model_config.py` | **v2.1.1** 模型注册表管理 (UI 后端): load/save/validate/probe, deterministic 锁定 | ✅ |
| `agent_spec.py` | P2 agent.yaml 加载 + 自洽校验 | ✅ |
| `llm_planner.py` | **v2.1 P0** ReAct + 提示工程 + JSON-Schema 绑定 + LLM 工具选择（提议; 引擎裁决） | LLM 感知/规划 |
| `resilience.py` | **v2.1 P1** 指数退避重试 + 熔断器三态 + 超时 + fallback | ✅ |
| `schema_validator.py` | **v2.1 P1** jsonschema 运行时校验 RFQ/quote/context | ✅ |
| `security.py` | **v2.1 P1** 路径穿越防护 + 大小上限 + PII/凭证脱敏 + 令牌桶限流 | ✅ |
| `audit.py` | SHA-256 链式审计（tamper-evident） | ✅ |
| `reply.py` | 英文回复草稿（draft_only，不定数字） | 模板 |
| `crm_memory.py` | CRM + Fact/Episodic 记忆（SQLite，线程安全） | ✅ |
| `rag.py` | 历史经验检索（援） | funasr/内置兜底 |
| `config.py` | YAML 配置加载（禁止硬编码） | ✅ |
| `api_server.py` | 全模态上传端口 + PRD§13 + P1/P2/P3 端点（FastAPI） | — |

### 4b. evaluation/ — v2.1 P2 评估体系

| 文件 | 角色 | 确定性 |
|------|------|--------|
| `metrics.py` | 字段/工具准确率·任务完成率·报价偏差·消融·A/B + evaluate_controller | ✅ |
| `rag_eval.py` | RAGAS 风格 faithfulness/context_precision/context_recall/answer_relevancy（词法代理+可选 LLM judge） | ✅ |

## 5. config / schemas / deploy / data

| 路径 | 角色 |
|------|------|
| `config/settings.yaml` | 端点/路径/后端（timo/funasr/model_router/storage/guardrails/observability） |
| `config/policy.yaml` | 业务红线（公差 HITL 等级/毛利/金额门禁/DFM/多模态/外发） |
| `config/commercial.yaml` | 商业费率表（运费/关税/VAT/保险/Incoterms/时效/de minimis） |
| `config/agent.yaml` | nemo-agents-spec-v1 部署契约 |
| `config/models.yaml` | **v2.1.1** 模型注册表 (LLM/VLM/Embedding/OCR/ASR/DETERMINISTIC + funasr 网关), UI 可编辑 |
| `config/prompts/*.yaml` | **v2.1 P0** 提示模板+few-shot（rfq_extraction/reply_draft/summarize/translate/tool_selection） |
| `config/guardrails/nemo/` | **v2.1 P3** NeMo Guardrails colang（config.yml + rails.co，backend 可切 nemo） |
| `schemas/rfq.schema.json` · `context.schema.json` | 数据契约（v2.1 起运行时强制校验） |
| `deploy/Dockerfile` · `docker-compose.yml` · `k8s.yaml` · `profiles.yaml` | Profile A/B/C/D 部署 |
| `deploy/hpa.yaml` · `grafana-dashboard.json` | **v2.1 P3** K8s HPA + Prometheus ServiceMonitor/Rule + Grafana 看板 |
| `data/golden_scenarios.json` · `data/eval_set.json` | 验收集 S1–S5+M1 + 评估/RAG 黄金集 |
| `data/samples/` | 真实 .eml + .STEP 样本 |
| `data/{contexts,traces,demo,artifacts}` · `*.sqlite3` | 运行产物（.gitignore 排除） |

## 6. tests / notebooks / docs

| 路径 | 角色 |
|------|------|
| `tests/` | **245** 项：golden13 + upload_api24 + commercial12 + postmortem7 + guardrails15 + observability6 + model_router6 + agent_spec12 + planner12 + resilience10 + schema8 + security13 + evaluation13 + model_config12 + models_api6 + **supplier_pipeline99**（desensitize15+supplier_db12+matcher16+state_machine12+inbox7+po7+auto_threshold7+outsource6+skill_registry6+pipeline11） |
| `notebooks/00–13` | **14** 个可运行演示（环境自检/黄金链/CAT/Hero/上传端口/商业层/闭环/护栏可观测/部署/**供应商流水线**） |
| `docs/` | README·ARCHITECTURE(+frozen)·PRD(frozen)·INTEGRATION·VERIFICATION-REPORT·-MAPPING·DEPLOYMENT·**SUPPLIER-PIPELINE** |

## 7. 外部依赖（不在本包内，运行时需要）

| 依赖 | 位置 | 用途 | 缺失时 |
|------|------|------|--------|
| cnc-ai-brain v12 引擎 | `_timo_engine/Timo_CNC-AI-Brain-v12.0-Fusion - 副本/`（含 .venv） | 在线 :7862 + 离线 vendored kernel + STEP OCP 几何 | 在线不可达→离线兜底；离线兜底需引擎 .venv |
| funasr-gui | `C:\Users\<user>\funasr-gui` | ASR/RAG/VLM 多模态 | 显式 MOCK 降级 |

---

## 10. supplier_module/ — **v2.3.0 NEW** 客户确认后履约子系统

> **客户面前**（v2.0–v2.2）→ 报价给客户；**工厂背后**（v2.3.0）→ 把订单分派给供应商。
> 由 `customer_confirmed=true` 事件触发，独立状态机+独立持久化，与主 RFQ 状态机解耦。

| 文件 | 角色 | 确定性 |
|------|------|--------|
| `supplier_module/desensitize.py` | 数据脱敏硬门禁：STEP OCP header / PDF /Info / 标题栏 / 文件名 → 客户指纹 SHA-256 | ✅ 规则 |
| `supplier_module/supplier_db.py` | SQLite schema v1.0 + 10 家种子（domestic/asia/europe/north_america） | ✅ |
| `supplier_module/matcher.py` | 7 维加权打分（材料/工艺/交期/产能/质量/评分/地区）+ TopN | ✅ |
| `supplier_module/state_machine.py` | 8 状态子状态机（PENDING→…→CONFIRMED/FAILED）+ IllegalTransitionError + JSON 持久化 | ✅ |
| `supplier_module/supplier_inbox.py` | MockInbox(默认) + IMAPInbox(默认 raise NotImplementedError，需 enabled=True) | ✅ |
| `supplier_module/po_generator.py` | PO dataclass + text，markup_pct 独立计算（不与 final_price 利润双算） | ✅ |
| `supplier_module/auto_threshold.py` | AUTO 阈值判定：features_count<10 && route<10（叠加非替换） | ✅ |
| `supplier_module/orchestrator.py` | 端到端一条龙：desensitize→match→quote→select→PO→confirm | ✅ |
| `data/suppliers.sqlite3` | 10 家样本数据（commit 入包） | ✅ |
| `skills/supplier-match/SKILL.md` | 第 5 个 Agent Skill，OpenAI function-calling 工具描述 | ✅ |
| `config/policy.yaml:auto_quote_threshold` | 新增阈值配置（叠加非替换） | — |

## 11. v2.3.1 — A/B 路由 + Fallback（模型设置工具升级）

> 在不重启的前提下切换同一角色的接入拓扑：主端点 / 备用端点 / 兜底端点按策略分流。
> **铁律①保持**：DETERMINISTIC 不可参与 A/B，锁定走 Timo 内核；后端 validate + UI 不渲染双向守护。

| 文件 / 字段 | 角色 | 确定性 |
|------|------|--------|
| `services/model_config:choose_route` | 4 策略决策：`primary_only` / `fallback` / `ab_hash`(SHA-256 稳定分流) / `ab_round_robin`(counter 交替) | ✅ 规则 |
| `services/model_config:_hash_pick` | SHA-256(key + "|" + request_id) 取首字节 mod 2；同 id 永远同选 | ✅ |
| `services/model_config.validate` (扩展) | ab_test/fallback 结构 + alternate 协议 + deterministic 不可 A/B 校验 | ✅ |
| `services/model_config.probe_all` (扩展) | 配置了 alternate/fallback 时额外探活并返回 `{online, latency_ms, endpoint, model, strategy}` | — 网络 |
| `services/model_router` (扩展) | `resolve(role)` / `pick(role, request_id=None)` 接入 `choose_route`；返回 `source` / `strategy` | ✅ |
| `config/models.yaml` (entry 级) | 可选 `ab_test: {strategy, alternate:{endpoint,model}}` + `fallback:{endpoint,model}` | — |
| `webui/index.html` (A/B 折叠面板) | 每张非确定性卡：策略 dropdown + alternate 输入 + fallback 输入 + 状态徽章 | ✅ UI |
| `tests/test_model_config_ab.py` (20) | validate / choose_route / probe_all 全覆盖 | ✅ |
| `tests/test_models_api.py` (+1 UI smoke) | HTML 含 v2.3.1 + 4 策略 + 确定性卡无 ab-* input id | ✅ |

**策略语义**：
- `primary_only` — 只用主端点；离线则调用方按 plan 降级（不冒充）。
- `fallback` — 主端点离线时切到 `fallback.endpoint`；正常仍走主端点。
- `ab_hash` — 同 `request_id` 永远落到同一边（用户体验一致 + 评估可比）。
- `ab_round_robin` — 进程内 counter 交替；适合无状态压测。

**铁律**：
- `DETERMINISTIC` 在 validate / UI 两层均拒绝 ab_test / fallback 字段；`router.resolve("DETERMINISTIC")` 直接绕开 `choose_route` 永远走 Timo。
- `choose_route` 不做 HTTP 重试，只返回 endpoint/model 决策；调用方负责真探活。

> 收敛说明：本主干是**唯一 canonical 交付**；同目录下其它 `union-export-agent*` / `*_FINAL*` / `00_*` 等为并发会话产物，非本包内容。

## 12. v2.4.0 — 控制台重设计 · 反馈邮箱 + 3D STEP 上传

> 在不破坏 v2.3.1 A/B 路由与确定性铁律①的前提下，把"用户高频能力"补齐到控制台：
> 参考 V12 信息密度 + OLED 暗色工程控制台风格；模型设置卡完全保留。

| 文件 / 字段 | 角色 | 确定性 |
|------|------|--------|
| `services/feedback_store.py` | SQLite：`submit / list_recent / count_unread`；type ∈ {bug,feature,consult,other}；title 2-200；body 5-5000；email 正则；蜜罐 `website`；IP 滑窗 5/min/60s | ✅ 规则 |
| `services/api_server.py`（+3 endpoints） | `POST /v1/feedback`、`GET /v1/feedback?limit&status`、`GET /v1/feedback/unread` | ✅ |
| `services/step_thumbnail.py` | 8 顶点等角投影 SVG；`make_thumbnail(timo, path, use_cache=True)`；sha256[:16] 缓存到 `data/thumbnails/`；引擎失败降级 SVG | ✅ |
| `services/api_server.py`（+1 endpoint） | `POST /v1/upload/step-with-thumbnail` (.step/.stp) | ✅ |
| `webui/index.html`（重设计） | 5 个 nav tab + header `🆘反馈` 按钮 + 未读 badge；Lucide 风格 inline SVG icons；`#tab-threeD` 拖拽 + accept；`#tab-feedback` 表单 + 蜜罐 + mailto | ✅ UI |
| `.gitignore`（+1 行） | `data/feedback.sqlite3` 不入库 | ✅ |
| `tests/test_feedback_store.py` (16) | init / submit / 字段长度 / 未知 type / 坏 email / 蜜罐 / 限流 / list desc / status 过滤 / unread 计数 / 可选 email / UA 截断 | ✅ |
| `tests/test_step_thumbnail.py` (9) | fallback / 真实几何 / cache 命中 / cache 关闭 / 文件不存在 / 不同文件不同 sha / bbox→svg / 空 bbox / fallback_svg 文本 | ✅ |
| `tests/test_models_api.py` (+4) | UI 5-tab+SVG smoke / feedback 三端点 roundtrip / 短字段拒绝 / 非法 type+email 拒绝 | ✅ |

**P0（必须）** — 反馈邮箱 / 3D 上传 / 5 tab 导航 / SVG icons / header 反馈按钮
**P1（增强）** — 顶部状态 pill 颜色 / 首屏 6 大能力可视化 / 1080p 单屏可达
**P2（可选）** — 缩略图缓存命中提示 / 反馈历史侧栏 / CSS 变量双主题（[data-theme]）

**铁律延伸**：
- 反馈邮箱数据 `data/feedback.sqlite3` 在 `.gitignore`，本机反馈永不入库；
- STEP 缩略图缓存 `data/thumbnails/` 同样不入库；
- 控制台所有模型设置卡的 v2.3.1 A/B 折叠面板未受影响，4 策略继续生效；
- DETERMINISTIC 锁定逻辑在 validate / UI / router.resolve 三处继续生效。

**回归**：326 passed, 1 skipped（v2.3.1 的 285 → v2.4.0 的 326，+41 passed；2 个预存在 OpenBLAS memory failures 与本次改动无关 — 在 v2.3.1 baseline stash 上同样失败）。

## 13. v3.0.0 — NemoClaw 混合架构（方案 C）

> Skills 全封装 + Dispatcher 智能/规则路由 + OpenShell 铁律守护 + webui 第 6 tab 设置面板。
> LLM 只决定「调用哪些 Skill」，不决定确定性 Skill 的输出。

| 文件 / 字段 | 角色 | 确定性 |
|------|------|--------|
| `config/skills.yaml` | Skill 启停 + Dispatcher 策略 + OpenShell 开关 | ✅ 配置 |
| `openshell/iron-rule-1.yaml` | 确定性输出锁定（**locked 不可关**） | ✅ |
| `openshell/hitl-required.yaml` | 金额/风险/DFM/验收 → HITL | ✅ |
| `openshell/local-only.yaml` | 文件路径沙箱 | ✅ |
| `openshell/skill-allowlist.yaml` | Skill 白名单 | ✅ |
| `services/skill_config.py` | 配置 load/save/validate（强制 iron-rule-1） | ✅ |
| `services/openshell.py` | 策略引擎：precheck/postcheck/override 拒绝 | ✅ |
| `services/skill_dispatcher.py` | 意图路由 + 编排 + 审计 | ✅ 规则 / LLM 提议 |
| `skills/_runtime.py` + `skills/*/tool.py` | 10 个可执行 Skill 封装 | 包装既有确定性服务 |
| `services/api_server.py`（+4） | `/v1/skills/config` · `/v1/agent/task` · `/v1/agent/route` · `/v1/agent/openshell` | — |
| `webui/index.html` `#tab-skills` | 设置面板：策略/OpenShell/Skill 启停/试调度 | ✅ UI |
| `tests/test_openshell_policies.py` (10) | YAML/铁律/沙箱/HITL/override | ✅ |
| `tests/test_skill_dispatcher.py` (17) | 路由/拦截/API | ✅ |

**设置功能（用户要求）**：
- Dispatcher：`auto` / `rules_only` / `llm` + LLM 来源 `models_yaml`（沿用 v2.3.1 A/B）/ `rules_only`
- OpenShell：4 策略 enable；**iron-rule-1 locked UI 不可关**
- Skill：逐个 enable/disable；deterministic 标注 iron-rule-1
- 试调度：webui 内 intent → trace / hitl / violations / 审计

**铁律①落点**：OpenShell `attempt_override` 在 dispatch 后用 sha256 拒绝确定性输出改写；save API 对关闭 iron-rule-1 返回 400。

**回归**：354 passed, 1 skipped（v2.4.0 326 → v3.0.0 354）。

## 14. v3.0.1 — 邮件工作台 · Gmail IMAP + HITL 审批 + V12 仪表板 + 跨区跳转

> Gmail 主入口从"上传 .eml"工作流升级为 IMAP 真接入 + 9 区聚合 + 铁律① 篡改拦截。
> 不破坏 v3.0.0 NemoClaw / v2.3.1 A/B / v2.4.0 控制台风格；后端零发明，全部复用现有 `services.crm_memory / commercial / verification / file_intake / reply` 等模块。

| 文件 / 字段 | 角色 | 确定性 |
|------|------|------|
| `services/credentials.py` (NEW) | Fernet AES-128-CBC + HMAC-SHA256 加密存储 App Password；machine-stable key (MAC+hostname sha256[:16])；data/credentials.json 0600 权限；降级 base64-insecure 显式标记 | ✅ |
| `services/gmail_imap.py` (NEW) | GmailMailbox (connect/sync/status/disconnect)；imap_tools (Apache-2.0) 封装；mock factory 注入；idempotent；mail_id = `gmail_<sha256[:16]>`；.eml+.meta.json 双写；badges 含 GMAIL_PULLED | ✅ 规则 |
| `services/v12_status.py` (NEW) | V12Status: kernel_online + calc_quote_total/p50/p95 + dfm C1-C6 + sha256 审计 + recent_spans；data/traces/*.jsonl 聚合 | ✅ |
| `services/gmail_api.py` (NEW router) | GET/POST /v1/gmail/{settings,connect,disconnect,sync,status} (5 endpoints)；默认 enabled=False；显式开启 + connect 才能用 | ✅ |
| `services/v12_api.py` (NEW router) | GET /v1/v12/{status,audit,dfm} (3 endpoints) | — |
| `services/mailbox_api.py` (+1 endpoint) | GET /v1/mail/{mid}/context/hitl: draft + quote + quote_sha16_locked + locked + can_approve；iron-rule-1 **持久锁** (data/drafts/{cid}.json 存首次 sha16) | ✅ 规则 |
| `services/api_server.py` (注册新 router) | `app.include_router(gmail_router)` + `app.include_router(v12_router)` | — |
| `webui/index.html` (F-1 ~ F-4) | #tab-v12 仪表板 + Gmail 连接条 + HITL 审批面板 (🔒/🔓 sha16-12) + 跨区跳转 + 7-pill 面包屑 (#mailCrumb) | ✅ UI |
| `data/mailbox/demo_test_001.{eml,meta.json}` | 演示邮件 (alice@acme.com → RFQ-20260917-00CA3C, HITL) | — |
| `data/credentials.json` (per-machine) | Fernet 加密凭据，0600 权限 | ✅ |
| `tests/test_credentials.py` (8) | save/load 往返 / mask / delete / list / status / 缺参 / 损坏 JSON | ✅ |
| `tests/test_gmail_imap_api.py` (8) | GmailMailbox 4 + Gmail API 4 (mock imap_tools) | ✅ |
| `tests/test_v12_status_api.py` (9) | 空 traces / calc_quote+dfm 聚合 / p50+p95 / audit / Timo fallback + 4 API | ✅ |
| `tests/test_hitl_endpoint.py` (6) | 无 cid / 缺 ctx / PASS / HITL / 篡改 quote / sha16 稳定 | ✅ |
| `tests/test_mailbox_ui_49.py` (8) | UI 符号静态 smoke (跨区跳转 + 面包屑) | ✅ |

**铁律①落点**：
- Gmail IMAP：默认 disabled；settings POST 后才能 connect；连接失败返回 ok=false 不静默冒充
- HITL 篡改拦截：`mail_context_hitl` 读 `data/drafts/{cid}.json` 的首次 `quote_sha16_locked` 与当前 `quote_sha16` 比较；不等 → `locked=false, can_approve=false`；UI 弹红字 banner "iron-rule-1 violation: 锁定 hash X ≠ 当前 hash Y, 已拒绝批准"
- 凭据加密：Fernet (AES-128-CBC + HMAC-SHA256)；data/credentials.json 0600 权限；machine-stable key

**回归**：417 passed, 1 skipped（v3.0.0 354 → v3.0.1 417，+63；其中 39 个新增 + 24 个老测试因 iron-rule-1 修复而多覆盖）

**Verified (E2E)**：
- 19 个 GET 端点 + 5 个 POST 端点 + ROOT 全 200
- 浏览器 DOM 验证：面包屑 7 pills 渲染 + focusRegion/focusHITL 高亮 + openContext 跨邮件跳转
- 篡改 context.quote.unit_price → locked=false → banner 触发


---

## 15. v6.1.0 — 核心场景全通 SkillDispatcher · 铁律①复合锁 · Skill 层补齐 (25/25)

> 修复独立测评 (AUDIT-REPORT-v6 / EVAL-REPORT-v6-expert) 与实跑基线的 4 个 P0 + 2 个 dispatcher 深层 bug。
> S1–S5+M1 六大黄金场景**首次全部经 `SkillDispatcher` 跑通 6/6**（此前仅直连 CATController 验证过）。
> 架构决策：分层模块 skill 化 — skills 层 = 能力接口，services 层 = 业务真相（铁律⑥）；不装外部功能包。
> 铁律① 边界不变：SMTP/IMAP/OAuth 外发默认禁，`external_send: draft_only`。

| 文件 / 字段 | 角色 | 确定性 |
|------|------|------|
| `services/agent_cache.py` (FIX) | get/set 均 `copy.deepcopy` — 调用方突变返回 dict 不再污染缓存（BUG-1 根因：nim_health 写 `_cache` 键） | ✅ |
| `services/api_server.py` (FIX) | `app.mount("/css"/"/js", StaticFiles)`（B1 静态资源 404）；FastAPI `version="6.1.0-livekernel"` + health `v6.1.0-livekernel`（B3 版本统一） | — |
| `services/schema_validator.py` (FIX) | `_light()` 兜底改递归校验：type/enum/required/properties 路径标注（B4 — jsonschema 缺席时 enum 不再静默放行） | ✅ |
| `services/asr_engine.py` + `services/intake_pdf.py` (FIX) | `subprocess.run(..., encoding="utf-8", errors="replace")`（BUG-3 Windows cp1252 中文乱码） | ✅ |
| `services/openshell.py` (FIX) | 铁律①锁键 `lock_key(skill_id, args)` = `skill_id:sha256(args)[:16]` 复合键；`postcheck(..., args=None)` 向后兼容 — 同 skill 不同输入的合法差异不再误报"确定性输出被改写"（dispatcher bug B） | ✅ 规则 |
| `services/skill_dispatcher.py` (FIX) | `_build_args` body 优先级 `email_text > intent`（bug A：路由短语顶掉 RFQ 正文）；postcheck 传 `args=call_args`；golden_chain 透传 `voice_transcript` | ✅ 规则 |
| `skills/golden-chain/tool.py` (FIX) | `voice_transcript` 参数 → `CATController.run`；result 透出 `multimodal_conflicts` — M1 (Email±0.02 vs Voice±0.05) 正确升级 HITL / VOICE_EMAIL_CONFLICT | ✅ |
| `skills/cnc-quote/tool.py` (NEW) | 确定性 CNC 报价 skill（BUG-4：有 SKILL.md 无 tool.py）；在线 :7862 / 离线 byte-identical；铁律① LLM 不生成价格 | ✅ 确定性 |
| `skills/_runtime.py` (FIX) | `get_register_meta` ID 三轨解析（原样/下划线/连字符）；`_load_tool` 连字符键装饰器 meta 合并进规范下划线 sid（`alias_of` 标注） | — |
| `scripts/count_skills.py` (NEW) | skill 数字单一来源（`--json`）→ **25/25 全带 tool.py, 0 缺失** | ✅ |
| `index.html` (FIX) | 根融合版 5 处 marker v6.0.0 → v6.1.0 | ✅ UI |
| `webui/index.html` (FIX) | 副标题 bump `v6.1.0-fusion · 全场景经 SkillDispatcher · 铁律①复合锁 · voice 透传 · 缓存隔离修复` | ✅ UI |
| `tests/test_mailbox_ui.py` (7) + `tests/test_models_api.py` (FIX+1) | v5 工作台断言 `/` → `/webui`（BUG-2）；新增 `test_static_assets_mounted`；副标题断言兼容 v6.1.0-fusion | ✅ |
| `tests/test_v6_root_index.py` (FIX) | 根路由断言兼容 v6.1.0 融合版 | ✅ |
| `.gitignore` (FIX) | 排除 `tools/`（6.3GB NovaStudio）+ `.tmp/` `.dumate/` `.image_gen/` `.codeartsdoer/` | — |

**铁律①落点（本版新增）**：
- 复合锁键：确定性 skill 输出锁按 `(skill_id, 输入指纹)` 隔离 — 跨 dispatch 不再误报篡改，同输入改写仍拦截（`test_iron_rule_override_blocked_in_dispatch` / `test_openshell_blocks_deterministic_override` 契约不破）
- M1 多模态冲突（铁律⑤）经 skill 层可复现：`voice_transcript` 透传后 `multimodal_conflicts=['VOICE_EMAIL_CONFLICT']` → HITL
- cnc-quote 补齐后价格唯一权威来源仍为 Timo 确定性引擎，`_source` 可溯源（live:/api/quote 或 offline:calc_quote）

**回归**：529 passed, 1 skipped, 0 failed（实跑基线 517 passed / 11 failed → 全绿）

**Verified (E2E)**：
- 6 场景 dispatcher smoke：S1/S2/S4 PASS · S3 BLOCKED · S5/M1 HITL，FAILS=0，route 全部 `['golden_chain']`
- cnc-quote 实跑：6061×50 → unit_price 172.8，`_source=offline:calc_quote`
- `scripts/count_skills.py --json`：total 25 / with_tool 25 / missing_tool []

## 16. v6.3.1 — omni 融合增量（叙事证据 + G1/G2 补齐）

> 对照外部「邮件驱动 AI 报价客服」方案（Dify/n8n/OpenClaw/RAGFlow + 4 GitHub 参考项目）的逐环差距；
> 融合边界：只融叙事/证据/素材，禁接外部仓代码，Dify/n8n 不作系统本体（铁律①冲突 + 双系统真相 + 环境约束）。
> 铁律①不变：LLM 不生成最终数字；SMTP/IMAP/OAuth 默认禁；draft_only；确定性输出 sha 锁。

| 文件 / 字段 | 角色 | 确定性 |
|---|---|---|
| `docs/PRIOR-ART-v8.md` (NEW) | 外部方案逐环 file:line 对照 + G1-G4 缺口 + 融合边界判定 | ✅ 文档 |
| `README.md` §5 生态定位 (NEW) | 外部主流做法 ⇄ 本仓实现差异表 + 缺口诚实标注 | ✅ 文档 |
| `services/hitl_escalation.py` (NEW) | G1: HITL 超时扫描 + 备用审核人升级通知（只通知不代审）+ 去重窗口 + 审计 | ✅ 规则 |
| `config/policy.yaml` `hitl.timeout_hours` / `hitl.backup_approvers` | G1 策略单源（默认 2h / 空列表仅落审计） | ✅ 配置 |
| `services/mail_puller.py` `PendingEntry.hitl_since` / `escalated_at` | G1 计时起点 + 升级去重标记（旧行回退 queued_at 兼容） | ✅ |
| `services/mail_orchestrator.py` `_escalate_overdue_hitl` | G1: loop 每周期扫描，异常不崩 loop | ✅ |
| `services/quote_pdf.py` (NEW) | G2: 报价 PDF 渲染（platypus）+ content_sha256 锁 canonical 载荷 + CJK 字体 | ✅ 规则 |
| `skills/write-reply/tool.py` (+attach) | G2: 草稿附件接线，异常显式 `attachment_error` 不静默 | — |
| `tests/test_hitl_escalation.py` (12) | 策略 / 计时 / 去重 / 审计 / 绝不代审 | ✅ |
| `tests/test_quote_pdf.py` (8) | 渲染 / sha 稳定 / no_price / reportlab 缺失降级 / skill 端到端 | ✅ |
| release 标记 | README 标题 / 根 index.html / webui 副标题 / api_server version+health / MANIFEST / CHANGELOG 统一 v6.3.1 | ✅ |

**铁律①落点（本版新增）**：
- G1 升级只发通知（`kind="hitl_timeout"`, `action_required="approve_or_reject"`, `draft_only`），
  状态机仍须人工 `POST /v1/rfq/{cid}/approve`；`escalate_overdue` 无任何批准写路径
- G2 `content_sha256` 锁的是 canonical 报价载荷 JSON（context_id/客户/物料/数量/单价/总价/交期/引擎来源），
  不锁 PDF 字节（reportlab 内嵌 CreationDate 时间戳）；`data/artifacts/` gitignore 不入库

## 17. v6.3.2 — 节点 Profile 实测口径化 + Embed-1B 接线

> 让 GB10 Spark 节点部署真正跑通：rag_layers 接 Embed-1B 非对称双塔，节点 Profile 配置全量对齐实测拓扑
> （Omni :8002 / Embed :8011 / 30B :8000 / Timo :7862，4B 不驻 · user Q1）。
> 铁律①不变：DETERMINISTIC 永远 Timo；egress 全 DENY；节点配置零密钥/零公网 IP 字面量。

| 文件 / 字段 | 角色 | 确定性 |
|---|---|---|
| `services/rag_layers.py` `HybridEmbedder` (model/query_prefix/passage_prefix + embed kind) | Embed-1B 非对称双塔接线：query/passage 前缀（缺则排序错 0.3758 vs 0.5209）+ source 如实带 url | ✅ 规则 |
| `agents/cat_controller.py` (embed_model/前缀透传) | 从 rag_layers 配置构造 HybridEmbedder，单源不硬编码 | ✅ |
| `config/models.node.yaml` (NEW) | 节点运行时模型注册表 = backend=local 真正路由源（choose_route 读 models.yaml，不读 settings.roles）；T5 覆盖节点 config/models.yaml | ✅ 配置 |
| `config/settings.dgx-spark-nvidia.yaml` (重写 v4) | 节点 Profile ops 覆盖源（config.py 只读 settings.yaml，本文件不被代码加载）；实测口径，无 Windows/开发机/NIM 容器端口 | ✅ 配置 |
| `tests/test_node_profile_overlay.py` (16) | 钉死覆盖源实测口径 + models.node.yaml schema/choose_route/ModelRouter 端到端 | ✅ |
| release 标记 | README 标题 / 根 index.html / webui 副标题 / api_server version+health / MANIFEST / CHANGELOG 统一 v6.3.2 | ✅ |

**铁律①落点（本版复核）**：节点 Profile egress 仍全 DENY；DETERMINISTIC 在 models.node.yaml `locked+enabled` 锁死 Timo :7862；节点配置不含任何密钥/密码/公网 IP 字面量（仅 127.0.0.1 本地端口）。

## 18. v7.0.0 — B 端后台重设计 · 六大工作台控制台

> 工业非标外贸 B 端后台全新设计：no-build ES Modules 控制台（`webui/console/`），六大工作台 =
> 邮件 / 订单 / 图纸（真 3D）/ 客户情报（RAG+联网+多模态库）/ 模型设置 / 本地状态。
> 订单升级为独立实体（状态机 询盘→报价→样品→批量→发货→完结，非法迁移 409）；
> 旧单文件 UI 保留在 `/webui/v5`。铁律①不变：全端点经 `mockScan` 递归检测 + MOCK badge，绝不冒充在线。

| 文件 / 字段 | 角色 | 确定性 |
|---|---|---|
| `services/orders_store.py` + `services/orders_api.py` (NEW) | 独立订单实体：JSON 落盘 + 状态机 + 服务端筛选/排序/分页/批量；`/v1/orders` 新路由遮蔽旧 context 聚合 | ✅ 规则 |
| `webui/console/` (NEW, index.html + css + js/api,ui,mesh3d,app + tabs/×6 + vendor/three.min.js) | 六工作台控制台：hash 路由 + 懒加载 tab + 统一表格组件（筛选/批量/分页/空态）+ three.js 真 3D 网格查看器 | ✅ |
| `js/api.js` `mockScan/mockBadge` | 铁律①可视化：`_mock/mock/degraded=true` 或 `source/_url` 命中 `MOCK:`/`-offline`/`-error` → 每个面板挂 amber MOCK badge | ✅ 规则 |
| `services/api_server.py` `/v1/drawings/{id}/mesh` + `/v1/thumbnails/{sha}.svg` + `/webui` 与 `/webui/v5` 路由 | 3D 网格端点（base64 Float32/Uint32）+ sha256-16 缩略图查表 + 控制台挂载（StaticFiles mount 先于通配路由） | ✅ |
| `services/mailbox_api.py` geometry 区 `thumb_url` | 邮件附件几何 → 缩略图 URL 真实回链（缺失则 null，不造假） | ✅ |
| `webui/console/js/vendor/three.min.js` | vendored（r~135，出自 CNC zip app/static/），本地离线可跑 | ✅ |
| `tests/test_console_ui.py` (5) + `tests/test_orders_api.py` (21) | 控制台 shell/资产/六 tab 端点接线断言 + 订单状态机/迁移/批量/分页断言 | ✅ |
| release 标记 | README 标题 / 根 index.html / webui 副标题 / api_server version+health / MANIFEST / CHANGELOG 统一 v7.0.0 | ✅ |

**验收**：本地 pytest 891 passed / 1 skipped（全量约 7.3 分钟）；:8900 活体冒烟 /health v7.0.0-livekernel、/webui 200、/v1/orders 真数据、media/status 诚实 offline。
**已知边界**：本机无 Chrome，浏览器端渲染（ESM 加载、three.js 绘制）未经视觉验证——仅 `node --check` 语法门 + TestClient 内容断言。

## 19. v7.1.0 — Item6：策展知识层 + SOP/reid 联动 Skill 按 NVIDIA AgentSkills 标准注册 OpenClaw

> 遍历 `C:\Users\<user>\Videos\skill\skill`（含 `reid-operating-system`）外部 skill 目录，**只蒸馏知识、绝不执行外部运行时、绝不复制作者本地路径**（`/home/<user>/...` 等一律剔除，P0-B.4 脱敏铁律）。
> 产出 5 个确定性策展 Skill（material-knowledge / dfm-rules / process-knowledge / sop-router / reid-triage），
> 全部经 **6 触点**注册进 OpenClaw，可被 `GET /v1/skills` 列出、`POST /v1/agent/task skills:[id]` 调度。
> 铁律①不变：5 Skill 全 `deterministic`，**不定价**（终价归 `calc_quote` 唯一权威）、**不推进/改写状态机**（SOP 仅映射建议）。

| 文件 / 字段 | 角色 | 确定性 |
|---|---|---|
| `services/domain_knowledge.py` (NEW) | 蒸馏出的领域知识数据模块（材料牌号/DFM 规则/工艺路线/SOP 阶段映射/reid 分诊协议），纯数据 + 查表函数，无外部依赖 | ✅ 规则 |
| `skills/{material-knowledge,dfm-rules,process-knowledge,sop-router,reid-triage}/SKILL.md` (NEW ×5) | NVIDIA AgentSkills frontmatter（name/description/version/tool_contract.openai_function）；description 用全角 `：` 规避 YAML `: ` 扫描错 | ✅ 标注 |
| `skills/<id>/tool.py` (NEW ×5) | `run(ctx, **kwargs)` 入口，runtime `discover()` 经 importlib 逐请求扫描，无需重启即现形 | ✅ |
| `config/skills.yaml` (164-196) | 5 Skill enabled/label/description/iron_rule=deterministic/openshell 声明 | ✅ 配置 |
| `config/skill_registry.yaml` `core` (39-44) | 5 Skill 列入 core 清单（kebab-case id，iron_rule=deterministic） | ✅ 配置 |
| `services/guardrails.py` `TOOL_ALLOWLIST` (101-105) | snake + kebab 双形入白名单，供 `skill_registry.cross_check_allowlist` 在 `GET /v1/skills` 交叉校验 | ✅ 规则 |
| `openshell/skill-allowlist.yaml` `allowed` | dispatcher precheck 全局门（`OpenShell.check_skill_allowed`）；缺此触点则调度被拒"不在白名单"——本版补齐第 6 触点 | ✅ 规则 |
| release 标记 | README 标题 / 根 index.html / webui 副标题 / api_server version+health / MANIFEST / CHANGELOG 统一 v7.1.0 | ✅ |

**验收**：本地 pytest 896 passed / 2 failed / 1 skipped（2 例失败 = `webui-dist` 未跟踪 React 构建产物标题断言，v7.0 起既存债，与 Item6 无关）；`GET /v1/skills` cross_check `ok:true`，5 Skill 全 callable/enabled/deterministic；`POST /v1/agent/task skills:[id]` 5/5 执行成功（material_knowledge 命中 6061 铝合金全属性、dfm_rules risk=blocked+hitl_required、process_knowledge 4 条工艺路线、sop_router 阶段=可制造性审查+next_skills、reid_triage degraded 诚实）；override 篡改审计 `allowed:false`（铁律①复合锁拦截）。
**已知边界**：5 Skill 暂无专属 pytest 用例（经 runtime discover + 活体 dispatch 集成验证，非新增测试文件）；reid-operating-system 引擎本机未安装，`reid_triage` 走 degraded 协议路径（诚实降级，不冒充分析）。
