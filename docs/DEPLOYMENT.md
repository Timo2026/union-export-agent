# DEPLOYMENT.md — 部署指南（Profile A/B/C/D）

对齐冻结 PRD §16。四个 profile 共用同一套 Context/Skill/Agent/API 契约，只换后端接线。

## Profile A — Demo / Laptop（零 GPU 依赖）

```bash
# 无需启动任何后端: 离线 vendored kernel (byte-identical) + MOCK 多模态
python scripts/run_demo.py --offline      # S1-S5+M1 全绿
python -m pytest tests/ -q                # 全套回归
python scripts/start_api.py --port 8900   # 上传端口 API (Swagger /docs)
```
- engine：离线子进程 `import calc_quote+ConflictChecker`（引擎 `.venv`）
- 多模态：显式 `MOCK` 标注，不冒充
- 存储：SQLite + 本地文件

## Profile B — DGX Spark P0（真实本地服务）

```bash
# 1. 制造内核 (完整版 app.main:app, 含 /api/conflict-check /api/quote)
python scripts/start_engine.py --background          # :7862
# 2. 多模态 Intake + RAG (funasr-gui)
#    在 C:\Users\<user>\funasr-gui 启动 server.py → :8866 (ASR:8089/VLM:1234/emb:1278)
# 3. 上传端口 API
python scripts/start_api.py --port 8900 --background # :8900
# 4. 自检
python bootstrap.py                                   # 各后端在线状态
python scripts/demo_uploads.py                        # 全模态上传演示
```
- 或容器编排：`docker compose -f deploy/docker-compose.yml up -d --build`
- ASR：FunASR/Qwen3-ASR（P0 本地）；**不用 Parakeet**（Blackwell/compute 12.0 不支持自托管）
- 存储：PostgreSQL + 本地向量 + 对象存储；OTEL 上报 collector

## Profile E — spark-388d 节点（miniconda + OCC 环境，2026-09-20 实测）

节点：`203.0.113.10:6051`（SSH，user `Developer`），aarch64 / GB10 / 121GB 统一内存，
无 passwordless sudo → 全部 user-level 安装。`pypi.org` 不可达，`repo.anaconda.com` /
`conda.anaconda.org` / tuna+aliyun pypi 镜像可达。

```bash
# 1) miniconda (user-level, 已装: conda 26.7.1 → ~/miniconda3)
#    注: Anaconda ToS 需先接受 (conda 26.x 强制):
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

# 2) OCC 环境 (已建: python 3.11 + cadquery 2.8.0 + OCP aarch64)
#    STEP B-rep 冒烟已过: bbox/体积双路径 (raw OCP / cadquery) 一致
~/miniconda3/envs/occ/bin/python -c "import OCP, cadquery; print(cadquery.__version__)"

# 3) 离线内核指向节点环境 (免改 settings.yaml 的 Windows 路径)
export CNC_BRAIN_SRC=/path/to/cnc-ai-brain          # 引擎源码根 (含 app/ src/)
export CNC_BRAIN_PY=$HOME/miniconda3/envs/occ/bin/python   # 或引擎自带 venv
python scripts/start_api.py --port 8900 --background
```

- `CNC_BRAIN_SRC` / `CNC_BRAIN_PY` 环境变量覆盖 `config/settings.yaml` 的
  `timo.engine_src` / `timo.engine_python`（见 `adapters/timo_adapter.py` 构造器）；
  回归测试 `tests/test_timo_engine_env.py`。
- 复刻脚本：`deploy/probe_spark_miniconda.py`（节点自检）、`deploy/setup_occ_env.py`
  （幂等建环境）、`deploy/occ_step_smoke.py`（STEP B-rep 冒烟）。
- 工作目录约定：所有产物落 `$HOME` 下，不污染系统目录。

## Profile C —  production / lab

```bash
# agent.yaml 契约 (nemo-agents-spec-v1) 注册前, 先自洽校验:
python -c "from services.agent_spec import load_agent_spec, validate; print(validate(load_agent_spec()))"
# K8s 部署上传端口 API:
kubectl apply -f deploy/k8s.yaml
```
- Runtime：NeMo Fabric；Serving：NIM（`model_router.backend=nvidia`）
- RAG：NeMo Retriever；Guardrails：`guardrails.backend=nemo`（内置规则兜底）
- Observability：OTEL + DCGM（`observability.otlp_endpoint` 指向 collector）
- 契约字段需以目标 NeMo Platform 版本 CLI/schema 复核后注册（见 agent.yaml 顶部声明）

## Profile D — Scaled ASR

- ASR 独立部署在**实际支持 Parakeet 的 GPU**或 FunASR 集群；上层协议与 Profile C 一致。
- 仅扩展 ASR 层，Context/Skill/Agent API 不变。

## 端口总览

| 服务 | 端口 | 说明 |
|------|------|------|
| cnc-ai-brain（制造内核） | 7862 | `/api/health /api/conflict-check /api/quote /api/cnc-quick` |
| funasr-gui（多模态） | 8866 | `/health /transcribe /rag/search /rag/ask` |
| └ ASR | 8089 | Qwen3-ASR-0.6B |
| └ VLM/LLM | 1234 | qwen3.8-27b（OpenAI 兼容） |
| └ Embedding | 1278 | 向量化 |
| Union 上传端口 API | 8900 | `/v1/upload/* /v1/rfq/* /v1/guardrails/check /v1/traces/{cid} /v1/model-router/status /v1/agent-spec` |

## 环境要求

- Python 3.11（主干）；引擎 `.venv` 提供 OCP/cadquery/fastapi。
- 主干依赖：`PyYAML` + `fastapi/uvicorn/python-multipart`（+ 可选 `pypdf/openpyxl`）。
- 数据不出车间：业务主数据/客户文件/图纸/语音/Agent memory 默认本地处理；外部 API 需显式授权（egress allow-list）。
