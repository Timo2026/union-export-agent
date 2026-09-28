"""reply.py — 英文回复草稿生成 (Sales Agent).

原则: 草稿只反映确定性引擎产出的事实 (报价/交期/冲突/替代方案);
LLM 不生成最终数字。默认 draft_only, 高风险不自动发送 (external_send policy)。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from services.profile import load_profile, sign_off


def build_reply(ctx_dict: Dict[str, Any], verification: Dict[str, Any],
                profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """生成英文回复草稿。profile 缺省 → load_profile() (data/profile.json);

    落款 = profile.sign_off (署名原样 / name+title 组 / 兜底串) — 不再硬编码。
    """
    prof_dict = profile if profile is not None else load_profile()
    sign = sign_off(prof_dict)
    rfq = ctx_dict.get("rfq", {})
    com = ctx_dict.get("commercial", {})
    quote = com.get("quote", com)
    cust = ctx_dict.get("customer", {})
    status = verification.get("status", "PASS")
    mat = rfq.get("material", "the requested material")
    qty = rfq.get("quantity", "the requested quantity")
    surf = rfq.get("surface") or "as-machined"
    tol = rfq.get("tolerance_grade") or "standard tolerance"
    name = cust.get("contact_name") or cust.get("name") or "there"

    unit = quote.get("unit_price")
    total = quote.get("final_price") or quote.get("total_price")
    lead = quote.get("lead_time_days")
    src = quote.get("_source", com.get("source", "deterministic engine"))

    if status == "BLOCKED":
        conflicts = ctx_dict.get("manufacturing", {}).get("dfm", {}).get("conflicts", [])
        ctext = "; ".join(c.get("message", str(c)) for c in conflicts) or "a manufacturing constraint"
        alt = _alternative(rfq, conflicts)
        subject = f"Re: RFQ {ctx_dict.get('context_id')} — process clarification needed"
        body = (
            f"Dear {name},\n\n"
            f"Thank you for your inquiry for {qty} pcs in {mat} with {surf}.\n\n"
            f"After DFM review we found a hard process conflict: {ctext}. "
            f"We therefore cannot quote this combination as specified.\n\n"
            f"{alt}\n\n"
            f"Could you confirm an alternative so we can proceed with a firm quotation?\n\n"
            f"Best regards,\n{sign}"
        )
        auto_send = False
    elif status == "HITL":
        reasons = "; ".join(verification.get("reasons", [])) or "requires internal review"
        subject = f"Re: RFQ {ctx_dict.get('context_id')} — under review"
        body = (
            f"Dear {name},\n\n"
            f"Thank you for your inquiry for {qty} pcs in {mat} ({surf}, {tol}).\n\n"
            f"Your request is currently under engineering/commercial review ({reasons}). "
            f"We will revert with a firm quotation shortly.\n\n"
            f"Best regards,\n{sign}"
        )
        # 苏格拉底五要素追问 (P0-C): 缺 RFQ 关键字段时, 按客户语种列出待补要素,
        # 让客户一次补全而非空等复核。无缺失则不加 (不给客户添噪)。仍 draft_only。
        socratic = _socratic_block(rfq, cust)
        if socratic:
            body += f"\n\n{socratic}"
        auto_send = False
    elif status == "CLARIFY":
        # v2.4.0 (2026-09-25 TIMO: "门禁太高, 降低"): 缺阻塞字段 → 无价澄清信, 可自动外发。
        # 铁律: 该分支绝不出现价格/报价附件 — 缺材料或尺寸时引擎给的只是默认值估算,
        # 先问齐要素再出 firm quote。只提客户已给的要素, 缺失项不写成占位符。
        try:
            from services.lang import L, detect_language
            lang = detect_language(text=rfq.get("raw_text") or "",
                                   email=cust.get("contact_name") or "",
                                   country=cust.get("country") or "")
            known = []
            if rfq.get("material"):
                known.append(f"material {rfq['material']}")
            if rfq.get("quantity") is not None:
                known.append(f"quantity {rfq['quantity']} pcs")
            if rfq.get("dimensions_mm"):
                known.append(f"dimensions {'x'.join(str(d) for d in rfq['dimensions_mm'])} mm")
            body = f"Dear {name},\n\n"
            body += ("Thank you for your inquiry (" + ", ".join(known) + ").\n\n"
                     if known else "Thank you for your inquiry.\n\n")
            socratic = _socratic_block(rfq, cust)
            body += (socratic + "\n\n" if socratic else
                     "To prepare a firm quotation we need a few more details.\n\n")
            body += f"Best regards,\n{sign}"
            subject = L("clarify_subject", lang).format(
                ctx=ctx_dict.get("context_id", ""))
        except Exception:
            subject = f"Re: RFQ {ctx_dict.get('context_id')} — clarification needed"
            body = (f"Dear {name},\n\nTo prepare a firm quotation we need a few more "
                    f"details.\n\nBest regards,\n{sign}")
        auto_send = True  # 无价澄清信可自动发; 真发送由 orchestrator 冷却窗口把关
    else:
        subject = f"Quotation {ctx_dict.get('context_id')} — {mat} {qty} pcs"
        # v2.5.0 (2026-09-26): 货币标注改为跟随引擎 currency。原硬编码 "USD/CNY"
        # 双币种并标, 与报价单渲染 (quote_pdf.py: currency 缺省 CNY) 自相矛盾 —
        # 自动外发时等于让客户自己挑币种, 是真实报价事故源 (客户按 USD 支付)。
        # 引擎未给 currency 时缺省 CNY (本仓库报价货币口径)。
        cur = (quote.get("currency") if isinstance(quote, dict) else None) or "CNY"
        price_line = (f"Unit price: {cur} {unit} | Total: {cur} {total} | Lead time: {lead} days."
                      if unit is not None else "Pricing to follow.")
        body = (
            f"Dear {name},\n\n"
            f"Thank you for your inquiry. We are pleased to quote as follows:\n\n"
            f"- Material: {mat}\n"
            f"- Quantity: {qty} pcs\n"
            f"- Surface finish: {surf}\n"
            f"- Tolerance: {tol}\n"
            f"- {price_line}\n\n"
            f"(Estimate produced by our deterministic manufacturing engine [{src}]; "
            f"valid 14 days, subject to final drawing confirmation.)\n\n"
            f"Best regards,\n{sign}"
        )
        auto_send = False  # 默认 draft_only

    return {
        "subject": subject, "body": body, "status": status,
        "auto_send": auto_send,
        "mode": "auto_clarify" if status == "CLARIFY" else "draft_only",
        "quote_source": src,
    }


def _socratic_block(rfq: Dict[str, Any], cust: Dict[str, Any]) -> str:
    """苏格拉底五要素追问块 (P0-C): 引擎产出 missing_information 时, 按客户语种
    列出待补要素, 让客户一次补全。无缺失返回 "" (不加噪)。纯确定性, 不调 LLM。"""
    try:
        from services.lang import L, detect_language, missing_to_elements
    except Exception:
        return ""
    elems = missing_to_elements(rfq.get("missing_information") or [])
    if not elems:
        return ""
    lang = detect_language(text=rfq.get("raw_text") or "",
                           email=cust.get("contact_name") or "",
                           country=cust.get("country") or "")
    lines = [L("clarify_intro", lang)] + [f"- {L(e, lang)}" for e in elems]
    lines.append(L("clarify_outro", lang))
    return "\n".join(lines)


def _alternative(rfq: Dict[str, Any], conflicts) -> str:
    mat = (rfq.get("material") or "").lower()
    surf = rfq.get("surface") or ""
    if mat in ("304", "316l") and "阳极氧化" in surf:
        return ("Suggested alternative: for stainless steel, passivation (钝化) or electropolishing "
                "provides corrosion protection; anodizing is not applicable to 304/316L.")
    if rfq.get("tolerance_grade", "").upper() in ("IT4", "IT5"):
        return ("Suggested alternative: relax tolerance to IT6/IT7 for standard CNC, "
                "or confirm grinding/wire-EDM if IT4/IT5 is critical (added cost & lead time).")
    if mat in ("6061", "7075") and "镀锌" in surf:
        return "Suggested alternative: for aluminum, anodizing or nickel plating is preferred over zinc plating."
    return "Please advise an adjusted specification and we will re-quote."
