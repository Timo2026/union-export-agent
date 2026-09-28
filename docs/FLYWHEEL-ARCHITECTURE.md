# FLYWHEEL-ARCHITECTURE.md — 飞轮架构契约

**版本**: v6.1
**日期**: 2026-09-19
**对应任务**: T6.1-T6.15 飞轮层
**分支**: `feature/flywheel-v6.1`

---

## 一、目标

> **让每一次报价都让下一次更准 + 让每一位客户都被留住**

三个飞轮相互驱动:

```
业务飞轮    → 询盘 → 自动报价 → 跟进 → 复购
              ↓
数据飞轮    → 报价结果回流 → 偏差学习 → 价格校准
              ↓
模型飞轮    → 客户偏好画像 → 健康分 → 流失预警 → 主动触达
```

---

## 二、5 张新表 (T6.1)

| 表 | 字段 | 用途 |
|---|---|---|
| **customer_health** | customer_id, health_score, churn_risk, total_quotes, won_quotes, lost_quotes, avg_margin_pct, avg_response_days, last_contact_at, breakdown_json | 客户健康快照 |
| **follow_ups** | id, customer_id, context_id, scheduled_at, sent_at, channel, intent, condition, status, response_text, nlg_variant | 跟进任务队列 |
| **quote_calibration** | id, context_id, customer_id, material, surface, quantity, quoted_unit_price, actual_unit_cost, deviation_pct, outcome, calibration_action, confidence | 报价偏差事件 |
| **preference_profile** | customer_id, tolerance_bias, material_preference, surface_preference, quantity_avg/std, decision_speed_days, price_sensitivity, preferred_incoterms, communication_style, risk_signals | 客户偏好画像 |
| **sandbox_quotes** | customer_id, context_id, quoted_at, material, surface, unit_price, outcome, ingested_to_rag | L2 历史报价语义索引 |

**新增位置**: `services/crm_memory.py` 同库追加 5 表，向后兼容（已有 4 表不变）。

---

## 三、5 个核心服务 (T6.2/3/4/5/6)

| 服务 | 类 | 职责 |
|---|---|---|
| `services/customer_health.py` | `CustomerHealthEngine` | 健康分计算 + 风险等级 + 主动触达决策 |
| `services/quote_calibration.py` | `QuoteCalibration` | 偏差学习 + bias_pct 提案 + 客户/全局聚合 |
| `services/customer_profile.py` | `CustomerProfile` | 偏好画像自动构建 + 增量更新 |
| `services/sandbox.py` | `CustomerSandbox` | L2 历史报价语义沙箱（per-customer SQLite） |
| `services/customer_flywheel.py` | `CustomerFlywheel` + `RetentionAlert` | 编排中枢: before_run + after_run |

**配合**: `services/sandbox.py` (per-customer SQLite)

---

## 四、4 个新 Skill (T6.7)

| Skill ID | 工具契约 | 后端 | iron_rule |
|---|---|---|---|
| `customer-flywheel` | `customer_flywheel(action, ...)` | services.customer_flywheel:CustomerFlywheel | deterministic |
| `quote-calibration` | `quote_calibration(action, ...)` | services.quote_calibration:QuoteCalibration | deterministic |
| `customer-health` | `customer_health(action, ...)` | services.customer_health:CustomerHealthEngine | deterministic |
| `retention-alert` | `retention_alert(threshold, days)` | services.customer_flywheel:RetentionAlert | deterministic |

**铁律保持**: 所有 4 个 Skill 都是 deterministic，不允许 LLM 干预。

---

## 五、Context 上下文联动 (T6.8)

9 区 Context → 11 区扩展:

```
原有 9 区:
  customer / rfq / geometry / rag / pending / verification /
  postmortem / commercial / trace

新增 2 区 (T6.8):
  flywheel_state: {health_score, churn_risk, follow_ups_due,
                   price_bias_pct, price_bias_confidence,
                   preference_tags, tolerance_bias, price_sensitivity,
                   last_outcome, _escalate_to_HITL}
  sandbox_ref: "customer_id" (指向 CustomerSandbox 标识)
```

---

## 六、CATController 钩子 (T6.9)

`run()` 头尾各加一行:

```python
# T6.9 before_run
ctx.flywheel_state = self.flywheel.before_run(customer)
ctx.sandbox_ref = ctx.flywheel_state.get("customer_id", "")

# ... 黄金链 8 步 ...

# T6.9 after_run
flywheel_result = self.flywheel.after_run(
    ctx.to_dict(), verification, reply
)
```

**返回**: `result["flywheel"]` 含沙箱写入/followup调度/健康分重算的 actions 列表。

---

## 七、Timo 引擎接入 (T6.10)

`adapters/timo_adapter.py:quote()` 新增参数:

```python
def quote(self, rfq: Dict[str, Any],
          dynamic_adjustments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """dynamic_adjustments = {bias_pct, confidence, source}
    作为 _flywheel_bias_pct 参数传给 Timo (铁律①保持: 不改 Timo 内部)
    """
```

飞轮产生的 bias_pct (上限 ±10%) 通过参数注入，不修改 calc_quote 内部确定性逻辑。

---

## 八、跟进任务调度 (T6.2)

报价 PASS 后自动生成 5 步跟进链:

| Day | 渠道 | 意图 | 触发条件 |
|---|---|---|---|
| 1 | email | check_clarity | 无回复 |
| 3 | telegram | gentle_nudge | 无回复 |
| 7 | email | add_incentive | 报价陈旧 |
| 14 | email | final_offer | 未成交 |
| 30 | internal | re_engage | 丢单回流 |

---

## 九、沙箱隔离 (T6.6)

两层沙箱并存:

| 层 | 文件 | 隔离粒度 | 用途 |
|---|---|---|---|
| **L1** | `services/sandbox.py` | 每客户独立 SQLite | 全数据隔离 (RFQ/quote/postmortem/pricing_model) |
| **L2** | `services/sandbox.py` (语义层) | 每客户 quotes.jsonl + RAG dataset | L2 历史报价语义索引 (跨沙箱不污染) |

**GDPR forget**: `CustomerSandbox.forget()` → 删除本地文件 + RAG dataset + 脱敏主库 PII。

---

## 十、5 场景 Demo (T6.15)

| ID | 场景 | 飞轮验证点 |
|---|---|---|
| D1 | 6061 阳极氧化 PASS | 跟进任务链 D+1/D+3/D+7/D+14/D+30 生成 |
| D2 | TC4 IT5 HITL | 健康分触发 HITL 升级 |
| D3 | 304+阳极氧化 BLOCKED | 失败原因回流 calibration |
| D4 | 多模态冲突 | L1 沙箱隔离 (A 不污染 B) |
| **D5** | **客户复购** | **L2 历史报价语义检索 + bias_pct -3%** |

---

## 十一、铁律守护 (6 条)

| 铁律 | 飞轮实现 |
|---|---|
| ① LLM 不负责价格 | flywheel 仅产生 bias_pct 作为 Timo 参数注入 |
| ② State Machine 是真相 | 飞轮 after_run 在 CRM_MEM 状态触发 |
| ③ Context 是唯一上下文 | flywheel_state + sandbox_ref 注入 Context |
| ④ RAG 提供证据不改事实 | L2 历史报价仅检索，不改 quote 数字 |
| ⑤ 多模态冲突必须升级 | 健康分低 → flywheel 建议升级 HITL |
| ⑥ AI Runtime 不是业务逻辑 | flywheel 是工具，决策在 CATController |

---

## 十二、测试覆盖 (T6.12)

41 个测试用例 (tests/test_flywheel.py):
- T6.1 SQLite 5 表 CRUD (8)
- T6.3 customer_health 健康分 (6)
- T6.4 quote_calibration 价格自学习 (6)
- T6.5 customer_profile 偏好画像 (4)
- T6.6 sandbox 隔离 (5)
- T6.2 customer_flywheel 编排 (4)
- T6.11 OpenShell + ALLOWLIST (2)
- T6.9 CATController 钩子 (2)
- T6.10 Timo 适配 (1)
- Iron Rule 不变量 (2)
- Demo D5 (1)

**全量回归**: 543 passed, 1 deselected, 0 failed

---

## 十三、文件清单 (新增/修改)

新增:
- services/customer_health.py
- services/quote_calibration.py
- services/customer_profile.py
- services/sandbox.py
- services/customer_flywheel.py
- skills/customer-flywheel/{SKILL.md, tool.py, __init__.py}
- skills/quote-calibration/{SKILL.md, tool.py, __init__.py}
- skills/customer-health/{SKILL.md, tool.py, __init__.py}
- skills/retention-alert/{SKILL.md, tool.py, __init__.py}
- tests/test_flywheel.py
- docs/FLYWHEEL-ARCHITECTURE.md

修改:
- services/crm_memory.py (新增 5 表 + 8 个 CRUD 方法)
- services/context_engine.py (新增 flywheel_state + sandbox_ref)
- agents/cat_controller.py (飞轮 init + before_run + after_run 钩子)
- adapters/timo_adapter.py (dynamic_adjustments 参数)
- services/guardrails.py (TOOL_ALLOWLIST 新增 4 个 skill)