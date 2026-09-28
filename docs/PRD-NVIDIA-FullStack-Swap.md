# PRD · NVIDIA 全栈平替方案（Spark 实证版）

> **部分作废（2026-09-20）**：NIM/Riva/Parakeet 路径随 docker 无权限与 Blackwell 约束关闭；模型栈以 `docs/PRD-MASTER-UEA-DELIVERY.md` v2.0 §1.2-F 实测表为准。

| 字段 | 内容 |
|------|------|
| 版本 | v2.0.0-nvidia-fullstack |
| 日期 | 2026-09-20 |
| 前提 | **Spark GPU 全栈已跑通**：LLM/VLM/ASR/OCR/Embedding 均在 NVIDIA 架构上可用 |
| 原则 | 配置级平替，不重写代码；每个角色逐个切，切一个验一个 |
| 密级 | 公开；禁止写 NGC_API_KEY |

---

## 1. 核心判断

**得分杠杆从「切一条链路碰瓷」升级为「全栈 NVIDIA 平替 + 行为等价回归」。**

> 同一套 Skill 契约与确定性引擎，6 个推理角色全部从 LMStudio/local 切到 NVIDIA 全栈组件，
> **引擎价格 sha256 必须不变**（铁律①的跨后端证明），LLM 字段允许统计差异并写明。

评委三刀升级答法：
1. **价格谁生成？** → Timo 引擎，与推理后端无关；local vs NVIDIA 两份 sha256 一致是铁证
2. **用了哪些 NVIDIA 技术？** → NIM(LLM/VLM/Embed) + Riva/Parakeet(ASR/OCR) + NeMo Retriever(RAG) + Guardrails + Triton（逐角色可指）
3. **在哪跑的？** → `docs/evidence/nvidia/` 每个角色一份冒烟 + 黄金链全栈对照

---

## 2. 角色映射矩阵（平替总表）

| 角色 | 当前 (local/LMStudio) | NVIDIA 全栈平替 | 接口 | 端点占位 | 切换证据 |
|------|----------------------|----------------|------|----------|----------|
| **REASON/FAST LLM** | `qwen3.8-27b` `:1234` | NIM for LLM (`Llama-3.1-8B/70B` 或 `Qwen-NIM`) | OpenAI `/v1` | `http://spark:8000/v1` | nim-smoke + chat 冒烟 |
| **VISION VLM** | `qwen3.8-27b` `:1234` | NIM for VLM (`Llama-3.2-11B-Vision` / `Qwen2-VL`) 或 vLLM+TensorRT | OpenAI `/v1` | `http://spark:8020/v1` | 图片理解冒烟 |
| **EMBED** | `Qwen3-Embedding-0.6B` `:1278` | NIM for Embedding (`nv-embedqa-e5-v5` / `snowflake-arctic-embed`) | OpenAI `/v1` | `http://spark:8011/v1` | 向量冒烟 + RAG 回归 |
| **ASR** | `Qwen3-ASR` `:8089` | NVIDIA Riva ASR 或 Parakeet TDT（看 GPU compute 兼容） | Riva gRPC/REST | `http://spark:9000` | 转写冒烟 |
| **OCR** | `PaddleOCR` (disabled) | NVIDIA Riva OCR 或 GPU 加速 OCR | REST | `http://spark:8100` | 文字识别冒烟 |
| **RAG 检索** | 本地文件向量 (`rag_layers.py`) | NeMo Retriever（Embedding + Reranking 微服务） | REST | `http://spark:8001` | RAG recall 回归 |
| **Guardrails** | builtin (`guardrails.py`) | NeMo Guardrails（Colang 可编程） | REST `:7331` | `http://spark:7331` | 注入/越狱负向回归 |
| **DETERMINISTIC** | Timo 引擎 `:7862` | **不平替**（铁律①锁定，永远走确定性内核） | — | — | sha256 跨后端比对 |

**关键不变量**：DETERMINISTIC 角色永远不平替。这是铁律①的核心——不管 LLM 换什么后端，价格永远由 Timo 引擎裁决。

---

## 3. 执行序（逐角色切，切一个验一个）

| 序 | 动作 | 命令 | 证据 |
|----|------|------|------|
| N0 | 节点自检：确认每个 NVIDIA 组件端口 | `nvidia-smi` + 逐组件 `/v1/models` 或 health | `00-nvidia-stack-selfcheck.txt` |
| N1 | 填 `models.nvidia-fullstack.yaml` 的实际端口 | 编辑配置 | 配置 diff |
| N2 | LLM 冒烟（首个平替） | `python services/nim_smoke.py --url http://spark:8000/v1` | `nim-llm-smoke.txt` |
| N3 | Embedding 冒烟 + RAG 向量回归 | nim_smoke embed + `tests/test_rag_layers.py` | `nim-embed-smoke.txt` |
| N4 | VLM 冒烟（图片理解） | nim_smoke vlm 或 curl vision endpoint | `nim-vlm-smoke.txt` |
| N5 | ASR + OCR 冒烟 | 各组件 health + 一次真实转写/识别 | `riva-asr-ocr-smoke.txt` |
| N6 | NeMo Guardrails 启用 + 注入负向回归 | `deploy/nim/docker-compose.yml` 取消注释 + `pytest tests/test_guardrails.py` | `guardrails-nemo-smoke.txt` |
| N7 | **黄金链全栈跑通**：models.yaml 全切 NVIDIA | `python scripts/run_demo.py --settings config/settings.dgx-spark-p0.yaml --models config/models.nvidia-fullstack.yaml` | `03-demo-nvidia-fullstack.log` |
| N8 | **行为等价回归**：local vs NVIDIA，引擎价格 sha256 比对 | 跑两次黄金链，比 `unit_price` sha256 | `behavior-parity-local-vs-nvidia.json` |

---

## 4. 行为等价验收（最关键的证据）

```
同一黄金样例 (data/eval_set.json 6 cases)
  ├── local runtime (LMStudio/local embeddings)
  │     └── 引擎价格 sha256 = X
  └── nvidia-fullstack (NIM/Riva/Retriever)
        └── 引擎价格 sha256 = X  ← 必须相等

LLM 生成字段（RFQ 抽取/回复草稿）允许统计差异，写进报告。
引擎价格（unit_price/final_price）必须 byte-identical。
```

输出 `docs/evidence/nvidia/behavior-parity-local-vs-nvidia.json`：

```json
{
  "sample_id": "S1-PASS",
  "engine_price_sha256": {
    "local": "abc123...",
    "nvidia_fullstack": "abc123...",
    "parity": true
  },
  "llm_field_accuracy": {
    "local": 0.92,
    "nvidia_fullstack": 0.95,
    "note": "LLM 字段允许统计差异"
  }
}
```

---

## 5. 证据落盘

```
docs/evidence/nvidia/
  00-nvidia-stack-selfcheck.txt    # nvidia-smi + 各组件端口确认
  nim-llm-smoke.txt                # NIM LLM /v1/models + chat
  nim-embed-smoke.txt              # NEM Embedding 向量冒烟
  nim-vlm-smoke.txt                # VLM 图片理解冒烟
  riva-asr-ocr-smoke.txt           # Riva ASR/OCR 冒烟
  guardrails-nemo-smoke.txt        # NeMo Guardrails 注入拦截
  models-yaml-fullstack-diff.md    # local → nvidia 全栈切换前后对照
  03-demo-nvidia-fullstack.log     # 黄金链全 NVIDIA 后端实跑日志
  behavior-parity-local-vs-nvidia.json  # 行为等价证明（价格 sha256 一致）
```

---

## 6. 降级策略

| 风险 | 降级 |
|------|------|
| 某 NVIDIA 组件端口对不上 | 该角色保持 local，报告里标「该角色保留 local，其余 NVIDIA」 |
| ASR Parakeet 不支持节点 GPU compute | 用 Riva ASR 或 GPU 加速 FunASR（不冒充 Parakeet） |
| NeMo Guardrails 镜像拉不起 | 保留 builtin，标「Guardrails builtin 兜底，NeMo 配置已就绪」 |
| 行为等价 sha256 不一致 | **这是 blocker**——排查引擎调用路径，不得宣称平替成功 |

---

## 7. 提交门禁（NVIDIA 全栈面）

- [ ] 6 个角色中 **至少 4 个**切到 NVIDIA 组件并有冒烟证据
- [ ] 黄金链在全 NVIDIA 后端下跑通（或标明哪几个角色保留 local）
- [ ] 行为等价 JSON 落盘：引擎价格 sha256 local == nvidia
- [ ] `models.yaml` 切换前后 diff 入证
- [ ] 答辩口径无夸大：没跑通的角色诚实标注
