"""test_mail_manual_api.py — 2026-09-24 邮件过滤层: 手动流 ledger 对账 + 人工端点单测.

覆盖 (代码核对后先写测试, TDD):
  手动流 ledger 对账 (缺陷: 人工 approve+send 后 ledger 停留 HITL):
    1) approve 成功 → 反查 mail_id (by context_id) → pending HITL→DONE
    2) send-reply 成功 → ledger DONE + mark_mailbox_read (人工发出后标已读)
    3) approve/send 时无 ledger 条目 → 不炸, 诚实 noop
  人工 reprocess 覆写 (灰区/误过滤恢复入口):
    4) POST /v1/mail/{id}/reprocess → force=1 条目 (driver=console) + 审计
    5) reprocess 未知邮件 → 404; 已在 NEW → 原位升级 force 不追加重复行
  存量重分类 (节点 inv12: ~40 封垃圾停在 HITL/NEW 的 backlog 修复):
    6) reclassify → 非询价 → SKIPPED + NON_RFQ 徽标, 不建 context
    7) reclassify → 真询价 → 不动; 终态 → 不动; dry_run → 只预览不改写
  删除清指纹:
    8) mail/batch delete → drop_content_index, 同内容可再入队 (不误判重投)
  demo_scenario 等待环:
    9) SKIPPED 也是终态 (后台 loop 抢先 claim 时等待环识别)
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from services.mail_puller import MailPuller, PendingEntry, STATE_DONE, STATE_HITL, STATE_NEW

_ROOT = Path(__file__).resolve().parent.parent

JUNK_SUBJECT = "【NVIDIA 开发者通知】您的直播日程提醒: 主题演讲即将开始"
JUNK_BODY = "尊敬的开发者, 欢迎参加本次大会。报名截止前可修改报名信息, 详见链接。"
RFQ_SUBJECT = "询价报价 c2123 工件 铝合金6061 数量 9"
RFQ_BODY = "请报价: 见图纸, 精度 0.1, 表面阳极氧化黑, 数量 9 pcs, 交期 2 周。"


# ---------- 工具 ----------
def _write_mail(root: Path, mail_id: str, *, from_: str, subject: str,
                body: str, badges: Optional[List[str]] = None) -> Path:
    box = root / "data" / "mailbox"
    box.mkdir(parents=True, exist_ok=True)
    eml = box / f"{mail_id}.eml"
    eml.write_bytes(
        (f"From: {from_}\r\nTo: sales@union-mfg.com\r\nSubject: {subject}\r\n"
         f"Date: Mon, 21 Sep 2026 10:00:00 +0800\r\n\r\n{body}\r\n").encode("utf-8"))
    (box / f"{mail_id}.meta.json").write_text(json.dumps({
        "from": from_, "subject": subject, "badges": badges or ["NEW"],
        "source": "test",
    }, ensure_ascii=False), encoding="utf-8")
    return eml


def _pending_rows(root: Path) -> List[Dict[str, Any]]:
    p = root / "data" / "mail_puller" / "pending.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _last_row(root: Path, mail_id: str) -> Optional[Dict[str, Any]]:
    rows = [r for r in _pending_rows(root) if r.get("mail_id") == mail_id]
    return rows[-1] if rows else None


def _append_entry(root: Path, mail_id: str, state: str, **kw: Any) -> None:
    MailPuller(root=root)._append_pending([PendingEntry(mail_id=mail_id, state=state, **kw)])


def _inject_context(api: Any, cid: str, **result_extra: Any) -> None:
    """把 RFQ context 塞进 _STORE (approve/send-reply 都走 _need(cid))."""
    api._STORE[cid] = {
        "inputs": {}, "customer": {},
        "result": {"state": "HITL", "quote": {"unit_price": 1.0, "final_price": 2.0},
                   "reply": {"subject": "Quotation", "body": "Dear buyer, ...",
                             "auto_send": False},
                   **result_extra},
    }


class _AlwaysSkippedIndex(dict):
    """假 pending_index: 任何 mail_id 都返回 SKIPPED (等待环注入)."""

    def get(self, key, default=None):  # noqa: D102
        return {"state": "SKIPPED", "context_id": None, "driver": "email"}


class _FakePuller:
    """demo_scenario 等待环用: enqueue no-op, 状态恒 SKIPPED."""

    def _enqueue_pending_from_mailbox(self) -> int:
        return 0

    def pending_index(self):
        return _AlwaysSkippedIndex()


# ---------- fixture ----------
@pytest.fixture()
def client(tmp_path, monkeypatch):
    from services import api_server as api

    (tmp_path / "data" / "mailbox").mkdir(parents=True, exist_ok=True)
    shutil.copy(_ROOT / "data" / "golden_scenarios.json",
                tmp_path / "data" / "golden_scenarios.json")
    monkeypatch.setattr(api, "_ROOT", tmp_path)
    monkeypatch.setattr(api, "_SUITE_MAILBOX_DIR", tmp_path / "data" / "mailbox")
    monkeypatch.setattr(api, "_mail_bg", {})
    with TestClient(api.app) as c:
        c.tmp_root = tmp_path  # type: ignore[attr-defined]
        yield c
    api._STORE.clear()


# ---- 1. approve 对账 ----
def test_approve_reconciles_ledger_to_done(client):
    """人工 approve 成功 → 反查 context_id 对应邮件 → ledger HITL→DONE.

    缺陷回归 (2026-09-24 节点实测): RFQ-20260924-3C3346 approve+send 后
    pending 仍 HITL, 控制台徽标/仪表板全部停在旧态。
    """
    _write_mail(client.tmp_root, "m_appr", from_="buyer@northwind.com",
                subject=RFQ_SUBJECT, body=RFQ_BODY)
    _append_entry(client.tmp_root, "m_appr", STATE_HITL, context_id="RFQ-APP-1")
    from services import api_server as api
    _inject_context(api, "RFQ-APP-1")
    r = client.post("/v1/rfq/RFQ-APP-1/approve")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "DONE"
    assert d.get("ledger_mail_id") == "m_appr"
    assert _last_row(client.tmp_root, "m_appr")["state"] == "DONE"
    assert _last_row(client.tmp_root, "m_appr")["consumer"] == "console-approve"


def test_approve_without_ledger_entry_still_ok(client):
    """无 pending 条目 (demo/mock 邮件) → approve 不炸, 诚实报告未对账."""
    from services import api_server as api
    _inject_context(api, "RFQ-NOLEDGER-1")
    r = client.post("/v1/rfq/RFQ-NOLEDGER-1/approve")
    assert r.status_code == 200
    assert r.json().get("ledger_mail_id") is None


# ---- 2. send-reply 对账 + 标已读 ----
def test_send_reply_reconciles_ledger_and_marks_read(client, monkeypatch):
    """人工 send-reply 成功 → ledger HITL→DONE + IMAP \Seen (发出后标已读)."""
    import services.gmail_imap as gim
    import services.reply_sender as rs

    read_calls: List[Any] = []
    monkeypatch.setattr(gim, "mark_mailbox_read",
                        lambda root, mid, **kw: read_calls.append(mid) or {"ok": True, "uid": "77"})
    sent: List[Dict[str, Any]] = []

    def _fake_send(**kw: Any) -> Dict[str, Any]:
        sent.append(kw)
        return {"ok": True, "context_id": "RFQ-SEND-1", "to": kw.get("to_addr"),
                "from_addr": "sales@union-mfg.com", "attachments": [], "audit": "x"}

    monkeypatch.setattr(rs, "send_quote_reply", _fake_send)

    _write_mail(client.tmp_root, "m_send", from_="buyer@northwind.com",
                subject=RFQ_SUBJECT, body=RFQ_BODY)
    _append_entry(client.tmp_root, "m_send", STATE_HITL, context_id="RFQ-SEND-1")
    from services import api_server as api
    _inject_context(api, "RFQ-SEND-1", human_approved={"approver": "human", "ts": 1.0})

    r = client.post("/v1/rfq/RFQ-SEND-1/send-reply", data={"to_addr": "buyer@northwind.com"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True and sent
    assert d["ledger"]["mail_id"] == "m_send"
    assert d["ledger"]["reconciled"] is True
    assert d["imap_read"]["ok"] is True
    assert read_calls == ["m_send"]
    row = _last_row(client.tmp_root, "m_send")
    assert row["state"] == "DONE" and row["consumer"] == "console-send"
    # 人工流审计留痕
    audit = (client.tmp_root / "data" / "skill_audit.jsonl").read_text(encoding="utf-8")
    assert "imap_marked_read_manual" in audit


def test_send_reply_without_ledger_entry_does_not_block_send(client, monkeypatch):
    """无 ledger 条目 → 照常发送 (bookkeeping 失败不把成功发送变成错误)."""
    import services.reply_sender as rs
    monkeypatch.setattr(rs, "send_quote_reply",
                        lambda **kw: {"ok": True, "context_id": "RFQ-SEND-2",
                                      "to": kw.get("to_addr"), "attachments": []})
    from services import api_server as api
    _inject_context(api, "RFQ-SEND-2", human_approved={"approver": "human", "ts": 1.0})
    r = client.post("/v1/rfq/RFQ-SEND-2/send-reply", data={"to_addr": "buyer@x.com"})
    assert r.status_code == 200
    assert r.json()["ledger"]["reconciled"] is False


# ---- 3. reprocess ----
def test_reprocess_appends_force_entry(client):
    """reprocess → force=1 NEW 条目 (driver=console) + 审计 — 绕过分类/去重."""
    _write_mail(client.tmp_root, "m_rp", from_="someone@buyer.com", subject="平台", body="")
    r = client.post("/v1/mail/m_rp/reprocess")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    row = _last_row(client.tmp_root, "m_rp")
    assert row["state"] == "NEW"
    assert row["force"] == 1
    assert row["driver"] == "console"
    assert row["source_ref"] == "manual-reprocess"
    audit = (client.tmp_root / "data" / "skill_audit.jsonl").read_text(encoding="utf-8")
    assert "mail_force_reprocess" in audit


def test_reprocess_unknown_mail_404(client):
    r = client.post("/v1/mail/no_such_mail/reprocess")
    assert r.status_code == 404


def test_reprocess_upgrades_new_entry_in_place(client):
    """已在 NEW 的邮件 reprocess → 原位升级 force=1, 不追加重复行 (防幽灵 line)."""
    _write_mail(client.tmp_root, "m_rp2", from_="a@b.com", subject=RFQ_SUBJECT, body=RFQ_BODY)
    _append_entry(client.tmp_root, "m_rp2", STATE_NEW)
    r = client.post("/v1/mail/m_rp2/reprocess")
    assert r.status_code == 200
    rows = [r_ for r_ in _pending_rows(client.tmp_root) if r_["mail_id"] == "m_rp2"]
    assert len(rows) == 1
    assert rows[0]["force"] == 1
    assert rows[0]["driver"] == "console"


# ---- 4. reclassify 存量重分类 ----
def test_reclassify_marks_non_rfq_skipped(client):
    """存量垃圾邮件 (过滤层上线前入队) → SKIPPED + NON_RFQ 徽标, 不建 context."""
    _write_mail(client.tmp_root, "m_junk", from_="notify@nvidia.cn",
                subject=JUNK_SUBJECT, body=JUNK_BODY)
    _append_entry(client.tmp_root, "m_junk", STATE_NEW)
    r = client.post("/v1/mail/maintenance/reclassify")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True and d["dry_run"] is False
    assert d["skipped"] == 1 and d["kept"] == 0
    row = _last_row(client.tmp_root, "m_junk")
    assert row["state"] == "SKIPPED" and row["consumer"] == "reclassify"
    meta = json.loads((client.tmp_root / "data" / "mailbox" / "m_junk.meta.json")
                      .read_text(encoding="utf-8"))
    assert "NON_RFQ" in meta["badges"]
    assert meta["filter"]["kind"] == "skip"
    # 不建任何 RFQ context
    ctx_dir = client.tmp_root / "data" / "contexts"
    assert not ctx_dir.exists() or not any(ctx_dir.glob("*.json"))
    audit = (client.tmp_root / "data" / "skill_audit.jsonl").read_text(encoding="utf-8")
    assert "mail_reclassify" in audit


def test_reclassify_keeps_genuine_rfq(client):
    """真询价 (哪怕是 HITL) → reclassify 不动, 等人的还继续等."""
    _write_mail(client.tmp_root, "m_rfq", from_="buyer@northwind.com",
                subject=RFQ_SUBJECT, body=RFQ_BODY)
    _append_entry(client.tmp_root, "m_rfq", STATE_HITL, context_id="RFQ-RC-1")
    r = client.post("/v1/mail/maintenance/reclassify")
    d = r.json()
    assert d["kept"] == 1 and d["skipped"] == 0
    assert _last_row(client.tmp_root, "m_rfq")["state"] == "HITL"
    meta = json.loads((client.tmp_root / "data" / "mailbox" / "m_rfq.meta.json")
                      .read_text(encoding="utf-8"))
    assert "filter" not in meta  # 未改写 meta
    assert "NON_RFQ" not in meta["badges"]


def test_reclassify_ignores_terminal_states(client):
    """已有裁决 (DONE/BLOCKED/...) → 不翻案."""
    _write_mail(client.tmp_root, "m_done", from_="notify@nvidia.cn",
                subject=JUNK_SUBJECT, body=JUNK_BODY)
    _append_entry(client.tmp_root, "m_done", STATE_DONE)
    r = client.post("/v1/mail/maintenance/reclassify")
    d = r.json()
    assert d["skipped"] == 0 and d["kept"] == 0
    assert _last_row(client.tmp_root, "m_done")["state"] == "DONE"


def test_reclassify_dry_run_previews_only(client):
    """dry_run → 只列预览, ledger/meta 一律不改写."""
    _write_mail(client.tmp_root, "m_junk2", from_="notify@nvidia.cn",
                subject=JUNK_SUBJECT, body=JUNK_BODY)
    _append_entry(client.tmp_root, "m_junk2", STATE_NEW)
    r = client.post("/v1/mail/maintenance/reclassify", params={"dry_run": True})
    d = r.json()
    assert d["dry_run"] is True and d["skipped"] == 1
    assert _last_row(client.tmp_root, "m_junk2")["state"] == "NEW"
    meta = json.loads((client.tmp_root / "data" / "mailbox" / "m_junk2.meta.json")
                      .read_text(encoding="utf-8"))
    assert "filter" not in meta
    assert not (client.tmp_root / "data" / "skill_audit.jsonl").exists() or \
        "mail_reclassify" not in (client.tmp_root / "data" / "skill_audit.jsonl").read_text(encoding="utf-8")


# ---- 5. delete 清指纹 ----
def test_mail_batch_delete_clears_content_index(client):
    """delete → 清指纹索引: 同内容再投递是新邮件, 不被去重误吞."""
    body = "Unique probe body 0d3f9a for dedup regression"
    eml = _write_mail(client.tmp_root, "m_del", from_="dup@buyer.com",
                      subject="Re: quote", body=body)
    _append_entry(client.tmp_root, "m_del", STATE_NEW)
    puller = MailPuller(root=client.tmp_root)
    from services.mail_puller import _eml_signature
    sig = _eml_signature(eml)
    puller._refresh_content_index_locked()
    assert puller.dedup_check(sig, "dup@buyer.com", "Re: quote") is True

    r = client.post("/v1/mail/batch", json={"ids": ["m_del"], "action": "delete"})
    assert r.status_code == 200
    assert r.json()["done"] == ["m_del"]
    assert not eml.exists()
    assert _pending_rows(client.tmp_root) == []
    assert puller.dedup_check(sig, "dup@buyer.com", "Re: quote") is False


# ---- 6. demo_scenario 等待环识别 SKIPPED ----
def test_demo_scenario_waits_skipped_terminal(client, monkeypatch):
    """后台 loop 抢先 claim 且判定 SKIPPED → 等待环识别为终态 (不超时谎报)."""
    from services import api_server as api
    monkeypatch.setitem(api._mail_bg, "puller", _FakePuller())
    r = client.post("/v1/demo/scenario/S1")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "SKIPPED"
    assert d["ok"] is True  # 跳过是确定性裁决, 不是失败
