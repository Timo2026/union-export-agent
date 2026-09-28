"""gen_fusion_evidence.py — v6.3.1 融合增量验收证据生成 (G1/G2).

用法:
    python scripts/gen_fusion_evidence.py            # 离线内核 (byte-identical)
    python scripts/gen_fusion_evidence.py --online   # 在线优先 :7862, 离线兜底

产出 (data/fusion_evidence/):
  g1_escalation_sample.json   — HITL 超时升级: 策略值 + 通知载荷 + 审计行 + 升级后状态 (仍 HITL, 绝不代审) + 去重证明
  g2_quote_pdf_sample.json    — 报价 PDF: 真实离线引擎报价 + content_sha256 + pdf_sha256 + 附件条目
  g2_artifacts/{cid}/quote-{cid}-{sha8}.pdf — 报价单 PDF 本体

铁律:
  - G1 升级只通知不代审; 策略来自 config/policy.yaml, 不经 LLM;
  - G2 PDF 只反映确定性引擎产出; content_sha256 锁报价事实, 不锁 PDF 字节。
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bootstrap import build_controller                                    # noqa: E402
from services.config import load_policy, load_settings                    # noqa: E402
from services.hitl_escalation import EscalationPolicy, escalate_overdue   # noqa: E402
from services.intake import extract_rfq                                   # noqa: E402
from services.mail_puller import MailPuller, PendingEntry, STATE_HITL     # noqa: E402
from services.quote_pdf import attach_quote_pdf, render_quote_pdf         # noqa: E402

_EV = _ROOT / "data" / "fusion_evidence"
_SCEN = json.loads((_ROOT / "data" / "golden_scenarios.json").read_text(encoding="utf-8"))["scenarios"]


def _rel(p) -> str:
    """证据只存仓库相对路径 (posix), 不带本机绝对路径/用户名。"""
    try:
        return Path(p).resolve().relative_to(_ROOT).as_posix()
    except ValueError:
        return Path(p).name


def gen_g1(evidence_dir: Path) -> dict:
    """G1: 构造一条超时 4h 的 HITL pending, 跑真实策略升级扫描, 落证据。"""
    puller = MailPuller(root=evidence_dir / "g1_workspace")
    now = time.time()
    entry = PendingEntry(mail_id="evid_mail_001", state=STATE_HITL,
                         hitl_since=now - 4 * 3600,
                         context_id="RFQ-20260921-EVID1", driver="email")
    puller.puller_dir.mkdir(parents=True, exist_ok=True)
    with puller.pending_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    policy = EscalationPolicy.from_policy(load_policy(_ROOT))
    notifications: list = []

    def notifier(kind, payload):
        notifications.append({"kind": kind, "payload": payload})
        return True

    audit_dir = evidence_dir / "g1_workspace" / "audit"
    out1 = escalate_overdue(puller, policy=policy, notifier=notifier, now=now,
                            audit_dir=audit_dir)
    # 窗口内第二次 → 去重 (防通知风暴)
    out2 = escalate_overdue(puller, policy=policy, notifier=notifier, now=now + 600,
                            audit_dir=audit_dir)

    after = puller._read_pending()[0]
    audit_lines = [json.loads(x) for x in
                   (audit_dir / "hitl_escalations.jsonl").read_text(encoding="utf-8").splitlines()
                   if x.strip()]
    sample = {
        "feature": "G1 HITL 审批超时升级 / 备用审核人 (v6.3.1)",
        "policy_source": "config/policy.yaml (hitl 节)",
        "policy": {"timeout_hours": policy.timeout_hours,
                   "backup_approvers": policy.backup_approvers},
        "entry_before": entry.to_dict(),
        "first_scan": [d.to_dict() for d in out1],
        "notifications": notifications,
        "audit_records": audit_lines,
        "dedup_second_scan_within_window": [d.to_dict() for d in out2],
        "entry_after": after.to_dict(),
        "iron_rule": "升级只通知不代审 — 状态仍为 HITL, 审批仍须人工 POST /v1/rfq/{cid}/approve",
    }
    (evidence_dir / "g1_escalation_sample.json").write_text(
        json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
    # 中间 workspace (pending.jsonl) 不入证据; before/after/audit 已落 JSON
    import shutil
    shutil.rmtree(evidence_dir / "g1_workspace", ignore_errors=True)
    return sample


def gen_g2(evidence_dir: Path, offline: bool) -> dict:
    """G2: 跑真实黄金链场景 (离线内核), 用真实引擎报价渲染 PDF, 落证据。"""
    settings = load_settings(_ROOT)
    if offline:
        settings["timo"]["base_url"] = "http://127.0.0.1:59999"
    ctrl = build_controller(settings_override=settings)

    sc = next(s for s in _SCEN if s["id"] == "S1")  # DONE/PASS 场景, 有真实报价
    r = ctrl.run(email_text=sc["email"], customer=sc.get("customer"))
    rfq = extract_rfq(sc["email"], sc.get("customer"))
    quote = r["quote"]
    cid = r["context_id"]

    art_dir = evidence_dir / "g2_artifacts"
    rendered = render_quote_pdf(quote, cid, out_dir=art_dir,
                                customer=sc.get("customer") or {}, rfq=rfq)

    # 草稿附件条目 (write-reply 接线同款)
    draft = {"subject": r["reply"]["subject"], "body": "(draft_only 草稿正文略)",
             "auto_send": r["reply"]["auto_send"]}
    attach_quote_pdf(draft, quote=quote, context_id=cid,
                     customer=sc.get("customer") or {}, rfq=rfq, out_dir=art_dir)

    if rendered.get("path"):
        rendered["path"] = _rel(rendered["path"])
    for att in draft.get("attachments") or []:
        if att.get("path"):
            att["path"] = _rel(att["path"])

    sample = {
        "feature": "G2 报价单 PDF 附件闭环 (v6.3.1)",
        "scenario": sc["id"],
        "engine_source": r["engine_source"],
        "context_id": cid,
        "verification_status": r["verification_status"],
        "quote": quote,
        "rfq": rfq,
        "rendered": rendered,
        "draft_attachments": draft.get("attachments"),
        "draft_only": True,
        "iron_rule": "PDF 只反映确定性引擎产出; content_sha256 锁报价事实 (canonical json), "
                     "不锁 PDF 字节 (reportlab 内嵌时间戳); 附件永不自动外发",
    }
    (evidence_dir / "g2_quote_pdf_sample.json").write_text(
        json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
    if ctrl.crm is not None:
        ctrl.crm.close()
    return sample


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--online", action="store_true", help="在线优先 :7862 (默认离线 byte-identical)")
    a = ap.parse_args()

    _EV.mkdir(parents=True, exist_ok=True)
    g1 = gen_g1(_EV)
    g2 = gen_g2(_EV, offline=not a.online)

    print("=" * 78)
    print(" v6.3.1 融合增量验收证据 → data/fusion_evidence/")
    print("=" * 78)
    print(f' [G1] policy timeout_hours={g1["policy"]["timeout_hours"]} '
          f'backup_approvers={g1["policy"]["backup_approvers"]}')
    print(f' [G1] escalated={len(g1["first_scan"])} '
          f'notifications={len(g1["notifications"])} '
          f'audit_records={len(g1["audit_records"])} '
          f'dedup_second_scan={len(g1["dedup_second_scan_within_window"])}')
    print(f' [G1] entry_after.state={g1["entry_after"]["state"]} (仍 HITL, 未代审)')
    print(f' [G2] scenario={g2["scenario"]} engine={g2["engine_source"]} cid={g2["context_id"]}')
    print(f' [G2] unit_price={g2["quote"].get("unit_price")} '
          f'final_price={g2["quote"].get("final_price")}')
    print(f' [G2] content_sha256={g2["rendered"].get("content_sha256")}')
    print(f' [G2] pdf={g2["rendered"].get("path")} ({g2["rendered"].get("bytes")} bytes)')
    print(f' [G2] attachments={g2["draft_attachments"]}')
    return 0 if (g1["first_scan"] and g2["rendered"].get("ok")) else 1


if __name__ == "__main__":
    sys.exit(main())
