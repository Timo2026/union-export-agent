# 实测评估 · UI / 后台 / Omni 模型 联动与真实数据

| 字段 | 内容 |
|------|------|
| 日期 | 2026-09-21（公网实测；节点进程级 SSH 本回合未完成则明示） |
| 目标 URL | `http://203.0.113.10:8051/webui?cachebust=tabs2` |
| 方法 | HTTP 全端点探测 + 黄金链真实 intake + 附件上传 + traces + model probe；**禁止绕过** |
| 口径 | 只写实测；router 与 probe 不一致处**以 probe 为准** |

---

## 0. 结论先行

| 判定 | 说明 |
|------|------|
| **UI ↔ 后台：已接线** | `:8051` 控制台 v6.3.2-fusion，13 标签；`/health`、`/docs`、`/v1/*` 均 200 |
| **后台 ↔ 确定性引擎：强联动** | `live:cnc-ai-brain:7862`；报价 `quote_source=live:/api/quote`；DFM `live:/api/conflict-check` |
| **Omni 为主多模态：真在线** | VISION/ASR/OCR 角色统一 `nemotron-omni-30b-a3b` @ `127.0.0.1:8002/v1`；图片上传 `_source=live:vlm:127.0.0.1:8002` |
| **Embedding：真在线** | `nemotron-embed-1b` @ `:8011`，probe 200 |
| **LLM 30B：当前离线** | `:8000` **Connection refused**；Skill 路由 `llm_error=llm_offline` → 规则兜底 |
| **状态总线有脏数据** | `/v1/model-router/status` 显示 FAST/REASON **online**，与 probe **矛盾** |
| **真实数据存在** | 邮件 9 封 DEMO S1–S5/M1，状态 DONE/HITL/BLOCKED；飞轮客户多枚；trace/span 完整 |
| **`:9051` 不是模型网口** | 实测 **Jupyter Server**；不能当 OpenAI `/v1` 公网入口 |

**一句话**：控制台与后端、Timo 引擎、**Omni 多模态**已形成可用闭环；**文本 LLM 档（30B）未驻留**，且 **router 在线位图不可信**——「以 Omni 为主」成立，「全模型已上线」不成立。

---

## 1. 入口与 UI 层

| 项 | 实测 | 判定 |
|----|------|------|
| `GET /webui?cachebust=tabs2` | **200**，HTML ~188KB，`title=Union Export Agent · 控制台` | ✅ 在线 |
| 副标题 | `v6.3.2-fusion · 节点实测口径 (Omni/Embed/30B 三驻) · 13 标签/69 端点 · GB10…` | 🟡 文案称「三驻」，**30B 实测未驻留** |
| 标签页（13） | models, demo, endpoints, threeD, rag, feedback, skills, workbench, mailbox, v12, rfq, flywheel, ops | ✅ |
| UI fetch 面 | `/v1/models/config` `/v1/models/probe` `/v1/rfq/*` `/v1/upload/*` `/v1/skills/config` `/v1/agent/*` `/v1/feedback*` `/v1/rag/*` `/v1/mail/*` `/v1/flywheel/*` `/v1/cache/stats` `/health` | ✅ 与后台对齐 |
| `GET /docs` | 200 | ✅ Swagger |
| `GET /api/health` | **404** | ❌ 正确路径是 `/health` |
| `GET :9051/` | **Jupyter Server** | ❌ 非模型网关 |
| `GET :9051/v1/models` | 404 | ❌ 公网无 LLM OpenAI 口 |

### UI–模型关系（`/v1/models/config`）

| 角色 | 模型 ID | Endpoint | enabled | 语义 |
|------|---------|----------|---------|------|
| LLM/REASON/FAST | nemotron-30b-a3b | `:8000/v1` | true | 30B-A3B；FAST=REASON 同档 |
| VISION | **nemotron-omni-30b-a3b** | `:8002/v1` | true | 只出事实不定价；兼 OCR |
| ASR | **nemotron-omni-30b-a3b** | `:8002/v1` | true | Omni 音频路径 |
| OCR | 同 Omni | `:8002` | **false** | 显式 disabled，由 VLM 覆盖 |
| EMBED | nemotron-embed-1b | `:8011/v1` | true | query:/passage:；失败 Hash MOCK |
| DETERMINISTIC | calc_quote+ConflictChecker | `:7862` | locked | 铁律① |

**结论**：配置上 **Omni 主 VISION+ASR**，符合「以 omni 为主」；文本/向量是 30B + Embed-1B，不是 Omni 全包。

---

## 2. 后台 health

`GET /health` → 200：

```json
{
  "status": "ok",
  "service": "union-export-agent",
  "version": "v6.3.2-livekernel",
  "engine": "live:cnc-ai-brain:7862",
  "multimodal": "live:127.0.0.1:8002",
  "contexts": 2
}
```

| 字段 | 判定 |
|------|------|
| engine live:7862 | ✅ Timo 在线 |
| multimodal live:8002 | ✅ Omni 面在线 |
| contexts:2 | ℹ️ 与 mail 9 条计数口径不同 |

---

## 3. 模型探测 vs 路由表（必须对齐）

### 3.1 `POST /v1/models/probe`（真探测 · 以此为准）

| 角色 | model | online | 延迟 | 证据 |
|------|-------|--------|------|------|
| llm | nemotron-30b-a3b | **false** | 0.2ms | ConnectionRefused @ :8000 |
| **vlm Omni** | nemotron-omni-30b-a3b | **true** | 1.3ms | 200 @ :8002 |
| embedding | nemotron-embed-1b | **true** | 0.9ms | 200 @ :8011 |
| ocr | omni | skipped disabled | — | 诚实关闭 |
| **asr Omni** | nemotron-omni-30b-a3b | **true** | 0.7ms | 200 @ :8002 |
| deterministic | Timo | **true** | 1.6ms | 200 |

### 3.2 `GET /v1/model-router/status`

`online_roles` 含 FAST/REASON 且 `online:true`（`:8000 nemotron-30b-a3b`）——与 probe **冲突**。

| 点 | router | probe | 判定 |
|----|--------|-------|------|
| LLM/FAST/REASON | online | **refused** | **假绿灯** |
| VISION/ASR Omni | online | online | 一致 ✅ |
| EMBED | online | online | 一致 ✅ |
| DETERMINISTIC | online | online | 一致 ✅ |

**禁止绕过结论**：状态面脏数据会误导 UI/评委，必须与 probe 同源。

---

## 4. 功能联动（真实数据）

### 4.1 邮件 → 黄金链

`GET /v1/mail/inbox` → **9 封**：

| mail_id | state | context_id | driver |
|---------|-------|------------|--------|
| DEMO-S1 | **DONE** | RFQ-20260922-DF8717 | email |
| DEMO-S2 | DONE | RFQ-20260922-05F7E6 | email |
| DEMO-S3 | **BLOCKED** | RFQ-20260922-E6089A | email |
| DEMO-S4 | DONE | RFQ-20260922-D77AD5 | email |
| DEMO-S5 | **HITL** | RFQ-20260922-BB695E | email |
| DEMO-M1 | DONE | RFQ-20260922-CBC849 | email |

→ 三态分流真实存在。

### 4.2 报价上下文 RFQ-20260922-DF8717

| 字段 | 值 |
|------|-----|
| verification | PASS · state DONE |
| reply | draft_only · auto_send=false · quote_source **live:/api/quote** |
| quote | unit_price 222.8 · final_price 9413.3 |
| dfm | live:/api/conflict-check |

### 4.3 Trace span 链

```
agent_run → guardrail:input → skill:rfq-extraction
  → skill:dfm-conflict (live:/api/conflict-check)
  → skill:cnc-quote (live:/api/quote, 12.09ms)
  → skill:freight-customs → schema:validate → skill:verification → PASS
```

纯文本询盘 **无 omni span**（合理）；Omni 证据见上传。

### 4.4 Intake

`POST /v1/rfq/intake` form `email_text+customer+country` → **200** 新 `RFQ-20260922-1F358A` PASS。  
JSON 错字段 → 400「需要 email_file 或 email_text…」。

### 4.5 Omni 真调用（图片）

`POST /v1/upload/image` → 200：

- `_source` = **`live:vlm:127.0.0.1:8002`**
- `_mock` = **false**
- perception = 中文事实（纯色图、无零件标注…）→ **不定价**，符合契约。

### 4.6 STEP（引擎权威）

`POST /v1/upload/step` → 200：OCP B-rep bbox/volume/weight；features C1 失败已标注；**非 Omni**，分工正确。

### 4.7 Skill 调度

`POST /v1/agent/task`：

- route `rules` + **`llm_error=llm_offline`**
- planned 含 **check_dfm**，executed **无 check_dfm**（静默跳过）
- calc_quote 带 iron_rule + sha256

### 4.8 飞轮 / 缓存

- flywheel customers 多条 `quote_count≥1`
- cache hits/misses 有数

---

## 5. 治理 OpenShell

- iron-rule-1 **enabled + locked**
- hitl / local-only / skill-allowlist enabled
- 策略区 violation_count=0；audit 流有历史 `violations:2`（console driver）——分层表述，勿混谈
- 外发 draft_only / auto_send=false 与铁律一致

---

## 6. 问题清单（禁止粉饰）

| ID | 严重度 | 问题 | 影响 |
|----|--------|------|------|
| **P0-1** | 高 | **LLM :8000 refused**（30B 未驻留） | 文本规划/抽取实际靠规则；「三驻」不实 |
| **P0-2** | 高 | **router 与 probe 假一致**（假 online） | UI/驾驶舱误导 |
| **P1-1** | 中 | dispatch **check_dfm 计划有、执行无** | chat 路径 DFM 可能未跑 |
| **P1-2** | 中 | 公网 **无** OpenAI `/v1`（:9051=Jupyter） | 外部客户端不能直连模型 |
| **P1-3** | 中 | `/api/health` 404 | 文档路径错误 |
| **P2-1** | 中低 | 副标题「30B 三驻」vs 实测 | 口播越级风险 |
| **P2-2** | 中低 | 独立 OCR disabled（Omni 覆盖） | 需讲清 |
| **P2-3** | 低 | health contexts:2 vs mail 9 | 口径未文档化 |
| **P2-4** | 低 | guardrails body 需 `text` 字段 | 调用方 schema |
| **P2-5** | 低 | STEP features C1 失败 | 几何主路径仍 OK |
| **P3-1** | 信息 | SSH BatchMode 密钥登录失败；需 env/脚本凭据 | 节点 `ps` 级证据待补 |

---

## 7. 「以 Omni 为主」总评

| 维度 | 判定 |
|------|------|
| 配置主轴 | ✅ VISION+ASR 全是 Omni |
| 运行实证 | ✅ live:vlm:8002 非 mock |
| 文本主链 | 🟡 30B down → 常走规则 |
| 向量 | ✅ Embed-1B 并行，分工正确 |
| 价格/DFM | ✅ Timo，与 Omni 切割正确 |
| 口播 | **N1+**（多模态实跑）；不可说「三模型齐驻」 |

联动完整度（实测）：

```
UI/接口 ████████░░  Omni 多模态 █████████░  Embedding ███████░░
文本LLM ██░░░░░░░░  Timo 引擎  █████████░  邮件黄金链 █████████
Skill   ███████░░░  状态一致性 ███░░░░░░░  治理铁律   █████████
```

---

## 8. 测试与真实数据索引

| 测试 | 结果 |
|------|------|
| UI webui | 200 |
| /health | engine+omni live |
| /v1/models/probe | Omni/Embed/Timo ✅ · **LLM ❌** |
| /v1/models/config | Omni 主多模态 |
| /v1/model-router/status | 与 probe **冲突** |
| /v1/mail/inbox | 9 封三态 |
| /v1/rfq/DF8717 | PASS 价 draft_only |
| /v1/traces/DF8717 | skill 链 |
| POST intake form | 200 |
| POST upload/image | live:vlm:8002 |
| POST upload/step | OCP B-rep |
| POST agent/task | rules + llm_offline；check_dfm 跳过 |
| /v1/flywheel/customers | 真实客户 |
| /v1/agent/openshell | iron locked |
| :9051/v1/models | ❌ Jupyter |

**未覆盖（明示）**：Omni 音频上传全链、RAG 全链、SSH 进程列表、30B 冷启动质量、SMTP。

---

## 9. 必修顺序

1. 拉起或诚实下线 **30B (:8000)** 并改副标题  
2. **router 与 probe 同源**  
3. **check_dfm 强制或显式 skip 原因**  
4. 文档统一 `/health`；标明 :9051=Jupyter  
5. 口播：可说 Omni 多模态实跑；不可说三模型三驻  

---

## 10. 一句话

> **UI 已接后台，报价走 Timo 真引擎，多模态走 Omni 真端点；但文本 30B 离线、路由表假绿、调度丢 DFM——主链真、状态面脏，修这三处才算全链可信。**
