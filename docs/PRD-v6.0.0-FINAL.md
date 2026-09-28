# PRD v6.0.0 · FINAL（三份分歧合并定调）

> 状态：**待你最终拍板** · 日期 2026-09-19
> 作用：合并 `PRD-v6-NVIDIA-Alignment.md`(8任务/14h) + `PRD-v6-unified-workbench.md`(主线聚焦) + `PRD-v6.0.0-CONFIRM.md`(三周分层) 三份分歧，按**实测真相**定调
> 原则：实测优先于文档 · 消除双口径 · 无 GPU 不假装

---

## 0. 三份 PRD 分歧对比

| 维度 | Alignment(8任务) | Unified-Workbench(主线) | CONFIRM(三周) | **FINAL 取舍** |
|---|---|---|---|---|
| 核心主张 | 全量 V1-V8 14h | UI统一+NVIDIA口径，工程债降级v7 | W1-W3分层，最稳20h | **采 Unified 主线** |
| 装饰器/Pydantic | V2+V3 必做(3.5h) | 明确降级 v7 backlog | 列入 W2 | **降级 v7**（挤占 UI 时间） |
| DAG 编排 | 不在 V1-V8 | 不做 | 列入 W3 | **不做** |
| NIM 实证 | 云端探活(需key) | 口径为主+显式失败 | 云端探活(需key) | **见下方实测** |
| DoD 严格度 | 8 条验收 | 最严(版本唯一/数字一致/双确认/截图) | 量化指标 | **采 Unified DoD** |
| 缓存复用 | AgentCache 加键 | 未提 | 未提 | **采 Alignment 思路** |

---

## 1. 实测真相（2026-09-19 现场，优先于一切文档）

| 项 | 之前文档说 | **实测** | 偏差 |
|---|---|---|---|
| Skill 目录数 | 30 (README) | **25** | 🔴 营销虚高 |
| 有 tool.py 数 | 18 | **19** | 🟡 实际多 1 |
| 无 tool.py 数 | 7 | **6** | 🟡 实际少 1 |
| NVIDIA_API_KEY | 默认有 | **未设置** | 🔴 云端探活做不了 |
| NIM 进程 | — | **0** | 🔴 无实跑 |
| API:8900 | v5.1.0 | **ok v5.1.0 contexts=0** | 🟢 在线 |
| pytest | 508 passed | 上轮抽测 94/94 绿 | 🟢 主干健康 |

**结论**：①README "30 skills" 必须改 "25(19独立+6委托)"；②无 NVIDIA_API_KEY → D4 云端探活**当下不可行**，只能走"清单+显式失败"。

---

## 2. 最终主线（采 Unified-Workbench，合并 Alignment 缓存思路）

**一句话：以 `:8900/` 为唯一演示入口，接真 API、消灭 Mock 双口径、统一 NVIDIA 口径诚实表述、补 6 个缺 tool.py 的 skill；装饰器/DAG/Pydantic 降级 v7。**

### Must（v6 必做，~10h）
| ID | 任务 | 估时 | 验收 |
|---|---|---|---|
| F1 | 补 6 个无 tool.py skill（cnc-quote/dfm-conflict/reply-draft/rfq-extraction/step-analysis/verification）委托声明式 tool.py | 2h | 25/25 有 tool.py |
| F2 | 融合版壳接真 API：根 index.html 的 30 fetch 从 Mock 改真接线（新建 webui/v6/ 保留原件回退） | 4h | :8900/ 默认进 Workbench，5/5 endpoint 真 |
| F3 | 版本号统一：health/UI品牌/README/webui残标 全改 v6.0.0 | 1h | 四处同号 |
| F4 | README 数字诚实化：30→"25 Skill (19 独立+6 委托)"；NIM 加"(profile就绪,需GPU或API key实跑)" | 1h | 与实测一致 |
| F5 | 截图证据 docs/screenshots/v6/（默认/HITL/3D/Skill/审计 ≥5 张）+ pytest 回归 | 2h | 截图+508仍绿 |

### Should（若有余力，~3h）
| ID | 任务 | 估时 |
|---|---|---|
| F6 | AgentCache 加 `nvidia:health` 键（探活结果缓存，无 key 时显式 503 不假装） | 1h |
| F7 | guardrails nemo backend 切换路径写清（默认仍 builtin，文档标明切换步骤） | 1h |
| F8 | NIM 探活脚本 nim_health.py：有 NVIDIA_API_KEY 则探 build.nvidia.com，无则 503 | 1h |

### Won't（明确降级 v7）
- ❌ @register_function 装饰器 → v7（挤占 UI 时间，且 NeMo Toolkit 非赛题核心）
- ❌ Pydantic schema 自动生成 → v7
- ❌ DAG 编排(networkx) → v7
- ❌ OTel trace exporter → v7
- ❌ 真正 NIM 容器部署 → 需 GPU 环境

---

## 3. 最终 D1-D5 决策

| # | 决策 | **FINAL 答案** | 依据 |
|---|---|---|---|
| D1 UI 方向 | **融合壳吞真接线**（根 index.html 改 v6 壳，新建 webui/v6/） | Unified 主线 + CONFIRM 建议 |
| D2 改动方式 | **新建 webui/v6/ 保留原件** | 零回退风险 |
| D3 README 口径 | **"25 Skill (19 独立 + 6 委托声明)"** | 实测真相 |
| D4 NIM 证据 | **当下：清单+显式失败(无 API key)；若有 key：F8 云端探活** | 实测无 key |
| D5 执行范围 | **F1-F5 Must (10h) + F6-F8 Should (3h)** | 时间盒约束 |

---

## 4. NVIDIA 栈契合度预期

| 完成档 | 契合度 | 说明 |
|---|---|---|
| 只 F1-F5 (Must) | 3.5 → **3.9** | UI 口径统一 + 数字诚实，补齐运行时实证外的全部 |
| F1-F8 (全量) | 3.9 → **4.1** | 加缓存探活路径（仍无 key 不假装） |
| 若你给 NVIDIA_API_KEY | 4.1 → **4.3** | F8 真探活拿 1 条 trace |
| 装饰器/DAG/Pydantic(降级v7) | +0.3 潜力 | 不挤占比赛时间 |

---

## 5. 立即开工的第一步（确认后即执行）

```
1. 新建 webui/v6/ 目录，复制 webui/index.html 作基底
2. grep 出根 index.html 的 30 处 fetch，逐一改真 API
3. 跑 pytest 确保主干不破
4. README/health/版本号四统一
5. 截 5 张图
```

**等你一个字：开始 / 改某项 / 提供 NVIDIA_API_KEY。**
