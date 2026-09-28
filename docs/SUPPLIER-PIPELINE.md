# Supplier Pipeline (v2.3.0) — 客户确认后履约子系统

> **客户面前**（v2.0–v2.2）：邮件→RFQ→DFM→CNC 报价→关务→发价→CRM。
> **工厂背后**（v2.3.0 NEW）：客户确认 → **脱敏 → 匹配 → 询价 → 选 → 下单**。

## 1. 为什么单独做一个子系统

| 维度 | 现有项目（v2.2.0） | v2.3.0 新增 |
|---|---|---|
| 角色 | 客户面前 | 工厂背后 |
| 输入 | 客户邮件/RFQ | 客户确认事件 |
| 输出 | 英文报价单 + CRM | 脱敏 ZIP + PO + 供应商回执 |
| 核心门禁 | 毛利/公差/金额/冲突 | **零客户 PII 泄漏** |
| 持久化 | `crm.sqlite3` + 审计链 | `suppliers.sqlite3` + `supplier_pipelines/*.json` |
| 利润模型 | 引擎 final_price（已含~30%） | 外协 markup（独立，不双算） |

**关键边界**：客户面前价格（final_price，含利润）≠ 外协履约成本 + markup。两条定价路径，**绝不双算**。

## 2. 状态机（子状态机，独立于主 RFQ 状态机）

```
PENDING → DESENSITIZED → MATCHED → QUOTED → SELECTED → PO_SENT → CONFIRMED
   ↓         ↓             ↓        ↓         ↓          ↓
  FAILED    FAILED        FAILED   FAILED    FAILED    FAILED
```

- 任意状态可转 FAILED（终态）
- CONFIRMED / FAILED 不可再出
- 历史全保留（`SupplierPipeline.history`）
- 持久化：每一步原子写 `data/supplier_pipelines/{context_id}.json`

## 3. 模块清单

```
supplier_module/
├── __init__.py
├── desensitize.py        # STEP header / PDF /Info / 标题栏 / 文件名 → 指纹哈希
├── supplier_db.py        # SQLite schema v1.0 + 10 家种子（5 国内 + 5 海外）
├── matcher.py            # 7 维加权打分 + TopN
├── supplier_inbox.py     # MockInbox(内置) + IMAPInbox(默认 raise NotImplementedError)
├── po_generator.py       # PO dataclass + text（markup 独立计算）
├── state_machine.py      # 子状态机 + JSON 持久化
├── auto_threshold.py     # AUTO 阈值（features_count<10 && route<10）
└── orchestrator.py       # 端到端编排（失败用 PipelineResult.failed=True 表达）
```

## 4. 核心契约（不可破）

### 4.1 零客户 PII 泄漏（硬门禁）
- 流向供应商的 ZIP（来自 desensitize.py）必须**不包含**客户姓名/邮箱/电话/地址/项目号/图纸元数据
- 测试断言：`tests/test_desensitize.py::test_zip_globally_contains_no_customer_pii`（15 测试覆盖）
- 客户档案指纹：`SHA-256(salt + JSON(规范化档案))`，用于内部关联，不可逆

### 4.2 markup 不双算
- 引擎 final_price：已含~30% 利润（policy.margin.target_pct=30）
- 外协 sell：PO 成本 × (1 + markup_pct/100)
- **两条路径独立**，由 `compute_outsource_markup()` 隔离计算

### 4.3 AUTO 阈值叠加非替换
- 新增 `config/policy.yaml:auto_quote_threshold`（features_count_max=10, process_route_max=10）
- 与现有 HITL 门禁（IT4/IT5/毛利/金额/缺失/多模态）**叠加**：任一不满足仍 HITL
- 严格小于（`<`），等于阈值不进 AUTO

### 4.4 数据不出车间
- MockInbox 是默认（v2.3.0 内置响应模板）
- IMAPInbox 必须显式 `enabled=True` 才会执行（`NotImplementedError` 兜底）
- 即使 enabled=True 也是占位（不连真实 IMAP），roadmap 才有真接入

## 5. 端到端流（happy path）

```python
from supplier_module.orchestrator import run_supplier_pipeline
from supplier_module.supplier_inbox import MockInbox, SupplierQuote

result = run_supplier_pipeline(
    context_id="ctx-001",
    customer={"name": "...", "email": "...", "project_code": "..."},
    rfq={"material": "6061", "processes": ["milling"], "quantity": 50,
         "promised_lead_time_days": 14, "destination_region": "domestic"},
    files=[("bracket.step", step_bytes, "step"), ("drawing.pdf", pdf_bytes, "pdf")],
    inbox=MockInbox(responses={1: SupplierQuote(1, 200.0, 10, "ISO9001", 0.9)}),
    markup_pct=30.0,
)
# result.final_state == CONFIRMED
# result.po["sell_price_cny"] == 260.0  # 200 × 1.30
# result.artifacts["desensitize"]["customer_fingerprint"]  # SHA-256
```

## 6. 测试统计

| 模块 | 测试数 | 通过率 |
|---|---:|---:|
| desensitize | 15 | 100% |
| supplier_db | 12 | 100% |
| matcher | 16 | 100% |
| state_machine | 12 | 100% |
| supplier_inbox | 7 | 100% |
| po_generator | 7 | 100% |
| auto_threshold | 7 | 100% |
| outsource_markup | 6 | 100% |
| skill_registry | 6 | 100% |
| pipeline (集成) | 11 | 100% |
| **新增小计** | **99** | **100%** |
| pytest 全量 | 245 | 100% |

## 7. Roadmap（不挡 v2.3.0 演示）

- **几何相似度匹配**：当前用材料/工艺/公差/产能/交期标签打分；可加 STEP shape signature / embedding 评分
- **IMAP 真接入**：当前占位；生产部署时显式 `enabled=True` + 凭据
- **GTM 验证**：供应商收到脱敏 ZIP 后回执解析（当前 mock）
- **审计链**：每一步 SHA-256 哈希串接（参考 crm_memory 模式）

## 8. DoD 验收

- [x] supplier_module/ 9 个核心文件
- [x] data/suppliers.sqlite3 10 家种子
- [x] skills/supplier-match/SKILL.md 进注册表
- [x] config/policy.yaml 加 AUTO 阈值
- [x] services/commercial.py 加外协 markup
- [x] 99 个新测试全绿
- [x] docs/SUPPLIER-PIPELINE.md
- [x] 1 个新 notebook 演示
- [x] CHANGELOG / MANIFEST 同步
- [x] git commit v2.3.0
- [ ] 有 GPU 时：PO 邮件模板 → SMTP 真发送（roadmap）