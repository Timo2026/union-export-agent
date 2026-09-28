"""tests/test_inbound_worker.py — inbound_scanner 常驻 worker (Z6, 先红后绿).

缺口 (代码实证): InboundScanner 状态机完备但全仓零外部调用方 — zip 丢进
data/inbound 无人处理, 邮箱 zip 断点 3。本测试钉死常驻语义:
  1) worker start → 后台线程按 interval tick (zip 自动解包→BOM 批量报价)
  2) stop → 线程退出, 不再 tick
  3) interval<=0 / UEA_INBOUND_SCAN=0 → disabled, 不起线程 (逃生门)
  4) tick 抛异常 → worker 不死, last_error 如实记账, 下一轮继续
  5) api lifespan 起停 worker (镜像 mail autostart 模式) + 状态/tick 端点
门禁: conftest 默认 UEA_INBOUND_SCAN=0 — pytest 进程永不自动扫真实 data/inbound。
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from services import api_server as apiserver


class _FakeScanner:
    """记录 tick 调用; boom=True 模拟 tick 抛异常 (worker 必须不死)."""

    def __init__(self, boom: bool = False) -> None:
        self.ticks = 0
        self.boom = boom

    def tick(self, limit: int = 0, dry_run: bool = False):
        self.ticks += 1
        if self.boom:
            raise RuntimeError("scan boom")
        return {"scan": {"discovered": 0, "new": 0}, "run": {"processed": 0}}

    def status(self):
        return {"total": 0, "by_state": {}}


@pytest.fixture
def worker_cls(monkeypatch):
    from services import inbound_worker
    monkeypatch.setenv("UEA_INBOUND_SCAN", "1")
    monkeypatch.setenv("UEA_INBOUND_SCAN_INTERVAL", "0.05")
    return inbound_worker.InboundScannerWorker


# ---------- 1-4. worker 机械化语义 ----------

def test_worker_start_ticks_then_stops(worker_cls):
    sc = _FakeScanner()
    w = worker_cls(scanner=sc)
    r = w.start()
    assert r["state"] == "started"
    deadline = time.time() + 3
    while sc.ticks < 1 and time.time() < deadline:
        time.sleep(0.02)
    assert sc.ticks >= 1                       # 后台线程真的在 tick
    w.stop()
    frozen = sc.ticks
    time.sleep(0.25)                           # interval 0.05 → 停后不应再涨
    assert sc.ticks == frozen
    assert w.status()["running"] is False


def test_worker_disabled_zero_interval(monkeypatch, worker_cls):
    monkeypatch.setenv("UEA_INBOUND_SCAN_INTERVAL", "0")
    sc = _FakeScanner()
    w = worker_cls(scanner=sc)
    r = w.start()
    assert r["state"] == "disabled"
    assert w.status()["running"] is False
    time.sleep(0.15)
    assert sc.ticks == 0                       # disabled = 配置意图, 不起线程


def test_worker_kill_switch_env_zero(monkeypatch, worker_cls):
    monkeypatch.setenv("UEA_INBOUND_SCAN", "0")
    sc = _FakeScanner()
    w = worker_cls(scanner=sc)
    r = w.start()
    assert r["state"] == "disabled"
    time.sleep(0.15)
    assert sc.ticks == 0


def test_worker_survives_tick_exception(worker_cls):
    """tick 炸 → worker 不死: last_error 记账, 下一轮继续 (无人值守铁律)."""
    sc = _FakeScanner(boom=True)
    w = worker_cls(scanner=sc)
    w.start()
    try:
        deadline = time.time() + 3
        while sc.ticks < 2 and time.time() < deadline:
            time.sleep(0.02)
        assert sc.ticks >= 2                   # 异常后仍在跑
        st = w.status()
        assert st["running"] is True
        assert "scan boom" in (st["last_error"] or "")
    finally:
        w.stop()


def test_worker_status_shape(worker_cls):
    sc = _FakeScanner()
    w = worker_cls(scanner=sc)
    st = w.status()
    for k in ("enabled", "interval_s", "running", "ticks",
              "last_tick_at", "last_error", "scanner"):
        assert k in st, f"status 缺字段 {k}"


def test_worker_interval_from_env(monkeypatch, worker_cls):
    monkeypatch.setenv("UEA_INBOUND_SCAN_INTERVAL", "42")
    w = worker_cls(scanner=_FakeScanner())
    assert w.interval == 42


# ---------- 5. api lifespan 接线 + 端点 ----------

def test_conftest_inbound_kill_switch_active():
    """pytest 进程默认必须带 UEA_INBOUND_SCAN=0 (conftest 双保险, 同 mail autostart)."""
    import os
    assert os.environ.get("UEA_INBOUND_SCAN") == "0"


def test_lifespan_starts_and_stops_inbound_worker(monkeypatch):
    started = {"n": 0}

    def fake_start_once():
        started["n"] += 1
        w = type("W", (), {"stop": lambda self, timeout=5.0: {"ok": True},
                           "status": lambda self: {"running": False}})()
        apiserver._inbound_bg["worker"] = w
        return w

    monkeypatch.setattr(apiserver, "_inbound_start_once", fake_start_once)
    monkeypatch.setenv("UEA_INBOUND_SCAN", "1")
    try:
        with TestClient(apiserver.app):
            pass
        assert started["n"] == 1
        assert "worker" not in apiserver._inbound_bg   # shutdown 已摘
    finally:
        apiserver._inbound_bg.pop("worker", None)


def test_inbound_kill_switch_env_zero_no_worker(monkeypatch):
    constructed = {"n": 0}

    def boom_start_once():
        constructed["n"] += 1
        raise AssertionError("kill switch 下不应构造 worker")

    monkeypatch.setattr(apiserver, "_inbound_start_once", boom_start_once)
    monkeypatch.setenv("UEA_INBOUND_SCAN", "0")
    with TestClient(apiserver.app):
        pass
    assert constructed["n"] == 0


def test_inbound_status_and_tick_endpoints(monkeypatch):
    monkeypatch.setenv("UEA_INBOUND_SCAN", "0")   # 不起真线程

    class _RecWorker:
        def __init__(self):
            self.runs = 0

        def run_once(self):
            self.runs += 1
            return {"scan": {"discovered": 0}, "run": {"processed": 0}}

        def status(self):
            return {"running": False, "ticks": self.runs, "enabled": True}

    w = _RecWorker()
    monkeypatch.setitem(apiserver._inbound_bg, "worker", w)
    try:
        with TestClient(apiserver.app) as c:
            d = c.get("/v1/inbound/status").json()
            assert d["running"] is False
            t = c.post("/v1/inbound/tick").json()
            assert t["ok"] is True
            assert w.runs == 1
    finally:
        apiserver._inbound_bg.pop("worker", None)


def test_inbound_tick_without_worker_503(monkeypatch):
    """无 worker (未启动/被 kill switch) → 503, 不私自构造 scanner 扫真实目录."""
    monkeypatch.setenv("UEA_INBOUND_SCAN", "0")
    monkeypatch.setitem(apiserver._inbound_bg, "worker", None)
    try:
        with TestClient(apiserver.app) as c:
            r = c.post("/v1/inbound/tick")
            assert r.status_code == 503
    finally:
        apiserver._inbound_bg.pop("worker", None)


def test_inbound_status_without_worker(monkeypatch):
    monkeypatch.setenv("UEA_INBOUND_SCAN", "0")
    monkeypatch.setitem(apiserver._inbound_bg, "worker", None)
    try:
        with TestClient(apiserver.app) as c:
            d = c.get("/v1/inbound/status").json()
            assert d["running"] is False
            assert "reason" in d
    finally:
        apiserver._inbound_bg.pop("worker", None)
