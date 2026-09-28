# v6.0.0 专家测评报告（实测 · 禁止绕过）

**角色**：Python / Agent 工程评审  
**对象**：`union-export-agent-livekernel` 当前工作区（含 v6 FINAL 声称改动）  
**方法**：全量遍历 + **真实 pytest**（非「推理测试」）+ HTTP 抽查 + 代码审计  
**日期**：2026-09-19  
**解释器**：`_timo_engine\...\.venv\Scripts\python.exe`（系统 Python / MIMO_PYTHON **无 pytest**）

---

## 1. 执行摘要

| 项 | 声称（文档/汇报） | **实测** | 判定 |
|----|-------------------|----------|------|
| pytest | 524 passed / 推理 100% | **515 passed · 13 failed · 1 skipped** | ❌ 未达标 |
| Skill 口径 | 25 = 20 独立 + 5 委托 | **SKILL.md=25 · tool.py=24 · 缺 tool.py=`cnc-quote`** | ❌ 数字不准 |
| `@register_function` | 25 skill 全覆盖 | **生产 skill 目录 0 处使用**；仅 `_runtime` 定义 + 单测内联装饰 | ❌ 过度宣称 |
| Guardrails nemo | nemo_soft 可跑 colang | **`_nemo_rails` 可加载但 check_* 从不调用**；未装包时静默降级 builtin | ⚠️ 半成品 |
| NIM 证据 | AgentCache `nvidia:health` + mock 诚实 | 模块与 `/v1/nim/health` **存在**；**force_refresh 缓存语义有测试失败** | ⚠️ 部分 |
| UI 合一 | `:8900/` = 根融合版真接线 | **运行中服务仍吐旧 webui v3.0.1 控制台**；代码路由已改但未重启；**`/css/workbench.css` 404** | ❌ 未生效/静态资源缺失 |
| 版本一致 | v6.0.0 = health/UI/README | health **`v5.1.0-livekernel`**；UI 文件写 v6.0.0；FastAPI `version=2.0-livekernel` | ❌ 三处不一致 |
| 诚实边界 | 不假装 NIM/GPU | mock 字段设计正确；**但 README/UI 自评 8.5 与实测失败不符** | ⚠️ 文档超前代码 |

**总评**：业务内核与大量单测仍健康（515 绿）；**v6「F1–F8 全绿」不成立**。存在 **UI 静态资源未挂载、测试未同步、装饰器未落地、nemo 未真正进检查路径、口径数字错误** 等高优先级缺陷。

---

## 2. 实测环境

```text
工作区: C:\Users\<user>\Desktop\比赛\英伟达第三\union-export-agent-livekernel
pytest: 有（Timo venv pytest 9.1.1）
运行服务: http://127.0.0.1:8900  → /health version=v5.1.0-livekernel
         engine=offline:vendored-kernel(byte-identical)
         multimodal=MOCK:funasr-offline
```

全量命令：

```powershell
$py = "...Timo...\.venv\Scripts\python.exe"
$env:PYTHONPATH = "<livekernel>"
& $py -m pytest tests/ -q --tb=line
```

**结果**：`13 failed, 515 passed, 1 skipped, 2 warnings in 160.26s`

---

## 3. 失败用例清单（13）

### 3.1 UI / 默认入口（10）— 与「根 index.html 顶替 webui」直接相关

| 文件 | 用例 | 现象 |
|------|------|------|
| `test_mailbox_ui.py` | `test_root_serves_workbench_default` 等 7 个 | 断言 webui 特征（`wb-shell`、7 区「图纸」、Demo S1、`window.Mail`…）在 GET `/`；现为融合版 index → **测试未跟着切换** |
| `test_models_api.py` | 3 个 UI 断言 | 同样期望旧控制台 HTML（模型设置 / v2.3.1 / v2.4 tabs） |

**含义**：  
- 若产品决策是「根融合版为唯一入口」→ **必须改这 10 个测试** 或改为读 `webui/index.html` / `/webui`。  
- 若决策是「兼容旧 UI」→ 应用 `/webui` 测 legacy，`/` 测 v6，**不能两套断言打同一 URL**。  
- **当前是「半切换」：代码路由改了、测试与线上进程未改。**

### 3.2 NIM 缓存（1）

`test_nim_health.py::test_cache_hit_on_second_call`  
- 断言 `force_refresh=True` 后 `_cache=="miss"`，实测 **`hit`**。  
- 原因倾向：`AgentCache` 单例/持久化键 `skill_id="nvidia:health"` 与 TTL/加载逻辑导致 **force 路径未真正绕过已有 entry**，或测试隔离不足（`reset_global` 后仍从磁盘/跨用例污染）。  
- **产品影响**：探活「强制刷新」不可信，UI 可能显示过期 NIM 状态。

### 3.3 Schema 校验（2）— **业务正确性缺陷（非 UI）**

| 用例 | 期望 | 实测 |
|------|------|------|
| `test_rfq_bad_tolerance_enum` | `tolerance_grade=IT99` → `valid=False` | **`valid=True`** |
| `test_context_bad_state_enum` | `state=FLYING` → `valid=False` | **`valid=True`** |

→ `services/schema_validator.py` **未对枚举 fail-fast**（或 jsonschema/light 引擎路径与测试契约不一致）。  
→ 这直接削弱「schema mismatch → 拦截」的工程主张，非法状态/公差可能进入下游。

---

## 4. 代码审计缺陷（Bug / 不足）

### P0

| ID | 缺陷 | 证据 | 影响 |
|----|------|------|------|
| **B1** | **静态资源未挂载** | `api_server.py` 无 `StaticFiles`/`mount`；`GET /css/workbench.css` → **404**（实测） | 即便重启服务让 `/` 吐根 `index.html`，页面 **无样式/可能功能残缺** |
| **B2** | **运行时与代码不同步** | 代码 `GET /` 优先根 index；**`:8900/` 仍返回旧 v3 控制台** | 「v6 UI 已上线」在现网为假 |
| **B3** | **版本三套** | health `v5.1.0` · UI 标题 `v6.0.0` · FastAPI `version="2.0-livekernel"` · health 函数硬编码 `v5.1.0-livekernel` | 评审/审计口径混乱 |
| **B4** | **Schema 枚举不生效** | 上表 2 失败 | 非法 RFQ/context 可能通过校验 |
| **B5** | **测试与入口策略冲突未收敛** | 13 失败中 10 个 UI 合同 | CI/回归无法「全绿」 |

### P1

| ID | 缺陷 | 证据 | 影响 |
|----|------|------|------|
| **B6** | **Skill 数字不实** | README/index「20 独立 + 5 委托」；实测 **24 个 tool.py + 1 个无（cnc-quote）** | 答辩按字面核对会翻车 |
| **B7** | **`@register_function` 未在业务 skill 落地** | `grep @register_function skills/**` 仅 `_runtime` 文档字符串；生产 tool.py 无装饰器 | 「NeMo 兼容装饰器全覆盖」不成立；与 autodiscovery **ID 约定还不一致**（装饰器测试用 `write-reply` 连字符，discover 用 `write_reply` 下划线）→ **装饰器覆盖 autodiscovery 的测试场景对真实 skill 无效** |
| **B8** | **nemo_soft「可切换」名不副实** | `Guardrails` 可构造 `LLMRails`，但 `check_input/check_tool/check_output` **从不调用 `self._nemo_rails`**，始终走内置正则 | 即使 `pip install nemoguardrails` 也不产生 NeMo 语义拦截 |
| **B9** | **settings 注释与实现不一致** | yaml 写「切 nemo_soft 需 `UEA_USE_NEMO_GUARDRAILS=1`」；`guardrails.py` **不读该环境变量** | 配置文档误导 |
| **B10** | **NIM `force_refresh` / 缓存语义缺陷** | 测试失败；`cache.set(CACHE_KEY,{},result)` 后原地改 `_cache`，键模型是 `skill_id+args hash` 而非字面 `nvidia:health`（文档/验收写「键 nvidia:health」易误解） | 调试与 UI 缓存指示可能错 |
| **B11** | **`discover(force=True)` 清空 `_REGISTRY` 不清理 `_REGISTER_META`** | `_runtime.discover` | 元数据与注册表可能分叉 |
| **B12** | **UI 能力相对 webui 大幅回退** | 根 index 无模型面板/Skill 设置/Gmail/3D/黄金链 Demo 按钮等（旧测试还在断言这些在 `/`） | 「融合版」名不副实，运维入口丢失 |

### P2

| ID | 缺陷 |
|----|------|
| **B13** | `cnc-quote` 有 SKILL.md + openai_function 契约，**无 tool.py** → registry/dispatcher 无法执行该 id（除非别名映射未在 UI/文档写清） |
| **B14** | 根 index 黄金链步骤名 `PARSE` vs 文档/测试常见 `PARSE_RFQ/INTAKE→CRM` 口径不完全一致 |
| **B15** | `FileResponse(index)` 未 `media_type`/缓存策略；无 `/webui` 与 `/` 的契约测试矩阵更新 |
| **B16** | 文档 `REGRESSION-REPORT-v6.md` / 自评 SER 8.5 **将「文件存在」写成「测试通过」**，与本次实测冲突 |

---

## 5. 摘要：项目还剩什么「真」

**仍然扎实（515 绿覆盖）**

- 大部分业务链路、dispatcher、openshell、golden regression、supplier 模块等基线测试通过。  
- NIM mock **字段设计**（`online/configured/reason=NIM_NOT_CONFIGURED/source=mock`）方向正确。  
- guardrails **builtin 三段**（input/tool/output）逻辑存在且多数护栏测试通过。  
- 铁律叙事（iron-rule-1、draft_only）在代码路径中仍可指认。

**v6 实际增量（按证据）**

| 能力 | 状态 |
|------|------|
| 根 index 真接线 fetch（health/inbox/8 区） | 代码在；**现网未切上 + css 404** |
| `/webui` legacy 路由 | 代码在 |
| `nim_health` + `/v1/nim/*` | 代码在；缓存/force 有缺陷 |
| `register_function` API | 有；**业务未用** |
| `nemo_soft` | **壳**；检查路径未接 |
| README 诚实化 | 改了数字，但 **20+5 仍不对** |
| 测试 | **新增文件在；全量 13 红** |

---

## 6. 推理：为什么会出现「汇报全绿 / 实测 13 红」

1. **用 Read/Grep「推理测试」替代 pytest** → 把「文件存在」当成「断言通过」。  
2. **先改默认 UI 路由，未同步测试矩阵与 StaticFiles** → 入口合同撕裂。  
3. **装饰器/nemo 做了 API 表面，未接入生产调用路径** → 契约对齐评分虚高。  
4. **README/PRD 多份并行**，数字来自一次过时 Glob 而非可重复脚本。  
5. **服务未重启** → 演示环境与仓库 HEAD 脱节。

---

## 7. 测评评分（实测口径）

| 维度 | 汇报分 | **实测分** | 说明 |
|------|--------|------------|------|
| 测试可信度 | 9.0（推理） | **5.5** | 515/528 通过率 97.5%，但存在 P0 失败与假绿叙述 |
| UI 交付 | 9.0 | **3.0** | 现网仍旧 UI；新 UI 静态资源 404 |
| Skill/NemoClaw 口径 | 9.0 | **5.0** | 数量与装饰器落地均偏差 |
| Guardrails/NeMo | 4.5 | **3.0** | builtin 可用；nemo 未进检查路径 |
| NIM 证据链 | 5.0 | **3.5** | mock 诚实；缓存/force/键名需修 |
| Schema/正确性 | — | **4.0** | 枚举校验失效 |
| 文档诚实度 | 9.0 | **6.0** | 有意识写边界，但结论超前于实测 |
| **综合 v6 完成度** | 8.5 | **4.5–5.0** | 路径有，**未闭环** |

---

## 8. 修复优先级（建议执行序）

1. **P0-静态资源**：`app.mount("/css", StaticFiles(directory="css"))`、`/js`（及 index 引用的其它路径）；E2E 打开 `/` 断言 CSS 200。  
2. **P0-入口合同**：二选一写死——A) `/`=v6，`/webui`=legacy，**重写 10 个 UI 测试**；B) 回滚 `/` 到 webui，v6 仅 `/v6`。禁止现状。  
3. **P0-重启并验收** `:8900`：health、`/`、css、inbox 探活截图。  
4. **P0-schema**：修 `schema_validator` 枚举（IT4–IT10、状态机枚举），跑 `test_schema_validation.py` 全绿。  
5. **P0-版本**：health/app/UI/README **统一 v6.0.0**（或统一回 v5.1.0+tag，禁止混用）。  
6. **P1-口径脚本**：`scripts/count_skills.py` 输出 SKILL.md/tool.py/委托，README 只引用脚本结果（当前应类似 **24 tool.py + 1 缺失 = 25 SKILL.md**）。  
7. **P1-装饰器**：统一 skill_id（建议 `folder.replace("-","_")`）并在至少核心 `tool.py` 真正 `@register_function`；`discover` 与 meta 清理对齐。  
8. **P1-nemo**：要么在 `check_*` 调用 `self._nemo_rails.generate/check`，要么文档降级为「预留接口」并删「默认可切实跑」表述。  
9. **P1-nim cache**：`force_refresh` 必须 `invalidate` 或跳过 get；键名文档改为「`skill_id=nvidia:health` 的 LRU entry」。  
10. **P1-全量 pytest**：修 13 红后写入 CI；**禁止再报「推理 100%」**。

---

## 9. 结论（一句话）

**v6 是一次有价值的方向落地（UI 合一入口、NIM mock 诚实字段、skill 补文件、装饰器 API），但远未「FINAL 全绿」：实测 13 failed；现网仍跑旧 UI；新 UI 缺静态资源挂载；Nemo/装饰器/README 数字存在过度宣称。综合完成度约 4.5–5.0/10，需先修 P0 再谈 NVIDIA 契合度 8.5。**

---

## 10. 复现命令（禁止绕过）

```powershell
cd C:\Users\<user>\Desktop\比赛\英伟达第三\union-export-agent-livekernel
$py = "C:\Users\<user>\Desktop\比赛\英伟达第三\_timo_engine\Timo_CNC-AI-Brain-v12.0-Fusion - 副本\.venv\Scripts\python.exe"
$env:PYTHONPATH = (Get-Location).Path
& $py -m pytest tests/ -q --tb=line
# 期望当前: 13 failed, 515 passed, 1 skipped
```

```powershell
curl.exe -s http://127.0.0.1:8900/health
curl.exe -s -o NUL -w "%{http_code}" http://127.0.0.1:8900/css/workbench.css
# 预期现状: health=v5.1.0…  css=404
```
