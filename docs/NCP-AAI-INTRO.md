# NCP-AAI 介绍材料 — 设备 / 全栈 / 模型 / 项目四问

> 所有数字均为 2026-09-26 节点 spark-388d 实测口径; 证据列 file:line 或节点命令输出。
> 配套演示顺序: `docs/DEMO-RUNBOOK-8051.md`(公网 `http://<NODE-PUBLIC-IP>:8051/`)。

## 1. 设备 — 单台 NVIDIA DGX Spark 扛全链

| 项 | 实测值 | 证据 |
|----|--------|------|
| 设备 | NVIDIA GB10(aarch64, sm_121) | 节点 `nvidia-smi --query-gpu=name` → `NVIDIA GB10`; `uname -m` → `aarch64` |
| 驱动 | 580.82.09 | 同上 |
| 统一内存 | 121GB 总(实占 98G / 可用 22G) | 节点 `free -g` |
| 常驻重负载 | Omni-30B-A3B NVFP4 单服务(09-22 实测实占 ~73.5G 量级) | 节点 `ps aux` vLLM 进程 |

讲解口径: 没有机房、没有多卡集群 — 一台桌面级 GB10, 同时跑推理、向量、几何报价内核和全部业务服务, 公网一条线(frp → :8051)就是评委入口。

## 2. 全栈 — NVIDIA 技术栈用在哪、用到哪

| 层 | 技术 | 用在哪(证据) |
|----|------|------|
| 推理服务 | **vLLM 0.20.0**(env `nemotron`, OpenAI 兼容端点) | 节点 `pip show vllm` → 0.20.0; `ps aux` → `vllm.entrypoints.openai.api_server` |
| 模型 | **Nemotron-3-Nano-Omni-30B-A3B-Reasoning-NVFP4**(LLM+VLM+ASR 三角一) | HF cache 路径 + `--served-model-name nemotron-omni-30b-a3b --reasoning-parse…`(进程参数) |
| 模型 | **Nemotron-3-Embed-1B-NVFP4**(非对称双塔, `query:/passage:` 前缀) | 进程 `--runner pooling --convert embed`; config/models.yaml:24-32 |
| 模型 | Qwen3-0.6B(:8902, 低质真实续写 fallback, 不 MOCK) | 进程 `--gpu-memory-utilization 0.06`; config/models.yaml:13-15 |
| 量化 | NVFP4(全模型栈权重格式) | 模型目录名 `…-NVFP4` |
| 编排 | 自研 FastAPI/uvicorn(occ env,:8888) + OpenClaw 技能白名单 | services/api_server.py; `ps aux` uvicorn |
| 几何/工艺 | Timo 确定性内核(:7862, OCCT/CadQuery 栈) | config/settings.yaml:11; agents/cat_controller.py:434 |
| 几何环境 | conda env `occ`(py3.11 + cadquery 2.8.0 + OCP) | 节点 env 路径 `/home/Developer/miniconda3/envs/occ` |
| 检索 | 自建 SearXNG(:8080, 零外部 key) + 分层 RAG | `POST /v1/web/search`(api_server.py:535) |

诚实口径: NVIDIA 栈负责"感知与生成"(LLM/VLM/ASR/Embedding 四角色两个端点); **定价计算不走 NVIDIA 也不走 LLM** — 走确定性引擎(铁律②)。护栏是内置引擎(builtin), 不冒充 NeMo Guardrails; OCR 无独立服务, 由 Omni VLM 覆盖且显式 disabled(config/models.yaml:33-40)。

## 3. 模型 — 五角色一张表(config/models.yaml, 节点实测同款)

| 角色 | 模型 | 端点 | 用途 | 降级策略 |
|------|------|------|------|----------|
| REASON(LLM) | nemotron-omni-30b-a3b | :8002/v1 | RFQ 抽取/规划/草稿/摘要/翻译(LLM 提议, 引擎裁决) | 离线 → :8902 qwen3-0.6b 真实低质续写 |
| VISION(VLM) | nemotron-omni-30b-a3b | :8002/v1 | 图纸/图片感知, 只出事实不定价; 兼 OCR | 不可达显式 MOCK |
| ASR | nemotron-omni-30b-a3b | :8002/v1 | 语音→文字(节点 `asr_mode: cli`, scripts/asr_cli.py 子进程) | 不回落 omni(英文 caption 污染), 宁可显式 MOCK |
| EMBED | nemotron-embed-1b | :8011/v1 | RAG 向量(非对称前缀) | 不可达 → HashEmbedder 显式 MOCK |
| DETERMINISTIC | calc_quote+ConflictChecker(Timo) | :7862 | **报价/DFM 唯一权威** | 节点无监听 → 离线 byte-identical vendored kernel |

工具调用: :8002 带 `--enable-auto-tool-choice --tool-call-parser qwen3_coder`, probe 200 + 正确 tool_calls 实测可用(models.yaml:12)。

## 4. 项目四问

**解决什么问题?** 外贸机加工报价流程的"读需求 → 查工艺 → 算价格 → 人工把关 → 出单据"全链。客户从邮件/图纸/语音三个入口进来(含 zip 附件批量 BOM), 系统抽取需求、检测工艺冲突、由确定性引擎出价、HITL 收敛后产出报价单(PDF/XLSX)并落 CRM。行业痛点: 报价员来回对图纸对公差、口说无凭、价格口径漂移。

**给谁用?** 机加工出口企业的销售/工艺/报价员(一线用户), 以及他们的管理者(看板与审计)。评委视角: 一个"AI 当副驾驶、人当签字人"的样板。

**怎么用?** 公网打开 `http://<NODE-PUBLIC-IP>:8051/`(或节点本机 :8888): 邮件台收询价(S1-S5/M1 场景即真实黄金链); zip 丢进去自动批量报价; 图纸中心看折叠去重后的图纸; RAG 库管文档; 一句话走 Agent 技能(`POST /v1/agent/task`)。顺序细节见 `docs/DEMO-RUNBOOK-8051.md`。

**怎么用好?** 三条铁律 + 一个机制:
1. **LLM 不定价**(铁律②): 价格永远由 :7862 引擎裁决, LLM 只做抽取/规划/表达 — 用好模型的前提是划清它的职权。
2. **数据不出本机**(铁律①): 回复一律 draft_only; SMTP/IMAP/OAuth 默认禁 — 上公网也只暴露只读演示链。
3. **人工在环**(铁律③): BLOCKED/HITL 是终态不是失败; 语音与邮件冲突(M1)升级人, 不静默采纳任一方。
4. **诚实降级机制**: 任何端点不可达 → 显式 MOCK/fallback 并标注, 没有"假在线"; 这是把演示变成生产的关键工程素养。

## 5. 30 秒电梯稿(背下来)

"一台 NVIDIA DGX Spark, vLLM 0.20.0 上跑 Nemotron-3 全家桶 — Omni-30B-A3B 一个端点统一 LLM/视觉/语音, Embed-1B 管检索, Qwen3-0.6B 兜底。我们把它们圈在'感知与生成'层; 报价数字由一个确定性引擎裁决, 人只在 HITL 点头。客户从邮件、图纸、语音来的询价, 系统读需求、查冲突、出报价单, 冲突和缺参一律升级人工 — 不静默、不冒充、不外发。"
