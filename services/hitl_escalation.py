"""services.hitl_escalation — G1 (v6.3.x): HITL 审批超时升级 / 备用审核人.

对照外部方案风险② ("审核人不在线 → 邮件回复延迟; 2h 未审自动通知备用审核人"):
策略单源在 config/policy.yaml (hitl.timeout_hours / hitl.backup_approvers), 不交给 LLM。

铁律:
  - 升级只通知, 永不代审 — 状态机仍须人工 approve (POST /v1/rfq/{cid}/approve);
  - 备用审核人名单来自 policy 配置, 不来自模型生成;
  - 去重窗口 = 一个 timeout, 防通知风暴; 旧 pending 行无 hitl_since 时回退 queued_at。
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .mail_puller import MailPuller, PendingEntry, STATE_HITL

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_HOURS = 2.0

NotifierFn = Callable[[str, Dict[str, Any]], bool]


@dataclass
class EscalationPolicy:
    """G1 策略 (policy.yaml hitl 节)."""

    timeout_hours: float = DEFAULT_TIMEOUT_HOURS
    backup_approvers: List[str] = field(default_factory=list)

    @classmethod
    def from_policy(cls, policy: Optional[Dict[str, Any]]) -> "EscalationPolicy":
        hitl = (policy or {}).get("hitl") or {}
        timeout = hitl.get("timeout_hours", DEFAULT_TIMEOUT_HOURS)
        try:
            timeout = float(timeout)
        except (TypeError, ValueError):
            log.warning("[hitl-escalation] bad timeout_hours %r → default %s",
                        timeout, DEFAULT_TIMEOUT_HOURS)
            timeout = DEFAULT_TIMEOUT_HOURS
        approvers = hitl.get("backup_approvers") or []
        if isinstance(approvers, str):
            approvers = [approvers]
        approvers = [str(a).strip() for a in approvers if str(a).strip()]
        return cls(timeout_hours=timeout, backup_approvers=approvers)


@dataclass
class EscalationDecision:
    """单条 HITL 条目的升级判定."""

    mail_id: str
    context_id: Optional[str]
    age_hours: float
    timeout_hours: float
    timed_out: bool
    backup_approvers: List[str] = field(default_factory=list)
    escalated: bool = False  # 本次是否实际发出升级 (去重命中则为 False)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mail_id": self.mail_id,
            "context_id": self.context_id,
            "age_hours": self.age_hours,
            "timeout_hours": self.timeout_hours,
            "timed_out": self.timed_out,
            "backup_approvers": self.backup_approvers,
            "escalated": self.escalated,
            "reason": self.reason,
        }


def _waiting_since(entry: PendingEntry) -> float:
    """HITL 等待起点: hitl_since → started_at → queued_at (旧行向后兼容)."""
    return entry.hitl_since or entry.started_at or entry.queued_at


def check_entry(entry: PendingEntry, policy: EscalationPolicy,
                now: Optional[float] = None) -> Optional[EscalationDecision]:
    """判定单条 pending 条目是否 HITL 超时. 非 HITL 条目返 None."""
    if entry.state != STATE_HITL:
        return None
    now = time.time() if now is None else now
    age_hours = max(0.0, (now - _waiting_since(entry)) / 3600.0)
    timed_out = age_hours >= policy.timeout_hours
    return EscalationDecision(
        mail_id=entry.mail_id,
        context_id=entry.context_id,
        age_hours=round(age_hours, 3),
        timeout_hours=policy.timeout_hours,
        timed_out=timed_out,
        backup_approvers=list(policy.backup_approvers),
        reason="hitl_overdue" if timed_out else "hitl_within_timeout",
    )


def _already_escalated_recently(entry: PendingEntry, now: float, policy: EscalationPolicy) -> bool:
    last = getattr(entry, "escalated_at", None)
    if not last:
        return False
    return (now - last) < policy.timeout_hours * 3600.0


def _append_audit(audit_dir: Path, payload: Dict[str, Any]) -> None:
    audit_dir.mkdir(parents=True, exist_ok=True)
    path = audit_dir / "hitl_escalations.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def escalate_overdue(
    puller: MailPuller,
    policy: Optional[EscalationPolicy] = None,
    notifier: Optional[NotifierFn] = None,
    now: Optional[float] = None,
    audit_dir: Optional[Path] = None,
) -> List[EscalationDecision]:
    """扫 pending.jsonl 中 HITL 条目, 对超时者: 通知 + 落审计 + 标记 escalated_at.

    返回本次实际发出升级的 decision 列表 (escalated=True)。
    去重: 同一条目一个 timeout 窗口内只升级一次; notifier=None 时仅记录审计。
    """
    policy = policy or EscalationPolicy()
    now = time.time() if now is None else now
    escalated: List[EscalationDecision] = []

    for entry in puller._read_pending():
        decision = check_entry(entry, policy, now=now)
        if decision is None or not decision.timed_out:
            continue
        if _already_escalated_recently(entry, now, policy):
            continue

        payload: Dict[str, Any] = {
            "kind": "hitl_timeout",
            "mail_id": entry.mail_id,
            "context_id": entry.context_id,
            "driver": getattr(entry, "driver", ""),
            "age_hours": decision.age_hours,
            "timeout_hours": decision.timeout_hours,
            "backup_approvers": decision.backup_approvers,
            "action_required": "approve_or_reject",
            "draft_only": True,
            "ts": now,
        }

        notified = False
        if notifier is not None:
            try:
                notified = bool(notifier("hitl_timeout", payload))
            except Exception as e:  # 通知失败不阻塞扫描 (铁律: 通知失败不阻塞主链)
                log.exception("[hitl-escalation] notifier failed for %s: %r", entry.mail_id, e)
        payload["notified"] = notified

        if audit_dir is not None:
            try:
                _append_audit(audit_dir, payload)
            except Exception as e:
                log.exception("[hitl-escalation] audit append failed: %r", e)

        # 标记去重窗口 (状态不变: 升级不代审)
        try:
            puller.mark_state(entry.mail_id, STATE_HITL, escalated_at=now)
        except Exception as e:
            log.exception("[hitl-escalation] mark_state failed for %s: %r", entry.mail_id, e)

        decision.escalated = True
        escalated.append(decision)

    return escalated
