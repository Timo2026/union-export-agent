# 交付包 07 · NVIDIA 全栈介绍 + DGX 价值 + 模型选型 + 十日开发路径（含坑清单）

## 一、NVIDIA 全栈介绍（每项实测，可直接给评委）

**五级实跑栈**（本会话 3 轮 SSH 实测）：
1. **硬件**：DGX Spark GB10（Grace Blackwell · aarch64 · 121GiB 统一内存 · compute cap 12.1 · 驱动 580.82.09）
2. **系统栈**：CUDA 13.0 + PyTorch 2.11.0+cu130 + Triton 3.6 + cuDNN 9.19 + NCCL 2.28.9 + CUTLASS DSL 4.7（28 个 nvidia-* 运行库）
3. **模型**：Nemotron-3-Nano-Omni-30B-A3B-Reasoning-**NVFP4**（21GB · Blackwell 原生 FP4）+ Nemotron-3-Embed-1B-NVFP4
4. **推理**：vLLM 0.20 ×3 实例（Omni:8002 / Embed:8011 / Qwen3-0.6B:8902 fallback）
5. **Agent 框架**：NemoClaw（38 skills）+ NeMo Guardrails（三段护栏，nemo_soft 可切）+ nemo-agents-spec-v1 契约 + NCP-AAI 协议对齐

诚实分级：🟢 实跑（上述全部）🟡 配置可切（nemo_soft）🔴 清单未部署（NIM/TensorRT/Triton Server——本地 vLLM 已覆盖其角色）

## 二、DGX Spark 对本项目的帮助（三件不可替代）

1. **统一内存 121GiB = 模型矩阵的天花板**：Omni-30B 实占 66.2GB 显存 + Embed 1.8GB + Qwen 6.7GB，仍余 23GB 内存跑全套服务——普通工作站做不到 any-to-any 模型常驻
2. **aarch64 原生 CAD 推理**：cadquery 2.8.0+OCP 在 GB10 实跑 STEP B-rep（实测 100×100×260mm 体积 199,098.43mm³ 误差 0）——报价基于真几何而非估算
3. **本地全栈闭环**：邮件→解析→报价→附件全程不出机器（铁律①的数据层意义），制造业客户的核心合规诉求

## 三、模型怎么选型的 & 为什么（实测推理链）

| 决策 | 为什么（实测证据） |
|---|---|
| **Omni-30B 统一 LLM/VLM/OCR/ASR** | 初版想三驻分层（Nano-4B :8002 + 30B :8000 + Omni :8020 + ASR :8021）——实测 **30B 与 Omni 同驻 KV cache 分配 crash-loop（watchdog 22 次重启）**；Omni any-to-any 一个模型覆盖四角色，262K ctx + tool-calls 实测可用（600 token 预算下正确返回 calc_quote 调用） |
| **NVFP4 而非 BF16/GGUF** | Blackwell 原生 FP4 tensor core 路径；GGUF 已否决（无 FP4 加速）；NVFP4 让 30B 只占 21GB 磁盘/66GB 显存 |
| **Embed-1B 独立档** | 检索与生成分离；非对称双塔需 query:/passage: 前缀（实测不加前缀相关文档排倒数） |
| **Qwen3-0.6B fallback** | Omni 离线时低质真实续写顶班，不 MOCK |
| **Timo v12 确定性引擎** | 铁律①：LLM 提议、引擎裁决；报价 byte-identical 可复现（实测两次 ¥222.65 完全一致） |

## 四、十日开发路径与坑（基于 CHANGELOG + 本会话 12 轮实测）

| 日 | 里程碑 | 坑（实测编号） |
|---|---|---|
| D1-2 | 冻结 PRD + 黄金链骨架 | 4 份 PRD 共存不收敛 → 拍板 FINAL |
| D3 | L3 邮件自动驾驶 | claim race：后台 loop 抢先 FIFO → 租约 mark_state |
| D4 | GB10 节点对齐 | pypi 受阻→清华源 · 无 sudo→全 pip · ToS 门禁 · SSH banner 抖动 |
| D5 | 飞轮+RAG 分层 | 中文注入漏判（英文护栏打不住「请忽略之前的指令」）|
| D6 | 全栈回归 | 34 failed 清理：测试口径过时（旧 UI/旧拓扑断言）|
| D7 | 铁律加固 | **iron-rule-1 跨 dispatch 误报**（T3 输入指纹根治）· **AgentCache 命中丢 scratch**（T1 回写根治）|
| D8 | 演示加固 | **RAG P95 15s**（锁内序列化 73MB → 锁外，392ms）· **护栏连字符变体绕过**（defect-free 漏拦→词级正则）|
| D9 | 尽调增强 | reid 引擎桥 + Omni 协议执行；工具调用 600 token 预算才吐 tool_calls |
| D10 | 知识库点云 | three.js 手写零新依赖；jsdom 无 WebGL→try/catch 降级 |
| 赛前 | 交付冲刺 | 敏感文档曾入 RAG（已删+黑名单）· frp 回环假象误判"8051 断"（外部 200）· flywheel 统计键名脱节归零 |

**累计坑位 20+，全部有测试或配置锁定。**

> **展开版见 `交付包/09-十日开发稿-TEN-DAYS.md`**（入仓实体 `docs/TEN-DAYS.md`）：D1–D10 逐日详稿 + K01–K33 坑位全清单（现象/根因/修法/锁定方式四列）+ 三个招牌坑的演讲话术 + 数字口径表与三处勘误 + 五条纪律。
