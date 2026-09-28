"""orders_store.py — 独立订单实体存储 (v7.0 工作台重设计).

data/orders.json 单文件 JSON 存储 (原子写), 外贸订单状态机:
  inquiry(询盘) → quote(报价) → sample(样品) → batch(批量) → shipped(发货) → closed(完结)
  任一在途状态可 → lost(丢单); closed/lost 为终态。
非法状态迁移由 API 层拦截为 409。
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = _ROOT / "data" / "orders.json"

STATUSES = ["inquiry", "quote", "sample", "batch", "shipped", "closed", "lost"]
STATUS_ZH = {
    "inquiry": "询盘", "quote": "报价", "sample": "样品", "batch": "批量",
    "shipped": "发货", "closed": "完结", "lost": "丢单",
}
TRANSITIONS: Dict[str, set] = {
    "inquiry": {"quote", "lost"},
    "quote": {"sample", "lost"},
    "sample": {"batch", "lost"},
    "batch": {"shipped", "closed", "lost"},
    "shipped": {"closed"},
    "closed": set(),
    "lost": set(),
}

_LOCK = threading.Lock()


def can_transition(frm: str, to: str) -> bool:
    return to in TRANSITIONS.get(frm, set())


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def load() -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    try:
        data = json.loads(DB_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    orders = data.get("orders", [])
    return orders if isinstance(orders, list) else []


def _save(orders: List[Dict[str, Any]]) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DB_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"orders": orders, "updated_at": _now()},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    for attempt in range(5):  # Windows: 目标文件可能被杀软/服务瞬时占用, 重试后仍败才抛
        try:
            os.replace(tmp, DB_PATH)
            return
        except PermissionError:
            time.sleep(0.1 * (attempt + 1))
    os.replace(tmp, DB_PATH)


def _new_id(orders: List[Dict[str, Any]]) -> str:
    day = time.strftime("%Y%m%d")
    n = sum(1 for o in orders if str(o.get("id", "")).startswith(f"ORD-{day}-")) + 1
    while any(o.get("id") == f"ORD-{day}-{n:03d}" for o in orders):
        n += 1
    return f"ORD-{day}-{n:03d}"


EDITABLE_FIELDS = {"customer_id", "customer_name", "title", "quantity",
                   "amount_usd", "currency", "drawing_sha", "context_id", "note"}

# 引擎专属字段 (铁律①): 只能经 apply_quote 写入, 手工 PATCH 覆写不了
QUOTE_FIELDS = ("unit_price", "quote_source", "quote_sha16", "quoted_at")


def create(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not str(payload.get("customer_name") or payload.get("customer_id") or "").strip():
        raise ValueError("customer_id / customer_name 至少填一项")
    status = payload.get("status", "inquiry")
    if status not in STATUSES:
        raise ValueError(f"未知状态: {status}")
    order = {
        "id": _new_id(load()),
        "customer_id": payload.get("customer_id", ""),
        "customer_name": payload.get("customer_name", payload.get("customer_id", "")),
        "title": payload.get("title", "未命名订单"),
        "status": status,
        "quantity": int(payload.get("quantity") or 1),
        "amount_usd": float(payload.get("amount_usd") or 0.0),
        "currency": payload.get("currency", "USD"),
        "drawing_sha": payload.get("drawing_sha"),
        "context_id": payload.get("context_id"),
        "source": payload.get("source", "manual"),
        "note": payload.get("note", ""),
        "history": [{"ts": _now(), "action": "create", "status": status,
                     "by": payload.get("source", "manual")}],
        "created_at": _now(),
        "updated_at": _now(),
    }
    with _LOCK:
        orders = load()
        order["id"] = _new_id(orders)
        orders.insert(0, order)
        _save(orders)
    return order


def get(order_id: str) -> Optional[Dict[str, Any]]:
    for o in load():
        if o.get("id") == order_id:
            return o
    return None


def _match(o: Dict[str, Any], status: str, customer: str, q: str) -> bool:
    if status:
        want = {s.strip() for s in status.split(",") if s.strip()}
        if o.get("status") not in want:
            return False
    if customer:
        c = customer.lower()
        if c not in str(o.get("customer_id", "")).lower() \
                and c not in str(o.get("customer_name", "")).lower():
            return False
    if q:
        k = q.lower()
        blob = " ".join(str(o.get(f, "")) for f in
                        ("id", "title", "customer_id", "customer_name", "context_id",
                         "drawing_sha", "note")).lower()
        if k not in blob:
            return False
    return True


def _sort_key(v: Any) -> Tuple[int, float, str]:
    """排序键归一: 数值 epoch / ISO 字符串 → 同一量纲 float; 其余字符串 rank1; None 垫底."""
    if v is None:
        return (2, 0.0, "")
    if isinstance(v, (int, float)):
        return (0, float(v), "")
    s = str(v)
    try:
        return (0, datetime.fromisoformat(s).timestamp(), "")
    except ValueError:
        return (1, 0.0, s)


def list_orders(status: str = "", customer: str = "", q: str = "",
                page: int = 1, size: int = 20, sort: str = "-created_at"
                ) -> Dict[str, Any]:
    items = [o for o in load() if _match(o, status, customer, q)]
    reverse = sort.startswith("-")
    key = sort.lstrip("-+") or "created_at"
    items.sort(key=lambda o: _sort_key(o.get(key)), reverse=reverse)
    total = len(items)
    pages = max(1, (total + size - 1) // size)
    page = min(max(1, page), pages)
    return {"items": items[(page - 1) * size: page * size], "total": total,
            "page": page, "size": size, "pages": pages,
            "statuses": STATUSES, "status_zh": STATUS_ZH}


def transition(order_id: str, to_status: str, by: str = "ui") -> Dict[str, Any]:
    """单订单状态迁移; 返回 {"ok":True,...} 或抛 ValueError(404/409 语义由 API 层翻译)。"""
    with _LOCK:
        orders = load()
        o = next((x for x in orders if x.get("id") == order_id), None)
        if o is None:
            raise KeyError(order_id)
        frm = o.get("status", "inquiry")
        if to_status not in STATUSES:
            raise ValueError(f"未知状态: {to_status}")
        if not can_transition(frm, to_status):
            raise ValueError(f"非法流转: {frm} → {to_status}")
        o["status"] = to_status
        o["updated_at"] = _now()
        o.setdefault("history", []).append(
            {"ts": _now(), "action": "transition", "from": frm, "to": to_status, "by": by})
        _save(orders)
        return o


def update_fields(order_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    with _LOCK:
        orders = load()
        o = next((x for x in orders if x.get("id") == order_id), None)
        if o is None:
            raise KeyError(order_id)
        for k, v in patch.items():
            if k in EDITABLE_FIELDS and v is not None:
                o[k] = v
        o["updated_at"] = _now()
        o.setdefault("history", []).append(
            {"ts": _now(), "action": "edit", "fields": sorted(
                k for k in patch if k in EDITABLE_FIELDS and patch[k] is not None)})
        _save(orders)
        return o


def apply_quote(order_id: str, *, amount_usd: float, currency: str,
                unit_price: float, quote_source: str, quote_sha16: str,
                quoted_at: str = "") -> Dict[str, Any]:
    """引擎报价落单 (铁律①: 金额唯一权威 = Timo 引擎, 手工 PATCH 改不了溯源字段).

    写 amount_usd/currency + QUOTE_FIELDS 引擎字段 + history {action: auto_quote} 审计.
    订单不存在抛 KeyError (由 API 层翻 404).
    """
    quoted_at = quoted_at or _now()
    with _LOCK:
        orders = load()
        o = next((x for x in orders if x.get("id") == order_id), None)
        if o is None:
            raise KeyError(order_id)
        o["amount_usd"] = float(amount_usd or 0)
        o["currency"] = currency or "CNY"
        o["unit_price"] = float(unit_price or 0)
        o["quote_source"] = quote_source
        o["quote_sha16"] = quote_sha16
        o["quoted_at"] = quoted_at
        o["updated_at"] = _now()
        o.setdefault("history", []).append(
            {"ts": quoted_at, "action": "auto_quote", "amount_usd": o["amount_usd"],
             "quote_source": quote_source, "quote_sha16": quote_sha16, "by": "engine"})
        _save(orders)
        return o


def delete(order_id: str) -> bool:
    with _LOCK:
        orders = load()
        rest = [o for o in orders if o.get("id") != order_id]
        if len(rest) == len(orders):
            return False
        _save(rest)
        return True


def bulk_transition(ids: List[str], to_status: str, by: str = "bulk"
                    ) -> Dict[str, Any]:
    ok: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    for oid in ids:
        try:
            o = transition(oid, to_status, by=by)
            ok.append({"id": oid, "status": o["status"]})
        except KeyError:
            failed.append({"id": oid, "reason": "not_found"})
        except ValueError as e:
            failed.append({"id": oid, "reason": str(e)})
    return {"ok": ok, "failed": failed}


def new_order_id() -> str:  # 供测试/种子脚本预生成 (非必须路径)
    return f"ORD-SEED-{uuid.uuid4().hex[:8]}"
