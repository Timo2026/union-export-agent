# EMAIL_SUBSYSTEM.md — 邮件子系统（IMAP 拉取 / 草稿回复 / 出网关）

## 架构
```
IMAP (imap.qq.com / imap.gmail.com) 
  → MailPuller (services/mail_puller.py · 30s 轮询 · 文件锁 · 退避表)
  → pending.jsonl (状态机: NEW→PROCESSING→DONE/HITL/BLOCKED/SKIPPED/FAILED)
  → MailClassifier (询价/非询价/灰区 — 负标记过滤, 退信/发票/广告自动拦)
  → CATController 黄金链 (报价 → 草稿 + PDF/XLSX 附件)
  → HITL 人工确认 → egress 闸 → SMTP(可选)
```

## 实测数据（2026-09）
- **130 封**真实邮件自动拉取 · consecutive_failures=0 · last_pull 间隔 30s
- 分类实况：SKIPPED 76（非询价）/ DONE 38 / HITL 8（风险单）/ BLOCKED 2
- 附件媒体管道：zip 安全解包（GBK 名/嵌套/zip-slip 拒绝）→ VLM/ASR 提取 → RAG 向量化

## 出网关（铁律①执行层）
- `egress: allow=false` 默认全 DENY；SMTP 单通道需显式批准后开启
- 凭据 Fernet 加密存储（机器绑定密钥派生）· `UEA_APP_SECRET` 随服务 env 持久化（重启不丢）
- 邮件回复默认 **draft_only**：草稿全文 + 报价 PDF/XLSX 附件生成，人工确认才发送
- HITL 超时升级（G1）：2h 未审 → 通知备用审核人，**绝不代审**

## 已知边界（诚实）
- Gmail 用 App Password（OAuth 在 backlog）
- 同邮件 reprocess 会追加新行（状态按 mail_id 取最新）
