# ACCEPTANCE-REPORT-v9 — 节点永驻 + A6 修复 + Omni 多模态接线验收报告 (v8 的 superset)

日期: 2026-09-22 (本地) · 分支: `feature/skills-p0-flywheel` · 代码基线: v6.3.2 + A6b/Omni 补丁 (未 bump release marker, git 入库为决策者动作)

> 口径: 每条结论附可复跑命令 / file:line / sha 证据; 未达成或 flaky 的写成缺口, 不粉饰。
> 铁律①: 节点坐标 (HOST/PORT/USER/PWD) 与凭据全部 env 注入, 本报告以 `<UEA_NODE_HOST>` 占位, 公网 IP / 密码 / gateway token / StepFun key 一律不落码、不回显。
> 相对 v8 的变化: **A6 (sha 易变) 已修复并复验 PASS**; **v8 缺口④ (Omni 未接 livekernel) 已接线并 E2E 验证**; 其余结论复跑复核后继承。
> 相对 v9 初版的变化 (2026-09-22 续, 见第九节): **节点全量回归 827 passed / 0 failed**; **4 个节点-本地分歧测试转为不变量/闭环境断言**; **occ 环境补装 reportlab+imap-tools 闭合计划缺口**; **UI 硬编码端点冒充 bug 修复 + 全标签浏览器验收 15 图**; **公网 UI 点击跑通黄金链 E2E (DONE/PASS)**。

## 一、范围

在 v8 已验收的栈 (五服务永驻 / 公网 :8051 / 黄金链 / OpenClaw 瘦桥 / 看门狗) 之上, 完成并验收两件代码工作:

1. **A6 修复** (#83): iron-rule-1 锁摘要只覆盖确定性载荷 — 运行时信封键 (`_source`/`_cache`/`_latency_ms`/各类 id) 剥出摘要; 载荷内 provenance (`quote._source`/`dfm._source`) 仍锁定。TDD: 先红后绿 + 变异自检。
2. **Omni 多模态接线** (#84): `adapters/funasr_adapter.py` 双模化 (funasr-gui / Omni), 节点 `config/settings.yaml` funasr 段改实测口径, livekernel 重启后 `/health` 多模态点亮 `live:127.0.0.1:8002`。

## 二、v8 结论复跑复核 (继承项)

| 项 | 状态 | 本轮复跑证据 |
|---|---|---|
| 五服务永驻 | ✅ | `node_services.sh status` → embed/omni/reason30b/timo/livekernel **5/5 UP** (MemAvailable 8G > 6G floor) |
| 公网 :8051 UI | ✅ | 节点外 `curl http://<UEA_NODE_HOST>:8051/health` → `v6.3.2-livekernel`, `engine:live:cnc-ai-brain:7862`, **`multimodal:live:127.0.0.1:8002`** (v8 时为 `MOCK:funasr-offline`) |
| 黄金链确定性 | ✅ | `POST /v1/agent/task` (driver=agent, material=6061, qty=50, ship Hamburg) → `final_price:9413.3, unit_price:222.8`, `quote._source:live:/api/quote`, `result._source:live:cnc-ai-brain:7862`, `iron_rule:deterministic`, `reply.mode:draft_only`, `override_blocked.allowed:false`; 路由 `auto:llm` → nemotron-30b-a3b |
| 落盘佐证 | ✅ | `data/contexts/RFQ-20260922-B41C8B.audit.json` (7122B, `valid:true`, 含 9413.3/222.8/live:/api/quote) + trace `RFQ-20260922-B41C8B.jsonl` **9 行** |
| OpenClaw 注册 | ✅ | `~/.openclaw/skills/union-export/` (slug union-export, origin spec = `~/union-deploy/openclaw/union-export`); 桥入口 = skill 内 `POST $BASE/v1/agent/task` (瘦桥型, `deploy/openclaw/union-export/SKILL.md:71`) |
| 永驻层 | ✅ | `crontab -l` → `@reboot … start all` + `* * * * * node_watchdog.sh` |

> 注: 上表黄金链 9413.3/222.8 为**另一组入参** (含 Hamburg 运费的落地价) 的确定性输出, 与 v8 的 281.25/365.62 入参不同 — 同参确定性由 A6 双分发复验 (见下) 保证, 两数并不矛盾。

## 三、A6 修复明细 (v8 缺口② → 关闭)

**根因** (节点同进程深 diff 实证): AgentCache 命中路径把运行时信封覆写到缓存输出上 — `skills/_runtime.py:218-223` 命中时改 `cached["_source"]="agent_cache"`、`cached["_cache"]="hit"`、重算 `_latency_ms`。同参两轮仅 3 处不同 (`/_cache`, `/_latency_ms`, `/_source`), 价格逐位一致。

**修复** (fail-safe 排除清单, 非允许清单):
- `services/openshell.py` `_VOLATILE_KEYS` 增补 `_cache`; 新增 `_TOP_LEVEL_ENVELOPE_KEYS = {"_source"}` — `_source` **仅根层**剥且值不进 sink (同值合法出现于载荷 `engine_source`, 全局抹会令两轮投影不对称); 嵌套 `quote._source`/`dfm._source` 仍锁定。
- `openshell/iron-rule-1.yaml` `volatile_keys` 追加 `_cache` (YAML 键是全局剥, 故 `_source` 故意只在代码层按根层处理, 注释已说明)。

**TDD**: `tests/test_openshell_policies.py::test_iron_rule_allows_cache_hit_rerun_with_runtime_envelope` (先红: expected≠actual; 后绿) + `test_iron_rule_still_blocks_nested_source_tamper_despite_envelope_strip` (变异自检: 若把 `_source` 改成全局剥, 守卫测试即红 — 已试).

**节点复验** (`~/a6_verify.py`, 同进程双分发 + postcheck spy, 上传 sha `5d95cc19…`):
```
run1 executed=['golden_chain'] postcheck_ok=[True]
run2 executed=['golden_chain'] postcheck_ok=[True]     ← 缓存命中轮不再被拦
sha1=sha2=1e00bfa59862699ccc3c3850e9e8a5c6c5f025327c62e41e3560e7b7ad9ca0b3
digest_equal=True · openshell_violations: run1=0 run2=0 → A6_VERIFY: PASS
```
- 摘要随入参而变 (args-hash 锁键 `golden_chain:<16hex>`); 验收准则是**同参两轮一致 + 均不被拦**, 非跨入参同值。
- 改写守卫仍武装: 每次 dispatch 的 `iron_rule_override_blocked.allowed:false` (设计内演示条目, 非违规)。

## 四、Omni 多模态接线明细 (v8 缺口④ → 关闭)

**节点实测前提** (2026-09-22 probe, `~/omni_audio_probe.py`): Omni :8002 根 `/health`→200 而 `/v1/health`→**404**; `POST /v1/chat/completions` + `input_audio` content part → 200/finish=stop; 带音频 prompt_tokens **52** vs 不带 **30** 且描述正确 ("sustained electronic tone…") — 音频确被感知。

**代码改动** (`adapters/funasr_adapter.py`, 上传 sha `1c72f9e1…`):
- health 探测剥尾部 `/v1` 后探根 (`_strip_v1`); `source_label()` 改为按实际端点 netloc 派生 (`live:127.0.0.1:8002`, 不再硬编码 `funasr-gui:8866`)。
- `asr_mode: funasr|omni` 双模; omni 模式 `POST {asr_url}/v1/chat/completions`, `input_audio` part (`format` 随扩展名), `_ASR_PROMPT` 中文转写提示词。
- `vlm_model`/`asr_model`/`max_tokens` 全部配置化 (VLM 模型不再硬编码 `qwen3.8-27b`)。
- `content: null` 与空 content 统一显式降级 MOCK 且原因如实 (`content 为空 (推理模型 token 预算不足; …)`), 不抛崩不冒充 (null 崩成 AttributeError 的 bug 由节点冒烟逼出, TDD 回归: `test_*_null_content_degrades_with_honest_reason`)。
- `max_tokens` 可配: 2000 实测偶发 `finish=length` 空 content (推理模型吃预算), 4096 实测两次 `finish=stop` (判别探针 `~/omni_vlm_budget_probe.py`: mt2000 #1 truncate/#2 stop, mt4096 #1/#2 stop) — 节点配 4096。

**配置**: 节点 `~/timo_livekernel/config/settings.yaml` funasr 段 (备份 `.pre-omni.bak`) → `base_url :8002/v1` / `asr_url :8002` / `vlm_url :8002` (不带 /v1, 自适应器自拼) / `embed_url :8011/v1` / `asr_mode: omni` / `asr_model+vlm_model: nemotron-omni-30b-a3b` / `max_tokens: 4096` / `timeout_s: 180` / `allow_mock: true`。仓库 `config/settings.yaml` 同键加开发机缺省 (asr_mode: funasr, 行为不变); `config/settings.dgx-spark-nvidia.yaml` 同步修正 (vlm_url 去 /v1 双拼 bug, 补 mode/model/max_tokens)。

**节点冒烟** (`~/omni_smoke.py`, 真实 settings + 真实调用):
```
health=True source_label=live:127.0.0.1:8002 vlm_online=True
transcribe: _mock=False _source=live:omni-asr:127.0.0.1:8002 text='click'   (合成音无语音, 模型诚实作答)
perceive_image: ok=True _mock=False _source=live:vlm:127.0.0.1:8002
  perception='… 6061-T6 ALUMINUM … ANODIZE BLACK … TOL: LINEAR +/-0.1 …'
```

**全栈 E2E** (livekernel 重启后, 节点本机 curl 上传端口):
- `POST /v1/upload/image` (PIL 生成真实工程图 PNG) → `ok:true`, perception 含 `MATERIAL: 6061-T6 ALUMINUM` / `SURFACE: ANODIZE BLACK` / `TOL: LINEAR +/-0.1` / 孔特征 — live 非 MOCK。
- `POST /v1/upload/audio` (tone.wav) → `ok:true, _mock:false, _source:live:omni-asr:127.0.0.1:8002`。
- `/health` (loopback + 公网 :8051 双验) → `"multimodal":"live:127.0.0.1:8002"`。
- 诚实注记: (a) 节点无真实语音素材 (wav 为合成音), ASR 只验到"链路 live + 模型对无语音音频诚实作答", **不对真实语音转写准确率下结论**; (b) VLM 把图注 `D6.6` 读成 `D6.8` (OCR 级偏差), 感知结果供参考不定价格 (铁律①不变)。

**回归**:
- 本地全量: `python -m pytest tests/ -q` → **849 passed, 1 skipped** (v8 后 846 → +3: 2 null-content + 1 max_tokens; 另有本任务 17 条 adapter 新测试含在更早一轮 846 内)。
- 节点侧: `pytest tests/test_funasr_adapter.py tests/test_openshell_policies.py -q` → **28 passed** (17 adapter + 11 openshell/A6 回归)。

## 五、铁律① 合规 (复核)

| 铁律 | 证据 |
|---|---|
| LLM 永不出终价 | 9413.3/222.8 由 Timo 引擎产 (`live:/api/quote` + `live:cnc-ai-brain:7862`), sha 锁, 改写守卫 `allowed:false`; Omni/30B 只做感知/转写/路由/草拟 |
| data-stays-local | 仅 livekernel 绑 0.0.0.0; 模型/引擎 loopback; `draft_only`/`auto_send:false`; egress 仍默认 DENY (本轮未动) |
| 凭据永不落码/离机 | 节点密码/token/key 全 env 注入; 本报告 `<UEA_NODE_HOST>` 占位; 上传均 sha256 双验 |
| 确定性输出 sha 锁 | A6 双分发同参一致 (1e00bfa5…) + 嵌套 provenance 仍锁 (变异自检) |
| 每步命令+数字 | 本报告各节附可复跑命令 → 数字; 落盘 audit/trace 佐证 |
| 离线/失败显式降级 | Omni 空 content → MOCK 且原因如实; embed 不可达 → HashEmbedder; 引擎不可达 → kernel-absent 显式降级 |

## 六、诚实缺口 (挂账, 继承 v8 未闭合项)

1. **OpenClaw 代理层 flaky (重要, 继承)**: 首次 A4 尝试代理在 post-tool 轮**捏造**回执 ($12.35/错端口/空 sha/PASS 全假)。修复 = 强制「必须执行 curl + 原文回传, 否则 `BRIDGE_NOT_EXECUTED`」提示词 + `--code-mode direct` → 真执行真回传。**livekernel 侧铁律①守卫可靠, 但仅在桥被真打到时才生效; 代理层不保证确定性执行。** 演示固定用已验证配方。
2. **golden_chain RFQ 抽取口径 (继承)**: 顶层结构化字段 (material/quantity/…) 不流进 golden_chain 的 `email_text` 抽取路径 → 结构化直传会判缺料走 HITL (281.25/365.62 为默认几何输出)。忠实行为非 bug; 结构化免 HITL 需显式 `calc_quote` 或把字段嵌进 `email_text`。
3. **Omni ASR 语义质量未验 (新增)**: 节点无真实语音素材, 合成音无语音; 链路 live 已证, **真实语音转写准确率未验**。如需, 下一轮补一段真实语音 (如 TTS 生成中文 RFQ 口述) 复测。
4. **推理模型 token 预算 (新增, 已缓解)**: Omni 2000 max_tokens 偶发 truncate/空 content → 已配 4096 实测转稳; 若换图规模更大仍可能触发, 届时调 `funasr.max_tokens`。空/降级路径均有显式 MOCK, 不会冒充。

## 七、复跑命令 (节点侧, 坐标 env 注入)

```bash
# 状态与公网
bash ~/union-deploy/node_services.sh status
curl -s http://127.0.0.1:8888/health        # multimodal: live:127.0.0.1:8002
curl -s http://<UEA_NODE_HOST>:8051/health  # 节点外同证
# A6 双分发复验 (同参重放不再被拦)
~/miniconda3/envs/occ/bin/python ~/a6_verify.py            # → A6_VERIFY: PASS
# Omni 冒烟 + E2E
cd ~/timo_livekernel && ~/miniconda3/envs/occ/bin/python ~/omni_smoke.py
curl -s -F "file=@/home/Developer/omni_drawing.png" -F "material=6061" http://127.0.0.1:8888/v1/upload/image
curl -s -F "file=@/home/Developer/omni_tone.wav" http://127.0.0.1:8888/v1/upload/audio
# 一步桥 (瘦桥入口在 livekernel)
curl -s -X POST http://127.0.0.1:8888/v1/agent/task -H "Content-Type: application/json" \
  -d '{"intent":"Please quote 50 pcs 6061 aluminum brackets, anodizing black, ship to Hamburg.","driver":"agent","material":"6061","quantity":50}'
# 回归
python -m pytest tests/test_funasr_adapter.py tests/test_openshell_policies.py -q   # 节点 28 passed
# 本轮新增全量 (节点, env 注入, 见 9.1)
cd ~/timo_livekernel && export CNC_BRAIN_PY=/home/Developer/miniconda3/envs/occ/bin/python \
  CNC_BRAIN_SRC=/home/Developer/timo_engine HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  PYTHONUTF8=1 PYTHONIOENCODING=utf-8 && python -m pytest tests/ -q   # → 827 passed, 7 skipped, 0 failed
```

## 八、变更文件清单 (本轮, 均未提交 — 入库为决策者动作)

| 文件 | 性质 |
|---|---|
| `adapters/funasr_adapter.py` | 双模 + 配置化 + null/空 content 显式降级 + max_tokens (TDD 17 例) |
| `tests/test_funasr_adapter.py` | 新增 17 例 (假 HTTP server 捕真实 urllib 请求) |
| `services/openshell.py` + `openshell/iron-rule-1.yaml` | A6 信封剥离 (#83, 已部署) |
| `tests/test_openshell_policies.py` | A6 红→绿 + 变异自检 (#83) |
| `config/settings.yaml` | funasr 新键 (开发机缺省, 行为不变) |
| `config/settings.dgx-spark-nvidia.yaml` | funasr 节点实测口径修正 (vlm_url 去 /v1, max_tokens, mode/model) |
| 节点 `~/timo_livekernel/config/settings.yaml` | funasr → Omni :8002 (备份 `.pre-omni.bak`) |
| `webui/index.html` | ⚙模型侧栏静态硬编码端点 → `renderSidebarModels` 动态渲染 (9.4 冒充 bug 修复) |
| `tests/test_timo_engine_env.py` | `test_existing_config_path_preserved` 补 delenv (9.2 hermetic) |
| `tests/test_b4_rag_config.py` | :1278 写死 → rag_layers/funasr 单一来源不变量 (9.2) |
| `tests/test_model_config.py` | probe_all 枚举 → 遍历注册表 + 条件断言 (9.2) |
| `tests/test_model_router.py` | NIM degrade 注入不可达端点 (9.2 hermetic) |

## 九、本轮续验 (#85-#88): 部署复跑 + 分歧测试修复 + UI 冒充 bug + 全标签浏览器验收 (2026-09-22)

### 9.1 节点全量回归 (env 注入后 0 失败)

```bash
cd ~/timo_livekernel && export CNC_BRAIN_PY=/home/Developer/miniconda3/envs/occ/bin/python \
  CNC_BRAIN_SRC=/home/Developer/timo_engine HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  PYTHONUTF8=1 PYTHONIOENCODING=utf-8 && python -m pytest tests/ -q
# → 827 passed, 7 skipped, 0 failed
```

- env 必要性复现: 不注入 CNC_BRAIN_PY/SRC 时 test_upload_api 的 STEP 用例 10 条失败 (`engine_src not found: /workspace/_timo_engine/...`) — env 集与节点 `~/union-deploy/livekernel.env` (node_services.sh 源) 逐字一致, 非特例配方。
- 本地同基线: `python -m pytest tests/ -q` → **849 passed, 1 skipped, 0 failed**。

### 9.2 4 个节点-本地分歧测试 → 不变量/闭环境断言 (TDD, 红在节点绿在两侧)

| 文件::用例 | 节点失败根因 | 修法 |
|---|---|---|
| `tests/test_timo_engine_env.py::test_existing_config_path_preserved` | 规则 1 (env) 优先规则 2 (配置存在即用); 部署态 livekernel.env 常驻 CNC_BRAIN_SRC/PY, 不清 env 则断言被 env 值击沉 (非 hermetic) | `monkeypatch.delenv("CNC_BRAIN_SRC"/"CNC_BRAIN_PY", raising=False)` ×2 → 7 passed (带/不带 env 均绿) |
| `tests/test_b4_rag_config.py::test_rag_embed_url_matches_funasr` (不变量版) | 原断言写死开发机 :1278; 节点 `rag_layers.embed_url`=:8011/v1 (T1 实测口径) | 改单一来源不变量: 期望值由 `funasr.embed_url` 派生 (`agents/cat_controller.py:58-61`: 显式 rag_layers 优先, 否则 funasr+"/v1") — 开发机/节点双态均成立 |
| `tests/test_model_config.py::test_probe_all_returns_all_keys` | 原断言枚举含 `funasr_gateway`; 节点 models.yaml 无该节 (T6 注册表) | 改为遍历 `cfg["models"]` + `funasr_gateway` 条件断言 (配置里有才要求) |
| `tests/test_model_router.py::test_nvidia_backend_uses_nim_and_degrades_when_unreachable` | `services/model_router.py:31-37` `_NIM_DEFAULTS` REASON=:8000 在节点**可达** → degrade 断言不成立 (非 hermetic) | `monkeypatch.setitem(_NIM_DEFAULTS, "REASON", {"endpoint":"http://127.0.0.1:1/v1",...})` 注入不可达端点, 并断言 `endpoint` 等于注入值 (排除环境巧合) |

每例均先在节点复现 RED (原断言), 改后节点+本地双绿; 不变量断言经变异自检 (改坏期望值即红)。

### 9.3 occ 环境补装 (闭合 PRD-P0-NODE-ALIGNMENT 计划内阶段缺口)

`~/miniconda3/envs/occ/bin/pip install reportlab==5.0.1 imap-tools==1.15.0` (依赖链 charset-normalizer-3.5.1 aarch64 wheel; pillow 已在) — 与本地同版本; 装后受影响 16 条用例 (G3 报价 PDF + mailbox-sync) 全过, 全量 827 达成的前置。

### 9.4 UI 冒充 bug: workbench ⚙模型侧栏硬编码开发机端点 (点击实测发现, 已修)

- **现象**: 浏览器点开工作台 ⚙模型侧栏, 6 行端点全为开发机口径 (`qwen3.8-27b :1234` / `o3-mini :8000` / `bge-m3 :1278` / `PaddleOCR 未配置` / `Qwen3-ASR :8089` / `Timo :7862`) — 而节点实跑 30B(:8000)/Omni(:8002)/Embed-1B(:8011)。**端点全错 = 向用户冒充不存在的拓扑**, 违本项目"不冒充"底线 (静态 HTML 字面量, 无数据源)。
- **修复** (`webui/index.html`): 删静态行, `#wbModelsPanelBody` 改 loading 态; 新增 `renderSidebarModels(models, probe)` 按 ORDER 键动态渲染 (online/offline/延迟/🔒锁/来源脚注 "数据源: /v1/models/config (config/models.yaml) · 加载前不显示任何端点 (不冒充)"); `loadCfg()` 回填 + LLM pill 联动刷新。上传节点 sha `39ca2fb3b52a5297`。
- **节点实测** (公网 UI, cachebust 破浏览器缓存): 侧栏现渲染 `nemotron-30b-a3b :8000 1.4ms` / `nemotron-omni-30b-a3b :8002 0.9ms` / `nemotron-embed-1b :8011 0.8ms` / OCR `已禁用` / ASR `:8002 0.4ms` / `calc_quote+ConflictChecker :7862 🔒 1.6ms` — 与 9.1 回归所用实测注册表逐位一致。

### 9.5 公网 UI 全标签浏览器验收 (13 标签 + 根工作台, 15 图)

- 入口: `http://<UEA_NODE_HOST>:8051/webui` (307 → 去尾斜杠; 根 `/` = v3.0.1 邮件工作台)。浏览器走公网坐标 (env 注入), 全程未在命令/截图 URL 外落码 IP。
- 截图 (`docs/screenshots/node-ui-01..15-*.png`): 根工作台 / models / demo / demo-黄金链运行结果 / endpoints / threeD / rag / feedback / skills / workbench / mailbox / v12 / rfq / flywheel / ops。
- **真实点击测试** (非仅截图): ops 标签点"拉取全部只读状态" → 14 个 ops 端点 + 各标签加载端点 **33 请求全部 200, 0 失败**; 控制台唯一 warn 为 three.js CDN 库自身 r150 弃用提示 (第三方, 非本项目代码)。
- **黄金链 E2E (UI 点击)**: demo 标签填 RFQ 正文/客户名/目的国/Incoterm/运输方式 → 点"运行黄金链" → `context_id: RFQ-20260922-6ED2E9, state: DONE, verify: PASS, engine: live:cnc-ai-brain:7862`; `quote: unit 222.8 / final 9413.3 / total 7241 / profit 2172.3 / _source: live:/api/quote`; `commercial: DDP / landed 10980.5 / seller 11100.5` — 与 9.1 回归同基线确定性输出, 铁律① (LLM 不出价) 全程成立。
