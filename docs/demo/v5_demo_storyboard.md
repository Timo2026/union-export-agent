# v5.0.0 L3 演示视频分镜脚本

**总时长**: 5 min · **场景数**: 5 · **总帧数**: 30

**输出**: docs/demo/frames/*.png

---

## 场景 1: PASS 路径自动批准

**时间段**: 00:00 - 01:00

- **00:00** 00_initial: Workbench 默认状态 (NVIDIA 绿品牌色 + 黄金链空态)
- **00:10** 01_select_s1: 选中 S1 (Alice Chen, 6061 PASS)
- **00:20** 02_inspector: 中栏 Inspector 显示邮件详情 + 黄金链 7/8 步 done
- **00:30** 03_chat_verify: 右栏 Chat 发送 'verify gate'
- **00:40** 04_send: 点 ▶ 发送 → mock agent 回复 '5/5 PASS'
- **00:50** 05_approval: 切到 Approval tab → sha16 锁 + ✓ 批准按钮

## 场景 2: HITL 路径 + 通知外发

**时间段**: 01:00 - 02:00

- **01:00** 10_select_s2: 选中 S2 (Bob Smith, TC4 IT5 HITL)
- **01:10** 11_inspector: 中栏 Inspector 显示 HITL 触发原因 (公差/金额/材料)
- **01:20** 12_approval: Approval tab: sha16 锁 + 双确认按钮
- **01:30** 13_chat_approve: 右栏 Chat 发 'approve this quote' → agent 解释
- **01:40** 14_send: 点发送 → mock agent 提示需人工
- **01:50** 15_skill_console: 打开 Skill Console 看 18 个 skill + 审计尾巴

## 场景 3: BLOCKED 路径 + 铁律②拦截

**时间段**: 02:00 - 03:00

- **02:00** 20_select_s3: 选中 S3 (Carol Wang, 304 阳极氧化 BLOCKED)
- **02:10** 21_inspector: 中栏 Inspector 显示 BLOCKED + MATERIAL_SURFACE_MISMATCH 冲突
- **02:20** 22_chat_explain: Chat 发送 'explain why BLOCKED'
- **02:30** 23_send: mock agent 解释 304 不锈钢不能阳极氧化
- **02:40** 24_blocked_panel: Agent 给出替代方案 (钝化/粉末喷涂)
- **02:50** 25_no_approve: Approval tab 无 ✓ 批准按钮 (铁律② 守护)

## 场景 4: NovaStudio 4 工具整合

**时间段**: 03:00 - 04:00

- **03:00** 30_novastudio_dir: 展示 tools/ 目录 (MinerU + ragflow + OmniVoice + SearXNG)
- **03:10** 31_intake_pdf: 演示 services/intake_pdf.py 调 MinerU 解析 PDF
- **03:20** 32_rag_search: 演示 services/rag_search.py 调 ragflow 检索
- **03:30** 33_asr_engine: 演示 services/asr_engine.py 调 OmniVoice ASR
- **03:40** 34_web_search: 演示 services/web_search.py 调 SearXNG
- **03:50** 35_offline_fallback: 4 工具未启动时 mock fallback (test_novastudio 7 用例)

## 场景 5: 自动批准 + spark dashboard + 审计

**时间段**: 04:00 - 05:00

- **04:00** 40_l3_pipeline: 展示 MailOrchestrator 自动跑 L3 黄金链
- **04:10** 41_auto_approve: PASS 路径 → auto_approve → audit jsonl +1
- **04:20** 42_notify: HITL/BLOCKED 路径 → notify_external (Telegram/Email/Slack)
- **04:30** 43_spark_dashboard: spark-output/dashboard.html 实时更新 (节点变绿)
- **04:40** 44_audit_jsonl: data/skill_audit.jsonl 含 audit_tag=l3-auto
- **04:50** 45_final: 最终全量 499 passed + 0 failed
