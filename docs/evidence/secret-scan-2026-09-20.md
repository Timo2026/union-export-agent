# 密钥清污只读核查报告（2026-09-20）

> 范围：提交主体 `union-export-agent-livekernel` 工作树 + git 全历史。**只读核查，未改动/未删除任何文件。**
> 结论先行：**git 历史干净**；工作树有 **1 项必须处置**（5 个 deploy 脚本含节点登录口令明文）+ **2 项打包必须排除**（真实 QQ 邮件、凭据库）。

## 1. 核查矩阵

| 对象 | 状态 | 证据 |
|------|------|------|
| git 历史 · `data/credentials.json` | ✅ 从未入库 | `git log --all -- data/credentials.json` 空 |
| git 历史 · `deploy/*claude*spark.py`（5 个含口令脚本） | ✅ 从未入库 | `git log --all -- "deploy/*claude*spark*.py"` 空 |
| `data/credentials.json`（QQ 邮箱凭据） | ✅ Fernet 加密（cipher 120 字符）+ masked 展示；已被 `.gitignore:44` 排除 | 结构只读巡检：`/services/qq/{account,encrypted,cipher,masked}`，无明文 |
| NGC_API_KEY | ✅ 全树仅 `${ENV}` 引用与占位；`.env.example` 占位受测试锁定 | grep 全树 + `test_nim_secrets_env_only_no_hardcoded_keys` |
| `deploy/nim/.env.example` | ✅ 占位模板（`paste-your-...`），无真值 | 测试断言逐行扫 |
| `tools/`（含 ragflow `.env` 28 行密码） | ✅ 整目录 `.gitignore:67` 排除 | `git check-ignore -v tools/ragflow/docker/.env` |
| `data/*.sqlite3` / contexts / traces / artifacts / crm_sandboxes | ✅ `.gitignore:29-31` 排除 | `git check-ignore -v data/audit.sqlite3` |
| `data/mailbox/demo_test_001.eml`（已入库） | ✅ 合成数据（alice@acme.com → sales@union.io） | 头只读检查 |
| `services/mail_puller.py:185` | ✅ `"INJECTED"` 为测试注入标记，非密钥 | 上下文只读 |

## 2. 必须处置（user 决策，本任务未动）

### 2.1 🔴 节点登录口令明文（最高优先）
- 位置：`deploy/{diag,fix,install,finalize,verify}_claude_path_spark.py` 第 9 行，5 处同值 `PWD = "<spark-51 登录口令>"`（值不在此复述）
- 状态：**未入 git**，但**未被 .gitignore 覆盖** → `git add -A` 会误入库；目录拷贝式打包会泄露
- 建议动作（按序）：
  1. **轮换 spark-51 登录口令**（该值已在多人会话中流转，按泄露处置）
  2. 5 个脚本改读环境变量 `os.environ["UEA_SPARK_PWD"]`（或删除这些一次性脚本——它们是 Claude Code 安装排障产物，非交付资产）
  3. `.gitignore` 增加 `deploy/*claude*spark*.py` 或改放 `deploy/local/`
  4. **补测试缺口**：`test_deploy_no_hardcoded_secret_assignments` 的 pattern 只匹配 `API_KEY|TOKEN|PASSWORD|AUTH` 关键词，`PWD = "..."` 不在其列——这就是明文口令活到今天的原因。建议 pattern 增加 `(?:PWD|PASS|PASSWD|SECRET|CREDENTIAL)`。

### 2.2 🟡 真实邮箱数据在工作树（打包排除，勿入库）
- `data/mailbox/qq_*.eml` + `.meta.json`（14 封真实 QQ 邮件，含小米通知等个人邮件）、`data/mail_puller/{pending.jsonl,state.json}`、`data/customers/`、`data/backups/`、`data/_d4_extract/`
- 均未入库；**交付包必须排除**（与 PRD §4.8 门禁「无明文节点密码/NGC key/邮箱授权进交付包」对齐）

### 2.3 🟢 已由 gitignore 兜住（无需动作，打包时复核）
- `data/credentials.json`（加密态也在打包时排除——铁律 data-stays-local）
- sqlite3 / contexts / traces / artifacts / crm_sandboxes / tools/

## 3. 交付包打包口径（建议）

```
git archive HEAD | tar -x -C build/     # 唯一安全打包方式 (git 历史已验干净)
# 禁止: 目录拷贝 / git add -A (会带入 2.1/2.2 未排除项)
```

## 4. 复查命令（只读）

```bash
git log --all --oneline -- data/credentials.json "deploy/*claude*spark*.py"   # 应空
git ls-files data/ | grep -vE "knowledge|golden|eval|flywheel|samples|sandboxes|mailbox/(README|\.gitkeep|demo_test)"  # 应只剩白名单
grep -rIn --exclude-dir=tools --exclude-dir=.git -E "^(PWD|PASS|TOKEN|SECRET)\s*=\s*[\"'][^\"']{4,}" --include="*.py" .  # 应只剩 5 处 (轮换后为 0)
```
