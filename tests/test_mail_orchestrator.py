"""tests/test_mail_orchestrator.py — T2: 自动触发链路 (pull → CATController) 12 用例.

覆盖:
  1. PASS 路径: mock CAT verdict=PASS → DONE + 自动 approve + audit +1
  2. HITL 路径: mock CAT verdict=HITL → HITL + notify 调通
  3. BLOCKED 路径: mock CAT verdict=BLOCKED → BLOCKED + notify
  3b. BLOCKED 路径 · 真 CAT 形态: state=ARCHIVED + verification_status=BLOCKED → BLOCKED
     (2026-09-21 实测 bug: orchestrator 取 state 键把 ARCHIVED 当 verdict → 误判 FAILED)
  4. FAILED 路径: CAT 抛异常 → FAILED + 不阻塞主链
  5. 重复触发幂等: 同一 mail_id claim 后 state=PROCESSING, 再次 run_pipeline 返 already-processing
  6. 启动/停止后台 loop + 监听 NEW 自动跑
  7. notifier 失败不阻塞主链 (返 notified=False, state 仍正常)
  8. pending.jsonl 持久化 + audit jsonl 含 audit_tag=l3-auto
  9. P0 driver 标记: email 入口 → result.driver + audit payload.driver
  10. P0 driver 标记: agent 驱动 entry 同样透传
  11. P0 driver 标记: CAT 调用收到 driver kwarg
  12. audit jsonl + pending 持久化
  14. RAG 输出侧闭环: 报价落定 → quote_history 自动 +1 / 无报价不索引 /
      索引失败不断链 (2026-09-26 节点断链实证: 1 vs 1354 可入库报价)
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from services.mail_puller import MailPuller, PendingEntry, STATE_NEW, STATE_PROCESSING


# ---------- 工具 ----------
def _write_eml(tmp_root: Path, mail_id: str, *, from_: str = "alice@northwind.com",
               subject: str = "RFQ 6061 brackets", body: str = "Need quote 50 pcs 6061") -> Path:
    """写一个真实可被 stdlib email 解析的 .eml 文件."""
    eml_path = tmp_root / "data" / "mailbox" / f"{mail_id}.eml"
    eml_path.parent.mkdir(parents=True, exist_ok=True)
    raw = (
        f"From: {from_}\r\n"
        f"To: sales@union-mfg.com\r\n"
        f"Subject: {subject}\r\n"
        f"Date: Mon, 19 Sep 2026 10:00:00 +0800\r\n"
        f"\r\n"
        f"{body}\r\n"
    ).encode("utf-8")
    eml_path.write_bytes(raw)
    meta_path = eml_path.with_suffix(".meta.json") if eml_path.suffix == ".eml" else eml_path.parent / f"{mail_id}.meta.json"
    meta_path.write_text(json.dumps({
        "from": from_, "subject": subject, "received_at": time.time(),
        "badges": ["NEW", "GMAIL_PULLED"], "source": "test"
    }), encoding="utf-8")
    return eml_path


def _make_puller(tmp_root: Path) -> MailPuller:
    return MailPuller(root=tmp_root, interval_s=0.5, limit=10, mailbox_factory=None)


class MockCAT:
    """Mock CATController: 返固定 verdict.

    sm_state: 显式指定状态机终态 (真 CAT 形态)。None 时退化为 verdict 同值
    (旧形态, 双键同值会掩盖 orchestrator 取错键的 bug — 见 3b 用例)。
    """

    def __init__(self, verdict: str = "PASS", *, raise_exc: Optional[Exception] = None,
                 context_id: str = "RFQ-MOCK-001",
                 sm_state: Optional[str] = None):
        self.verdict = verdict
        self.raise_exc = raise_exc
        self.context_id = context_id
        self.sm_state = sm_state
        self.call_count = 0
        self.last_email_text = ""
        self.last_customer: Dict[str, Any] = {}

    def run(self, email_text: str, customer: Optional[Dict[str, Any]] = None,
            **kwargs: Any) -> Dict[str, Any]:
        self.call_count += 1
        self.last_email_text = email_text
        self.last_customer = customer or {}
        if self.raise_exc:
            raise self.raise_exc
        return {
            "state": self.sm_state if self.sm_state is not None else self.verdict,
            "context_id": self.context_id,
            "verification_status": self.verdict,
            "reasons": ["mock reason"] if self.verdict != "PASS" else [],
        }


def _make_orch(tmp_root: Path, cat: Any, notifier=None) -> Any:
    from services.mail_orchestrator import MailOrchestrator
    puller = _make_puller(tmp_root)
    return MailOrchestrator(root=tmp_root, puller=puller, cat=cat, notifier=notifier), puller, cat


# ---- 1. PASS 路径 ----
def test_pass_path_done_and_audit(tmp_root: Path) -> None:
    _write_eml(tmp_root, "M-PASS-1")
    orch, puller, cat = _make_orch(tmp_root, MockCAT(verdict="PASS"))
    # 先把邮件挂到 pending (模拟 puller 已 enqueue)
    puller._append_pending([PendingEntry(mail_id="M-PASS-1", state=STATE_NEW)])
    r = orch.run_pipeline("M-PASS-1")
    assert r.ok is True
    assert r.state == "DONE"
    assert r.context_id == "RFQ-MOCK-001"
    assert r.approved is True
    assert cat.call_count == 1
    # pending 状态更新
    assert puller.list_by_state("DONE")[0].mail_id == "M-PASS-1"
    # audit 落库
    audit_path = tmp_root / "data" / "skill_audit.jsonl"
    assert audit_path.exists()
    lines = [json.loads(l) for l in audit_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert any(l.get("event") == "pipeline_done" and l.get("audit_tag") == "l3-auto" for l in lines)


# ---- 2. HITL 路径 ----
def test_hitl_path_notified(tmp_root: Path) -> None:
    _write_eml(tmp_root, "M-HITL-1")
    notif = []
    def n(kind, payload):
        notif.append((kind, payload))
        return True
    orch, puller, cat = _make_orch(tmp_root, MockCAT(verdict="HITL"), notifier=n)
    puller._append_pending([PendingEntry(mail_id="M-HITL-1", state=STATE_NEW)])
    r = orch.run_pipeline("M-HITL-1")
    assert r.ok is True
    assert r.state == "HITL"
    assert r.notified is True
    assert r.approved is False
    assert len(notif) == 1
    assert notif[0][0] == "hitl"
    assert notif[0][1]["context_id"] == "RFQ-MOCK-001"
    assert puller.list_by_state("HITL")[0].mail_id == "M-HITL-1"


# ---- 3. BLOCKED 路径 ----
def test_blocked_path_notified(tmp_root: Path) -> None:
    _write_eml(tmp_root, "M-BLK-1")
    notif = []
    def n(kind, payload):
        notif.append((kind, payload))
        return True
    orch, puller, cat = _make_orch(tmp_root, MockCAT(verdict="BLOCKED"), notifier=n)
    puller._append_pending([PendingEntry(mail_id="M-BLK-1", state=STATE_NEW)])
    r = orch.run_pipeline("M-BLK-1")
    assert r.ok is True
    assert r.state == "BLOCKED"
    assert r.notified is True
    assert notif[0][0] == "blocked"
    assert puller.list_by_state("BLOCKED")[0].mail_id == "M-BLK-1"


# ---- 3b. BLOCKED 路径 · 真 CAT 形态 (回归 2026-09-21 S3 实测 bug) ----
def test_blocked_path_real_cat_shape_state_archived(tmp_root: Path) -> None:
    """真 CATController BLOCKED 路径: sm.state=ARCHIVED (cat_controller.py:429/433),
    verdict 在 verification_status=BLOCKED。orchestrator 必须认 verification_status;
    若优先取 state, "ARCHIVED" 不在 (PASS/DONE/HITL/BLOCKED) 映射表 → 误判 FAILED,
    且 pending 落 FAILED、blocked 通知不发 (2026-09-21 demo S3 实测复现)。"""
    _write_eml(tmp_root, "M-BLK-REAL-1")
    notif = []
    def n(kind, payload):
        notif.append((kind, payload))
        return True
    orch, puller, cat = _make_orch(
        tmp_root, MockCAT(verdict="BLOCKED", sm_state="ARCHIVED"), notifier=n)
    puller._append_pending([PendingEntry(mail_id="M-BLK-REAL-1", state=STATE_NEW)])
    r = orch.run_pipeline("M-BLK-REAL-1")
    assert r.state == "BLOCKED"
    assert r.notified is True
    assert notif[0][0] == "blocked"
    assert puller.list_by_state("BLOCKED")[0].mail_id == "M-BLK-REAL-1"
    assert puller.list_by_state("FAILED") == []


# ---- 4. FAILED 路径 ----
def test_failed_path_cat_exception(tmp_root: Path) -> None:
    _write_eml(tmp_root, "M-FAIL-1")
    orch, puller, _ = _make_orch(tmp_root, MockCAT(raise_exc=RuntimeError("cat boom")))
    puller._append_pending([PendingEntry(mail_id="M-FAIL-1", state=STATE_NEW)])
    r = orch.run_pipeline("M-FAIL-1")
    assert r.ok is False
    assert r.state == "FAILED"
    assert "cat boom" in r.reason
    assert puller.list_by_state("FAILED")[0].mail_id == "M-FAIL-1"
    assert puller.list_by_state("DONE") == []
    assert puller.list_by_state("HITL") == []
    # 主链不阻塞: orchestrator 本身仍可继续处理下一封
    _write_eml(tmp_root, "M-PASS-2")
    puller._append_pending([PendingEntry(mail_id="M-PASS-2", state=STATE_NEW)])
    # 新建 PASS cat
    from services.mail_orchestrator import MailOrchestrator
    orch2 = MailOrchestrator(root=tmp_root, puller=puller,
                              cat=MockCAT(verdict="PASS", context_id="RFQ-002"))
    r2 = orch2.run_pipeline("M-PASS-2")
    assert r2.ok is True
    assert r2.state == "DONE"


# ---- 5. 重复触发幂等 ----
def test_repeat_run_idempotent(tmp_root: Path) -> None:
    _write_eml(tmp_root, "M-IDEMP-1")
    orch, puller, cat = _make_orch(tmp_root, MockCAT(verdict="PASS"))
    puller._append_pending([PendingEntry(mail_id="M-IDEMP-1", state=STATE_NEW)])
    # 1st run: claim + DONE
    r1 = orch.run_pipeline("M-IDEMP-1")
    assert r1.ok is True
    assert r1.state == "DONE"
    assert cat.call_count == 1
    # 2nd run: 已 DONE, 不再调 CAT
    r2 = orch.run_pipeline("M-IDEMP-1")
    assert r2.ok is False
    assert r2.state == "DONE"
    assert r2.reason.startswith("already in state")
    assert cat.call_count == 1  # 没再调


# ---- 6. 后台 loop 自动跑 ----
def test_loop_drains_pending(tmp_root: Path) -> None:
    _write_eml(tmp_root, "M-LOOP-1")
    _write_eml(tmp_root, "M-LOOP-2")
    orch, puller, cat = _make_orch(tmp_root, MockCAT(verdict="PASS", context_id="RFQ-LOOP"))
    puller._append_pending([
        PendingEntry(mail_id="M-LOOP-1", state=STATE_NEW),
        PendingEntry(mail_id="M-LOOP-2", state=STATE_NEW),
    ])
    orch.start_loop(poll_interval_s=0.3)
    # 等后台处理 2 封
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if len(puller.list_by_state("DONE")) >= 2:
            break
        time.sleep(0.2)
    orch.stop(timeout=3.0)
    assert len(puller.list_by_state("DONE")) == 2
    assert cat.call_count == 2


# ---- 7. notifier 失败不阻塞 ----
def test_notifier_failure_does_not_block(tmp_root: Path) -> None:
    _write_eml(tmp_root, "M-NFAIL-1")
    def n(kind, payload):
        raise ConnectionError("telegram down")
    orch, puller, _ = _make_orch(tmp_root, MockCAT(verdict="HITL"), notifier=n)
    puller._append_pending([PendingEntry(mail_id="M-NFAIL-1", state=STATE_NEW)])
    r = orch.run_pipeline("M-NFAIL-1")
    assert r.ok is True
    assert r.state == "HITL"
    assert r.notified is False  # 通知失败但状态正常
    assert puller.list_by_state("HITL")[0].mail_id == "M-NFAIL-1"


# ---- 9. P0 driver 标记: email 入口透传到 result + audit ----
def test_driver_marker_email_flows_to_result_and_audit(tmp_root: Path) -> None:
    _write_eml(tmp_root, "M-DRV-1")
    orch, puller, cat = _make_orch(tmp_root, MockCAT(verdict="PASS"))
    puller._append_pending([PendingEntry(mail_id="M-DRV-1", state=STATE_NEW,
                                         driver="email", source_ref="<m1>")])
    r = orch.run_pipeline("M-DRV-1")
    assert r.ok is True
    assert r.driver == "email"
    audit_path = tmp_root / "data" / "skill_audit.jsonl"
    lines = [json.loads(l) for l in audit_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    done = [l for l in lines if l.get("event") == "pipeline_done"]
    assert done and done[-1]["payload"]["driver"] == "email"


# ---- 10. P0 driver 标记: agent 驱动 entry 同样透传 ----
def test_driver_marker_agent_entry(tmp_root: Path) -> None:
    _write_eml(tmp_root, "M-DRV-2")
    orch, puller, cat = _make_orch(tmp_root, MockCAT(verdict="PASS"))
    puller._append_pending([PendingEntry(mail_id="M-DRV-2", state=STATE_NEW,
                                         driver="agent", source_ref="flywheel:retention")])
    r = orch.run_pipeline("M-DRV-2")
    assert r.ok is True
    assert r.driver == "agent"
    audit_path = tmp_root / "data" / "skill_audit.jsonl"
    lines = [json.loads(l) for l in audit_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    done = [l for l in lines if l.get("event") == "pipeline_done"]
    assert done[-1]["payload"]["driver"] == "agent"


# ---- 11. P0 driver 标记: CAT 调用收到 driver ----
def test_driver_marker_passed_to_cat(tmp_root: Path) -> None:
    _write_eml(tmp_root, "M-DRV-3")
    cat = MockCAT(verdict="PASS")
    cat.last_driver = None
    orig_run = cat.run

    def run_spy(email_text, customer=None, **kw):
        cat.last_driver = kw.get("driver")
        return orig_run(email_text, customer, **kw)

    cat.run = run_spy
    orch, puller, _ = _make_orch(tmp_root, cat)
    puller._append_pending([PendingEntry(mail_id="M-DRV-3", state=STATE_NEW,
                                         driver="email", source_ref="<m3>")])
    r = orch.run_pipeline("M-DRV-3")
    assert r.ok is True
    assert cat.last_driver == "email"


# ---- 13. 黄金链 LLM 阶段: Omni 驱动抽取/起草 (env 门, 默认开) ----
def test_chain_use_llm_default_on(tmp_root: Path, monkeypatch) -> None:
    monkeypatch.delenv("UEA_CHAIN_USE_LLM", raising=False)
    _write_eml(tmp_root, "M-LLM-1")
    cat = MockCAT(verdict="PASS")
    cat.last_use_llm = "unset"
    orig_run = cat.run

    def run_spy(email_text, customer=None, **kw):
        cat.last_use_llm = kw.get("use_llm")
        return orig_run(email_text, customer, **kw)

    cat.run = run_spy
    orch, puller, _ = _make_orch(tmp_root, cat)
    puller._append_pending([PendingEntry(mail_id="M-LLM-1", state=STATE_NEW,
                                         driver="email", source_ref="<m4>")])
    r = orch.run_pipeline("M-LLM-1")
    assert r.ok is True
    assert cat.last_use_llm is True


def test_chain_use_llm_env_off(tmp_root: Path, monkeypatch) -> None:
    monkeypatch.setenv("UEA_CHAIN_USE_LLM", "0")
    _write_eml(tmp_root, "M-LLM-2")
    cat = MockCAT(verdict="PASS")
    cat.last_use_llm = "unset"
    orig_run = cat.run

    def run_spy(email_text, customer=None, **kw):
        cat.last_use_llm = kw.get("use_llm")
        return orig_run(email_text, customer, **kw)

    cat.run = run_spy
    orch, puller, _ = _make_orch(tmp_root, cat)
    puller._append_pending([PendingEntry(mail_id="M-LLM-2", state=STATE_NEW,
                                         driver="email", source_ref="<m5>")])
    r = orch.run_pipeline("M-LLM-2")
    assert r.ok is True
    assert cat.last_use_llm is False


# ---- 12. audit jsonl + pending 持久化 ----
def test_audit_and_persistence(tmp_root: Path) -> None:
    _write_eml(tmp_root, "M-PERS-1")
    orch, puller, _ = _make_orch(tmp_root, MockCAT(verdict="DONE", context_id="RFQ-PERS"))
    puller._append_pending([PendingEntry(mail_id="M-PERS-1", state=STATE_NEW)])
    orch.run_pipeline("M-PERS-1")
    # audit 含 l3-auto tag
    audit_path = tmp_root / "data" / "skill_audit.jsonl"
    lines = [json.loads(l) for l in audit_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    events = [l["event"] for l in lines]
    assert "pipeline_done" in events
    assert all(l.get("audit_tag") == "l3-auto" for l in lines)
    # 新建 orchestrator 读同一目录 → pending 状态保持
    from services.mail_orchestrator import MailOrchestrator
    puller2 = _make_puller(tmp_root)
    orch2 = MailOrchestrator(root=tmp_root, puller=puller2, cat=MockCAT(verdict="DONE"))
    entries = puller2._read_pending()
    assert any(e.mail_id == "M-PERS-1" and e.state == "DONE" for e in entries)


# ---- 13. 2026-09-24 过滤层: 非询价/灰区/force 覆写/终态已读 ----
def _write_junk_eml(tmp_root: Path, mail_id: str, subject: str,
                    body: str = "感谢您的参与, 详情见链接。") -> Path:
    return _write_eml(tmp_root, mail_id, from_="notify@nvidia.cn",
                      subject=subject, body=body)


def test_non_rfq_mail_skipped_no_cat_run(tmp_root: Path) -> None:
    """NVIDIA 通知类邮件 → SKIPPED, 绝不调 CAT (不建 RFQ context)."""
    _write_junk_eml(tmp_root, "M-JUNK-1", "【入选通知】恭喜！你的作品已入选云栖大会")
    orch, puller, cat = _make_orch(tmp_root, MockCAT(verdict="PASS"))
    puller._append_pending([PendingEntry(mail_id="M-JUNK-1", state=STATE_NEW)])
    r = orch.run_pipeline("M-JUNK-1")
    assert r.state == "SKIPPED"
    assert r.ok is True
    assert cat.call_count == 0                      # 关键: 不碰黄金链
    assert r.context_id is None
    e = puller.list_by_state("SKIPPED")[0]
    assert e.error and "非询价" in e.error
    meta = json.loads((tmp_root / "data" / "mailbox" / "M-JUNK-1.meta.json")
                      .read_text(encoding="utf-8"))
    assert "NON_RFQ" in meta["badges"]
    assert meta["filter"]["kind"] == "skip"
    # audit 留痕
    audit = (tmp_root / "data" / "skill_audit.jsonl").read_text(encoding="utf-8")
    assert "mail_filtered" in audit


def test_gray_zone_mail_skipped_with_review_badge(tmp_root: Path) -> None:
    """灰区邮件 (无信号) → SKIPPED + GRAY_REVIEW 徽标 (可 reprocess 覆写)."""
    _write_eml(tmp_root, "M-GRAY-1", from_="someone@buyer.com",
               subject="平台", body="")
    orch, puller, cat = _make_orch(tmp_root, MockCAT(verdict="PASS"))
    puller._append_pending([PendingEntry(mail_id="M-GRAY-1", state=STATE_NEW)])
    r = orch.run_pipeline("M-GRAY-1")
    assert r.state == "SKIPPED"
    assert cat.call_count == 0
    meta = json.loads((tmp_root / "data" / "mailbox" / "M-GRAY-1.meta.json")
                      .read_text(encoding="utf-8"))
    assert "GRAY_REVIEW" in meta["badges"]
    assert meta["filter"]["kind"] == "gray"


def test_force_flag_bypasses_filter(tmp_root: Path) -> None:
    """force=1 (人工 reprocess) → 绕过分类, 照常跑黄金链."""
    _write_junk_eml(tmp_root, "M-FORCE-1", "【入选通知】恭喜！你的作品已入选")
    orch, puller, cat = _make_orch(tmp_root, MockCAT(verdict="PASS"))
    puller._append_pending([PendingEntry(mail_id="M-FORCE-1", state=STATE_NEW, force=1)])
    r = orch.run_pipeline("M-FORCE-1")
    assert r.state == "DONE"
    assert cat.call_count == 1
    audit = (tmp_root / "data" / "skill_audit.jsonl").read_text(encoding="utf-8")
    assert "mail_force_reprocess" in audit


def test_genuine_rfq_writes_filter_meta(tmp_root: Path) -> None:
    """真询价正常入链, meta.filter 记录 rfq 判定 (inbox 前端 chips 用)."""
    _write_eml(tmp_root, "M-RFQ-9", subject="询价报价 c2123 工件 铝合金6061 数量 9",
               body="请报价, 精度 0.1, 阳极氧化黑")
    orch, puller, cat = _make_orch(tmp_root, MockCAT(verdict="PASS"))
    puller._append_pending([PendingEntry(mail_id="M-RFQ-9", state=STATE_NEW)])
    r = orch.run_pipeline("M-RFQ-9")
    assert r.state == "DONE"
    meta = json.loads((tmp_root / "data" / "mailbox" / "M-RFQ-9.meta.json")
                      .read_text(encoding="utf-8"))
    assert meta["filter"]["kind"] == "rfq"


def test_terminal_state_marks_imap_read(tmp_root: Path, monkeypatch) -> None:
    """终态 DONE → 调 mark_mailbox_read 标 \Seen (用户: 完成后再标已读)."""
    calls = []
    import services.gmail_imap as gim
    monkeypatch.setattr(gim, "mark_mailbox_read",
                        lambda root, mid, **kw: calls.append((str(root), mid)) or {"ok": True})
    _write_eml(tmp_root, "M-READ-1")
    orch, puller, cat = _make_orch(tmp_root, MockCAT(verdict="PASS"))
    puller._append_pending([PendingEntry(mail_id="M-READ-1", state=STATE_NEW)])
    r = orch.run_pipeline("M-READ-1")
    assert r.state == "DONE"
    assert calls and calls[0][1] == "M-READ-1"


def test_hitl_not_marked_read(tmp_root: Path, monkeypatch) -> None:
    """HITL 等待人工 → 保持未读 (人工 send-reply 后才标, 端点侧)."""
    calls = []
    import services.gmail_imap as gim
    monkeypatch.setattr(gim, "mark_mailbox_read",
                        lambda root, mid, **kw: calls.append(mid) or {"ok": True})
    _write_eml(tmp_root, "M-HITL-9")
    orch, puller, cat = _make_orch(tmp_root, MockCAT(verdict="HITL"))
    puller._append_pending([PendingEntry(mail_id="M-HITL-9", state=STATE_NEW)])
    r = orch.run_pipeline("M-HITL-9")
    assert r.state == "HITL"
    assert calls == []


def test_mark_read_policy_off(tmp_root: Path, monkeypatch) -> None:
    """policy mark_read_on_terminal=false → 不标 (运维开关)."""
    calls = []
    import services.gmail_imap as gim
    monkeypatch.setattr(gim, "mark_mailbox_read",
                        lambda root, mid, **kw: calls.append(mid) or {"ok": True})
    (tmp_root / "config").mkdir()
    (tmp_root / "config" / "policy.yaml").write_text(
        "mail_filter:\n  mark_read_on_terminal: false\n", encoding="utf-8")
    _write_eml(tmp_root, "M-NOREAD-1")
    orch, puller, cat = _make_orch(tmp_root, MockCAT(verdict="PASS"))
    puller._append_pending([PendingEntry(mail_id="M-NOREAD-1", state=STATE_NEW)])
    r = orch.run_pipeline("M-NOREAD-1")
    assert r.state == "DONE"
    assert calls == []


def test_skipped_mail_marks_read(tmp_root: Path, monkeypatch) -> None:
    """SKIPPED (过滤掉) 也是终态 → 标已读, 不再重复解读."""
    calls = []
    import services.gmail_imap as gim
    monkeypatch.setattr(gim, "mark_mailbox_read",
                        lambda root, mid, **kw: calls.append(mid) or {"ok": True})
    _write_junk_eml(tmp_root, "M-JUNK-9", "ClawHub blocked a skill version")
    orch, puller, cat = _make_orch(tmp_root, MockCAT(verdict="PASS"))
    puller._append_pending([PendingEntry(mail_id="M-JUNK-9", state=STATE_NEW)])
    r = orch.run_pipeline("M-JUNK-9")
    assert r.state == "SKIPPED"
    assert calls == ["M-JUNK-9"]


def test_force_reprocess_after_skip_runs_pipeline(tmp_root: Path) -> None:
    """SKIPPED → 人工 reprocess 追加 force=1 行 → drain 再跑: 绕过过滤进黄金链.

    回归: entry_now/mark_state 若命中首行 (旧 SKIPPED), force 丢失 → 重跑仍被
    过滤层拦回, 人工 reprocess 端点形同虚设。
    """
    _write_junk_eml(tmp_root, "M-RP-1", "【入选通知】恭喜！你的作品已入选")
    orch, puller, cat = _make_orch(tmp_root, MockCAT(verdict="PASS"))
    puller._append_pending([PendingEntry(mail_id="M-RP-1", state=STATE_NEW)])
    r1 = orch.run_pipeline("M-RP-1")
    assert r1.state == "SKIPPED" and cat.call_count == 0
    # 人工 reprocess (镜像 POST /v1/mail/{id}/reprocess): 追加 force=1 NEW 行
    puller._append_pending([PendingEntry(mail_id="M-RP-1", state=STATE_NEW, force=1,
                                         driver="console")])
    r2 = orch.run_pipeline("")   # drain 入口: 自己 claim 下一条 (尾行, force=1)
    assert r2.state == "DONE" and cat.call_count == 1
    assert puller.pending_index()["M-RP-1"]["state"] == "DONE"


def test_failed_paths_mark_imap_read(tmp_root: Path, monkeypatch) -> None:
    """FAILED (CAT 异常 / 未知 verdict) 也是终态 → 标已读 (终态即标, 用户拍板)."""
    calls: List[str] = []
    import services.gmail_imap as gim
    monkeypatch.setattr(gim, "mark_mailbox_read",
                        lambda root, mid, **kw: calls.append(mid) or {"ok": True})
    _write_eml(tmp_root, "M-FAIL-9")
    orch, puller, cat = _make_orch(
        tmp_root, MockCAT(verdict="PASS", raise_exc=RuntimeError("boom")))
    puller._append_pending([PendingEntry(mail_id="M-FAIL-9", state=STATE_NEW)])
    assert orch.run_pipeline("M-FAIL-9").state == "FAILED"
    _write_eml(tmp_root, "M-FAIL-10", subject="RFQ unknown verdict",
               body="please quote this part")
    orch2, puller2, cat2 = _make_orch(tmp_root, MockCAT(verdict="WEIRD"))
    puller2._append_pending([PendingEntry(mail_id="M-FAIL-10", state=STATE_NEW)])
    assert orch2.run_pipeline("M-FAIL-10").state == "FAILED"
    assert calls == ["M-FAIL-9", "M-FAIL-10"]


# ---- 14. RAG 输出侧闭环: 报价落定 → quote_history 向量自动 +1 ----
# 根因实证 (2026-09-26): 全仓 grep index_quote( 生产调用点只有 tests 与手工
# rag-ingest skill; 黄金链 run_pipeline 零调用 → 节点 quote_history=1 vs
# crm 主库 2095 条报价 (1354 条带 customer_id 可入库), L2 相似召回空转。

class _SpyRAG:
    """记录 index_quote 调用的 rag_gateway 替身 (契约同 LayeredRAGGateway)."""

    def __init__(self) -> None:
        self.calls: List[Any] = []

    def index_quote(self, customer_id: str, quote_id: str, text: str) -> bool:
        self.calls.append((customer_id, quote_id, text))
        return True


class _BoomRAG:
    """index_quote 恒抛 — 验证索引失败绝不阻塞黄金链."""

    def index_quote(self, customer_id: str, quote_id: str, text: str) -> bool:
        raise RuntimeError("embed down")


def _write_context_json(tmp_root: Path, context_id: str, *,
                        customer_id: str = "ACME",
                        quote: Optional[Dict[str, Any]] = None,
                        material: str = "6061") -> Path:
    """按 ContextEngine.save 落盘形状写 data/contexts/{cid}.json
    (commercial.quote 顶层键 — 与 _try_auto_quote 读的口径一致)."""
    d = tmp_root / "data" / "contexts"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{context_id}.json").write_text(json.dumps({
        "customer": {"customer_id": customer_id, "name": "ACME GmbH"},
        "rfq": {"material": material, "surface": "anodizing",
                "tolerance_grade": "IT7", "quantity": 100},
        "commercial": {"quote": quote if quote is not None else
                       {"unit_price": 172.57, "final_price": 17257.0,
                        "currency": "CNY"}},
        "decision": {"status": "PASS"},
    }), encoding="utf-8")
    return d / f"{context_id}.json"


def test_pass_quote_indexed_into_rag(tmp_root: Path) -> None:
    """PASS 且 context 带 commercial.quote → rag_gateway.index_quote 恰好调 1 次,
    点 id = customer_id:context_id (与存量回填 index_all_quotes 口径一致),
    text 含材料与单价等召回信号。"""
    _write_eml(tmp_root, "M-RAG-1")
    cat = MockCAT(verdict="PASS")
    spy = _SpyRAG()
    cat.rag_gateway = spy
    _write_context_json(tmp_root, "RFQ-MOCK-001")
    orch, puller, _ = _make_orch(tmp_root, cat)
    puller._append_pending([PendingEntry(mail_id="M-RAG-1", state=STATE_NEW)])
    r = orch.run_pipeline("M-RAG-1")
    assert r.state == "DONE"
    assert len(spy.calls) == 1
    cid, qid, text = spy.calls[0]
    assert cid == "ACME"
    assert qid == "RFQ-MOCK-001"
    assert "6061" in text and "172.57" in text


def test_no_quote_not_indexed(tmp_root: Path) -> None:
    """context 无 commercial.quote (未定价/被拦) → 不索引 (不污染召回语料)."""
    _write_eml(tmp_root, "M-RAG-2")
    cat = MockCAT(verdict="HITL")
    spy = _SpyRAG()
    cat.rag_gateway = spy
    _write_context_json(tmp_root, "RFQ-MOCK-001", quote={})
    orch, puller, _ = _make_orch(tmp_root, cat)
    puller._append_pending([PendingEntry(mail_id="M-RAG-2", state=STATE_NEW)])
    r = orch.run_pipeline("M-RAG-2")
    assert r.state == "HITL"
    assert spy.calls == []


def test_rag_index_failure_does_not_block(tmp_root: Path) -> None:
    """index_quote 抛错 → 主链照常 DONE + audit 留痕 (best-effort, 铁律:
    索引失败绝不阻塞报价链路; quote_indexer 契约同款)."""
    _write_eml(tmp_root, "M-RAG-3")
    cat = MockCAT(verdict="PASS")
    cat.rag_gateway = _BoomRAG()
    _write_context_json(tmp_root, "RFQ-MOCK-001")
    orch, puller, _ = _make_orch(tmp_root, cat)
    puller._append_pending([PendingEntry(mail_id="M-RAG-3", state=STATE_NEW)])
    r = orch.run_pipeline("M-RAG-3")
    assert r.state == "DONE"
    audit = (tmp_root / "data" / "skill_audit.jsonl").read_text(encoding="utf-8")
    assert "rag_index_failed" in audit
