# TEN-DAYS · 十日开发路径与坑（工程交付版）

> **定位**：`docs/delivery/NVIDIA-STACK-AND-MODEL-CHOICE.md` 第四节「十日开发路径与坑」的**展开版**，同时是 PPT 第 10 页（十日路径）与 8 分钟演讲「踩坑与修复 1.5min」段落的**素材底稿**。
> **本文件**：`docs/TEN-DAYS.md`（README 仓库结构所列条目，本次补上实体）；比赛评审侧同名件为 `盘点汇总/交付包/09-十日开发稿-TEN-DAYS.md`。
> **口径权威**：数字以 `docs/PRD-MASTER-UEA-DELIVERY.md` v2.0 + 2026-09-26/27 节点实测为准；与历史时点数字冲突处，见本稿 §1 口径表与 §6 勘误。
> **与另两份历程文档的关系**：`docs/十日谈.md` = 里程碑叙事简版（M0–M8，战略视角）；`docs/DECAMERON.md` = 长卷文学版（四日实战 + 六日叙事延展，写到 09-20 凌晨）；**本稿 = 工程交付版**（D1–D10 + 赛前，覆盖到 09-27，逐坑给修法与锁定方式）。三份并存，不互相覆写。
> **脱敏**：全文不含公网 IP、密码、真实邮箱账号；节点以 `spark-51 / spark-388d` 内网名指代，公网入口只写「:8051（frp 映射）」。
>
> **路径说明（主仓副本）**：本仓 `docs/` 尚未同步 `delivery/` 子目录与 `deploy.ipynb`；文中指向 `docs/delivery/*` 与 `docs/deploy.ipynb` 的引用以**开源交付包**为准（`盘点汇总/github-package/docs/`，该副本已含全部引用目标）。

---

## 0. 怎么读这份稿

三句话：

1. **十日做了两件事**——把「一封询盘邮件」变成「一份可审计的报价对象」，再把这件事搬到 GB10 上真跑起来并留下证据。
2. **十日修了 33 个坑**（§4 全清单，全栈/选型稿写「20+」，本稿逐条展开编号 K01–K33），每一条都有测试、配置或留档锁定，没有一条靠「下次注意」。
3. **十日的真正产物不是功能数，是口径**：同一个报价 byte-identical 可复现、同一份文档四处版本号对得上、同一句「全绿」能给出确切命令与环境。

评委三刀 → 本稿对应位置：

| 评委问 | 翻到哪 |
|---|---|
| 价格谁生成的？ | §3 D1（byte-identical 契约）、§5 坑一（铁律①锁的误报与根治） |
| 用了哪些 NVIDIA 技术、在哪跑的？ | §3 D4（GB10 节点对齐 + 全栈配置）、§1 口径表 GPU 行 |
| 换了后端生意还在不在 / 你们踩过什么真坑？ | §5 三个坑（含演讲话术）、§4 全清单、§6 诚实边界 |

---

## 1. 数字口径表（先锁口径，再讲故事）

| 维度 | **当前权威（09-27）** | 历史时点（保留不覆写） | 已作废 / 勘误 |
|---|---|---|---|
| 测试（节点全量） | **1070 passed / 26 failed / 6 skipped**（26 条逐簇定性为环境依赖，§6） | 700 passed / 45 skipped（09-21 ARM 首轮）· 1060/36（09-27 修前） | ~~34 failed~~（D6 清理）· ~~36 failed~~（D8 修 10 条过时断言后转绿） |
| 测试（本地全量） | **1595 passed**（D7 口径） | 758（09-21）· 725（09-20 晚复跑） | ~~701 passed~~（09-20 凌晨时点，DECAMERON 正文保留）· ~~「6 failed / 1525 passed」~~（Z10 实测证伪，§6） |
| Skill | **38 注册 / 79 运行时可调用**（`skills/` 39 目录，含 1 个 stage 提案 text2cad） | 33（09-20）· 30（09-19）· 25（09-19 早）· 18 → 17 → 11 | — |
| 知识库 RAG | **475 篇入库**；`quote_history` 向量 **1355 条**（回填追平，> eligible 1354） | 7 篇（09-25 生产库探针清理后） | ~~quote_history = 0~~（09-26 早，输出侧断链，K24） |
| 上下文留痕 | 节点 `/health` contexts **4,986**（真实磁盘计数，持续增长） | 4,364 → 4,372（09-26） | ~~contexts 恒 0~~（B4，已修） |
| 邮件 | **130 封**真实邮件自动处理（09-27 口径） | 78 封（09-26）· 74 封 · 14 封（QQ 首连） | pending 124：HITL 8 / DONE 38 / SKIPPED 76 / BLOCKED 2 / FAILED 0 |
| 客户飞轮 | **66 客户 · 3,530 报价**（工作台口径） | stats total_quotes=3464（B2 修复后） | ~~total_quotes=0~~（键名脱节，K25）；仓库盘点另有 crm 5,874 条 RFQ/报价、71 客户（含非飞轮租户，两个口径不混用） |
| RAG 检索性能 | **3 并发 P50 224ms / max 392ms**；串行 P50 181ms | P95 **15,222ms**（09-26 压测，修前） | 提升约 40 倍，根因见 K21 |
| GPU 推理 | GB10 · CUDA 13.0 · torch 2.11.0+cu130 · vLLM 0.20.0 · **~77 tok/s**（Qwen3-0.6B bf16，Triton JIT 已破解） | 62.6 tok/s（09-20 上午首通） | ~~「Triton 缺头文件暂阻」~~（CPATH 双路径已解，K13） |
| 模型矩阵 | Omni-30B NVFP4（21GB 磁盘 / 66.2GB 显存）+ Embed-1B（1.8GB）+ Qwen3-0.6B fallback（6.7GB），余 ~23GB 跑全套服务 | 三驻分层方案（Nano-4B / 30B / Omni / ASR 专档） | ~~30B 与 Omni 同驻~~（KV cache 分配 crash-loop，watchdog 22 次重启，K12）；~~nv-embedqa~~、~~GGUF 主路径~~、~~NIM 容器线~~（§6） |
| 版本 | **v7.1.0-livekernel** | v2.0.0 → v2.4 → v3.0.1 → v4.0 → v5.0 → v6.0 → v6.1 → v6.2(WIP) → v6.3.0/1/2 → v7.0.0 → v7.1.0 | ~~版本三套不一致~~（health v5.1 / UI v6.0 / FastAPI 2.0，K05） |
| 开源交付包 | `github-package/` **687 文件 · 319 py · 125 md · 105 png · 48MB**（09-27 复测；含 docs/ 33M 资产 + webui-dist 6.0M），脱敏两轮复扫清零 | 首报 683 文件 / 37MB（SFTP 拉取包体积，未计完整 docs 资产） | — |

**单一来源纪律**：skill 数字来自 `scripts/count_skills.py`；版本标记六处同步（README / 根 index.html / 控制台副标题 / api_server version+health / MANIFEST / CHANGELOG）； contexts 来自 `/health` 真实磁盘计数，不写估算。

---

## 2. 十日总览

| 日 | 日历落点 | 里程碑 | 版本 | 坑号 | 当日量化 | 证据 |
|---|---|---|---|---|---|---|
| D1 | 09-17 | PRD 收敛 + 黄金链骨架 + 真实内核接线 | v2.0.0-livekernel | K01 K02 K03 | 95 passed · 9 notebooks · S1–S5+M1 全绿 · ¥9,413.3 在线离线一致 | CHANGELOG v2.0.0 |
| D2 | 09-17 夜 – 09-18 | 评分补强 P0–P3 + 供应商履约子系统 + 控制台重设计 | v2.1.0 → v2.4.0 | K04 K05 K06 K07 | 150 → 245 → 326 passed · 10 家供应商种子 · 15 条脱敏断言 · 195 条 trace 聚合 | CHANGELOG v2.1–v2.4 · DECAMERON 第二/三日 |
| D3 | 09-18 夜 – 09-19 | NemoClaw 混合架构（Dispatcher + OpenShell）+ L3 邮件自动驾驶 | v3.0.0 → v5.0.0 | K08 K09 K10 K11 | 354 → 417 → 462 → 499 passed · Skill 11→30 · IMAP 30s 轮询上线 | CHANGELOG v3.0.x/v4.0/v5.0 |
| D4 | 09-20 | GB10 节点对齐：SSH → GPU 攻坚 → 公网 :8051 → NVIDIA 全栈配置 | Unreleased（E 线） | K12 K13 K14 K15 K16 | GPU 62.6 → ~77 tok/s（4.8× CPU）· 701→725 passed · 公网 Bearer 上线 | DECAMERON 第七/八/九日 · `docs/evidence/nvidia/` |
| D5 | 09-19 夜 – 09-21 | 双飞轮 + 分层 RAG + Embed-1B 非对称双塔接线 | v6.2(WIP) → v6.3.2 | K17 K18 K19 | 562 passed · 飞轮 19 测试 · 沙箱隔离 A 不被 B 召回 · 475 篇入库路径打通 | CHANGELOG v6.2/v6.3.x · `tests/test_flywheel.py` |
| D6 | 09-21 – 09-23 | 全栈回归 + B 端后台重设计（13 标签 → 六工作台）+ STEP 真 3D 网格 | v6.3.0 → v7.0.0 | K20 K26 | 758 passed（本地）· 700/45（节点 ARM）· 34 failed 清零 · 39 张图纸 | CHANGELOG v6.3.0/v7.0.0 · `docs/NODE-DIFF.md` |
| D7 | 09-24 – 09-25 | 铁律加固：5 新策展 Skill + 负向触发矩阵 + 公网门禁 P1-1 + 静默 MOCK 根治 + ASR 关思考 | v7.1.0 | K22 K23 K27 K28 K29 K30 | 38 skill 注册 · P1-1 61 测试 + 17/17 真 uvicorn 实证 · ASR 72.9s → 0.6s（121×） | CHANGELOG v7.1.0 及 09-25 五连修 |
| D8 | 09-26 | 演示加固：压测 + RAG 锁外序列化 + 护栏变体 + 12 BUG 核对 + 自动报价八道闸 | v2.5.0（gate） | K21 K24 K25 K31 | RAG P95 15.2s → max 392ms · 12 BUG 修 10 · quote_history 0 → 1355 | 压测巡检报告 · T4T6 报告 · Z10 报告 |
| D9 | 09-26 – 09-27 | 尽调增强：reid 引擎桥 + Omni 协议执行 + 测试上节点 + text2cad 可行性实测 | — | K32 | `test_search_reid.py` 节点 24/24 全绿（0.49s）· 法兰实测 V=169,646mm³ → STEP 9.4KB / STL 50KB | 节点部署补全汇报 · 核心问题真实回答 |
| D10 | 09-27 | 知识库 3D 点云：PCA 投影 + hover/点击详情（手写 three.js，零新依赖） | — | — | 200 点 / 448 边 / 5 类 · tsc+vite build 0 错（1.38s）· 公网 bundle 已换 | 点云节点信息交互修复汇报 |
| 赛前 | 09-27 | 交付冲刺：开源包组装 + 脱敏两轮 + 截图补拍 + 部署 notebook + 交付包（含本稿共 10 件） | v7.1.0 发布态 | K33 | 687 文件 / 48MB · deploy.ipynb 15 cells（nbformat 4 合法）· 13+2 张截图齐 · 敏感项两轮清零 | DELIVERY-REPORT · 00-交付汇报 |

**编号说明（推理留痕）**：D 序号沿用全栈/选型稿的**里程碑序**，不按严格日历序——D4（节点对齐，09-20）与 D5（飞轮/RAG，09-19 夜起）在日历上交叠，因为节点侧与本地侧当时是两条并行战线。DECAMERON 的「四日实战 + 六日叙事延展」是另一种切法，两者不冲突：那份写到 09-20 凌晨，本稿写到 09-27 交付。

---

## 3. 逐日详稿

### D1 · 收敛与奠基（09-17）

那天桌面上摊着五个不同时期的脚手架：五个 `main.py`、五份互相矛盾的 `requirements.txt`，外加四份共存的 PRD。开赛前最后一周，再不收敛就完了。

第一动作是删，不是写。把提交主体压成 `union-export-agent-livekernel` 一个，路线钉成一句：**Replace the adapters, not the architecture**——适配器可换，架构不动。四份 PRD 拍板一份 FINAL（K01）。

下午接真实内核。`TimoAdapter` 在线优先 `:7862`，离线回退 vendored kernel（子进程 import 真 `calc_quote` + `ConflictChecker`），要求 **byte-identical**。第一次跑通时在线 S1 报 ¥9,413.3，离线也是 ¥9,413.3，小数点后一位不差。铁律①（LLM 不定价，引擎裁决）从这天起有了牙齿（K02 是它的第一次实战：`/api/cnc-quick` 模糊解析丢 `surface`，S3 漏判 DFM 冲突，改成自抽结构化字段调 `/api/conflict-check`）。

黄金链当天立起来：`Email/Voice/STEP → Intake → Context(context_id) → RFQ 状态机 → DFM → Quote → 五步验证 → HITL/BLOCKED/REPLY → CRM+Memory → SHA-256 审计`。

**学到**：byte-identical 不是洁癖，是契约。它让「本地无 GPU 改完推上节点」成为安全操作——不一致会立刻暴露。D4 那天这条契约救了场。
**量化**：v2.0.0 · 95 passed · 9 notebooks 全 PASS · S1–S5+M1 全绿。
**证据**：CHANGELOG `[2.0.0-livekernel]`；`docs/PRD-frozen-v1.0.md`。

### D2 · 从「能跑」到「评分能看」（09-17 夜 – 09-18）

对着 NCP-AAI 评分清单（7 维 / 25 考点）自评，估分 ~57。比赛不看谁能跑，看评分。于是 P0–P3 一夜铺开：LLM Planner（ReAct + JSON-Schema 绑定，**关在笼子里**——只抽字段、选技能、起草回复）、resilience（指数退避 + 熔断三态）、schema_validator、security（路径穿越 / 限流 / PII 脱敏）、evaluation（字段与工具准确率、消融、A/B）、RAGAS 风格 RAG 评测、HPA + Grafana + NeMo Guardrails colang。

`latency_report.py` 聚合 195 条真实 trace，瓶颈定位到 `cnc-quote`——第一次有「系统哪里慢」的量化证据。

白天转做工厂背后：`supplier_module` 七步原子提交（脱敏硬门禁 → 供应商库 → 7 维打分 → 8 状态子状态机 → mock 收件箱 + PO → AUTO 阈值 → skill 注册）。最得意的一处设计是 `IMAPInbox` 默认 `raise NotImplementedError`，必须显式 `enabled=True`——数据不出车间靠默认值守，不靠口号。控制台同步重设计（暗色 OLED，5 tab，3D STEP 上传引擎不可用也返回降级 SVG 不阻断前端）。

**学到**：评分补强最容易破铁律。让 LLM 直接出价最快、demo 最漂亮，但那样就没有「确定性基准」可对照——D7 修铁律①锁误报时，靠的正是这个基准还在。
**量化**：v2.1.0 → v2.4.0 · 150 → 245 → 326 passed · 估分 ~57 → ~80+ · 脱敏断言 15 条。
**证据**：CHANGELOG v2.1–v2.4；`docs/SUPPLIER-PIPELINE.md`；`docs/NCP-AAI-COVERAGE.md`。

### D3 · NemoClaw 与邮件自动驾驶（09-18 夜 – 09-19）

核心命题一句话：**LLM 只负责意图路由，不决定确定性 Skill 输出。**

`skill_dispatcher.py` 三策略（auto / rules_only / llm），规则路由兜底，LLM 在线才启用、失败自动回退且**不静默冒充**。`openshell/` 四策略落地：`iron-rule-1`（locked，四层强制：validate / save / UI / runtime）、`hitl-required`、`local-only` 路径沙箱、`skill-allowlist`。`attempt_override` 是这天最精妙的一处——它**演示并拒绝**改写，测试因此能断言「拒绝行为」而非「调用不存在」。

深夜接 Gmail IMAP（凭据 Fernet 加密 + 0600 权限），HITL 端点做**真持久锁定**：首次 sha16 落 `data/drafts/{cid}.json`，篡改 quote 后 `locked=false`，UI 红字拦截。再往上做 L3 邮件自动驾驶：`mail_puller`（30s 轮询 + 退避表 + 文件锁）+ `mail_orchestrator`（claim → run_pipeline → PASS 自动批准 / HITL·BLOCKED 通知）+ quality_scorer 自迭代 + 三通道通知 fallback。

两个 dispatcher 深层 bug 当天暴露：body 优先级 `intent > email_text` 导致 RFQ 正文被路由短语顶掉（K09，单元测试的 mock 邮件太干净，跑真邮件才发现）；铁律①锁键用裸 `skill_id`，同 skill 不同输入被误判「确定性输出被改写」（K10，改 `lock_key(skill_id, args)` 复合键——这条在 D8 还会以另一种形态复发，见 §5 坑一）。

**学到**：LLM 的价值在路由，不在生成。「这封邮件走哪个 skill」它擅长；「这个零件报多少」它不擅长且不可审计。
**量化**：v3.0.0 → v5.0.0 · 354 → 417 → 462 → 499 passed · Skill 11 → 30 · 端点 19 GET + 5 POST + ROOT 全 200。
**证据**：CHANGELOG v3.0.x/v4.0/v5.0；`docs/nemoclaw-architecture.md`；`docs/PLAN-L3-AUTOPILOT.md`。

### D4 · GB10 节点对齐（09-20）

解压 `Timo.zip`：44KB，两个文件——节点访问手册 + 本队凭据。SSH 端口不是 22 是 6051，业务端口 8051（← 节点 8888），服务必须绑 `0.0.0.0`，公网必须加认证。四条任一漏了都连不通；第一次起服务绑 `127.0.0.1`，公网 timeout，排查半小时才回手册找到那行字（K16）。

节点实测：Ubuntu 24.04.3 · **aarch64** · 内核 6.11.0-1014-nvidia · **GB10**（Grace-Blackwell）· 驱动 580.82.09 · **CUDA 13.0** · sm_(12,1) · **Developer 无 sudo** · Python 3.12.3（PEP668 受保护）。「无 sudo」这一行决定了接下来三小时。

GPU 攻坚三次迭代（K13）：① `TORCHDYNAMO_DISABLE=1` → 仍缺 `Python.h`（transformers 内部照样调 Triton 编译）；② `dpkg -x` 解包 dev 包设 `CPATH` → 头文件版本与 3.12.3 不完全匹配，编译不过；③ 读完报错发现缺的不止 `Python.h`，还有平台相关的 `pyconfig.h`（在 `config-3.12-aarch64-linux-gnu/` 下），**双路径**都进 `CPATH` → Triton JIT 通过，bf16 **62.6 tok/s**（vs CPU 13.1，4.8×），当晚复测 ~77 tok/s。

同日三件事并行：公网 :8051 + Bearer 上线（带宽红线：50 队共享，禁 scp >1GB，模型只能节点内拉）；`models.nvidia-fullstack.yaml` 写就，五角色端点配齐，`model_router` 的 `DETERMINISTIC / mock / nvidia` 三条路径**完全绕开** `choose_route`——确定性 100% 走 Timo；节点全量回归跑到 701 passed（当晚复跑 725，旧失败项 `test_deploy_manifests` 断言已修）。测试还顺手抓出一个真 bug：`deploy/nim/.env.example` 是 UTF-16 混编码（PowerShell 追加痕迹），docker compose env-file 不兼容（K15）。

**学到**：无 sudo 不是终点是起点——`~/.local`、venv、`dpkg -x`、`CPATH` 每层都有用户级解法，只是多绕一两步。以及：**报错要读完**，读一半就动手浪费了一整轮尝试。
**量化**：GPU 4.8× 加速 · 701 → 725 passed · Skill 30 → 33 · 公网端点活 · 节点证据落 `data/node_evidence/`。
**证据**：DECAMERON 第七/八/九日；`docs/evidence/nvidia/00-nvidia-stack-selfcheck.txt`；`docs/PRD-NVIDIA-FullStack-Swap.md`；`config/models.nvidia-fullstack.yaml`。

### D5 · 双飞轮与分层 RAG（09-19 夜 – 09-21）

修完 P0 已深夜，但叙事还差一环：**系统用得越久越准**。`services/flywheel/` 六模块新建（tenant / vector_store / quote_indexer / similar_recall / price_corrector / reaction_labeler / feedback_loop），四个 skill 注册进 `TOOL_ALLOWLIST`。分级修正 cap 是铁律①的延伸：COLD 5% / WARM 10% / HOT 15%，**只产证据与系数提案，永不改 `final_price`**。双层沙箱隔离测试是关键那条——租户 A 索引的报价绝不被 B 召回，`{"all_ok": true, "samples_A": 3, "B_samples": 0, "sandbox_pass": true}`。

RAG 侧做分层（L1 客户 / L2 历史报价 / L3 对话 / L4 工艺）+ 上传入口（ZIP / 嵌套 ZIP / GBK）+ Embed-1B **非对称双塔**接线。后者有个不显眼但要命的细节：query 与 passage 必须分别加前缀，不加则语义排序错乱（实测相关度 0.3758 vs 0.5209，相关文档排到倒数）（K19）。

诚实记录一条失败：报价矫正 `leave-one-out MAPE 51.12 → 52.58`，**暂无改善**，标注 proposal-only。如果当初让 corrector 直接乘进 `final_price`，这个「没改善」就永远看不见——已经被污染了。

**学到**：诚实的失败比虚假的成功有价值，前提是把「提案」与「裁决」在代码层分开。
**量化**：562 passed · 飞轮 19 测试 · Skill 26 → 30 · `.gitignore` 修正后 37 个误入索引的 sqlite 清出（K18：`data/*.sqlite3` 在 gitignore 里不递归，要 `data/**/*.sqlite3`）。
**证据**：CHANGELOG v6.2/v6.3.x；`方案-双飞轮与客户沙箱.md`；`scripts/run_flywheel_demo.py`。

### D6 · 全栈回归与 B 端后台重设计（09-21 – 09-23）

v6.3.0 交付版：把此前 28 个「存在但不可达」的端点全部接进浏览器（13 标签 / 69 端点），补 `POST /v1/demo/scenario/{sid}` 修掉 6 个死按钮，加 context 磁盘复水（邮件驱动 context 从不进内存 `_STORE`，RFQ 生命周期端点会 404）。脱敏包部署到节点，ARM 全量 **700 passed / 45 skipped**，OCC cadquery 2.8.0 真解析 STEP B-rep（1 solid，V=199,098.43mm³）。

v7.0.0 把 13 标签单文件收敛为**六工作台模块化控制台**（邮件 / 订单 / 图纸 / 客户情报 / 模型设置 / 本地状态），no-build ES modules；新增订单实体（状态机 + 非法迁移 409 + 758 张历史报价种子）、STEP 真 3D 网格管线（OCP `BRepMesh_IncrementalMesh` 子进程 worker，损坏 STEP 段错误隔离，Float32/Uint32 base64 → three.js BufferGeometry，600k 面自适应粗化）、客户情报（SearXNG 联网命中，不可达**显式** `mock:true`）、多模态情报库（音频→ASR / 图片→VLM / 视频→抽轨抽帧 → 入向量集合）。

回归这天最不光彩也最有用：34 个 failed 摆在那（K20）。逐条查下来全是**测试口径过时**——断言旧 UI 文案、旧拓扑、旧资产路径，产品行为是对的。清完之后定下规矩：`python -m pytest tests/ -q` 是每个 commit 前的必经步骤，「测试通过」不等于「跑过测试」。

**学到**：成熟项目的瓶颈不在写新东西，在把已有的东西串起来证明它能跑。`ab_report` 在 `evaluation/metrics.py` 里躺了很久没人调用，调用一次它才从死代码变成得分。
**量化**：758 passed（本地）· 700/45（节点）· 34 failed 清零 · 39 张图纸 · 六工作台上线。
**证据**：CHANGELOG v6.3.0/v7.0.0；`docs/NODE-DIFF.md`；`docs/ACCEPTANCE-REPORT-v8-node-deploy.md`。

### D7 · 铁律加固（09-24 – 09-25）

v7.1.0：遍历素材库蒸馏**事实性领域知识**为确定性本地 skill，5 个新 skill（material-knowledge / dfm-rules / process-knowledge / sop-router / reid-triage）按 NVIDIA AgentSkills 标准注册，全部 `iron_rule=deterministic`、不定价（`cannot_override_price`）、不推进状态机（`advances_state=false`），未收录材料**诚实返回 not-found 不假造**。注册要过**六触点**，这天连踩两个：SKILL.md description 里的 ASCII `: `（如 `禁止: 定价`）让 `yaml.safe_load` 抛 ScannerError → frontmatter 解析成空 → registry 丢 name/description（改全角 `：`，K27）；漏了第 6 触点 `openshell/skill-allowlist.yaml`，5 个新 skill 全被 dispatcher precheck 拦成「不在白名单」（K28）。

同日填**负向触发矩阵**：全仓搜 negative trigger → 0 命中，33 个 SKILL.md 全讲正向触发，没有一个讲「什么时候不该动」。给核心 8 个 skill 补禁止条件、误触发后果、对应负向测试。这是 Skills 工程深度的真正分水岭：会聊天也会报价的 Agent 不值钱，**该报价时报价、不该报价时纹丝不动**的才值钱。

09-25 五连修：
- **OpenClaw skill 层四案**（K29）——最危险的一条是 `ocp-geometry-code` 里的**假几何论断**：把 `extrude()` 在 YZ 平面的方向写成 −X，属编造。三重判据实测（质心 / `Plane.named().zDir` / bbox）证明是 **+X**；按错方向装配会在零件反侧生成 boss/pin，干拉检查还看不出来。另三案：manifest `os:[darwin]`+`bins:[chrome]` 在 Linux/aarch64 上被 gate 拦成 Needs setup（换 `os:[linux,darwin]`+`python3`+`anyBins:[soffice]`，PDF 本就有 LibreOffice 兜底）；`reid-operating-system` 三处死入口（不存在的 CLI 子命令、无执行位的裸管道、用 Ollama 专属 `/v1/api/tags` 探 vLLM 恒 404 → 改 `/v1/models`）；`unionskill-quote` 按**嵌套** `breakdown` 取值而真实响应是 45 个平铺字段 + `cost_breakdown`，导致重量 0.000kg、成本表整块消失。
- **静默 MOCK 陷阱**（K30）——`settings.yaml` 兜底 roles 仍指向从未部署的死端口，`models.yaml` 一旦读不到就落到 `MOCK:llm-offline`，不报错不告警直接给假数据。双源校准为实测常驻端点，铁律：端点只配一处。同轮把 Omni 的 ASR 路径**显式关思考**：同一段 15.07s 真实语音，4096+开思考 72.9s / 8192+开思考 159.9s 且 `content=None`（reasoning 无上限，调大 max_tokens 不是正解）/ 4096+关思考 **0.6s、25 token**——121× 提速。顺手隔离 53 个假测试资产（PNG/WAV 头之后全零，喂 Omni 返 400，adapter 降级 `_mock=True`，而降级值与真值外观无差别，调用方只判 `ok` 就中招），并清掉生产 RAG 库里的探针污染文档。
- **公网门禁 P1-1**（K22）——`api_server` 零鉴权 + 绑 `0.0.0.0`，经 NAT 在 :8051 暴露 106 条路径，公网免鉴权可拉 RAG 库内容（逐字节比对确认 8051 就是本机出口）。补 `services/security.py` 十个 gate 原语 + 中间件 + `/__auth` 登录（HMAC-SHA256 票据、`compare_digest` 常量时间比较、换 token 旧票据立即失效）。选 cookie 而非「前端逐处注入 header」的理由很实际：155 处 `fetch()` 分散在四个文件与 React 构建产物里，逐处改必然漏。回环判定兼容 `::1` / `::ffff:127.0.0.1` / testclient 合成主机名，watchdog 与内部脚本不受影响。61 项回归 + 真 uvicorn 实例 17/17 实证。
- **报价门禁分级 v2.4.0**——「缺字段即 HITL」严于引擎能力（引擎最小输入集本就不含表面/公差，实案已算出 ¥281.25 仍被挂人工）。新增 `CLARIFY` 状态与无价澄清信，四重闸（开关 / 草稿模式 / 24h 冷却 / **价格泄漏正则**——正文出现币种或金额即拒发并升级人工）。两个细节坑：`_apply_quote_gate()` 必须在几何富化**之后**调用，否则 STEP 附件客户被误判缺尺寸而误发澄清信（K06 同源）；`CLARIFY` 原会掉进 else 被判 `STATE_FAILED`，澄清信永远发不出去（E2E 才暴露）。
- **孤儿链清理**——`rfq_filter.py` + `policy.yaml` 的 `rfq_filter:` 段在职能迁到 `mail_classifier` 后残留成「看起来生效、实际完全无效」的死链（它曾被真实使用，审计里有 19 条 `rfq_filtered_out`）。清理走可恢复路径，并且**没有**动同前缀的 `rfq_state_machine.py`——它有四处活引用。死链判定必须按代码跑通才能断言。

**学到**：克制比能力更贵。负向触发是 skill 的「不作为」契约，和铁律①的「不越界」契约是一对：一个管「该做不做」，一个管「不该做却做」。
**量化**：38 skill 注册 · skill 域 pytest 83 passed · P1-1 61+17 项 · ASR 121× · 本地全量 1595 passed。
**证据**：CHANGELOG v7.1.0 与 09-25 各条；`docs/evidence/skills/negative-trigger-matrix.md`；`tests/test_p11_api_gate.py`。

### D8 · 演示加固（09-26）

上午压测：常规页面 30–40 QPS 零错误（mail/inbox 29.9 QPS P95 260ms、drawings 40.5 QPS P95 170ms），但 **rag/search P95 = 15.2s**，quote 端到端 P50 11.1s（rules 链 3–8s，含 Omni 路由才慢）。下午演示测试直接撞上两个 P0 阻塞：S1 黄金链 `check_dfm` 挂 "material required"、`verify_gate` 被 iron-rule-1 误杀。

根因两条，都在代码级定位到行：
- **BUG-A（K23）**：`_build_args` 的 `common` 字典在 skill 循环**之前**构建，`common["rfq"]` 在 parse_rfq 尚未运行时求值 → 恒 null；后续 skill 靠 `ctx.scratch` 兜底，**但 parse_rfq 第二次起命中 AgentCache，命中路径直接 return，不写 scratch** → 兜底全落空。「早上好、下午坏」的真凶就是它。
- **BUG-B（K21 同源）**：`verify_gate` 的 args 返回 `{"ctx_dict": None}` → lock_key 恒为 `verify_gate:e93152c0d941f9a7`；dispatcher 是进程级单例，`Shell.locks` 跨所有 dispatch 持久 → 第一次写锁之后，**任何**询盘的 verify_gate 输出 digest 必不同 → 必判「确定性输出被改写」→ output=null，前端验证状态全空。实测取证：3 个不同 intent 的 expected 全相同，同请求两次 actual 相同。

修法 T1/T2/T3：缓存命中分支回写 scratch（rfq/specs/quote/dfm/verification/step_facts）；check_dfm/calc_quote 分支**在循环内**重读 `ctx.scratch['rfq']`；verify_gate 锁 args 加输入指纹 `_input_fp`（rfq+quote+dfm）——同询盘同锁、异询盘异锁，这才对得上铁律语义「同一输入不可改写」。T5 回归 6 用例全绿：¥222.65 两次一致（缓存命中路径也一致）、304 法兰 ¥419.0、POM ¥102.2、316 镀铬轴 ¥454.0、探针「6061 报价」¥281.25，`viol=0`。

T6 治 RAG：`JsonFileBackend._save` 在**锁内**序列化全量 JSON（73MB 起，随库涨到 108MB），回填线程每次 upsert 全量 dumps 持锁秒级，并发 search 全排队。改成**锁外 dumps + 短锁写盘**，3 并发 P95 15,222ms → max **392ms**。

T4（`Shell.locks` 按 dispatch 隔离）**主动撤回**：补丁锚点选错，`_viol_base` 在 execute 早期，try 之后整块无法安全缩进，py_compile EXIT=1。两条路——手工重排 300 行缩进（高风险）或撤回。判断是 T3 的指纹分键已根治误报（回归 viol=0 证实），T4 只是纵深加固，按「最小改动、不冒险」撤回，备份保留。撤回后回归 6 用例 + 探针全绿，零回退。

同日核对 12 个历史 BUG：**10 个已修**（RAG 敏感文档、flywheel 统计归零、护栏连字符变体、/health contexts 恒 0、feedback 109 条噪声、use_llm 开关失效、iron-rule-1 误报、引擎 LLM 候选 9 个死端口、FAILED 计数残留、邮箱凭据失忆），余两条：frp 公网匿名直通（P0 安全，演示期经拍板暂不处理）、节点 pytest 失败清零（D9 完成）。

还有 v2.5.0 自动报价外发：`auto_quote_send_enabled` 在 Python 侧**零读取点**、阈值只被测试引用——发送链路从未实现，不是翻开关的活。照抄澄清信已验证的同构模式，草稿层仍 `draft_only`，发送决策与**八道闸**全在 orchestrator（逃生门 / PASS 六项逐项复用不复写 / 报价事实完备 / 护栏落盘 / **价格一致性**——正文必须原样含 unit_price 与 final_price，LLM 改写须原数 / 复杂度阈值 / **自环防御**——收件人等于本账号即跳过，否则信被 puller 拉回形成 CLARIFY↔报价 自环 / 幂等）。顺带修掉一个真实事故源：PASS 分支硬编码 `USD/CNY 222.8` 双币种并标，与 PDF 渲染的 `currency` 自相矛盾，等于让客户自己挑币种，改为跟随 `quote.currency`。

**学到**：演示前必须自己压一遍、自己跑一遍黄金链。这两个 P0 都是「上午能过、下午挂」的形态，靠单测永远抓不到。
**量化**：RAG ~40× · 6 用例 + 探针全绿 · 12 BUG 修 10 · quote_history 0 → **1355**（回填追平 > eligible 1354）· 新增 `tests/test_auto_quote.py` 15 用例。
**证据**：`全链路对齐压测与CoT修复清单.md`；`BUG修复交付报告-T1T2T3.md`；`修复计划执行完毕报告-T4T6.md`；`SER全链路验收报告-0926.md`；CHANGELOG v2.5.0。

### D9 · 尽调增强与口径对齐（09-26 – 09-27）

reid 尽调走「引擎 v1.5 决策层 + Omni 协议执行」双段：决策层给分诊结论，Omni 负责协议化执行与叙述，铁律②守住——**尽调不产价**。工具调用侧摸到一条硬阈值：Omni 在 600 token 预算下才稳定吐 `tool_calls`，预算给小了它会把话讲完而不调用（K32）。

测试资产补齐上节点：`tests/test_search_reid.py`（21KB）此前只在本地跑，上传后节点实跑 **24/24 全绿（0.49s）**，闭合上轮「D9 偏差」。

节点全量回归 36 failed → 修 10 条**过时断言**（产品代码零改动）：`test_model_router_layered` 7 条期望的是 P2 规划拓扑（Nano-4B / 30B 分层 / ASR 专档 8020·8021），实际 v2 决策已全接 Omni:8002 + Embed:8011；`test_v6_root_index` / `test_console_ui` 断言旧 UI 文案；`test_sandbox_listing` 期望的种子沙箱在节点已被清理；`test_model_router` 断言 primary 不通即 offline+MOCK，而实际 C4 fallback(:8902) 真实接管 `online=True`——**产品行为是对的，测试是错的**。最终基线 **1070 passed / 26 failed / 6 skipped**。

剩下 26 条逐簇定性为环境依赖（QQ 邮箱真实同步状态 5 · 部署路径设计差异 5 · 节点图纸资产 3 · puller 生产运行锁 3 · gate 响应序列化差异 2 · profile/imap/网络重试/媒体后端/飞轮沙箱 7）。判定写死：**不为通过测试而在节点改测试语义**，那会掩盖真实环境差异；本地跑这些是绿的（1595 passed）。

text2cad 可行性当天在节点直测：CadQuery 2.8.0 从中文描述解析法兰 OD120/ID60/T20 → bbox 120×20 ✓ 体积 **169,646mm³** ✓ → STEP 9.4KB + STL 50KB。结论是缺的只有中间一层「结构化参数 → 参数化模板」（6–8 个模板，LLM 只填槽位不做自由代码生成），抽取 / 几何引擎 / 3D 展示 / 定价四环都已在手；对比对象 nl2cad 实测解析中文失败（NonexNonexNone 假几何），不接它的服务。方案落 `推理执行页文字生图改造方案.md`，skill 以 stage 状态入包不发布。

**学到**：测试失败要先分诊「谁错了」。这天 10 条是测试错、26 条是环境差异，混为一谈就会去改产品代码迎合断言。
**量化**：节点 1070 passed · search_reid 24/24 · 法兰几何实测通过 · 12 BUG 全部收口（余 frp 一条经拍板留档）。
**证据**：`节点部署补全与测试修复汇报.md`；`核心问题真实回答-邮件RAG画图.md`；`Z10交付声明验证报告.md`。

### D10 · 知识库 3D 点云（09-27）

用户反馈很具体：点云能看到点，看不到点上的文档信息。取证发现**后端数据本来就齐全**——`/v1/rag/projection` 每个 node 已含 `id / cls_label / label（60 字摘要）/ customer_id / chars`；根因在前端 `KnowledgePointCloud.tsx` 只做了渲染（Points + 边 + OrbitControls），没有任何 raycaster 拾取。

纯前端修，后端零改动：raycaster 拾取（threshold 0.08，pointerenter/move/leave/click 四事件）、左上角 hover 浮提示（不遮挡操作，显示 id / 类别 / 客户 / 字数 / 摘要前 120 字 + 「点击固定详情」引导）、点击详情卡（类别色点对应点色、本轮 RAG 命中徽标、摘要 pre 滚动区）、光标 crosshair、dispose 时解绑全部监听防泄漏。投影本身是 PCA 降维 200 点 / 448 边 / 5 类，three.js 手写轨道控制，**零新依赖**；测试侧 jsdom 无 WebGL，用 try/catch 降级不炸 CI。

验证走完整链：本地 `tsc -b` + `vite build` 0 错（1.38s，新 bundle `index-DSmUweh8.js`）→ tar-over-stdin 原子上传（备份 `webui-dist.bak.hover-260927*`）→ 公网 HTML 已引用新 bundle → bundle 内四项交互代码全命中 → 数据端点字段齐。点云从「只能看」变成「能查」。

**学到**：先取证再动手。这条如果按「后端没传信息」去改后端，会白做一轮。
**量化**：200 点 / 448 边 / 5 类 · 构建 0 错 · 公网 bundle 已换 · 回滚一条命令在档。
**证据**：`点云节点信息交互修复汇报.md`；`/v1/rag/projection`。

### 赛前 · 交付冲刺（09-27）

节点源码打包（排除 data/ 运行数据、node_modules、`__pycache__`、`*.bak.*`、日志、stage 目录）→ SFTP 拉取 37MB → 解包 690 文件 → 组装 GitHub 标准结构：README / LICENSE(MIT) / CHANGELOG / MANIFEST / CONTRIBUTING / 强化 .gitignore + `docs/`（75 md，含架构/PRD/验收/十日谈）+ screenshots 43 张（含 `v51/` 子目录 5 张）+ `deploy.ipynb`（15 cells，nbformat 4 合法）+ `docs/delivery/` 比赛物料 + skills 39 / openshell 4 / services / agents / adapters / tests + CI workflow。组装后复测 **687 文件 · 319 py · 125 md · 105 png · 48MB**（比首报 683/37MB 多的是补拍截图与完整 docs 资产）。

脱敏三重自检跑两轮：公网 IP（2 文件）→ `<NODE-PUBLIC-IP>`；内网 IP → `<NODE-LAN-IP>`；真实账号（3 处）→ `<REDACTED-ACCOUNT>`；`.env` 只留 example 模板；复扫清零。`alice/tester/sales@union*` 等 70+ 邮箱是测试夹具，按惯例保留。交付包成形（00 汇报 / 01 README / 02 架构+功能 / 04 部署+Skill 标准包 / 06 PPT+演讲稿 / 07 全栈+选型+十日 / 08 截图清单 / deploy.ipynb / DELIVERY-REPORT），本稿为交付包第 10 件。

截图缺口同日补齐：`/#/search` 的 reid 尽调与知识库 3D 点云两张，走 `scripts/screenshot_search_8051.py` 打公网真后端（本机无 Chromium，复用系统 Edge + SwiftShader WebGL）。这里又踩一个小坑：hover 检测锚点若用文本「点击固定详情」，会命中 canvas 下方的静态图例行造成**假阳性**，必须锚 `div.pointer-events-none.absolute`（tooltip 唯一类）——已在脚本注释里锁定。至此决赛清单 13+2 张全部到位（`15_search_reid.png` / `16_search_pointcloud.png`，后者 tooltip 显示真实文档「横梁伸长杆盖-V1.0.PDF · 761 字」）。

冲刺期还捞回三条容易漏的：敏感文档（登录信息表）曾进 RAG——已删 + 黑名单，`docs/` 里保留的是脱敏声明与事故复盘注释，不是数据；frp 回环造成「8051 断了」的假象——本地 curl 走回环失败，外部实测 200，误判一次；flywheel 统计键名脱节导致 total_quotes 归零——修键名后 3464 恢复。

**学到**：交付的可信度来自口径一致，不来自功能多。README badge、git tag、CHANGELOG、health 返回值四处对得上，比多一个功能值钱。
**量化**：687 文件 / 48MB · 125 md · 105 png · 截图 43 张 · 敏感项两轮清零 · 交付包 10 件。
**证据**：`DELIVERY-REPORT.md`（开源交付包根）；评审侧 `交付包/00-交付汇报.md`；`docs/evidence/secret-scan-2026-09-20.md`。

---

## 4. 坑位总清单（K01–K33）

| # | 日 | 现象 | 根因 | 修法 | 锁定方式 |
|---|---|---|---|---|---|
| K01 | D1 | 4 份 PRD 共存，方向不收敛 | 多轮规划叠加，无单一权威 | 拍板 FINAL，其余标「已被取代」+ 勘误表 | 文档头勘误表（PRD-MASTER v2.0 为唯一权威） |
| K02 | D1 | S3 漏判 DFM 冲突 | `/api/cnc-quick` 模糊解析丢 `surface` | 自抽结构化字段调 `/api/conflict-check` | 黄金链 S1–S5+M1 回归 |
| K03 | D1 | 引擎 `.venv` 起不来；FastAPI+SQLite 报错；customer_id 抖动 | 缺 `pyvenv.cfg`；线程池跨线程；`hash()` 不稳定 | 按系统 Python 3.11.9 重建；`check_same_thread=False`；换 md5 | v2.0.0 95 passed |
| K04 | D2 | PO 利润双算 | `final_price` 已含利润再乘 markup | `SELL = PO 成本 × (1+markup)` 独立计算 | outsource 6 测试 |
| K05 | D2/D6 | 版本三套不一致（health / UI / FastAPI） | 各处硬编码 | 六处标记同步 + 单一来源 | release marker 断言 |
| K06 | D2/D7 | 有 STEP 附图的客户被误发澄清信 | `_apply_quote_gate()` 在几何富化之前调用 | 调用点移到富化之后 | v2.4.0 门禁测试 |
| K07 | D2 | 反馈库 109 条未读噪声 | 测试/演示数据未清 | 清理 + 去重，未读回到 1 | B5 实测复核 |
| K08 | D3 | 铁律①锁被绕过风险 | 单层校验可漏 | `locked=true` 在 validate/save/UI/runtime 四层强制 | 40 项契约测试 |
| K09 | D3 | RFQ 正文被路由短语顶掉 | `_build_args` body 优先级 `intent > email_text` | 改 `email_text > intent` | dispatcher 17 测试 + 真邮件跑通 |
| K10 | D3 | 同 skill 不同输入被判「输出被改写」 | 锁键用裸 `skill_id` | `lock_key(skill_id, args)` 复合键 | 铁律①回归（D8 再深化为 K21） |
| K11 | D3 | 后台 loop 抢先 FIFO，邮件重复处理 | claim race | 租约 `mark_state(mail_id,"PROCESSING")` | demo scenario 5 测试 |
| K12 | D4 | 30B 与 Omni 同驻 crash-loop | KV cache 分配冲突，watchdog 22 次重启 | v2 决策：Omni-30B 统一 LLM/VLM/OCR/ASR 四角色 | `test_model_router_layered` 断言对齐 v2 拓扑 |
| K13 | D4 | Triton JIT 编译失败，GPU 用不上 | 无 sudo 装不了 dev 包；缺 `Python.h` **和** `pyconfig.h` | `CPATH` 双路径（include + config-3.12-aarch64-linux-gnu） | 节点 GPU 快照 + tok/s 实测 |
| K14 | D4 | pypi/HF 不可达；僵尸脚本占带宽；SSH banner 抖动 | 网络策略；`ollama-linux-arm64.tgz` 在该 release 不存在（实为 `.tar.zst`）持续 404；跳板机限流 | 清华源 + hf-mirror（`HF_ENDPOINT` + `HF_HUB_DISABLE_XET=1`）；kill 僵尸；重连重试 | 部署 notebook 注释 + `docs/NODE-DIFF.md` |
| K15 | D4 | `docker compose` env-file 不兼容 | `.env.example` UTF-16 混编码（PowerShell 追加痕迹） | 重写干净 UTF-8 占位模板 | `test_deploy_manifests` 6 项 |
| K16 | D4/D8 | 公网访问 timeout；后又误判「8051 断了」 | 服务绑 `127.0.0.1`；frp 回环造成本地 curl 假失败 | 绑 `0.0.0.0` + 逐字读手册；外部实测 200 为准 | 部署 runbook + 外部探针 |
| K17 | D5 | 飞轮报价召回不准 | Embed 非对称双塔缺 `query:`/`passage:` 前缀 | 配置驱动前缀，入库/查询分路 | 0.3758 → 0.5209 实测 + `test_node_profile_overlay` |
| K18 | D5 | 37 个 sqlite 误入 git 索引 | `data/*.sqlite3` 在 gitignore 里不递归 | 改 `data/**/*.sqlite3` + `git rm --cached`（磁盘保留） | .gitignore 强化 + 导出自检 |
| K19 | D5 | 报价矫正无改善 | 数据不足，方案本身待验证 | **诚实标注** proposal-only，MAPE 51.12 → 52.58 照写 | CHANGELOG 留痕 |
| K20 | D6 | 节点 34 failed | 测试口径过时（旧 UI / 旧拓扑 / 旧资产断言） | 逐条对齐实况，产品代码零改动 | 全量回归命令入 commit 前必经步骤 |
| K21 | D7/D8 | verify_gate 被 iron-rule-1 误杀，output=null | args 恒 `{"ctx_dict": None}` → lock_key 恒定；dispatcher 进程级单例，`Shell.locks` 跨 dispatch 持久 | T3：锁 args 加输入指纹 `_input_fp`（rfq+quote+dfm） | T5 回归 6 用例 `viol=0` |
| K22 | D7 | 公网免鉴权可拉 RAG 内容（106 条路径暴露） | `api_server` 零鉴权 + 绑 `0.0.0.0` 经 NAT 出口 | gate 原语 10 函数 + 中间件 + `/__auth`（HMAC 票据、常量时间比较、换 token 旧票失效）；回环白名单 | 61 项回归 + 真 uvicorn 17/17 |
| K23 | D7/D8 | check_dfm 挂 "material required"，「早上好下午坏」 | `common` 在循环外快照恒 null；AgentCache 命中路径直接 return，不写 `ctx.scratch` | T1 命中分支回写 scratch；T2 循环内重读 rfq | T5 回归 + 缓存命中路径二次跑一致 |
| K24 | D8 | RAG P95 15.2s；报价没沉淀进向量库（quote_history=0） | `JsonFileBackend._save` 锁内序列化 73→108MB；`QuoteIndexer` 存在但黄金链上无调用点 | T6 锁外 dumps + 短锁写盘；Q3 回填 + 挂钩，追平 1355 条 | 压测复跑 P50 224/max 392ms；Z10 实测 1355 > eligible 1354 |
| K25 | D8 | 飞轮统计归零、/health contexts 恒 0、FAILED 计数残留 | 键名脱节、口径未接真实磁盘计数、状态未剔除 | 修键名（3464）、真实计数（4364+）、by_state 剔除 FAILED | SER 12 BUG 逐项复核 |
| K26 | D6 | 幽灵客户混进 `/v1/flywheel/customers` | `glob('*.sqlite3').stem` 把杂散文件当 customer_id | cid 合法性正则过滤（短横线分段 token） | `test_sandbox_listing`（D9 放宽为「合法 cid 存在」，保留核心断言） |
| K27 | D7 | 5 个新 skill 的 registry 信息全空 | SKILL.md description 含 ASCII `: ` → YAML ScannerError → frontmatter 解析成 {} | 改全角 `：` | `/v1/skills` cross_check ok |
| K28 | D7 | 5 个新 skill 全被拦「不在白名单」 | 漏注册第 6 触点 `openshell/skill-allowlist.yaml` | 补 5 个 snake_case id | 六触点清单入 SKILL-PACK 规范 |
| K29 | D7 | skill 自身就是错的（4 案） | 假几何论断（YZ 平面 extrude 方向编造为 −X，实测 +X）；manifest os/bins 与本机不符；三处死入口（不存在的 CLI 子命令 / 无执行位裸管道 / 用 Ollama 端点探 vLLM 恒 404）；展示层按嵌套 `breakdown` 取值而真实是 45 平铺字段 | 三重判据实测补六平面方向全表；manifest 改 linux+python3+soffice；探针改 `/v1/models`；按真实契约取顶层字段 + `cost_breakdown` | `tests/test_matrix.py --quick` 3/3；quote skill 实跑重量 0.500kg / 工时 0.20h / 成本 5 项全渲染 |
| K30 | D7 | 模型离线时静默给假数据；ASR 空转写 | 兜底 roles 指向死端口 → `MOCK:llm-offline` 不告警；Omni reasoning 烧光 token 预算 → `content=None` 而 HTTP 200 | 双源校准为实测端点（端点只配一处）；`chat_template_kwargs={"enable_thinking": False}` | 兜底链 in-process 验证；ASR 三配置对照表（72.9s/159.9s/0.6s） |
| K31 | D7/D8 | 护栏被连字符变体绕过；中文注入放行 | 英文规则打不住「请忽略之前的指令」；`guarantee` 连字符变体漏判 | 补中文注入/越狱正则 + 词级正则（`\bguarantee`）→ REVIEW_AND_NO_SEND + force_no_send；含 B2B 中文误报回归 | guardrails 测试 + SER B3 复核 |
| K32 | D9 | Omni 不吐 `tool_calls` | token 预算不足，模型选择把话讲完 | 预算给到 600 token | 工具调用 probe 200 + 正确 `tool_calls` |
| K33 | 赛前 | 截图脚本判「hover 生效」是假阳性 | 检测锚点用文本「点击固定详情」，命中 canvas 下方静态图例行 | 改锚 tooltip 唯一类 `div.pointer-events-none.absolute`；本机无 Chromium → 复用系统 Edge + SwiftShader WebGL | `scripts/screenshot_search_8051.py` 注释锁定 |

**另有一条「非坑的坑」值得单列**：T4（`Shell.locks` 按 dispatch 隔离）**主动撤回**——补丁锚点选错导致 py_compile EXIT=1，两条路里选了不冒险那条，理由是 T3 已根治（回归 `viol=0` 证实），T4 只是纵深加固。原始备份保留，撤回后回归零回退。这条写进交付材料，是因为「知道自己没做什么、为什么不做」和「做了什么」一样需要留痕。

---

## 5. 三个最值得讲的坑（演讲 1.5 分钟版）

**坑一 · 铁律①的锁，自己误报了自己（K10 → K21）**
> 我们给确定性输出上了 sha256 锁，防 LLM 改写价格。结果这把锁跨请求持久：第一次某询盘写入锁之后，**任何**新询盘的 verify_gate 输出 digest 都不同，一律被判「确定性输出被改写」，验证状态全空。护栏变成了拦路障。根治办法是把锁键从裸 skill 名改成「skill + 输入指纹」——同询盘同锁、异询盘异锁。这本来才是铁律的语义：**同一输入不可改写**，不是「同一 skill 只能有一种输出」。

**坑二 · 早上好、下午坏（K23）**
> 演示上午能过，下午必挂，报 "material required"。查下来是两层叠加：参数快照在 skill 循环**之前**构建，那时 parse_rfq 还没跑，rfq 恒为 null；本来有 scratch 兜底，但第二次起 parse_rfq 命中缓存，而**缓存命中路径直接 return，不写 scratch**——兜底也空了。缓存优化吃掉了副作用。修法是命中分支把 rfq/specs/quote/dfm/verification/step_facts 回写 scratch，并且参数在循环内现读。教训写进了架构备注：带 scratch 写入的 skill，要么标 `cache_safe=false`，要么统一走回写。

**坑三 · 15 秒的检索（K24）**
> RAG 检索 P95 15.2 秒，演示时并发一点就卡。根因不在向量计算，在写盘：JSON 文件后端每次 upsert 都**在锁内**全量序列化，库涨到 100MB 级别，回填线程持锁秒级，所有搜索排队。改成锁外 dumps + 短锁写盘，3 并发 P50 224ms、max 392ms，约 40 倍。检索从「演示风险」变成「演示亮点」。

（三条的共同点：都不是算法问题，是**状态与边界**问题——锁的作用域、缓存的副作用、持锁的时长。）

---

## 6. 诚实边界与勘误

| 项 | 状态 | 说明 |
|---|---|---|
| NIM / TensorRT-LLM / Triton Server | 🔴 **清单就绪，未部署** | 节点 docker daemon 无权限且无 root，申请入组不可行；主路径改 vLLM 进程级，本地 vLLM 已覆盖其角色。编排文件仅对「有 docker 权限的目标环境」有效 |
| `nemo_soft` 护栏后端 | 🟡 配置可切，未激活 | colang 护栏流在仓，builtin 兜底 |
| 节点 26 条 pytest 失败 | 🟡 环境依赖，逐簇留档 | 本地同测试为绿（1595 passed）；**不在节点为通过测试而改测试语义** |
| frp 公网 :8051 匿名直通 | 🔴 遗留 P0 | 应用层 P1-1 门禁已就位（token + cookie），frp 层源 IP 透传未做；演示期经拍板暂不处理，已留档 |
| text2cad | 🟡 方案 + stage skill | 几何能力已节点实测（法兰 V=169,646mm³），中间模板层待排期，未发布 |
| 自动报价真机全闸验证 | 🟡 部分 | 已用真实引擎 context + 真实渲染附件完成一次真链路自闭环外发（IMAP 回读 UID=146，2 附件完整送达），但该次为直调 `send_quote_reply`；尚未走 `_try_auto_quote` 八闸对真实客户信发一封 |
| `check_hitl` 金额门禁 | 🟡 缺口 | 只判 `unit_price`，`total_price_review_cny: 100000` 在 policy 有值无执行点 |
| Gmail OAuth | ⬜ backlog | 当前 App Password，比赛场景够用 |
| HTTP 真实 failover | ⬜ backlog | `choose_route` 只决策不重试，调用方侧 fallback 切换未写 |
| 跨区跳转反查索引 | ⬜ backlog | `context_id → mail_id` 现为 inbox scan O(N) |

**三处必须勘误的历史声明**：

1. **「回归 6 failed / 1525 passed」不属实**。Z10 只读实测：节点全量 **36 failed / 1036 passed / 6 skipped**；且被归因为「Q6 text2cad WIP」的测试在文件系统上不存在。D9 修 10 条过时断言后基线为 **1070 / 26 / 6**。演示前引用「全绿」必须带确切命令与环境。
2. **`docs/DEMO-RUNBOOK-8051.md` 与 `docs/NCP-AAI-INTRO.md` 未落盘**（节点与 workspace 全盘搜索无命中，连未提交副本都没有），且 runbook 里写的 demo/scenario 端点与当前 API 不符。需要重写或从交付材料中撤下引用。
3. **GPU 吞吐与测试数**：DECAMERON 正文的「62.6 tok/s」「701 passed」是 09-20 凌晨时点数字，叙事保留不覆写；当前口径 **~77 tok/s** / **725 passed（09-20 晚）** → 节点 **1070 passed（09-27）**。

**一处两报告数字不一致，引用需注意**：D8 的 6 用例回归中，7075 用例在 `BUG修复交付报告-T1T2T3.md` 记为 **¥408.48（AL7075）**，在 `修复计划执行完毕报告-T4T6.md` 记为 **¥358.48（7075）**——两轮入参规格不同（材料牌号与尺寸组合），不是确定性失效；同一报告内 run1 两次 ¥222.65 完全一致才是 byte-identical 的判据。对外只引用 ¥222.65 / ¥281.25 两个已双轮验证的数字。

---

## 7. 留给后来者的五条纪律

1. **先连上再说**——一个连通的事实，胜过十页可行性论证。
2. **接口兼容 ≠ 行为等价**——换了后端必须跑 sha256 回归，「接上了」和「生意没变」差一个哈希。
3. **函数存在不等于能力存在**——调用过且留了产物才算交付；`ab_report` 躺了很久，调用一次才变成得分。
4. **凡涉及缓存 / 单例 / 可变状态 / 锁，必须实跑，不能推理替代**——把「文件存在」当「断言通过」是自欺；本稿三个招牌坑（K21 K23 K24）全在这一类。
5. **克制比能力更贵**——负向触发（不该做时纹丝不动）与铁律①（不越界定价）是一对；诚实的失败（MAPE 没改善照写）比虚假的成功有价值，前提是代码层把「提案」与「裁决」分开。

---

## 附录 A · 版本 / 日期索引

| 日期 | 版本 | 主题 |
|---|---|---|
| 09-17 | v2.0.0-livekernel · v2.1.0/2.1.1 · v2.2.0 · v2.3.0 | 主干收敛 + 真实内核 + 评分补强 + 供应商子系统 |
| 09-18 | v2.3.1 · v2.4.0 · v3.0.0 · v3.0.1 · v4.0.0 | A/B 路由 + 控制台 + NemoClaw + Gmail 工作台 + 三栏 Workbench |
| 09-19 | v5.0.0 · v6.0.0 · v6.1.0 · v6.2(WIP) | L3 邮件自动驾驶 + 30 skill + NVIDIA 对齐 + 四 P0 修复 + 双飞轮 |
| 09-20 | Unreleased（E 线） | 节点 SSH / GPU 攻坚 / 公网 :8051 / Nemotron 全栈配置 |
| 09-21 | v6.3.0 · v6.3.1 · v6.3.2 | 交付版（UI 全端点接线 + 节点 ARM 验证 + 脱敏公开）+ G1/G2 + Embed-1B 接线 |
| 09-22 | v7.0.0 | 六工作台控制台 + 订单实体 + STEP 真 3D + 客户情报 + 多模态情报库 |
| 09-24 | v7.1.0 | 5 个策展 skill 按 NVIDIA AgentSkills 标准注册（六触点） |
| 09-25 | 五连修 | OpenClaw skill 四案 + 静默 MOCK 根治 + ASR 关思考 + P1-1 公网门禁 + rfq_filter 孤儿链清理 + 报价门禁分级 v2.4.0 |
| 09-26 | v2.5.0（gate） | 压测 + T1/T2/T3 + T6 + T4 撤回 + 自动报价八道闸 + 12 BUG 核对 + Z10 验证 |
| 09-27 | 交付态 | search_reid 上节点 + 10 条断言修复（1070/26/6）+ 点云 hover + github-package 脱敏打包 + 交付包 10 件 |

## 附录 B · 证据文件索引（本稿引用来源）

- 架构与功能：`docs/ARCHITECTURE.md`（评审侧摘要：交付包 02-架构与功能解析.md）
- Skill 标准包与六触点：`docs/delivery/SKILL-PACK.md` + `docs/deploy.ipynb`
- 演讲与 PPT：`docs/delivery/PITCH-DECK-OUTLINE.md`（第 10 页 = 本稿 §2 总览表）
- 全栈 / DGX / 选型 / 十日概要：`docs/delivery/NVIDIA-STACK-AND-MODEL-CHOICE.md`（本稿是其第四节的展开）
- 截图：`docs/delivery/SCREENSHOTS.md`、`docs/screenshots/`（43 张，含 `v51/` 5 张；决赛清单 13+2 张齐）
- 历程另两版：`docs/十日谈.md`（简版 M0–M8）、`docs/DECAMERON.md`（长卷，含 09-20 勘误头）
- 修复与验收（评审侧留档，仓库外 `盘点汇总/`）：`BUG修复交付报告-T1T2T3.md`、`修复计划执行完毕报告-T4T6.md`、`全链路对齐压测与CoT修复清单.md`、`SER全链路验收报告-0926.md`、`Z10交付声明验证报告.md`、`节点部署补全与测试修复汇报.md`、`点云节点信息交互修复汇报.md`、`核心问题真实回答-邮件RAG画图.md`
- 全仓盘点（评审侧留档，仓库外）：`总报告.md` + `report-代码.md` / `report-文档.md` / `report-配置与技能.md` / `report-数据资产.md`
- 开源包：`DELIVERY-REPORT.md`（开源交付包根）+ `CHANGELOG.md`

## 附录 C · 30 秒口径（与 06 演讲稿一致，可直接背）

> 我们不是又一个聊天 Agent。Union Export Agent 把一封 CNC 询盘变成可审计的商业决策：LLM 提议，确定性引擎裁决价格，Skills 管窄触发与业务能力，DGX Spark + Nemotron 提供本地算力。十天里我们修了 33 个坑，最有价值的三个都不是算法问题，是状态与边界问题——锁的作用域、缓存的副作用、持锁的时长。今天节点状态：1070 测试通过、475 篇知识库、66 客户飞轮、邮箱 24 小时自动在跑。
