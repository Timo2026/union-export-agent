"""test_node_profile_overlay.py — 节点 Profile 覆盖源「实测口径」契约锁.

背景 (PRD-P0-NODE-ALIGNMENT §3.3/§6.4 + PRD-S-MODEL B9/F2):
  config/settings.dgx-spark-nvidia.yaml **不被代码加载** (services/config.py:19-21
  只读 config/settings.yaml)。它是 ops 约定 / 阶段 3 部署的「覆盖源」参考件。
  因此它的价值 = 准确反映节点实测拓扑, 不能残留 Windows 开发机口径误导部署。

节点实测拓扑 (v2 · 2026-09-22, user 拍板「放弃 30B, 全部接 Omni 30B」):
  REASON/FAST -> :8002  nemotron-omni-30b-a3b   (Omni-30B-A3B NVFP4, 统一推理端点)
  VISION      -> :8002  nemotron-omni-30b-a3b   (Omni-30B-A3B NVFP4, any-to-any 多模态)
  ASR         -> :8002  nemotron-omni-30b-a3b   (Omni any-to-any 音频路径; 专档 :8021 未部署)
  EMBED       -> :8011  nemotron-embed-1b       (Embed-1B NVFP4, 非对称双塔需 query:/passage: 前缀)
  DETERMINISTIC -> Timo 引擎 :7862 (铁律①锁死, 永不走 LLM)

契约 (本测试钉死, 防止开发机口径回流):
  - 无 Windows 路径 (反斜杠 / 盘符 / /workspace 占位)
  - 无开发机端口 (:1234 LMStudio / :1278 旧 embed / :8089 旧 ASR / :8866 funasr 网关)
  - 无 NIM 容器参考端口 (:8020 / :8021) —— 节点实跑 vLLM 进程级, Omni 在 :8002
  - rag_layers 带 Embed-1B 实测口径 (:8011 + 前缀 + timeout 15, 对齐 T1)
  - 铁律①: egress 全 DENY
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml  # type: ignore

_OVERLAY = (Path(__file__).resolve().parent.parent
            / "config" / "settings.dgx-spark-nvidia.yaml")


def _load() -> dict:
    return yaml.safe_load(_OVERLAY.read_text(encoding="utf-8"))


def _text() -> str:
    return _OVERLAY.read_text(encoding="utf-8")


# ---------- 1. 无 Windows / 占位路径 ----------

def test_no_windows_or_workspace_paths():
    txt = _text()
    assert "\\" not in txt, "覆盖源不得含 Windows 反斜杠路径"
    # Windows 盘符路径 (C:/ 或 C:\): 单字母盘符前非字母, 后接冒号+斜杠。
    # 用 lookbehind 排除 http:// (p 前有 t) 与 DETERMINISTIC: (大写键名, 无斜杠) 的误命中。
    assert not re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]", txt), (
        "覆盖源不得含 Windows 盘符路径 (如 C:/ 或 C:\\)")
    assert "/workspace/" not in txt, (
        "/workspace 占位路径节点实测不存在 (PRD §6.4); 引擎落点应为节点 home 派生")


# ---------- 2. 无开发机端口 ----------

def test_no_dev_machine_endpoints():
    txt = _text()
    for dev in (":1234", ":1278", ":8089", ":8866"):
        assert dev not in txt, f"覆盖源残留开发机端口 {dev} (节点不存在)"


def test_no_nim_container_reference_ports():
    """节点实跑 vLLM 进程级 (Omni :8002), 不用 NIM 容器参考端口 :8020/:8021."""
    txt = _text()
    assert ":8020" not in txt, "NIM 容器参考端口 :8020 与节点实测 Omni :8002 冲突"
    assert ":8021" not in txt, "ASR 专档 :8021 节点未部署, 不得作为实测口径"


# ---------- 3. 实测拓扑端口齐备 ----------

def test_resident_model_ports_present():
    txt = _text()
    for port in (":8002", ":8011", ":7862"):
        assert port in txt, f"节点实测常驻端口 {port} 缺失"


def test_timo_base_url_is_7862():
    d = _load()
    assert str(d["timo"]["base_url"]).rstrip("/").endswith(":7862")


def test_model_router_backend_local():
    """节点无 docker 权限 -> NIM 容器线不可行; 实跑 backend=local 走 models.yaml."""
    d = _load()
    assert d["model_router"]["backend"] == "local"


def test_role_endpoints_match_resident_topology():
    roles = _load()["model_router"]["roles"]
    assert ":8002" in roles["REASON"]["endpoint"], "REASON 应指 Omni 统一端点 :8002"
    assert roles["REASON"]["model"] == "nemotron-omni-30b-a3b"
    assert ":8002" in roles["VISION"]["endpoint"], "VISION 应指 Omni :8002"
    assert ":8011" in roles["EMBED"]["endpoint"], "EMBED 应指 Embed-1B :8011"
    assert roles["DETERMINISTIC"]["locked"] is True, "铁律①: DETERMINISTIC 锁死"
    assert ":7862" in roles["DETERMINISTIC"]["endpoint"]


# ---------- 4. rag_layers Embed-1B 实测口径 (对齐 T1) ----------

def test_rag_layers_embed_measured_config():
    rl = _load()["rag_layers"]
    assert ":8011" in rl["embed_url"], "embed_url 应指 Embed-1B :8011"
    assert rl["embed_model"] == "nemotron-embed-1b"
    # 非对称双塔: 缺前缀则排序错误 (0.3758 vs 0.5209, E3 冒烟实测)
    assert rl["embed_query_prefix"] == "query: "
    assert rl["embed_passage_prefix"] == "passage: "
    # 首调用 ~10.45s 超 3s; 稳态 10ms -> timeout 放宽到 15s
    assert float(rl["timeout_s"]) == 15.0


# ---------- 5. 铁律① egress 全 DENY ----------

def test_egress_denied():
    eg = _load()["egress"]
    assert eg["allow"] is False, "铁律①: egress 主闸默认 DENY"
    for ch in ("smtp", "webhook", "imap"):
        assert eg["channels"][ch] is False, f"铁律①: {ch} 通道必须 DENY"


# ---------- 6. 服务端口 = 公网映射口径 ----------

def test_server_port_matches_public_mapping():
    """公网 8888->8051 (节点 IP 见本地 node.env, 不写死/不入包).

    注: api_server.py:930-932 host 写死 127.0.0.1 + 默认 8900, 不读本段;
    实际 bind 由 T5 启动命令 --host 0.0.0.0 --port 8888 落地, 本段是部署意图记录。
    """
    srv = _load()["server"]
    assert srv["host"] == "0.0.0.0", "公网可达需 bind 0.0.0.0 (非 loopback)"
    assert int(srv["workbench_port"]) == 8888, "workbench_port=8888 对应公网 :8051"


# ==========================================================================
# 节点运行时驱动 config/models.node.yaml —— backend=local 的真正路由源
#
# 关键事实 (model_router.py:94-103 + model_config.py:21):
#   local 模式 resolve() 经 choose_route() 读 config/models.yaml (键 llm/vlm/
#   embedding/asr/deterministic), **完全不读 settings.model_router.roles**。
#   仓库自带 config/models.yaml 是开发机口径 (:1234/:1278/:8089, 节点全死)。
#   故节点部署 (T5) 必须以 models.node.yaml 覆盖节点 config/models.yaml,
#   否则所有 LLM 角色路由到死端点。本组测试钉死该文件的实测口径 + schema 合法。
# ==========================================================================

_MODELS_NODE = (Path(__file__).resolve().parent.parent
                / "config" / "models.node.yaml")


def _load_models_node() -> dict:
    return yaml.safe_load(_MODELS_NODE.read_text(encoding="utf-8"))


def test_models_node_schema_valid():
    """必须通过 model_config.validate() —— 否则节点 save()/load 链路炸。"""
    from services import model_config
    errs = model_config.validate(_load_models_node())
    assert errs == [], f"models.node.yaml schema 非法: {errs}"


def test_models_node_no_dev_endpoints():
    txt = _MODELS_NODE.read_text(encoding="utf-8")
    for dev in (":1234", ":1278", ":8089", ":8866"):
        assert dev not in txt, f"models.node.yaml 残留开发机端口 {dev}"


def test_models_node_measured_endpoints():
    m = _load_models_node()["models"]
    assert ":8002" in m["llm"]["endpoint"]
    assert m["llm"]["model"] == "nemotron-omni-30b-a3b"
    assert ":8002" in m["vlm"]["endpoint"]
    assert m["vlm"]["model"] == "nemotron-omni-30b-a3b"
    assert ":8011" in m["embedding"]["endpoint"]
    assert m["embedding"]["model"] == "nemotron-embed-1b"
    assert ":8002" in m["asr"]["endpoint"], "ASR 蹭 Omni 音频路径 (专档未部署)"


def test_models_node_deterministic_locked():
    """铁律①: deterministic 锁死 Timo :7862, 不可禁用/不可改 LLM。"""
    det = _load_models_node()["models"]["deterministic"]
    assert ":7862" in det["endpoint"]
    assert det["locked"] is True
    assert det["enabled"] is True


def test_models_node_choose_route_resolves_measured():
    """choose_route() 是 local 模式真正的决策函数 —— 验证它从本文件解析出实测端点。"""
    from services.model_config import choose_route
    cfg = _load_models_node()
    assert ":8002" in (choose_route("llm", cfg=cfg)["endpoint"] or "")
    assert ":8002" in (choose_route("vlm", cfg=cfg)["endpoint"] or "")
    assert ":8011" in (choose_route("embedding", cfg=cfg)["endpoint"] or "")


def test_models_node_drives_router_local(monkeypatch):
    """端到端: backend=local 的 ModelRouter 用本文件路由出实测端点 (roles 死配置不参与)。"""
    from services import model_config
    from services.model_router import ModelRouter

    monkeypatch.setattr(model_config, "_MODELS_YAML", _MODELS_NODE)

    class _FakeTimo:
        base_url = "http://127.0.0.1:7862"
        online = True

    mr = ModelRouter({"model_router": {"backend": "local", "roles": {}}}, timo=_FakeTimo())
    assert ":8002" in mr.resolve("REASON")["endpoint"]
    assert ":8002" in mr.resolve("FAST")["endpoint"], "v2: FAST 与 REASON 同指 Omni 统一端点"
    assert ":8002" in mr.resolve("VISION")["endpoint"]
    assert ":8011" in mr.resolve("EMBED")["endpoint"]
    det = mr.resolve("DETERMINISTIC")
    assert det["backend"] == "timo-kernel" and det["online"] is True


# ---------- 7. 弃用拓扑端口缺席 (2026-09-22 pivot: 放弃 30B, 全部接 Omni :8002) ----------
# :8000 是 30B 专属端口。Omni 与 30B unified-memory 不可共存 (30B 任何 util 配方
# 0.30/0.22/0.20 都在 KV cache 分配期 crash-loop, watchdog 22 次重启), pivot 后
# 两份节点口径文件零 :8000 残留, 防止开发机口径回流把部署引回 crash-loop 拓扑。

def test_overlay_no_abandoned_30b_port():
    txt = _text()
    assert ":8000" not in txt, "覆盖源残留 30B 端口 :8000 (已弃用, 全量 Omni :8002)"


def test_models_node_no_abandoned_30b_port():
    txt = _MODELS_NODE.read_text(encoding="utf-8")
    assert ":8000" not in txt, "models.node.yaml 残留 30B 端口 :8000 (已弃用, 全量 Omni :8002)"
