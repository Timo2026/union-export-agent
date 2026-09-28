"""customer_api.py — /v1/customer 客户情报 (v7.0 工作台, 联网 + 本地画像).

  GET /v1/customer/enrich?name=<客户名/ID>&limit=5
    → {name, web:{hits,mock,_source,warning?}, profile:{matched,...}, generated_at}
    SearXNG 不可达时 web.mock=true 显式标注 (铁律: 不静默冒充), 本地画像仍返回。
  GET /v1/customer/matches?q=<关键词>   轻量本地模糊匹配 (供选择器)
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter

from services import web_search
from services.sandbox import CustomerSandbox, list_all_sandboxes

router = APIRouter(prefix="/v1/customer", tags=["customer"])

_CRM_DB = Path(__file__).resolve().parent.parent / "data" / "crm.sqlite3"


def _match_customers(kw: str) -> List[Dict[str, Any]]:
    kw = kw.lower().strip()
    out = []
    for c in list_all_sandboxes():
        cid = str(c.get("customer_id", ""))
        if not kw or kw in cid.lower():
            out.append(c)
    return out[:20]


def _crm_lookup(kw: str) -> List[Dict[str, Any]]:
    """真 CRM customers 表按名称/ID 反查 (ro 连接, 沙箱只有 id 匹配不到公司名)."""
    import sqlite3
    kw = (kw or "").strip().lower()
    if not kw:
        return []
    db = _CRM_DB
    if not db.exists():
        return []
    cols = ["customer_id", "name", "country", "lifecycle_state",
            "total_orders", "total_revenue", "health_score"]
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT customer_id,name,country,lifecycle_state,total_orders,"
            "total_revenue,health_score FROM customers "
            "WHERE lower(name) LIKE ? OR lower(customer_id)=? "
            "ORDER BY updated_at DESC LIMIT 3", (f"%{kw}%", kw)).fetchall()
        con.close()
    except Exception:
        return []
    return [dict(zip(cols, r)) for r in rows]


def _sandbox_summary(cid: str) -> Dict[str, Any]:
    try:
        sb = CustomerSandbox(cid)
        history = sb.get_history(limit=5)
        model = sb.get_pricing_model()
        sb.close()
        return {"pricing_model": model, "recent_quotes": history.get("quotes", [])}
    except Exception:
        return {"pricing_model": {}, "recent_quotes": []}


@router.get("/matches")
def customer_matches(q: str = "") -> Dict[str, Any]:
    return {"items": _match_customers(q)}


@router.get("/enrich")
def enrich(name: str, limit: int = 5) -> Dict[str, Any]:
    limit = max(1, min(limit, 10))
    web = web_search.search(f"{name} 机械加工 采购 CNC manufacturing company", num=limit)
    offline = str(web.get("_source", "")).startswith(("searxng-offline", "searxng-error"))
    web = {**web, "mock": bool(offline or not web.get("hits") and offline)}

    matched: List[Dict[str, Any]] = []
    seen = set()
    for crm in _crm_lookup(name):
        cid = crm["customer_id"]
        seen.add(cid)
        matched.append({**_sandbox_summary(cid), **crm})
    for c in _match_customers(name):
        cid = str(c.get("customer_id", ""))
        if cid and cid not in seen and len(matched) < 3:
            matched.append({**_sandbox_summary(cid), **c})
    return {"name": name, "web": web,
            "profile": {"matched": matched, "match_count": len(matched)},
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
