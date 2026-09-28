# GitHub 标准开源交付包 — 交付汇报（2026-09-28 刷新）

## 交付物位置
`盘点汇总/github-package/` — **1301 文件 · 350 py · 141 md · 105 png · 39 skills 目录 · 135 tests**（09-28 刷新，本地 repo 为权威；出货集 = 目录 build **739 条目**，`github-package/` 前缀）

出货产物（内容全部刷新为当前包态，`github-package/` 前缀，ZIP_DEFLATED，排序 + 固定 mtime 确定性构建，四 zip 逐字节同 md5）：
- `union-export-agent-github-package-260927-FINAL-v2.zip`
- `union-export-agent-github-package-260927-FINAL.zip`
- `union-export-agent-github-package-260927-v2.zip`
- `union-export-agent-github-package-260927.zip`（含 data 自测夹具，公开克隆内可跑 pytest）
- `_node_pkg.tar.gz`（节点包产物，`./` 前缀，**与四个 zip 同一 content 集 739 条目、逐文件同 md5**）

## 09-28 刷新内容（对齐公网 8051 现行版本，权威 = 本地 repo）

| 项 | 刷新前（旧包/旧 zip） | 刷新后（本包） |
|---|---|---|
| webui-dist 前端构建 | 09-27 旧代 `index-DSmUweh8.js` | 线上同代 `index-DDaZfjqF.js`（与公网 8051 现行构建逐字节同源） |
| 批准门（CLARIFY） | `services/mailbox_api.py` `can_approve = (status == "HITL") and locked` | `can_approve = (status in ("HITL","CLARIFY")) and locked` — CLARIFY 判定单不再被禁用批准，节点已部署 + 公网 #/mailbox E2E 复验 |
| AgentCache 命中回写 | 无 | `skills/_runtime.py` 缓存命中时回写 `ctx.scratch`（rfq/specs/quote/dfm/verification/step_facts），多 skill DAG 二次调用不丢中间产物（TDD 2 测试 + 回归绿） |
| md 文档 | 两包存在陈旧/未脱敏副本 | 全量双向 md 同步（含 K12 脱敏稿） |
| junk / 活数据 / 备份件 | — | `__pycache__`、`*.pyc`、`.pytest_cache`、`data/crm.sqlite3`、**文件名含 `.bak` 者一律不入出货集**（BAD 契约收紧：旧 zip 曾漏收 `tests/*.py.bak2.<ts>`、`config/settings.yaml.pre-omni.bak`） |
| node 包内容 | GPN 缺 64 件（docs/ notebooks/ webui 源码/ env·models 件） | GPN 对齐 GP 出货集（缺 0 件、覆盖漂移 0 件），tar 与 zip 同集同字节 |

### 与上一版 728 zip 的血统对账（旧 zip 干跑快照 vs 本包出货集）
新增 15 件：
  + docs/BENCHMARK-GPU.md
  + docs/DEMO_SCRIPT.md
  + docs/EMAIL_SUBSYSTEM.md
  + docs/REAL_STATE.md
  + docs/REPRODUCTION.md
  + docs/SKILLS.md
  + docs/SUBMISSION_CHECKLIST.md
  + docs/TECH_STACK.md
  + env/nemotron.yml
  + env/occ.yml
  + models/MODELS.md
  + models/fetch_and_launch.sh
  + scripts/verify_replica.sh
  + tests/test_skill_cache_scratch_writeback.py
  + webui-dist/assets/index-DDaZfjqF.js
剔除 1 件：
  - webui-dist/assets/index-DSmUweh8.js
（无其它增删；新增件均为 repo HEAD 现有件或线上同代 dist，剔除件为被新 dist 取代的旧构建）

三方核对（节点@now / 本地 repo / 包）：以本地 repo 为权威；节点侧 9 项 SAFE_LOCAL（含 P1 修复线上在跑）、5 项 SAFE_PKG、2 项节点调优件不回灌（无能力损失）。

## CoT 任务执行结果

### ① 节点信息收集（SSH 实测，09-27）
- 服务：v7.1.0-livekernel · engine live:7862 · Omni live:8002 · contexts 4,986
- skills 39 目录 · README badge：pytest 1602 passed / GB10 aarch64 700 passed / HTTP endpoints 69

### ② 包组装口径
- 出货集 = 包目录遍历 − BAD 排除契约 − 文件名含 `.bak`；data 自测夹具（golden_scenarios / eval_set / samples）从本地 repo 补源（复制前脱敏预扫 0 命中）
- node tar：GPN 按同一契约 + 节点运行时产物排除（data/demo、data/flywheel_demo、data/node_evidence、GPN 独有 GitHub 脚手架）后构建，构建前先与 GP 出货集逐字节对齐
- 目录实测 55.1 MB（差额 = .gitignore 排除的运行数据，不入库；完整体积含 docs/ 截图资产 + webui-dist）

### ③ GitHub 标准结构
```
github-package/
├── README.md / LICENSE(MIT) / CHANGELOG / MANIFEST / CONTRIBUTING / .gitignore(强化)
├── docs/  ← 141 md（架构/PRD/验收/十日谈）+ screenshots 105 张
│   ├── deploy.ipynb        ← 环境配置 notebook（nbformat 4 合法）
│   └── delivery/           ← 比赛物料（SKILL-PACK 规范 / PPT 大纲演讲稿 / NVIDIA全栈+选型 / 截图清单）
├── skills/ 39 · openshell/ 4 策略 · services/ · agents/ · adapters/ · tests/ 135 个
├── openclaw-skills/text2cad · deploy/nim(.env.example 模板无真实值)
└── .github/workflows/ci.yml
```

### ④ 脱敏三重自检
| 检查项 | 命中 | 处理 |
|---|---|---|
| 公网 IP（节点公网地址） | 0 | `<NODE-PUBLIC-IP>` 占位（复制源预扫 + 出货后复扫双保险） |
| 内网 IP | 0 | `<NODE-LAN-IP>` 占位 |
| 真实账号（foxmail/QQ） | 0 | `<REDACTED-ACCOUNT>` |
| password/api_key/token 赋值 | 0 | deploy/nim 仅 .env.example 模板 |
| deny-list token 折叠 | 0 | 生产级扫描器（scripts/export_demo._secret_tokens + _collapse_concat） |

注：alice/tester/sales@union* 等 70+ 邮箱均为 demo/test 样例数据（测试夹具），按惯例保留。

### ⑤ .gitignore 强化
运行数据一律**逐条列 data/ 子路径** + 白名单取反（samples/、golden_scenarios.json）——三重保险（build 集排除 + gitignore + 已物理不在包内）。**禁加 `data/` 整目录规则**：晚于取反的整目录排除会连坐白名单，公开仓库将丢失测试样本。

### ⑥ 终验（09-28 刷新轮，zip 出厂前）
- **七面验证**（`scripts/_p7_verify.py`，逐产物，RESULT: PASS）：CRC 全过（testzip）/ namelist==manifest 集合双向 / ZIP==DIR 逐字节 md5 双边 / 排除断言（运行数据·凭据·pycache·`.bak` 0 命中 + 17 项关键交付物齐全）/ 脱敏复扫（deny-list token 折叠 0 / 公网 IP 0，RFC5737 文档段豁免，bundle 版本串误报逐条列名）/ foxmail·qq 账号扫描 / 跨产物一致性（四 zip 逐字节同 md5 + tar vs zip 内容集 0 差异）。
- **dist 代次断言**：每个产物内 `webui-dist/assets/index-DDaZfjqF.js` 与包目录同 md5（= 公网 8051 现行构建）。
- **批准门断言**：每个产物内 `services/mailbox_api.py` 含 CLARIFY 修复、旧 `== "HITL"` 缺陷门 0 命中。
- **tests/ 对账本地 repo**：两侧 139 个同名文件，md5 双边 —— **34 个仅 CRLF/LF 行尾差异（本地 repo 为 Windows CRLF 工作树，内容零差异）、0 个内容差异**；单侧独有件 2 个 = 已被 BAD 契约剔除的 `.bak` 备份件。
- **包内全量 pytest**：1596 passed, 11 skipped, 9 warnings in 661.95s (0:11:01) EXIT=0（口径：`PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python -m pytest tests/ -q`，运行目录 = 包根；日志 `盘点汇总/_gp_pkg_pytest_full.log`）。

## 下一步（用户执行）
```bash
cd 盘点汇总/github-package
git init && git add . && git commit -m "v7.1.0 release: NVIDIA NCP-AAI aligned"
git remote add origin <你的repo> && git push -u origin main
```
README 里替换 deploy.ipynb 的 repo URL 占位符即可。
