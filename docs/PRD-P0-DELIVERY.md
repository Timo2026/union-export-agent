# 可行 PRD · Nemotron 全栈交付（P0 → P3）

> **已取代（2026-09-20）**：唯一主 PRD 为 `docs/PRD-MASTER-UEA-DELIVERY.md` **v2.0**（含节点实测模型栈）。本文保留仅供溯源，冲突处以后者为准。

> 版本：v1.0 | 日期：2026-09-20 | 状态：**P0 已交付，待审核**

---

## 总览

| 阶段 | 目标 | 前置 | 工期 | 状态 |
|------|------|------|------|------|
| **P0** | Nemotron 全栈地基 | 无 | 0.5天 | ✅ 已交付 |
| **P1** | Nemotron 权重部署 + 进程服务 | P0 + 节点带宽 | 1-2天 | ⬜ 待执行 |
| **P2** | NIM 容器 + Omni 多模态 + 全栈验证 | P1 + docker权限 | 2-3天 | ⬜ 待执行 |
| **P3** | 生产化（外发/队列/可观测/跨平台） | P2 | 1-2周 | ⬜ 待执行 |

---

## P0：Nemotron 全栈地基（✅ 已交付）

### 目标
在不部署 Nemotron 权重的前提下，把"切换到 Nemotron 全家族"所需的所有配置/编排/路由/测试地基建好，使后续 P1 只需"拉权重+起服务+改 endpoint"即可生效。

### 交付物（6 文件）
| # | 文件 | 内容 | 状态 |
|---|------|------|------|
| 1 | `config/models.nvidia-fullstack.yaml` | Nemotron全家族配置 + N0自检结论 + 进程级回退 | ✅ |
| 2 | `config/settings.dgx-spark-nvidia.yaml` | Nemotron默认(NIM线+进程级回退) | ✅ |
| 3 | `deploy/nim/docker-compose.yml` | 三服务编排(Nano-4B/Lightning/Omni+Embed) | ✅ |
| 4 | `services/model_router.py` | _NIM_DEFAULTS更新为Nemotron | ✅ |
| 5 | `tests/test_model_router_layered.py` | FAST/REASON分层调度验证(10断言) | ✅ |
| 6 | `tests/test_price_sha256_regression.py` | 铁律①行为等价回归(价格sha256比对) | ✅ |

### P0 验收清单
- [x] `models.nvidia-fullstack.yaml` YAML 语法通过
- [x] `settings.dgx-spark-nvidia.yaml` 含 Nemotron NIM线 + 进程级回退
- [x] `docker-compose.yml` 含 4 服务(nano-4b/lightning/omni/embed)
- [x] `model_router.py` _NIM_DEFAULTS = Nemotron全家族
- [x] 节点 N0 自检完成(GPU/NIM/权重/docker/已部署服务)
- [x] 节点 GPU 推理已通(Qwen3-0.6B bf16 62.6 tok/s)
- [x] 节点公网 API 已部署(:8888→:8051, Bearer鉴权)
- [x] `pytest tests/test_model_router_layered.py` 全绿（**10/10 PASSED**）
- [x] `pytest tests/test_price_sha256_regression.py` 全绿（**13/13 PASSED**）

### P0 已知限制（诚实标注）
- 节点无 docker 权限 → NIM 容器线节点走不通，仅编排就绪
- 节点无 Nemotron 权重 → 配置中 endpoint 为占位，实际走 :8888 兜底
- Timo 引擎 :7862 节点未在线 → 价格回归测试需引擎环境

---

## P1：Nemotron 权重部署 + 进程服务

### 目标
在节点上拉取 Nemotron 权重，起进程级推理服务(llama.cpp/vLLM)，切换 model_router backend=nvidia，使黄金链跑在 Nemotron 上。

### 前置条件
- P0 地基已建 ✅
- 节点带宽可达（清华镜像/HF镜像）
- 磁盘空间充足（1.5TB可用 ✅）

### 执行项
| # | 任务 | 命令/产出 | 验收 |
|---|------|-----------|------|
| 1 | 拉取 Nemotron-3-Nano-4B 权重 | 节点内 `huggingface-cli download` (清华镜像) | ~/inference/models/Nemotron-3-Nano-4B/ 存在 |
| 2 | 起 Nano-4B 进程服务 | `python -m vllm.entrypoints.openai.api_server --model Nemotron-3-Nano-4B --port 8002` | curl :8002/v1/models 返回 model id |
| 3 | 拉取 Lightning-30B-A3B GGUF | 节点内下载 GGUF 量化版(Q4/Q5, ~15GB) | 文件存在 |
| 4 | 起 Lightning 进程服务 | `llama-server --model lightning-30b-a3b.Q5_K_M.gguf --port 8000 --n-gpu-layers 99` | curl :8000/v1/models 返回 |
| 5 | 切 backend=nvidia | `settings.yaml → model_router.backend: nvidia` | model_router.status() 全 online |
| 6 | 跑黄金链回归 | `pytest tests/test_golden_regression.py` | S1-S5+M1 6/6 PASS |
| 7 | 跑分层调度验证 | `pytest tests/test_model_router_layered.py` | 10/10 PASS |
| 8 | 跑价格sha256回归 | `pytest tests/test_price_sha256_regression.py` | 铁律①验证 PASS |

### 风险与回退
| 风险 | 概率 | 回退 |
|------|------|------|
| Nemotron 权重下载慢/失败 | 中 | 用 Qwen3-4B 顶替，标记 evidence 回退 |
| vLLM 不支持 aarch64+GB10 | 中 | 用 llama.cpp/transformers 进程级 |
| Lightning 30B 显存不足 | 低 | MoE 只激活3B，统一内存121GB足够；若不足降级 Nano-4B |
| 推理速度不达标 | 低 | MoE 延迟接近4B，GB10 统一内存带宽充足 |

### P1 验收标准
- Nemotron-3-Nano-4B 服务 :8002 在线，`/v1/models` 返回 model id
- Lightning-30B-A3B 服务 :8000 在线
- `model_router.backend = nvidia`，FAST/REASON 路由到 Nemotron endpoint
- 黄金链 S1-S5+M1 6/6 PASS（经 Nemotron 推理）
- 价格 sha256 回归 PASS（铁律①：换 LLM 后端，价格不变）

---

## P2：NIM 容器 + Omni 多模态 + 全栈验证

### 目标
部署 NIM 容器（需 docker 权限环境），拉起 Omni 多模态服务，完成 Nemotron 全栈验证，达到 N3 档。

### 前置条件
- P1 完成 ✅
- docker 权限（评委 DGX Spark 标准环境，或申请 Developer 加入 docker 组）
- NGC_API_KEY

### 执行项
| # | 任务 | 产出 | 验收 |
|---|------|------|------|
| 1 | 拉起 NIM 容器编排 | `docker compose -f deploy/nim/docker-compose.yml up -d` | 4 容器 healthy |
| 2 | 拉取 Nemotron-3-Nano-Omni 权重 | 节点内下载 | ~/inference/models/Nemotron-3-Nano-Omni/ |
| 3 | 起 Omni 服务 | vLLM 进程级或 NIM 容器 | curl :8020/v1/models 返回 |
| 4 | Omni 多模态验证 | 图纸VLM + 语音ASR + OCR 三合一测试 | 三模态全部响应 |
| 5 | 全栈端到端 | 邮件+图纸+语音 → 黄金链 → 报价 | E2E PASS |
| 6 | N3 档验证 | model_router 全 online + 全模态 | N3 口播达标 |

### P2 验收标准
- 4 NIM 容器 healthy（或 4 进程服务在线）
- Omni :8020 响应 VLM+ASR+OCR 三模态
- 端到端：邮件+图纸+语音 → 报价，全链 PASS
- model_router 6 角色全 online，N3 档达标

---

## P3：生产化

### 目标
解决生产化 6 大缺口，达到可上线标准。

### 执行项（对齐 PROJECT-SUMMARY §5.2-5.3）
| # | 任务 | 产出 | 优先级 |
|---|------|------|--------|
| 1 | 真实外发网关 | `services/notify/gateway.py` + 凭据入库 + 灰度开关 | P0-1 |
| 2 | 任务队列 | `services/tasks/{worker,tasks}.py` Celery+Redis + 幂等键 | P0-2 |
| 3 | 配置热加载 | `services/config_store.py` mtime轮询+订阅发布 | P0-3 |
| 4 | DB迁移+备份 | Alembic初始迁移 + beat日备份 | P0-4 |
| 5 | 供应商接入主干 | `services/supplier_api.py` + FULFILLMENT区段 | P1-1 |
| 6 | 多币种+多语种 | `services/fx.py` + `services/i18n.py` | P1-2 |
| 7 | Prometheus+Grafana | `/metrics`端点 + HPA三条告警 | P1-3 |
| 8 | Vault/KMS凭据 | credentials.py vault后端 | P1-4 |
| 9 | Linux/macOS脚本 | `start_novastudio.sh` + systemd | P2-3 |
| 10 | tools/拆解 | .gitignore → 独立仓库 + LFS | P2-4 |

### P3 验收标准
- 外发网关：报价可送达客户（灰度开关控制）
- 任务队列：多副本无重复处理（幂等键）
- 配置热加载：改 policy.yaml 20s 生效
- DB迁移：Alembic schema 版本化
- Prometheus：/metrics 可 scrape，HPA 告警联动
- 跨平台：Linux/macOS 一键启动

---

## 铁律保障（全阶段不变）

| 铁律 | P0 | P1 | P2 | P3 |
|------|----|----|----|----|
| ① LLM不定价 | 🔒 配置locked | 🔒 sha256回归 | 🔒 全栈验证 | 🔒 外发draft_only |
| ② 状态机不可绕 | ✅ | ✅ | ✅ | ✅ |
| ③ Context唯一 | ✅ | ✅ | ✅ | ✅ |
| ④ RAG仅引用 | ✅ | ✅ | ✅ | ✅ |
| ⑤ 多模态冲突升级 | ✅ | ✅ | Omni验证 | ✅ |
| ⑥ Runtime≠业务 | ✅ | ✅ | ✅ | ✅ |

---

## 决策点（需用户确认）

1. **P1 权重来源**：Nemotron 权重从 HF/清华镜像/NGC 下载？需确认可访问性。
2. **P1 服务方案**：vLLM vs llama.cpp vs transformers？aarch64+GB10 兼容性需验证。
3. **P2 docker 权限**：节点 Developer 不在 docker 组，是否申请加入？或全程走进程级？
4. **P3 优先级**：外发网关(P0-1) vs 任务队列(P0-2) 哪个先？外发是业务闭环，队列是并发安全。
5. **v6.2 飞轮迁移**：CAT黄金链是否迁移到 v6.2 FeedbackLoop？还是保持 v6.1 CustomerFlywheel？

---

## 一句话

> **P0 地基已建（配置+编排+路由+测试），P1 拉权重起服务即可切 Nemotron，P2 上 Omni 多模态，P3 生产化——每阶段都有明确验收标准和回退路径，铁律①全程锁定。**