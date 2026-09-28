# CONTRIBUTING.md — 贡献规范

本仓库是 **Union Manufacturing Export Agent** 的唯一 canonical 主干。贡献前请读 `MANIFEST.md` 与 `docs/`。

## 六条工程铁律（不可动摇）

1. **LLM 不负责最终价格** —— 报价/冲突/毛利/状态全部来自确定性引擎（Timo 内核）与 policy/费率表。
2. **State Machine 是业务真相** —— Agent 不能绕过 policy 直接标 DONE。
3. **Context 是全链路唯一业务上下文** —— `context_id` 贯穿证据/审计/CRM/trace。
4. **RAG 提供证据，不改事实** —— 检索结果只作 evidence。
5. **多模态冲突必须升级，不静默覆盖** —— Voice↔Email 关键尺寸不一致 → HITL。
6. **GPU/本地模型是 AI Runtime，不是业务逻辑** —— 后端可切换，上层契约不变。

## 编码约定

- Python 3.11，PEP 8；**禁止硬编码**：端口/路径/费率/阈值一律从 `config/*.yaml` 读取。
- 只用标准库 + 已声明依赖；制造内核重依赖（OCP/cadquery）由引擎 `.venv` 经子进程桥调用，不进主干依赖。
- 降级必须**显式标注**（`_source` / `_mock` / `MOCK:` / `offline:`），绝不把模拟结果冒充生产输出。
- 新技能必须进 `guardrails.TOOL_ALLOWLIST` 并有输入/输出 schema 与失败策略。
- Windows 注意：`set PYTHONUTF8=1`；含中文的 HTTP 请求用 UTF-8（勿依赖 curl -d 的 GBK）。

## 提交前检查（必须全绿）

```bash
python -m pytest tests/ -q          # 95 passed
python scripts/run_demo.py          # 6/6
python scripts/run_demo.py --offline# 6/6 (byte-identical)
python scripts/verify_notebooks.py  # ALL NOTEBOOKS PASS
```

- Commit 遵循 Conventional Commits：`feat:` / `fix:` / `docs:` / `test:` / `refactor:`。
- 改动黄金链/护栏/状态机/商业层必须补对应回归测试。
- 不动 `_foreign_concurrent/`（并发会话隔离物）与外部引擎/funasr 目录。

## 架构边界

- 架构已冻结（`docs/ARCHITECTURE-frozen-v1.0.md`）。**只换 adapter，不换架构。**
-  栈映射与诚实边界见 `docs/GPU-PLATFORM-MAPPING.md`（Parakeet 不支持 Blackwell → P0 用 FunASR）。
