# 项目进度看板 · 防盲目（实证盘点）

| 字段 | 内容 |
|------|------|
| 日期 | 2026-09-21（基于仓内实证，**未**本回合重跑 pytest） |
| 权威口径 | `docs/PRD-MASTER-UEA-DELIVERY.md` **v2.0**（冲突以该文为准） |
| 对比报告 | `docs/NODE-DIFF.md`（2026-09-21 07:35） |
| 纪律 | **停止加新模块**；先收敛底层/接口/最小闭环 |

---

## 1. 一句话诊断

你的判断成立：**可分解性低、耦合高、接口不稳定、底层未完全定**。  
本机模块「很多且深」，节点「几乎只有硬件」；文档/方案已多线并行，**缺的是单一可冻结的 v0 接口 + 一条双方都跑通的最小闭环**。

---

## 2. 本地模块盘点（有什么 · 能干什么）

### 2.1 结构层

| 层 | 产物 | 独立可跑？ | 质量/依赖 |
|----|------|------------|-----------|
| **Adapters** | `timo_adapter` / `funasr_adapter` / `_kernel_bridge` / `skill_pack_adapter` | Timo 离线 **可独立** | 铁律①核心；依赖引擎路径或 vendored |
| **Agents** | `cat_controller`（黄金链） | 经 bootstrap/API 可跑 | 与 services 强耦合（正常） |
| **Skills** | **33** 目录，本轮核验 **33/33 SKILL.md + tool.py** | 单 skill 可测；整链依赖 dispatcher | `skills.yaml` 注册 ≠ 目录全开（E-07 曾 🟡） |
| **Services** | **60+** py：mail_* / rag_* / flywheel / guardrails / api / nim_* / customer_* … | 多数**不能单独当产品** | 密度高 = 耦合与漂移风险 |
| **Config** | settings / models / agent / skills / openshell / dgx-spark-* | 配置源多 | **接口不稳定主因之一** |
| **Deploy** | nim compose / k8s / spark 探针 / node_* 脚本 | 节点侧脚本多、仓外凭据 | docker 节点已关闭 |
| **Scripts** | demo / golden / e2e / export / start_* | 本机演示链 **可跑**（验收报告） | — |
| **Tests** | 88 个 test_*.py；主 PRD 写 **725 passed**；NODE-DIFF 写 **752** | 本机可跑 | **数字不一致 → 进度板钉死：以一次 canonical 复跑为准** |
| **Docs/Plans** | PRD/PLAN×多、十日谈、PRIOR-ART、EMAIL-AGENT-DECISION… | 文档过剩 | 已触发「作废 banner」机制，需单一入口 |
| **UI** | `webui/index.html` Workbench | 本机可开 | 13 标签叙事 vs 接线需对账 |

### 2.2 能力映射（邮件 Agent 诉求 vs 已有）

摘自 `EMAIL-AGENT-ARCH-DECISION.md`（已收敛过一轮）：

| 诉求 | 现状 |
|------|------|
| 邮件驱动 | mail_puller + mail_orchestrator **已有** |
| V6 控制台 | Workbench **已有** |
| Agent vs 邮件来源标记 | audit 有 actor **缺 origin** → 真缺口 |
| 客户 email ID | CRM 模式 **已有** |
| 历史推演回复 | RAG L2 + reply-draft **已有** |
| OpenClaw skill | skill_pack_adapter 边界 **已有** |
| RAG+知识库 | rag_layers + data/knowledge **已有** |
| LLM Wiki | **未实现**（赛期风险项） |

**结论**：继续「拼邮件模块」低效；高杠杆是 **origin + 闭环演示 + 接口冻结**。

---

## 3. SSH / 节点 vs 本地（NODE-DIFF 摘要）

| 维度 | 本地 Windows | spark-388d | 判定 |
|------|--------------|------------|------|
| GPU | **无**（torch+cpu） | **GB10 + CUDA13**，Qwen3-0.6B **~77 tok/s GPU** | 节点独占平台分 |
| 架构 | x86_64 | **aarch64** | �署必须 Linux/aarch64 |
| 内存/盘 | — | 121GB 统一 / 1.5T 空闲 | 可驻留模型 |
| livekernel 代码 | **完整仓** | **无任何副本** | **最大断点** |
| Skills | 33 | 无 | 未同步 |
| 测试 | 本机绿（725/752 待统一） | node_pytest_arm.txt 有证据文件 | 节点非全量业务测 |
| OCC/CAD | 无 | **occ env + STEP smoke 产物** | 节点几何链已探 |
| vLLM / NIM | — | vLLM **未装**；**docker 无权限** | 容器路线关闭 |
| 模型权重 | — | hf-mirror **可下载**（Nemotron 清单已实测） | 未等于已驻留服务 |
| 证据落盘 | docs/evidence 部分 | `data/node_evidence/*` 7 项 | 有用但未收口进 evidence 规范 |

---

## 4. 真实进度（防盲目）

### 4.1 已完成（有证据）

| 项 | 证据 |
|----|------|
| 产品主干 + 33 Skills 制式 | 目录核验 + README/MANIFEST |
| 本机全量测试绿 | 主 PRD v2：**725 passed**（canonical `pytest tests/ -q`） |
| 离线黄金链 / 导出自检 | ACCEPTANCE-v7、export leaks 0 |
| 行业语料管线 | SER R-04~R-06（杰沃 PO/BOM） |
| 节点 SSH + GPU 推理链路 | Timo-SSH + NODE-DIFF + node_evidence |
| 节点 OCC STEP 冒烟 | `data/node_evidence/node_occ_*` |
| 模型「可下载」门禁 | 主 PRD §1.2-F（仓库 ID/体积） |
| 邮件架构收敛决策 | EMAIL-AGENT-ARCH-DECISION（80% 已有） |
| 文档权威入口 | MASTER PRD v2 + 作废 banner 机制 |

### 4.2 未完成 / 高风险缺口

| 缺口 | 为何致命 | 状态 |
|------|----------|------|
| **节点无 livekernel** | 平台分与「Spark 上跑 Agent」叙事无主体 | 🔴 断点 |
| **工作树 465+ 未提交 + 版本三处分裂** | 接口/配置无法冻结，协作即灾难 | 🔴 |
| **配置源过多**（settings/models/agent/dgx-spark 多份） | 每个 Agent 一套配置 | 🔴 接口债 |
| **origin/provenance 未入审计** | 控制台标记诉求未落地 | 🟡 小缺口 |
| **negative trigger / A/B 正式报告** | Skills 深度分 | 🟡 部分文档 |
| **Nemotron/vLLM 服务未起** | 口播仅能 N1，不能 N2+ | 🟡 下载≠服务 |
| **测试数字 725 vs 752** | 进度失真 | 🟡 钉死即可 |
| **方案文档多线** | 盲目感来源 | 🟡 收敛入口 |

### 4.3 阶段完成度（粗算，非虚高）

```
架构愿景     ████████░░  方向多但未收敛为单一 v0
本机产品     ███████░░░  功能面广，测试绿，版本/接口未冻
节点平台     ███░░░░░░░  硬件/GPU/OCC 有，Agent 未部署
最小闭环     ████░░░░░░  本机黄金链可演示；节点/邮件驱动未双端贯通
接口冻结     █░░░░░░░░░  未开始正式 freeze 文档
集成骨架     ███░░░░░░░  有 bootstrap/api，缺统一 mock 骨架约定
分工效率     ███░░░░░░░  正在从「并行拼模块」切到「收敛」
```

---

## 5. 本地 ⇄ 节点「该先对齐的 8 件事」

| # | 事 | 侧 | 优先级 |
|---|----|----|--------|
| 1 | **脱敏 livekernel 包上节点**（whitelist） | 节点 | P0 |
| 2 | 节点 **离线黄金链**（vendored/OCC env）跑通 | 节点 | P0 |
| 3 | 本机 **canonical pytest 一次** 写入看板 | 本地 | P0 |
| 4 | **配置契约收敛**（唯一 schema，其余 overlay） | 双侧 | P0 |
| 5 | audit **origin** 字段 + UI 标签 | 本地→节点 | P1 |
| 6 | 模型：先 **Embed-1B + Nano-4B** 进程级 `/v1`（按主 PRD） | 节点 | P1 |
| 7 | evidence 目录收口 node_evidence → docs/evidence/spark | 本地 | P1 |
| 8 | 版本 pin 一处真相 | 本地 | P0 |

---

## 6. 本看板的使用规则

1. **任何新功能提案**先对照 §2/§4：已有则接线，不新造。  
2. **任何 Agent 分工**必须挂在「已冻结接口」上；未冻接口不开新模块仓。  
3. **进度数字**只引用：canonical pytest、节点 health、golden 3/3、evidence 文件列表。  
4. 权威文档入口：**仅** `PRD-MASTER-UEA-DELIVERY.md` + 本看板 + 后续 `IFACE-v0.md`。
