# NemoClaw Integration Design — 选项 C 混合架构

**日期**: 2026-09-18
**作者**: qoder (brainstorming session)
**状态**: 已实施 (v3.0.0) — 用户批准方案 C + 设置功能；代码已落地，pytest 354 passed
**关联**: v3.0.0 (NemoClaw hybrid) / v2.4.0 (5-tab console) / v2.3.1 (A/B routing)


---

## 1. 背景与动机

v2.4.0 已交付稳定前端 + 后端 (反馈邮箱 / 3D STEP 上传 / A/B 路由 / 黄金链 6/6).
但用户反馈: 能力散落在 `/v1/*` 端点, 调度靠人写 if/else, 缺乏"自然语言 → 自动选 Skill"的智能路由.
NVIDIA 2026-03 GTC 发布的 NemoClaw (基于 OpenClaw + NeMo Agent Toolkit) 提供了官方架构:
**Blueprint + Agent Harness (Nemotron) + Skills + OpenShell 沙箱 + Model Router**.
我们采用**选项 C 混合方案**: 后端能力全 Skill 化 + 轻量 Skill Dispatcher (LLM 意图路由) + OpenShell 策略层强制铁律① + 新增 Skill 设置面板.

---

## 2. 架构 (目标态)

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend Layer (二选一, 不绑死)                              │
│  ┌──────────────────────┐    ┌──────────────────────────┐  │
│  │ v2.4.0 webui (保留)  │    │ NemoClaw Chat UI (可选)  │  │
│  │ 5 tabs + SVG icons   │    │ Nemotron-3-Ultra 前端    │  │
│  └──────────┬───────────┘    └────────────┬─────────────┘  │
└─────────────┼──────────────────────────────┼────────────────┘
              │ POST /v1/agent/task         │ NeMo Relay
              ▼                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Skill Dispatcher (新增 services/skill_dispatcher.py)         │
│   ├─ 接收: 自然语言 / 文件 / 上下文                          │
│   ├─ LLM 意图分类 (Nemotron 本地 / Ollama 兜底)              │
│   ├─ 路由: 选 1..N 个 Skill, 编排顺序                        │
│   └─ 返回: Skill 执行轨迹 + 最终产物                         │
└──────────────────────────┬──────────────────────────────────┘
                           │ function calling
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Skills (全封装, 每 Skill = Python 函数 + YAML schema)        │
│   ├─ Skill: parse_rfq         (intake 7 文件类型)            │
│   ├─ Skill: extract_specs     (LLM 提参, 可空)               │
│   ├─ Skill: check_dfm         (Timo 确定性, 铁律①)           │
│   ├─ Skill: calc_quote        (Timo 确定性, 铁律①)           │
│   ├─ Skill: verify_gate       (5 步验证 + HITL)              │
│   ├─ Skill: write_reply       (LLM 起草, Timo 校验)          │
│   ├─ Skill: submit_feedback   (v2.4.0)                       │
│   ├─ Skill: render_thumbnail  (v2.4.0)                       │
│   └─ Blueprint: golden_chain  (pipeline.run 状态机封装)      │
└──────────────────────────┬──────────────────────────────────┘
                           │ OpenShell 沙箱 (新增 openshell/)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  OpenShell Policies (新增 openshell/*.yaml)                   │
│   ├─ iron-rule-1.yaml   DETERMINISTIC 工具拒绝 LLM override │
│   ├─ hitl-required.yaml 高风险自动转人工审批                 │
│   ├─ local-only.yaml    文件路径限制 data/uploads/ + 沙箱   │
│   └─ skill-allowlist.yaml 显式列出可调用的 Skill 列表        │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / SDK
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Engine Layer (不动)                                          │
│   ├─ Timo 确定性内核 :7862                                  │
│   ├─ FunASR :8866                                          │
│   └─ SQLite feedback_store / thumbnail 缓存                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Skill 接口规范 (NemoClaw 兼容)

每个 Skill = 1 Python 函数 + 1 YAML schema + 1 unit test.

**Skill YAML 模板** (`skills/<skill_id>/SKILL.md` + `tool.py`):
```yaml
id: check_dfm
label: DFM 冲突检测 (Timo)
description: 11 硬规则冲突检测, 确定性, 不接受 LLM override
iron_rule: deterministic   # OpenShell iron-rule-1 强校验
input_schema:
  type: object
  required: [drawing, material, process]
  properties:
    drawing: {type: string, description: "STEP 文件路径 (data/uploads/ 内)"}
    material: {type: string, enum: [6061, 7075, ...]}
    process: {type: string, enum: [mill, lathe, ...]}
output_schema:
  type: object
  properties:
    conflicts: {type: array, items: {type: string}}
    risk_score: {type: number, minimum: 0, maximum: 1}
openshell_policy:
  - iron-rule-1      # 拒绝 LLM 修改 output.conflicts
  - local-only       # 拒绝路径逃逸 data/uploads/
```

**Python 函数签名**:
```python
def run(drawing: str, material: str, process: str, *, ctx: SkillContext) -> dict:
    """铁律①: 该函数输出权威, LLM/Dispatcher 不能修改."""
    ...
```

---

## 4. 新增文件清单 (凭代码核对, 不背书)

| 文件 | 状态 | 行数估 | 用途 |
|------|------|--------|------|
| `services/skill_dispatcher.py` | NEW | ~250 | LLM 意图分类 + Skill 编排 |
| `skills/<8 个 skill>/SKILL.md` | NEW | ~80×8 | NemoClaw Skill schema |
| `skills/<8 个 skill>/tool.py` | NEW | ~50×8 | Skill Python 函数封装 |
| `openshell/iron-rule-1.yaml` | NEW | ~40 | DETERMINISTIC 工具锁定 |
| `openshell/hitl-required.yaml` | NEW | ~30 | 高风险 HITL |
| `openshell/local-only.yaml` | NEW | ~25 | 路径沙箱 |
| `openshell/skill-allowlist.yaml` | NEW | ~20 | Skill 白名单 |
| `services/api_server.py` (扩) | MOD | +60 | +`/v1/agent/task` 端点 |
| `webui/index.html` (扩) | MOD | +200 | 新增 `#tab-skills` 设置面板 |
| `webui/skills_panel.js` | NEW | ~120 | Skill 启用/禁用 + 策略检查 |
| `tests/test_skill_dispatcher.py` | NEW | ~150 | 路由 + 编排测试 |
| `tests/test_openshell_policies.py` | NEW | ~120 | YAML 加载 + 铁律校验 |
| `tests/test_skills_integration.py` | NEW | ~200 | 8 Skill 端到端 |
| `docs/nemoclaw-architecture.md` | NEW | ~200 | 架构图 + 对外文档 |

总计 ~2150 行新增 + ~260 行修改. 估计 4-5 个 PR (按依赖切分).

---

## 5. Skill Dispatcher 接口设计

**入口**: `POST /v1/agent/task`
```json
{
  "intent": "客户上传 STEP + RFQ 邮件, 想要报价",
  "files": ["uploads/draw.step", "uploads/rfq.eml"],
  "context_id": "ctx_xxx"  // 可选, 接续历史
}
```

**返回**:
```json
{
  "dispatch_id": "disp_xxx",
  "trace": [
    {"skill": "parse_rfq", "input": {...}, "output": {...}, "ts": "..."},
    {"skill": "check_dfm", "input": {...}, "output": {...}, "ts": "...", "iron_rule_applied": true},
    ...
  ],
  "result": {...},  // 最终产物 (报价 / 反馈入库 / 缩略图)
  "hitl_required": false,
  "openshell_violations": []
}
```

**LLM 意图分类** (Nemotron 本地优先, Ollama 兜底):
- 输入: 用户 intent + files metadata + 历史 context
- 输出: Skill 调用序列 `[{skill: "parse_rfq", args: {...}}, ...]`
- 铁律: 分类只决定**调用哪些 Skill**, 不决定 Skill 的 output.

---

## 6. OpenShell 策略 (铁律①的工程化)

**iron-rule-1.yaml** (新增):
```yaml
policy_id: iron-rule-1
description: 确定性工具拒绝 LLM/Director override
applies_to:
  - check_dfm
  - calc_quote
  - verify_gate
enforce:
  - "skill.output.conflicts 在 dispatch 后不可被修改"
  - "skill.output.quote_total 与 Timo 内核返回值必须一致 (sha256 比对)"
  - "skill.output.risk_score > 0.7 触发 hitl-required"
audit:
  - "所有 iron-rule Skill 调用必须落 audit_log (SHA-256 hash chain)"
```

**hitl-required.yaml** (新增):
```yaml
policy_id: hitl-required
description: 高风险自动转人工
trigger:
  - quote_total > 50000 USD
  - risk_score > 0.7
  - "process == '5-axis-milling' AND material in ['titanium', 'inconel']"
action:
  - "dispatch 返回 hitl_required: true, 不返回最终报价"
  - "webui 弹 HITL modal, 等待人工 /v1/rfq/{id}/approve"
```

**local-only.yaml** (新增):
```yaml
policy_id: local-only
description: 数据不出车间
constraints:
  file_paths:
    allow_prefix: ["data/uploads/", "data/contexts/", "data/feedback.sqlite3"]
    deny_glob: ["*.env", "**/secret*", "/etc/*"]
  network:
    deny_hosts: ["0.0.0.0/0"]  # 拒绝外网, 除非显式 allowlist
    allow_hosts: ["127.0.0.1", "localhost", "timo:7862", "funasr:8866"]
```

---

## 7. 设置面板 (webui/index.html 第 6 个 tab)

新增 `#tab-skills`, 与现有 5 tab 并列:
- **Skill 列表**: 8 个 Skill 卡片, 每张显示 enable/disable toggle + 描述 + 上次调用时间
- **OpenShell 策略**: 4 个策略的 enable/disable + 当前违规计数
- **Model Router**: Nemotron 本地 / Ollama / OpenAI 兼容 / A/B (沿用 v2.3.1) 4 选项
- **铁律① 锁定**: 不可关闭 (按钮 disabled + tooltip 解释)
- **保存**: 调 `/v1/skills/config` POST, 落 `config/skills.yaml` (新增)
- **审计**: 最近 20 条 Skill 调用 + OpenShell 违规记录 (只读)

---

## 8. 数据流 (一次完整任务)

```
1. 用户上传 STEP + 在 intent 框写"我要报价, 5 天交期"
2. webui → POST /v1/agent/task {intent, files: [step]}
3. Skill Dispatcher:
   a. 调用 Nemotron / Ollama: 意图分类 → [parse_rfq, check_dfm, calc_quote, verify_gate, write_reply]
   b. 检查 openshell/skill-allowlist.yaml → 5 Skill 都在白名单
   c. 顺序执行, 每步记录 trace
   d. check_dfm 输出 conflicts → iron-rule-1 锁定, 不让 LLM 改
   e. calc_quote 输出 quote_total = 32500 USD → 不触发 HITL (< 50000)
   f. verify_gate: 5 步验证 PASS
   g. write_reply: LLM 起草, Timo 校验语法/单位
4. 返回: trace + result{quote, reply_draft, verification_status: PASS}
5. webui 渲染: 黄金链完成, 用户可审批 / 修改 / 拒绝
6. audit_log 落盘 (SHA-256 hash chain, 不可篡改)
```

---

## 9. 测试策略 (凭代码核对)

| 测试文件 | 覆盖 | 估行数 |
|---------|------|--------|
| `tests/test_skill_dispatcher.py` | 路由 / 编排 / LLM 兜底 / OpenShell 拦截 | ~150 |
| `tests/test_openshell_policies.py` | 4 个 YAML 加载 + 铁律校验 + HITL 触发 | ~120 |
| `tests/test_skills_integration.py` | 8 Skill 端到端 (mock Timo) | ~200 |
| `tests/test_skills_api.py` | `/v1/agent/task` 端到端 | ~80 |
| `tests/test_skills_ui.py` | webui 6 tabs + 设置面板 smoke | ~30 |

目标: v2.4.0 的 326 passed + v3.0.0 新增 ~80 = **~406 passed**.

---

## 10. 风险与边界 (诚实)

| 风险 | 缓解 |
|------|------|
| Nemotron 本地模型本机无 GPU | Ollama fallback (CPU 跑 Nemotron-1B / Qwen2.5-3B), latency ~3s/req |
| NeMo Agent Toolkit 装包失败 | 不强依赖, Skill YAML 通用规范可被任意 Harness 读, 我们提供最小 dispatcher |
| 比赛现场演示时 LLM 离线 | 强制 fallback 到规则路由 (regex 提参 + 关键词匹配 Skill) |
| 铁律①被 LLM 绕过 | OpenShell 双层守护: iron-rule-1.yaml 在 Skill 层 + 沙箱在 syscall 层 |
| OpenShell YAML 误改 | skills.yaml + openshell/*.yaml 都进 git, 改必须走 PR review |
| 改造工作量大 (4-5 PR) | 按依赖切分: PR1=Skill 骨架 → PR2=Dispatcher → PR3=OpenShell → PR4=设置面板 → PR5=回归 |

---

## 11. 不在 v3.0.0 范围 (留给未来版本)

- three.js 真实三维预览 (当前等角投影 SVG 已够用)
- SMTP 中继闭环反馈邮箱
- 跨主机多 Skill 联邦调度
- 实时协作 (webui 多用户同时编辑)
- v3.x 增量: blueprint 热加载 / Skill 版本管理 / 分布式 audit

---

## 12. 检查清单 (实施前必过)

- [ ] 用户 review 通过本 spec
- [ ] Nemotron-3-Ultra 或 Ollama 在本机可跑 (或确认 fallback 路径)
- [ ] Skill 8 个函数的 input/output 与现有 pipeline.run() 字段对齐
- [ ] OpenShell 4 个 YAML 在 dispatcher 启动时强制加载, 缺一即 fail-fast
- [ ] 铁律① 校验有自动化测试: 试图 LLM 改 quote → assert 被拒
- [ ] v2.4.0 的 326 passed 全部无回归
- [ ] webui 6 tab 在 1080p 单屏可达
- [ ] CHANGELOG.md [3.0.0] / MANIFEST.md §13 同步

---

**下一步**: 用户 OK 后, 调 `writing-plans` skill 出 TaskList, 按依赖顺序逐个执行.
