# 交付包 04 · deploy.ipynb（部署 Notebook）+ 05 · SKILL-PACK.md（Skill 标准包）

## deploy.ipynb 说明
本文件按 Jupyter notebook JSON 格式（nbformat 4.5）编写，单元格可全部直接执行。
内容：从零把项目部署到 DGX Spark 节点（与本文档配套的 12 轮实测部署路径）。

## SKILL-PACK.md（Skill 标准包制作规范 — 对齐 NVIDIA AgentSkills 标准 + 决赛 workshop）

### 一个 Skill = 一个目录
```
skills/<name>/
├── SKILL.md          # frontmatter: name/description/触发词 — "路由表不是百科"
├── tool.py           # run(ctx, **kwargs) -> dict（iron_rule 标注）
├── __init__.py
└── evals/evals.json  # 含负向用例（正确答案是"不调用该 skill"）
```

### 本项目 38 个 skill 的六触点注册（实测口径）
1. SKILL.md frontmatter（YAML 冒号转义注意：曾出过空格致 registry 解析失败）
2. tool.py:run() 契约（OpenAI Function Calling JSON）
3. config/skills.yaml 启停 + Dispatcher 策略
4. config/skill_registry.yaml（policy/core/packs/catalog/quarantine 五区）
5. services/guardrails.py TOOL_ALLOWLIST（白名单外 → BLOCK）
6. openshell/skill-allowlist.yaml（OpenShell 门禁）

### 与官方 NVIDIA/skills 的边界（决赛 workshop 纪律）
- **官方 skill 保持原样**：固定上游提交，skill-card.md/签名/评测/benchmark 完整保留——改了内容原签名即失效
- **环境差异 → 适配层**（workspace/tools/run-official-skill.sh 处理本地端点）
- **业务逻辑 → 自研 skill**（走上面六触点）
- 验证命令：`model_signing verify --certificate ... --signature SKILL_DIR/skill.oms.sig`
- 安装：`npx skills@latest add nvidia/skills -s <skill> --yes`（需 skills CLI v1.5.16+）

### 窄触发、强路由（skill 设计三原则）
1. 一个 skill 只管一类事（省 token 且不误伤）
2. description 写清"什么时候触发/什么时候不触发"
3. evals 必须含"不该触发"的负向用例
