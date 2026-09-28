# NVIDIA 全栈框架 · Union Export Agent LiveKernel

> **已取代（2026-09-20）**：唯一主 PRD 为 `docs/PRD-MASTER-UEA-DELIVERY.md` **v2.0**（含节点实测模型栈）。本文保留仅供溯源，冲突处以后者为准。

> 版本：v2.0-nemotron-fullstack | 日期：2026-09-20 | 状态：地基已建，P0 交付待审核

---

## 一、框架定位（一句话）

**把制造业询盘邮件端到端变成可审计、可验证、可自动决策的商业对象**——L3 条件性自动驾驶，NVIDIA 全栈推理，Timo 引擎裁决数字。

---

## 二、整体架构（五层）

```
┌─────────────────────────────────────────────────────────────┐
│  L5 交付层  │ Workbench UI :8888 │ Gmail工作台 │ V12仪表板   │
├─────────────────────────────────────────────────────────────┤
│  L4 Agent层 │ CATController(黄金链7步) │ SkillDispatcher     │
│              │ FleetCoordinator v4 │ CEO/Reid双LLM决策      │
├─────────────────────────────────────────────────────────────┤
│  L3 Skill层 │ 33 Skills (NemoClaw混合架构)                  │
│              │ parse-rfq → check-dfm → calc-quote → verify   │
│              │ → write-reply → customer-flywheel → ...       │
├─────────────────────────────────────────────────────────────┤
│  L2 推理层  │ Model Router (6角色×3后端, A/B路由)            │
│              │ FAST: Nano-4B │ REASON: Lightning-30B-A3B    │
│              │ OMNI: Nano-Omni │ EMBED: nv-embedqa          │
│              │ DETERMINISTIC: Timo引擎 (铁律①锁定)           │
├─────────────────────────────────────────────────────────────┤
│  L1 基础层  │ GB10/CUDA13 │ Triton(已修) │ FastAPI :8900    │
│              │ SQLite×3 │ AgentCache LRU │ OTEL可观测        │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、黄金链（端到端数据流）

```
Gmail IMAP → MailPuller(30s轮询) → MailOrchestrator
  → CATController(7步状态机)
    ① Intake        — 邮件/附件/语音 intake
    ② RFQ提取       — parse-rfq skill → 结构化询盘
    ③ DFM冲突       — check-dfm skill → 可制造性检查
    ④ Timo报价      — calc-quote skill → 确定性价格 (铁律①)
    ⑤ 五步验证      — 辟谣/牟定/援引/推演/止疑
    ⑥ FleetCoordinator — 3专家(材料/DFM/价格)+Loop+Critic
    ⑦ CEO/Reid决策   — PASS自动批准 / HITL人工 / BLOCKED归档
  → CRM+Memory → SHA-256审计链
  → Workbench UI 展示 + Gmail回复草稿(draft_only)
```

**自动化等级**：L3 条件性自动驾驶（PASS 路径全自动，HITL/BLOCKED 通知人工兜底）

---

## 四、Nemotron 全栈推理矩阵

| 角色 | 模型 | 能效档 | 端点 | 职责 | N0状态 |
|------|------|--------|------|------|--------|
| **FAST** | Nemotron-3-Nano-4B | 边缘4B | :8002 | 意图分类/路由/快速抽取 | ⬜ 待部署 |
| **REASON** | Lightning-30B-A3B | MoE 30B/3B激活 | :8000 | ReAct规划/草稿/摘要 | ⬜ 待部署 |
| **OMNI** | Nemotron-3-Nano-Omni | 多模态三合一 | :8020 | VLM+ASR+OCR | ⬜ 待部署 |
| **EMBED** | nv-embedqa-e5-v5 | NIM官方 | :8011 | RAG向量化 | ⬜ 待部署 |
| **DETERMINISTIC** | Timo v12引擎 | 确定性 | :7862 | 报价/DFM/毛利 | 🔒 永锁定 |
| **N0兜底** | Qwen3-0.6B | GPU bf16 | :8888 | 冒烟/链路验证 | ✅ 已部署(62.6 tok/s) |

**能效梯度**：FAST(4B省延迟) → REASON(MoE省显存) → OMNI(三合一省服务数)
**N0门禁**：节点无NIM/无Nemotron权重/无docker → 进程级回退(:8888)

---

## 五、Skill 体系（33 Skill · NemoClaw 混合架构）

### 核心链 Skill（黄金链 7 步）
| Skill | 职责 | 铁律 |
|-------|------|------|
| parse-rfq | 询盘邮件→结构化RFQ | ④ RAG仅引用 |
| check-dfm | DFM可制造性冲突检查 | ① LLM不定价 |
| calc-quote | Timo确定性报价 | ① LLM不定价(locked) |
| verify-gate | 五步验证(辟牟援推止) | ② 状态机不可绕 |
| write-reply | 回复草稿(draft_only) | ⑥ Runtime≠业务 |

### 专家 Skill（FleetCoordinator v4）
| Skill | 职责 |
|-------|------|
| material-expert | 材料选择(4材料×3形状) |
| dfm-expert | DFM冲突专家 |
| price-expert | 价格合理性专家 |
| fleet-coordinator | 3专家+Loop+Critic |

### 飞轮 Skill（v6.2 双飞轮）
| Skill | 职责 |
|-------|------|
| customer-flywheel | 客户跟进飞轮(越报越准) |
| customer-health | 客户健康度 |
| quote-calibration | 报价校准(分级修正提案) |
| retention-alert | 流失预警 |

### 供应商 Skill（v2.3.0）
| Skill | 职责 |
|-------|------|
| supplier-match | 供应商匹配(标签打分TopN) |
| extract-specs | 规格提取 |
| freight-customs | 运费关税 |

### 多模态/工具 Skill
| Skill | 职责 |
|-------|------|
| rfq-extraction | RFQ抽取(含图纸) |
| step-analysis | STEP文件分析 |
| render-thumbnail | 3D缩略图渲染 |
| batch-quote | 批量报价(BOM 410/410) |
| quote-correction | 报价矫正(L2召回→PriceCorrector) |
| rag-ingest | RAG分层摄取 |

---

## 六、6 条工程铁律（全代码化）

| # | 铁律 | 实现机制 | 验证 |
|---|------|----------|------|
| ① | LLM不定价 | calc-quote locked, 价格100%来自Timo | test_price_sha256_regression |
| ② | 状态机不可绕 | RFQStateMachine IllegalTransition | test_state_machine_blocks_illegal |
| ③ | Context唯一 | context_id RFQ-前缀+唯一生成 | test_context_ids_unique |
| ④ | RAG仅引用 | rag_layers 只引用不生成 | test_rag_layers |
| ⑤ | 多模态冲突升级 | voice+email冲突→HITL | test_m1_conflict_surfaces |
| ⑥ | Runtime≠业务 | external_send=draft_only | test_egress_gate |

---

## 七、部署架构

### 节点（spark-51 / GB10）
```
常驻:
  Timo引擎 :7862 (确定性报价)
  Nano-4B  :8002 (FAST, 待部署)
  nv-embedqa :8011 (EMBED, 待部署)
  Workbench :8888 (UI, 公网:8051)
按需:
  Lightning-30B :8000 (REASON, MoE按需加载)
  Nano-Omni :8020 (VLM+ASR+OCR, 按需加载)
回退:
  Qwen3-0.6B :8888 (N0兜底, 已部署)
  FunASR :8866/:8089 (ASR回退)
公网跳板:
  203.0.113.10 :8051→8888 :9051→9000(Jupyter)
```

### 容器编排（deploy/nim/docker-compose.yml）
- nim-nano-4b → :8002 (FAST)
- nim-lightning → :8000 (REASON, MoE)
- nim-omni → :8020 (多模态三合一)
- nim-embed → :8011 (RAG向量化)
- 注：节点无docker权限 → 进程级替代(llama.cpp/vLLM)

### k8s（deploy/k8s.yaml + hpa.yaml）
- replicas:2, HPA三条告警(HighHITLRate/EngineCircuitOpen/QuoteLatencyHigh)
- GPU设备预留, 凭据走${ENV}引用

---

## 八、测试与评估

### 测试矩阵（701 passed）
| 维度 | 数量 | 状态 |
|------|------|------|
| 业务回归 | 515~517 | ✅ 97.9% |
| Skill/Dispatcher | 93 | ✅ |
| 飞轮 | 19 | ✅ |
| 部署清单 | 6 | ✅ |
| 黄金场景S1-S5+M1 | 6/6 | ✅ 经SkillDispatcher |
| Nemotron分层调度 | 10 | ✅ 新增 |
| 价格sha256回归 | 待跑 | ⬜ 铁律①验证 |

### 评估框架（NCP-AAI）
- P0: LLM提议/引擎裁决 ✅
- P1: 容错+降级 ✅
- P2: 评估指标 ✅
- P3: 平台化 ✅

---

## 九、给谁用 · 怎么用 · 解决什么

### 给谁用
| 用户角色 | 痛点 | 用法 |
|----------|------|------|
| **外贸业务员** | 询盘回复慢(2h+)、报价不专业 | 邮箱接单→自动报价→审核→一键回复 |
| **工厂报价工程师** | 重复报价、DFM冲突发现晚 | Workbench查看自动报价+DFM标记+人工修正 |
| **外贸制造业企业** | 询盘响应速度=竞争力 | 7×24自动接单报价，L3自动驾驶释放人力 |

### 怎么用
```
1. 邮箱配置 → Gmail IMAP 挂接 (MailPuller 30s轮询)
2. 询盘到达 → 自动进入黄金链 (7步状态机)
3. Workbench :8888 → 查看处理进度/报价/DFM/验证
4. PASS → 自动批准+回复草稿 / HITL → 人工审核 / BLOCKED → 归档
5. 客户飞轮 → 越报越准 (历史报价+客户健康+校准)
```

### 如何用户好
- **速度**：询盘响应 2h → 3min（40×加速）
- **准确性**：确定性引擎报价，无LLM幻觉（铁律①）
- **可审计**：SHA-256审计链，每个报价可溯源
- **多模态**：邮件+图纸+语音统一管道（Omni三合一）
- **越用越准**：双飞轮（客户跟进+报价数据飞轮）

### 解决了什么行业问题
| 行业问题 | 本项目解法 |
|----------|-----------|
| 外贸询盘响应慢（小时级） | L3自动驾驶 → 分钟级 |
| 报价不一致（人工/LLM幻觉） | Timo确定性引擎 + 铁律① |
| 多模态输入处理难（邮件+图纸+语音） | Omni三合一统一管道 |
| DFM冲突发现晚（生产时才暴露） | check-dfm skill 前置检查 |
| 客户流失（无跟进） | customer-flywheel 客户健康+流失预警 |
| 报价无沉淀（每次从零开始） | quote-calibration 历史校准飞轮 |

---

## 十、升级路径（N0 → N3）

| 档 | 条件 | FAST | REASON | VISION/ASR | EMBED | 口播 |
|----|------|------|--------|------------|-------|------|
| **N0** | 仅smi | Qwen3-0.6B兜底 | 0.6B | mock | hash | 链路通 |
| **N1** | 进程GPU | Nano-4B | 4B | mock | Qwen3-Embed | 单模态 |
| **N2** | +Omni | Nano-4B | 4B | Omni | nv-embedqa | 多模态 |
| **N3** | +NIM | Nano-4B | Lightning-30B | Omni | nv-embedqa | 全栈 |

**当前位置**：N0（地基已建，Nemotron配置就绪，待拉权重+起服务）