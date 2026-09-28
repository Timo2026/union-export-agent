# TECH_STACK.md — 技术栈（NVIDIA 全栈 + StepFun 如实口径）

## 一、NVIDIA 栈（全部节点实跑，见 REAL_STATE.md）

| 层 | 组件 | 版本实测 |
|---|---|---|
| 硬件 | DGX Spark GB10（Grace-Blackwell · aarch64 · 121GiB 统一内存） | 驱动 580.82.09 |
| 系统 | CUDA Toolkit / cuDNN / NCCL / Triton / CUTLASS DSL | CUDA 13.0 · cuDNN 9.19 · NCCL 2.28.9 · Triton 3.6 |
| 推理 | PyTorch + vLLM（3 实例） | 2.11.0+cu130 · vLLM 0.20.0 |
| 模型 | Nemotron-3-Nano-Omni-30B-A3B-Reasoning-**NVFP4** · Embed-1B-NVFP4 | Blackwell 原生 FP4（GGUF 已否决：无 FP4 tensor core 路径） |
| 护栏 | NeMo Guardrails（三段：input/tool/output） | builtin 实跑 / nemo_soft 可切 |
| Agent | NemoClaw（SKILL.md+tool.py 契约）· OpenShell 4 策略 · nemo-agents-spec-v1 | 39 skills |
| CAD | OpenCascade/cadquery 2.8.0 + OCP（aarch64 原生） | STEP B-rep 实跑（V=199,098.43mm³ 验证） |

## 二、推理优化实测
- NVFP4：30B 模型仅占 21GB 磁盘 / 66GB 显存——统一内存下与全套服务共存
- prefix-caching 开启；`--reasoning-parser nemotron_v3`；`--tool-call-parser qwen3_coder`（工具调用实测可用）
- 多实例聚合 **≈450 tokens/s**；8 并发 Qwen3 聚合 **340.2 tok/s**（CPU 单流参照的 26×，见 BENCHMARK-GPU.md）
- KV cache 经验：Omni(0.55 util, 实占 66GB) 与 30B 文本档同驻会 crash-loop（22 次重启教训）——单 any-to-any 统一端点比分层稳

## 三、StepFun 阶跃星辰（如实口径）
- **定位：fallback 回落位**（stepfun-plan / step-5-preview）。气隙（data-stays-local）运行下**不会主动出网**；本地 NVFP4 Nemotron 是唯一主力。
- 接线完成：`model_router backend=stepfun`（Step-1-8k / Step-1V-8k，OpenAI 兼容）；`STEPFUN_API_KEY` 未配置时**诚实降级**（online=False，不伪造调用）。
- 铁律①保证：DETERMINISTIC 永锁 Timo——**换任何 LLM 后端（含 StepFun）报价 byte-identical**。

## 四、非 NVIDIA 组件（诚实清单）
- Python 3.11（核心链标准库优先：urllib/subprocess/json/sqlite3/hashlib + PyYAML）
- FastAPI :8888 · uvicorn · React/Vite 前端（webui-dist v7.1.0） · three.js（图纸 3D + 知识库点云）
- SQLite（CRM/飞轮/沙箱） · JSONL 审计链
