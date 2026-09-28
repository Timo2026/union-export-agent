# V12 内核仪表板移植 + 图纸批量操作对接评估 — 设计规格

日期: 2026-09-24 · 分支: feature/skills-p0-flywheel · 状态: **待 user 批准** (brainstorming HARD-GATE)

## 0. 目标 (user 原话拆解)

1. "链接 shh，推理，执行，并修复，对接真后台 api" — STEP 图纸中心对节点真后端的验证+修复。**已完成并真端点验证** (见 §1)。
2. "批量操作立里的操作可以对接道 V12 上吗?" — 评估 + 结论 (见 §3)。
3. "把 V12 的 UI 部署上去" — V12 仪表板移植进 React 工作台并部署节点 (方案 P1, 见 §4)。
4. "你阅读，理解，分析，评估，推理，做方案" — 本文件即方案; **未获批准前不动 V12 相关代码**。

## 1. 本轮已完成 (修复, user 已指示"执行, 并修复")

`services/step_mesh.py` 两处改动 (本地 14/14 单测绿; 全量回归 **914 passed / 1 skipped / 1 warning**,
即 913 基线 + 新增 sniff 单测, 零失败):
- **OCP 版本兼容 (节点真 bug)**: `TopoDS.Face_s(exp.Current())` (step_mesh.py:84) 在节点 OCP v7.9.3.1
  不存在 (cadquery 2.8.0 / occ env), 新版本地才有 → 全线 mesh 400。改为构造器造型
  `TopoDS.Face(exp.Current())`, 双侧 (本地新版 + 节点 v7.9.3.1) 实测通过。
- **magic 嗅探 (诚实失败可操作化)**: `_looks_like_iso_step()` 前置校验 ISO-10303-21 文本头;
  二进制文件误改名 .step (节点 27 张中的"顶盖") 从"文件损坏或格式非法"变为
  "非 ISO-10303-21 STEP 文本 (疑似非 STEP 文件误改为 .step 后缀)"。

节点部署与验证 (证据 `data/node_evidence/inv7_stepmesh_fix.txt` / `inv8_mesh_verify.txt` / `inv9_stepmesh_v2.txt`,
全程 hostname+端口脱敏, 无口令外泄):
- 部署链: paramiko SFTP + sha256 双校验 + py_compile + `node_services.sh restart livekernel`
  (tmux watchdog, READY 3s); 回滚点 `~/union-deploy/backups/pre-stepmesh-fix-*` / `pre-stepmesh-v2-*`
- 真端点: sample.step **200 ok (208 三角)**; box_cq **200 ok (12 三角)**;
  **1010003-底板-V1.0.STEP 1.73MB → 200 ok, 17793 三角 / 18470 顶点**, bbox 565×420×85mm;
  顶盖 → 400 可操作原因; `/v1/drawings` 复核 **total=27, has_mesh=26**
- 公网入口 (http://spark-388d:8051 同源 NAT): `/health` v7.1.0-livekernel + mesh ok=true + 27/26 复核通过

## 2. 已验证的代码事实 (file:line)

**V12 后端 (读多写少, 全 GET)**:
- `services/v12_api.py:17-28` — `/v1/v12/{status,audit?limit=10,dfm}` 三端点, APIRouter prefix `/v1/v12`
- `services/v12_status.py:43-73` — status 字段: version / kernel_online / kernel_health_ok /
  source_label / calc_quote_total / p50 / p95 / dfm_c1_c6_counts{C1..C6} / dfm_conflicts_total /
  span_count / trace_count / recent_spans[10]
- `services/v12_status.py:75-97` — audit: 逐 trace 文件首行取 trace_id (≥16 hex) → sha256_16 + context_id
- `services/v12_status.py:108-170` — 聚合: 遍历 `data/traces/*.jsonl` 每文件**末 300 行**;
  calc_quote/cnc-quote 名 → 吞吐+分位; conflict/dfm 名 → 冲突计数 (rule/code/category 含 C1..C6 才入桶)

**V12 遗留 UI (唯一存在处, 单文件控制台, 未被 React 工作台收录)**:
- `webui/index.html:863-918` — tab HTML: 状态栏 (LED/ver/src/刷新/时间戳) + 4 卡片
  (calc_quote 吞吐条 / C1-C6 桶 / sha256 审计链 ol / 最近 trace ul) + 底栏 (trace/span/source)
- `webui/index.html:246-281` — 对应 CSS (.v12-* 约 35 行)
- `webui/index.html:2170-2213` — JS IIFE (~45 行): `fetch('/v1/v12/status')` + `fetch('/v1/v12/audit?limit=8')`
  并行; tab 切入刷新 (`index.html:1344`); 无轮询; esc/fmtTime 工具
- 现状: `webui-redesign/` 9 视图无 V12; `webui/console/` 6 标签无 V12; grep 全仓 JS 引用仅此一处

**节点 V12 真数据 (本轮公网实测, 修复重启后)**:
`version=v12.0.0-Fusion kernel_online=true source=live:cnc-ai-brain:7862 calc_quote_total=1148
p50=12.42ms p95=24.34ms spans=11342 traces=1267 dfm_c1_c6_counts 全 0 (rule 名不含 C1-C6 字面量,
**如实展示 0, 不伪造**) conflicts_total=1267; recent_spans 真名: agent_run / guardrail:input /
skill:rfq-extraction / skill:dfm-conflict / skill:cnc-quote; audit hashes 存在`

**图纸批量操作 (评估对象)**:
- `webui-redesign/src/views/Drawings.tsx:111-129` — 批量 = **客户端逐项聚合**真实端点
  (`backend.drawingMesh(id)` / `drawingThumbUrl(id)`), **串行** for 循环 (节点 OCC 并发坑既定约束),
  结束 toast 如实报"成功 X / 失败 Y (共 N)"; 无后端批量端点 (09-23 设计决策: 不伪造)
- `services/api_server.py:1199` list / `:1234` thumbnail / `:1268` mesh — **三端点均不发射 span**
  (grep: api_server.py 仅 `/v1/traces/{cid}` 只读消费, :1127-1133)

**trace 机制 (对接枢纽)**:
- `services/observability.py:59-67` — span 字典 schema (trace_id/span_id/parent_id/name/kind/
  start_time/duration_ms/status/attributes/events)
- `services/observability.py:87-91` — `Tracer.start_span`; `:105-118` — export 写
  `data/traces/{context_id}.jsonl` (模式 "w" 整文件覆写)
- 即: **任何流程只要按 schema 追加 span 行, V12 的 recent_spans / audit / span_count 自动收录**
  (v12_status.py:129-159 读末 300 行; audit 读首行)

**前端/构建/部署链**:
- `webui-redesign/src/App.tsx` — 9 路由 (Overview/Mailbox/Orders/Drawings/Search/RagLibrary/Models/Status/Inference)
- `webui-redesign/src/components/layout/Sidebar.tsx:41-66` — 3 组导航 (业务台 4 / 智能检索 2 / 系统 3);
  `:251` 陈旧标记 "Omni 4B 常驻 / v3.1.0" (实际 v7.1.0, Omni 30B 常驻) — 本次顺手校正 (release marker 同步铁律)
- `webui-redesign/src/api/client.ts` — ENDPOINTS 真实端点注册表 + `getBase()` (生产同源直连);
  `api/backend.ts:326-331` — 类型化 fetcher 约定 (`api<MeshResp>(..., {timeoutMs: 90000})`)
- `webui-redesign/vite.config.ts` — outDir `../webui-dist`, emptyOutDir; build = `tsc -b && vite build`
  (tsc 若被无关组件目录 (components/{drawings,knowledge,mailbox,models}) 拖红 → 既定变通 `npx vite build`,
  9 视图不在其导入图, esbuild 正确 tree-shake; 见 09-23 规格 §2)
- `services/api_server.py:113-119` — `_WORKBENCH_DIR` (env `UEA_WORKBENCH_DIR`, 默认 `<root>/webui-dist`),
  挂载 `/assets` StaticFiles + 根路由 FileResponse serve index.html → **静态产物落盘即生效, 无需重启**
- `deploy/node_deploy.py:32-104` — paramiko connect + sftp.put + sha256 双校验 (凭据只走 env)
- `deploy/node_services.sh:118-122` — livekernel = OCC_PY uvicorn :8888; restart 走 tmux watchdog

## 3. 评估: 批量操作里的操作可以对接到 V12 上吗?

**结论: 能, 但唯一诚实的对接形态是"可观测对接"(span), 不是"按钮内嵌"。**

- V12 是**只读内核监控台**: 报价吞吐 / DFM 冲突 / sha256 审计链 / trace 时间线。批量操作是**数据处理动作**
  (批量建 mesh / 批量缩略图 / 客户 RAG / 联网情报)。把动作按钮嵌进监控台 = 关注点错位, 且 V12 的语义
  (内核健康) 与图纸库处理无关。
- V12 的数据源就是 `data/traces/*.jsonl` 的 span (§2), 而图纸三端点**零 span** → 批量操作今天在 V12 上
  完全不可见。补上 span 发射, 批量操作即自动出现在 V12 时间线 / 审计链 / span 计数 — **零 V12 后端改动**。
- 因此"对接到 V12"= 让图纸操作进入 V12 的可观测面 (P2); 若要 V12 上直接看到批量吞吐/失败汇总,
  加一片前缀聚合 + 一张卡片 (P2+); 若要服务端真批量端点 (P3, 改 09-23 既定决策, 单列拍板)。

## 4. 方案 (P1 为主, P2 推荐同做, P3 待拍板)

### P1 — V12 内核仪表板移植 (user 明确要求"把 V12 的 UI 部署上去")

新增/改动 (全部在 webui-redesign 源, 不动 backend):
1. `src/api/client.ts` ENDPOINTS += `v12Status: "/v1/v12/status"`, `v12Audit: "/v1/v12/audit"`,
   `v12Dfm: "/v1/v12/dfm"` (真实端点一一对应, 不发明)
2. `src/api/backend.ts` += `V12StatusResp` / `V12AuditResp` 类型 + `v12Status()` / `v12Audit(limit)`
   fetcher (沿用 `api<T>` + timeoutMs 约定; V12 status 聚合 1267 trace 文件偏重, timeout 60s 并在 UI 明示"聚合中")
3. `src/views/V12.tsx` — 移植遗留仪表板, 结构一一对应:
   状态栏 (LED=内核在线 / v12.0.0-Fusion / source_label / 刷新钮 / 时间戳);
   卡片① calc_quote 吞吐 (total + p50/p95 + 吞吐条); 卡片② C1-C6 DFM (总数 + 6 桶, >0 高亮 — 现为 0 则如实显示 0);
   卡片③ sha256 审计链 (limit=8 列表); 卡片④ 最近 trace (recent_spans 8 条: trace_id/name/duration/status);
   底栏 (trace 数 / span 数 / source)。
   交互沿用遗留语义: 挂载即拉 + 手动刷新 (无轮询, 避聚合负载); 加载/错误态诚实降级 (OfflineError → 提示, 不造假数据)。
   复用 `components/ui` (Card/Badge/StatusDot), 风格对齐现有 9 视图。
4. `src/App.tsx` + `<Route path="/v12" element={<V12 />} />`
5. `src/components/layout/Sidebar.tsx` 系统组 += `{ to: "/v12", label: "V12 内核", icon: Gauge }`;
   顺手把 `:251` 的 `v3.1.0` 校为 `v7.1.0` (陈旧标记, release marker 同步铁则)
6. 测试: `webui-redesign` 既有 vitest 用例 + 新增 V12 视图渲染/降级用例 (mock fetch)

### P2 — 批量操作 → V12 可观测对接 (推荐同做, ~30 行)

1. `services/api_server.py` mesh (:1268) / thumbnail (:1234) 端点完成后, 按 observability schema
   **追加**一行 span 到固定 trace 文件 (新建 `services/trace_emit.py` append 帮助, context_id 固定
   `drawings-ops`): `name=drawings.mesh | drawings.thumb`, `status` 随 ok/失败,
   `duration_ms` 实测, `attributes={drawing_id, sha256_16, ok, tri_count?, reason?}`;
   trace_id 每 span 一个 uuid4 hex (32, 满足 V12 audit ≥16 约束)
2. 效果 (零 V12 后端改动): V12 recent_spans / audit 链 / span_count 立即收录图纸操作
3. (可选 P2+) `services/v12_status.py` 聚合 += `drawings.*` 名前缀桶 (count + 近 N 条) + `V12.tsx`
   第 5 张卡片 "图纸库批处理" — 若你要直接在 V12 看批量汇总; 不加亦已在时间线可见
4. 测试: span 行 schema 单测 (字段/status/duration); 全量 pytest 无回归

### P3 — 后端批量端点 `POST /v1/drawings/batch` (需单独拍板, 默认不做)

- 先例存在: `POST /v1/mail/batch` (api_server.py MailBatchRequest, action delete|retry)
- 内容: {ids, action: mesh|thumb|rag} 服务端**串行**循环 (保 OCC 串行铁律) + 单 span
  {total, ok, fail, duration_ms}; 前端 Drawings.tsx:111-129 改调该端点
- 影响: 推翻 09-23"客户端聚合"决策 → 单列一项, user 明确批准才做; 本轮**不动的部分**

## 5. 部署与验证 (P1, 沿用既定链路)

1. 本地 `npx vite build` (tsc -b 若被无关目录拖红则变通) → `webui-dist` (emptyOutDir 会清空重建;
   `webui-dist` 未跟踪无 git 兜底, 先整目录备份副本, 同 09-23 swap 惯例)
2. 本地 :8900 serve + browser-use 真浏览器实测 `#/v12`: LED/4 卡/刷新/错误态 + 9 视图回归无白屏
3. 节点: `cp` 备份线上 `~/timo_livekernel/webui-dist` → `~/union-deploy/backups/pre-v12ui-<ts>/`
4. `deploy/node_deploy.py` paramiko 上传 webui-dist (sha256 双校验逐文件)
5. 复核 (静态挂载即时生效, 无需重启; 仍验健康): `GET /` 新壳 + `/assets/index-*.js` 新 hash 200 +
   `/v1/v12/status` 200; 公网 NAT :8051 `#/v12` 真数据 (kernel_online=true, 1148 报价量级);
   `/webui` `/webui/v5` `/docs` 遗留路由 200 无回归; `/health` v7.1.0-livekernel
6. 脱敏: 截图/证据不含真实账号/口令 (铁律)

## 6. 安全铁律 (全程)

1. 凭据只走 env (node_deploy/node_coords), 命令与证据不回显口令/公网 IP (hostname+端口口径)
2. 不伪造: DFM 桶为 0 就显示 0; 顶盖失败就显示可操作原因; 联网无命中如实报
3. 不动节点运行时口径: settings/models/skills md5 部署前后一致 (inv6 惯例, P1 只碰 webui-dist 静态产物)
4. 不删并发写手文件; P1 只动 `views/` + `api/` + Sidebar 两行 + App 一行
5. release marker 三处同步 (CHANGELOG/MANIFEST/webui 副标题) — 若本轮以 release 收口

## 7. 明确不做 (YAGNI)

- 不把批量动作按钮嵌进 V12 视图 (§3 结论)
- 不新增/修改 V12 后端端点 (P1 零后端改动; P2+ 仅聚合扩展, 需另批)
- 不改 DFM 桶匹配逻辑 (C1-C6 字面量不中是内核 span 命名的现状, 如实展示)
- 不做 P3 (服务端批量端点) 除非单独拍板
- 不动 `webui/index.html` 遗留 V12 (保留 legacy 可达, 与 React 版并存, 如 09-23 对 v5 的处理)

## 8. 执行清单 (批准后, TDD 逐 task)

- P1: T1 api 层端点+类型+fetcher (含单测) → T2 V12.tsx 视图 (vitest 渲染/降级) → T3 路由+侧边栏
  → T4 本地 build + browser-use 实测 → T5 节点部署 + 公网复核
- P2: T6 trace_emit + 端点接入 + 单测 → T7 全量 pytest (当前基线 913 绿 + step_mesh 新增 1) → T8 部署复核 V12 时间线出现 drawings.*
- 收口: 证据落 `data/node_evidence/`, release 三处 marker 同步 (若收口), 汇报
