"""write_reply — 英文回复草稿 (draft_only, 不定最终数字承诺)."""
from __future__ import annotations

from typing import Any, Dict


def run(ctx, use_llm: bool = False, **kwargs) -> Dict[str, Any]:
    rfq = ctx.scratch.get("rfq") or {}
    verification = ctx.scratch.get("verification") or {}
    quote = ctx.scratch.get("quote") or {}
    from services.reply import build_reply
    ctx_dict = {
        "rfq": rfq,
        "quote": quote,
        "verification_status": verification.get("verification_status", "PASS"),
        "reasons": verification.get("reasons") or [],
    }
    try:
        out = build_reply(ctx_dict, verification.get("raw") or verification)
    except Exception as e:  # noqa
        return {"ok": False, "skill": "write_reply", "error": repr(e)}
    # G2 (v6.3.1): 报价 PDF 附件 (draft_only; reportlab 缺库显式降级, 不炸链)
    try:
        from services.quote_pdf import attach_quote_pdf
        attach_quote_pdf(out, quote=quote,
                         context_id=ctx.scratch.get("context_id")
                         or ctx_dict.get("context_id") or "",
                         customer=ctx.scratch.get("customer") or {},
                         rfq=rfq)
    except Exception as e:  # noqa
        out["attachments"] = []
        out["attachment_error"] = repr(e)
    subject = out.get("subject") or out.get("title") or ""
    body = out.get("body") or out.get("text") or str(out)
    source = "template:services.reply"
    if use_llm:
        planner = ctx.planner
        if planner is None:
            try:
                planner = ctx.get_ctrl().planner
            except Exception:
                planner = None
        if planner is not None and getattr(planner, "online", lambda: False)():
            lr = planner.draft_reply(ctx_dict)
            data = lr.get("data") if isinstance(lr, dict) else None
            if isinstance(data, dict) and (data.get("body") or data.get("text")):
                body = data.get("body") or data.get("text")
                subject = data.get("subject") or subject
                source = lr.get("_source", "live:llm")
            else:
                source = f"{source}|llm_miss:{lr.get('_source') if isinstance(lr, dict) else 'n/a'}"
        else:
            source = f"{source}|MOCK:llm-offline"
    result = {
        "ok": True,
        "skill": "write_reply",
        "iron_rule": "draft_only",
        "draft_only": True,
        "subject": subject,
        "body": body,
        "reply": body,
        "attachments": out.get("attachments") or [],
        "_source": source,
    }
    if out.get("attachment_error"):
        result["attachment_error"] = out["attachment_error"]
    ctx.scratch["reply"] = result
    return result
