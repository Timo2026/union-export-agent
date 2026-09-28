"""tests/test_hitl_escalation.py — G1 (v6.3.x): HITL 审批超时升级 / 备用审核人.

对照外部方案风险② ("审核人不在线 → 邮件回复延迟; 2h 未审自动通知备用审核人"):
策略单源 config/policy.yaml (hitl.timeout_hours / hitl.backup_approvers);
铁律: 升级只通知不代审 — 状态机仍须人工 approve, 备用审核人来自 policy 而非 LLM。
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from services.hitl_escalation import EscalationPolicy, check_entry, escalate_overdue
from services.mail_puller import MailPuller, PendingEntry, STATE_DONE, STATE_HITL


def _write_pending(puller: MailPuller, entries) -> None:
    puller.puller_dir.mkdir(parents=True, exist_ok=True)
    with puller.pending_path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")


# ---- 1) 策略加载 ----

def test_policy_defaults():
    pol = EscalationPolicy.from_policy({})
    assert pol.timeout_hours == 2.0
    assert pol.backup_approvers == []


def test_policy_from_yaml_values():
    pol = EscalationPolicy.from_policy(
        {"hitl": {"timeout_hours": 1.5, "backup_approvers": ["boss@x.com", " pm@y.com "]}})
    assert pol.timeout_hours == 1.5
    assert pol.backup_approvers == ["boss@x.com", "pm@y.com"]


def test_policy_bad_values_fallback():
    pol = EscalationPolicy.from_policy(
        {"hitl": {"timeout_hours": "abc", "backup_approvers": "solo@x.com"}})
    assert pol.timeout_hours == 2.0
    assert pol.backup_approvers == ["solo@x.com"]


def test_real_policy_yaml_has_g1_keys():
    from services.config import load_policy
    hitl = load_policy().get("hitl") or {}
    assert "timeout_hours" in hitl, "policy.yaml hitl 缺 timeout_hours (G1 接线)"
    assert "backup_approvers" in hitl, "policy.yaml hitl 缺 backup_approvers (G1 接线)"


# ---- 2) 超时判定 ----

def test_fresh_hitl_not_timed_out():
    now = time.time()
    e = PendingEntry(mail_id="m1", state=STATE_HITL, hitl_since=now - 60)
    d = check_entry(e, EscalationPolicy(timeout_hours=2.0), now=now)
    assert d is not None
    assert d.timed_out is False
    assert d.age_hours < 0.02


def test_overdue_hitl_timed_out():
    now = time.time()
    e = PendingEntry(mail_id="m2", state=STATE_HITL, hitl_since=now - 3 * 3600)
    d = check_entry(e, EscalationPolicy(timeout_hours=2.0, backup_approvers=["boss@x.com"]), now=now)
    assert d.timed_out is True
    assert d.age_hours == pytest.approx(3.0, abs=0.01)
    assert d.backup_approvers == ["boss@x.com"]


def test_non_hitl_entry_ignored():
    now = time.time()
    e = PendingEntry(mail_id="m3", state=STATE_DONE, queued_at=now - 10 * 3600)
    assert check_entry(e, EscalationPolicy(), now=now) is None


def test_legacy_entry_falls_back_to_queued_at():
    """旧 pending 行无 hitl_since → 回退 queued_at, 不漏升级."""
    now = time.time()
    e = PendingEntry(mail_id="m4", state=STATE_HITL, queued_at=now - 5 * 3600)
    d = check_entry(e, EscalationPolicy(timeout_hours=2.0), now=now)
    assert d.timed_out is True


# ---- 3) mark_state 接线 ----

def test_mark_state_sets_hitl_since_and_roundtrips(tmp_path):
    puller = MailPuller(root=tmp_path)
    _write_pending(puller, [PendingEntry(mail_id="m5", state="NEW")])
    assert puller.mark_state("m5", STATE_HITL) is True
    e = puller._read_pending()[0]
    assert e.hitl_since is not None
    raw = json.loads(puller.pending_path.read_text(encoding="utf-8").splitlines()[0])
    assert PendingEntry.from_dict(raw).hitl_since == e.hitl_since


# ---- 4) 升级扫描: 通知 / 去重 / 审计 / 不代审 ----

def test_escalate_overdue_notifies_once_then_dedupes(tmp_path):
    puller = MailPuller(root=tmp_path)
    now = time.time()
    _write_pending(puller, [PendingEntry(mail_id="m6", state=STATE_HITL,
                                         hitl_since=now - 3 * 3600, context_id="RFQ-1")])
    calls = []

    def notifier(kind, payload):
        calls.append((kind, payload))
        return True

    pol = EscalationPolicy(timeout_hours=2.0, backup_approvers=["boss@x.com"])
    out1 = escalate_overdue(puller, policy=pol, notifier=notifier, now=now,
                            audit_dir=tmp_path / "audit")
    assert len(out1) == 1 and out1[0].escalated is True
    assert calls and calls[0][0] == "hitl_timeout"
    assert calls[0][1]["backup_approvers"] == ["boss@x.com"]

    # 窗口内第二次 → 不重复通知 (防通知风暴)
    out2 = escalate_overdue(puller, policy=pol, notifier=notifier, now=now + 600,
                            audit_dir=tmp_path / "audit")
    assert out2 == [] and len(calls) == 1

    # 超过一个 timeout 窗口 → 再次升级
    out3 = escalate_overdue(puller, policy=pol, notifier=notifier, now=now + 3 * 3600,
                            audit_dir=tmp_path / "audit")
    assert len(out3) == 1 and len(calls) == 2


def test_escalate_overdue_writes_audit_and_never_approves(tmp_path):
    puller = MailPuller(root=tmp_path)
    now = time.time()
    _write_pending(puller, [PendingEntry(mail_id="m7", state=STATE_HITL,
                                         hitl_since=now - 4 * 3600, context_id="RFQ-2")])
    out = escalate_overdue(puller, policy=EscalationPolicy(timeout_hours=2.0),
                           notifier=lambda k, p: True, now=now,
                           audit_dir=tmp_path / "audit")
    assert len(out) == 1

    audit_file = tmp_path / "audit" / "hitl_escalations.jsonl"
    assert audit_file.exists()
    rec = json.loads(audit_file.read_text(encoding="utf-8").splitlines()[0])
    assert rec["kind"] == "hitl_timeout"
    assert rec["mail_id"] == "m7" and rec["context_id"] == "RFQ-2"

    # 铁律: 升级只通知不代审 — 状态仍是 HITL, 且记下 escalated_at
    e = puller._read_pending()[0]
    assert e.state == STATE_HITL
    assert e.escalated_at == pytest.approx(now, abs=1.0)


def test_escalate_overdue_no_notifier_still_records(tmp_path):
    puller = MailPuller(root=tmp_path)
    now = time.time()
    _write_pending(puller, [PendingEntry(mail_id="m8", state=STATE_HITL,
                                         hitl_since=now - 3 * 3600)])
    out = escalate_overdue(puller, policy=EscalationPolicy(timeout_hours=2.0),
                           notifier=None, now=now, audit_dir=tmp_path / "audit")
    assert len(out) == 1
    assert (tmp_path / "audit" / "hitl_escalations.jsonl").exists()
