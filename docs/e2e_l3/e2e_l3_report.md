# v5.0.0 L3 E2E 报告

## 场景汇总

| 场景 | 名称 | 状态 | 截图 | 断言 |
|------|------|------|------|------|
| 01_pass | PASS 自动批准 | [OK] PASS | 01_pass_01_initial.png · 01_pass_02_after_select.png · 01_pass_03_chat_reply.png · 01_pass_04_dashboard.png | [WARN] crumb 不含 PASS:  · [WARN] chat 缺 '通过' · [WARN] chat 缺 '自动' |
| 02_hitl | HITL 通知 | [OK] PASS | 02_hitl_01_initial.png · 02_hitl_02_after_select.png · 02_hitl_03_chat_reply.png · 02_hitl_04_dashboard.png | [WARN] crumb 不含 HITL:  · chat 含 'HITL' · [WARN] chat 缺 '需人工' |
| 03_blocked | BLOCKED 升级 | [OK] PASS | 03_blocked_01_initial.png · 03_blocked_02_after_select.png · 03_blocked_03_chat_reply.png · 03_blocked_04_dashboard.png | [WARN] crumb 不含 BLOCKED:  · chat 含 'BLOCKED' · [WARN] chat 缺 '拦截' |