"""test_model_router.py — L3 Model Mesh 路由单元测试 (local/nvidia/mock + DETERMINISTIC)."""
from __future__ import annotations

import pytest

from services import model_router
from services.model_router import ModelRouter, ROLES


class _FakeTimo:
    base_url = "http://127.0.0.1:7862"
    online = True


def _settings(backend="local"):
    return {"model_router": {"backend": backend, "roles": {
        "FAST": {"endpoint": "http://127.0.0.1:1/v1", "model": "m"},
        "EMBED": {"endpoint": "http://127.0.0.1:1/v1", "model": "e"}}}}


def test_deterministic_always_routes_to_timo():
    mr = ModelRouter(_settings("local"), timo=_FakeTimo())
    r = mr.resolve("DETERMINISTIC")
    assert r["backend"] == "timo-kernel"
    assert r["online"] is True
    assert "LLM" in r["note"]        # 明确不走 LLM


def test_all_roles_resolvable():
    mr = ModelRouter(_settings("local"), timo=_FakeTimo())
    st = mr.status()
    assert set(st["routes"].keys()) == set(ROLES)


def test_mock_backend_labels_all_non_deterministic_as_mock():
    mr = ModelRouter(_settings("mock"), timo=_FakeTimo())
    for role in ("FAST", "VISION", "REASON", "EMBED", "ASR"):
        r = mr.resolve(role)
        assert r["backend"] == "mock" and r["online"] is False
    # DETERMINISTIC 仍是内核
    assert mr.resolve("DETERMINISTIC")["backend"] == "timo-kernel"


def test_nvidia_backend_uses_nim_and_degrades_when_unreachable(monkeypatch):
    """注入不可达 REASON 端点 — 原断言依赖"本机无 NIM"环境假设: 节点常驻 30B
    :8000 时 _NIM_DEFAULTS.REASON 探活在线会击沉本用例 (非 hermetic)。
    注入后 r["endpoint"] 断言同时证明注入生效 (不会因开发机本就不可达而空转)。"""
    monkeypatch.setitem(
        model_router._NIM_DEFAULTS, "REASON",
        {"endpoint": "http://127.0.0.1:1/v1", "model": "nvidia/test-nim"})
    mr = ModelRouter(_settings("nvidia"), timo=_FakeTimo())
    r = mr.resolve("REASON")
    assert r["backend"] == "nvidia-nim"
    assert r["model"]                      # NIM 模型名已配置
    assert r["endpoint"] == "http://127.0.0.1:1/v1"   # 注入生效, 非环境巧合
    assert r["online"] is False            # 注入不可达端点 → 探测失败
    assert "降级" in r["note"]


def test_local_unreachable_endpoint_marked_offline(monkeypatch):
    """v2.3.1: local backend 走 models.yaml + choose_route(), 不再被 roles_cfg.endpoint 覆盖。
    注入一个不通的 llm endpoint, 验证 offline + MOCK note。
    """
    from services.model_config import load as _load
    cfg = _load()
    # 把 llm endpoint 临时改成一个肯定不通的端口
    cfg["models"]["llm"]["endpoint"] = "http://127.0.0.1:1/v1"
    cfg["models"]["llm"]["model"] = "offline-mock"
    mr = ModelRouter(_settings("local"), timo=_FakeTimo())
    mr._model_cfg = cfg  # 覆盖默认加载的 models.yaml
    mr._probe_cache.clear()
    r = mr.resolve("FAST")
    assert r["backend"] == "local" and r["online"] is False
    assert "MOCK" in r["note"]


def test_status_lists_online_roles():
    mr = ModelRouter(_settings("local"), timo=_FakeTimo())
    st = mr.status()
    # 至少 DETERMINISTIC 在线 (timo online=True)
    assert "DETERMINISTIC" in st["online_roles"]


# ---- C4: primary 离线 → fallback 切换 (P1 巡检: 节点 Omni :8002 单点) ----
def _cfg_with_fallback(primary="http://127.0.0.1:1/v1",
                       fb="http://fb-host/v1", fb_model="qwen3-0.6b"):
    from services.model_config import load as _load
    cfg = _load()
    cfg["models"]["llm"]["endpoint"] = primary
    cfg["models"]["llm"]["model"] = "offline-primary"
    cfg["models"]["llm"]["fallback"] = {"endpoint": fb, "model": fb_model}
    return cfg


def test_local_primary_offline_falls_back(monkeypatch):
    cfg = _cfg_with_fallback()
    mr = ModelRouter(_settings("local"), timo=_FakeTimo())
    mr._model_cfg = cfg
    monkeypatch.setattr(mr, "_probe", lambda ep, path="/models": "fb-host" in ep)
    r = mr.resolve("FAST")
    assert r["online"] is True and r["source"] == "fallback"
    assert r["endpoint"] == "http://fb-host/v1" and r["model"] == "qwen3-0.6b"
    assert "fallback" in r["note"]


def test_local_pick_primary_offline_falls_back(monkeypatch):
    cfg = _cfg_with_fallback()
    mr = ModelRouter(_settings("local"), timo=_FakeTimo())
    mr._model_cfg = cfg
    monkeypatch.setattr(mr, "_probe", lambda ep, path="/models": "fb-host" in ep)
    r = mr.pick("FAST", request_id="req-1")
    assert r["online"] is True and r["source"] == "fallback"


def test_local_both_down_still_explicit_mock(monkeypatch):
    cfg = _cfg_with_fallback()
    mr = ModelRouter(_settings("local"), timo=_FakeTimo())
    mr._model_cfg = cfg
    monkeypatch.setattr(mr, "_probe", lambda ep, path="/models": False)
    r = mr.resolve("FAST")
    assert r["online"] is False and "MOCK" in r["note"]


def test_local_primary_online_ignores_fallback(monkeypatch):
    cfg = _cfg_with_fallback()
    mr = ModelRouter(_settings("local"), timo=_FakeTimo())
    mr._model_cfg = cfg
    monkeypatch.setattr(mr, "_probe", lambda ep, path="/models": True)
    r = mr.resolve("FAST")
    assert r["online"] is True and r["source"] == "primary"
    assert r["endpoint"] == "http://127.0.0.1:1/v1"


def test_probe_cache_expires_by_ttl(monkeypatch):
    """task #95: 探针缓存必须带 TTL。节点实测坑: livekernel 启动时 30B 在线 →
    _probe_cache 写死 True 且永不过期; 30B 崩溃后 /v1/model-router/status 仍报
    online:true (状态冒充), watchdog 日志与 UI 口径互相矛盾。"""
    calls = {"n": 0}
    state = {"ok": True}

    class _Resp:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def _fake_urlopen(url, timeout=None):
        calls["n"] += 1
        if not state["ok"]:
            raise OSError("backend dead")
        return _Resp()

    monkeypatch.setattr(model_router.urllib.request, "urlopen", _fake_urlopen)
    now = {"t": 1000.0}
    monkeypatch.setattr(model_router.time, "monotonic", lambda: now["t"])

    mr = ModelRouter(_settings("local"), timo=_FakeTimo())
    ep = "http://127.0.0.1:9/v1"
    assert mr._probe(ep) is True
    assert calls["n"] == 1
    assert mr._probe(ep) is True          # TTL 内命中缓存, 不重复探测
    assert calls["n"] == 1

    now["t"] += 11.0                       # 超过默认 10s TTL
    state["ok"] = False                    # 后端进程此刻已死
    assert mr._probe(ep) is False          # 缓存过期 → 重新探测 → 如实报离线
    assert calls["n"] == 2
