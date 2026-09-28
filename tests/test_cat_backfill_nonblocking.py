"""test_cat_backfill_nonblocking.py — cat 初始化回填不得阻塞构造 (2026-09-26 节点事故回归)。

事故链: Q3 backfill_if_stale 在 CATController.__init__ 同步全量回填 (crm 上千条
× 在线 embed, 首调 ~10s) → CAT 构造发生在 api_server lifespan 的 mail autostart
(_mail_bg_start_once → build_controller) → uvicorn 卡在 "Waiting for application
startup" >6min 不绑端口 → 公网 :8051 全断。本地测试全绿也没抓到: 测试直构造 CAT
不走 lifespan。

本文件锁死契约:
  1. 构造秒回 — 回填转后台 daemon 线程 (startup 永不依赖回填完成);
  2. 回填最终仍执行 (Q3 收益不丢, 只是不再卡启动);
  3. env UEA_QUOTE_BACKFILL=0 可整体关停 (与 UEA_MAIL_AUTOSTART 同款运维闸)。
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from bootstrap import build_controller

_ROOT = Path(__file__).resolve().parent.parent


class _StubGateway:
    """记录调用 + 可阻塞的 backfill 桩 (模拟节点慢 embed 全量回填)。"""

    def __init__(self):
        self.calls = 0
        self.release = threading.Event()
        self.done = threading.Event()

    def backfill_if_stale(self, stale_ratio: float = 0.9):
        self.calls += 1
        assert self.release.wait(timeout=10), "stub backfill never released"
        self.done.set()
        return {"backfilled": True, "reason": "stale"}


@pytest.fixture
def stub_gw(monkeypatch):
    import services.rag_layers as rl
    gw = _StubGateway()
    monkeypatch.setattr(rl, "LayeredRAGGateway", lambda **kw: gw)
    return gw


@pytest.fixture
def cat_settings(tmp_path):
    from services.config import load_settings
    s = load_settings(_ROOT)
    s.setdefault("storage", {})["crm_db"] = str(tmp_path / "crm.sqlite3")
    s.setdefault("storage", {})["contexts_dir"] = str(tmp_path / "contexts")
    s["rag_layers"] = {"enabled": True, "vector_backend": "memory",
                       "embed_url": "http://127.0.0.1:59998/v1"}
    s["funasr"] = dict(s.get("funasr") or {}, embed_url="http://127.0.0.1:59998")
    return s


def test_cat_init_returns_without_waiting_for_backfill(cat_settings, stub_gw):
    """构造秒回 (回填阻塞 10s 级也不能拖慢) + 后台线程最终执行回填。"""
    t0 = time.monotonic()
    ctrl = build_controller(settings_override=cat_settings)
    elapsed = time.monotonic() - t0
    assert ctrl.rag_gateway is not None, "网关应仍在 (回填失败也不降级 None)"
    assert elapsed < 1.5, (
        f"CATController 构造被回填阻塞 {elapsed:.1f}s — api startup 杀手 "
        f"(节点事故: >6min 卡 Waiting for application startup)")
    stub_gw.release.set()
    assert stub_gw.done.wait(timeout=5), "回填被丢弃: 后台线程未执行"
    assert stub_gw.calls == 1


def test_backfill_env_killswitch(cat_settings, stub_gw, monkeypatch):
    """UEA_QUOTE_BACKFILL=0 → 不建回填线程 (运维急停闸)。"""
    monkeypatch.setenv("UEA_QUOTE_BACKFILL", "0")
    ctrl = build_controller(settings_override=cat_settings)
    assert ctrl.rag_gateway is not None
    time.sleep(0.3)
    assert stub_gw.calls == 0, "UEA_QUOTE_BACKFILL=0 时不应回填"
