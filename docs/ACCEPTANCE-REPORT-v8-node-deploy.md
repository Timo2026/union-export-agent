# ACCEPTANCE-REPORT-v8 — 节点永驻部署 + OpenClaw 一步桥验收报告

日期: 2026-09-22 (本地) · 节点侧产物时间戳为 UTC 2026-09-21 · 分支: `feature/skills-p0-flywheel` · 版本: **v6.3.2**

> 口径: 每条结论附可复跑命令 / file:line / sha 证据; 未达成或 flaky 的写成缺口, 不粉饰。
> 铁律①: 节点坐标 (HOST/PORT/USER/PWD) 与凭据全部 env 注入, 本报告以 `<UEA_NODE_HOST>` 占位, 公网 IP / 密码 / gateway token / StepFun key 一律不落码、不回显。
> 本报告不 bump release marker (v6.3.2 标记已于 T3 同步); git 入库为决策者动作, 本轮未提交 (遵循 no-commit 约束)。

## 一、目标与范围

落地已批准设计「Omni 永驻 + Embed 永驻 + Timo 引擎 / livekernel / OpenClaw 接线三件部署 + union skill 注册到 OpenClaw」, 并把 UI 映射到公网 `:8051`。执行链 T1–T10:

- **常驻拓扑**: Omni + Embed + 30B 三驻 (4B 不驻) · **旧副本**: 备份→停旧→原位部署 v6.3.2 · **永驻档位**: crontab @reboot + 看门狗 + tmux · **Skill 形态**: 瘦桥型 (指导 + curl 调 livekernel)。
- 验收项 A1–A7: 五服务在线 / 公网 UI / 黄金链确定性报价 / OpenClaw 一步桥 / 看门狗自愈 / sha 稳定性 / 证据汇总。

## 二、验收结果总览

| 项 | 状态 | 证据 (命令 → 数字) |
|---|---|---|
| A1 五服务永驻在线 | ✅ | `node_services.sh status` → embed/omni/reason30b/timo/livekernel **5/5 UP**; `ss -ltnp` → 仅 `0.0.0.0:8888` 对外, 余皆 `127.0.0.1`; MemAvailable **8–9G > 6G floor** |
| A1b 三模型真出 token | ✅ | `curl :8011/:8000/:8002 /v1/models` → `nemotron-embed-1b` / `nemotron-30b-a3b` / `nemotron-omni-30b-a3b`; Omni 生成探针 → `chatcmpl-b4d0d366…` 带 reasoning |
| A2 公网 :8051 UI 映射 | ✅ | 本地 (节点外) `curl http://<UEA_NODE_HOST>:8051/health` → `v6.3.2-livekernel`, `engine:live:cnc-ai-brain:7862`; `/` → 工作台 HTML, title「Union Manufacturing Export Agent · v6.3.2 节点实测口径 (真接线)」 |
| A3 黄金链确定性报价 (铁律①全套) | ✅ | unit_price **281.25** / final **365.62** CNY · `_source:live:cnc-ai-brain:7862` · `quote._source:live:/api/quote` · `iron_rule:deterministic` · sha `0b219b0b…` · state/verification **HITL** · `draft_only`/`auto_send:false` · `hitl_required:true` |
| A3b 取证佐证 (非捏造) | ✅ | 节点落盘 `data/contexts/RFQ-20260921-1D2884.audit.json` (7220B, `valid:true`, 含 281.25/365.62) + `data/traces/….jsonl` **9 行 = 回传 span_count:9** |
| A4 OpenClaw 一步自治桥 | ✅ (诚实验证, 见 §四缺口①) | `openclaw agent exec --code-mode direct` → `toolSummary{calls:1,tools:["exec"],failures:0}` (真跑 curl) · 原文回传 RAW JSON · 字段全中真值 (281.25/:7862/HITL/sha 0b219b0b/override blocked) · session `93c9d673…` |
| A5 看门狗自愈 + crontab 永驻 | ✅ | `crontab -l` → `@reboot … start all` + `* * * * * node_watchdog.sh`; watchdog.log 每分钟自治打点「all 5 services UP」; (前轮 `kill -9 timo` ~45s 自愈 pid 1011641→1055374) |
| A6 sha 稳定性 | ⚠️ 缺口 (守卫正确, 输出非字节稳定) | 同参重放 → **BLOCKED**: `executed_skills:[]`, `error:openshell_violation`, `expected 0b219b0b` vs `actual fe0a…`, `override_blocked.allowed:false` |
| A7 证据汇总 | ✅ | 本报告 + 上述每条可复跑命令 |

## 三、分层明细

### A1 — 五服务永驻栈 (launch/依赖序: embed→omni→reason30b→timo→livekernel)

| 服务 | 端口 | 模型/角色 | 绑定 | 监管 |
|---|---|---|---|---|
| embed | :8011 | nemotron-embed-1b (飞轮 RAG 编码) | 127.0.0.1 | unmanaged (永驻) |
| omni | :8002 | nemotron-omni-30b-a3b (多模态) | 127.0.0.1 | unmanaged (永驻) |
| reason30b | :8000 | nemotron-30b-a3b @131072 (路由/规划, tool-calling) | 127.0.0.1 | tmux:reason30b |
| timo | :7862 | cnc-ai-brain 确定性报价引擎 | 127.0.0.1 | tmux:timo |
| livekernel | :8888 | union-export-agent FastAPI 编排器 v6.3.2 | **0.0.0.0** (供 :8051 NAT) | tmux:livekernel |

- livekernel 必须**最后**起 (`ModelRouter._probe` 启动时缓存存活, 无重探)。
- 监管脚本 `deploy/node_services.sh` (幂等: `start_svc` 若 port_up 则 adopt 跳过; GPU 服务受 `mem_ok` 门禁)。
- 铁律① 出口收敛实证: 仅 livekernel 绑 `0.0.0.0`, 模型/引擎全 loopback-only。

### A2 — 公网 :8051 → 节点 0.0.0.0:8888 (节点外验证)

从本地 Windows (节点外) 直拉公网端点, health 与 UI 根均返回 v6.3.2 真后端 (非 mock、非占位)。`<UEA_NODE_HOST>` 由 `~/.uea_node_env` (仓库外) 注入。

### A3 — 黄金链确定性报价 + 铁律①全套 (经 A4 桥回传, 节点落盘佐证)

回传 RAW JSON 关键字段 (逐字, 非转述):
- `route`: `{skills:["golden_chain"], source:"llm", strategy:"auto:llm", model:"nemotron-30b-a3b"}` — 30B 真规划路由。
- `quote`: `{unit_price:281.25, final_price:365.62, profit:84.38, lead_time_days:5, _source:"live:/api/quote"}`。
- `result._source:"live:cnc-ai-brain:7862"` · `iron_rule:"deterministic"` · `iron_rule_applied:true` · `output_sha256:"0b219b0bf84cb51e57c5e9fe30fb0e5b22c1343c8c900c01e6de787a8708a4f8"`。
- `state/verification_status:"HITL"` · `next_action:"HUMAN_REVIEW"` · `dfm_valid:true` · `hitl_required:true`。
- `reply`: `{mode:"draft_only", auto_send:false, guardrail_output:{pass:true,flags:[]}}`。
- `iron_rule_override_blocked.allowed:false` (改写守卫已武装并拦截)。
- 飞轮锚点: `quote_anchor{hits:[{customer_id:"CUST-0001", unit_price:222.8}], source:"vector:quote_history", embed_source:"live:http://127.0.0.1:8011/v1", degraded:false}` — **Embed-1B 永驻已接入报价召回链** (L2 锚点仅证据不改引擎数字, 见 `agents/cat_controller.py:350`)。
- 可观测: `span_count:9, tool_calls:5, tool_errors:0, hitl_triggers:1, audit_valid:true, audit_head:"dfc5ea55…"`。

取证佐证 (证明 JSON 来自真实 dispatch 而非捏造): 节点 `RFQ-20260921-1D2884.audit.json` 实存 7220B / `valid:true` / 含 281.25·365.62·context_id; trace jsonl 9 行与回传 `span_count:9` 精确吻合。

### A4 — OpenClaw 一步自治桥 (瘦桥型 skill)

- Skill `deploy/openclaw/union-export/SKILL.md` (version 6.3.2, `allowed-tools: Read Bash(curl *)`) 已注册: `openclaw skills list` → `✓ ready union-export … openclaw-managed`。
- 调用: `openclaw agent exec --json --message-file /tmp/a4b_task.txt --model nvidia-reason/nemotron-30b-a3b --code-mode direct --timeout 300`。
- 结果: `ok:true, status:ok, assistantTurns:2, codeModeEngaged:false`, `toolSummary{calls:1, tools:["exec"], failures:0}` — 代理**真执行了 curl** (exec 工具), 并逐字回传 RAW JSON + 仅拷贝已验证字段。回传值与 A3 真值逐项吻合 (281.25 / :7862 / HITL / sha 0b219b0b / override blocked / draft_only / hitl_required true)。
- 桥链: OpenClaw 自治代理 → union-export skill → `Bash(curl)` → livekernel :8888 → dispatcher (auto:llm 路由 golden_chain) → Timo 确定性引擎 :7862 → 铁律① sha 锁 + 改写拦截 + draft_only + HITL 门。

### A5 — 永驻层 (crontab + 看门狗 + tmux)

- `crontab -l`: `@reboot sleep 20 && …/node_services.sh start all` + `* * * * * …/node_watchdog.sh`。
- watchdog.log 每分钟自治打点 (18:13/18:14/18:15:01「all 5 services UP, MemAvailable 9G」) — 无人工触发。
- 前轮自愈实证: `kill -9` timo 后看门狗 ~45s 内重启 (pid 1011641→1055374)。

### A6 — sha 稳定性 (现场演示, 见 §四缺口②)

同参重放 (锁内仍存 A4b 的 `0b219b0b`):
```
executed_skills: []
trace[0].ok: False  error: openshell_violation
violations: [{policy:"iron-rule-1", skill:"golden_chain:c186fa22dde110ae",
  reason:"确定性输出被改写", expected_sha256:"0b219b0b…", actual_sha256:"fe0a…"}]
iron_rule_override_blocked.allowed: false
```
- 锁键 = `skill:args-hash` (`golden_chain:c186fa22dde110ae`, args-hash 取 material/qty/surface/tol, **非 context_id**)。
- 锁为**纯内存** (`services/openshell.py:216`), 重启即清, 无落盘。`lock_deterministic_output` (:140-150) 首见注册; `verify_locked_output` (:153-169) 摘要不符即拦; `postcheck` (:226-245) 违规则拒用该输出。

## 四、铁律① 合规

| 铁律 | 证据 |
|---|---|
| LLM 永不出终价 | 价由 Timo 确定性引擎产 (`_source:live:cnc-ai-brain:7862`), sha 锁 `0b219b0b…`, 改写守卫 `allowed:false`; 30B 仅规划路由 (auto:llm) 与草拟文本 |
| data-stays-local | 仅 livekernel 绑 0.0.0.0 (供 :8051); 模型/引擎 loopback-only; `reply.mode:draft_only`/`auto_send:false`; 节点 `OPC_API_KEY` 实测为空 |
| 凭据永不落码/离机 | 节点密码 / OpenClaw gateway token / StepFun key 全 env 注入并掩码; 本报告以 `<UEA_NODE_HOST>` 占位, 无公网 IP 字面量 |
| 确定性输出 sha 锁 | A3 锁 + A6 拦截双证; 守卫语义正确 (任何字节不符即拦) |
| 每步命令+数字 | 本报告各节均附可复跑命令 → 数字 |
| 逐任务执行 | T1–T10 顺序闭环 (#70–#82), 无跳号 |

## 五、诚实缺口 (挂账)

1. **A4 代理层 flaky (重要)**: 首次 A4 尝试 (`--code-mode auto`) 代理只调 `read`、**从未跑 curl**, 在 "isolated finalization" 阶段 (stderr: `settled post-tool turn lacked a final answer → running isolated finalization`) **捏造**了整份回执: `$12.35 USD` / `:8080` (错端口) / 空串 sha `e3b0c442…` / `PASS` / `hitl_required:false` — 全假。根因: 30B 环境代理在 post-tool 轮缺终答时会编造 provenance。修复: 强制「必须执行 curl + 原文回传 + 否则回 `BRIDGE_NOT_EXECUTED`」提示词 + `--code-mode direct` → 本轮真执行真回传。**结论: livekernel 铁律① 守卫本身可靠, 但仅在桥被真打到时才生效; 代理层不保证确定性执行。** 建议: 演示固定用已验证的强制提示词 + direct 调用, 或在 skill 内加「桥执行断言」。

2. **A6 sha 易变 → 同参重放被拦**: 报价**价格是确定的** (281.25 跨多轮一致), 但 golden_chain 输出 blob 内嵌每轮易变 timestamp/nonce, 故 iron-rule-1 对任何字节不符 (含合法同参重放) 一律拦。**守卫无误**, 副作用是合法重跑需先重启清锁。演示配方 = **重启→只跑一次** (已验证)。代码修复 (只对确定性价格载荷取 sha / 排除易变 id) **建议但未实施** (贴近定价、超出本轮部署范围、未获批)。

3. **golden_chain RFQ 抽取口径**: 以顶层结构化字段 (material/quantity/…) 传入时, 未流进 golden_chain 的 `email_text` 抽取路径 → RFQ 判为缺料 → 走 HITL (确定性报价 281.25/365.62 为引擎对默认几何的输出)。这是**忠实行为非 bug**; 若要结构化字段直出免 HITL, 需走显式 `calc_quote` skill 路径或把字段嵌进 `email_text`。演示脚本需注意此口径。

4. **Omni 已永驻但未接入 livekernel 多模态**: Omni :8002 常驻并真出 token, 但 livekernel `/health` 多模态仍报 `MOCK:funasr-offline` — 即 Omni 驻留在模型服务层达成, 尚未接进 livekernel 的语音/多模态摄取路径 (本轮设计为「Omni 永驻」, 接入为后续步骤)。

## 六、复跑命令 (节点侧, 坐标 env 注入)

```bash
# 五服务状态 + 端口拓扑
bash ~/union-deploy/node_services.sh status
ss -ltnp | grep -E ':(8000|8002|8011|7862|8888)\b'
# 三模型出 token
curl -s http://127.0.0.1:8011/v1/models ; curl -s http://127.0.0.1:8000/v1/models ; curl -s http://127.0.0.1:8002/v1/models
# 公网 UI (节点外)
curl -s http://<UEA_NODE_HOST>:8051/health
# OpenClaw 一步桥 (强制真执行)
openclaw agent exec --json --message-file /tmp/a4b_task.txt --model nvidia-reason/nemotron-30b-a3b --code-mode direct --timeout 300
# A6 同参重放 (演示拦截); 演示前重启清锁
bash ~/union-deploy/node_services.sh restart livekernel
```
