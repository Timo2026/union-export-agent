# PRIOR-ART v7 — 外部方案调研（任务 #21 / A2，禁止重复造轮子）

> 日期 2026-09-20 · 方法：WebSearch 4 组关键词 · 结论口径：**方法学是否主流一致 + 是否有可直接引入的开源件**（受铁律①本地化 + 离线 vendored 约束，不轻易加依赖）

## 1. 本地混合检索（对应 #23 B1 / #29 C3）

| 先例 | 要点 | 对本项目 |
|---|---|---|
| [sqlite-vec + FTS5 混合检索](https://alexgarcia.xyz/blog/2024/sqlite-vec-hybrid-search/index.html) · [Simon Willison 评述](https://simonwillison.net/2024/Oct/4/hybrid-full-text-search-and-vector-search-with-sqlite/) · [notebook](https://github.com/liamca/sqlite-hybrid-search/blob/main/sqlite-hybrid-search.ipynb) · [RAG on SQLite](https://blog.sqlite.ai/building-a-rag-on-sqlite) | SQLite 单文件内 FTS5 关键词 + vec 向量 + RRF 融合 = 本地-first RAG 主流形态 | **印证我们"单库分层+RRF"设计正确**（funasr-gui 已是此模式）。sqlite-vec 需原生扩展，暂不引入依赖；#23 用 v6.2 vector_store + :1278 即可兑现同构设计 |
| [vstash: Local-First Hybrid Retrieval with Adaptive Fusion](https://arxiv.org/html/2604.15484v1) | 本地自适应融合检索（2026-04 论文） | 融合权重自适应可作为 #29 C3 迭代项，不阻塞 |

## 2. 分层/路由 RAG（对应 #23 B1 LayeredRAGGateway）

| 先例 | 要点 | 对本项目 |
|---|---|---|
| [Learning to Route Queries across Knowledge Bases for Step-wise reasoning](https://arxiv.org/html/2505.22095v1) | 多 KB 间查询路由是有研究支撑的独立问题（非拍脑袋架构） | 我们的"四层网关按层路由"方向主流；实现保持轻量（规则+embedding 打分）即可 |
| [LightRAG](https://github.com/hkuds/lightrag) | 图谱 RAG 开源件 | 不引入：需网络抽取管道+云 LLM 调用面，违反离线/本地铁律；工艺层保持 L4 现方案 |
| [RAG 客服系统设计 (MDPI)](https://www.mdpi.com/2674-113X/5/2/15) | 客户信息+工单分层进 RAG 的学术先例 | 佐证 L1 客户层的价值叙事 |

## 3. Skill 路由（对应待拍板的 F2 路由器）

| 先例 | 要点 | 对本项目 |
|---|---|---|
| [SkillRouter: Retrieve-and-Rerank Skill Selection at Scale](https://github.com/zhengyanzhao1997/SkillRouter) · [arXiv](https://arxiv.org/html/2603.22455v1) | 大规模技能库 = 检索-重排两阶段选择，已开源 | **直接印证路径3"池子+粗筛+精排"**；F2 若开工，先评估复用其检索骨架而非自写 |
| [Tencent/R3-Skill](https://github.com/Tencent/R3-Skill) | 腾讯开源的技能检索/重排 | 同上，候选参考实现 |
| [vLLM semantic-router cross-encoder reranking epic](https://github.com/vllm-project/semantic-router/issues/2247) | 工程级路由器正在做 bi-encoder+cross-encoder 运行时 | 三级混合路由（你贴的 MoE 材料）与工业界演进一致；我们可用其 issue 设计做参照，不引依赖 |
| [Skill Is Not Document: two-stage retriever for agent skill routing](https://www.researchgate.net/publication/405852700_Skill_Is_Not_Document_A_Query-Conditional_Benchmark_and_Two-Stage_Retriever_for_LLM_Agent_Skill_Routing) | 技能描述≠文档，需 query 条件化两阶段检索 | 提醒：池子元数据要按"可调度接口"建索引，不是全文 |

## 4. 历史报价相似检索（对应 #24 B2 / #30-33 D 线）

| 先例 | 要点 | 对本项目 |
|---|---|---|
| [CBR vs 回归 vs NN 成本估算比较](https://www.researchgate.net/publication/223310651_Comparison_of_construction_cost_estimating_models_based_on_regression_analysis_neural_networks_and_case-based_reasoning) | 小样本场景 CBR（相似案例锚点）优于学习模型——经典结论 | **"quote_anchor 相似工况历史报价"方法学正统**，正是 391 PO 数据量的正确姿势 |
| [制造成本 DL 估算](https://github.com/Rutwik1000/Manufacturing-Cost-Estimation-Based-On-Deep-Learning) · [报价自动生成项目](https://github.com/hadilaff/Project-Price-Prediction-and-Automated-Quote-Generation) | 玩具级，无机加工领域深度 | 无直接可引件；确定性引擎（Timo）+ CBR 锚点组合仍是自建最优 |

## 5. 负面对照（任务 #A3 · 行业真实性最强第三方证据）

> 来源：`email_receiver` 生产级 daemon（openclaw 生态，admin 生产机 systemd P0 + 看门狗，2026-03-08 部署至今约 6 个月）。
> **边界**：仅作证据/叙事引用，外部仓代码禁入 livekernel 仓体；其 SMTP 直发模式与本仓 egress DENY 直接冲突，不集成。
> **脱敏**：zip 内授权码已抹除、15MB 真实客户数据未打包，zip 本身干净。

| 维度 | email_receiver（野生生产系统） | livekernel（本仓） |
|------|-------------------------------|-------------------|
| 自动化等级 | L4（自动报价 + **自动 SMTP 直发**，无人工） | L3（PASS 自动批准 / HITL+BLOCKED 人工兜底） |
| 价格生成 | SQLite 引擎直接算 → 直接对外 | Timo 引擎裁决 + **sha256 锁**；LLM 永不定价 |
| 审计 | 无审计链 | SHA-256 tamper-evident 链式审计 |
| 外发策略 | SMTP 自动回复（事故面） | **egress 默认 DENY**；draft_only；HITL 永不自动外发 |
| 状态机 | 无 | RFQStateMachine 非法转移拦截 |
| 多模态冲突 | 静默覆盖 | 必须升级不静默覆盖 |

**判定**：这是一份"防火墙式自动回复"模式的真实生产样本。它**正面证明行业痛点真实**（6 个月生产、CNC 询盘→报价→回复全管线有人用）；同时**反面印证本仓设计前提**——铁律①（价格引擎裁决+sha256 锁）、draft_only、HITL、egress DENY 不是学院派洁癖，而是对这种"自动外发无锁定"事故面的工程回答。

**用法**：写进交付报告 §3（行业问题）作为痛点真实性证据；答辩时作为"接口兼容≠行为等价"的对照——它也能自动报价，但**不可审计、不可验证、不可回退**，与本仓的可验证商业对象形成正反对照。

---

## 6. 总裁定

1. **无需引入任何新依赖**：sqlite-vec/LightRAG/semantic-router 均因离线铁律/原生扩展/云调用面暂不引入；但**方法学与上述主流全部同向**，答辩叙事可直接引用。
2. 唯一值得**代码级复用评估**的是 SkillRouter/R3-Skill 的两阶段检索骨架（待 F2 拍板后）。
3. CBR 文献是 #24 quote_anchor 的理论背书——写进 SER/验收报告。
