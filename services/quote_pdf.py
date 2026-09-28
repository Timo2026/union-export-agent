"""services.quote_pdf — G2 (v6.3.1): 报价单 PDF 附件闭环.

对照 rfq-quote-agent 核心交付物: 确定性引擎报价渲染成 PDF, 随草稿/审批流转。

铁律:
  - PDF 只反映确定性引擎产出的事实 (material/qty/price/lead time 原样排版, 不重算);
  - 附件只进草稿, 永不自动外发 (draft_only; egress 默认 DENY 不变);
  - content_sha256 锁"报价事实" (canonical json), 不锁 PDF 字节 — reportlab 元数据含时间戳;
  - reportlab 为可选依赖: 缺库 → 显式降级 (attachment_error=reportlab_not_installed), 不炸链。
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ARTIFACTS_DIR = _ROOT / "data" / "artifacts"

_FONT_NAME = "Helvetica"
_font_tried = False


def _reportlab_available() -> bool:
    try:
        import reportlab  # noqa: F401
        return True
    except Exception:
        return False


def _register_cjk_font() -> str:
    """优先注册 CJK 字体 (报价单常含中文表面处理/材料); 失败回退 Helvetica."""
    global _FONT_NAME, _font_tried
    if _font_tried:
        return _FONT_NAME
    _font_tried = True
    try:
        from reportlab.pdfbase import cidfonts
        from reportlab.pdfbase import pdfmetrics
        pdfmetrics.registerFont(cidfonts.UnicodeCIDFont("STSong-Light"))
        _FONT_NAME = "STSong-Light"
    except Exception:
        _FONT_NAME = "Helvetica"
    return _FONT_NAME


def _canon(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)


def _has_price(quote: Dict[str, Any]) -> bool:
    return any(quote.get(k) is not None for k in ("unit_price", "final_price", "total_price"))


def _content_payload(context_id: str, quote: Dict[str, Any], customer: Dict[str, Any],
                     rfq: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "context_id": context_id,
        "customer": customer.get("name") or customer.get("contact_name") or "",
        "material": rfq.get("material", ""),
        "quantity": rfq.get("quantity", ""),
        "surface": rfq.get("surface") or "",
        "tolerance_grade": rfq.get("tolerance_grade") or "",
        "unit_price": quote.get("unit_price"),
        "final_price": quote.get("final_price") or quote.get("total_price"),
        "currency": quote.get("currency", "CNY"),
        "lead_time_days": quote.get("lead_time_days"),
        "engine_source": quote.get("_source", "deterministic engine"),
    }


def render_quote_pdf(
    quote: Dict[str, Any],
    context_id: str,
    out_dir: Optional[Path] = None,
    customer: Optional[Dict[str, Any]] = None,
    rfq: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """渲染报价 PDF → out_dir/{context_id}/quote-{context_id}-{sha8}.pdf.

    返回:
      ok=True  → {"ok", "path", "content_sha256", "pdf_sha256", "context_id"}
      ok=False → {"ok": False, "reason": "no_price" | "reportlab_not_installed", "context_id"}
    """
    out_dir = Path(out_dir) if out_dir else DEFAULT_ARTIFACTS_DIR
    quote = quote or {}
    customer = customer or {}
    rfq = rfq or {}

    if not _has_price(quote):
        return {"ok": False, "reason": "no_price", "context_id": context_id}
    if not _reportlab_available():
        return {"ok": False, "reason": "reportlab_not_installed", "context_id": context_id}

    payload = _content_payload(context_id, quote, customer, rfq)
    content_sha = hashlib.sha256(_canon(payload).encode("utf-8")).hexdigest()

    target_dir = out_dir / context_id
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"quote-{context_id}-{content_sha[:8]}.pdf"

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                        TableStyle)

        font = _register_cjk_font()
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle("QuoteTitle", parent=styles["Title"], fontName=font,
                                     fontSize=16, spaceAfter=6)
        meta_style = ParagraphStyle("QuoteMeta", parent=styles["Normal"], fontName=font,
                                    fontSize=9, textColor=colors.HexColor("#444444"))
        warn_style = ParagraphStyle("QuoteWarn", parent=styles["Normal"], fontName=font,
                                    fontSize=9, textColor=colors.HexColor("#b91c1c"))

        story = [
            Paragraph(f"Quotation {context_id} — DRAFT", title_style),
            Paragraph(f"Customer: {payload['customer'] or 'N/A'} · "
                      f"Material: {payload['material'] or 'N/A'} · "
                      f"Qty: {payload['quantity'] or 'N/A'}", meta_style),
            Paragraph(f"Surface: {payload['surface'] or 'as-machined'} · "
                      f"Tolerance: {payload['tolerance_grade'] or 'standard'}", meta_style),
            Spacer(1, 6 * mm),
        ]

        cur = payload["currency"] or "CNY"
        rows = [["Description", "Qty", f"Unit ({cur})", f"Total ({cur})"]]
        desc = f"{payload['material'] or 'Part'} ({payload['surface'] or 'as-machined'}, " \
               f"{payload['tolerance_grade'] or 'standard'})"
        rows.append([desc, str(payload["quantity"] or "-"),
                     str(payload["unit_price"] if payload["unit_price"] is not None else "-"),
                     str(payload["final_price"] if payload["final_price"] is not None else "-")])
        tbl = Table(rows, colWidths=[80 * mm, 20 * mm, 30 * mm, 30 * mm])
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(
            f"Lead time: {payload['lead_time_days'] or 'TBD'} days · "
            f"Engine: {payload['engine_source']}", meta_style))
        story.append(Paragraph(
            f"Content lock: sha256:{content_sha[:16]}…", meta_style))
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(
            "DRAFT ONLY — generated by the deterministic manufacturing engine; "
            "valid 14 days, subject to final drawing confirmation. "
            "This attachment is never auto-sent (iron rule 1).", warn_style))

        doc = SimpleDocTemplate(str(path), pagesize=A4,
                                title=f"Quotation {context_id} (DRAFT)",
                                author="Union Export Agent")
        doc.build(story)
    except Exception as e:
        log.exception("[quote-pdf] render failed for %s: %r", context_id, e)
        return {"ok": False, "reason": f"render_failed: {e!r}", "context_id": context_id}

    pdf_bytes = path.read_bytes()
    return {
        "ok": True,
        "path": str(path),
        "content_sha256": content_sha,
        "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "bytes": len(pdf_bytes),
        "context_id": context_id,
    }


def attach_quote_pdf(
    draft: Dict[str, Any],
    quote: Dict[str, Any],
    context_id: str,
    customer: Optional[Dict[str, Any]] = None,
    rfq: Optional[Dict[str, Any]] = None,
    out_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """把报价 PDF 作为附件挂到回复草稿 (draft_only 不变).

    - 渲染成功 → draft["attachments"] = [{kind: quote_pdf, path, shas, draft_only: True}]
    - 无价格   → attachments = [] (正常无附件, 不记 error)
    - 缺依赖   → attachments = [] + attachment_error = reportlab_not_installed (显式降级)
    """
    r = render_quote_pdf(quote, context_id, out_dir=out_dir, customer=customer, rfq=rfq)
    if r.get("ok"):
        draft["attachments"] = [{
            "kind": "quote_pdf",
            "path": r["path"],
            "content_sha256": r["content_sha256"],
            "pdf_sha256": r["pdf_sha256"],
            "draft_only": True,
        }]
        draft["attachment_error"] = None
    else:
        draft["attachments"] = []
        if r.get("reason") != "no_price":
            draft["attachment_error"] = r.get("reason")
    return draft
