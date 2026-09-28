# Negative Trigger 矩阵（核心 8 skill）

> 对应 PRD §7.2。评委最狠的一问：「会不会对无关输入也乱触发业务 skill？」本矩阵 + 配套负向 pytest 是硬答。
> 状态：**草稿骨架**，待 M5 填实并在 Spark 复跑。

## 采集元信息（M5 跑完填）

- 节点：`spark-NN`（仅编号）
- 时间：`YYYY-MM-DD HH:MM`（节点时区）
- 路由层版本：`agents/cat_controller.py` commit hash
- 负向测试结果：见 `negative-pytest.txt`

## 矩阵

对每条核心 skill 写清四列：何时触发 / **何时禁止触发** / 误触发后果 / 对应负向测试 ID。

| Skill | 正向触发 | **禁止触发（negative）** | 误触发后果 | 负向测试 |
|-------|----------|--------------------------|-----------|----------|
| `calc-quote` | 已抽取 RFQ + 引擎可达 | 闲聊/天气/纯翻译；用户口头"编个价格"而无引擎输入；图纸未过 DFM | 铁律①被绕过，价格由 LLM 生成 → 审计链断裂 | `test_neg_calc_quote_no_engine_input` / `test_neg_calc_quote_chitchat` |
| `dfm-conflict` | 已有 RFQ + 工艺约束 | 无图纸/无工艺上下文的纯文本问答 | 幻觉冲突，BLOCKED 误爆 | `test_neg_dfm_no_drawing` |
| `rfq-extraction` | 邮件/语音/STEP 含询盘信号 | 已是结构化 RFQ；非询盘闲聊 | 重复抽取/字段污染 | `test_neg_rfq_already_structured` / `test_neg_rfq_smalltalk` |
| `reply-draft` | 报价已裁决 + 状态 PASS/HITL | BLOCKED 状态；铁律①未过；egress 未放行 | draft_only 失守 → 真发信 | `test_neg_reply_blocked_state` / `test_neg_reply_egress_closed` |
| `verify-gate` | 引擎返回结果待核 | 引擎不可达且无离线兜底 | 假 PASS 通过 | `test_neg_verify_no_engine_no_offline` |
| `rag-ingest` | 客户文件/语音到位 | 已入库重复文件；egress 敏感文件 | 重复向量/数据外溢 | `test_neg_rag_dup_ingest` |
| `orchestrator` | 多步业务流上下文 | 单步闲聊指令 | 过度编排、浪费 token | `test_neg_orchest_single_turn` |
| `ceo-decision` | 战略级冲突需升级 | 常规报价冲突（应走 dfm-conflict） | 升级泛滥、HITL 过载 | `test_neg_ceo_routine_conflict` |

## 制式补丁（写到每个 SKILL.md）

每个核心 SKILL.md 增补一段：

```markdown
## Negative triggers（不触发）
- 与报价/DFM/审计无关的闲聊、翻译闲谈、纯代码问答
- <skill 专属的禁止条件>
误触发后果：<一句话>
对应负向测试：tests/test_neg_<skill>.py::<test_id>
```

## M5 验收门禁

- [ ] 上表 8 行「禁止触发」全部填实且非模板套话
- [ ] 8 个核心 SKILL.md 已写入 Negative triggers 段
- [ ] `tests/test_neg_*.py` 全绿（目标 skill 未被选中，或被选中但被 guardrails/allowlist 拒绝）
- [ ] 至少 1 组负向用例在 Spark 节点复跑通过
