# SKILLS.md — Agent Skills 全景与护栏模型

## 一、Skill 体系（两套，各司其职）

### A. livekernel 业务 Skill（39 目录 · NemoClaw 标准）
每个 skill = `SKILL.md`（frontmatter: name/description/触发词——**路由表不是百科**）+ `tool.py:run()`（OpenAI Function Calling 契约）+ `__init__.py` + 可选 `evals/evals.json`（含负向用例）。

| 族 | 成员（节选） |
|---|---|
| 黄金链 (8) | parse-rfq · extract-specs · check-dfm · calc-quote · verify-gate · write-reply · golden-chain · cnc-quote |
| 专家/编排 (8) | fleet-coordinator · material/price/dfm-expert · quality-loop · orchestrator · ceo-decision · reid-os |
| 飞轮 (4) | customer-flywheel · quote-calibration · customer-health · retention-alert |
| RAG/尽调 (5) | rag-ingest · quote-correction · rag-search · reid-triage · search-reid |
| 策展知识 (5, Item6) | material-knowledge · dfm-rules · process-knowledge · sop-router · reid-triage |

**六触点注册**：SKILL.md frontmatter + tool.py + config/skills.yaml + config/skill_registry.yaml + guardrails.TOOL_ALLOWLIST + openshell/skill-allowlist.yaml

### B. OpenClaw 平台技能（47 个，11 完全可用）
NVIDIA 栈技能（nemotron-customize / nemo-retriever / jetson-* 等，官方 Skill 保持原样不改动——签名纪律）+ union 桥接技能（cnc-quote-system / email-quote / dfam-check）。

## 二、护栏模型（四层）
| 层 | 机制 |
|---|---|
| OpenShell | 4 策略：iron-rule-1（确定性输出 sha256 锁，**输入指纹分键**）· hitl-required · local-only · skill-allowlist |
| Guardrails 三段 | input（中英注入/凭据提取 BLOCK）→ tool（白名单外 BLOCK）→ output（违禁承诺 REVIEW_AND_NO_SEND，连字符变体已堵） |
| 铁律① | DETERMINISTIC 永锁 Timo——换任何 LLM 后端报价 byte-identical |
| HITL 分诊 | verify_gate 五步（辟牟援推止）· 超时升级不代审 |

## 三、负向触发矩阵（技能工程分水岭）
`POST /v1/guardrails/check` 实弹验证：注入 BLOCK · 越权工具 BLOCK · 违禁承诺 force_no_send；evals 必含"**不该触发**"的负向用例（对齐 NVIDIA AgentSkills evals 规范）。
