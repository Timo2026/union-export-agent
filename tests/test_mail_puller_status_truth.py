"""test_mail_puller_status_truth.py — 2026-09-25 邮件拉取器状态真相契约 (E3 Fix A).

事故背景 (节点公网 :8051 状态页): 凭据解密失败 (UEA_APP_SECRET 不在
服务进程环境) → is_enabled()=False → lifespan autostart 走 "disabled", puller
线程从未启动; 而 data/mail_puller/state.json 是上一个进程 (2214851) 留下的
running=True 遗留值。于是:
  - 状态页 "邮件拉取器" 卡片读 /v1/gmail/status 的缓存 mailbox 单例 connected
    (结构上恒为 false) → 显示 "未连接·最近同步 0 封"
  - 邮箱抽屉健康卡读 state.running 遗留值 → 显示 "运行中"
两个视图各信了一个假字段。

本文件锁定的真相契约 (RED→GREEN, 禁止改断言迁就实现):
  1. /v1/mail/puller/status: running / thread_alive 只信本进程线程; state.json
     的 running 是遗留值, 线程不在必须纠偏为 False
  2. pid_alive 如实反映 state.pid 的进程活性 (跨进程遗留 pid ≠ 本 puller)
  3. /v1/gmail/status 的 puller 块:
       credentials_ok   = 解密级真相 (load_credentials(service) is not None)
       settings_enabled = 配置意图 (gmail_settings.enabled)
       enabled          = 两者与 (puller 该不该跑)
       thread_alive     = 本进程后台线程活性 (不拿 mailbox 单例 connected 冒充)
  4. lifespan 拉起的 puller 实例必须注册为 get_puller() 单例 (set_global),
     控制台端点才能读到同一实例的线程真相
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from services import api_server
from services.api_server import app

DEAD_PID = 999999


@pytest.fixture(autouse=True)
def _reset_mail_bg():
    """隔离 api_server._mail_bg, 测试后还原 (避免跨文件污染)."""
    saved = dict(api_server._mail_bg)
    api_server._mail_bg.clear()
    yield
    api_server._mail_bg.clear()
    api_server._mail_bg.update(saved)


def _write_gmail_settings(root: Path, *, enabled: bool = True, service: str = "gmail") -> None:
    p = root / "data" / "gmail_settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"enabled": enabled, "service": service}), encoding="utf-8")


def _write_state(root: Path, **kw: Any) -> None:
    """写遗留 state.json (默认模拟上个进程留下的 running=True)."""
    d = root / "data" / "mail_puller"
    d.mkdir(parents=True, exist_ok=True)
    base: dict = {
        "enabled": True, "running": True, "last_pull_at": 1790000000.0,
        "last_error": None, "consecutive_failures": 0, "next_pull_at": None,
        "total_pulled": 74, "total_pending": 10, "started_at": 1790000000.0,
        "pid": DEAD_PID,
    }
    base.update(kw)
    (d / "state.json").write_text(json.dumps(base), encoding="utf-8")


class _NoMailClient:
    """mock IMAP 客户端: 空收件箱, 2 条消息上限."""

    class _Folder:
        def set(self, name: str) -> None:
            pass

    def __init__(self) -> None:
        self.folder = self._Folder()

    def login(self, user: str, pwd: str) -> None:
        pass

    def logout(self) -> None:
        pass

    def fetch(self, limit: int = 50, reverse: bool = True, **kwargs):
        return iter([])

    def flag(self, uid_list, flag_set, value) -> None:
        pass


@pytest.fixture
def cred_file(tmp_path, monkeypatch):
    """隔离全局 credentials: 注入可解密凭据文件 (同进程同密钥, save→load 往返)."""
    from services import credentials as cred_mod

    p = tmp_path / "credentials.json"
    monkeypatch.setattr(cred_mod, "CRED_FILE", p)
    return p


# ---------- 1) /v1/mail/puller/status: 遗留 state.running 必须被线程真相纠偏 ----------

def test_stale_state_running_corrected_by_thread_truth(tmp_path, monkeypatch):
    """遗留 state.json running=True (上个进程写的) + 本进程无 puller 线程 →
    running=False / thread_alive=False / state.running=False / pid_alive=False.

    这正是事故日的节点现场: 文件说在跑, 线程根本没起。
    """
    from services.mail_puller import MailPuller

    _write_state(tmp_path, running=True, pid=DEAD_PID)
    p = MailPuller(root=tmp_path)
    monkeypatch.setitem(api_server._mail_bg, "puller", p)
    with TestClient(app) as c:
        r = c.get("/v1/mail/puller/status")
    assert r.status_code == 200
    d = r.json()
    assert d["thread_alive"] is False
    assert d["running"] is False
    assert d["puller"]["state"]["running"] is False  # 遗留值被打假
    assert d["pid_alive"] is False                    # DEAD_PID 不是活进程


def test_live_thread_makes_running_true(tmp_path, monkeypatch, cred_file):
    """真启 puller 线程 (mock IMAP 工厂 + 注入凭据) → thread_alive/running True,
    state.running True, pid=本进程, pid_alive True."""
    from services import credentials as cred_mod
    from services.mail_puller import MailPuller

    _write_gmail_settings(tmp_path)
    cred_mod.save_credentials("gmail", "alice@gmail.com", "fake-app-pwd")
    p = MailPuller(root=tmp_path, interval_s=60, cred_file_path=cred_file,
                   mailbox_factory=lambda h, prt: _NoMailClient())
    r0 = p.start()
    assert r0["ok"] is True
    monkeypatch.setitem(api_server._mail_bg, "puller", p)
    try:
        with TestClient(app) as c:
            r = c.get("/v1/mail/puller/status")
        d = r.json()
        assert d["thread_alive"] is True
        assert d["running"] is True
        assert d["puller"]["state"]["running"] is True
        assert d["puller"]["state"]["pid"] == os.getpid()
        assert d["pid_alive"] is True
    finally:
        p.stop(timeout=3.0)


# ---------- 2) /v1/gmail/status puller 块: 解密级真相, 不用 mailbox 单例冒充 ----------

def _register_puller(tmp_path, monkeypatch) -> None:
    from services import mail_puller as mp
    from services.mail_puller import MailPuller

    p = MailPuller(root=tmp_path)
    monkeypatch.setattr(mp, "_global", p)


def test_gmail_status_puller_block_credentials_failed(tmp_path, monkeypatch):
    """settings.enabled=true 但凭据不可解密 (事故形态) →
    settings_enabled=True, credentials_ok=False, enabled=False, thread_alive=False.

    RED 依据: 修复前 /v1/gmail/status 没有 puller 块 (只有恒 false 的 mailbox)。
    """
    from services import gmail_api as ga
    from services import credentials as cred_mod

    sett = tmp_path / "gmail_settings.json"
    sett.write_text(json.dumps({"enabled": True, "service": "qq",
                                "host": "imap.qq.com", "port": 993}), encoding="utf-8")
    monkeypatch.setattr(ga, "SETTINGS_FILE", sett)
    # 凭据文件条目在, 但加密体不可解密 (密钥不匹配 → load_credentials 静默 None)
    cred = tmp_path / "credentials.json"
    cred.write_text(json.dumps({"services": {"qq": {
        "account": "tester@qq.com",
        "encrypted": "gAAAAABogus-not-decryptable-under-any-key",
        "cipher": "fernet",
    }}}), encoding="utf-8")
    monkeypatch.setattr(cred_mod, "CRED_FILE", cred)
    _register_puller(tmp_path, monkeypatch)
    with TestClient(app) as c:
        r = c.get("/v1/gmail/status")
    assert r.status_code == 200
    d = r.json()
    assert d["settings"]["enabled"] is True
    pl = d["puller"]
    assert pl["settings_enabled"] is True
    assert pl["credentials_ok"] is False   # 解密级真相: 条目在也不等于可用
    assert pl["enabled"] is False          # puller 不该跑
    assert pl["thread_alive"] is False
    assert pl["state"]["running"] is False


def test_gmail_status_puller_block_live(tmp_path, monkeypatch, cred_file):
    """凭据可解密 + 线程活着 → credentials_ok/enabled/thread_alive 全 True."""
    from services import credentials as cred_mod
    from services import gmail_api as ga
    from services import mail_puller as mp
    from services.mail_puller import MailPuller

    _write_gmail_settings(tmp_path)  # puller 自身 root 的 settings (is_enabled 读它)
    sett = tmp_path / "data" / "gmail_settings.json"
    monkeypatch.setattr(ga, "SETTINGS_FILE", sett)  # API 端点读同一份
    cred_mod.save_credentials("gmail", "alice@gmail.com", "fake-app-pwd")
    p = MailPuller(root=tmp_path, interval_s=60, cred_file_path=cred_file,
                   mailbox_factory=lambda h, prt: _NoMailClient())
    monkeypatch.setattr(mp, "_global", p)
    r0 = p.start()
    assert r0["ok"] is True
    try:
        with TestClient(app) as c:
            r = c.get("/v1/gmail/status")
        d = r.json()
        pl = d["puller"]
        assert pl["settings_enabled"] is True
        assert pl["credentials_ok"] is True
        assert pl["enabled"] is True
        assert pl["thread_alive"] is True
        assert pl["state"]["running"] is True
    finally:
        p.stop(timeout=3.0)


# ---------- 3) lifespan 注册的单例同源 ----------

def test_bg_start_once_registers_shared_singleton(tmp_path, monkeypatch):
    """_mail_bg_start_once 拉起的实例必须注册为 get_puller() 单例
    (disabled 路径也要注册 — 控制台端点才能读到同一实例的 state/线程真相)."""
    from services import mail_puller as mp

    monkeypatch.setattr(api_server, "_ROOT", tmp_path)
    r = api_server._mail_bg_start_once()
    assert r["state"] == "disabled"  # 无 settings/凭据 → disabled 路径
    assert api_server._mail_bg["puller"] is not None
    assert mp.get_puller() is api_server._mail_bg["puller"]
    assert api_server._mail_bg["puller"].root == tmp_path
    mp.reset_global()  # set_global 直写模块全局, 测试后复位防跨文件泄漏


def test_set_global_registers_instance(tmp_path):
    """set_global 后 get_puller 返回同一实例 (公开 API, 不许改私有 _global)."""
    from services import mail_puller as mp
    from services.mail_puller import MailPuller

    p = MailPuller(root=tmp_path)
    mp.set_global(p)
    try:
        assert mp.get_puller() is p
    finally:
        mp.reset_global()
