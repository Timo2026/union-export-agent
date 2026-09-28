"""inbound_worker.py — data/inbound 常驻扫描 worker (zip 邮件断点 3 修复, 2026-09-26).

InboundScanner 状态机完备 (幂等 item_key + 扫描/解包/BOM 批量报价), 但全仓零
调用方 — zip 丢进 data/inbound 无人处理, 邮箱 zip 附件落盘后也不会自动流转。
本 worker 补上常驻调度: daemon 线程按 interval 调 scanner.tick() (扫一次 + 处理
一次), 镜像 mail autostart 的双层门禁:
  - env UEA_INBOUND_SCAN=0 → 整体 disable (disabled 是配置意图, 不起线程)
  - interval 从 UEA_INBOUND_SCAN_INTERVAL 读 (默认 30s); <=0 → disabled
LINK-3 双保险: pytest conftest 默认置 UEA_INBOUND_SCAN=0, 测试进程永不自动扫。

无人值守语义 (与 puller watchdog 同型):
  - tick 抛异常不死线程 — last_error 记账, 下一轮继续
  - stop() 幂等; lifespan shutdown 统一收敛
  - status() 全量可观测 (interval/running/ticks/last_error + scanner 状态)
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

DEFAULT_INBOUND_SCAN_INTERVAL_S = 30


class InboundScannerWorker:
    """InboundScanner 的常驻调度壳 (不掺报价逻辑, 只管起停/观测/容错)。"""

    def __init__(self, root: Optional[Path] = None,
                 interval_s: Optional[float] = None,
                 scanner: Any = None) -> None:
        self.root = Path(root) if root else Path.cwd()
        if interval_s is None:
            try:
                interval_s = float(os.environ.get(
                    "UEA_INBOUND_SCAN_INTERVAL", DEFAULT_INBOUND_SCAN_INTERVAL_S))
            except (TypeError, ValueError):
                interval_s = DEFAULT_INBOUND_SCAN_INTERVAL_S
        self.interval = float(interval_s)
        self.enabled = (os.environ.get("UEA_INBOUND_SCAN", "1") != "0"
                        and self.interval > 0)
        if scanner is None:
            from services.inbound_scanner import InboundScanner
            scanner = InboundScanner(root=self.root)
        self.scanner = scanner
        self.ticks = 0
        self.last_tick_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---------- 生命周期 ----------
    def start(self) -> Dict[str, Any]:
        """起 daemon 线程。disabled → 不起 (配置意图, 非故障)。"""
        if not self.enabled:
            return {"state": "disabled", "interval_s": self.interval}
        if self._thread is not None and self._thread.is_alive():
            return {"state": "running"}
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop,
                                        name="inbound_scanner", daemon=True)
        self._thread.start()
        log.info("[inbound_worker] started (interval=%.1fs)", self.interval)
        return {"state": "started", "interval_s": self.interval}

    def stop(self, timeout: float = 5.0) -> Dict[str, Any]:
        self._stop_event.set()
        t = self._thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=timeout)
        return {"ok": True}

    def run_once(self) -> Dict[str, Any]:
        """扫一次 + 处理一次 (也是手动 tick 端点的最小单元)。"""
        self.last_error = None
        r = self.scanner.tick()
        self.ticks += 1
        self.last_tick_at = time.time()
        return r

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_once()
            except Exception as e:  # noqa: BLE001 — 无人值守: 单轮炸不死线程
                self.last_error = repr(e)
                log.warning("[inbound_worker] tick failed (继续下一轮): %r", e)
            self._stop_event.wait(timeout=self.interval)

    # ---------- 观测 ----------
    def status(self) -> Dict[str, Any]:
        running = bool(self._thread is not None and self._thread.is_alive())
        out: Dict[str, Any] = {
            "enabled": self.enabled,
            "interval_s": self.interval,
            "running": running,
            "ticks": self.ticks,
            "last_tick_at": self.last_tick_at,
            "last_error": self.last_error,
        }
        try:
            out["scanner"] = self.scanner.status()
        except Exception as e:  # noqa: BLE001 — 观测不炸
            out["scanner_error"] = repr(e)
        return out
