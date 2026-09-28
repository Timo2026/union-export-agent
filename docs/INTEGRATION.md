# INTEGRATION.md — 真实后端接线指南

本主干的核心价值是**把冻结架构接到真实服务**（Replace the adapters, not the architecture）。
三个真实后端，全部本地、可降级、结果可溯源。

---

## 1. 制造决策内核 — cnc-ai-brain v12.0.0-fusion

**源码位置**（本机已解压）：
```
C:\Users\<user>\Desktop\比赛\英伟达第三\_timo_engine\Timo_CNC-AI-Brain-v12.0-Fusion - 副本
```
> 从 `Timo_CNC-AI-Brain-v12.0-Fusion - 副本 (2).zip`（2.8GB / 23126 文件）解压。
> 自带 `.venv`（含 OCP/cadquery/fastapi/uvicorn/numpy）。原 zip 的 `.venv` 缺 `pyvenv.cfg`，
> 已按系统 Python 3.11.9 (`C:\Users\<user>\AppData\Local\Programs\Python\Python311`) 修复。

### 1a. 在线路径（HTTP :7862）
```bash
python scripts/start_engine.py --background   # 用引擎 .venv 启动 app.main:app
# 健康检查
curl http://127.0.0.1:7862/api/health
```
端点：`/api/health` · `/api/conflict-check` · `/api/quote` · `/api/cnc-quick` · `/api/upload` · `/api/export`。

> 注意：`main_lite.py` 是零依赖精简版，**不含** `/api/conflict-check` 与 `/api/quote`；
> 在线结构化报价必须用完整版 `app.main:app`。

### 1b. 离线路径（vendored kernel，byte-identical）
`TimoAdapter._offline()` 用子进程调用引擎 `.venv` python 执行 `adapters/_kernel_bridge.py`：
```python
from src.neuro_core.conflict_check import ConflictChecker   # 真实禁忌矩阵
from app.main_lite import calc_quote                        # 真实确定性报价
```
—— **直接跑真实代码，无任何示意系数**。因此在线/离线结果一致（实测 S1 均 unit=222.8 / final=9413.3）。

配置见 `config/settings.yaml → timo.{base_url, engine_src, engine_python, allow_fallback}`。

---

## 2. 多模态 Intake + RAG — funasr-gui

**源码位置**：`C:\Users\<user>\funasr-gui`（server.py）。

| 服务 | 端口 | 用途 |
|------|------|------|
| FastAPI | :8866 | `/health` `/transcribe` `/rag/search` `/rag/ask` `/ingest` |
| ASR | :8089 | Qwen3-ASR-0.6B 语音转写 |
| VLM/LLM | :1234 | qwen3.8-27b（OpenAI 兼容，图纸/图片理解） |
| Embedding | :1278 | 向量化（SQLite FTS5 + RRF 混合检索） |

`FunASRAdapter` 在线命中真实端点；未启动时返回**显式 MOCK**（`_mock=True`, `_source=MOCK:...`），
绝不把模拟结果冒充生产转写/检索（对齐冻结 PRD「Offline mode must be clearly labeled」）。

> ASR 现实约束（已核验）： NeMo Retriever 自托管 Parakeet 音频 NIM **不支持 Blackwell/compute 12.0**，
> 故 DGX Spark 上 P0 本地 ASR 用 FunASR/Qwen3-ASR，Parakeet 仅作有受支持 GPU 时的可选后端。

---

## 3. Model Router（L3 Model Mesh）

`config/settings.yaml → model_router`：FAST/VISION/REASON/EMBED/ASR 五角色 + DETERMINISTIC。
- **DETERMINISTIC 永远走 Timo 内核**（报价/冲突/状态机/毛利），不走 LLM。
- backend 可切 `local`(funasr/ollama) | `nvidia`(NIM) | `mock`，上层 Context/Skill/Agent API 不变。

---

## 4. 降级矩阵

| 场景 | Timo :7862 | funasr :8866 | 行为 |
|------|-----------|--------------|------|
| 全在线 | ✅ | ✅ | 真实报价 + 真实 ASR/RAG |
| 仅内核在线 | ✅ | ❌ | 真实报价 + ASR/RAG 显式 MOCK |
| 仅 funasr 在线 | ❌ | ✅ | 离线 byte-identical 内核 + 真实多模态 |
| 全离线 | ❌ | ❌ | 离线内核 + MOCK 多模态，**S1–S5+M1 仍全绿** |

降级不改架构、不改上层协议；每个结果都带 `_source` 标签可溯源。

---

## 5. 上传端口 API 服务（services/api_server.py）

```bash
python scripts/start_api.py --port 8900 --background   # Swagger UI: http://127.0.0.1:8900/docs
python scripts/demo_uploads.py                          # 演示所有端口 (未起服务则用 TestClient)
```

- **单模态上传端口**：`/v1/upload/{email,step,audio,pdf,excel,image,auto}`（multipart 字段 `file`）。
- **统一 intake**：`/v1/rfq/intake` 一次收 `email_file/audio_file/step_file/pdf_file/excel_file` + 客户字段，
  保存到 `data/artifacts/{context_id}/`，解析后跑黄金链，返回 `context_id` + 结果。
- **契约端点**：`/v1/rfq/{cid}/{analyze,quote,verify,approve,reply-draft,crm-sync}`（PRD §13）。
- **STEP 几何**：`/v1/upload/step` 与 intake 均调用 `TimoAdapter.step_geometry`（引擎 `.venv` 子进程 → 真实 OCP
  B-rep 体积/重量）+ `step_features`（C1 孔/壁厚/圆角，5s 硬超时则 partial，不抛异常）。
- **线程安全**：CRM SQLite 连接用 `check_same_thread=False`（FastAPI 同步端点跑在线程池）。
- 依赖：`fastapi / uvicorn / python-multipart`（PDF/Excel 解析可选 `pypdf / openpyxl`，缺库显式 skipped）。

---

## 6. P1 商业层 / P3 闭环 / VLM 感知

### 6.1 Freight / Customs / Incoterms（services/commercial.py + config/commercial.yaml）
- 全部费率（运费/关税/VAT/保险/操作费/时效/Incoterm 承担项/de minimis）来自 `config/commercial.yaml`，
  **确定性计算，LLM 不参与数字**；改配置即改定价策略。
- 计费重 = `max(实重, 体积重)`；体积重 = 总体积cm³ / 运输方式除数（air 6000 / express 5000 / sea 1000）。
- Incoterm → `seller_quote_price`（货值 + 卖方承担项）；`landed_cost`（买方真实到手成本）。
- 由 `CATController.run(..., destination_country, shipping_mode, incoterm, hs_code)` 在报价后自动计算，
  写入 `ctx.commercial` 并进审计；API 端点 `/v1/rfq/{cid}/commercial` 读取。

### 6.2 Postmortem 闭环（services/postmortem.py）
- `record_outcome(crm, cid, won/lost, actual_cost, actual_leadtime_days)` → 偏差 → `knowledge_updates`，落 `postmortems` 表。
- `recall_customer_memory(crm, customer)` → Fact memory 召回（历史报价/复盘）→ Context 证据 + 风险信号。
- API 端点 `/v1/rfq/{cid}/postmortem`（form: outcome/actual_cost/actual_leadtime_days/note）。

### 6.3 VLM 图纸感知（adapters/funasr_adapter.perceive_image）
- 走 `vlm_url`（qwen3.8-27b @ :1234，OpenAI 兼容 `/v1/chat/completions`，base64 图片）。
- **只输出结构化感知事实**（零件类型/尺寸/材料/表面处理/公差/孔特征），不决定价格。
- VLM 离线（探测 `/v1/models`）→ 显式 `MOCK:vlm-offline`，不冒充生产感知。
- intake 中若感知为真实（非 MOCK），并入 `body_text` 供 RFQ 抽取参考。


