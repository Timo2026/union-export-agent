# Demo Script v6 — 黄金链离线演示（数字均来自实跑）

> 运行：`python scripts/run_demo.py --offline`
> 内核：`offline:vendored-kernel(byte-identical)`（零网络/零 GPU/零外部服务）
> 回归：`python -m pytest tests/ -q` → **529 passed, 1 skipped, 0 failed**
> Skills：`python scripts/count_skills.py` → **26/26**（含新并入 `feasibility-checker`）

## 讲解顺序（6 步）

| # | 场景 | 结局 | 单价 | 总价 | 毛利 | 讲解点 |
|---|------|------|------|------|------|--------|
| 1 | S1 | PASS | 222.8 | 9413.3 | 23.1% | 标准件端到端自动批准，审计链 sha256 有效 |
| 2 | S2 | PASS | 3378.5 | 41724.5 | 23.1% | 高价值件；价格由确定性内核算，LLM 不参与定价（铁律②）|
| 3 | S3 | BLOCKED | - | - | - | 越权/不可承诺 → 输出护栏拦截归档，不生成报价 |
| 4 | S4 | PASS | 429.0 | 9480.9 | 23.1% | 另一 PASS 变体，展示链路稳定 |
| 5 | S5 | HITL | 3372.5 | 41650.4 | 23.1% | 触发人工复核，不自动作答 |
| 6 | **M1** | **HITL** | 222.8 | 9413.3 | 23.1% | **英雄时刻**：语音声称放宽公差 ±0.05 vs 邮件 ±0.02 → 冲突 `VOICE_EMAIL_CONFLICT`，系统**不静默采纳任一方**，升级人工 |

## 三条铁律演示话术

1. **数据不出本机**：M1 外部邮件 `auto_send=False`（仅草稿）；无 SMTP/IMAP 真实外发。
2. **LLM 不定价**：所有单价/总价来自确定性内核；`feasibility-checker`、专家 Agent 只判可行性/给建议，`pricing=none`。
3. **人工在环**：S3 拦截、S5/M1 HITL 升级，PASS 之外一律不自动发。

## 收尾

- 打开 V12 仪表板 / Workbench 看黄金链 8 步进度。
- 强调：这是**可跑通黄金链的工程原型 + 离线可复现演示**，非已上线生产系统（诚实口径）。

> 结果文件：`data/demo/demo_result.json`（`all_ok=true`, `engine_source=offline:vendored-kernel(byte-identical)`）。
