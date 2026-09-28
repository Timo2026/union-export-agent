# 节点部署 + 真实 QQ IMAP + STEP 预览重设计 — 设计规格

日期: 2026-09-23 · 分支: feature/skills-p0-flywheel · 状态: 已批准执行 (user: "推理，执行")

## 0. 目标 (user 原话拆解)

把整个 UI + 后台部署到节点 `203.0.113.10:8051`；主力模型 omni；重设计工业非标外贸
B 端后台 (邮箱列表 / 订单列表 / STEP 图纸预览 + 客户 RAG/联网搜索 + 筛选/批量/分页/空状态 /
模型设置 / 本地状态查询 / 多模态 RAG 库)；邮箱可改 — 启用真实 QQ IMAP 收信 (授权码已给)，
SMTP 保持 draft_only；STEP 预览参考 fusion.zip + funasr-gui。

## 1. 已锁定的 3 个决策 (AskUserQuestion)

1. **前端交付物 = `webui-redesign` 真后端版** (Tailwind 9 视图, 已接线 + 浏览器实测)，
   构建到 `webui-dist`，替换当前部署的 antd 前端。**不是** mock 单 HTML。
2. **邮箱 = 启用真实 QQ IMAP 收信；SMTP 保持 draft_only**。授权码经 `POST /v1/gmail/connect`
   Fernet 加密落 `data/credentials.json`，开 imap egress，`enabled=true service=qq`，真拉信。
   **授权码用后必须轮换。**
3. **节点部署 = env 注入坐标，用现有 `deploy/node_deploy.py` + `node_bootstrap.ipynb`**，
   先 dry-run 验连通再推。

## 2. 已验证的代码事实 (file:line / 命令证据)

- **前端源权威副本 = `C:\Users\<user>\AppData\Local\Temp\uea-real\`** (有 `src/api/backend.ts` +
  9 视图全接线 + `deliverable.ts` 已删)。repo 内 `webui-redesign/` 是**陈旧且未跟踪**
  (`git ls-files webui-redesign`=0, 缺 `src/api/backend.ts`)，`webui-dist/` 也未跟踪 (=0)。
- **构建可行 (已实测)**: `npx vite build` → `✓ 1926 modules transformed, built in 1.54s`，
  产物 index.html + index.css 42KB + index.js 444KB + 4 PNG (~4.9MB)。
  `tsc -b` 会因**并发写手**的 `components/{drawings,knowledge,mailbox,models}` 类型错误而红，
  但我的 9 视图只 import `components/ui` + `components/layout` + `api`，这些坏目录**不在导入图**，
  vite (esbuild) 正确 tree-shake 掉 → **构建走 `vite build`，跳过 `tsc -b`**。
- **后端在跑**: `GET http://127.0.0.1:8900/health` → 200；根路径 serve HTML；
  `/v1/workbench/status` 慢 (12-25s, 前端 timeout 已设 45000ms)。
- **邮箱接线点**: `services/gmail_imap.py` (QQ_HOST=imap.qq.com:25, port 993:26, connect:58-73,
  sync 写 data/mailbox/{id}.eml:116-153)；`services/mail_puller.py` (_read_conn_cfg service==qq
  切 imap.qq.com:591-592, poll_once:257-292)；`services/gmail_api.py` (POST /v1/gmail/connect:79
  需 enabled=true 否则 403:86-87, 落 creds:93；POST /v1/gmail/sync:107 gated:110-111)；
  `data/gmail_settings.json` (enabled/host/port/folder/service)；`config/settings.yaml:85-93`
  egress gate (smtp:false, imap:false)。
- **SMTP 铁律①**: `services/notify/email_notifier.py` real_send 默认 False:28/36, send() 不在
  real_send 时写本地:41, egress_gate.check("smtp"):43-48；`skills/write-reply/tool.py:57-58` draft_only。
- **节点部署**: `deploy/node_coords.py:11-28` 只从 env `UEA_NODE_HOST/PORT/USER/PWD` 读 (缺则 SystemExit)；
  `deploy/node_deploy.py` paramiko SFTP + sha256 双校验, 默认上传 node_bootstrap.ipynb 到
  `~/union-deploy/staging`；`deploy/node_services.sh:118-122` uvicorn :8888 → NAT 公网 :8051。
- **参考资产存在**: `CNC-AI-Brain-v12.0.0-fusion.zip` (1058985 bytes)；`C:\Users\<user>\funasr-gui\`
  (server.py, index.html, VISION_RAG_PLAN.md, rag.sqlite3, records, outputs)。
- **导出排除清单**: `scripts/export_demo.py` IGNORE credentials.json/gmail_settings.json/.env/*.pem/
  sqlite/logs (92-97) + FORBIDDEN_NAMES 自检 (100-101) + 公网 IP 正则 (71,81-88)。

## 3. 阻塞项 (执行前须知)

- **节点 env 未注入**: 本 shell 与 Windows User 级 `UEA_NODE_HOST/PORT/USER/PWD` **全空**。
  Stage 4 需要它们。user 可并行注入 (PowerShell):
  `$env:UEA_NODE_HOST='203.0.113.10'; $env:UEA_NODE_PORT='6051'; $env:UEA_NODE_USER='<user>'; $env:UEA_NODE_PWD='<pwd>'`
  Stage 1-3 为本地工作，不受阻。
- **授权码（明文已脱敏 `<REDACTED-AUTHCODE>`，原值见本机轮换记录）已在 transcript 暴露 → 用后必须轮换；绝不外泄；绝不入库。**

## 4. 执行阶段 (CoT 清单, 逐个执行, 禁止绕过)

- **Stage 1 — 前端构建落地**: 从 uea-real `vite build` → 校验产物 → swap 进 repo `webui-dist`
  (先备份现有 antd 产物到 webui-dist.bak, 因未跟踪无 git 兜底) → 本地 serve 验证 9 视图真后端。
- **Stage 2 — 真实 QQ IMAP 收信 [已完成 2026-09-23]**: 备份 credentials.json/gmail_settings.json →
  **更正**: IMAP 入站**不受 egress 闸管控** (settings.yaml 注释明示 "Gmail IMAP 入站连接由其自有
  settings.enabled 门禁, 不在此闸"; grep 全仓无 imap egress 强制) → **不动 settings.yaml, smtp 保持 false**。
  gmail_settings.json 已是 enabled=true service=qq host=imap.qq.com port=993 (无需改)。
  用新授权码 `<REDACTED-AUTHCODE>` 先 imap_tools 登录测试成功 → save_credentials("qq", 既有账号, 新码) Fernet 加密落盘 →
  GmailMailbox(service=qq,host=imap.qq.com).sync() **实拉 22 封新信** (qq_*.eml 34→56, skipped 28) →
  GET /v1/mail/inbox count=50 (41 QQ 源, 真发件人 <REDACTED-REAL-SENDER> 等) →
  前端 Mailbox 实测显示 09-23 06:32 新鲜真信, online 模式。**SMTP 全程 draft_only 未动**
  (output_external_send:draft_only, egress.allow:false, smtp:false, real_send=False 全核实)。
  **隐私**: 收件箱暴露真实个人账号 (Gmail / GitHub / QQ, 均已按隐私清单脱敏) → Stage 5 截图必须脱敏。
- **Stage 3 — STEP 预览 (范围 3a) [已完成 2026-09-23]**: 读 fusion.zip manifest (136 条目: app/static/three.min.js
  + src/runtime/step_parser.py + cad-step-rag/cad-quote skills + 真 .STEP)；funasr-gui index.html **无 3D viewer**
  (是 ASR/RAG GUI) → 3D 参考取 fusion.zip 的 three.js。核实后端真端点: GET /v1/drawings (page/page_size/q/**customer**),
  /v1/drawings/{id}/thumbnail (SVG), /v1/drawings/{id}/mesh (返 positions_b64 Float32x3 + indices_b64 Uint32x3 +
  bbox/vertex_count/tri_count/deflection, 子进程 OCP 懒构建缓存), GET /v1/web/search。**无 drawings 批量端点** →
  批量操作走客户端逐项真端点聚合 (不伪造)。实现: 新增 `src/views/StepMeshViewer.tsx` (three.js BufferGeometry 解码 b64,
  OrbitControls, mesh 失败回退 SVG) + 重写 `Drawings.tsx` (3D/缩略图切换 + 筛选 chips 全部/有mesh/有缩略图 +
  联网情报 lane + 客户端批量选择/批量构建 mesh+缩略图) + backend.ts 加 MeshResp/drawingMesh/customer 参数 +
  three-shim.d.ts。three.js 懒加载 code-split (主包 449KB + StepMeshViewer chunk 557KB)。**浏览器实测**:
  node_occ_smoke_sample.step → canvas 942x1045 WebGL-ok, 标签 "216 顶点 · 208 三角" (与真 mesh 一致);
  联网 lane 如实报 "无命中 — JSONDecodeError" (searxng 出口降级); 批量选 2 → 操作条出现。源码已同步 repo webui-redesign。
- **Stage 4 — 节点部署**: env 注入后 `python deploy/node_coords.py` dry-run 验坐标 →
  `deploy/node_deploy.py` SFTP 推 bootstrap + webui-dist + 后端 → 节点 tmux 起 uvicorn :8888 →
  公网 :8051 冒烟 (health + 9 视图 + omni 主力) → 节点全量测试。
- **Stage 5 — 收尾**: 轮换 QQ 授权码 → 确认 credentials/settings 未入任何 commit/export →
  release marker 三处同步 (CHANGELOG/MANIFEST/webui 副标题) → 截图脱敏 (真实 QQ 账号热替换) →
  带证据汇报。

## 5. 安全铁律 (全程)

1. SMTP/real_send 永不开 — draft_only。
2. credentials.json / gmail_settings.json / 授权码 永不入 commit/export/deploy。
3. 授权码用后轮换。
4. 截图暴露真实 QQ 账号必须脱敏。
5. 不删并发写手的文件 (components/layout|ui, index.css 是他们的；views/ + api/ 是我的)。
6. 节点 aarch64 GB10 sm_121 内存受限 — omni 常驻, 重模型按需, STEP 批任务串行, 清华源 pip。
7. verify by code — 不发明 API/端点。
