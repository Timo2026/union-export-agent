"""tests/test_reply_attachment.py — G2/G2b 黄金链回复挂报价单附件.

客户诉求: "完成报价后, 回传给我报价模板.XSLX, PDF都可以行" —
黄金链 reply 必须带 PDF+XLSX 附件 (draft_only 铁律不变, 缺库显式降级)。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from bootstrap import build_controller


@pytest.fixture(scope="module")
def ctrl(require_engine):
    c = build_controller()
    yield c
    if c.crm is not None:
        c.crm.close()


def test_golden_chain_reply_carries_pdf_and_xlsx(ctrl, tmp_path, monkeypatch):
    """PASS 路径: 持久化 decision.reply 带 quote_pdf + quote_xlsx, 文件落盘, draft_only 不变."""
    import json

    import services.quote_pdf as qp
    import services.quote_xlsx as qx
    monkeypatch.setattr(qp, "DEFAULT_ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(qx, "DEFAULT_ARTIFACTS_DIR", tmp_path)

    r = ctrl.run(
        email_text="请报价: 铝合金6061 工件 100 件, 尺寸50x30x10mm, 阳极氧化, 公差IT7",
        customer={"name": "Acme", "email": "buyer@acme.cn"},
    )
    cid = r["context_id"]
    if r["verification_status"] != "PASS":
        pytest.skip(f"scenario status={r['verification_status']} (引擎离线口径)")
    # 铁律不变 (汇总层)
    assert r["reply"]["auto_send"] is False and r["reply"]["mode"] == "draft_only"
    # 全文 reply 落盘在 context decision 里
    ctx_path = Path("data") / "contexts" / f"{cid}.json"
    assert ctx_path.exists()
    reply = json.loads(ctx_path.read_text(encoding="utf-8"))["decision"]["reply"]
    kinds = [a["kind"] for a in reply.get("attachments") or []]
    assert "quote_pdf" in kinds and "quote_xlsx" in kinds
    for a in reply["attachments"]:
        assert a["draft_only"] is True
        assert Path(a["path"]).exists()
        # content lock 与 context 绑定
        assert cid in Path(a["path"]).name
    # 附件路径按 context 隔离
    assert (tmp_path / cid).is_dir()


def test_reply_summary_exposes_attachment_count(ctrl, tmp_path, monkeypatch):
    """out['reply'] 汇总带附件计数 (前端/端点无需解析全文)."""
    import services.quote_pdf as qp
    import services.quote_xlsx as qx
    monkeypatch.setattr(qp, "DEFAULT_ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(qx, "DEFAULT_ARTIFACTS_DIR", tmp_path)

    r = ctrl.run(
        email_text="请报价: 铝合金6061 工件 100 件, 尺寸50x30x10mm, 阳极氧化, 公差IT7",
        customer={"name": "Acme", "email": "buyer@acme.cn"},
    )
    if r["verification_status"] != "PASS":
        pytest.skip(f"scenario status={r['verification_status']} (引擎离线口径)")
    summary = r["reply"]
    assert summary["attachments_count"] == 2
    assert set(summary["attachment_kinds"]) == {"quote_pdf", "quote_xlsx"}
    assert summary["attachment_error"] is None


def test_no_price_no_attachment_no_error(ctrl, tmp_path, monkeypatch):
    """无报价 (BLOCKED) → attachments=[], 不记 attachment_error."""
    import services.quote_pdf as qp
    import services.quote_xlsx as qx
    monkeypatch.setattr(qp, "DEFAULT_ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(qx, "DEFAULT_ARTIFACTS_DIR", tmp_path)

    r = ctrl.run(
        email_text="请报价: 不锈钢304 工件 10 件, 阳极氧化处理",  # 304+阳极氧化 → BLOCKED
        customer={"name": "Acme"},
    )
    summary = r["reply"]
    assert summary["attachments_count"] == 0
    assert summary["attachment_kinds"] == []
    assert summary["attachment_error"] is None
    assert summary["auto_send"] is False
