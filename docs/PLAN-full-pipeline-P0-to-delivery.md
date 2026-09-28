# 全流程总图 · Union Export Agent 参赛交付（P0 → 上线）

| 字段 | 内容 |
|------|------|
| 版本 | v1.0 · 2026-09-20 |
| 提交主体 | `union-export-agent-livekernel`（唯一） |
| 分支现状 | `feature/skills-p0-flywheel` · 工作树大量未提交 · HEAD 仍停 v3.0.1 标记 |
| 代码健康 | 验收报告：pytest **701 passed / 1 skipped**；skills **33/33 tool.py** |
| Spark | **已连通** spark-51（内网 spark-388d）· GB10 · aarch64 · 无 sudo · Qwen3-0.6B CPU 13 tok/s |
| 战略 | 行业主叙事 × Spark/触发/A-B 实证（见 `PRD-NCPAAI-Spark-Submission.md`） |
| 本文角色 | **总施工图**：从地基到交房的全流程，等你确认后按阶段执行 |

---

## 0. 一页摘要（你现在在哪、要去哪）

```
已完成（毛坯+部分精装）          缺口（要补的证/要修的账）
─────────────────────────      ─────────────────────────
33 Skills 制式 + 治理 yaml      negative trigger 基本空
701 测试绿（本机）              Spark 上未跑通 livekernel
黄金链 demo / 截图帧            A/B 有函数无正式实验报告
NIM/K8s 部署清单 + 配置切换     Spark 上无 models.yaml 实切证据
杰沃 PO/BOM 管道（历史实证）    版本 pin / 凭据外泄风险
Spark SSH + 小模型 CPU 推理     Workbench 未绑 0.0.0.0:8888 公网
PRD/覆盖矩阵/验收报告 v7        视频/十日谈/正式提交包未收口
```

**目标房子**：评委能用 DGX Spark 上的 Agent，看一封询盘如何变成**可审计报价**；Skills 窄触发不误伤；A/B 证明技能有用；价格永远来自引擎。

---

## 1. 施工阶段总表（地基 → 交房）

| 阶段 | 比喻 | 内容 | 完成定义 DoD |
|------|------|------|----------------|
| **P0 地基** | 三通一平 | 战略锁定、资产边界、密钥与版本账、本机基线复跑 | 知道交什么/不交什么；本机 701 可复现；无密钥进交付面 |
| **P1 主体** | 钢筋混凝土 | livekernel 在 Spark：同步、路径、引擎/API 起服 | 节点 health + 证据目录落盘 |
| **P2 水电** | 强弱电 | NVIDIA/模型链路 + Skills 触发治理 | ≥1 条推理链路实证；核心 skill 有 negative trigger |
| **P3 精装** | 门窗厨卫 | Demo 打磨、A/B、UI 可访问 | 公网/隧道可演示；A/B JSON |
| **P4 验收** | 分户验收 | 全量测试、脱敏、版本 pin、证据包齐 | 门禁清单全勾 |
| **P5 交房** | 交付上线 | 提交包、答辩口径、录屏 | 可交、可讲、可复现 |

阶段可部分并行，但 **P0 门禁不满足不宣称 P1「平台分已拿到」**。

---

## 2. P0 地基（先清账，再盖楼）

### 2.1 战略（已拍板，执行时不再摇摆）

- 只交 livekernel；Timo2026 垂直商业价值 = 主叙事  
- 得分 = Spark 实证 + Skills 负向触发 + A/B + Demo  
- 官方 NVIDIA/skills：**本机精选参考**，禁止全量上节点逐个装

### 2.2 资产地图（禁止误伤）

| 路径 | 角色 | 动作 |
|------|------|------|
| `union-export-agent-livekernel/` | **唯一参赛主干** | 唯一写入/部署源 |
| `Timo/` 手册与登录表 | 平台凭据 | **仅本地**；禁止进 git/视频/PRD |
| 历史 14 目录 / zip | 素材库 | 只读引用（答辩 notebook、答辩脚本范本） |
| `_timo_engine/...` | 确定性引擎源 | 上节点用 Linux 路径重建 venv |
| `deploy/*claude*spark*.py` 等 | 含明文密码的脚本 | **P0 脱敏/移出仓库面**（见风险） |

### 2.3 P0 必做清单

| ID | 任务 | 说明 |
|----|------|------|
| P0-1 | **密钥清理** | `Timo-SSH推理报告.md`、`deploy/install_claude_code_spark.py` 等含节点密码 → 移出工作树交付面或改环境变量；`.gitignore`；答辩材料不出现密码 |
| P0-2 | **版本账** | README/CHANGELOG/MANIFEST/webui/api 与 git 现状对齐策略：提交前 pin（例如 v6.2.0-spark）或明确「以工作树验收报告为准」的一句话口径 |
| P0-3 | **本机基线** | 复跑 `pytest tests/ -q` + `run_demo --offline` + `export_demo` 自检，确认与 ACCEPTANCE-v7 一致 |
| P0-4 | **evidence 目录规范** | 按 PRD §5 建 `docs/evidence/{spark,skills,ab,nvidia}/` |
| P0-5 | **节点信息入脑不入仓** | spark-51 / 6051 / 8051 / 9051；公网仅 8888→8051、9000→9051；无 sudo；aarch64 |

### 2.4 P0 DoD

- [ ] 交付面无明文节点密码  
- [ ] 本机测试/离线 demo 绿且数字有记录  
- [ ] 版本口径一句话写清  
- [ ] evidence 骨架存在  

---

## 3. P1 主体结构（Spark 上把房子立起来）

> 对应 PRD M0–M2。你 SSH 已通；小模型推理已验证；**缺的是 livekernel 本体在节点可跑**。

### 3.1 序列

| ID | 任务 | 命令/动作要点 | 证据 |
|----|------|----------------|------|
| P1-1 | 节点自检归档 | `nvidia-smi; python3 -V; df -h; free -h; docker info` | `evidence/spark/00-env-selfcheck.txt` |
| P1-2 | 代码上节点 | `rsync -avzP -e "ssh -p 6051" livekernel/ Developer@...:~/union-export-agent-livekernel/`（排除 `.git` 大文件/邮箱数据可选） | 同步日志 |
| P1-3 | 引擎路径 | 把 Timo 引擎放到 `/workspace/_timo_engine/...`，节点重建 `.venv`；启用 `config/settings.dgx-spark-p0.yaml` | health `:7862` 或离线 fallback 明确标注 |
| P1-4 | 起 API/Workbench | `host=0.0.0.0` **port=8888**（映射公网 8051）；其余 7862 等用 `ssh -L` | `ss -tlnp` 见 `0.0.0.0:8888` |
| P1-5 | tmux 托管 | 长任务 `tmux new -s uea` | 会话存在 |
| P1-6 | 黄金链/离线 demo | `run_golden_core` 或 `run_demo --offline` 在节点跑通 | `evidence/spark/03-demo-run.log` |
| P1-7 | 公网可达 | 本机浏览器 `http://203.0.113.10:8051`（注意公网需认证红线） | 截图/日志（无密码） |

### 3.2 架构落点（节点）

```
公网评委
   │
   ▼
203.0.113.10:8051  →  节点 0.0.0.0:8888  Workbench/API (livekernel)
                              │
                              ├─ 127.0.0.1:7862  Timo 确定性引擎（隧道调试）
                              ├─ 127.0.0.1:xxxx  节点推理（Qwen3-0.6B / 其后端）
                              └─ data/ audit · contexts · skills/ 33
```

### 3.3 P1 DoD

- [ ] 节点上有可启动的 livekernel  
- [ ] `0.0.0.0:8888` 监听 + 公网或隧道访问证明  
- [ ] 报价路径 health 或离线 byte-identical 演示成功并**如实标注**  

---

## 4. P2 水电（NVIDIA 运行时 + Skills 工程）

### 4.1 模型/平台（诚实边界）

| ID | 任务 | 约束 |
|----|------|------|
| P2-1 | 用好节点已有 **Qwen3-0.6B** | CPU 13 tok/s 可作 FAST 演示；GPU Triton JIT 缺 `Python.h`、无 sudo → **不硬闯** |
| P2-2 | OpenAI-compat 探活 | 在节点起最小 `/v1` 包装或现成推理服务；`models.yaml` / `settings.dgx-spark-p0.yaml` 切 **一条** role |
| P2-3 | NIM | 仅当镜像/权限/显存允许；否则答辩口径「契约+配置已接，现场算力路径=X」 |
| P2-4 | 禁止 | Parakeet 自托管（Blackwell 约束）；MUSA 冒充 NIM；宣称全模型常驻 |
| P2-5 | 官方 NVIDIA/skills | 本机 `npx skills@latest add nvidia/skills --list` 精选；**不**在 Spark 全量安装 |

### 4.2 Skills 工程（评分主粮）

| ID | 任务 | 产出 |
|----|------|------|
| P2-6 | Negative trigger 矩阵 | `evidence/skills/negative-trigger-matrix.md`（先核心 8 个 skill） |
| P2-7 | SKILL.md 补「不触发」 | calc-quote / dfm-conflict / rfq-extraction / verify-gate 等 |
| P2-8 | 负向 pytest | 路由层：无关输入不得触发业务 skill |
| P2-9 | 业务 33 skills | **随仓整包在节点生效**，不走官方 CLI 逐个 add |

### 4.3 P2 DoD

- [ ] Spark 上至少一条模型调用有日志  
- [ ] 核心 skill 有 negative trigger + 负向测试绿  
- [ ] 文档写清 GPU/NIM 真实状态  

---

## 5. P3 精装（Demo、A/B、体验）

| ID | 任务 | 产出 |
|----|------|------|
| P3-1 | 端到端 Demo 脚本对齐 | PASS / HITL / BLOCKED + negative 不触发 + 引擎 sha256 |
| P3-2 | A/B 实验 | `evaluation/metrics.py:ab_report` → `evidence/ab/*.json`（with/without skill 或 LLM vs 正则）；至少一组在 Spark |
| P3-3 | 行为等价 | 同黄金样例：local vs 节点端点；**价格 sha256 必须一致** |
| P3-4 | Workbench 打开路径 | 8051 认证/占位说明；截图进 evidence |
| P3-5 | 录屏/分步 | `record_demo` / 人工；脱敏 |
| P3-6 | （可选）StepFun | 仅当有 key 且不影响主线；否则不承诺 |

### P3 DoD

- [ ] 一份可复现 A/B 报告  
- [ ] 评委路径 5 分钟内能讲完并点开  
- [ ] 价格裁决演示不冷场（在线失败→离线引擎）  

---

## 6. P4 验收（分户验收）

| 检查项 | 方法 |
|--------|------|
| 回归 | 本机全量 pytest；节点至少 golden + 关键 skill 测试 |
| 演示包 | `scripts/export_demo.py` 敏感扫描 0 泄漏 |
| 版本 pin | README/CHANGELOG/MANIFEST/api/webui 一致 |
| 密钥 | 全仓搜节点密码/邮箱授权/NGC key；未跟踪脚本不进提交包 |
| 邮箱数据 | `data/mailbox/*.eml` 等不进开源包 |
| 证据包 | PRD §13 门禁全勾 |
| 覆盖矩阵 | `NCP-AAI-COVERAGE.md` 状态改为「以 evidence 为准」 |

---

## 7. P5 交付上线（交房）

| 交付物 | 内容 |
|--------|------|
| 代码包 | livekernel 干净树（或 export_demo 包）+ MIT + README 快速开始 + Spark 实证入口 |
| 文档包 | PRD-Spark-Submission · DEPLOYMENT · NVIDIA-MAPPING · evidence/* · 验收报告 |
| 演示包 | 录屏或脚本 + 截图帧；公网 URL（8051）+ 隧道备用 |
| 答辩包 | 30 秒/2 分钟口径（PRD §12）；可复用 `00_FINAL_DELIVERABLE/04_答辩与Demo脚本.md` 结构、NCP-AAI notebooks 讲稿 |
| 上线定义 | **不是** SaaS 生产上线，而是：节点可演示 + 提交渠道可交付 + 评委可复现关键证据 |

---

## 8. 全流程甘特（逻辑依赖，非日历）

```
P0 清账 ──┬── P1 Spark 立主体 ── P2 模型/Skills ── P3 Demo/A-B ── P4 验收 ── P5 交付
          │         │                  │
          └─────────┴── 本机基线/脱敏/negative 文档可并行穿插
```

**建议执行批次（确认后我按此开工）**

1. **批次 A（本机，0.5–1 天）**：P0-1~4 + P2-6/7/8 negative 文档与测试  
2. **批次 B（节点，0.5–1 天）**：P1-1~7 把房子立在 Spark  
3. **批次 C（联动）**：P2-1~2 模型切一条 + P3-2 A/B + P3-3 价格等价  
4. **批次 D（收口）**：P4 全门禁 + P5 提交/答辩包  

---

## 9. 风险总表（施工风险）

| 风险 | 等级 | 处置 |
|------|------|------|
| 仓库/脚本明文密码 | **高** | P0 立即处理 |
| 工作树未提交、版本叙事分裂 | 高 | P4 pin；不在未 pin 时宣称正式版 |
| 节点无 sudo / GPU kernel 缺头文件 | 中高 | CPU/离线引擎兜底，诚实口径 |
| 公网端口未认证 | 高（官方红线） | 8051 加简单 token/Basic 再给外人 |
| scp 大文件/共享带宽 | 中 | rsync 排除；节点内下载 |
| A/B 无差异 | 中 | 加负向场景：误触发率、违规拦截 |
| 把 NVIDIA/skills 全量上节点 | 中 | 禁止；白名单≤8 且需进演示 |
| 凭据/客户邮件进提交包 | 高 | export 自检 + 人工扫 |

---

## 10. 指挥棒：谁在什么时候动

| 角色 | 职责 |
|------|------|
| 你（决策者） | 确认本方案；持有节点密码不进聊天/仓库；拍板版本号与是否录视频 |
| 我（执行） | 按批次改仓、写 evidence、出脚本与文档；SSH 操作优先用你本机已配通道或去密钥化脚本 |
| 不动的 | 其它 14 个历史目录；赛期不重写架构 |

---

## 11. 确认清单（你勾选后开工）

请直接回复：**「按方案执行，从批次 A 开始」** 或指出要改的阶段。

- [ ] 接受「只交 livekernel + 主叙事保留 + 实证得分」  
- [ ] 接受阶段划分 P0→P5 与批次 A→D  
- [ ] 接受 P0 优先清密钥与版本账  
- [ ] 接受 Spark 上先 Profile B + 离线兜底，NIM 有则用、无则诚实降级  
- [ ] 接受官方 NVIDIA/skills 不全量上节点  
- [ ] 确认节点业务端口映射：8051/9051（spark-51）  
- [ ] （可选）截止日期与是否必交视频/十日谈  

---

## 12. 一句话

> **地基是清账与叙事锁定，主体是 Spark 上的 livekernel，水电是模型链路与 Skills 负向触发，精装是 A/B 与 Demo，验收是证据门禁，交房是可复现的提交包——全程只维护这一套房。**
