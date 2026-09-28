"""tests/test_quote_pdf.py — G2 (v6.3.1): 报价单 PDF 附件闭环.

对照 rfq-quote-agent 核心交付物 (确定性引擎报价 → PDF 报价单随审批流转)。
铁律①: 附件只进草稿, 永不自动外发 (draft_only 不变); reportlab 缺库 → 显式降级不炸链。
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.quote_pdf import attach_quote_pdf, render_quote_pdf

QUOTE = {
    "unit_price": 128.5,
    "final_price": 12850.0,
    "total_price": 12850.0,
    "currency": "CNY",
    "lead_time_days": 12,
    "_source": "timo-engine-v12",
}

CTX_DICT = {
    "context_id": "RFQ-G2-1",
    "rfq": {"material": "6061", "quantity": 100, "surface": "as-machined",
            "tolerance_grade": "IT7"},
    "customer": {"name": "Acme", "email": "buyer@acme.cn"},
    "quote": QUOTE,
    "verification_status": "PASS",
}


def _sha_len_ok(s: str) -> bool:
    return isinstance(s, str) and len(s) == 64 and all(c in "0123456789abcdef" for c in s)


# ---- 1) 渲染 ----

def test_render_quote_pdf_ok(tmp_path):
    r = render_quote_pdf(QUOTE, context_id="RFQ-G2-1", out_dir=tmp_path,
                         customer={"name": "Acme"})
    assert r["ok"] is True, r
    p = Path(r["path"])
    assert p.exists() and p.stat().st_size > 0
    assert p.read_bytes()[:5] == b"%PDF-"
    assert "RFQ-G2-1" in p.name
    assert _sha_len_ok(r["content_sha256"]) and _sha_len_ok(r["pdf_sha256"])
    assert r["context_id"] == "RFQ-G2-1"


def test_render_deterministic_content_sha(tmp_path):
    r1 = render_quote_pdf(QUOTE, context_id="RFQ-G2-1", out_dir=tmp_path / "a")
    r2 = render_quote_pdf(QUOTE, context_id="RFQ-G2-1", out_dir=tmp_path / "b")
    assert r1["ok"] and r2["ok"]
    assert r1["content_sha256"] == r2["content_sha256"]  # 内容锁确定性


def test_render_no_price_returns_noop(tmp_path):
    r = render_quote_pdf({"currency": "CNY"}, context_id="RFQ-G2-2", out_dir=tmp_path)
    assert r["ok"] is False and r["reason"] == "no_price"
    assert not list(tmp_path.rglob("*.pdf"))


def test_render_missing_reportlab_graceful(tmp_path, monkeypatch):
    import services.quote_pdf as qp
    monkeypatch.setattr(qp, "_reportlab_available", lambda: False)
    r = render_quote_pdf(QUOTE, context_id="RFQ-G2-3", out_dir=tmp_path)
    assert r["ok"] is False and r["reason"] == "reportlab_not_installed"
    assert not list(tmp_path.rglob("*.pdf"))


# ---- 2) 草稿附件闭环 ----

def test_attach_quote_pdf_adds_attachment_to_draft(tmp_path):
    from services.reply import build_reply
    draft = build_reply(CTX_DICT, {"status": "PASS"})
    out = attach_quote_pdf(draft, quote=QUOTE, context_id="RFQ-G2-1",
                           customer={"name": "Acme"}, out_dir=tmp_path)
    atts = out["attachments"]
    assert len(atts) == 1
    a = atts[0]
    assert a["kind"] == "quote_pdf"
    assert a["draft_only"] is True          # 铁律①: 附件不自动外发
    assert Path(a["path"]).exists()
    assert _sha_len_ok(a["content_sha256"])
    # 草稿本体不被破坏
    assert draft["auto_send"] is False and draft["mode"] == "draft_only"
    assert out.get("attachment_error") is None


def test_attach_no_price_no_attachment(tmp_path):
    from services.reply import build_reply
    draft = build_reply({**CTX_DICT, "quote": {}}, {"status": "PASS"})
    out = attach_quote_pdf(draft, quote={}, context_id="RFQ-G2-4", out_dir=tmp_path)
    assert out["attachments"] == []
    assert out.get("attachment_error") is None


def test_attach_missing_reportlab_marks_error_on_draft(tmp_path, monkeypatch):
    import services.quote_pdf as qp
    monkeypatch.setattr(qp, "_reportlab_available", lambda: False)
    from services.reply import build_reply
    draft = build_reply(CTX_DICT, {"status": "PASS"})
    out = attach_quote_pdf(draft, quote=QUOTE, context_id="RFQ-G2-5", out_dir=tmp_path)
    assert out["attachments"] == []
    assert out["attachment_error"] == "reportlab_not_installed"
    assert draft["auto_send"] is False and draft["mode"] == "draft_only"  # 仍 draft_only


# ---- 3) skill 端到端 ----

def test_write_reply_skill_carries_attachment(tmp_path, monkeypatch):
    import importlib.util
    import services.quote_pdf as qp
    monkeypatch.setattr(qp, "DEFAULT_ARTIFACTS_DIR", tmp_path)
    tool_path = Path(__file__).resolve().parent.parent / "skills" / "write-reply" / "tool.py"
    spec = importlib.util.spec_from_file_location("_test_write_reply_tool", tool_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ctx = SimpleNamespace(
        scratch={
            "rfq": CTX_DICT["rfq"],
            "quote": QUOTE,
            "verification": {"verification_status": "PASS", "reasons": []},
            "context_id": "RFQ-G2-6",
            "customer": CTX_DICT["customer"],
        },
        planner=None,
        get_ctrl=lambda: SimpleNamespace(planner=None),
    )
    r = mod.run(ctx)
    assert r["ok"] is True and r["draft_only"] is True
    assert r["attachments"][0]["kind"] == "quote_pdf"
    assert Path(r["attachments"][0]["path"]).exists()
