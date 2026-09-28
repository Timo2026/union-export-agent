"""tests/test_mail_puller.py — T1: 邮件轮询 puller + 状态机 (8 用例).

覆盖:
  1. start/stop 基础启停 (后台线程)
  2. is_enabled 三种场景 (enabled + cred / enabled 无 cred / disabled)
  3. poll_once 成功路径 (mock IMAP 工厂 → 落 .eml + enqueue pending)
  4. poll_once IMAP 连接失败 → 退避计数
  5. poll_once sync 失败 → 退避计数
  6. 状态机: NEW → PROCESSING → DONE 完整流程
  7. claim_next_new 原子性 + 并发安全
  8. mark_state 非法 state 拒绝 + mail_id 不存在返 False
"""
from __future__ import annotations

import contextlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

# 必须在 import services.mail_puller 前
ROOT = Path(__file__).resolve().parent.parent

from services.mail_puller import PendingEntry  # noqa: E402,F401


@pytest.fixture
def tmp_root(tmp_path: Path, isolated_creds) -> Path:
    """为每个测试建独立 root 目录 + 全局 credentials 隔离."""
    (tmp_path / "data").mkdir()
    return tmp_path


@pytest.fixture
def mock_imap_factory():
    """Mock imap_tools.MailBox: 返回 2 封假邮件."""
    from email.message import EmailMessage

    class MockMsg:
        def __init__(self, uid: str, frm: str, subj: str, body: str = "Hello"):
            self.uid = uid
            self.from_ = frm
            self.subject = subj
            self.text = body
            self.html = None
            self.to_values: List[str] = []
            self.cc_values: List[str] = []
            self.date_str = "2026-09-19 10:00:00"
            self.attachments: List[Any] = []

    class MockFolder:
        def set(self, name: str) -> None:
            pass

    class MockClient:
        def __init__(self):
            self.folder = MockFolder()
            self._logged_in = False
            self._msgs = [
                MockMsg("u-001", "alice@northwind.com", "RFQ 6061 brackets", "Need quote 50 pcs"),
                MockMsg("u-002", "bob@acme.de", "TC4 urgent", "10 pcs titanium"),
            ]

        def login(self, user: str, pwd: str) -> None:
            self._logged_in = True

        def logout(self) -> None:
            self._logged_in = False

        def fetch(self, limit: int = 50, reverse: bool = True, **kwargs):
            assert self._logged_in, "must login first"
            return iter(self._msgs[:limit])

        def flag(self, uid_list, flag_set, value):
            pass

    def factory(host: str, port: int) -> MockClient:
        return MockClient()

    return factory


@pytest.fixture
def failing_factory():
    """总是抛异常的 IMAP 工厂 (测失败路径)."""
    def factory(host: str, port: int):
        class Bad:
            def login(self, *a, **kw):
                raise ConnectionError("imap refused")

            def logout(self):
                pass

            def folder(self):
                class F:
                    def set(self, n): pass

                return F()

            def fetch(self, *a, **kw):
                raise TimeoutError("fetch timeout")

        return Bad()

    return factory


def _write_gmail_settings(root: Path, *, enabled: bool = True, host: str = "imap.gmail.com", port: int = 993) -> Path:
    p = root / "data" / "gmail_settings.json"
    p.write_text(json.dumps({"enabled": enabled, "host": host, "port": port}), encoding="utf-8")
    return p


def _write_credentials(root: Path, account: str = "test@gmail.com", password: str = "fake-app-pwd") -> None:
    from services.credentials import save_credentials
    save_credentials("gmail", account, password)


def _make_puller(tmp_root: Path, factory=None) -> Any:
    from services.mail_puller import MailPuller
    return MailPuller(root=tmp_root, interval_s=0.5, limit=10, mailbox_factory=factory)


# ---- 1. start/stop 基础 ----
def test_start_stop_background_thread(tmp_root: Path, mock_imap_factory) -> None:
    _write_gmail_settings(tmp_root, enabled=True)
    _write_credentials(tmp_root)
    puller = _make_puller(tmp_root, factory=mock_imap_factory)
    r = puller.start()
    assert r["ok"] is True
    assert r["running"] is True
    # 给后台线程 1s 跑一次
    time.sleep(1.2)
    r2 = puller.stop(timeout=3.0)
    assert r2["ok"] is True
    assert r2["running"] is False
    # 至少跑过 1 次
    st = puller.status()
    assert st["state"]["last_pull_at"] is not None
    assert st["state"]["consecutive_failures"] == 0


# ---- 2. is_enabled 三态 ----
def test_is_enabled_three_states(tmp_root: Path) -> None:
    # (a) 无 settings → disabled
    p = _make_puller(tmp_root)
    assert p.is_enabled() is False
    # (b) settings.enabled=true 但无 credentials → disabled
    _write_gmail_settings(tmp_root, enabled=True)
    assert p.is_enabled() is False
    # (c) settings.enabled=false 即使有 credentials → disabled
    _write_credentials(tmp_root)
    _write_gmail_settings(tmp_root, enabled=False)
    assert p.is_enabled() is False
    # (d) 全开 → enabled
    _write_gmail_settings(tmp_root, enabled=True)
    assert p.is_enabled() is True


# ---- 3. poll_once 成功 ----
def test_poll_once_success_enqueues_pending(tmp_root: Path, mock_imap_factory) -> None:
    _write_gmail_settings(tmp_root, enabled=True)
    _write_credentials(tmp_root)
    puller = _make_puller(tmp_root, factory=mock_imap_factory)
    res = puller.poll_once()
    assert res["ok"] is True
    assert res["fetched"] == 2
    assert res["enqueued"] == 2
    # mailbox 应有 2 个 .eml + 2 个 .meta.json
    emls = list((tmp_root / "data" / "mailbox").glob("*.eml"))
    metas = list((tmp_root / "data" / "mailbox").glob("*.meta.json"))
    assert len(emls) == 2
    assert len(metas) == 2
    # pending.jsonl 应有 2 行 NEW
    pendings = puller.list_by_state("NEW")
    assert len(pendings) == 2
    # 二次 poll_once → 已存在 skipped=2, enqueued=0
    res2 = puller.poll_once()
    assert res2["ok"] is True
    assert res2["enqueued"] == 0
    assert puller.list_by_state("NEW") == puller.list_by_state("NEW")  # 仍 2 条 NEW (未处理)


# ---- 4. 失败重试 + 退避计数 ----
def test_failure_records_and_backoff(tmp_root: Path, failing_factory) -> None:
    _write_gmail_settings(tmp_root, enabled=True)
    _write_credentials(tmp_root)
    puller = _make_puller(tmp_root, factory=failing_factory)
    # 1st failure
    r = puller.poll_once()
    assert r["ok"] is False
    assert r["stage"] == "connect"
    st = puller.status()
    assert st["state"]["consecutive_failures"] == 1
    assert "imap refused" in (st["state"]["last_error"] or "")
    # 2nd failure
    r2 = puller.poll_once()
    assert r2["ok"] is False
    assert puller.status()["state"]["consecutive_failures"] == 2
    # 3rd failure
    puller.poll_once()
    assert puller.status()["state"]["consecutive_failures"] == 3
    # 成功后归零
    # 替换为成功 factory → poll_once 应清零
    from services.mail_puller import MailPuller
    puller2 = MailPuller(root=tmp_root, interval_s=0.5, limit=10, mailbox_factory=lambda h, p: None)
    # 注入成功工厂: 直接 mock IMAP 拉 1 封
    class GoodMsg:
        uid = "g-001"
        from_ = "ok@x.com"
        subject = "OK"
        text = "OK"
        html = None
        to_values: List[str] = []
        cc_values: List[str] = []
        date_str = "2026-09-19"
        attachments: List[Any] = []

    class GoodClient:
        folder = type("F", (), {"set": lambda self, n: None})()
        def login(self, *a, **kw): pass
        def logout(self): pass
        def fetch(self, limit=50, reverse=True, **kwargs): return iter([GoodMsg()])
        def flag(self, *a, **kw): pass

    puller2._factory = lambda h, p: GoodClient()
    # puller2 独立, 不会影响前一个
    r3 = puller2.poll_once()
    assert r3["ok"] is True
    assert puller2.status()["state"]["consecutive_failures"] == 0


# ---- 5. 状态机完整流程 NEW→PROCESSING→DONE ----
def test_state_machine_full_lifecycle(tmp_root: Path) -> None:
    _write_gmail_settings(tmp_root, enabled=False)  # 避免真实拉信
    puller = _make_puller(tmp_root)
    # 手工写 3 条 NEW
    from services.mail_puller import PendingEntry, STATE_NEW, STATE_PROCESSING, STATE_DONE, STATE_HITL, STATE_FAILED
    entries = [PendingEntry(mail_id=f"M{i:03d}", state=STATE_NEW) for i in range(3)]
    puller._append_pending(entries)
    assert len(puller.list_by_state("NEW")) == 3
    # claim_next_new 应原子获取一个
    e = puller.claim_next_new(consumer="orchestrator")
    assert e is not None
    assert e.state == STATE_PROCESSING
    assert e.consumer == "orchestrator"
    assert e.started_at is not None
    # 现在 2 NEW + 1 PROCESSING
    assert len(puller.list_by_state("NEW")) == 2
    assert len(puller.list_by_state("PROCESSING")) == 1
    # mark_state DONE
    assert puller.mark_state(e.mail_id, STATE_DONE, context_id="RFQ-20260919-XYZ") is True
    assert len(puller.list_by_state("DONE")) == 1
    done = puller.list_by_state("DONE")[0]
    assert done.context_id == "RFQ-20260919-XYZ"
    assert done.finished_at is not None
    # mark_state HITL (另一个 mail)
    e2 = puller.claim_next_new()
    assert puller.mark_state(e2.mail_id, STATE_HITL, error="IT5 precision") is True
    assert len(puller.list_by_state("HITL")) == 1


# ---- 6. claim_next_new 原子性 ----
def test_claim_next_new_thread_safe(tmp_root: Path) -> None:
    _write_gmail_settings(tmp_root, enabled=False)
    puller = _make_puller(tmp_root)
    from services.mail_puller import PendingEntry, STATE_NEW
    puller._append_pending([PendingEntry(mail_id=f"M{i:03d}", state=STATE_NEW) for i in range(10)])
    claimed = []
    lock = threading.Lock()

    def worker():
        while True:
            e = puller.claim_next_new(consumer=f"worker-{threading.get_ident()}")
            if e is None:
                return
            with lock:
                claimed.append(e.mail_id)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)
    # 10 条应全部被 claim 一次 (无重复)
    assert len(claimed) == 10
    assert len(set(claimed)) == 10
    assert len(puller.list_by_state("NEW")) == 0
    assert len(puller.list_by_state("PROCESSING")) == 10


# ---- 7. mark_state 非法 state 拒绝 ----
def test_mark_state_invalid_rejected(tmp_root: Path) -> None:
    _write_gmail_settings(tmp_root, enabled=False)
    puller = _make_puller(tmp_root)
    from services.mail_puller import PendingEntry, STATE_NEW, MailPullerError
    puller._append_pending([PendingEntry(mail_id="M001", state=STATE_NEW)])
    with pytest.raises(MailPullerError):
        puller.mark_state("M001", "INVALID_STATE")
    with pytest.raises(MailPullerError):
        puller.mark_state("M001", "")
    # mail_id 不存在
    assert puller.mark_state("M-NOT-EXIST", "DONE") is False
    # 合法但不存在的 mail_id → False
    assert puller.mark_state("M-NOT-EXIST", "DONE") is False


# ---- 8. 持久化原子性 + 重启恢复 ----
def test_persistence_survives_restart(tmp_root: Path) -> None:
    _write_gmail_settings(tmp_root, enabled=False)
    puller1 = _make_puller(tmp_root)
    from services.mail_puller import PendingEntry, STATE_NEW
    puller1._append_pending([
        PendingEntry(mail_id="M-001", state=STATE_NEW),
        PendingEntry(mail_id="M-002", state="DONE"),
    ])
    # 新建第二个 puller 读同一目录 → 应看到同样数据
    puller2 = _make_puller(tmp_root)
    assert len(puller2._read_pending()) == 2
    # state.json 持久化
    puller1._update_state(consecutive_failures=2, last_error="x")
    puller3 = _make_puller(tmp_root)
    st = puller3._read_state()
    assert st.consecutive_failures == 2
    assert st.last_error == "x"


# ---- 9. P0 driver 标记: 默认值 ----
def test_pending_entry_driver_defaults(tmp_root: Path) -> None:
    from services.mail_puller import PendingEntry
    e = PendingEntry(mail_id="M-DRV-1")
    assert e.driver == "email"      # 邮件队列默认邮件驱动
    assert e.source_ref == ""


# ---- 10. P0 driver 标记: 旧数据向后兼容 ----
def test_pending_entry_from_dict_legacy_compat(tmp_root: Path) -> None:
    """旧 pending.jsonl 行无 driver/source_ref → 解析不炸, 默认 email."""
    from services.mail_puller import PendingEntry
    legacy = {
        "mail_id": "M-OLD-1", "state": "NEW", "queued_at": 1.0,
        "started_at": None, "finished_at": None, "context_id": None,
        "error": None, "consumer": None, "attempts": 0,
    }
    e = PendingEntry.from_dict(legacy)
    assert e.driver == "email"
    assert e.source_ref == ""
    d = e.to_dict()
    assert d["driver"] == "email"
    # round-trip
    assert PendingEntry.from_dict(d).mail_id == "M-OLD-1"


# ---- 11. P0 driver 标记: 显式 driver 穿越状态机 ----
def test_driver_survives_state_transitions(tmp_root: Path) -> None:
    from services.mail_puller import PendingEntry, STATE_NEW, STATE_DONE
    puller = _make_puller(tmp_root)
    puller._append_pending([PendingEntry(mail_id="M-DRV-2", state=STATE_NEW,
                                         driver="email", source_ref="<abc@msg>")])
    e = puller.claim_next_new(consumer="orchestrator")
    assert e is not None and e.driver == "email" and e.source_ref == "<abc@msg>"
    assert puller.mark_state("M-DRV-2", STATE_DONE, context_id="RFQ-X") is True
    done = puller.list_by_state("DONE")[0]
    assert done.driver == "email"          # mark_state 不丢 driver
    assert done.source_ref == "<abc@msg>"


# ---- 12. 2026-09-24 邮件过滤层: 内容指纹去重 (SKIPPED/force/DUP) ----
def _write_eml(box: Path, mail_id: str, frm: str, subject: str, body: str,
               badges=("NEW", "QQ_PULLED")) -> Path:
    from email.message import EmailMessage
    msg = EmailMessage()
    msg["From"] = frm
    msg["To"] = "sales@union.local"
    msg["Subject"] = subject
    msg["Date"] = "Wed, 24 Sep 2026 10:00:00 +0800"
    msg.set_content(body)
    (box / f"{mail_id}.eml").write_bytes(bytes(msg))
    (box / f"{mail_id}.meta.json").write_text(json.dumps({
        "uid": f"uid-{mail_id}", "folder": "INBOX", "badges": list(badges),
        "source": "qq-imap", "from": frm, "subject": subject,
    }, ensure_ascii=False), encoding="utf-8")
    return box / f"{mail_id}.eml"


def test_skipped_state_is_terminal(tmp_root: Path) -> None:
    """SKIPPED 是合法终态 (过滤层用), mark_state 接受."""
    from services.mail_puller import MailPuller, PendingEntry, STATE_NEW, STATE_SKIPPED
    puller = _make_puller(tmp_root)
    puller._append_pending([PendingEntry(mail_id="M-SK-1", state=STATE_NEW)])
    assert STATE_SKIPPED == "SKIPPED"
    assert puller.mark_state("M-SK-1", STATE_SKIPPED, error="非询价: 命中 ['通知']") is True
    e = puller.list_by_state("SKIPPED")[0]
    assert e.error.startswith("非询价")


def test_force_flag_roundtrip(tmp_root: Path) -> None:
    """PendingEntry.force: 人工 reprocess 覆写过滤/去重 (向后兼容旧行缺省 0)."""
    from services.mail_puller import PendingEntry
    e = PendingEntry.from_dict({"mail_id": "M-F", "state": "NEW", "queued_at": 1.0})
    assert e.force == 0
    e2 = PendingEntry.from_dict({"mail_id": "M-F", "state": "NEW", "queued_at": 1.0, "force": 1})
    assert e2.force == 1
    assert PendingEntry.from_dict(e2.to_dict()).force == 1


def test_content_index_dedup_on_enqueue(tmp_root: Path) -> None:
    """两封同内容不同 mail_id 的 .eml → 只有首封入队, 次封 meta 打 DUP 徽标."""
    from services.mail_puller import MailPuller
    box = tmp_root / "data" / "mailbox"
    box.mkdir(parents=True)
    _write_eml(box, "qq_first", "bob@buyer.com", "RFQ 6061 bracket", "Need quote 50 pcs")
    _write_eml(box, "qq_second", "bob@buyer.com", "RFQ 6061 bracket", "Need quote 50 pcs")
    puller = _make_puller(tmp_root)
    added = puller._enqueue_pending_from_mailbox()
    assert added == 1
    idx = puller.pending_index()
    assert "qq_first" in idx and "qq_second" not in idx
    meta2 = json.loads((box / "qq_second.meta.json").read_text(encoding="utf-8"))
    assert "DUP" in meta2["badges"]
    # 内容索引落盘且含该指纹
    sig_index = json.loads((tmp_root / "data" / "mail_puller" / "content_index.json")
                           .read_text(encoding="utf-8"))
    assert len(sig_index) == 1 and "qq_first" in sig_index.values()


def test_content_index_backfill_from_disk(tmp_root: Path) -> None:
    """存量邮件 (无索引文件) → 首次入队时回填索引, 之后重投被去重."""
    from services.mail_puller import MailPuller
    box = tmp_root / "data" / "mailbox"
    box.mkdir(parents=True)
    _write_eml(box, "qq_hist", "old@buyer.com", "询价 7075", "数量 30")
    puller = _make_puller(tmp_root)
    assert puller._enqueue_pending_from_mailbox() == 1
    # 再来一封同内容新 UID → 不入队 + DUP
    _write_eml(box, "qq_hist2", "old@buyer.com", "询价 7075", "数量 30")
    assert puller._enqueue_pending_from_mailbox() == 0


def test_deleted_mail_content_reaccepted(tmp_root: Path) -> None:
    """被删除邮件的指纹 → 新副本允许入队 (删除是人工意图, 不永久拉黑内容).

    与 mail_batch delete 对齐: 删 .eml+.meta.json 并清 ledger 行 + 指纹条目。
    """
    from services.mail_puller import MailPuller
    box = tmp_root / "data" / "mailbox"
    box.mkdir(parents=True)
    _write_eml(box, "qq_gone", "x@buyer.com", "询价 A", "10 pcs")
    puller = _make_puller(tmp_root)
    assert puller._enqueue_pending_from_mailbox() == 1
    # 模拟 mail_batch delete: 删文件 + 清 ledger 行 + 清指纹 (api_server 同款动作)
    (box / "qq_gone.eml").unlink()
    (box / "qq_gone.meta.json").unlink()
    puller._write_pending([e for e in puller._read_pending() if e.mail_id != "qq_gone"])
    puller.drop_content_index("qq_gone")
    _write_eml(box, "qq_newcopy", "x@buyer.com", "询价 A", "10 pcs")
    assert puller._enqueue_pending_from_mailbox() == 1


def test_poll_once_dedup_check_blocks_redelivery(tmp_root: Path) -> None:
    """sync 级去重: 同内容换 UID 重投 → deduped=1, 不建 .eml, 服务器端标已读."""
    from services.mail_puller import MailPuller

    holder = {}

    def factory(host, port):
        msgs = [
            # 同内容两个 UID (byteswarm 场景): from/subject/text 一致
            _DupMsg("u-1"), _DupMsg("u-2"),
        ]
        holder["c"] = _MockClientWithFlag(msgs)
        return holder["c"]

    _write_gmail_settings(tmp_root, enabled=True)
    _write_credentials(tmp_root)
    puller = _make_puller(tmp_root, factory=factory)
    r = puller.poll_once()
    assert r["ok"] is True
    assert r["fetched"] == 1     # 只有第一封落盘
    assert r["deduped"] == 1     # 第二封判重
    box = tmp_root / "data" / "mailbox"
    assert len(list(box.glob("*.eml"))) == 1
    # 重投封在服务器端被标 \Seen
    assert holder["c"].flag_calls == [("u-2", ("\Seen",), True)]


class _DupMsg:
    """同内容两个 UID 的 mock 邮件 (byteswarm 翻版)."""
    def __init__(self, uid):
        self.uid = uid
        self.from_ = "verification@byteswarm.ai"
        self.subject = "FDE 实战松｜报名成功与专属登录链接"
        self.text = "欢迎报名, 请查收登录链接。"
        self.html = None
        self.to_values = ["sales@union.local"]
        self.cc_values = []
        self.date_str = "2026-09-24 10:00:00"
        self.attachments = []


class _MockClientWithFlag:
    def __init__(self, msgs):
        self._msgs = msgs
        self._logged_in = False
        self.flag_calls = []

        class F:
            def set(self, name):
                pass

        self.folder = F()

    def login(self, user, pwd):
        self._logged_in = True

    def logout(self):
        pass

    def fetch(self, limit=50, reverse=True, **kwargs):
        assert self._logged_in
        self.fetch_kwargs = kwargs
        return iter(self._msgs)

    def flag(self, uid_list, flag_set, value):
        self.flag_calls.append((uid_list, flag_set, value))


# ---- 18. 2026-09-24 追加史语义: 后行=当前态 (reprocess/retry 追加第二行) ----
def _ledger_rows(tmp_root: Path) -> List[Dict[str, Any]]:
    p = tmp_root / "data" / "mail_puller" / "pending.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_mark_state_updates_latest_line(tmp_root: Path) -> None:
    """人工 reprocess/retry 追加第二行后, mark_state 必须改尾行 — 与 pending_index
    '后行覆盖' 对齐; 改首行会让尾行卡 PROCESSING, 控制台徽标永悬 (真 bug 回归)."""
    puller = _make_puller(tmp_root)
    puller._append_pending([PendingEntry(mail_id="m-2line", state="SKIPPED", error="旧过滤")])
    puller._append_pending([PendingEntry(mail_id="m-2line", state="NEW", force=1, driver="console")])
    assert puller.mark_state("m-2line", "DONE", consumer="orchestrator") is True
    rows = _ledger_rows(tmp_root)
    assert rows[0]["state"] == "SKIPPED"   # 历史行保持原判, 不涂改
    assert rows[1]["state"] == "DONE"      # 尾行 = 当前态, 被更新
    assert puller.pending_index()["m-2line"]["state"] == "DONE"


def test_current_entry_returns_latest_line(tmp_root: Path) -> None:
    """current_entry = 最后一行: reprocess 的 force=1 在尾行, 首行是旧 SKIPPED —
    取首行会丢 force 标记, 人工重跑仍被过滤层拦回 (回归)."""
    puller = _make_puller(tmp_root)
    puller._append_pending([PendingEntry(mail_id="m-cur", state="SKIPPED")])
    puller._append_pending([PendingEntry(mail_id="m-cur", state="NEW", force=1, driver="console")])
    cur = puller.current_entry("m-cur")
    assert cur is not None and cur.state == "NEW" and cur.force == 1
    assert puller.current_entry("absent") is None


def test_status_by_state_dedupes_latest_row(tmp_root: Path) -> None:
    """不足-1: status() by_state 必须按 mail_id 取最新行. reprocess 追加尾行
    DONE 后, 首行 FAILED 不能再计入统计 — 否则队列概览与 pending_index /
    current_entry 的权威态漂移 (控制台徽标显示 FAILED 但邮件其实已转正)."""
    puller = _make_puller(tmp_root)
    puller._append_pending([PendingEntry(mail_id="m-cnt-a", state="FAILED", error="llm timeout")])
    puller._append_pending([PendingEntry(mail_id="m-cnt-a", state="DONE")])  # reprocess 追加尾行
    puller._append_pending([PendingEntry(mail_id="m-cnt-b", state="NEW")])
    p = puller.status()["pending"]
    assert p["by_state"]["FAILED"] == 0
    assert p["by_state"]["DONE"] == 1
    assert p["by_state"]["NEW"] == 1
    assert p["total"] == 2          # 2 个 mail_id, 非 3 行
    assert sum(p["by_state"].values()) == p["total"]


def test_dead_marks_imap_read(tmp_root: Path, monkeypatch) -> None:
    """重试超限 DEAD (死信) → best-effort 标 IMAP 已读 (终态即标, 用户拍板)."""
    calls: List[str] = []
    import services.gmail_imap as gim
    monkeypatch.setattr(gim, "mark_mailbox_read",
                        lambda root, mid, **kw: calls.append(mid) or {"ok": True})
    puller = _make_puller(tmp_root)
    puller._append_pending([PendingEntry(mail_id="m-dead", state="PROCESSING")])
    st = puller.fail_with_retry("m-dead", "boom", max_attempts=1)
    assert st == "DEAD"
    assert calls == ["m-dead"]


# ---- Round C: 挂死加固 — poll_once bounded watchdog (2026-09-24) ----
class _HangClient:
    """login 成功但 fetch 永久阻塞 (半开连接/对端不应的真景 mock)."""
    def __init__(self, release: threading.Event):
        self._release = release
        self._logged_in = False
        self.folder = type("F", (), {"set": lambda self, n: None})()

    def login(self, *a, **kw):
        self._logged_in = True

    def logout(self):
        pass

    def fetch(self, *a, **kw):
        self._release.wait(60)  # 挂到测试显式释放 (worker 线程杀不死, 只能放行)
        raise ConnectionError("released after test")


def test_poll_once_watchdog_bounds_hang(tmp_root: Path) -> None:
    """fetch 挂死 → poll_once 必须在 watchdog_s 内返回 ok=False/stage=watchdog,
    且记一次失败 (退避表可计数). 用测试侧 5s join 守护证明它没挂死整个调用."""
    from services.mail_puller import MailPuller
    _write_gmail_settings(tmp_root, enabled=True)
    _write_credentials(tmp_root)
    release = threading.Event()
    puller = MailPuller(root=tmp_root, interval_s=0.2, limit=10, watchdog_s=0.5,
                        mailbox_factory=lambda h, p: _HangClient(release))
    holder: Dict[str, Any] = {}

    def run():
        holder["r"] = puller.poll_once()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=5.0)
    try:
        assert not t.is_alive(), "poll_once 挂死未返回 (watchdog 未生效)"
        r = holder["r"]
        assert r["ok"] is False
        assert r["stage"] == "watchdog"
        st = puller.status()["state"]
        assert st["consecutive_failures"] == 1
        assert "watchdog" in (st["last_error"] or "").lower()
    finally:
        release.set()


def test_puller_alive_after_watchdog(tmp_root: Path) -> None:
    """watchdog 熔断单周期后 puller 对象仍可用: 换好工厂 → poll_once 成功归零.
    (线程泄漏是 Python 宿命, 但绝不能把 puller 状态机/退避计数一起带走.)"""
    from services.mail_puller import MailPuller
    _write_gmail_settings(tmp_root, enabled=True)
    _write_credentials(tmp_root)
    release = threading.Event()
    puller = MailPuller(root=tmp_root, interval_s=0.2, limit=10, watchdog_s=0.5,
                        mailbox_factory=lambda h, p: _HangClient(release))

    class GoodMsg:
        uid = "w-001"
        from_ = "ok@x.com"
        subject = "OK"
        text = "OK"
        html = None
        to_values: List[str] = []
        cc_values: List[Any] = []
        date_str = "2026-09-24"
        attachments: List[Any] = []

    class GoodClient:
        folder = type("F", (), {"set": lambda self, n: None})()
        def login(self, *a, **kw): pass
        def logout(self): pass
        def fetch(self, limit=50, reverse=True, **kwargs): return iter([GoodMsg()])
        def flag(self, *a, **kw): pass

    holder: Dict[str, Any] = {}

    def run_hang():
        holder["r1"] = puller.poll_once()

    t = threading.Thread(target=run_hang, daemon=True)
    t.start()
    t.join(timeout=5.0)
    try:
        assert not t.is_alive()
        assert holder["r1"]["ok"] is False and holder["r1"]["stage"] == "watchdog"
        # 换好工厂 → 下一周期必须成功并把失败计数归零
        puller._factory = lambda h, p: GoodClient()
        r2 = puller.poll_once()
        assert r2["ok"] is True and r2["fetched"] == 1
        st = puller.status()["state"]
        assert st["consecutive_failures"] == 0
        assert st["last_error"] is None
        assert st["last_pull_at"] is not None
    finally:
        release.set()


def test_loop_survives_watchdog_hang(tmp_root: Path) -> None:
    """_loop 遇挂死周期不能死: watchdog 熔断记账 + 退避等待, loop 线程存活
    (backoff 30s 由既有退避测试覆盖, 这里只证'挂死杀不死 loop')."""
    from services.mail_puller import MailPuller
    _write_gmail_settings(tmp_root, enabled=True)
    _write_credentials(tmp_root)
    release = threading.Event()
    puller = MailPuller(root=tmp_root, interval_s=0.2, limit=10, watchdog_s=0.3,
                        mailbox_factory=lambda h, p: _HangClient(release))
    try:
        puller.start()
        time.sleep(1.2)
        alive = puller._thread is not None and puller._thread.is_alive()
        puller.stop(timeout=3.0)
        st = puller.status()["state"]
        assert alive, "挂死周期把 loop 线程带崩了"
        assert st["consecutive_failures"] >= 1, f"watchdog 未记账: {st}"
        assert "watchdog" in (st["last_error"] or "").lower()
    finally:
        release.set()


# ---- 9. ledger 文件锁: 并发公平性 + Windows 竞争归并 ----
def test_file_lock_no_starvation_under_saturation(tmp_root: Path) -> None:
    """锁持续饱和时, 单次等锁必须有界 (≤ 等待者数 × 临界区), 不能饿死.

    根因 (探针实测 2001 次获取: 临界区 max 47ms / 等锁 max 4937ms / 34 次 >1s):
    _file_lock 是 0.05s sleep 自旋, 锁释放瞬间被后来者抢走, 排队线程整轮错过,
    反复被插队 → 尾部单次等待被拉到秒级, 撞穿调用点硬编码 5s timeout
    (S4 P2 的 6~12 次 file lock timeout 即此). 注入 20ms 临界区成本只为把锁
    压在常忙状态 (公平性与 ledger 大小无关), 判据取 0.8s: 当前实现实测 4078ms.
    """
    import os
    from services.mail_puller import STATE_DONE, STATE_PROCESSING, MailPuller, MailPullerError

    puller = MailPuller(root=tmp_root)
    n = 100
    puller._append_pending([PendingEntry(mail_id=f"MID-{i:04d}", state=STATE_PROCESSING)
                            for i in range(n)])
    orig_write = puller._write_pending

    def slow_write(entries):
        time.sleep(0.02)  # 注入临界区成本 → 锁常忙
        orig_write(entries)

    puller._write_pending = slow_write

    orig_lock = puller._file_lock
    waits: List[float] = []
    errs: List[str] = []
    rl = threading.Lock()

    def timed_lock(timeout: float = 5.0):
        @contextlib.contextmanager
        def _cm():
            t0 = time.monotonic()
            with orig_lock(timeout=timeout):
                with rl:
                    waits.append(time.monotonic() - t0)
                try:
                    yield None
                except BaseException:
                    raise
        return _cm()

    puller._file_lock = timed_lock

    def worker(idx: int) -> None:
        for i in range(40):
            mid = f"MID-{(idx * 40 + i) % n:04d}"
            try:
                puller.mark_state(mid, STATE_DONE)
            except MailPullerError as ex:
                with rl:
                    errs.append(repr(ex))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=90)
    assert not any(t.is_alive() for t in threads), "有 worker 卡在锁上未退出"
    assert waits, "一次锁都没获取到"
    worst = max(waits)
    assert worst <= 0.8, (
        f"锁饥饿: 单次等锁最坏 {worst*1000:.0f}ms (应在 8 等待者×临界区 量级 ~250ms), "
        f"超时 {len(errs)} 次: {errs[:2]}"
    )
    assert not errs, f"锁饥饿导致 {len(errs)} 次 file lock timeout: {errs[:2]}"


def test_file_lock_held_open_is_contention_not_permission_error(tmp_root: Path) -> None:
    """锁文件正被外部句柄持有时必须报 MailPullerError, 不能逃逸成 PermissionError.

    Windows 实锤 (探针 8 线程 448 次抢锁炸过 1 次): 锁文件存在且被别的句柄
    打开时, os.open(O_CREAT|O_EXCL) 抛的是 ERROR_SHARING_VIOLATION→errno 13
    PermissionError, 不是 ERROR_FILE_EXISTS→FileExistsError; 而 _file_lock 只
    捕 FileExistsError, 于是竞争被当成"权限错误"直接抛给调用方.
    """
    import os

    from services.mail_puller import MailPuller, MailPullerError
    puller = MailPuller(root=tmp_root)
    path = puller.lock_path
    path.parent.mkdir(parents=True, exist_ok=True)
    holder_fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)  # 外部持有者
    try:
        with pytest.raises(MailPullerError):
            with puller._file_lock(timeout=0.5):
                pass
    finally:
        os.close(holder_fd)
        path.unlink(missing_ok=True)
