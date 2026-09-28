# Union Export Agent — 生产加固解决方案 (v6.0.0 → Production)

> 版本：v0.1 / 2026-09-19
> 范围：P0 / P1 / P2 全部 12 项
> 形态：方案文档（先确认，后实施）。所有路径均已对本仓库实测核实，非纯纸面推演。

---

## 一、摘要（1 页版）

v6.0.0 是一个「可跑通黄金链的工程原型」：两端（Gmail IMAP 拉信、外发审批短信）和中间（并发、持久化、配置、可观测）存在拉通缺口。本方案把生产化工作拆成 **4 个阶段 12 项任务**，每项都给出：现状（实证）→ 目标 → 落地文件/接口 → 验收标准。

**关键纠偏（与原始痛点清单不一致处，已实测）**：

| 原始说法 | 实测 | 影响 |
|---|---|---|
| tools/ 1.2GB「直接嵌入 Git，克隆慢」 | `tools/` 实际 **6.3 GB**，且 `git ls-files tools` = 0（**未入库**），git status 显示 `?? tools/` | 克隆不慢，但**误 `git add .` 会把 6.3GB 提交进库**；且 tools/ 只在开发机存在，CI/服务器拿不到 |
| 供应商"最小闭环"待建 | `supplier_module/` 已是独立实现（orchestrator / state_machine / supplier_inbox），测试 `tests/test_supplier_pipeline.py` 直接从 `supplier_module.*` 导包 | P1-1 是**接线+补验收**，不是从零建设；且 Dockerfile 未 COPY 该目录，接线时需补 |
| SMTP/Telegram/Slack「未打通」 | `services/notify/email_notifier.py` 已含真实 SMTP 路径（`_smtp_send`，`real_send=False` 兜底写 `.eml`）；`telegram.py`/`slack.py` 已是真实 API 实现 | 缺的是**接线**（orchestrator 仍走 `_default_notifier` 写 jsonl）+ 凭据入库 + 管理面开关，不是重写 |
| model 配置无法热更 | `services/model_config.load()` 每次调用现读 `config/models.yaml`，UI 保存即生效 | 热加载**已部分存在**（models.yaml）；缺的是 settings/policy/commercial 与运行时对象 |
| k8s「无蓝绿/滚动」| `deploy/k8s.yaml` 已 `replicas: 2` + readiness/liveness + PVC；`hpa.yaml` 已就绪 | 缺 `rollingUpdate` 策略、compose 侧单副本、PDB；是**补强**不是重来 |

**排序原则**：先打通「外发 + 队列」这两个数据出口与吞吐瓶颈（P0），再上持久化/可观测（P0/P1），最后接 GPU/TSA/Linux（P2），每步保持 499 pytest 全绿为回归门槛。

---

## 二、现状核实（实证快照）

| 层 | 现状 | 证据 |
|---|---|---|
| 触发 | MailPuller：Gmail IMAP 30s 轮询 → `data/pending.jsonl`；MailOrchestrator：后台 daemon **线程** 5s drain，`pending.jsonl` + 文件锁做"队列" | `services/mail_puller.py`、`services/mail_orchestrator.py:210` |
| 工作内存 | `services/api_server.py:_STORE` 为进程内 Dict（`api_server.py:119`） | 单实例、丢失即丢 |
| 外发 | 默认 `_default_notifier` 只写 `data/notifications.jsonl`；Email/Telegram/Slack 真实发送器未接线；orchestrator 的 `notifier(kind, payload)` 签名与 `NotifierBase.send(NotificationEvent)` 不匹配 | `services/mail_orchestrator.py:326`、`services/notify/*` |
| 凭据 | `services/credentials.py`：Fernet(AES-128-CBC+HMAC) 加密落 `data/credentials.json`，密钥=固定 app_secret+machine seed | 已具备，无 Vault/KMS |
| 配置 | import 时 `load_settings/load_policy/load_commercial` 一次性加载；models.yaml 已"每次现读" | `bootstrap.py:62`、`services/model_config.py:33` |
| 存储 | sqlite3（audit/crm/feedback），无迁移工具、无备份 | `config/settings.yaml:storage` |
| 可观测 | OTEL JSONL trace + 可选 OTLP（`otlp_endpoint: null`）；**无 /metrics HTTP 导出** | `config/settings.yaml:observability` |
| 部署 | compose 单副本（无 healthcheck 于 api）；k8s replicas=2 + HPA；无滚动策略/PDB | `deploy/docker-compose.yml`、`deploy/k8s.yaml`、`deploy/hpa.yaml` |
| 工具链 | `tools/` 6.3GB **未跟踪**；启动仅 `.bat` | `git status --porcelain` → `?? tools/` |

---

## 三、目标与约束

### 3.1 目标架构演进（in-process → 可扩容）

```
今天:  IMAP 线程 ─┐
       orchestrator线程 ─┼─ 进程内 _STORE ─→ sqlite ─→ jsonl 通知
       api uvicorn  ────┘

目标:  IMAP(Puller Worker) ─┐
        └─→ Redis(任务队列, 幂等键) ──→ Celery Worker(黄金链) ──→ sqlite/Postgres(Alembic)
        api uvicorn(多副本) ────────────→ Redis
        Worker 出站 → Gateway(notify 路由) → SMTP/Telegram/Slack(真实) + 失败重试/死信
        配置层 config-store(watchdog) → 各运行时订阅
        可观测 Prometheus /metrics + OTEL → Grafana
```

### 3.2 硬约束（不可破坏）

1. **铁律①**：DETERMINISTIC 报价永远走 Timo v12 / FleetCoordinator CalculationEngine，队列与并发改造不得引入 LLM 改数通道。
2. **铁律②**：状态机是业务真相；消息幂等键 = 状态机合法转移的映射，禁止绕过。
3. **铁律③**：`external_send.default = draft_only` 保持；真实外发只经 P0-1 的审批网关激活。
4. **回归门槛**：每个 Phase 交付时 `python -m pytest tests/ -q --timeout=60` 保持 499 passed / 1 skipped / 0 failed。

---

## 四、P0 方案（必做，4 项）

### P0-1 打通真实外发链路（SMTP / Telegram / Slack）

> 实测：发送器代码已齐，缺接线与门禁。

- **现状**：`services/notify/email_notifier.py` 已含 `_smtp_send()`（SMTP/STARTTLS/login）；`telegram.py` 用 urllib 走 Bot API；`slack.py` 走 Webhook。三者在 `base.py` 同一 `NotifierBase` 抽象下。MailOrchestrator 的 `_notify()` 调 `notifier(kind, payload)`，与 `send(NotificationEvent)` 签名不一致 → 从未真正触发真实发送器。
- **目标**：HITL/BLOCKED 通知经真实通道发出；draft_only 门禁保留；失败有重试与死信记录。
- **方案**：
  1. 新增 `services/notify/gateway.py` — `NotifyGateway`：
     - 把 orchestrator 的 `(kind, payload: dict)` 归一为 `NotificationEvent`（补 parse 层，唯一签名差异点）。
     - 路由 = `config/settings.yaml` 新增 `notify: {channels: [telegram, email, slack], failover: chain}`。
     - 通道连接优先链式 failover；全部失败 → 写 `data/notifications/dead.letter.jsonl`，留 `next_retry_ts`。
  2. 凭据入库：`POST /v1/notify/credentials` 复用 `credentials.py`（service 名 `smtp`/`telegram`/`slack`），支持隐藏展示（`mask_secret` 已有）。
  3. 管理面开关：`POST /v1/notify/config {enabled: true, real_send: true}`，落地 `data/notify_settings.json`；**默认 false**（保持铁律③）。
  4. MailOrchestrator 注入 `NotifyGateway` 替换 `_default_notifier`（仅当 enabled），行为变化走环境变量 `UEA_NOTIFY_REAL=1` 灰度。
  5. 测试：`tests/test_notify_gateway.py` — 签名归一、链式 failover、dead-letter、draft_only 默认守卫 4 组。

- **验收**：配置真实 SMTP/Telegram token 后，一条 HITL 邮件 → 至少一个通道收到通知；未配置时行为与今天一致（写 jsonl 成功返回）；499 回归绿。

### P0-2 引入任务队列（Celery + Redis），替换 in-process drain

> 实测：唯一"队列"是 `pending.jsonl` + 文件锁，消费在 daemon 线程内；api 的 `_STORE` 是进程内 Dict。

- **目标**：拉信、黄金链、通知三个阶段解耦，支持多 worker / 多副本、幂等、重试、死信。
- **方案**：
  1. 新增依赖：`celery>=5.3`、`redis>=5.0`（可选 `hiredis`）、`prometheus-celery-exporter`（P1-3 共用）。
  2. `services/tasks/`（新目录）：
     - `worker.py` 定义 `app = Celery("uea", broker=redis://...:6379/0, result_backend=redis://...:6379/1)`。
     - `tasks.py`：
       - `task_pull_mails` —— 周期（beat 30s）调 MailPuller，产出 `pending` 入队。
       - `task_run_golden_chain(mail_id, idempotency_key=<state_hash>)` —— 调 CATController；**幂等键 = sha1(mail_id + pending.state)**，完成即 `mark_state` 已存在（复用文件锁，先锁后入队）。
       - `task_notify(verdict, mail_id, context_id)` —— 走 P0-1 Gateway。
  3. `bootstrap.py` 增 `build_worker()`：与 `build_controller()` 同为组装根，worker 复用同一 singleton 构造。
  4. **优雅降级**：`config/settings.yaml` 加 `queue: {backend: "thread" | "celery"}`；Redis 不可达时回退现有线程 drain（`MailOrchestrator.start_loop` 保留），保证无 Redis 环境（当前本地 demo）行为不变。
  5. 幂等与重试：`autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, max_retries=5`；超限入死信表 `task_failed_<mail_id>`。
  6. 测试：`tests/test_tasks_queue.py` — 幂等键映射（同一状态不重复跑）、重试计数、Redis-miss 回退 thread 模式（用 fake broker 不做真实连接）。

- **验收**：`docker compose up` 起 broker+worker 后，一封新邮件经 redis 流转状态 DONE/HITL/BLOCKED；kill worker 重发不产生重复黄金链；无 Redis 时 `UEA_QUEUE_BACKEND=thread` 行为 = 今天。

### P0-3 配置热加载（watchdog + mtime 轮询）

> 实测：models.yaml 已"每次现读"；settings/policy/commercial 只 import 时加载一次；Windows 无 SIGHUP。

- **方案**：
  1. `services/config_store.py`（新）：统一 `ConfigStore`，mtime 差异检测 + 锁内原子重载：
     - 注册 `config/settings.yaml|policy.yaml|commercial.yaml|models.yaml|skills.yaml`。
     - `watch(path)` / `get(section)`；`changed_on` 记每文件 hash。
     - 触发方式：Windows 用 5s mtime 轮询；Linux 可选 watchdog → 同样走 `apply`。
  2. `apply` 契约：因 `CATController` 持 policy/planner 等引用，采用**订阅发布**：`on_changed(section, fn)`；Controller/Guardrails/ModelRouter 各自注册"重建 sketch + swap in"。
  3. API：`GET /v1/config/status`（文件 + hash + last_reload）、`POST /v1/config/reload`（手动触发，写 audit）。
  4. 变更审计：reload 前后 diff 写入 `data/skill_audit.jsonl`（event=`config_reload`）。
  5. 测试：`tests/test_config_store.py` — 改 policy.yaml 后 5s 内生效、diff 审计、损坏 YAML 拒绝生效并回滚上次版本。

- **验收**：不重启进程，修改 `config/policy.yaml`（如金额门禁阈值）→ 20s 内新报价走新阈值；坏 YAML 保持旧配置并落审计。

### P0-4 数据库迁移与备份（Alembic + 备份策略）

> 实测：sqlite3（audit/crm/feedback）+ 若干 jsonl，无迁移、无备份。

- **方案**：
  1. 新增依赖：`alembic>=1.12`、`sqlalchemy>=2.0`（仅模型层，业务代码仍走原生 sqlite3 的保持不动；先抽出 `data/` 三库 schema 基线）。
  2. `alembic/` 目录：初始迁移 = 现有 audit/crm/feedback 建表 DDL 快照；后续变更一律走迁移，禁手工 `ALTER`。
  3. **可选升级通道（Phase 4 独立项）**：`storage.type: sqlite|postgres`；Postgres 用 `SQLAlchemy` URL `postgresql+psycopg://...`，同 schema 双跑测试。
  4. 备份：
     - 每日凌晨 beat 任务 `task_backup`：SQLite 用 `sqlite3 .backup`（在线一致性）→ `data/backups/<date>/`。
     - 保留策略：近 7 天日备份 + 最近 4 周周备份，超期清理。
     - 与 P0-2 共用 celery beat；文件锁防与写入并发。
  5. `scripts/backup_db.py` + `scripts/restore_db.py`（可用性演练脚本）。
  6. 测试：`tests/test_db_backup.py` — 造数→backup→删库→restore→行数一致；迁移 `alembic upgrade head` 从头可建。

- **验收**：一键备份/还原可行；`alembic revision` 新增列后旧库可平滑升级（同表数据保留）。

---

## 五、P1 方案（应做，4 项）

### P1-1 供应商履约闭环接入（supplier_module 接线并补验收）

> 实测：`supplier_module/`（orchestrator / state_machine / supplier_inbox）已存在，测试在 `tests/test_supplier_pipeline.py` 直接导包；但**不在** api_server / Dockerfile COPY 列表 / 主干流程中。

- **方案**：
  1. 接线：`services/supplier_api.py` 暴露 `/v1/supplier/*`（match → PO 生成 → 排产 → 收货回执）；复用 `supplier_module.orchestrator`。
  2. 触发点：黄金链 PASS 路径之后进入 `RFQStateMachine` 新增 `FULFILLMENT` 区段（保持铁律② 合法转移表同步更新）。
  3. 入主干：Dockerfile `COPY supplier_module/ ./supplier_module/`（+ 新 `services/supplier_api.py`）。
  4. 补验收：`verified` 状态到货回写 CRM；对账（PO 数量 vs 收货数量）不一致 → HITL。
  5. 测试并入 CI：`tests/test_supplier_pipeline.py` 纳入主干回归（当前已常绿，仅接入 trunk 路径）。

- **验收**：PASS 报价 → 生成 PO → 模拟排产/收货 → 状态机 FULFILLMENT 全链路在 API 可用；回归绿。

### P1-2 多币种 / 汇率 / 多语种模板

> 实测：`config/commercial.yaml:currency: CNY` 单币种；通知模板 `base.py:build_default_template` 单语言（中英混排 Markdown）。

- **方案**：
  1. `config/commercial.yaml` 增 `currencies: {CNY: {rate_to_cny: 1.0}, USD: {...}, EUR: {...}}` + `fx_rate_date`；汇率来源标注（手动/时钟源），禁止 LLM 生成汇率（铁律① 精神延伸）。
  2. `services/fx.py`：`to_cny(amount, cur)` / `format_quote(cur)` 确定性换算；`CalculationEngine` 输出保持元数据（金额 = 基准 CNY + 币种 + 汇率日期），展示层换算。
  3. 多语种：`services/i18n.py` — 模板字典（en/zh/ 未来 ja/de）；`build_default_template(event, lang)` 按客户区域语种渲染；e-mail/Telegram/Slack 共用。
  4. 锁：报价快照必须含 `currency + fx_rate_date + fx_rate`，HITL 复核展示同源（铁律③/④ 对齐）。
  5. 测试：`tests/test_fx_i18n.py` — 换算确定性、汇率缺失拒绝报价、双方言模板渲染。

- **验收**：USD/EUR 询盘得出币种正确、汇率带日期来源的报价；无汇率表时该币种显式 HITL 而非静默 CNY。

### P1-3 Prometheus + Grafana 实时大盘

> 实测：`hpa.yaml` 已含 ServiceMonitor/PrometheusRule 定义；grafana-dashboard.json 已存在；缺 `/metrics` HTTP 端点与 scrape target。

- **方案**：
  1. 依赖：`prometheus-client`（或 `prometheus-fastapi-instrumentator`）；`services/metrics.py` 规整现有 Observability `metrics: [tool_calls, tool_errors, hitl_triggers, retrievals, model_calls]`（settings.yaml 已列）为 Counter/Histogram。
  2. `api_server.py` 增 `GET /metrics`；`observability.otel_endpoint` 与 `/metrics` 双轨并行（JSONL 现状保留过渡）。
  3. 关键指标（对齐 hpa.yaml 已有告警规则）：`uea_requests_total`、`uea_hitl_triggers_total`、`uea_circuit_open{backend="timo"}`、`uea_skill_duration_ms_bucket{skill="cnc-quote"}`。
  4. `deploy/prometheus.yml` + 验证 `grafana-dashboard.json` 与新版指标名一致（现 dashboard 为 v3 视觉稿，需核）。
  5. 测试：`tests/test_metrics.py` — 触发一次报价后 `/metrics` 可见 `uea_skill_duration_ms` 直方图、HITL 计数递增。

- **验收**：仪表盘可见 4 类指标；`HighHITLRate`、`EngineCircuitOpen`、`QuoteLatencyHigh` 三条告警规则在规则计算器内可触发验证。

### P1-4 Vault/KMS 接管凭据

> 实测：`credentials.py` Fernet 本地存储可用；密钥=固定 app_secret+machine seed，无中央密钥服务。

- **方案**：
  1. `services/credentials.py` 增 abstract backend：`local`（现状，默认）与 `vault`（KV v2，`VAULT_ADDR` + `VAULT_TOKEN` 环境注入，AppRole 可选）。
  2. `config/settings.yaml` 加 `credentials: {backend: local, vault_path: "secret/uea"}`；运行时不落盘的凭据只存进程内存。
  3. compose/k8s：vault sidecar（agent）注入 SMTP/Telegram/Slack token → app 直接消费，`data/credentials.json` 不再写入敏感项（原有项迁移后移除）。
  4. 铁律守卫不变：mask 展示、`0600`、审计 `credential_read/write`。
  5. 测试：`tests/test_credentials_vault.py` — fake Vault（`vaultifier` 或 stub HTTP）下 get/save/迁移流程。

- **验收**：切到 vault 后端后 SMTP/Telegram 凭据从 Vault 注入可用；token 轮换不需要重启（读时实时）。

---

## 六、P2 方案（可缓 / 环境依赖，4 项）

### P2-1 NVIDIA NIM 真实集群跑通（依赖 GPU 集群）

- **现状**：`deploy/nim/` 清单就绪；`services/nim_health.py` 探活 build.nvidia.com 或自配 `UEA_NIM_BASE`；本机 0 NIM 进程。
- **方案**：在具备 NVIDIA API Key / GPU 集群后，按 `deploy/nim/` 逐个拉起 → `nim_health.py` + `tests/test_nim_health.py` 转真实；model_router `backend: nvidia` 端到端跑一次黄金链（REASON/FAST 切 NIM，DETERMINISTIC 仍本地）；TRT-LLM/Triton 用 concurrency benchmark 验证 P95 < 3s（对齐 QuoteLatencyHigh 告警）。单独设里程碑，不阻塞 P0/P1。

### P2-2 审计链 TSA 时间戳

- **现状**：`data/contexts/{cid}.audit.json` SHA-256 链 + `data/skill_audit.jsonl`，无可信时间。
- **方案**：`services/timestamp.py` — 用 RFC 3161 TSA（本地 timescaledb-tsa 或公用 TSA）对审计条目摘要打时间戳；验签脚本 `scripts/verify_timestamp.py`；可选公证（RFC 3161 长存 + Archive Chain）供司法举证。验收：审计条目可离线验证时间与完整性。

### P2-3 Linux / macOS 启动脚本 + systemd

- **现状**：`一键启动.bat`、`一键自检.bat`、`scripts/start_novastudio.bat`、`verify_l3_demo.bat` 均 Windows-only；Python 侧 `start_api.py`/`start_engine.py` 已跨平台。
- **方案**：`scripts/start_novastudio.sh`（等价 4 工具拉起 + 健康检查）、`scripts/start.sh`/`stop.sh`；`deploy/systemd/uea-api.service`、`uea-worker.service`（ExecStartPre 健康检查，Restart=on-failure）；README 双平台文档。CI 内可加 Ubuntu 冒烟（NovaStudio 4 工具用 docker compose，天然跨平台）。

### P2-4 tools/ 拆解（子模块 / 镜像 / 对象存储）

- **现状**：`tools/` 6.3GB、未跟踪、仅本地；git status 噪声 `?? tools/`，存在 `git add .` 误提交高风险。
- **方案（推荐顺序）**：
  1. 立即（低成本）：项目根 `.gitignore` 加 `tools/`，杜绝误提交；README 注明 tools 由 `scripts/install_tools.ps1/.sh` 下载。
  2. 中期：每个工具对应独立 Git 仓库（Git LFS 或对象存储 URL），`install_tools` 按 hash 校验下载解压 → `tools/<name>/`。
  3. 远期：MinerU / ragflow 改镜像引用（docker compose pull），OmniVoice/SearXNG 走发布包；仓库零二进制约 6.3GB。

---

## 七、分期实施计划

| Phase | 内容 | 依赖 | 里程碑 / 验收 |
|---|---|---|---|
| **1（并发+外发）** | P0-1 通知网关、P0-2 队列（thread 回退优先）、P1-4 local+vault 骨架 | settings 增 notify/queue/credentials 节 | 一封邮件 E2E 可真实通知；无 Redis 回退 thread；499 回归绿 |
| **2（配置+持久化）** | P0-3 配置热加载、P0-4 Alembic+备份 | Phase 1 | 改 policy.yaml 20s 生效；备份/还原演练通过 |
| **3（履约+可观测）** | P1-1 供应商接入、P1-3 Prometheus/Grafana、P1-2 FX/i18n | Phase 1-2 | `/v1/supplier/*` 全链路 API；/metrics 大盘；USD/EUR 报价 |
| **4（环境项）** | P2-1 NIM、P2-2 TSA、P2-3 Linux、P2-4 tools 拆解；storage=postgres 迁移 | 有 GPU 集群 / 服务器 | NIM 黄金链 benchmark；审计可验证；Ubuntu 冒烟绿；tools 零仓库占用 |

**每个 Phase 出口检查单**：全量 pytest 499 绿 + 该 Phase 新增测试绿 + 文档（README/PRD 数字）同步更新 + `MANIFEST.md` 记录新增文件。

---

## 八、依赖与环境变更清单（增量）

```
requirements.txt（追加，均为可选 import-gated，无它们旧路径照常跑）:
  celery>=5.3          # P0-2
  redis>=5.0           # P0-2
  alembic>=1.12        # P0-4
  sqlalchemy>=2.0      # P0-4
  prometheus-client    # P1-3
  # vault 用 urllib 直连 HTTP API（不引 hvac，减少依赖面）
  # 汇率/TSA 用 stdlib，不引新依赖
```

新增环境变量：`UEA_QUEUE_BACKEND`、`UEA_NOTIFY_REAL`、`VAULT_ADDR`、`VAULT_TOKEN`、`UEA_NIM_BASE`（已有 `EMAIL_SMTP_*`、`TELEGRAM_*`、`SLACK_WEBHOOK_URL`）。

---

## 九、风险与对策

| 风险 | 对策 |
|---|---|
| 队列化改变状态机时序（铁律②） | 幂等键映射先评审；`pending.jsonl` 文件锁先锁后入队；保留 thread 回退 |
| 真实外发误触达客户（铁律③ draft_only） | `UEA_NOTIFY_REAL`/管理端开关默认关；通知对象固定为内部 ops 收件，报价对象仍 draft_only；审批链审计 |
| Celery 在 Windows dev 环境受限 | 本地默认 thread 回退；Windows 上开发、Linux 上生产 worker |
| sqlite→Postgres 迁移数据漂移 | 双跑阶段：两库每日行数/LRU hash 对账一致后再切换 |
| tools/ 误提交入库 | .gitignore 加 `tools/`（Phase 2-4 立即执行，独立小改动） |
| NIM/GPU 不可达导致 P2-1 悬空 | 明确为环境独立里程碑，P0/P1 不过度依赖；`nim_health` 保持 mock 降级 |

---

## 十、结论

- **今天即可动手**（不依赖任何外部条件）：P0-1 通知网关（代码已 80% 在）、P0-3 配置热加载、P0-4 Alembic+备份、P1-1 供应商接线、P2-3 Linux 脚本、P2-4 tools 的 `.gitignore` 第一步。
- **需要环境**：P0-2 Redis/Celery、P1-3 大盘、P1-4 Vault、P1-2 汇率来源 → 在确认后尽快拉齐前端基础。
- **需要 GPU 集群**：P2-1 NIM / TRT-LLM；其余项不阻塞。

建议下一个动作：**确认本方案（Phase 顺序可讨论）→ 从 Phase 1 的 P0-1 开始实施**，每个任务以「新增代码 + 新测试 + 499 回归绿」为完成定义。