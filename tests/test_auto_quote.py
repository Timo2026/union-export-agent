"""tests/test_auto_quote.py — v2.5.0 自动报价外发八道闸 (PASS → 真报价单).

对齐 TIMO 2026-09-26 "完成订单自动报价"。
实现: services/mail_orchestrator._try_auto_quote。
铁律①不变: cat_controller 草稿层仍 draft_only (黄金回归/openshell 断言不碰),
发送决策与八道闸全在 orchestrator — 与 _try_auto_clarify 同构。

本文件只验闸门行为, 不做真实 SMTP 外发 (send_quote_reply 一律 monkeypatch)。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from services.mail_puller import MailPuller, PendingEntry, STATE_NEW
from services.mail_orchestrator import MailOrchestrator

# ---------- 工具 ----------

_POLICY = """
quote_gate:
  enabled: true
  blocking_fields: [material, quantity, dimensions]
  defaultable:
    surface_finish: "无"
    tolerance: IT8
  auto_clarify_enabled: true
  auto_clarify_cooldown_hours: 24
  auto_quote_send_enabled: true
auto_quote_threshold:
  features_count_max: 10
  process_route_max: 10
hitl:
  auto_send_allowed_only_when: [no_dfm_hard_conflict, margin_above_floor]
margin:
  floor_pct: 15.0
  review_below_pct: 20.0
"""


def _write_eml(tmp_root: Path, mail_id: str, *, from_: str = "Alice <alice@northwind.com>",
               subject: str = "RFQ 6061 brackets", body: str = "Need quote 50 pcs 6061") -> None:
    d = tmp_root / "data" / "mailbox"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{mail_id}.eml").write_bytes(
        f"From: {from_}\r\nTo: sales@union-mfg.com\r\nSubject: {subject}\r\n"
        f"Date: Mon, 19 Sep 2026 10:00:00 +0800\r\n\r\n{body}\r\n".encode("utf-8"))
    (d / f"{mail_id}.meta.json").write_text(json.dumps(
        {"from": from_, "subject": subject, "received_at": time.time()}), encoding="utf-8")


def _write_policy(tmp_root: Path, text: str = _POLICY) -> None:
    cfg = tmp_root / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "policy.yaml").write_text(text, encoding="utf-8")


class MockCAT:
    """与 tests/test_mail_orchestrator.py 同形: 返固定 verdict。"""

    def __init__(self, verdict: str = "PASS", context_id: str = "RFQ-MOCK-001"):
        self.verdict = verdict
        self.context_id = context_id
        self.call_count = 0

    def run(self, email_text: str, customer: Optional[Dict[str, Any]] = None,
            **kw: Any) -> Dict[str, Any]:
        self.call_count += 1
        return {"state": self.verdict, "context_id": self.context_id,
                "verification_status": self.verdict,
                "reasons": [] if self.verdict == "PASS" else ["mock reason"]}


def _write_ctx(tmp_root: Path, cid: str, *, status: str = "PASS",
               unit: Any = 222.8, total: Any = 9413.3,
               body: Optional[str] = None, guard_pass: bool = True,
               feats: Any = None, attachments: Optional[list] = None,
               process: str = "三轴CNC") -> Dict[str, Any]:
    """落盘一个 context (真 CAT 的持久化形态)。"""
    ctx = {
        "context_id": cid,
        "rfq": {"material": "6061", "quantity": 50},
        "geometry": {"features_count": feats} if feats is not None else {},
        "commercial": {"quote": {"unit_price": unit, "final_price": total,
                                 "currency": "CNY", "process": process}},
        "decision": {
            "status": status,
            "reply": {
                "body": body if body is not None else
                "Dear Alice,\n\nUnit price: CNY 222.8 | Total: CNY 9413.3 | Lead time: 5 days.\n"
                "(Estimate produced by our deterministic engine [live:/api/quote].)\n\n"
                "Best regards,\ntimo.cao",
                "subject": f"Quotation {cid}",
                "mode": "draft_only",
                "auto_send": False,
                "attachments": attachments if attachments is not None else
                [{"kind": "quote_pdf", "path": "/tmp/fake.pdf"}],
                "guardrail_output": {"pass": guard_pass, "flags": []},
            },
        },
    }
    p = tmp_root / "data" / "contexts" / f"{cid}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(ctx, ensure_ascii=False, indent=2), encoding="utf-8")
    return ctx


def _make(tmp_root: Path, cat: Any) -> Any:
    puller = MailPuller(root=tmp_root, interval_s=0.5, limit=10, mailbox_factory=None)
    return MailOrchestrator(root=tmp_root, puller=puller, cat=cat), puller


def _read_audit(tmp_root: Path) -> list:
    p = tmp_root / "data" / "skill_audit.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _events(tmp_root: Path, name: str) -> list:
    return [l for l in _read_audit(tmp_root) if l.get("event") == name]


def _fake_sender(recorder: list, *, raise_exc: Optional[Exception] = None):
    def fake(**kw):
        if raise_exc:
            raise raise_exc
        recorder.append(kw)
        return {"ok": True, "attachments": ["quote-fake.pdf"],
                "from_addr": "sales@union-mfg.com"}
    return fake


# ---------- 闸 1: 开关 ----------
def test_flag_off_never_sends(tmp_root: Path, monkeypatch) -> None:
    _write_policy(tmp_root, _POLICY.replace("auto_quote_send_enabled: true",
                                            "auto_quote_send_enabled: false"))
    _write_eml(tmp_root, "M-1")
    _write_ctx(tmp_root, "RFQ-OFF-1")
    sent: list = []
    monkeypatch.setattr("services.reply_sender.send_quote_reply", _fake_sender(sent))
    orch, puller = _make(tmp_root, MockCAT("PASS", "RFQ-OFF-1"))
    puller._append_pending([PendingEntry(mail_id="M-1", state=STATE_NEW)])
    r = orch.run_pipeline("M-1")
    assert r.state == "DONE" and r.quoted is False
    assert sent == []                       # 逃生门: 不开就一封都不发
    assert _events(tmp_root, "auto_quote_sent") == []


# ---------- 闸 2: 只走 PASS ----------
@pytest.mark.parametrize("status", ["HITL", "CLARIFY", "BLOCKED"])
def test_non_pass_status_never_sends(tmp_root: Path, monkeypatch, status: str) -> None:
    _write_policy(tmp_root)
    _write_eml(tmp_root, "M-2")
    _write_ctx(tmp_root, f"RFQ-{status}-1", status=status)
    sent: list = []
    monkeypatch.setattr("services.reply_sender.send_quote_reply", _fake_sender(sent))
    orch, puller = _make(tmp_root, MockCAT(status, f"RFQ-{status}-1"))
    puller._append_pending([PendingEntry(mail_id="M-2", state=STATE_NEW)])
    r = orch.run_pipeline("M-2")
    assert r.quoted is False
    assert sent == []
    assert _events(tmp_root, "auto_quote_sent") == []


# ---------- 闸 3: 报价事实完备 ----------
@pytest.mark.parametrize("kw", [{"unit": None}, {"unit": 0}, {"total": None}])
def test_incomplete_quote_never_sends(tmp_root: Path, monkeypatch, kw: Dict[str, Any]) -> None:
    _write_policy(tmp_root); _write_eml(tmp_root, "M-3")
    _write_ctx(tmp_root, "RFQ-INC-1", **kw)
    sent: list = []
    monkeypatch.setattr("services.reply_sender.send_quote_reply", _fake_sender(sent))
    orch, puller = _make(tmp_root, MockCAT("PASS", "RFQ-INC-1"))
    puller._append_pending([PendingEntry(mail_id="M-3", state=STATE_NEW)])
    r = orch.run_pipeline("M-3")
    assert r.quoted is False and sent == []
    sk = _events(tmp_root, "auto_quote_skipped")
    assert sk and sk[-1]["payload"]["reason"] == "incomplete_quote"


# ---------- 闸 4: 输出护栏 ----------
def test_guardrail_fail_never_sends(tmp_root: Path, monkeypatch) -> None:
    _write_policy(tmp_root); _write_eml(tmp_root, "M-4")
    _write_ctx(tmp_root, "RFQ-G-1", guard_pass=False)
    sent: list = []
    monkeypatch.setattr("services.reply_sender.send_quote_reply", _fake_sender(sent))
    orch, puller = _make(tmp_root, MockCAT("PASS", "RFQ-G-1"))
    puller._append_pending([PendingEntry(mail_id="M-4", state=STATE_NEW)])
    r = orch.run_pipeline("M-4")
    assert r.quoted is False and sent == []
    sk = _events(tmp_root, "auto_quote_skipped")
    assert sk and sk[-1]["payload"]["reason"] == "guardrail_output_fail"


# ---------- 闸 5: 价格一致性 (LLM 改写数字 → 拒发) ----------
def test_price_not_in_body_is_rejected(tmp_root: Path, monkeypatch) -> None:
    _write_policy(tmp_root); _write_eml(tmp_root, "M-5")
    # 正文里的 unit_price 被改成 999.9 / final 被抹掉 → 与商业事实不符
    _write_ctx(tmp_root, "RFQ-P-1",
               body="Dear Alice,\n\nUnit price: CNY 999.9 only. Best regards,\ntimo.cao")
    sent: list = []
    monkeypatch.setattr("services.reply_sender.send_quote_reply", _fake_sender(sent))
    orch, puller = _make(tmp_root, MockCAT("PASS", "RFQ-P-1"))
    puller._append_pending([PendingEntry(mail_id="M-5", state=STATE_NEW)])
    r = orch.run_pipeline("M-5")
    assert r.quoted is False and sent == []
    rej = _events(tmp_root, "auto_quote_rejected")
    assert rej and rej[-1]["payload"]["reason"] == "price_not_in_body"


def test_price_formatted_variants_accepted(tmp_root: Path, monkeypatch) -> None:
    """千分位/两位小数形态也算一致 (汇率换算/LLM 格式化不改数值)。"""
    _write_policy(tmp_root); _write_eml(tmp_root, "M-5b")
    _write_ctx(tmp_root, "RFQ-P-2", unit=41798.57, total=41798.57,
               body="Dear Alice,\n\nUnit price: CNY 41,798.57. Best regards,\ntimo.cao")
    sent: list = []
    monkeypatch.setattr("services.reply_sender.send_quote_reply", _fake_sender(sent))
    orch, puller = _make(tmp_root, MockCAT("PASS", "RFQ-P-2"))
    puller._append_pending([PendingEntry(mail_id="M-5b", state=STATE_NEW)])
    r = orch.run_pipeline("M-5b")
    assert r.quoted is True and len(sent) == 1


# ---------- 闸 6: 复杂度阈值 ----------
def test_threshold_blocks_complex_part(tmp_root: Path, monkeypatch) -> None:
    _write_policy(tmp_root); _write_eml(tmp_root, "M-6")
    _write_ctx(tmp_root, "RFQ-T-1", feats=10)     # 严格小于才 AUTO: 10<10 False
    sent: list = []
    monkeypatch.setattr("services.reply_sender.send_quote_reply", _fake_sender(sent))
    orch, puller = _make(tmp_root, MockCAT("PASS", "RFQ-T-1"))
    puller._append_pending([PendingEntry(mail_id="M-6", state=STATE_NEW)])
    r = orch.run_pipeline("M-6")
    assert r.quoted is False and sent == []
    sk = _events(tmp_root, "auto_quote_skipped")
    assert sk and sk[-1]["payload"]["reason"] == "auto_quote_threshold"


# ---------- 闸 7: 自环防御 ----------
def test_self_send_guard_blocks_own_address(tmp_root: Path, monkeypatch) -> None:
    """发给自己账号的信会被 puller 拉回 → 形成 CLARIFY→报价 环, 必须拦。"""
    from services.credentials import save_credentials
    save_credentials("qq", "tester@qq.com", "testpw")
    _write_policy(tmp_root)
    _write_eml(tmp_root, "M-7", from_="tester@qq.com")
    _write_ctx(tmp_root, "RFQ-S-1")
    sent: list = []
    monkeypatch.setattr("services.reply_sender.send_quote_reply", _fake_sender(sent))
    orch, puller = _make(tmp_root, MockCAT("PASS", "RFQ-S-1"))
    puller._append_pending([PendingEntry(mail_id="M-7", state=STATE_NEW)])
    r = orch.run_pipeline("M-7")
    assert r.quoted is False and sent == []
    sk = _events(tmp_root, "auto_quote_skipped")
    assert sk and sk[-1]["payload"]["reason"] == "self_send_guard"


# ---------- 闸 8: 幂等 ----------
def test_same_context_sent_only_once(tmp_root: Path, monkeypatch) -> None:
    _write_policy(tmp_root)
    _write_ctx(tmp_root, "RFQ-IDEM-1")
    sent: list = []
    monkeypatch.setattr("services.reply_sender.send_quote_reply", _fake_sender(sent))
    # 两封不同邮件指向同一 context (重复投递/人工 reprocess 场景)
    _write_eml(tmp_root, "M-8a"); _write_eml(tmp_root, "M-8b")
    orch, puller = _make(tmp_root, MockCAT("PASS", "RFQ-IDEM-1"))
    puller._append_pending([PendingEntry(mail_id="M-8a", state=STATE_NEW)])
    r1 = orch.run_pipeline("M-8a")
    puller._append_pending([PendingEntry(mail_id="M-8b", state=STATE_NEW, force=1)])
    r2 = orch.run_pipeline("M-8b")
    assert r1.quoted is True and r2.quoted is False
    assert len(sent) == 1                     # 只外发一次
    assert [e["payload"]["reason"] for e in _events(tmp_root, "auto_quote_skipped")][-1] \
        == "already_sent"


# ---------- 主路径: 八闸全过 → 真发 + 审计 ----------
def test_all_gates_pass_sends_quote(tmp_root: Path, monkeypatch) -> None:
    _write_policy(tmp_root); _write_eml(tmp_root, "M-OK")
    ctx = _write_ctx(tmp_root, "RFQ-OK-1")
    sent: list = []
    monkeypatch.setattr("services.reply_sender.send_quote_reply", _fake_sender(sent))
    orch, puller = _make(tmp_root, MockCAT("PASS", "RFQ-OK-1"))
    puller._append_pending([PendingEntry(mail_id="M-OK", state=STATE_NEW)])
    r = orch.run_pipeline("M-OK")
    assert r.state == "DONE" and r.quoted is True
    assert len(sent) == 1
    kw = sent[0]
    assert kw["cid"] == "RFQ-OK-1"
    assert kw["to_addr"] == "alice@northwind.com"
    assert kw["quote"]["unit_price"] == 222.8          # 商业事实原样透传
    assert kw["attachments"] == ctx["decision"]["reply"]["attachments"]
    assert kw["approver"] == "l3-auto-quote"
    assert kw["subject"] == "Quotation RFQ-OK-1"
    ev = _events(tmp_root, "auto_quote_sent")
    assert ev and ev[-1]["payload"]["unit_price"] == 222.8
    assert ev[-1]["payload"]["final_price"] == 9413.3
    # pipeline_done 记 quoted=True (端到端可观测)
    done = [l for l in _read_audit(tmp_root) if l.get("event") == "pipeline_done"]
    assert done and done[-1]["payload"]["quoted"] is True


def test_sender_failure_does_not_break_pipeline(tmp_root: Path, monkeypatch) -> None:
    _write_policy(tmp_root); _write_eml(tmp_root, "M-ERR")
    _write_ctx(tmp_root, "RFQ-ERR-1")
    monkeypatch.setattr("services.reply_sender.send_quote_reply",
                        _fake_sender([], raise_exc=RuntimeError("smtp down")))
    orch, puller = _make(tmp_root, MockCAT("PASS", "RFQ-ERR-1"))
    puller._append_pending([PendingEntry(mail_id="M-ERR", state=STATE_NEW)])
    r = orch.run_pipeline("M-ERR")
    assert r.ok is True and r.state == "DONE" and r.quoted is False   # 主链不断
    assert _events(tmp_root, "auto_quote_failed")
