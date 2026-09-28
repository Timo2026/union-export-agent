# DEMO RUNBOOK — 公网 :8051 评委演示顺序(实链路版)

> 入口: `http://<NODE-PUBLIC-IP>:8051/`(frp → 节点 livekernel :8888)
> 真实口径: 每一步的"预期"均来自已部署实链(2026-09-26 节点验收), 价格/数字以引擎实际返回为准, 本文件不预设未实测数值。
> 演示前必读"红线": 只演示已上线实链, 不演示 WIP(见 §14)。

## 0. 演示前自检(2 分钟, 全部 200 再开场)

| # | 动作 | 入口(证据 file:line) | 预期 |
|---|------|------|------|
| 0.1 | 公网根可达 | `GET http://<NODE-PUBLIC-IP>:8051/` | 200 + SPA HTML(doctype, 非空壳) |
| 0.2 | 服务健康 | `GET :8051/health`(services/api_server.py:523) | `status ok`, 版本 `v7.1.0-livekernel`, `engine` 指向 `cnc-ai-brain:7862`, `multimodal` 指向 `127.0.0.1:8002` |
| 0.3 | 邮件拉取在跑 | `GET :8051/v1/mail/puller/status`(api_server.py:319) | `running=true`, `consecutive_failures=0`, `last_pull_at` 在推进 |
| 0.4 | inbound 扫描在跑 | `GET :8051/v1/inbound/status`(api_server.py:689) | `running=true`, `ticks` 在涨, `last_error=null` |
| 0.5 | 报价引擎在线 | health 的 `engine` 字段 / `#/status` 页 | `live:cnc-ai-brain:7862`(config/settings.yaml:11) |

**讲解点(30s)**: 全链跑在单台 NVIDIA DGX Spark(GB10)上, 公网这一条线就是评委入口; 没有任何步骤需要连外部商业 API。

## 1. 开场 — Overview(#/)

- 输入: 打开根路径, 停 3 秒让面板加载。
- 预期: 系统定位一屏读完 — 邮件询价 → 报价黄金链; 服务拓扑卡(5 服务 + 3 模型)。
- 讲解点: "这个系统解决的是外贸机加工报价流程: 客户邮件/图纸/语音进来, 系统读需求、查工艺、算价格、人工把关后出报价单。"

## 2. 英雄时刻 — 黄金链 S1(标准 RFQ → 自动报价 → DONE)

- 输入: `#/mailbox` 页眉场景条按钮 **S1**(6061 x50 + anodizing; 前端 `webui-redesign/src/views/Mailbox.tsx` `DEMO_SCENARIOS`/`runDemo`, 经 `ENDPOINTS.demoScenario` → api_server.py:562 `POST /v1/demo/scenario/S1`)。
- 预期: pending 状态机 `NEW→PROCESSING→DONE`; 邮件详情抽屉显示解析出的 RFQ(材料/数量/公差/表面处理); 报价卡显示**单价/总价/毛利率**, 报价来源标注 `cnc-ai-brain:7862`(决策点 agents/cat_controller.py:434 `self.timo.quote`)。
- 可展开证据: `POST /v1/rfq/{cid}/quote-pdf`(api_server.py:1086)/ `quote-xlsx`(1099) → 下载报价单 PDF/XLSX; `POST /v1/rfq/{cid}/crm-sync`(1164) → 落 CRM。
- 讲解点: **铁律② — 报价永远由确定性引擎裁决, 永不走 LLM**; LLM 只做意图/槽位/表达。
- 实测口径(2026-09-26 21:37 公网 E2E): 点 S1 → 列表即落 `[DEMO S1] 6061 x50 + anodizing -> DONE` 行(AL 头像 + NEW/重复投递徽标); **当天第二次跑同一场景会带"重复投递"徽标** — 内容哈希去重层的诚实标记, 演示 lease 直占不受阻, 照常讲解即可(这正是"不虚增、可追溯"的卖点)。

## 3. 诚实性 — S3(BLOCKED)

- 输入: `#/mailbox` → 场景 **S3**(304 + anodizing)。
- 预期: 状态 `BLOCKED`, 回复草稿被护栏拦截归档, **不生成报价**。
- 讲解点: 不可承诺的条件(材料+工艺冲突)不硬算, 输出侧护栏(forbidden_promise)直接拦; "宁可 BLOCKED, 不可扮全能"。

## 4. 人工在环 — S5(HITL 缺参升级)

- 输入: 场景 **S5**(TC4 + IT5)。
- 预期: 状态 `HITL`, 系统列出缺失/待确认槽位, **不自动作答**, 等人工补齐再跑。
- 讲解点: 铁律③ — PASS 之外一律不自动外发; HITL 不是失败, 是设计内的收敛路径。

## 5. 多模态英雄时刻 — M1(语音 vs 邮件公差冲突)

- 输入: 场景 **M1**(邮件 ±0.02 + 语音声称 ±0.05)。
- 预期: 状态 `HITL`, 冲突码 `VOICE_EMAIL_CONFLICT` — 系统**不静默采纳任一方**, 把两个证据并排升级人工。
- 讲解点: 语音走 Omni(:8002)音频路径(节点 `asr_mode: cli`, scripts/asr_cli.py 子进程); 冲突检测在编排层, 不靠模型自觉。
- 注: S1/S2/S3/S5/M1 五按钮 2026-09-26 已全部上线实测在位(公网 #/mailbox 页眉); 若现场个别按钮点了没反应(后端集群瞬时不可达), 口播讲解 + 展示 `/v1/mail/inbox` 历史 HITL 记录(节点已有实证)。

## 6. zip 邮件断点链 — 附件自动流转 + BOM 批量报价

- 输入(二选一):
  - A(存量证据): `GET :8051/v1/inbound/status`(api_server.py:689) 展示 `ticks`/复跑统计(节点存量 468 件已复跑);
  - B(现场触发): 把测试 zip 放进节点 `data/inbound/`(经 mailbox 发 zip 附件邮件亦可), 等 ≤30s。
- 预期: scanner 自动解包(zip-slip 拒绝/GBK 名/嵌套递归), BOM xlsx → 批量报价(OCP 几何内核), 产物向量化入 `ingest_docs`; `GET :8051/v1/rag/docs`(api_server.py:668) 文档数上涨(节点基线 475); 手动触发 `POST :8051/v1/inbound/tick`(700)。
- 讲解点: "丢一个压缩包进去就行" — 无人值守常驻 worker, 断点幂等(同 key 不重跑, 文件改动才重入队)。

## 7. 联网检索 — #/search(SearXNG lane)

- 输入: `#/search` 输入一个真实查询(如某材料牌号 + 价格)。
- 预期: 结果来自节点自建 SearXNG(:8080, 零外部 key), RAG 引用带层级标注; `POST /v1/web/search`(api_server.py:535) 同源。
- 讲解点: 检索是自建的, 不依赖任何商业搜索 API; 搜到的内容才进 RAG, 入库前过敏感词黑名单。

## 8. 图纸中心 — #/drawings

- 输入: `#/drawings` 列表 → 点开一张。
- 预期: SVG 缩略图(sha256_16 去重折叠, 同图不重复存), STEP 网格预览(`GET /v1/drawings/{id}/mesh`, api_server.py:1779), 伪 STEP 前置校验拦截。
- 讲解点: 图纸→VLM(Omni :8002)感知做过实物探针; 同名/同内容图纸自动折叠, 不虚增数量。

## 9. 推理与路由 — #/inference / #/models

- 输入: `#/inference` 看一次请求的形状(latency/tokens/模型); `#/models` 看配置与探活。
- 预期: 四角色端点(llm/vision/audio/embed)统一走 Omni + Embed-1B; fallback 链可见(llm 主端点离线 → qwen3-0.6B :8902 自动切); `GET /v1/model-router/status`(api_server.py:1207)/ `POST /v1/models/probe`(1438) 探活为 live。
- 讲解点: 单 GB10 上四角色共栈; 任何端点不可达时**显式降级并标注**, 不冒充在线(mock 必带 MOCK 标记)。

## 10. 状态页 — #/status

- 输入: `#/status`。
- 预期: 5 服务(livekernel/Timo/Omni/Embed-0.6B/SearXNG)+ 3 模型的实时拓扑, 与 `/health`(api_server.py:523) 同源数据。
- 讲解点: 可观测是一等功能 — 每个状态都可对回端点, 没有"装饰灯"。

## 11. 署名一体(可选 30s)

- 输入: `#/mailbox` 顶栏头像 → ProfileDrawer 改署名 → 看邮件落款/SMTP From 显示名同步变。
- 预期: 三处同一份 profile(`GET/POST /v1/profile`, api_server.py:376/383)。
- 讲解点: 小功能演示"单一数据源"工程观; SMTP 保持 draft_only, 不真发(铁律①)。

## 12. Agent 一步调用(可选, 评委好问)

- 输入: `POST :8051/v1/agent/task`(api_server.py:1343), body 例: `{"task": "cnc-quote", "params": {...}}`。
- 预期: OpenClaw 分发到已注册 skill(以 `GET :8051/v1/skills`, api_server.py:1297 的实际返回为准 — cnc-quote/dfm-check/email-quote 三薄桥代码在 `openclaw-skills/` 已就绪, 节点注册态演示前先查); openshell 白名单门禁外的调用被护栏拦并记因。
- 讲解点: 技能是薄桥 + 白名单, 不是"啥都能跑"; 被拦也是一次正确行为, 审计链留痕。**若该步未注册, 跳过实操改口播**, 不要现场注册。

## 13. 收尾话术(三铁律 + 四问)

1. **数据不出本机**: SMTP/IMAP/OAuth 默认禁, 回复一律 draft_only; 凭据只在节点本机。
2. **LLM 不定价**: 单价/总价/毛利全部来自 :7862 确定性内核; LLM 只判可行性与表达。
3. **人工在环**: BLOCKED/HITL 是终态不是失败; 冲突(语音 vs 邮件)升级人不静默。
4. **诚实标注**: 离线/MOCK/降级全部显式, 没有"假在线"。

## 14. 演示红线(不要碰)

| 不演示 | 原因(证据) |
|--------|-----------|
| text2cad / 自然语言生成 STEP | Q6 WIP, 6 条契约测试仍红(已知基线), 未上线 |
| OCR 档位 | N3 拍板保持 disabled; VLM 能力由 Omni lane 真实覆盖, 不重复表演 |
| reid 激活 | 未拍板, 节点未启用 |
| 任何"自动外发邮件" | 铁律① draft_only; send-reply 端点存在但默认不自动触发 |

## 15. 应急预案

| 症状 | 处置 |
|------|------|
| 页面 200 但白屏 | 缓存问题: 硬刷新(cache-bust); 资产走 `/B` 前缀挂载(api_server.py), 别信节点本机 curl(节点本机无 :8051, 空转假绿) |
| 场景按钮转圈超 2min | 后台 orchestrator 抢先 claim → 演示端点只等 120s 终态, 等不到回 "未落定"(2026-09-26 S3 实测: toast 报 timeout, 数秒后邮件仍落 BLOCKED 行 — 后台集群慢, 非链路坏); 等 ≤25s 自动刷新, **终态以 `/v1/mail/inbox` 为准**, 不要重复点(api_server.py:613 逻辑: 等终态不重复跑) |
| 引擎超时 | 检查 `#/status` engine 卡; 报价失败会显式报错, **不要**口头编价格 |
| 全场异常 | 先恢复公网再排查(用户口径: 评委要看到); 重启只能 `node_services.sh restart livekernel`, 禁裸 pkill |

---
证据基线: 2026-09-26 节点 spark-388d 公网 E2E(根/status/inbound/rag search 全 200, puller 0 失败, 回填 476→567/100s 推进; V4 补 demo 场景按钮后 21:37 公网实测: `#/mailbox` 五按钮在位, 点 S1 落 DONE 行, bundle index-Et7PRzSV, 回滚点 webui-dist.bak.v4demo-260926213602)。本地回归基线 6 failed(text2cad Q6 WIP)/1525 passed。路由行号以 services/api_server.py 当前工作树为准。
