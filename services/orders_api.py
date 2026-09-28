"""orders_api.py — /v1/orders 订单端点 (v7.0 工作台重设计).

  GET    /v1/orders              列表: status(逗号多值)/customer/q/page/size/sort
  POST   /v1/orders              建单 (邮件台"转订单"带 context_id 即走此)
  GET    /v1/orders/{id}         详情
  PATCH  /v1/orders/{id}         改字段 和/或 状态迁移 (非法迁移 409)
  DELETE /v1/orders/{id}         删单
  POST   /v1/orders/bulk         批量: {ids, action: transition|delete, target_status}
  GET    /v1/orders/meta         状态机元数据 (前端渲染色签/可用流转)
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import orders_store as osx

router = APIRouter(prefix="/v1/orders", tags=["orders"])


class OrderQuoteError(Exception):
    def __init__(self, status: int, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason


class OrderCreate(BaseModel):
    customer_id: str = ""
    customer_name: str = ""
    title: str = "未命名订单"
    status: str = "inquiry"
    quantity: int = 1
    amount_usd: float = 0.0
    currency: str = "USD"
    drawing_sha: Optional[str] = None
    context_id: Optional[str] = None
    note: str = ""
    source: str = "manual"
    # 订单自动报价 (铁律①: 数字只来自引擎)
    auto_quote: bool = False
    material: str = ""
    surface: str = ""
    tolerance_grade: str = ""
    weight_kg: Optional[float] = None
    max_dim_mm: Optional[float] = None


class OrderPatch(BaseModel):
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    title: Optional[str] = None
    quantity: Optional[int] = None
    amount_usd: Optional[float] = None
    currency: Optional[str] = None
    drawing_sha: Optional[str] = None
    context_id: Optional[str] = None
    note: Optional[str] = None
    to_status: Optional[str] = None


class QuoteRequest(BaseModel):
    """POST /v1/orders/{id}/quote 入参 (模式 B 引擎直裁; 全空 = 模式 A 读 context)."""
    material: Optional[str] = None
    quantity: Optional[int] = None
    surface: Optional[str] = None
    tolerance_grade: Optional[str] = None
    weight_kg: Optional[float] = None
    max_dim_mm: Optional[float] = None


class BulkRequest(BaseModel):
    ids: List[str]
    action: str = "transition"
    target_status: Optional[str] = None


@router.get("/meta")
def orders_meta() -> Dict[str, Any]:
    return {"statuses": osx.STATUSES, "status_zh": osx.STATUS_ZH,
            "transitions": {k: sorted(v) for k, v in osx.TRANSITIONS.items()}}


@router.get("")
def list_orders(status: str = "", customer: str = "", q: str = "",
                page: int = 1, size: int = 20, sort: str = "-created_at"
                ) -> Dict[str, Any]:
    size = max(1, min(size, 200))
    page = max(1, page)
    return osx.list_orders(status=status, customer=customer, q=q,
                           page=page, size=size, sort=sort)


_QUOTE_PARAM_KEYS = ("material", "quantity", "surface", "tolerance_grade",
                     "weight_kg", "max_dim_mm")


def _sha16(core: Dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(core, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _run_order_quote(order: Dict[str, Any], params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """订单自动报价单点权威 (铁律①: 数字只来自引擎, LLM 不参与).

    模式 A (context): order.context_id → api_server._need(cid) 黄金链已产出的 quote.
    模式 B (params):  material 必填 → ctrl().timo.quote(canonical rfq) 引擎直裁.
    失败抛 OrderQuoteError (订单不动, 不写假数).
    """
    p = {k: v for k, v in (params or {}).items()
         if k in _QUOTE_PARAM_KEYS and v not in (None, "")}
    cid = order.get("context_id") or ""

    if not p.get("material") and cid:
        # ---- 模式 A: 读上下文已产出报价 ----
        import services.api_server as asrv
        ent = asrv._need(cid)  # 上下文不存在 → HTTPException 404 直接外抛
        result = ent["result"]
        quote = result.get("quote") or {}
        amount = float(quote.get("final_price") or quote.get("total_price") or 0)
        if amount <= 0:
            raise OrderQuoteError(
                409, f"context {cid} 无有效报价 (state={result.get('state')}) — "
                     "先跑黄金链 / BLOCKED 不可报价 / 或带 material 参数走引擎直裁")
        core = {k: quote[k] for k in ("final_price", "unit_price", "total_price", "currency")
                if quote.get(k) is not None}
        source = f"context:{cid}"
        unit = float(quote.get("unit_price") or 0)
        currency = quote.get("currency") or "CNY"
        rfq_quantity = (result.get("rfq") or {}).get("quantity")
    elif p.get("material"):
        # ---- 模式 B: 引擎直裁 (byte-identical) ----
        import services.api_server as asrv
        rfq: Dict[str, Any] = {
            "material": str(p["material"]),
            "quantity": int(p.get("quantity") or order.get("quantity") or 1),
            "surface": str(p.get("surface") or "无"),
            "tolerance": str(p.get("tolerance_grade") or "IT8"),
        }
        if p.get("weight_kg") is not None:
            rfq["weight_kg"] = float(p["weight_kg"])
        if p.get("max_dim_mm") is not None:
            rfq["max_dim_mm"] = float(p["max_dim_mm"])
        try:
            q = asrv.ctrl().timo.quote(rfq)
        except Exception as e:
            raise OrderQuoteError(
                502, f"引擎报价失败 (Timo 不可达/拒算): {e!r} — 订单金额未改动, 不写假数")
        amount = float(q.get("final_price") or q.get("total_price") or 0)
        if amount <= 0:
            raise OrderQuoteError(502, f"引擎未返回有效价格: {q!r}")
        core = {k: q[k] for k in ("final_price", "unit_price", "total_price", "currency")
                if q.get(k) is not None}
        source = q.get("_source") or "engine:unknown"
        unit = float(q.get("unit_price") or 0)
        currency = q.get("currency") or "CNY"
        rfq_quantity = rfq["quantity"]
    elif cid:
        raise OrderQuoteError(409, f"context {cid} 无有效报价 — 带 material 参数走引擎直裁")
    else:
        raise OrderQuoteError(400, "无 context_id 且无报价参数 (material 必填) — 无法自动报价")

    sha = _sha16(core)
    updated = osx.apply_quote(
        order["id"], amount_usd=amount, currency=currency, unit_price=unit,
        quote_source=source, quote_sha16=sha)
    return {"ok": True,
            "order": updated,
            "quote": {"amount_usd": amount, "unit_price": unit, "currency": currency,
                      "quote_source": source, "quote_sha16": sha,
                      "rfq_quantity": rfq_quantity}}


@router.post("")
def create_order(req: OrderCreate) -> Dict[str, Any]:
    try:
        order = osx.create(req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if req.auto_quote:
        # 建单即报价: 失败不阻断建单 (RFQ/订单实体仍在), 如实带 quote_error
        try:
            return _run_order_quote(order, req.model_dump(exclude_none=True))["order"]
        except (OrderQuoteError, HTTPException) as e:
            order["quote_error"] = getattr(e, "reason", None) or getattr(e, "detail", str(e))
            return order
    return order


@router.post("/{order_id}/quote")
def quote_order(order_id: str, req: Optional[QuoteRequest] = None) -> Dict[str, Any]:
    """订单自动报价 (铁律①): 无参读 context 已产出报价; 带 material 走引擎直裁.

    引擎失败 → 502 且订单金额不动 (不写假数); quote_* 字段手工 PATCH 覆写不了.
    """
    o = osx.get(order_id)
    if o is None:
        raise HTTPException(status_code=404, detail=f"订单不存在: {order_id}")
    try:
        return _run_order_quote(o, req.model_dump(exclude_none=True) if req else None)
    except OrderQuoteError as e:
        raise HTTPException(status_code=e.status, detail=e.reason)


@router.get("/{order_id}")
def get_order(order_id: str) -> Dict[str, Any]:
    o = osx.get(order_id)
    if o is None:
        raise HTTPException(status_code=404, detail=f"订单不存在: {order_id}")
    return o


@router.patch("/{order_id}")
def patch_order(order_id: str, req: OrderPatch) -> Dict[str, Any]:
    if osx.get(order_id) is None:
        raise HTTPException(status_code=404, detail=f"订单不存在: {order_id}")
    fields = {k: v for k, v in req.model_dump(exclude_none=True).items()
              if k != "to_status"}
    if fields:
        osx.update_fields(order_id, fields)
    if req.to_status:
        try:
            osx.transition(order_id, req.to_status)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
    return osx.get(order_id)


@router.delete("/{order_id}")
def delete_order(order_id: str) -> Dict[str, Any]:
    if not osx.delete(order_id):
        raise HTTPException(status_code=404, detail=f"订单不存在: {order_id}")
    return {"ok": True, "id": order_id}


@router.post("/bulk")
def bulk(req: BulkRequest) -> Dict[str, Any]:
    if not req.ids:
        raise HTTPException(status_code=400, detail="ids 为空")
    if req.action == "delete":
        done = [i for i in req.ids if osx.delete(i)]
        failed = [{"id": i, "reason": "not_found"} for i in req.ids if i not in done]
        return {"ok": [{"id": i} for i in done], "failed": failed}
    if req.action == "transition":
        if not req.target_status:
            raise HTTPException(status_code=400, detail="transition 需要 target_status")
        return osx.bulk_transition(req.ids, req.target_status)
    raise HTTPException(status_code=400, detail=f"未知批量动作: {req.action}")
