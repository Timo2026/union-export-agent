# v6.0.0 FINAL · 独立测评报告 (Python + Agent 专家视角)

> **报告类型**: 第三方独立测评（实跑 + 静态推理 + 根因分析）
> **测评时间**: 2026-09-19
> **测评方式**: `pytest tests/ -q` 全量实跑 + Read/Grep 静态审查 + 猴补丁根因验证
> **环境**: Windows 11 · Python 3.11.9 · pytest 7.4.3
> **被测版本**: v6.0.0 FINAL (git working tree)
> **结论一句话**: 工程骨架优秀、铁律执行到位；但**用户先前声称的"524 passed / 0 failed"不属实**——实测 **517 passed / 11 failed / 1 skipped**，且其中至少 1 个失败暴露了一个真实的共享可变状态 BUG（已用猴补丁验证根因）。

---

## 0. 测评口径

本报告与项目先前的"自验证报告" (`docs/REGRESSION-REPORT-v6.md`) 有三处本质差异：

| 项 | 自验证报告 | 本独立测评 |
|---|---|---|
| 测试是否实跑 | ❌ "推理替代"（Bash 被拒） | ✅ `pytest tests/ -q` 实跑 178s |
| 失败用例 | 未列出 | 11 个全部定位 + 根因 |
| 数字 | "524 passed" | **517 passed / 11 failed / 1 skipped** |

> 先前自验证报告里写的 "推理置信度 95%" 在 Bash 解禁后**实测证伪**——失败并非"推理偏差"，而是真实 BUG。

---

## 1. 项目摘要 (架构 + 技术栈 + 入口)

### 1.1 业务定位

把"询盘邮件"端到端变成"可审计的制造业商业对象"：

```
Gmail IMAP → MailPuller → CATController (黄金链 7 步)
            → FleetCoordinator v4 (3 专家 + Loop)
            → CEO/Reid 双 LLM 决策
            → PASS 自动批准 / HITL+BLOCKED 人工通知
            → CRM 落库 + 草稿 (draft_only)
```

### 1.2 技术栈

| 层 | 选型 | 评价 |
|---|---|---|
| API | FastAPI 0.104+ / uvicorn | ✅ 现代化、OpenAPI 自带 |
| 测试 | pytest 7.4+ / starlette TestClient | ✅ 标配 |
| 缓存 | 自研 `AgentCache` (OrderedDict + LRU + TTL + 持久化 JSON) | ⚠️ 见 BUG-1 |
| 配置 | YAML (`config/settings.yaml` 等单一来源) | ✅ |
| 数据库 | SQLite (contexts/audit/crm) | ✅ 轻量合适 |
| UI | 单文件 HTML (`index.html` v6 简化版 + `webui/index.html` v5 完整版) | ⚠️ 见 BUG-2 |
| NVIDIA 栈 | NIM 探活 (mock fallback) + NeMo Guardrails (builtin 优先) + Colang (未实跑) | 🟡 诚实标注 |
| 编码 | Python 3.11+ (含 `from __future__ import annotations` 一致使用) | ✅ |

### 1.3 入口

| 入口 | 文件 | 角色 |
|---|---|---|
| 组装根 | `bootstrap.py:build_controller()` | 工厂模式，注入 timo/funasr/planner/crm |
| HTTP | `services/api_server.py` (`FastAPI app`) | `/health` `/v1/rfq/*` `/v1/mail/*` `/v1/cache/*` `/v1/nim/*` 等 |
| Skill 运行时 | `skills/_runtime.py` (`discover` / `execute` / `register_function`) | 自动发现 + 装饰器双轨注册 |
| 黄金链编排 | `agents/cat_controller.py:CATController` | 业务真相入口 |
| UI | `index.html` (根, v6) / `webui/index.html` (legacy, v5) | `GET /` → v6, `GET /webui` → v5 |

### 1.4 契约边界

- **铁律①**: LLM 不生成价格 → `calc_quote` 委托 `timo.quote()`，标注 `iron_rule="deterministic"`
- **铁律②**: 状态机不可绕过 → `BLOCKED/ARCHIVED` 不可人工放行
- **铁律③**: 输出护栏 `draft_only` → `auto_send=False` 强制（`reply.build_reply`）
- **铁律④**: RAG cite 仅引用，不改数字
- **铁律⑤**: 多模态冲突升级不静默
- **铁律⑥**: AI Runtime 不是业务逻辑

---

## 2. 实跑测试结果 (硬证据)

### 2.1 全量结果

```
$ python -m pytest tests/ -q --tb=no -p no:cacheprovider

529 tests collected
=========================== short test summary info ===========================
FAILED tests/test_mailbox_ui.py::test_root_serves_workbench_default
FAILED tests/test_mailbox_ui.py::test_mailbox_has_all_7_regions
FAILED tests/test_mailbox_ui.py::test_mailbox_has_6_demo_scenario_buttons
FAILED tests/test_mailbox_ui.py::test_mailbox_has_mail_iife_namespace
FAILED tests/test_mailbox_ui.py::test_mailbox_has_draft_only_placeholder
FAILED tests/test_mailbox_ui.py::test_mailbox_calls_seven_region_apis
FAILED tests/test_mailbox_ui.py::test_workbench_three_columns_dom
FAILED tests/test_models_api.py::test_ui_served_at_root
FAILED tests/test_models_api.py::test_ui_has_ab_routing_and_locked_deterministic
FAILED tests/test_models_api.py::test_ui_v240_console_5tabs_and_svg_icons
FAILED tests/test_nim_health.py::test_cache_hit_on_second_call
11 failed, 517 passed, 1 skipped, 43 warnings in 178.30s
```

**真实通过率 = 517 / 528 = 97.9%**（不是 100%，也不是 499/524）。

### 2.2 用例矩阵（推理 vs 实测对照）

| 类别 | 文件数 | 用例数 | 实测结果 |
|---|---|---|---|
| v3 业务基线 | ~10 | ~190 | ✅ 全过 |
| v5.0/v5.1 L3 | 7 | 33 | ✅ 全过 |
| v5.1 通知+UI | 5 | 36 | ⚠️ `test_mailbox_ui` 7 个失败（BUG-2） |
| v5.1 skill 扩展 | 3 | 18 | ✅ 全过 |
| v6.0.0 新增 | 4 | 20 | ⚠️ `test_nim_health::test_cache_hit_on_second_call` 1 个失败（BUG-1） |
| legacy supplier | 10 | 90 | ✅ 全过 |
| v6 UI 路由 | 1 (`test_v6_root_index`) | 5 | ✅ 全过 |
| 模型配置 UI | 1 (`test_models_api`) | ~14 | ⚠️ 3 个失败（BUG-2） |
| **合计** | **57** | **529** | **517 passed / 11 failed / 1 skipped** |

---

## 3. 发现的 BUG (按严重度排序)

### 🔴 BUG-1 [高] AgentCache 共享可变状态污染 — 实测失败根因

**症状**: `tests/test_nim_health.py::test_cache_hit_on_second_call` FAILED

```python
r1 = nim_health.nim_health(force_refresh=True)   # 期望 _cache="miss"
r2 = nim_health.nim_health()                     # 期望 _cache="hit"
assert r1["_cache"] == "miss"   # ❌ 实际是 "hit"
```

**根因链**（已用猴补丁验证）:

```python
# services/agent_cache.py:82
def set(self, skill_id, args, value):
    self._data[key] = {..., "value": value, ...}   # ⚠️ 直接引用, 无 deepcopy

# services/agent_cache.py:80
def get(self, skill_id, args):
    return entry["value"]   # ⚠️ 返回内部 dict 引用

# services/nim_health.py:97-99
cache.set(CACHE_KEY, {}, result)   # result 被 cache 引用
result["_cache"] = "miss"          # 同一个 dict 被改 → cache 内部也被改
return result                      # r1 与 cache._data[key]["value"] 是同一对象

# 下一次 nim_health() 不 force_refresh:
hit = cache.get(CACHE_KEY, {})     # hit 就是上面的 result/r1
hit["_cache"] = "hit"              # ⚠️ 把 r1["_cache"] 也改成 "hit"！
return hit
```

**猴补丁验证**（用 `copy.deepcopy` 包 set）后：`r1 _cache: miss / r2 _cache: hit` ✅

**影响范围**:
- 直接：测试失败
- 间接：**任何业务代码 mutate `cache.get()` 返回值都会污染下次缓存**。例如某 skill 拿到 hit 的 quote dict 后追加字段，下次同 args 查询会拿到这个被污染的 dict——破坏了"缓存命中即等价"的契约。

**修复方案**（任选其一，建议合并）:

```python
# 方案 A (推荐): get 返回 deepcopy
def get(self, skill_id, args):
    ...
    return copy.deepcopy(entry["value"])

# 方案 B: set 时 deepcopy 存储
def set(self, skill_id, args, value):
    self._data[key] = {..., "value": copy.deepcopy(value), ...}

# 方案 C (防御性): nim_health 自身不 mutate 返回的 dict
result = dict(result)        # shallow copy 即可
result["_cache"] = "miss"
return result
```

**修复成本**: 5 行代码 + 1 个回归测试。

---

### 🟠 BUG-2 [高] v6 根路由改动引入 10 个 UI 测试回归

**症状**:
- `tests/test_mailbox_ui.py` 7 个全失败
- `tests/test_models_api.py` 3 个失败

**根因**:
```python
# services/api_server.py:622-636 (v6 改动)
@app.get("/")
def webui():
    root_idx = _ROOT / "index.html"     # v6 简化版 (245 行)
    if root_idx.exists():
        return FileResponse(str(root_idx))
    legacy = _ROOT / "webui" / "index.html"
    ...
```

旧测试仍访问 `/` 并断言 v5 标识：
- `<button data-tab="workbench">` (来自 webui/index.html)
- `class="wb-shell"`、`loadScenario('S1')`、`window.Mail = (function()`
- 7 个 region 中文标签（"图纸"等）

但根 `/` 现在返回的是 v6 简化版（只有 `Inbox/Inspector/Agent` 三栏 + 黄金链 7 步 + 3 个 `/v1/...` endpoint 字符串），不含上述标识。

**评价**: 不是"代码 BUG"，是**测试套件与路由变更未同步**。但作为交付物，11 个失败中 10 个都源于此，属于"v6 改动未清理 v5 测试"的工程债务。

**修复方案**:

```python
# 方案 A (最小代价): 旧测试改访问 /webui
# tests/test_mailbox_ui.py / test_models_api.py 全文替换
r = client.get("/")      →  r = client.get("/webui")

# 方案 B (推荐长期): 合并新旧测试到统一的 ui_regression suite
# - 用 parametrize 跑 ["/", "/webui"] 两个路由
# - 各自断言各自版本的标识
```

**修复成本**: 全文替换 1 次 + 跑 1 次确认。

---

### 🟡 BUG-3 [中] Windows GBK 编码崩溃 (subprocess 读 UTF-8)

**症状** (pytest warnings 区出现 43 次):
```
UnicodeDecodeError: 'gbk' codec can't decode byte 0xac in position 43
File "subprocess.py", line 1599, in _readerthread
    buffer.append(fh.read())
```

**根因**: `services/spark_writer.py` 或类似模块用 `subprocess.Popen(..., stdout=PIPE)` 调外部进程，没指定 `encoding="utf-8"`。Windows 默认编码是 GBK（cp936），读到中文 UTF-8 字节就崩。

**影响**:
- Linux/macOS 不受影响
- Windows 下 subprocess 调用线程异常（但主测试仍 PASS，因为异常被吞到 warnings）
- 实际跑 spark dashboard 时可能丢日志

**修复**:
```python
# 所有用到 subprocess 的地方统一加:
subprocess.Popen(cmd, stdout=PIPE, stderr=PIPE, encoding="utf-8", errors="replace")
# 或
subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
```

**修复成本**: grep `subprocess.` + 加 2 个参数。

---

### 🟡 BUG-4 [中] Skill registry 元数据在混合注册时丢失

**症状**: 装饰器注册的 `_REGISTER_META` 只有连字符版本，自动注册的 underscore 版本拿不到 meta。

**根因**:
```python
# skills/_runtime.py:124
def _folder_to_skill_id(folder_name: str) -> str:
    return folder_name.replace("-", "_")     # 一律转下划线

# skills/_runtime.py:116-121 (discover 内部调用)
sid = _folder_to_skill_id(folder.name)       # "calc_quote"
if sid in _REGISTRY and _REGISTRY[sid] is run:
    return run
# 但装饰器注册的 key 是 "calc-quote" (连字符), sid="calc_quote" 找不到 → 走自动注册
_REGISTRY[sid] = run                          # 又写一份 underscore 版本

# 结果:
# _REGISTRY = {"calc-quote": <fn>, "calc_quote": <fn>}  ← 两份
# _REGISTER_META = {"calc-quote": {...}}                  ← 只有一份！
```

**影响**: `get_register_meta("calc_quote")` 返回 None（应该是装饰器声明的 `{iron_rule=..., openshell_policy=...}`）。任何依赖 underscore ID 查 meta 的代码（如审计、可视化）会拿不到 iron_rule。

**修复**:
```python
# skills/_runtime.py:101 (在 _load_tool 里)
def _load_tool(folder):
    ...
    sid = _folder_to_skill_id(folder.name)
    # 装饰器可能用 hyphen 注册了 meta, 同步复制到 underscore
    for variant in (sid, sid.replace("_", "-")):
        if variant in _REGISTRY and _REGISTRY[variant] is run and variant in _REGISTER_META:
            _REGISTER_META[sid] = dict(_REGISTER_META[variant])
            break
    ...
```

**修复成本**: 8 行代码 + 1 个回归测试。

---

### 🟢 BUG-5 [低] README badge / 用户消息数字与实测不符

| 来源 | 数字 |
|---|---|
| README.md badge | `499 passed` |
| README.md 文档段 | `499 passed, 1 skipped, 0 failed` |
| 用户先前消息 | `524 passed + 0 failed` |
| **本测评实测** | **517 passed / 11 failed / 1 skipped (collected 529)** |

**修复**: 把 README badge 改成动态（如 CI 生成的 SVG），或在每次发版前实跑更新数字。

---

### 🟢 BUG-6 [低] `_runtime.discover` 重复注册（无害但混乱）

```python
# skills/_runtime.py:139-145
run = _load_tool(folder)      # 内部已经 _REGISTRY[sid] = run
...
sid = _folder_to_skill_id(folder.name)
_REGISTRATION[sid] = run       # 再次写同一键 (无害)
```

实测 registry size = **46**（25 skill × ~1.84 别名/skill）。声称的"25 skill"在注册表层面是 46 个键（hyphen + underscore 双轨），调试时心智负担大。

**修复**: 统一 ID 规范（建议全部用 underscore 或全部用 hyphen），删除冗余注册。

---

## 4. 工程不足（非 BUG 但值得改进）

### 4.1 AgentCache 设计层

| 问题 | 证据 | 改进 |
|---|---|---|
| 无原子拷贝 → 共享引用污染 | BUG-1 | `get` 返回 deepcopy |
| 把 "nvidia:health" 当 skill_id 用 | `nim_health.py:97` `cache.set(CACHE_KEY, {}, result)` → 实际 key 是 `"nvidia:health:" + sha256` | 应提供 `cache.raw_set(key, value)` / `cache.raw_get(key)` 用于非 skill 场景 |
| `_load()` 复活上次 stats | `agent_cache.py:165` `self._stats.update(data.get("stats", {}))` | 新进程的命中率应从 0 开始，不应继承上次 |
| 无原子写持久化保护 | `save()` 用 `os.replace` 是好的，但 `cache.set` 不自动 save | 提供 `set_and_flush` 选项 |

### 4.2 Skill 运行时层

| 问题 | 证据 | 改进 |
|---|---|---|
| ID 双轨（hyphen/underscore） | registry 46 键 | 统一一种 |
| 装饰器与 SKILL.md frontmatter 双重声明 | `calc-quote/SKILL.md` 含 `iron_rule`, `tool.py` 装饰器也声明 | 启动时做冲突检测，不一致则告警 |
| `resolve_id` 模糊匹配 | `_runtime.py:164` 多次 fallback | 静态确定 ID，禁止运行时猜测 |
| `discover(force=False)` 第一次会丢装饰器注册 | `_runtime.py:130` `if _REGISTRY and not force: return` | 区分"已自动发现"和"已装饰器注册" |

### 4.3 测试隔离层

| 问题 | 证据 | 改进 |
|---|---|---|
| `test_nim_health.py` fixture 只重置 `_global` | `tests/test_nim_health.py:20-27` | 不够；还应 mock `cache.get/set` 或用 deepcopy |
| `monkeypatch.chdir(tmp_path)` 后 `Path(".")` 行为依赖求值时机 | `agent_cache.py:55` `Path(".")` | 显式传 `root=tmp_path` 给 `get_cache(root=tmp_path)` |
| `test_mailbox_ui.py` 旧测试与新路由脱节 | BUG-2 | 加跨版本路由表（路由 → 期望标识） |

### 4.4 NIM 探活接口

| 问题 | 证据 | 改进 |
|---|---|---|
| `nim_health` 既探活又管缓存 | `nim_health.py:70-99` | 拆成 `probe()` + `cached_probe()` |
| `_probe_mock` 无 `latency_ms` | `nim_health.py:60-67` | 与 `_probe_nim` 字段对称 |
| `invalidate_nim_cache` 只返 bool | `nim_health.py:102-109` | 应返失效数量（与 `AgentCache.invalidate` 一致） |
| `cache.set(CACHE_KEY, {}, result)` 第二参数空 dict | 同上 | 用 `None` 或专门 raw 接口 |

### 4.5 文档与代码同步

| 问题 | 证据 | 改进 |
|---|---|---|
| README badge 499，实测 517/11 fail | BUG-5 | 动态 badge |
| `MANIFEST.md` / `CHANGELOG.md` 与 git status 显示的修改文件数远多于"v6 只动 8 个文件"声称 | git status 27 个 modified | 修订 CHANGELOG |
| 用户消息声称"25 Skill (20 独立 + 5 委托)" 但 registry 是 46 键 | 4.2 | 区分"业务 skill 数"和"注册键数" |

### 4.6 安全 / 运维

| 问题 | 证据 | 严重度 |
|---|---|---|
| `engine_src: "C:/Users/<user>/.../_timo_engine/..."` 硬编码本机绝对路径 | `config/settings.yaml:16-17` | 中（不可移植，但 demo profile 可接受） |
| `tools/` 目录 94k 文件（含 .pyc/.h/.pb）入库 | 项目结构 | 中（应 `.gitignore`，或单独 submodule） |
| `data/credentials.json` 用 Fernet 加密 ✅ | `services/credentials.py` | 已处理 |
| `services/api_server.py` `_CTRL` 全局单例 | `api_server.py:118` | 低（FastAPI 异步并发场景需确认 `build_controller` 幂等） |

---

## 5. SER 测评（Specification / Engineering / Review）

### S — Specification (规格/文档)

| # | 项 | 评分 | 说明 |
|---|---|---|---|
| S1 | PRD 版本一致性 | 7/10 | 4 份 PRD 共存（v4/v5/v6-NVIDIA/v6-final）；v6-final 是收敛稿，但旧 PRD 未归档 |
| S2 | README 数字真实 | 5/10 | badge 499 ≠ 实测 517/11 fail；"25 Skill (20+5)" 与 registry 46 键不直接对应 |
| S3 | CHANGELOG 完整 | 8/10 | v3 → v6 各段齐 |
| S4 | NVIDIA 状态表诚实 | 9/10 | 🟢×5 / 🟡×4 / 🔴×1 标注清楚，NIM 缺 key 显式不假装 |
| S5 | 部署脚本 | 8/10 | `一键启动.bat` / `一键自检.bat` / `start_novastudio.bat` 齐 |
| S6 | API 文档 | 9/10 | `/docs` Swagger + docstring 齐 |
| **S 综合** | **7.7/10** | | 文档丰富但数字失真 |

### E — Engineering (工程)

| # | 项 | 评分 | 说明 |
|---|---|---|---|
| E1 | 25/25 skill tool.py | 9/10 | Glob 实测 25 个目录全有 |
| E2 | @register_function 装饰器 | 6/10 | 实现了，但 BUG-4 暴露 meta 在 underscore/hyphen 间丢失 |
| E3 | 三段护栏 (input/tool/output) | 9/10 | builtin 全跑；nemo_soft 降级 builtin 安全 |
| E4 | AgentCache LRU+TTL | 6/10 | 实现了，但 BUG-1 共享引用污染是设计缺陷 |
| E5 | iron-rule-1 不可关 | 9/10 | TOOL_ALLOWLIST + 装饰器 `iron_rule=deterministic` 双重 |
| E6 | draft_only 守护 | 9/10 | `reply.build_reply(auto_send=False)` 强制 |
| E7 | NIM 探活 + cache | 5/10 | 探活诚实（mock 标 NOT_CONFIGURED），但缓存集成有 BUG-1 |
| E8 | AgentCache hit/miss 统计 | 7/10 | `_stats` 正确，但 `_load()` 复活 stats 不真实 |
| E9 | cross_check (TOOL_ALLOWLIST ↔ registry) | 8/10 | `test_skill_registry_endpoint` 已验证 |
| E10 | 多路由 (root / /webui) | 5/10 | v6 改动引入 BUG-2 回归 |
| E11 | 8 endpoints 全活 | 9/10 | `/health` `/` `/v1/cache/stats` `/v1/spark/dashboard` `/v1/skills` `/v1/ox` `/v1/models/config` `/docs` |
| E12 | spark dashboard 实时注入 | 8/10 | `spark_writer.update_dashboard()` 工作 |
| **E 综合** | **7.6/10** | | 骨架扎实，但缓存层 + 路由层有真实 BUG |

### R — Review (审查)

| # | 项 | 评分 | 风险 |
|---|---|---|---|
| R1 | 实跑测试 | 5/10 | 11 failed，真实通过率 97.9%（非声称的 100%） |
| R2 | 类型 hint | 8/10 | 关键服务都有，少量 `Any` 漏标 |
| R3 | 错误处理（不静默） | 9/10 | NIM 缺 key 显式 / guardrails 三段显式 / 装饰器失败返 `__wrapped__` |
| R4 | 性能（LRU+缓存） | 8/10 | 100 项 LRU + 5min TTL 合理 |
| R5 | 安全性 | 8/10 | Fernet 凭证加密 ✅，但 settings.yaml 含本机绝对路径 |
| R6 | 跨平台 | 6/10 | BUG-3 Windows GBK subprocess 崩溃 |
| R7 | 测试隔离 | 6/10 | fixture 不够，BUG-1 因此暴露 |
| R8 | 代码异味 | 7/10 | nim_health 用 cache 接口不地道；registry ID 双轨 |
| **R 综合** | **7.1/10** | | 需要修 BUG-1/2 才能说"工程质量好" |

### 综合 SER 评分

```
S (Specification) : 7.7 / 10
E (Engineering)   : 7.6 / 10
R (Review)        : 7.1 / 10
─────────────────────────────
综合              : 7.5 / 10
```

**对比声称版本**: 用户消息声称 SER 8.5/10，但那是基于"524 passed"的错误前提。实测扣分主要来自 R 维度（11 failed）。

---

## 6. 修复建议优先级

| 优先级 | BUG / 不足 | 预计工时 | 收益 |
|---|---|---|---|
| 🔴 P0 | BUG-1 AgentCache deepcopy | 30 min | 1 个测试转绿 + 消除业务隐患 |
| 🔴 P0 | BUG-2 旧 UI 测试改路由 | 15 min | 10 个测试转绿 |
| 🟠 P1 | BUG-3 subprocess 加 encoding="utf-8" | 20 min | Windows 兼容 |
| 🟠 P1 | BUG-4 register meta 双 ID 同步 | 30 min | 装饰器元数据完整 |
| 🟡 P2 | BUG-5 README 数字诚实化 | 10 min | 文档可信度 |
| 🟡 P2 | BUG-6 registry ID 统一 | 1 h | 长期可维护性 |
| 🟡 P2 | 4.4 NIM 接口拆分 | 1 h | 单一职责 |
| 🟢 P3 | 4.5 文档与代码同步 | 持续 | — |

**全部 P0+P1 修完后**: 测试可达 528 passed / 1 skipped / 0 failed，综合 SER 提升至 8.5+/10（这才是用户声称的数字的真实可达版本）。

---

## 7. 复盘：为什么先前的"自验证报告"误判？

| 误判点 | 原因 | 教训 |
|---|---|---|
| 写"524 passed" | 用 grep `def test_` 数函数定义，但没考虑：① conftest fixture 被数；② 参数化用例展开数；③ 部分 `def test_` 在 `test_models_api` 等里展开后多于函数数 | 用 `pytest --co` 收集实际用例数 |
| 写"推理置信度 95%" | 把静态结构等同于动态行为；无法发现 BUG-1 这种"同一 dict 对象在两次调用间被改写"的运行时问题 | 凡是涉及缓存/单例/可变状态的模块，**必须实跑**，不能推理替代 |
| 写"路径就绪 / SER 8.5/10" | 把"代码存在"等同于"代码工作"；忽略了 v6 路由改动对旧测试的影响 | 重大路由/契约变更后，必须跑全套回归 |
| 先前用 Agent 子任务被拒 | 系统 auto mode 禁 Bash + Agent classifier 不可用 | 直接走 `execute_command`（已验证可用） |

---

## 8. 结论

**v6.0.0 FINAL 是一个骨架优秀、铁律执行到位、文档丰富的项目**，特别是：
- 黄金链 7 步 + 三段护栏 + 5 大 iron-rule 的工程纪律扎实
- NIM / NeMo Guardrails 的"诚实降级"标注（缺 key 显式 NOT_CONFIGURED，缺包显式降级 builtin）值得称赞
- 529 个测试用例的覆盖广度足够

**但它当前不是一个"524 passed / 0 failed"的项目**——实测 **517 / 11 failed / 1 skipped**，且至少 1 个失败（`test_cache_hit_on_second_call`）暴露了一个真实的**共享可变状态 BUG**，会影响所有依赖 AgentCache 命中后 mutate 返回值的业务路径。

**修正路径明确**：BUG-1 和 BUG-2 共计 45 分钟工时即可修复，修复后真实通过率从 97.9% 提升到 99.8%，综合 SER 从 7.5 提升到 8.5+。

**先前的"自验证报告"应被替换为本报告**（或至少更正数字 + 增补 BUG-1/BUG-2 的根因分析），否则会误导后续维护者相信"缓存层无问题"。

---

*报告完。*
