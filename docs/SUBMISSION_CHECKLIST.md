# SUBMISSION_CHECKLIST.md — 黑客松交付清单 / 评分映射 / 时间线

## A. 必交项
| # | 交付项 | 位置 | 状态 |
|---|---|---|---|
| 1 | GitHub 开源仓库 URL | 本包 push 后 | ✅ 686 文件 / MIT / 脱敏两轮清零 |
| 2 | B 站演示视频 URL | 按 docs/DEMO_SCRIPT.md 分镜拍摄 | ⏳ 线下 |
| 3 | 十日谈征文（CSDN/知乎） | docs/十日谈.md（成稿可直接发） | ✅ 成稿 |
| 4 | 团队合影 | 线下 | ⏳ |

## B. README 评分硬指标映射
| 官方要求 | 落点 | 状态 |
|---|---|---|
| 项目说明 ≥500 字 | README §一定位 + §全栈融合 + §真实闭环 | ✅ |
| 部署说明 | docs/REPRODUCTION.md + docs/deploy.ipynb | ✅ |
| 技术栈说明 | README §NVIDIA 全栈表 + docs/TECH_STACK.md（含 StepFun 如实口径） | ✅ |
| Skill Markdown | skills/ 39 目录 SKILL.md（NVIDIA AgentSkills 标准） | ✅ |

## C. 评分维度对应证据
| 维度 | 证据 |
|---|---|
| 实用性/落地 | 130 封真实邮件 · contexts 5,266 · 66 客户 3,530 报价（REAL_STATE.md） |
| 智能体深度 | 39 skills · OpenShell 4 策略 · iron-rule sha256 锁 · 飞轮分层 RAG · 负向触发矩阵 |
| 完整性 | 892/0/6（not node_env）· 全栈前后端 · 69 端点 5 路由 |
| 平台适配 | GB10/CUDA13/Omni-NVFP4/vLLM 实跑 · 450 tok/s · 30-90s 闭环 · BENCHMARK-GPU.md |
| 演示效果 | DEMO_SCRIPT.md（byte-identical 开场 → 断网重跑 → 负向触发） |
| 征文 | 十日谈.md（33 坑全复盘） |

## D. 演示前 30 分钟检查单
1. `/health` 200 · 6 lane online · puller last_pull < 60s
2. 录屏开启（第一保险）· 本机快照页就绪（第二保险）
3. 演示红线复习（DEMO-RUNBOOK-8051.md §16）：不说 4.8×、不点 text2cad、不提 frp
