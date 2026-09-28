"""test_model_router_layered.py — Nemotron 全家族分层调度验证.

验证 model_router 在 nvidia backend 下的路由端点 (节点真实拓扑 · 2026-09-25 实测):
  FAST/REASON/VISION/ASR -> :8002  nemotron-omni-30b-a3b   (Omni-30B any-to-any, 单卡统一编排)
  EMBED                  -> :8011  nemotron-embed-1b        (Embed-1B 专端口)
  DETERMINISTIC -> locked, timo-kernel                      (铁律1, 永不走 LLM)

节点实测证据 (本 effort 方案A/B1 2026-09-25):
  - Timo ModelRegistry 健康探测: 仅 :8002 omni-vllm OK (其余候选 dead), best = omni-vllm;
  - livekernel media/status: vlm :8002 online, model = nemotron-omni-30b-a3b;
  - Embed-1B :8011 起服实测 (非对称编码器, query:/passage: 前缀)。
  docker-compose 多端口编排 (Nano-4B :8002/Lightning :8000/Omni :8020/ASR :8021) 仅为
  有 docker 权限的目标环境参考; spark-51 docker daemon 无权限, 实跑为 vLLM 进程级单卡编排。

核心断言:
  - FAST/REASON/VISION/ASR 统一由 Omni :8002 承载 (实测栈, 非 aspirational 多端口)
  - EMBED 独立端口 (向量化与推理解耦)
  - 所有 NIM model 在 Nemotron 家族 (全 NVIDIA 自研纯度)
  - DETERMINISTIC 永远 locked 到 Timo 引擎 (与任何 LLM 角色分离)

对齐: services/model_router.py _NIM_DEFAULTS (2026-09-25 节点真实拓扑对齐)
      (hf-mirror API 实测仓库 ID, 见 docs/PRD-MASTER-UEA-DELIVERY.md §1.2-F)
"""
from __future__ import annotations

import pytest

from services.model_router import ModelRouter


class _FakeTimo:
    base_url = "http://127.0.0.1:7862"
    online = True


def _settings(backend="nvidia"):
    return {"model_router": {"backend": backend, "roles": {}}}


# ---------- 单角色端点断言 (节点实测拓扑: :8002 Omni 统一 / :8011 embed 专端口) ----------

def test_fast_routes_to_omni_port_8002():
    """FAST (意图分类/路由) 由 Omni :8002 承载 — 节点真实拓扑 (2026-09-25 实测)。"""
    mr = ModelRouter(_settings("nvidia"), timo=_FakeTimo())
    r = mr.resolve("FAST")
    assert "8002" in r["endpoint"], f"FAST 应路由到 :8002 (节点 Omni-30B), 实际 {r['endpoint']}"
    assert "omni" in r["model"].lower()


def test_reason_routes_to_omni_port_8002():
    mr = ModelRouter(_settings("nvidia"), timo=_FakeTimo())
    r = mr.resolve("REASON")
    assert "8002" in r["endpoint"], f"REASON 应路由到 :8002 (节点 Omni-30B), 实际 {r['endpoint']}"
    assert "omni" in r["model"].lower()


def test_vision_routes_to_omni_port_8002():
    mr = ModelRouter(_settings("nvidia"), timo=_FakeTimo())
    r = mr.resolve("VISION")
    assert "8002" in r["endpoint"], f"VISION 应路由到 :8002 (节点 Omni-30B), 实际 {r['endpoint']}"
    assert "omni" in r["model"].lower()


def test_asr_routes_to_omni_port_8002():
    mr = ModelRouter(_settings("nvidia"), timo=_FakeTimo())
    r = mr.resolve("ASR")
    assert "8002" in r["endpoint"], f"ASR 应路由到 :8002 (节点 Omni-30B), 实际 {r['endpoint']}"
    assert "omni" in r["model"].lower()


def test_embed_routes_to_nemotron_embed_port_8011():
    mr = ModelRouter(_settings("nvidia"), timo=_FakeTimo())
    r = mr.resolve("EMBED")
    assert "8011" in r["endpoint"], f"EMBED 应路由到 :8011 (Nemotron-Embed-1B), 实际 {r['endpoint']}"
    assert "embed" in r["model"].lower()
    assert "8002" not in r["endpoint"], "EMBED 不得与 LLM 推理共用 :8002"
    assert "embedqa" not in r["model"].lower(), "nv-embedqa 已否决 (NIM 容器路线关闭)"


# ---------- 分层调度核心断言 ----------

def test_fast_and_reason_layered_separation():
    """节点实测拓扑: FAST/REASON 同由 Omni :8002 承载 (单卡统一编排, any-to-any 一栈多角色)。

    真正的分层在角色边界而非端口: DETERMINISTIC 永远锁 Timo 内核, 与 LLM 角色完全分离。
    docker-compose 的多端口分层 (Nano-4B :8002 / Lightning :8000) 仅为有 docker 权限的
    目标环境参考 — spark-51 无 docker daemon, 按 aspirational 编排路由会打到死端口。
    """
    mr = ModelRouter(_settings("nvidia"), timo=_FakeTimo())
    fast = mr.resolve("FAST")
    reason = mr.resolve("REASON")
    det = mr.resolve("DETERMINISTIC")
    embed = mr.resolve("EMBED")
    assert fast["endpoint"] == reason["endpoint"] == "http://127.0.0.1:8002/v1"
    assert fast["model"] == reason["model"] == "nemotron-omni-30b-a3b"
    # 铁律1 分层: 确定性报价永不走 LLM
    assert det["backend"] == "timo-kernel" and det["endpoint"] != fast["endpoint"]
    # 向量化独立端口
    assert embed["endpoint"] != fast["endpoint"]


def test_vision_and_asr_use_dedicated_models():
    """节点实测: VISION/ASR 由同一 Omni any-to-any 统一承载, 但与 DETERMINISTIC/EMBED 分离。"""
    mr = ModelRouter(_settings("nvidia"), timo=_FakeTimo())
    vision = mr.resolve("VISION")
    asr = mr.resolve("ASR")
    det = mr.resolve("DETERMINISTIC")
    embed = mr.resolve("EMBED")
    assert vision["endpoint"] == asr["endpoint"] == "http://127.0.0.1:8002/v1"
    assert vision["model"] == asr["model"] == "nemotron-omni-30b-a3b"
    assert "omni" in vision["model"].lower()
    # 与确定性子系统/向量化子系统分离
    assert det["endpoint"] not in (vision["endpoint"], asr["endpoint"])
    assert embed["endpoint"] not in (vision["endpoint"], asr["endpoint"])


# ---------- Nemotron 全家族纯度 ----------

def test_nim_models_all_nvidia_family():
    """Nemotron 全家族纯度: 所有 NIM model 名含 nemotron (NVIDIA 自研)."""
    mr = ModelRouter(_settings("nvidia"), timo=_FakeTimo())
    for role in ("FAST", "REASON", "VISION", "ASR", "EMBED"):
        r = mr.resolve(role)
        m = r["model"].lower()
        assert "nemotron" in m, (
            f"{role} model={r['model']} 不在 Nemotron 家族 (NVIDIA 自研纯度破坏)"
        )


# ---------- 铁律1: DETERMINISTIC 锁定 ----------

def test_deterministic_locked_to_timo_kernel():
    """铁律1: DETERMINISTIC 永远路由到 Timo 引擎, 不走任何 LLM (含 Nemotron)."""
    mr = ModelRouter(_settings("nvidia"), timo=_FakeTimo())
    r = mr.resolve("DETERMINISTIC")
    assert r["backend"] == "timo-kernel"
    assert r["online"] is True
    assert "LLM" in r["note"]
    # 不含任何 Nemotron/Nano/Lightning 字样 (DETERMINISTIC 不平替)
    assert "nemotron" not in r.get("model", "").lower()


def test_deterministic_locked_even_in_mock_backend():
    """铁律1 双保险: 即使 backend=mock, DETERMINISTIC 仍走 Timo 引擎."""
    mr = ModelRouter(_settings("mock"), timo=_FakeTimo())
    r = mr.resolve("DETERMINISTIC")
    assert r["backend"] == "timo-kernel"
    assert r["online"] is True