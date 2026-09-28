"""test_gmail_imap_api.py — v3.0 #41/#43/#47 Gmail IMAP 拉信 + API 端点单测.

8 条覆盖 (凭代码核对, mock imap_tools 不真连):
  GmailMailbox (4):
    1) connect() 无凭据 → ok=False, error="no credentials saved"
    2) connect() 注入 mock factory → login 成功, last_account=account
    3) sync() 拉 2 封新信 → fetched=2, 写 .eml+.meta.json, badges 含 NEW+GMAIL_PULLED
    4) sync() 重复拉 → skipped 正确, fetched=0
  API 端点 (4):
    5) GET /v1/gmail/status 默认 enabled=False
    6) POST /v1/gmail/settings 切 enabled=true
    7) POST /v1/gmail/connect 未启用 → 403
    8) POST /v1/gmail/disconnect 清凭据
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import credentials as cred_mod
from services import gmail_imap as gim
from services.api_server import app


# ---------- GmailMailbox mock ----------
class _MockMsg:
    def __init__(self, uid, frm, subj, date_str="Wed, 17 Sep 2026 10:00:00 +0800", body="hello", atts=None):
        self.uid = uid
        self.from_ = frm
        self.subject = subj
        self.date_str = date_str
        self.text = body
        self.html = None
        self.attachments = atts or []
    @property
    def to_values(self): return ["sales@union.io"]
    @property
    def cc_values(self): return []


class _MockFolder:
    def __init__(self, msgs): self.msgs = msgs
    def set(self, folder): pass


class _MockMailBox:
    def __init__(self, msgs):
        self.msgs = msgs
        self.logged_in = False
        self.folder = _MockFolder(msgs)
        self.fetch_kwargs = None
        self.flag_calls = []
    def login(self, account, password): self.logged_in = True; self.account=account
    def logout(self): self.logged_in = False
    def fetch(self, limit=None, reverse=False, **kwargs):
        self.fetch_kwargs = {"limit": limit, "reverse": reverse, **kwargs}
        return iter(self.msgs[:limit] if limit else self.msgs)
    def flag(self, uid_list, flag_set, value):
        self.flag_calls.append((uid_list, flag_set, value))


@pytest.fixture
def mb_dir(tmp_path, monkeypatch):
    """隔离 mailbox_dir + credentials file."""
    fake_cred = tmp_path / "credentials.json"
    monkeypatch.setattr(cred_mod, "CRED_FILE", fake_cred)
    gim.reset_global()
    return tmp_path


# ---------- GmailMailbox tests ----------
def test_connect_no_credentials(mb_dir):
    """未存凭据 → connect 返回 ok=False, last_error='no credentials saved'."""
    mb = gim.GmailMailbox(mailbox_dir=mb_dir)
    r = mb.connect()
    assert r["ok"] is False
    assert "no credentials" in r["error"].lower()
    assert mb.last_error is not None


def test_connect_with_mock(mb_dir):
    """注入 mock factory → login 成功, last_account 正确."""
    cred_mod.save_credentials("gmail", "alice@gmail.com", "abcd-efgh-ijkl-mnop")
    mb = gim.GmailMailbox(
        mailbox_dir=mb_dir,
        mailbox_factory=lambda host, port: _MockMailBox([]),
    )
    r = mb.connect()
    assert r["ok"] is True
    assert r["account"] == "alice@gmail.com"
    assert r["host"] == "imap.gmail.com"
    assert mb.last_account == "alice@gmail.com"
    mb.disconnect()


def test_sync_writes_eml_and_meta(mb_dir):
    """拉 2 封 → fetched=2, data/mailbox/*.eml + *.meta.json 各 2 个, 含 GMAIL_PULLED badge."""
    cred_mod.save_credentials("gmail", "alice@gmail.com", "abcd-efgh-ijkl-mnop")
    msgs = [
        _MockMsg("100", "alice@gmail.com", "RFQ 6061 bracket"),
        _MockMsg("101", "bob@buyer.com", "Need 50 pcs 304"),
    ]
    mb = gim.GmailMailbox(
        mailbox_dir=mb_dir,
        mailbox_factory=lambda host, port: _MockMailBox(msgs),
    )
    assert mb.connect()["ok"] is True
    r = mb.sync(limit=10)
    assert r["ok"] is True
    assert r["fetched"] == 2
    assert r["skipped"] == 0
    emls = list(mb_dir.glob("*.eml"))
    metas = list(mb_dir.glob("*.meta.json"))
    assert len(emls) == 2 and len(metas) == 2
    # meta 检查 badges
    for m in metas:
        meta = json.loads(m.read_text())
        assert "NEW" in meta["badges"]
        assert "GMAIL_PULLED" in meta["badges"]
        assert meta["source"] == "gmail-imap"
        assert meta["uid"] in ("100", "101")
    mb.disconnect()


def test_sync_idempotent(mb_dir):
    """二次 sync → skipped=2, fetched=0 (幂等)."""
    cred_mod.save_credentials("gmail", "alice@gmail.com", "abcd-efgh-ijkl-mnop")
    msgs = [_MockMsg("200", "alice@gmail.com", "first mail")]
    mb = gim.GmailMailbox(
        mailbox_dir=mb_dir,
        mailbox_factory=lambda host, port: _MockMailBox(msgs),
    )
    assert mb.connect()["ok"] is True
    r1 = mb.sync(limit=10)
    assert r1["ok"] is True and r1["fetched"] == 1
    r2 = mb.sync(limit=10)
    assert r2["ok"] is True and r2["fetched"] == 0
    assert r2["skipped"] == 1
    mb.disconnect()


def test_sync_uses_unseen_and_does_not_mark_seen(mb_dir):
    """2026-09-24: 拉取必须只取未读且不提前标已读 — 处理完才由 mark_read 标."""
    cred_mod.save_credentials("gmail", "alice@gmail.com", "abcd-efgh-ijkl-mnop")
    holder = {}
    msgs = [_MockMsg("300", "bob@buyer.com", "RFQ quote")]
    mb = gim.GmailMailbox(
        mailbox_dir=mb_dir,
        mailbox_factory=lambda host, port: holder.setdefault("c", _MockMailBox(msgs)) or holder["c"],
    )
    assert mb.connect()["ok"] is True
    mb.sync(limit=10)
    kw = holder["c"].fetch_kwargs
    assert kw["criteria"] == "UNSEEN"
    assert kw["mark_seen"] is False
    assert holder["c"].flag_calls == []  # 拉取阶段绝不动 \Seen
    mb.disconnect()


# ---------- mark_read (\Seen 标记已读, 2026-09-24) ----------
def test_mark_read_flags_seen(mb_dir):
    """mark_read(uid) → flag STORE \\Seen=True, 返回 ok."""
    cred_mod.save_credentials("gmail", "alice@gmail.com", "abcd-efgh-ijkl-mnop")
    holder = {}
    msgs = [_MockMsg("400", "bob@buyer.com", "RFQ quote")]
    mb = gim.GmailMailbox(
        mailbox_dir=mb_dir,
        mailbox_factory=lambda host, port: holder.setdefault("c", _MockMailBox(msgs)) or holder["c"],
    )
    assert mb.connect()["ok"] is True
    r = mb.mark_read("400", folder="INBOX")
    assert r["ok"] is True
    assert holder["c"].flag_calls == [("400", ("\\Seen",), True)]
    mb.disconnect()


def test_mark_read_auto_connect(mb_dir):
    """未连接时 mark_read 自动 connect (凭据在)."""
    cred_mod.save_credentials("gmail", "alice@gmail.com", "abcd-efgh-ijkl-mnop")
    holder = {}
    mb = gim.GmailMailbox(
        mailbox_dir=mb_dir,
        mailbox_factory=lambda host, port: holder.setdefault("c", _MockMailBox([])) or holder["c"],
    )
    r = mb.mark_read("401")
    assert r["ok"] is True
    assert holder["c"].flag_calls == [("401", ("\\Seen",), True)]


def test_mark_read_no_credentials(mb_dir):
    """无凭据 → ok=False 显式报错, 不静默."""
    mb = gim.GmailMailbox(
        mailbox_dir=mb_dir,
        mailbox_factory=lambda host, port: _MockMailBox([]),
    )
    r = mb.mark_read("402")
    assert r["ok"] is False
    assert "no credentials" in r["error"].lower()


def test_mark_mailbox_read_writes_meta(mb_dir):
    """模块级 mark_mailbox_read: 读 meta uid/folder + gmail_settings → flag → 回写 meta."""
    cred_mod.save_credentials("gmail", "alice@gmail.com", "abcd-efgh-ijkl-mnop")
    holder = {}
    box = mb_dir / "data" / "mailbox"
    box.mkdir(parents=True)
    (box / "g_abc.meta.json").write_text(json.dumps({
        "uid": "500", "folder": "INBOX", "badges": ["NEW", "GMAIL_PULLED"],
        "source": "gmail-imap",
    }), encoding="utf-8")
    (mb_dir / "data" / "gmail_settings.json").write_text(json.dumps({
        "enabled": True, "service": "gmail", "host": "imap.gmail.com", "port": 993,
    }), encoding="utf-8")
    r = gim.mark_mailbox_read(mb_dir, "g_abc", factory=lambda host, port: holder.setdefault(
        "c", _MockMailBox([])) or holder["c"])
    assert r["ok"] is True
    assert holder["c"].flag_calls == [("500", ("\\Seen",), True)]
    meta = json.loads((box / "g_abc.meta.json").read_text())
    assert meta["imap_read_at"] is not None
    assert meta["imap_read_uid"] == "500"


def test_mark_mailbox_read_missing_meta(mb_dir):
    """meta 缺失 (mock 上传件) → ok=False 显式, 不猜 uid."""
    r = gim.mark_mailbox_read(mb_dir, "no_such_mail")
    assert r["ok"] is False
    assert "meta" in r["error"]


# ---------- API tests ----------
@pytest.fixture
def api_client(tmp_path, monkeypatch):
    """隔离运行时文件: SETTINGS_FILE + CRED_FILE 重定向 tmp, 不碰仓库真实配置."""
    import services.gmail_api as ga

    monkeypatch.setattr(ga, "SETTINGS_FILE", tmp_path / "gmail_settings.json")
    monkeypatch.setattr(cred_mod, "CRED_FILE", tmp_path / "credentials.json")
    with TestClient(app) as c:
        yield c
    ga._MAILBOX = None


def test_gmail_status_default_disabled(api_client):
    """GET /v1/gmail/status 默认 enabled=False."""
    r = api_client.get("/v1/gmail/status")
    assert r.status_code == 200
    d = r.json()
    assert "settings" in d
    assert d["settings"].get("enabled") is False


def test_gmail_settings_toggle(api_client):
    """POST /v1/gmail/settings 切 enabled=true."""
    r = api_client.post("/v1/gmail/settings", json={"enabled": True})
    assert r.status_code == 200
    d = r.json()
    assert d["saved"] is True
    assert d["settings"]["enabled"] is True
    # 复位
    api_client.post("/v1/gmail/settings", json={"enabled": False})


def test_gmail_connect_403_when_disabled(api_client):
    """未启用时 POST /v1/gmail/connect → 403 'gmail disabled'."""
    api_client.post("/v1/gmail/settings", json={"enabled": False})
    r = api_client.post("/v1/gmail/connect", json={"email": "alice@gmail.com", "app_password": "abcd-efgh-ijkl-mnop"})
    assert r.status_code == 403
    assert "gmail disabled" in r.json()["detail"].lower()


def test_gmail_disconnect_clears(api_client):
    """POST /v1/gmail/disconnect → 200 ok=True, 凭据清空."""
    r = api_client.post("/v1/gmail/disconnect")
    assert r.status_code == 200
    d = r.json()
    assert d.get("ok") is True
    # credentials 列表应空 (或保持空)
    s = api_client.get("/v1/gmail/status").json()
    assert s.get("credentials", {}).get("services", []) == []


# ---------- Round C: 挂死加固 — IMAP socket 级 timeout (2026-09-24) ----------
class _SpyMailBox:
    """捕获 MailBox(host, port, timeout=...) 构造 kwargs; 不真连."""
    instances: list = []

    def __init__(self, *args, **kwargs):
        self.init_args = args
        self.init_kwargs = kwargs
        self.folder = _MockFolder([])
        self.logged_in = False
        _SpyMailBox.instances.append(self)

    def login(self, account, password):
        self.logged_in = True

    def logout(self):
        self.logged_in = False


def test_make_client_passes_bounded_socket_timeout(mb_dir, monkeypatch):
    """Round C2: MailBox 必须带 socket 级 timeout — 半开连接 (connect 过了但
    login/fetch 永不应答) 才能被 socket timeout 打破, 否则 puller 线程永久挂死."""
    _SpyMailBox.instances.clear()
    monkeypatch.setattr("imap_tools.MailBox", _SpyMailBox)
    mb = gim.GmailMailbox(mailbox_dir=mb_dir)
    client = mb._make_client()
    assert isinstance(client, _SpyMailBox)
    assert "timeout" in client.init_kwargs
    assert client.init_kwargs["timeout"] == gim.IMAP_TIMEOUT_S


def test_make_client_custom_timeout_and_constant_bounds(mb_dir, monkeypatch):
    """自定义 timeout 透传; 默认常量必须是有界正数 (30s 量级)."""
    _SpyMailBox.instances.clear()
    monkeypatch.setattr("imap_tools.MailBox", _SpyMailBox)
    mb = gim.GmailMailbox(mailbox_dir=mb_dir, timeout=7.5)
    client = mb._make_client()
    assert client.init_kwargs["timeout"] == 7.5
    assert isinstance(gim.IMAP_TIMEOUT_S, (int, float))
    assert 0 < gim.IMAP_TIMEOUT_S <= 60


def test_connect_uses_timeout_end_to_end(mb_dir, monkeypatch):
    """connect() 真路径: mock MailBox 收 timeout 且 login 成功 — 证明超时
    覆盖 connect+login 全过程 (imaplib 同一 socket, 非仅 TCP connect)."""
    cred_mod.save_credentials("gmail", "alice@gmail.com", "abcd-efgh-ijkl-mnop")
    _SpyMailBox.instances.clear()
    monkeypatch.setattr("imap_tools.MailBox", _SpyMailBox)
    mb = gim.GmailMailbox(mailbox_dir=mb_dir, timeout=12.0)
    r = mb.connect()
    assert r["ok"] is True
    assert _SpyMailBox.instances[0].init_kwargs["timeout"] == 12.0
    mb.disconnect()