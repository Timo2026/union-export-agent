# Evidence Pack · Spark 实证落盘约定

> 本目录是 PRD §5「评分映射与证据包」的物理落点。**赛时一切平台/Skills/A-B 主张，缺证据即降级。**
> 密级：公开。**禁止**写入节点密码、登录表、NGC_API_KEY、客户真实账密。

## 目录结构与必含证据

```
docs/evidence/
  spark/
    00-env-selfcheck.txt      # nvidia-smi / python3 -V / docker info / df -h / free -h
    01-service-health.txt     # curl :7862/api/health :8866/health :8900/ NIM /v1/models
    02-public-or-tunnel.md    # 公网 :80NN 映射 或 ssh -L 隧道说明（无密码）
    03-demo-run.log           # 黄金链在 Spark 上实跑日志
  skills/
    negative-trigger-matrix.md   # 核心 skill 何时触发 / 何时禁止 / 误触发后果
    negative-pytest.txt          # 负向用例 pytest 输出
  ab/
    ab-report-skills-on-off.json   # with skills vs without skills
    ab-report-llm-vs-regex.json    # LLM 抽取 vs 正则抽取
    ab-report-readme.md            # 每份 JSON 一句话解读，连到「可验证商业价值」
  nvidia/
    nim-smoke.txt              # python services/nim_smoke.py 或 curl /v1/models
    models-yaml-diff.md        # models.yaml 切 NIM/local 前后对照
```

## 采集纪律

1. 每个证据文件顶部写明：采集时间（节点时区）、节点号（仅编号，如 `spark-07`，不含 IP/密码）、采集命令。
2. 端口/隧道说明里**只写映射关系**（如 `节点 8888 → 公网 80NN`），**绝不**写 SSH 密码或私钥。
3. 任何含凭据的日志先打码再落盘；不确定就先空着标 `[REDACTED]`。
4. 降级路径要**显式标注**：NIM 拉不起 → 写明 `degraded: local OpenAI-compat`，不冒充实跑。
