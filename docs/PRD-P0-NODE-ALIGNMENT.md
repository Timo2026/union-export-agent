# PRD-P0 · 节点对齐三连（安全止血 / OpenClaw 接线 / 引擎上线）

> 版本：v1.0 | 日期：2026-09-21 | 状态：**待 user 确认后执行**
> 关联：主 PRD `docs/PRD-MASTER-UEA-DELIVERY.md` · 前代 `docs/PRD-P0-DELIVERY.md`（已被主 PRD 取代，保留溯源）· `docs/NODE-DIFF.md` · 方案 `docs/PLAN-gpu-nvidia-model-stack.md`
> 依据：2026-09-21 06:00 UTC 节点实测侦察（14 轮 SSH 探针）+ 本地代码级核查。本文所有断言带 file:line / 探针输出证据。

---

## 0. 决策基线（user 2026-09-21 拍板，执行中不再重开）

| # | 决策 | 内容 |
|---|------|------|
| D1 | 执行路径 | **B：Qoder 经 SSH 驱动 + 幂等部署脚本双用途**；分阶段执行，每阶段 部署→测试→检查 三步走 |
| D2 | StepFun | **保留**，仅作云端验证/搜网 fallback；primary 走本地 vLLM；livekernel 核心链永不调云（铁律①） |
| D3 | 旧副本 | **整目录替换**：rm -rf 旧副本后解干净新包，绝不在旧副本上就地更新 |
| D4 | 阶段顺序 | 0→1→2 顺序执行；阶段 1 不依赖引擎，可提前 |
| D5 | 模型分层 | **4B 常驻快起驱动 skill；30B/Embed/Omni 挂 GPU 待命、经 skill/程序按需调用；OpenClaw 不常驻多模型** |

---

## 1. 节点实况基线（侦察结论，2026-09-21 06:00 UTC）

| 域 | 状态 | 证据 |
|---|---|---|
| OpenClaw | 网关 **active**（pid 787772，00:38:40 UTC 起，health `{"ok":true,"status":"live"}`，:18789 loopback）；35 skill 全 NVIDIA 栈、零 union；模型链 = stepfun-plan 全家（provider `models:[]`、无 apiKey，配额耗尽）→ **LLM 调用当前全失败**；本地 vLLM :8000 与临时垫片 :8901 均可用但**未接线** | systemd/health 探针；`~/.openclaw/openclaw.json`（`models.providers` 仅 stepfun-plan；`agents.entries.main.model.fallbacks` 全 stepfun 变体） |
| NVIDIA 基座 | `~/nvidia` 完整：nv.sh 编排 + hf-cache 四模型全下载（4B 7.5G / **30B-A3B-NVFP4 18G** / Omni 5.3G / Embed-1B 997M）+ skills staging 77M；vLLM 0.20.0 + torch 2.11.0+cu130（nemotron env）；**NeMo/nemoguardrails/AgentIQ/Parakeet 未安装** | 包清点 + du 探针 |
| 模型层 | **:8000 vLLM 服务中，模型 ID `nemotron-3-nano-4b`**（pid 827601，05:49:51 startup complete，max_model_len 16384）；**真实 chat 冒烟通过**（返回完整 completion）；30B/Embed/Omni 已下载未起服 | `/v1/models` + chat/completions 冒烟探针 |
| 引擎（Timo） | **节点不存在**：:7862 无服务；无 engine_src；旧副本 settings 的 engine_src 写死 Windows 路径 | 端口/目录探针 |
| miniconda | `nemotron`（py3.12.14）= 推理栈；**`occ`（py3.11.16，85 包）= 现成应用环境**：cadquery 2.8.0 + OCP + fastapi 0.141.1 + uvicorn 0.53.0 + python-multipart 0.0.32 + pypdf 6.19.0 + openpyxl 3.1.5 + pytest 9.1.1；**缺 reportlab + requests**（前者可选依赖缺库显式降级不炸链——tests/test_quote_pdf.py:66；后者仅 scripts/e2e_trade_agent.py 用） | 定向包版本探针 |
| 端口 | **8900 空闲**（livekernel 默认端口，services/api_server.py:930-932）；已占：8888（inference api_server）、8901（shim）、9000（jupyter）、9100、8000（vLLM）、18789（网关） | ss -tlnp 全量探针 |
| 旧副本 | `~/union-deploy/union-export-demo` **仍带 `data/credentials.json` + `.git`**，外加旧 tarball `union-export-node.tar.gz` | 探针实测 CRED-FILE-EXISTS |
| 链路/硬件 | 上行 0.4-0.5 MB/s（链路瓶颈）；节点→清华源 5.7 MB/s；zstd 二进制在；20 核；磁盘余 1.5T；统一内存 121GiB（当前 available 70G，网关 RSS 38.6G） | 探针实测 |

**本地基线**：Windows + 系统 Python 3.11.9（无 .venv）；干净导出包 `C:\Users\<user>\Documents\demo\union-export-agent-v6.3.1-p0b-livekernel.zip`（702 条目；无 credentials.json/.env；.git 为干净新仓——无 remote、零敏感串命中；deploy/ 仅 10 个基础设施模板，**带密码的 node_deploy.py 已正确排除**）；当前版本 v6.3.1（api_server.py:88 / CHANGELOG / MANIFEST / README 四处一致）；引擎源码实际体量 **~2MB**（app 1.4M + src 623K + 44 个 py；.venv 1.2G 与 data/stp_files 须排除）。

---

## 2. P0 范围

| 阶段 | 目标 | 前置 | 状态 |
|------|------|------|------|
| **P0-A** | 阶段 0 · 安全止血：节点旧副本整目录替换 + 部署脚本脱敏 | 无 | ⬜ 待执行 |
| **P0-B** | 阶段 1 · OpenClaw 模型接线：本地 vLLM 设为 primary，StepFun 降为 fallback，停垫片 | P0-A（脚本先行即可，可并行） | ⬜ 待执行 |
| **P0-C** | 阶段 2 · 引擎上线：Timo 引擎源码上节点 + 节点 settings 引擎段 | 无（不依赖 B） | ⬜ 待执行 |

**范围外（后续 PRD）**：阶段 3 livekernel 整目录部署 + pytest（P1）；阶段 4 OpenClaw union skill（P2）。本文档 §3 冻结其接口约定（模型分层 + settings 修订规格），使 P1 只需执行。

### 已知限制 · 多模态驱动三层断（2026-09-21 核查，user 提问触发）

| 层 | 实况 | 证据 |
|---|---|---|
| 内嵌 OmniVoice 驱动（ASR/TTS，services/asr_engine.py:1-3 的 `tools/omnivoice/`，6.3G） | **未进导出包**：export_demo.py:37-47 白名单制，tools/ 不在名单；且 engine/ 是 Windows 便携 Python 环境（DLLs/Lib/python311.dll/api-ms-win-*.dll），aarch64 节点不可运行 | zip tools/ 条目 = 0；engine 目录构成实测 |
| Omni-30B 推理服务 | 权重在（hf-cache 5.3G NVFP4）、nv.sh serveomni 编排在，但 **:8002/:8020 无监听——服务没起** | 端口全量扫描 |
| funasr/LM Studio 端点（settings.yaml:31-32 :8089/:1234） | Windows 本地口径，节点不存在 | 端口扫描 |

**影响面**：仅语音 intake 与图纸 VLM 感知两个多模态入口；**黄金链文本路径（邮件正文/PDF 附件）不受影响**（occ 有 pypdf 6.19.0）。**处置**：P0/P1 demo 口径 = 多模态入口显式降级（settings.yaml funasr.allow_mock 既有机制 + asr_engine.py 不可达返 None 不冒充），文档诚实标注；若多模态演示为硬需求 → P1 选项：起 Omni-30B（权重已在，nv.sh serveomni，配 agent.yaml:35-37 VISION_NIM/ASR_NIM）或节点重建 OmniVoice 栈（依赖地狱，不推荐）。

### 交付载具 v2 · 节点自举笔记本（2026-09-21 构建，detect 全链实测通过）

P0 三阶段改由 `deploy/node_bootstrap.ipynb`（15 单元格 / ~61KB / 纯 stdlib / 零 IP 与凭据字面量）驱动，替代"48MB 上传 + 逐条手工操作"；`deploy/node_deploy.py` 同步瘦身为轻量上传器（SFTP + sha256 双校验 + 下一步指引，不再内联部署流程）。

| 维度 | 规格 |
|---|---|
| 模式 | `UEA_BOOT_MODE=detect`（默认，只读基线）/ `execute`（阶段 0-3）/ `UEA_BOOT_SMOKE=1` 真实推理冒烟 / `UEA_BOOT_GOLDEN=1` 黄金链 verdict |
| 传输 | `local`（节点上 bash -lc）/ `ssh`（本机 paramiko；坐标走 `UEA_NODE_HOST/PORT/USER/PWD` env，nb-config） |
| 探测 | 4 段 detect（host/conda/ports → openclaw/vllm → engine/livekernel/staging/security → gap 表 + 阶段计划） |
| 护栏 | `ALLOWED_RM` 精确路径白清单 + HOME 前缀断言；quarantine 优先于 rm；网关重启 / pip / force-replace 均 env 显式开启（默认关，nb-exec-guard） |
| 证据 | 每轮报告 JSON 落节点 `~/union-deploy/backup/bootstrap-report-<TS>.json`（nb-final） |

- **detect 实测**（2026-09-21 18:53 / 18:59 两轮 SSH 只读）：22 行报告、9 探测域、8 项 gap 全部映射阶段 0-3；SMOKE 轮对 :8001 发真实 chat——`content='pong'` + `reasoning` 字段可解析（§3.4 格式兼容在节点复证）。
- **凭据卫生**：坐标单点 `deploy/node_coords.py`（env 注入，缺失显式失败并给注入示例）；14 个 spark 脚本硬编码坐标块全量替换；回归锁 `tests/test_deploy_manifests.py::test_deploy_no_hardcoded_node_coords`（红→绿，三种赋值形态全命中）；全量回归 805 passed / 1 skipped。
- **实况复核**（18:53，与 §1 06:00 侦察的差异，execute 前须拍板）：**:8000 4B 已停**（06:00 在服 pid 827601 → 现 curl 000）；**:8001 30B-A3B-NVFP4 在服**（pid 953771）；**:8002 Omni-30B 在服**（pid 962113）。影响 §3.1/§3.3/§5 的 4B-primary 锁定：或重启 4B 保 D5 基线，或 primary 改指 :8001（stage 1 补丁规格由 env `UEA_VLLM_URL`/`UEA_VLLM_MODEL` 驱动，改指无需动笔记本；D5 基线变更属 user 决策）。

---

## 3. 模型分层架构（D5 落地规范）

### 3.1 端口与角色映射（冻结）

| 层 | 模型 | 端口 | 生命周期 | 消费者 |
|---|---|---|---|---|
| L0 常驻 | nemotron-3-nano-4b | **:8000**（现状保持，勿重启折腾） | 常驻 | OpenClaw primary + livekernel FAST/VISION/REASON 默认档 |
| L1 按需 | 30B-A3B-NVFP4（18G 已下载） | :8001（nv.sh serve30b） | 按需起停，权重常驻 page cache 起服快 | skill 内深度推理（ceo-decision / 报价复核），程序内调用 |
| L2 按需 | Embed-1B（997M） | :8011 或与 L0 共实例 | 按需 | livekernel rag_layers.embed_url |
| L2 按需 | Omni-30B（5.3G） | :8002（nv.sh serveomni） | 按需 | 多模态 intake（VLM/ASR/OCR） |
| 云 | stepfun-plan/step-5-preview | api.stepfun.com | fallback 位，无 key 不生效 | **仅** OpenClaw 搜网验证意图；livekernel 核心链零调用 |

> nv.sh 头注释称 ":8000=30B / :8001=4B" 与实况相反（现 :8000=4B）。**以实况为准**：:8000=4B 常驻不动，同步修订 nv.sh 注释，避免下一个人被误导。

### 3.2 内存预算（121GiB 统一内存）

| 占用 | 现状 | P0 后目标 |
|---|---|---|
| OpenClaw 网关 | 38.6G RSS（峰值 53.4G） | 不变（节点主力运行时） |
| L0 4B vLLM | 已起（util 0.70-0.85 档） | 阶段 3 实测精确占用后下调 util 至 ≤0.30，给 L1 让位 |
| L1 30B | 未起 | 与 L0 **互斥**：起 30B 前停 4B 或压 util；30B util ~0.45（~54G） |

约束结论：**30B 与 4B+网关不可三方共存**。"挂 GPU 待命"的工程落地 = 权重常驻磁盘/page cache + 按需起停（nv.sh 已验证）；vLLM sleep-mode（权重留显存、KV 释放）作为优化选项留待阶段 3 实测后决定，**本文档不写死该 API**（未验证不主张）。

### 3.3 livekernel model_router 角色映射（阶段 3 settings 修订规格，冻结）

`config/settings.yaml`（services/config.py:19-21 只读此单文件；节点部署**不做整文件覆盖**，由笔记本阶段 3 行级外科修补：PATCH_SET 正则替换保注释、写后 yaml.safe_load 校验、.bak-uea 备份、幂等 NO-CHANGE；tests/test_node_bootstrap_notebook.py:208 锁注释保留）：

| 角色 | 节点值 |
|---|---|
| FAST / VISION / REASON | `http://127.0.0.1:8000/v1` / `nemotron-3-nano-4b` |
| EMBED | `http://127.0.0.1:8011/v1`（Embed-1B 起服后填；未起则哈希降级，显式 MOCK 不冒充） |
| ASR | 节点无 :8089 → `allow_mock: true` 显式降级（funasr 段整体关） |
| DETERMINISTIC | Timo 引擎锁死不变（铁律①） |
| backend | `local` |

`config/settings.dgx-spark-nvidia.yaml` 现文件**已过期**（:34-52 NIM 端口 :8002/:8020/:8011 节点不存在；:20-21 engine_src 指 `/workspace/_timo_engine`（实测不存在）；:56-69 fallback 指 :8888 Qwen 而非实测 :8000；:104 `workbench_port: 8888` 与 inference 服务撞位）→ P0-C 阶段 2 顺手重写为"实测口径"版，阶段 3 直接采用。

### 3.4 reasoning 格式兼容（接线方必须处理）

:8000 冒烟实测：Nemotron-3 为 reasoning 模型，`choices[0].message.content` 为 **null**，推理文本在 `reasoning` 字段，`max_tokens` 过小时全部预算被推理吃光（finish_reason=length）。livekernel 的 LLM 客户端与 OpenClaw 接线均需：解析 `reasoning` 字段 + 合理放大 max_tokens。**阶段 1 冒烟用例须覆盖此格式**。

---

## 4. P0-A · 阶段 0：安全止血

### 目标
清除节点上的凭证暴露面（旧副本 credentials.json + .git + 旧 tarball），部署脚本去硬编码密码，为整目录替换（D3）准备好干净包。

### 执行项
1. **本地备份旧副本**（仅留本地 Windows，任何情况不进导出包）：`~/union-deploy/union-export-demo` 整体 tar 到 `C:\Users\<user>\Documents\demo\node-oldcopy-backup-20260921.tar.gz`（含 credentials.json——本地留存用于轮换核对，日志中文件名可示、内容不示）
2. **节点删除**：`rm -rf ~/union-deploy/union-export-demo ~/union-deploy/union-export-node.tar.gz`（删除前 ls 确认路径精确匹配，不碰 `~/inference`、`~/nvidia`、`~/miniconda3`）
3. **部署脚本脱敏（已完成，载具 v2 配套）**：`deploy/node_deploy.py` 重写为轻量上传器；节点坐标单点 `deploy/node_coords.py` 只读 env（`UEA_NODE_HOST/PORT/USER/PWD`，缺失显式 SystemExit + 注入示例，不落盘不交互）；14 个 deploy/*.py spark 脚本硬编码坐标块全量替换；回归测试 `test_deploy_no_hardcoded_node_coords` 锁定（红→绿）。IP 一并 env 化——本 PRD 初版"IP 非密可保留常量"的宽容作废（测试口径更严）
4. **构建节点部署包**：从干净导出 zip（v6.3.1-p0b）解出内容打 node tarball（.git 可去留两可——干净仓、体积小；保留不影响安全，去掉更洁）；命名 `union-export-node-v631-p0b.tar.gz`
5. **轮换提醒**（user 侧执行）：节点 SSH 密码、QQ 邮箱授权码按既定轮换清单处理（memory 已记录暴露史）

### 验收清单
- [ ] 节点 `ls ~/union-deploy/` 无 union-export-demo、无旧 tar.gz
- [ ] 本地备份 tar 存在且 `tar -tzf` 可列
- [ ] `grep -c "$UEA_NODE_PWD" deploy/node_deploy.py` = 0（节点密码字面量见本地 node.env，不写死/不入包；已满足：全 deploy/ 目录 0 命中）；`UEA_NODE_PWD` 未设时脚本显式失败并打印注入示例（非崩溃、非交互输入——自动化优先）
- [ ] 新 node tarball `tar -tzf` 无 credentials.json / 无 .env / 无 node_deploy.py

### 回滚
旧副本本地备份在，任何时候可回传节点恢复原状（但恢复即恢复暴露面，仅限取证场景）。

---

## 5. P0-B · 阶段 1：OpenClaw 模型接线

### 目标
OpenClaw 从"配额耗死的云端链"切到"本地 vLLM primary"，恢复真实推理能力；StepFun 按 D2 保留 fallback 位；清理临时垫片。

> **执行前置（2026-09-21 18:53 实况复核）**：`:8000` 4B 已停（§2 载具 v2 节实测：06:00 在服 pid 827601 → 现 curl 000）。阶段 1 执行前须 user 拍板：重启 4B 保持 D5 基线，或 primary 改指 :8001 30B（`UEA_VLLM_URL=http://127.0.0.1:8001/v1 UEA_VLLM_MODEL=nemotron-3-nano-30b-a3b`，stage 1 补丁规格随之变更，下方验收清单模型 ID 同步改）。

### 执行项
1. **备份配置**：`cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.bak-20260921`
2. **编辑 `~/.openclaw/openclaw.json`**（改前 `python3 -m json.tool` 校验语法）：
   - `models.providers` 增：`"local-vllm": {"baseUrl": "http://127.0.0.1:8000/v1", "api": "openai-completions", "models": ["nemotron-3-nano-4b"]}`（本地 vLLM 无鉴权，不配 key）
   - `agents.entries.main.model.primary` = `"local-vllm/nemotron-3-nano-4b"`
   - `agents.entries.main.model.fallbacks` 保留 stepfun 链（D2；无 key 自然不生效，key 恢复后仅承搜网验证）
   - `models.mode` 保持 `merge`
3. **停垫片**：kill `openai_compat_shim.py` 进程（:8901）；**不动**其上游 :8888 inference api_server
4. **重启网关**：`systemctl --user restart openclaw-gateway.service`；`curl -s 127.0.0.1:18789/health` 确认 live
5. **冒烟（覆盖 §3.4 格式）**：经网关发一个真实任务，断言返回来自 `nemotron-3-nano-4b` 的真实 completion（校验 `reasoning` 字段可解析、非空）
6. **nv.sh 注释修订**：头注释端口映射改为实况（:8000=4B 常驻 / :8001=30B / :8002=Omni）

### 验收清单
- [ ] health live；openclaw.json 语法校验通过
- [ ] 冒烟任务返回真实推理文本（模型 ID = nemotron-3-nano-4b）
- [ ] :8901 无监听；:8888 inference api_server 仍在（pid 411542 不动）
- [ ] 备份文件在节点（脱敏范围外，用户 home 私有）

### 风险与回退
网关重启期间 ~10s 不可用（可接受）；配置写坏 → 还原 `.bak-20260921` + 重启。**铁律①注意**：StepFun fallback 保留意味着存在云端出站可能——限定在 OpenClaw 运行时层、仅搜网验证意图；livekernel 核心链零云调用（阶段 3 由测试断言）。

---

## 6. P0-C · 阶段 2：引擎上线

### 目标
Timo 引擎（CNC AI Brain）源码落节点 occ 环境，黄金链的 DFM/报价引擎步获得离线兜底能力（在线 :7862 节点没有，允许 allow_fallback 走本地 import）。

### 执行项
1. **本地打包引擎源码**（排除 .venv 1.2G / data/stp_files / PPT 交付 / __pycache__ / _tmp_*）：仅 `app/ + src/ + requirements*.txt + README/CHANGELOG/CONTRIBUTING + LICENSE`，zstd 压缩（预计压缩后 <1MB——源码 44 个 py 共 2MB）
2. **SFTP 上传 + 解包**至 `~/union-deploy/engine/Timo_CNC-AI-Brain-v12.0-Fusion`（上行 0.45MB/s，<1MB 约秒级）
3. **引擎接线（env 优先，免改配置）**：设 `CNC_BRAIN_SRC=~/union-deploy/engine/Timo_CNC-AI-Brain-v12.0-Fusion` + `CNC_BRAIN_PY=~/miniconda3/envs/occ/bin/python`（adapters/timo_adapter.py:51-58：env 覆盖优先级最高；若 /workspace 可写则按平台缺省布局放置更佳——timo_adapter.py:37-38）。**timo.base_url 保持 `http://127.0.0.1:7862` 不动**：节点无监听 → health 失败 → 自动走离线桥接（timo_adapter.py:85-90）；**不要置 null**（:71 `str(t.get("base_url"))` 会把 None 变成 "None" 串）
4. **重写 `config/settings.dgx-spark-nvidia.yaml` 为实测口径**：model_router 按 §3.3；server.workbench_port 改 8900（避开 8888 占用）；本文件仅 ops 约定不被代码加载（services/config.py:19-21 只读 settings.yaml），阶段 3 以其为覆盖源
5. **节点引擎冒烟**：occ python import 引擎 + 跑一个样例 STEP 的 DFM/报价计算（复用 deploy/occ_step_smoke.py 套路），记录输出
6. **引擎与 occ 环境依赖核对**：requirements.txt vs occ 已装 85 包，缺项清华源补（cadquery 2.8.0+OCP 已在，预计缺 0-2 个小包）

### 验收清单
- [ ] 节点 `~/union-deploy/engine/` 存在且 py 文件数 = 44
- [ ] `CNC_BRAIN_SRC`/`CNC_BRAIN_PY` env 已设；occ python 可 import 引擎
- [ ] 引擎冒烟：STEP → DFM/报价结果输出（与本地同输入确定性比对一致——sha 锁定口径）
- [ ] settings.dgx-spark-nvidia.yaml 无 Windows 路径、无 :1234/:1278/:8089、workbench_port=8900

### 风险与回退
引擎在 aarch64 + OCP 上的行为差异：若冒烟与本地结果不一致 → 记录差异点，阶段 3 前修复或显式降级标注（不冒充）。回滚 = 删 `~/union-deploy/engine`（源码本地永存）。

---

## 7. 验收总 checklist（P0 出口）

- [ ] P0-A 五项全过（§4）
- [ ] P0-B 五项全过（§5），OpenClaw 真实推理恢复
- [ ] P0-C 五项全过（§6），引擎节点可跑
- [ ] 三段证据落盘：`docs/evidence/p0-node-alignment-20260921.md`（命令输出脱敏后归档）
- [ ] 铁律①复核：节点无任何新增外发通道；egress 仍全 DENY（services/egress_gate.py 默认拒绝未改）

---

## 8. 风险与回退（P0 级）

| 风险 | 概率 | 处置 |
|---|---|---|
| openclaw.json 手编辑语法错误 | 中 | 改前 json.tool 校验 + .bak 备份；坏则还原重启 |
| 引擎 aarch64 结果与本地不一致 | 中 | 冒烟即发现；记录差异，阶段 3 前决断；不冒充一致 |
| 误删节点目录 | 低 | rm 前 ls 精确匹配；只动 `~/union-deploy` 两条目 |
| 4B util 下调后 KV 不足 | 低 | 阶段 3 实测后调；P0 不动 4B 运行参数 |
| StepFun fallback 被意外触发外发业务数据 | 低 | livekernel 核心链零云调用（阶段 3 测试断言）；OpenClaw 层仅搜网意图 |

---

## 9. 铁律保障（全阶段不变）

1. **铁律① data-stays-local**：livekernel 核心链（RFQ→报价→回复）零云端调用；StepFun 仅 OpenClaw 运行时 fallback 位且无 key 不生效；SMTP/IMAP/webhook 仍全 DENY（services/egress_gate.py 默认拒绝）
2. **DETERMINISTIC 永远 Timo**：calc_quote/verify_gate 不走 LLM；引擎上节点正是为了保这条
3. **显式降级不冒充**：reportlab 缺 → `reportlab_not_installed` 标注（阶段 3 会补装，P0 接受降级态）；ASR 无端点 → mock 显式标注
4. **凭证不出机**：节点密码/授权码只在本地与节点间传递，导出包零凭证（已双重验证：zip 无 credentials.json、deploy/ 无 node_deploy.py）

---

## 10. 待确认项（执行前最后一眼）

1. P0 范围切分（A/B/C 三段，阶段 3/4 留 P1/P2）是否符合预期？
2. §3.2 内存策略："30B 按需起停、与 4B 互斥"是否接受？（sleep-mode 留阶段 3 实测）
3. §5 步骤 2 的 fallback 保留顺序：stepfun 链原序保留，认可否？

---

## 一句话

**P0 三步：节点清污换新包（A）→ OpenClaw 接本地 4B 恢复真推理（B）→ 引擎上节点保铁律①（C）；全部是配置与搬运，零新功能开发；每阶段部署→测试→检查，证据落盘后交 P1。**
