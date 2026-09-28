"""tests/test_m0_backport.py — M0: 节点反超本地的热补丁簇回灌契约 (TDD RED)。

覆盖节点 v2.4.0 报价门禁分级 + v2.5.0 邮件自动报价外发的本地契约 (合并前必须全红):
  1. intake._extract_quantity: 套/台/批/pcs/lots 量词 + 投产/订购/order for 引导词
  2. verification: quote_gate 分级 — 阻塞字段缺 → CLARIFY (非 HITL); 可默认字段假设申报;
     quote_gate 关闭 → 回到"缺字段即 HITL"旧行为 (逃生门)
  3. reply: status=CLARIFY → mode=auto_clarify / auto_send=True / 正文无价格无币种;
     PASS 价格行跟随引擎 currency (缺省 CNY, 不再硬编码 USD/CNY)
  4. cat_controller._apply_quote_gate: 可默认字段回填+_assumed_defaults / 阻塞字段不回填 /
     audit quote_gate / 关闭时 {"enabled": False} 不碰 rfq
  5. mail_orchestrator: strip_html; CLARIFY verdict → HITL 桶 (不掉 FAILED);
     _try_auto_clarify 四闸 (mode/auto_send/冷却/价格泄漏正则);
     _try_auto_quote 八闸 (开关/PASS/报价事实/护栏/价格一致性/阈值/自环/幂等)
  6. config/policy.yaml: quote_gate / oversize / multimodal.size_conflict_ratio 段可加载
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from services.config import load_policy

ROOT = Path(__file__).resolve().parent.parent

QUOTE_GATE_POLICY: Dict[str, Any] = {
    "quote_gate": {
        "enabled": True,
        "blocking_fields": ["material", "quantity", "dimensions"],
        "defaultable": {"surface_finish": "无", "tolerance": "IT8"},
        "auto_clarify_enabled": True,
        "auto_clarify_cooldown_hours": 24,
        "auto_quote_send_enabled": True,
    },
    "auto_quote_threshold": {"features_count_max": 10, "process_route_max": 10},
}


def _ctx(missing: list, *, assumed: Optional[list] = None) -> Dict[str, Any]:
    rfq: Dict[str, Any] = {
        "material": "6061", "quantity": 4, "surface": "喷砂",
        "tolerance_grade": "IT8", "dimensions_mm": [50.0, 50.0, 20.0],
        "missing_information": missing,
    }
    if assumed:
        rfq["_assumed_defaults"] = assumed
    return {
        "context_id": "RFQ-M0-TEST",
        "rfq": rfq,
        "manufacturing": {"dfm": {"valid": True}},
        "commercial": {},
        "risk": {},
        "evidence": [{"evidence_id": "e1", "source_type": "email", "mock": False}],
    }


class _AuditStub:
    def __init__(self) -> None:
        self.events: list = []

    def log(self, event: str, payload: Dict[str, Any], actor: str = "") -> None:
        self.events.append({"event": event, "payload": payload, "actor": actor})


# ---------- 1. intake 数量抽取 (2026-09-25 节点热补丁: "目前投产3套" 原漏抽) ----------

def test_extract_quantity_cjk_units() -> None:
    from services.intake import _extract_quantity
    assert _extract_quantity("目前投产3套") == 3
    assert _extract_quantity("我们需要 120 件") == 120
    assert _extract_quantity("订 5 台 阀门") == 5
    assert _extract_quantity("2 批 法兰") == 2
    assert _extract_quantity("数量 15") == 15


def test_extract_quantity_ascii_units_and_guides() -> None:
    from services.intake import _extract_quantity
    assert _extract_quantity("please quote 50 pcs") == 50
    assert _extract_quantity("order for 20 pieces") == 20
    assert _extract_quantity("we need 3 lots") == 3
    assert _extract_quantity("订购 8 sets") == 8


def test_extract_quantity_no_false_positive() -> None:
    """'3 settings' 不得命中 sets; 'temperature' 场景无数字 → None。"""
    from services.intake import _extract_quantity
    assert _extract_quantity("please check 3 settings") is None
    assert _extract_quantity("no quantity mentioned anywhere") is None


# ---------- 2. verification quote_gate 分级 ----------

def test_verification_clarify_on_blocking_missing() -> None:
    from services.verification import Verification
    v = Verification(QUOTE_GATE_POLICY)
    r = v.run(_ctx(["material"]))
    assert r["status"] == "CLARIFY", f"缺阻塞字段应 CLARIFY, 实际 {r['status']}: {r['reasons']}"
    assert r["next_action"] == "AUTO_CLARIFY"
    assert any("阻塞字段缺失" in x and "material" in x for x in r["reasons"])


def test_verification_assumed_defaults_reported() -> None:
    from services.verification import Verification
    v = Verification(QUOTE_GATE_POLICY)
    r = v.run(_ctx(["surface_finish"], assumed=["surface_finish=无"]))
    assert r["status"] == "PASS", f"只有可默认字段缺 → 应 PASS, 实际 {r['status']}: {r['reasons']}"
    assert any("按默认值报价(待客户确认)" in x for x in r["reasons"])


def test_verification_gate_off_falls_back_to_hitl() -> None:
    from services.verification import Verification
    policy = {"quote_gate": {"enabled": False}}
    v = Verification(policy)
    r = v.run(_ctx(["material"]))
    assert r["status"] == "HITL", "逃生门: quote_gate 关闭 → 缺字段即 HITL (旧行为)"
    assert any("RFQ 关键信息缺失" in x for x in r["reasons"])


# ---------- 3. reply CLARIFY 分支 + 价格行币种 ----------

def test_reply_clarify_mode_no_price() -> None:
    from services.reply import build_reply
    ctx = _ctx(["material"])
    ctx["customer"] = {"contact_name": "Alice", "country": "US"}
    verification = {"status": "CLARIFY", "reasons": ["RFQ 阻塞字段缺失(需客户补充): material"]}
    r = build_reply(ctx, verification, profile={"sign_off": "Timo"})
    assert r["mode"] == "auto_clarify"
    assert r["auto_send"] is True
    assert r["status"] == "CLARIFY"
    body = r["body"]
    assert "Unit price" not in body
    assert "CNY" not in body and "USD" not in body and "¥" not in body
    assert "material" in body  # 只提客户已给要素, 缺失项不写成占位符


def test_reply_price_line_follows_quote_currency() -> None:
    from services.reply import build_reply
    ctx = _ctx([])
    ctx["customer"] = {"contact_name": "Bob"}
    ctx["commercial"] = {"quote": {"unit_price": 281.25, "final_price": 570.81,
                                   "lead_time_days": 15, "currency": "CNY"}}
    r = build_reply(ctx, {"status": "PASS", "reasons": []}, profile={"sign_off": "Timo"})
    assert r["mode"] == "draft_only"
    assert "Unit price: CNY 281.25" in r["body"]
    assert "USD/CNY" not in r["body"]


def test_reply_price_line_defaults_cny_when_engine_silent() -> None:
    from services.reply import build_reply
    ctx = _ctx([])
    ctx["customer"] = {"contact_name": "Bob"}
    ctx["commercial"] = {"quote": {"unit_price": 100.0, "final_price": 200.0,
                                   "lead_time_days": 10}}
    r = build_reply(ctx, {"status": "PASS", "reasons": []}, profile={"sign_off": "Timo"})
    assert "Unit price: CNY 100.0" in r["body"]


# ---------- 4. cat_controller._apply_quote_gate ----------

def _gate_stub(policy: Dict[str, Any]) -> Any:
    from types import SimpleNamespace
    from agents.cat_controller import CATController
    stub = SimpleNamespace(policy=policy)
    return CATController, stub


def test_apply_quote_gate_backfills_defaultable_and_reports() -> None:
    CATController, stub = _gate_stub(QUOTE_GATE_POLICY)
    rfq = {"material": "6061", "quantity": 4, "dimensions_mm": [50, 50, 20]}
    audit = _AuditStub()
    out = CATController._apply_quote_gate(stub, rfq, audit)
    assert rfq["surface"] == "无" and rfq["tolerance_grade"] == "IT8"
    assert rfq["_assumed_defaults"] == ["surface_finish=无", "tolerance=IT8"]
    assert rfq["missing_information"] == []  # 可默认字段补齐后无缺失
    assert out["assumed"] == ["surface_finish=无", "tolerance=IT8"]
    assert out["blocking"] == []
    assert [e["event"] for e in audit.events] == ["quote_gate"]


def test_apply_quote_gate_blocking_not_backfilled() -> None:
    CATController, stub = _gate_stub(QUOTE_GATE_POLICY)
    rfq = {"surface": "喷砂", "tolerance_grade": "IT8"}  # 材料/数量/尺寸全缺
    audit = _AuditStub()
    out = CATController._apply_quote_gate(stub, rfq, audit)
    assert out["blocking"] == ["material", "quantity", "dimensions"]
    assert set(rfq["missing_information"]) == {"material", "quantity", "dimensions"}
    assert "material" not in rfq  # 阻塞字段绝不回填 (回填等于造假价)


def test_apply_quote_gate_disabled_no_touch() -> None:
    CATController, stub = _gate_stub({"quote_gate": {"enabled": False}})
    rfq = {"material": "6061", "quantity": None}
    audit = _AuditStub()
    out = CATController._apply_quote_gate(stub, rfq, audit)
    assert out == {"enabled": False}
    assert "missing_information" not in rfq
    assert audit.events == []


# ---------- 5. mail_orchestrator ----------

def test_strip_html_removes_markup() -> None:
    from services.mail_orchestrator import strip_html
    assert strip_html("<p>Hello <b>world</b></p>") == "Hello world"
    assert strip_html("<style>a{color:red}</style><div>RFQ</div>") == "RFQ"
    assert strip_html("plain text") == "plain text"
    assert strip_html(None) == ""
    assert strip_html("<p>a &amp; b</p>") == "a & b"


def test_clarify_verdict_maps_to_hitl_state(tmp_root: Path) -> None:
    """CLARIFY 归入 HITL 桶 — 原本掉 else 判 FAILED, 澄清信永远发不出 (2026-09-25 实测)。"""
    from services.mail_puller import MailPuller, PendingEntry, STATE_NEW
    from services.mail_orchestrator import MailOrchestrator

    class MockCAT:
        def run(self, email_text, customer=None, **kwargs):
            return {"state": "HITL", "context_id": "RFQ-M0-CLARIFY",
                    "verification_status": "CLARIFY", "reasons": ["missing material"]}

    eml = tmp_root / "data" / "mailbox" / "M-CLARIFY-1.eml"
    eml.parent.mkdir(parents=True, exist_ok=True)
    eml.write_bytes(
        b"From: alice@northwind.com\r\nTo: sales@union-mfg.com\r\n"
        b"Subject: RFQ 6061 brackets\r\n\r\nNeed quote 50 pcs 6061\r\n")
    meta = eml.parent / "M-CLARIFY-1.meta.json"
    meta.write_text(json.dumps({"from": "alice@northwind.com",
                                "subject": "RFQ 6061 brackets",
                                "received_at": time.time(), "badges": ["NEW"],
                                "source": "test"}), encoding="utf-8")
    puller = MailPuller(root=tmp_root, interval_s=0.5, limit=10, mailbox_factory=None)
    orch = MailOrchestrator(root=tmp_root, puller=puller, cat=MockCAT(), notifier=None)
    puller._append_pending([PendingEntry(mail_id="M-CLARIFY-1", state=STATE_NEW)])
    r = orch.run_pipeline("M-CLARIFY-1")
    assert r.ok is True, f"pipeline 不应失败: {r.state} {r.reason}"
    assert r.state == "HITL", f"CLARIFY 须落 HITL 桶, 实际 {r.state}"
    assert r.quoted is False
    audit_path = tmp_root / "data" / "skill_audit.jsonl"
    lines = [json.loads(l) for l in audit_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    done = [l for l in lines if l.get("event") == "pipeline_done"][0]
    assert done["payload"]["clarified"] is False  # tmp_root 无 policy/context → 澄清跳过, 不外发


def _write_context(tmp_root: Path, cid: str, decision: Dict[str, Any],
                   quote: Optional[Dict[str, Any]] = None) -> None:
    p = tmp_root / "data" / "contexts" / f"{cid}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "context_id": cid,
        "decision": decision,
        "commercial": {"quote": quote or {}},
        "rfq": {"material": "6061", "quantity": 4},
        "geometry": {"features_count": 3},
    }, ensure_ascii=False), encoding="utf-8")


def _make_auto_orch(tmp_root: Path) -> Any:
    from services.mail_puller import MailPuller
    from services.mail_orchestrator import MailOrchestrator

    class _NeverRun:
        def run(self, *a, **k):  # pragma: no cover - 不应被调用
            raise AssertionError("CAT 不应在本类用例中被调用")

    puller = MailPuller(root=tmp_root, interval_s=0.5, limit=10, mailbox_factory=None)
    return MailOrchestrator(root=tmp_root, puller=puller, cat=_NeverRun(), notifier=None)


def test_auto_clarify_rejects_price_leak(tmp_root: Path, monkeypatch) -> None:
    monkeypatch.setattr("services.config.load_policy", lambda root=None: QUOTE_GATE_POLICY)
    orch = _make_auto_orch(tmp_root)
    _write_context(tmp_root, "RFQ-M0-LEAK", {"status": "HITL", "reply": {
        "mode": "auto_clarify", "auto_send": True,
        "subject": "Re: RFQ", "body": "we can offer 6061 at CNY 118.94 per pc"}})
    sent = []
    monkeypatch.setattr("services.reply_sender.send_quote_reply",
                        lambda **kw: sent.append(kw) or {"attachments": [], "from_addr": "a@b.c"})
    ok = orch._try_auto_clarify("M-LEAK-1", "RFQ-M0-LEAK", {}, {"from": "c@x.com"})
    assert ok is False and sent == []
    audit = [json.loads(l) for l in
             (tmp_root / "data" / "skill_audit.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert any(l.get("event") == "auto_clarify_rejected" and l["payload"]["reason"] == "price_leak"
               for l in audit)


def test_auto_clarify_passes_when_gates_ok(tmp_root: Path, monkeypatch) -> None:
    monkeypatch.setattr("services.config.load_policy", lambda root=None: QUOTE_GATE_POLICY)
    orch = _make_auto_orch(tmp_root)
    _write_context(tmp_root, "RFQ-M0-OK", {"status": "HITL", "reply": {
        "mode": "auto_clarify", "auto_send": True,
        "subject": "Re: RFQ", "body": "To prepare a firm quotation we need material and dimensions."}})
    sent = []
    monkeypatch.setattr("services.reply_sender.send_quote_reply",
                        lambda **kw: sent.append(kw) or {"attachments": [], "from_addr": "a@b.c"})
    ok = orch._try_auto_clarify("M-OK-1", "RFQ-M0-OK", {}, {"from": "cust@x.com"})
    assert ok is True
    assert len(sent) == 1 and sent[0]["quote"] is None and sent[0]["attachments"] == []
    assert (tmp_root / "data" / "auto_clarify_cooldown.json").exists()


def test_auto_clarify_cooldown_blocks_second_send(tmp_root: Path, monkeypatch) -> None:
    monkeypatch.setattr("services.config.load_policy", lambda root=None: QUOTE_GATE_POLICY)
    orch = _make_auto_orch(tmp_root)
    _write_context(tmp_root, "RFQ-M0-CD", {"status": "HITL", "reply": {
        "mode": "auto_clarify", "auto_send": True, "subject": "Re", "body": "need more details"}})
    monkeypatch.setattr("services.reply_sender.send_quote_reply",
                        lambda **kw: {"attachments": [], "from_addr": "a@b.c"})
    assert orch._try_auto_clarify("M-CD-1", "RFQ-M0-CD", {}, {"from": "cust@x.com"}) is True
    assert orch._try_auto_clarify("M-CD-2", "RFQ-M0-CD-2", {}, {"from": "cust@x.com"}) is False


def test_auto_quote_skips_non_pass(tmp_root: Path, monkeypatch) -> None:
    monkeypatch.setattr("services.config.load_policy", lambda root=None: QUOTE_GATE_POLICY)
    orch = _make_auto_orch(tmp_root)
    _write_context(tmp_root, "RFQ-M0-HITL", {"status": "HITL", "reply": {
        "mode": "draft_only", "body": "Unit price: CNY 100.0 | Total: CNY 200.0"}},
        quote={"unit_price": 100.0, "final_price": 200.0})
    assert orch._try_auto_quote("M-Q-1", "RFQ-M0-HITL", {}, {"from": "cust@x.com"}) is False


def test_auto_quote_rejects_price_not_in_body(tmp_root: Path, monkeypatch) -> None:
    monkeypatch.setattr("services.config.load_policy", lambda root=None: QUOTE_GATE_POLICY)
    orch = _make_auto_orch(tmp_root)
    _write_context(tmp_root, "RFQ-M0-PRICE", {"status": "PASS", "reply": {
        "mode": "draft_only", "subject": "Quote",
        "body": "Dear customer, please find our quotation attached."}},
        quote={"unit_price": 281.25, "final_price": 570.81, "currency": "CNY"})
    sent = []
    monkeypatch.setattr("services.reply_sender.send_quote_reply",
                        lambda **kw: sent.append(kw) or {"attachments": []})
    ok = orch._try_auto_quote("M-Q-2", "RFQ-M0-PRICE", {}, {"from": "cust@x.com"})
    assert ok is False and sent == []
    audit = [json.loads(l) for l in
             (tmp_root / "data" / "skill_audit.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert any(l.get("event") == "auto_quote_rejected" and l["payload"]["reason"] == "price_not_in_body"
               for l in audit)


def test_auto_quote_idempotent_per_context(tmp_root: Path, monkeypatch) -> None:
    monkeypatch.setattr("services.config.load_policy", lambda root=None: QUOTE_GATE_POLICY)
    orch = _make_auto_orch(tmp_root)
    _write_context(tmp_root, "RFQ-M0-IDEM", {"status": "PASS", "reply": {
        "mode": "draft_only", "subject": "Quote",
        "body": "Unit price: CNY 281.25 | Total: CNY 570.81"}},
        quote={"unit_price": 281.25, "final_price": 570.81, "currency": "CNY", "process": "三轴CNC"})
    store = tmp_root / "data" / "auto_quote_sent.json"
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps({"RFQ-M0-IDEM": {"to": "cust@x.com", "sent_at": time.time()}}),
                     encoding="utf-8")
    sent = []
    monkeypatch.setattr("services.reply_sender.send_quote_reply",
                        lambda **kw: sent.append(kw) or {"attachments": []})
    ok = orch._try_auto_quote("M-Q-3", "RFQ-M0-IDEM", {}, {"from": "cust@x.com"})
    assert ok is False and sent == []


def test_auto_quote_self_send_guard(tmp_root: Path, monkeypatch) -> None:
    monkeypatch.setattr("services.config.load_policy", lambda root=None: QUOTE_GATE_POLICY)
    monkeypatch.setattr("services.credentials.load_credentials",
                        lambda service=None: {"account": "self@union-mfg.com"})
    monkeypatch.setattr("services.reply_sender._mailbox_service", lambda: "qq")
    orch = _make_auto_orch(tmp_root)
    _write_context(tmp_root, "RFQ-M0-SELF", {"status": "PASS", "reply": {
        "mode": "draft_only", "subject": "Quote",
        "body": "Unit price: CNY 281.25 | Total: CNY 570.81"}},
        quote={"unit_price": 281.25, "final_price": 570.81, "currency": "CNY"})
    sent = []
    monkeypatch.setattr("services.reply_sender.send_quote_reply",
                        lambda **kw: sent.append(kw) or {"attachments": []})
    ok = orch._try_auto_quote("M-Q-4", "RFQ-M0-SELF", {}, {"from": "self@union-mfg.com"})
    assert ok is False and sent == []


def test_auto_quote_happy_path_sends(tmp_root: Path, monkeypatch) -> None:
    monkeypatch.setattr("services.config.load_policy", lambda root=None: QUOTE_GATE_POLICY)
    monkeypatch.setattr("services.credentials.load_credentials", lambda service=None: {})
    monkeypatch.setattr("services.reply_sender._mailbox_service", lambda: "qq")
    orch = _make_auto_orch(tmp_root)
    _write_context(tmp_root, "RFQ-M0-SEND", {"status": "PASS", "reply": {
        "mode": "draft_only", "subject": "Quotation RFQ-M0-SEND — 6061 4 pcs",
        "body": "Unit price: CNY 281.25 | Total: CNY 570.81 | Lead time: 15 days.",
        "guardrail_output": {"pass": True, "flags": []}, "attachments": []}},
        quote={"unit_price": 281.25, "final_price": 570.81, "currency": "CNY",
               "process": "三轴CNC", "lead_time_days": 15})
    sent = []
    monkeypatch.setattr("services.reply_sender.send_quote_reply",
                        lambda **kw: sent.append(kw) or {"attachments": [], "from_addr": "s@union-mfg.com"})
    ok = orch._try_auto_quote("M-Q-5", "RFQ-M0-SEND", {}, {"from": "cust@x.com",
                                                          "customer": {"contact_name": "Cust"}})
    assert ok is True
    assert len(sent) == 1 and sent[0]["cid"] == "RFQ-M0-SEND"
    store = json.loads((tmp_root / "data" / "auto_quote_sent.json").read_text(encoding="utf-8"))
    assert "RFQ-M0-SEND" in store
    audit = [json.loads(l) for l in
             (tmp_root / "data" / "skill_audit.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert any(l.get("event") == "auto_quote_sent" and l["payload"]["context_id"] == "RFQ-M0-SEND"
               for l in audit)


# ---------- 6. config/policy.yaml 段 ----------

def test_policy_yaml_quote_gate_sections() -> None:
    p = load_policy(ROOT)
    qg = p.get("quote_gate") or {}
    assert qg.get("enabled") is True
    assert qg.get("blocking_fields") == ["material", "quantity", "dimensions"]
    assert (qg.get("defaultable") or {}).get("surface_finish") == "无"
    assert (qg.get("defaultable") or {}).get("tolerance") == "IT8"
    assert qg.get("auto_clarify_enabled") is True
    assert qg.get("auto_quote_send_enabled") is True
    assert (p.get("oversize") or {}).get("max_dim_hitl_mm") == 500.0
    assert ((p.get("multimodal") or {}).get("size_conflict_ratio")) == 2.0
    assert (p.get("auto_quote_threshold") or {}).get("features_count_max") is not None
