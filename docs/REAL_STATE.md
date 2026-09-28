# REAL_STATE.md — 节点实测真实状态（2026-09-27 SSH 采集）

> 全部数字来自本会话 12+ 轮 SSH 实测探针，非纸面参数。脱敏口径：公网 IP → `NODE_PUBLIC_HOST`。

## 一、设备
| 项 | 实测 |
|---|---|
| 主机 | spark-388d · aarch64 · 内核 6.11.0-1014-nvidia · Ubuntu 24.04 |
| GPU | **NVIDIA GB10**（Grace-Blackwell）· 驱动 580.82.09 · CUDA 13.0 · compute cap 12.1 |
| 内存 | 121 GiB 统一内存（模型常驻后可用 ~23GB） |
| 磁盘 | 3.7T NVMe（用 60%） |
| 运行时 | up 7 天+ · 负载 <0.6 · GPU 温度 37-44°C · 满载时利用率 ≈96% / 显存 ≈74GB |

## 二、模型服务（全部 vLLM 0.20.0 实跑）
| 端口 | 模型 | 角色 | 实测 |
|---|---|---|---|
| :8002 | Nemotron-3-Nano-Omni-30B-A3B-Reasoning-**NVFP4**（21GB） | LLM/VLM/OCR/ASR 统一端点 | 262K ctx · tool-calls 可用（600 tok 预算） · 占显存 66.2GB · 多实例聚合 ≈450 tokens/s |
| :8011 | Nemotron-3-Embed-1B-NVFP4 | RAG 检索（query:/passage: 双塔前缀） | 2.2GB |
| :8902 | Qwen3-0.6B | Omni 离线 fallback（真实续写顶班，不 MOCK） | 6.7GB · 8 并发聚合 340.2 tok/s |
| :7862 | Timo CNC-AI-Brain v12（确定性引擎，CPU） | 报价/DFM/裁决（铁律①） | 报价 24ms/次 · byte-identical 复现 |

## 三、业务数据（演示口径）
| 指标 | 实测 |
|---|---|
| 邮件 | **130 封**真实邮件自动拉取（30s 轮询，IMAP） |
| 上下文 | **contexts 5,266**（持续增长） |
| RAG 知识库 | **475 篇**已向量化 |
| 客户飞轮 | **66 客户 / 3,530 报价** |
| 审计 | quote_history 1,355 条向量（回填完成） |
| 测试 | 节点 `pytest -m "not node_env"` **892 passed / 0 failed / 6 skipped**；本地全量 1602 |

## 四、端口总表（实测监听）
8888 livekernel API · 7862 Timo 引擎 · 8002 Omni · 8011 Embed · 8902 Qwen fallback · 8901 openai shim · 9000 JupyterLab · 18789 OpenClaw gateway · 22 SSH（frp 对外 6051/8051）

## 五、多模态样例（真实闭环）
6061 铝合金卡片阅读器外壳：图纸+语音输入 → Omni 抽规格（宽37×长87.70×高114.36mm、Ø2.90×2/Ø2.05×3/M2.5-6H、喷砂+阳极氧化）→ step-factory 生成 STEP（350 实体）→ dfam-check 壁厚校核 → reid-os 报价 → **端到端 30-90s，GPU ≈96%，CPU 基本闲置**。

## 六、OpenClaw 技能盘点
平台侧 47 skills（11 完全可用）+ livekernel 39 业务 skill 目录；NVIDIA 栈技能（nemotron-customize / nemo-retriever / jetson-* 等）与 union-export 桥接技能（cnc-quote-system / email-quote / dfam-check）并存。
