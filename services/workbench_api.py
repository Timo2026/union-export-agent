"""workbench_api.py — B 端工作台专用聚合路由 (前端后台统一入口).

设计原则:
  - 复用现有 services, 不重写业务逻辑 (邮箱/RAG/模型/审计/订单状态机/STEP/搜索).
  - 禁止硬编码: 数据路径用 _ROOT 相对, 端口/URL 从 os.environ 或 services 内部默认读.
  - 空状态友好: 无数据返回 items=[] + total=0, 不抛 500.
  - 铁律①: 报价/价格相关操作走 Timo 确定性引擎 (services.model_router DETERMINISTIC 角色),
    不让 LLM 定价格.
  - 所有端点返回 JSONResponse, 函数加类型注解 + docstring 说明复用了哪个 service.

端点清单 (prefix=/v1/workbench):
  GET  /emails                 客户邮箱列表 (复用 file_intake.parse_email_file)
  GET  /emails/{email_id}      邮件详情 + 附件 + 关联 RFQ
  POST /emails/batch           批量操作 (mark_read/archive/to_rfq/delete)
  GET  /orders                 订单列表 (复用 orders_store + data/contexts RFQ 全生命周期)
  GET  /orders/{order_id}      订单详情 (RFQ + 报价 + 验证 + 状态历史)
  POST /orders/batch           批量操作 (quote/verify/approve/reply; quote 走确定性引擎)
  GET  /status                 本地状态聚合 (复用 nim_health + model_config + audit + traces)
  GET  /rag/collections        RAG 向量库列表 (复用 rag_layers.LayeredRAGGateway)
  POST /rag/upload             多模态 RAG 入库 (复用 file_intake + rag_gateway.ingest_file)
  POST /rag/search             RAG 检索测试 (复用 rag_gateway.search / rag_search)
  GET  /rag/layers             分层 RAG 配置 (复用 rag_layers)
  GET  /step/preview/{file_id} STEP 图纸预览 (复用 step_thumbnail.make_thumbnail)
  POST /search                 搜索客户 RAG / 联网信息 (复用 rag_search + web_search)
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from services._version import __version__        # 版本单源 (B-P0-1)

log = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent

# ---- 数据目录 (项目数据约定, 非硬编码端口/URL) ----
_MAILBOX_DIR = _ROOT / "data" / "mailbox"
_CONTEXTS_DIR = _ROOT / "data" / "contexts"
_TRACES_DIR = _ROOT / "data" / "traces"
_AUDIT_DIR = _ROOT / "data" / "audit"
_DRAWING_DIRS = (_ROOT / "data" / "artifacts" / "step3d",
                 _ROOT / "data" / "artifacts" / "step")

# 批量操作上限 (可由环境变量覆盖, 禁止硬编码)
_MAX_BATCH = int(os.environ.get("UEA_WORKBENCH_MAX_BATCH", "200"))

router = APIRouter(prefix="/v1/workbench", tags=["workbench"])


# ============================================================
# 控制器单例 (复用 bootstrap.build_controller, 懒加载)
# ============================================================
_CTRL: Optional[Any] = None


def _ctrl() -> Any:
    """懒加载 CATController 单例 (复用 bootstrap.build_controller).

    controller 暴露: timo(确定性引擎), funasr(多模态), crm(客户记忆),
    rag_gateway(LayeredRAGGateway), planner, settings, policy, commercial_cfg.
    """
    global _CTRL
    if _CTRL is None:
        from bootstrap import build_controller
        _CTRL = build_controller(root=_ROOT)
    return _CTRL


def _safe_id(mid: str) -> bool:
    """防路径穿越: 拒绝含路径分隔符/.. 的 id."""
    return bool(mid) and "/" not in mid and "\\" not in mid and ".." not in mid


def _parse_iso_ts(s: str) -> Optional[float]:
    """ISO 日期字符串 → epoch 秒; 解析失败返 None (筛选条件静默忽略)."""
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return time.mktime(time.strptime(s, fmt))
        except ValueError:
            continue
    return None


def _read_meta(stem: str) -> Dict[str, Any]:
    """读 data/mailbox/{stem}.meta.json (复用 mailbox_api 约定的元数据格式)."""
    meta = _MAILBOX_DIR / f"{stem}.meta.json"
    if meta.exists():
        try:
            return json.loads(meta.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write_meta(stem: str, meta: Dict[str, Any]) -> None:
    """写回 .meta.json (mark_read/archive 用)."""
    path = _MAILBOX_DIR / f"{stem}.meta.json"
    try:
        path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log.warning("[workbench] write meta failed for %s: %r", stem, e)


# ============================================================
# 1. GET /emails — 客户邮箱列表
#    复用: services.file_intake.parse_email_file (邮件解析)
# ============================================================
@router.get("/emails")
def list_emails(
    page: int = 1,
    page_size: int = 20,
    sender: str = "",
    subject: str = "",
    date_from: str = "",
    date_to: str = "",
    is_unread: Optional[bool] = None,
    status: str = "",
) -> JSONResponse:
    """客户邮箱列表, 支持分页 + 多维筛选.

    复用 services.file_intake.parse_email_file 解析 data/mailbox/*.eml.
    空时返回 items=[] + total=0.
    """
    _MAILBOX_DIR.mkdir(parents=True, exist_ok=True)
    ts_from = _parse_iso_ts(date_from)
    ts_to = _parse_iso_ts(date_to)

    rows: List[Dict[str, Any]] = []
    try:
        files = sorted(_MAILBOX_DIR.glob("*.eml"),
                       key=lambda x: x.stat().st_mtime, reverse=True)
    except Exception:
        files = []

    for p in files:
        try:
            parsed = _safe_parse_email(p)
            meta = _read_meta(p.stem)
        except Exception:
            continue
        mtime = p.stat().st_mtime
        row_sender = parsed.get("from", "") or ""
        row_subject = parsed.get("subject", "") or ""
        unread = bool(meta.get("is_unread", False))

        # 筛选
        if sender and sender.lower() not in row_sender.lower():
            continue
        if subject and subject.lower() not in row_subject.lower():
            continue
        if ts_from and mtime < ts_from:
            continue
        if ts_to and mtime > ts_to:
            continue
        if is_unread is not None and unread != is_unread:
            continue
        if status and meta.get("status", "") != status:
            continue

        rows.append({
            "id": p.stem,
            "from": row_sender,
            "subject": row_subject,
            "received_at": mtime,
            "size_bytes": p.stat().st_size,
            "is_unread": unread,
            "status": meta.get("status", ""),
            "badges": meta.get("badges", []),
            "attachments_count": len(parsed.get("attachments") or []),
            "has_rfq": _has_rfq_for_mail(p.stem),
        })

    total = len(rows)
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    start = (page - 1) * page_size
    return JSONResponse({
        "items": rows[start:start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 0,
    })


def _safe_parse_email(path: Path) -> Dict[str, Any]:
    """复用 services.file_intake.parse_email_file (异常由调用方捕获)."""
    from services import file_intake as fi
    return fi.parse_email_file(str(path))


def _has_rfq_for_mail(stem: str) -> bool:
    """检查邮件是否已关联 RFQ context (查 data/contexts/*.json 的 mail_id 字段)."""
    if not _CONTEXTS_DIR.is_dir():
        return False
    meta = _read_meta(stem)
    cid = meta.get("context_id")
    if cid and (_CONTEXTS_DIR / f"{cid}.json").exists():
        return True
    return False


# ============================================================
# 2. GET /emails/{email_id} — 邮件详情
#    复用: file_intake.parse_email_file + file_intake.classify (附件分类)
# ============================================================
@router.get("/emails/{email_id}")
def get_email(email_id: str) -> JSONResponse:
    """邮件详情: 完整邮件 + 附件列表 + 关联 RFQ (如有).

    复用 services.file_intake.parse_email_file / classify.
    """
    if not _safe_id(email_id):
        raise HTTPException(400, "invalid email_id")
    path = _MAILBOX_DIR / f"{email_id}.eml"
    if not path.exists():
        # 兼容 stem 前缀匹配 (复用 mailbox_api._mailbox_path 思路)
        cand = list(_MAILBOX_DIR.glob(f"{email_id}*.eml"))
        if not cand:
            return JSONResponse({"hint": f"邮件不存在: {email_id}", "found": False},
                                status_code=404)
        path = cand[0]
        email_id = path.stem

    from services import file_intake as fi
    try:
        parsed = fi.parse_email_file(str(path))
    except Exception as e:
        return JSONResponse({"hint": f"解析失败: {e!r}", "found": False},
                            status_code=500)

    # 附件详情 (复用 fi.classify)
    attachments: List[Dict[str, Any]] = []
    for name in (parsed.get("attachments") or []):
        if not name:
            continue
        attachments.append({
            "name": name,
            "ext": Path(name).suffix.lower(),
            "kind": fi.classify(name),
        })

    # 关联 RFQ
    meta = _read_meta(email_id)
    rfq_summary = _rfq_for_mail(email_id, meta)

    return JSONResponse({
        "found": True,
        "id": email_id,
        "from": parsed.get("from", ""),
        "to": parsed.get("to", ""),
        "subject": parsed.get("subject", ""),
        "body": parsed.get("body", ""),
        "date": parsed.get("date", ""),
        "received_at": path.stat().st_mtime,
        "size_bytes": path.stat().st_size,
        "attachments": attachments,
        "meta": meta,
        "rfq": rfq_summary,
    })


def _rfq_for_mail(stem: str, meta: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """查邮件关联的 RFQ context (data/contexts/{cid}.json 摘要)."""
    cid = meta.get("context_id")
    if not cid:
        return None
    p = _CONTEXTS_DIR / f"{cid}.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    return {
        "context_id": cid,
        "state": d.get("state", ""),
        "customer": (d.get("customer") or {}).get("name", ""),
        "unit_price": ((d.get("commercial") or {}).get("quote") or {}).get("unit_price"),
        "verification": (d.get("decision") or {}).get("status", ""),
    }


# ============================================================
# 3. POST /emails/batch — 批量操作
#    复用: orders_store.create (to_rfq 建单) + 现有 mail_batch 逻辑
# ============================================================
class EmailBatchRequest(BaseModel):
    ids: List[str]
    action: str  # mark_read | archive | to_rfq | delete


@router.post("/emails/batch")
def batch_emails(req: EmailBatchRequest) -> JSONResponse:
    """邮件批量操作.

    - mark_read / archive: 更新 data/mailbox/{id}.meta.json (复用 mailbox_api 元数据约定)
    - to_rfq: 调 services.orders_store.create 建订单 (复用订单状态机)
    - delete: 删 .eml + .meta.json + 清 pending ledger (复用 api_server mail_batch 逻辑)
    """
    valid_actions = {"mark_read", "archive", "to_rfq", "delete"}
    if req.action not in valid_actions:
        raise HTTPException(400, f"action must be one of {sorted(valid_actions)}")
    ids = [str(i) for i in (req.ids or [])][:_MAX_BATCH]
    success: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []

    for mid in ids:
        if not _safe_id(mid):
            failed.append({"id": mid, "reason": "invalid_id"})
            continue
        eml = _MAILBOX_DIR / f"{mid}.eml"
        if not eml.exists():
            failed.append({"id": mid, "reason": "not_found"})
            continue
        try:
            if req.action == "delete":
                eml.unlink(missing_ok=True)
                (_MAILBOX_DIR / f"{mid}.meta.json").unlink(missing_ok=True)
                _scrub_pending_ledger(mid)
            elif req.action == "mark_read":
                meta = _read_meta(mid)
                meta["is_unread"] = False
                _write_meta(mid, meta)
            elif req.action == "archive":
                meta = _read_meta(mid)
                meta["status"] = "archived"
                _write_meta(mid, meta)
            elif req.action == "to_rfq":
                order = _create_order_from_email(mid)
                success.append({"id": mid, "order_id": order.get("id")})
                continue
            success.append({"id": mid})
        except Exception as e:
            log.warning("[workbench] batch %s failed for %s: %r", req.action, mid, e)
            failed.append({"id": mid, "reason": repr(e)[:120]})

    return JSONResponse({
        "action": req.action,
        "success_count": len(success),
        "failed_count": len(failed),
        "results": success,
        "failed": failed,
    })


def _scrub_pending_ledger(mid: str) -> None:
    """清 pending ledger 对应 mail_id 的行 (复用 services.mail_puller)."""
    try:
        from services.mail_puller import MailPuller
        puller = MailPuller(root=_ROOT)
        entries = [e for e in puller._read_pending() if e.mail_id != mid]
        puller._write_pending(entries)
    except Exception:
        pass


def _create_order_from_email(mid: str) -> Dict[str, Any]:
    """从邮件建订单 (复用 services.orders_store.create)."""
    from services import orders_store as osx
    parsed = _safe_parse_email(_MAILBOX_DIR / f"{mid}.eml")
    sender = parsed.get("from", "") or ""
    name = sender.split("<")[0].strip() or sender
    return osx.create({
        "customer_name": name,
        "title": (parsed.get("subject", "") or "邮件转订单")[:80],
        "status": "inquiry",
        "source": f"email:{mid}",
        "note": f"from mail {mid}",
    })


# ============================================================
# 4. GET /orders — 订单列表 (RFQ 全生命周期)
#    复用: services.orders_store (data/orders.json 状态机)
#         + data/contexts/*.json (RFQ 全生命周期, 同 api_server /v1/orders 聚合)
# ============================================================
@router.get("/orders")
def list_orders(
    page: int = 1,
    page_size: int = 20,
    customer: str = "",
    status: str = "",
    date_from: str = "",
    date_to: str = "",
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
) -> JSONResponse:
    """订单列表: 合并 data/orders.json (外贸订单状态机) + data/contexts (RFQ 全生命周期).

    复用 services.orders_store.list_orders + data/contexts 聚合.
    空时 items=[] + total=0.
    """
    rows: List[Dict[str, Any]] = []

    # 源 1: orders_store (data/orders.json)
    try:
        from services import orders_store as osx
        store_rows = osx.list_orders(status=status, customer=customer,
                                     page=1, size=10000).get("items", [])
        for o in store_rows:
            rows.append({
                "id": o.get("id", ""),
                "source": "orders_store",
                "customer_id": o.get("customer_id", ""),
                "customer_name": o.get("customer_name", ""),
                "title": o.get("title", ""),
                "status": o.get("status", ""),
                "quantity": o.get("quantity"),
                "amount_usd": o.get("amount_usd"),
                "currency": o.get("currency", "USD"),
                "context_id": o.get("context_id"),
                "created_at": o.get("created_at", ""),
                "updated_at": o.get("updated_at", ""),
                "mtime": _iso_to_epoch(o.get("updated_at") or o.get("created_at")),
            })
    except Exception as e:
        log.debug("[workbench] orders_store load failed: %r", e)

    # 源 2: data/contexts (RFQ 全生命周期)
    ctx_rows = _load_context_orders()
    rows.extend(ctx_rows)

    # 筛选
    ts_from = _parse_iso_ts(date_from)
    ts_to = _parse_iso_ts(date_to)
    filtered: List[Dict[str, Any]] = []
    for r in rows:
        if customer and customer.lower() not in (
                r.get("customer_id", "") + r.get("customer_name", "")).lower():
            continue
        if status and status.lower() not in str(r.get("status", "")).lower():
            continue
        mtime = r.get("mtime") or 0
        if ts_from and mtime < ts_from:
            continue
        if ts_to and mtime > ts_to:
            continue
        amt = r.get("amount_usd") or r.get("final_price") or 0
        if min_amount is not None and amt < min_amount:
            continue
        if max_amount is not None and amt > max_amount:
            continue
        filtered.append(r)

    # 按 mtime DESC
    filtered.sort(key=lambda r: r.get("mtime") or 0, reverse=True)
    total = len(filtered)
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    start = (page - 1) * page_size
    return JSONResponse({
        "items": filtered[start:start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 0,
    })


def _load_context_orders() -> List[Dict[str, Any]]:
    """聚合 data/contexts/*.json 为 RFQ 订单行 (复用 api_server /v1/orders 聚合逻辑)."""
    rows: List[Dict[str, Any]] = []
    if not _CONTEXTS_DIR.is_dir():
        return rows
    for p in _CONTEXTS_DIR.glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        cid = d.get("context_id") or p.stem
        cust = d.get("customer") or {}
        com = d.get("commercial") or {}
        dec = d.get("decision") or {}
        quote = com.get("quote") or {}
        rfq = d.get("rfq") or {}
        rows.append({
            "id": cid,
            "source": "context",
            "context_id": cid,
            "customer_id": cust.get("customer_id", ""),
            "customer_name": cust.get("name") or cust.get("customer_id", ""),
            "title": rfq.get("subject") or (rfq.get("raw_text") or "")[:60] or cid,
            "status": d.get("state") or "UNKNOWN",
            "verification_status": dec.get("status", ""),
            "quantity": rfq.get("quantity"),
            "amount_usd": quote.get("final_price") or quote.get("total_price"),
            "unit_price": quote.get("unit_price"),
            "currency": quote.get("currency", "CNY"),
            "margin_pct": com.get("margin_pct"),
            "lead_time_days": quote.get("lead_time_days"),
            "mtime": p.stat().st_mtime,
        })
    return rows


def _iso_to_epoch(s: str) -> float:
    """ISO 时间字符串 → epoch; 失败返 0."""
    ts = _parse_iso_ts(s)
    return ts if ts is not None else 0.0


# ============================================================
# 5. GET /orders/{order_id} — 订单详情
#    复用: orders_store.get + data/contexts 详情
# ============================================================
@router.get("/orders/{order_id}")
def get_order(order_id: str) -> JSONResponse:
    """订单详情: RFQ + 报价 + 验证 + 状态历史.

    复用 services.orders_store.get (data/orders.json) + data/contexts/{cid}.json.
    """
    # 源 1: orders_store
    detail: Optional[Dict[str, Any]] = None
    try:
        from services import orders_store as osx
        o = osx.get(order_id)
        if o is not None:
            detail = {"source": "orders_store", **o}
    except Exception:
        pass

    # 源 2: data/contexts
    ctx_path = _CONTEXTS_DIR / f"{order_id}.json"
    if ctx_path.exists():
        try:
            d = json.loads(ctx_path.read_text(encoding="utf-8"))
            detail = {
                "source": "context",
                "id": order_id,
                "context_id": order_id,
                "rfq": d.get("rfq", {}),
                "customer": d.get("customer", {}),
                "commercial": d.get("commercial", {}),
                "decision": d.get("decision", {}),
                "state": d.get("state", ""),
                "observability": d.get("observability", {}),
                "history": _extract_state_history(d),
            }
        except Exception as e:
            log.debug("[workbench] context load failed: %r", e)

    if detail is None:
        return JSONResponse({"hint": f"订单不存在: {order_id}", "found": False},
                            status_code=404)
    return JSONResponse({"found": True, **detail})


def _extract_state_history(d: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 context 提取状态历史 (复用 audit/trace 约定)."""
    hist = d.get("history") or d.get("state_history") or []
    if isinstance(hist, list):
        return hist
    return []


# ============================================================
# 6. POST /orders/batch — 批量操作
#    铁律①: quote 走 Timo 确定性引擎, 不让 LLM 定价格
#    复用: orders_store.transition / ctrl().timo (确定性报价)
# ============================================================
class OrderBatchRequest(BaseModel):
    ids: List[str]
    action: str  # quote | verify | approve | reply


@router.post("/orders/batch")
def batch_orders(req: OrderBatchRequest) -> JSONResponse:
    """订单批量操作.

    - quote: 铁律① 走 Timo 确定性引擎 (services.model_router DETERMINISTIC 角色),
             不让 LLM 定价格. 复用 ctrl().timo.
    - verify / approve / reply: 复用 services.orders_store.transition 状态机迁移.
    """
    valid_actions = {"quote", "verify", "approve", "reply"}
    if req.action not in valid_actions:
        raise HTTPException(400, f"action must be one of {sorted(valid_actions)}")
    ids = [str(i) for i in (req.ids or [])][:_MAX_BATCH]
    results: List[Dict[str, Any]] = []
    success_count = 0
    failed_count = 0

    # action → 目标状态映射 (orders_store 状态机)
    # 业务语义说明 (B-P1-7): orders_store 状态机合法状态为
    #   inquiry → quote → sample → batch → shipped → closed, 任一在途可 → lost.
    # 动作名 (verify/approve/reply) 是工作台 UI 语义, 映射到状态机中实际不存在的
    # verified/approved/replied 会导致 transition 抛 ValueError("未知状态").
    # 因此这里映射到状态机中语义最接近的合法状态:
    #   verify  (确认样品)  → sample  (样品阶段, quote→sample 合法)
    #   approve (批准批量)  → batch   (批量阶段, sample→batch 合法)
    #   reply   (回复发货)  → shipped (发货阶段, batch→shipped 合法)
    action_to_status = {"quote": "quote", "verify": "sample", "approve": "batch",
                        "reply": "shipped"}

    for oid in ids:
        try:
            if req.action == "quote":
                # 铁律①: 确定性引擎报价, 不走 LLM
                res = _deterministic_quote(oid)
            else:
                from services import orders_store as osx
                target = action_to_status[req.action]
                o = osx.transition(oid, target, by="workbench-batch")
                res = {"id": oid, "ok": True, "status": o.get("status"),
                       "action": req.action}
            results.append(res)
            success_count += 1
        except Exception as e:
            results.append({"id": oid, "ok": False, "reason": repr(e)[:120]})
            failed_count += 1

    return JSONResponse({
        "action": req.action,
        "success_count": success_count,
        "failed_count": failed_count,
        "results": results,
    })


def _deterministic_quote(order_id: str) -> Dict[str, Any]:
    """铁律①: 走 Timo 确定性引擎报价 (复用 ctrl().timo, 不让 LLM 定价格).

    model_router DETERMINISTIC 角色对应 ctrl().timo (TimoAdapter).
    B-P0-3 修复: 之前仅探活就返回 ok:True (假功能), 现在调用 TimoAdapter.quote()
    真实报价端点获取价格, 写入订单 amount_usd, 再迁移状态到 quote.
    报价失败时不迁移状态, 返回 ok:False (禁止冒充成功).
    """
    from services import orders_store as osx
    o = osx.get(order_id)
    if o is None:
        raise ValueError(f"订单不存在: {order_id}")
    c = _ctrl()
    # 确定性引擎探活 (不冒充在线)
    engine_label = "unknown"
    try:
        engine_label = c.timo.source_label()
    except Exception:
        pass
    # 铁律①: 从订单数据构造 RFQ, 调用 TimoAdapter.quote() 真实报价端点
    rfq = {
        "quantity": o.get("quantity", 1) or 1,
        "amount_usd": o.get("amount_usd", 0.0) or 0.0,
        "material": o.get("material", "6061"),
        "surface": o.get("surface") or o.get("surface_treatment") or "无",
        "tolerance": o.get("tolerance") or o.get("tolerance_grade") or "IT8",
        "weight_kg": o.get("weight_kg", 0.5) or 0.5,
        "max_dim_mm": o.get("max_dim_mm", 100.0) or 100.0,
    }
    quote_result: Optional[Dict[str, Any]] = None
    quote_error: Optional[str] = None
    try:
        quote_result = c.timo.quote(rfq)
    except Exception as e:
        quote_error = repr(e)[:200]
    # 报价失败 → 不迁移状态, 返回 ok:False (禁止冒充成功)
    if quote_result is None or quote_error is not None:
        return {
            "id": order_id,
            "ok": False,
            "action": "quote",
            "reason": "timo-quote-failed",
            "engine": "deterministic",
            "engine_label": engine_label,
            "error": quote_error or "timo-quote-returned-none",
            "hint": "Timo 确定性引擎报价失败, 状态未迁移 (铁律①: 不走 LLM)",
        }
    # 报价成功 → 把价格写入订单 amount_usd (EDITABLE_FIELD) + 状态机迁移到 quote
    price_value = (quote_result.get("total_price") or quote_result.get("price")
                   or quote_result.get("amount_usd"))
    if price_value is not None:
        try:
            osx.update_fields(order_id, {"amount_usd": float(price_value)})
        except Exception:
            pass
    updated = osx.transition(order_id, "quote", by="deterministic-engine")
    return {
        "id": order_id,
        "ok": True,
        "action": "quote",
        "status": updated.get("status"),
        "engine": "deterministic",  # 铁律①: 标注确定性引擎, 非 LLM
        "engine_label": engine_label,
        "quote": quote_result,       # B-P0-3: 真实报价结果 (含价格字段)
        "hint": "报价由 Timo 确定性引擎生成 (铁律①: 不走 LLM)",
    }


# ============================================================
# 7. GET /status — 本地状态聚合
#    复用: nim_health + model_config.probe_all + audit + traces
# ============================================================
@router.get("/status")
def workbench_status() -> JSONResponse:
    """一次性聚合: 服务健康 + 模型在线 + 节点信息 + 最近审计 + 最近 trace.

    复用 services.nim_health.nim_health + services.model_config.probe_all
    + data/audit + data/traces.
    任一子项失败不影响整体 (返该子项 error, 不抛 500).
    """
    # 服务健康 (复用 nim_health)
    nim: Dict[str, Any] = {}
    try:
        from services import nim_health as nh
        nim = nh.nim_health()
    except Exception as e:
        nim = {"online": False, "error": repr(e)[:120]}

    # 模型在线 (复用 model_config.probe_all)
    models: Dict[str, Any] = {}
    try:
        from services import model_config as mc
        models = mc.probe_all(mc.load())
    except Exception as e:
        models = {"error": repr(e)[:120]}

    # 节点信息
    node = {
        "root": str(_ROOT),
        "version": __version__,
        "mailbox_count": _count_files(_MAILBOX_DIR, "*.eml"),
        "contexts_count": _count_files(_CONTEXTS_DIR, "*.json"),
        "traces_count": _count_files(_TRACES_DIR, "*.jsonl"),
    }

    # 最近审计 (复用 data/audit 目录约定)
    recent_audit = _recent_audit(5)

    # 最近 trace
    recent_traces = _recent_traces(5)

    return JSONResponse({
        "nim": nim,
        "models": models,
        "node": node,
        "recent_audit": recent_audit,
        "recent_traces": recent_traces,
        "ts": time.time(),
    })


def _count_files(d: Path, pattern: str) -> int:
    """统计目录下匹配文件数 (空目录返 0)."""
    try:
        return sum(1 for _ in d.glob(pattern)) if d.is_dir() else 0
    except Exception:
        return 0


def _recent_audit(limit: int) -> List[Dict[str, Any]]:
    """最近审计事件 (复用 data/audit 目录 + services.audit 链式约定)."""
    out: List[Dict[str, Any]] = []
    if not _AUDIT_DIR.is_dir():
        return out
    try:
        files = sorted(_AUDIT_DIR.glob("*.json"),
                       key=lambda x: x.stat().st_mtime, reverse=True)[:limit]
    except Exception:
        return out
    for p in files:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({
                "file": p.name,
                "context_id": d.get("context_id", ""),
                "valid": d.get("valid"),
                "events_count": len(d.get("events", [])),
                "mtime": p.stat().st_mtime,
            })
        except Exception:
            continue
    return out


def _recent_traces(limit: int) -> List[Dict[str, Any]]:
    """最近 trace (复用 data/traces/*.jsonl)."""
    out: List[Dict[str, Any]] = []
    if not _TRACES_DIR.is_dir():
        return out
    try:
        files = sorted(_TRACES_DIR.glob("*.jsonl"),
                       key=lambda x: x.stat().st_mtime, reverse=True)[:limit]
    except Exception:
        return out
    for p in files:
        try:
            lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
            out.append({
                "context_id": p.stem,
                "span_count": len(lines),
                "mtime": p.stat().st_mtime,
            })
        except Exception:
            continue
    return out


# ============================================================
# 8. GET /rag/collections — RAG 向量库列表
#    复用: services.rag_layers.LayeredRAGGateway (ctrl().rag_gateway)
# ============================================================
@router.get("/rag/collections")
def rag_collections() -> JSONResponse:
    """RAG 向量库列表: 各库元信息 (名称/文档数/维度/最后更新).

    复用 services.rag_layers.LayeredRAGGateway (通过 ctrl().rag_gateway).
    gateway 未启用时返空列表 + hint.
    """
    g = _ctrl().rag_gateway
    if g is None:
        return JSONResponse({
            "items": [],
            "hint": "rag_gateway 未启用 (settings.rag_layers.enabled=false?)",
        })
    collections: List[Dict[str, Any]] = []
    # quote_history + ingest_docs 集合 (复用 rag_layers 常量)
    try:
        from services import rag_layers as rl
        known = [rl.QUOTES_COLLECTION, rl.INGEST_COLLECTION]
    except Exception:
        known = ["quote_history", "ingest_docs"]

    for name in known:
        info: Dict[str, Any] = {"name": name}
        try:
            if g.store is not None:
                points = list(g.store.list_points(name))
                info["doc_count"] = len(points)
                # 维度从 embedder 推断
                info["dim"] = getattr(g.embedder, "dim", None)
                # 最后更新时间
                mtimes = [pl.get("_indexed_at", 0)
                          for pl in (p.get("payload", {}) for p in points)]
                info["last_updated"] = max(mtimes) if mtimes else None
            else:
                info["doc_count"] = 0
        except Exception as e:
            info["error"] = repr(e)[:120]
            info["doc_count"] = 0
        collections.append(info)

    return JSONResponse({"items": collections, "count": len(collections)})


# ============================================================
# 9. POST /rag/upload — 多模态 RAG 入库
#    复用: file_intake + rag_gateway.ingest_file
# ============================================================
@router.post("/rag/upload")
async def rag_upload(
    file: UploadFile = File(...),
    collection: str = Form("ingest_docs"),
    modality: str = Form("text"),
    customer_id: Optional[str] = Form(None),
) -> JSONResponse:
    """多模态 RAG 入库 (text/image/audio/step).

    复用 services.file_intake (落盘 + 抽文本) + rag_gateway.ingest_file.
    """
    g = _ctrl().rag_gateway
    if g is None:
        return JSONResponse({"ok": False, "hint": "rag_gateway 未启用"},
                            status_code=503)

    # 落盘 (复用 api_server._save_upload 思路: 时间戳前缀 + uuid 防冲突)
    from services import security as sec
    art_dir = _ROOT / "data" / "artifacts" / "rag_ingest"
    art_dir.mkdir(parents=True, exist_ok=True)
    safe = sec.safe_filename(file.filename or "upload")
    dest = art_dir / f"{int(time.time() * 1000)}_{safe}"
    try:
        with dest.open("wb") as fh:
            from shutil import copyfileobj
            copyfileobj(file.file, fh)
    except Exception as e:
        return JSONResponse({"ok": False, "reason": repr(e)[:120]},
                            status_code=500)

    # 入库 (复用 rag_gateway.ingest_file)
    try:
        res = g.ingest_file(str(dest), customer_id=customer_id or None,
                            tags=[modality, collection],
                            doc_name=file.filename or None)
    except Exception as e:
        return JSONResponse({"ok": False, "reason": repr(e)[:120]})
    res["filename"] = file.filename
    res["modality"] = modality
    res["collection"] = collection
    return JSONResponse(res)


# ============================================================
# 10. POST /rag/search — RAG 检索测试
#     复用: rag_gateway.search (分层) / rag_search (ragflow)
# ============================================================
class RagSearchRequest(BaseModel):
    query: str
    collection: str = "ingest_docs"
    top_k: int = 5
    modality: Optional[str] = None


@router.post("/rag/search")
def rag_search(req: RagSearchRequest) -> JSONResponse:
    """RAG 检索测试: 返回 {matches:[{content,score,source,modality}]}.

    复用 services.rag_layers.LayeredRAGGateway.search (分层检索).
    gateway 未启用时降级到 services.rag_search (ragflow).
    """
    if not req.query.strip():
        return JSONResponse({"matches": [], "hint": "query 为空"})

    g = _ctrl().rag_gateway
    matches: List[Dict[str, Any]] = []

    if g is not None:
        try:
            res = g.search(req.query, top_k=req.top_k)
            for ev in res.get("evidence", []):
                matches.append({
                    "content": ev.get("text") or ev.get("snippet") or ev.get("note", ""),
                    "score": ev.get("score"),
                    "source": ev.get("source") or ev.get("_source", ""),
                    "modality": ev.get("layer", ""),
                })
            return JSONResponse({
                "matches": matches[:req.top_k],
                "degraded": res.get("degraded", False),
                "source": "rag_layers",
            })
        except Exception as e:
            log.debug("[workbench] rag_layers search failed, fallback: %r", e)

    # 降级: rag_search (ragflow)
    try:
        from services import rag_search as rs
        res = rs.search(req.query, top_k=req.top_k)
        for h in res.get("hits", []):
            matches.append({
                "content": h.get("snippet") or h.get("title", ""),
                "score": h.get("score"),
                "source": res.get("_source", ""),
                "modality": "craft",
            })
    except Exception as e:
        return JSONResponse({"matches": [], "error": repr(e)[:120]})

    return JSONResponse({"matches": matches[:req.top_k], "source": "rag_search"})


# ============================================================
# 11. GET /rag/layers — 分层 RAG 配置
#     复用: services.rag_layers
# ============================================================
@router.get("/rag/layers")
def rag_layers() -> JSONResponse:
    """分层 RAG 配置: 返回分层结构 (customer/quotes/conversations/craft).

    复用 services.rag_layers (ALL_LAYERS 常量 + gateway 状态).
    """
    try:
        from services import rag_layers as rl
        layer_names = list(rl.ALL_LAYERS)
    except Exception:
        layer_names = ["customer", "quotes", "conversations", "craft"]

    layer_desc = {
        "customer": "L1 客户信息层 — crm_memory SQL (结构化画像)",
        "quotes": "L2 历史报价层 — VectorStore quote_history 集合 (语义相似锚点)",
        "conversations": "L3 客户对话层 — funasr-gui /rag/search",
        "craft": "L4 工艺知识层 — services.rag.py (在线转发 / 离线内置案例)",
    }

    g = _ctrl().rag_gateway
    embedder_info: Dict[str, Any] = {}
    if g is not None:
        try:
            emb = g.embedder
            embedder_info = {
                "source": getattr(emb, "source", ""),
                "dim": getattr(emb, "dim", None),
                "degraded": getattr(emb, "degraded", None),
                "model": getattr(emb, "model", ""),
            }
        except Exception:
            pass

    return JSONResponse({
        "layers": [{"name": n, "desc": layer_desc.get(n, "")} for n in layer_names],
        "embedder": embedder_info,
        "gateway_enabled": g is not None,
    })


# ============================================================
# 12. GET /step/preview/{file_id} — STEP 图纸预览
#     复用: services.step_thumbnail.make_thumbnail + ctrl().timo
# ============================================================
@router.get("/step/files")
def step_files(limit: int = 50) -> JSONResponse:
    """列出本地 STEP 图纸（data/artifacts/step|step3d），供工作台预览列表使用."""
    items: List[Dict[str, Any]] = []
    seen = set()
    for d in _DRAWING_DIRS:
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if not p.is_file() or p.suffix.lower() not in (".step", ".stp"):
                continue
            if p.stem in seen:
                continue
            seen.add(p.stem)
            items.append({
                "id": p.stem,
                "name": p.name,
                "dir": d.name,
                "size_bytes": p.stat().st_size,
                "mtime": p.stat().st_mtime,
            })
            if len(items) >= max(1, min(limit, 200)):
                return JSONResponse({"items": items, "total": len(items)})
    return JSONResponse({"items": items, "total": len(items)})


@router.get("/step/preview/{file_id}")
def step_preview(file_id: str) -> JSONResponse:
    """STEP 图纸预览: OCP 几何元数据 (bbox/体积/重量/C1特征) + 缩略图 SVG.

    复用 services.step_thumbnail.make_thumbnail (确定性 OCP 几何 + SVG).
    """
    if not _safe_id(file_id):
        raise HTTPException(400, "invalid file_id")
    path = _find_step_file(file_id)
    if path is None:
        return JSONResponse({"hint": f"STEP 文件不存在: {file_id}", "found": False},
                            status_code=404)

    from services.step_thumbnail import make_thumbnail
    try:
        out = make_thumbnail(_ctrl().timo, str(path))
    except Exception as e:
        return JSONResponse({"ok": False, "reason": repr(e)[:200]},
                            status_code=500)

    return JSONResponse({
        "found": True,
        "file_id": file_id,
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "ok": out.get("ok"),
        "bbox": out.get("bbox"),
        "volume_cm3": out.get("volume_cm3"),
        "mass_g": out.get("mass_g"),
        "features_count": out.get("features_count", 0),
        "svg": out.get("svg"),
        "cached": out.get("cached"),
        "source": out.get("_source"),
    })


def _find_step_file(file_id: str) -> Optional[Path]:
    """按 stem 查找 STEP 文件 (复用 api_server._find_drawing 思路, 防路径穿越)."""
    for d in _DRAWING_DIRS:
        if not d.is_dir():
            continue
        for p in d.iterdir():
            if p.is_file() and p.stem == file_id and p.suffix.lower() in (".step", ".stp"):
                return p
    # 兼容 data/node_evidence 下的 .step
    node_dir = _ROOT / "data" / "node_evidence"
    if node_dir.is_dir():
        for p in node_dir.iterdir():
            if p.is_file() and p.stem == file_id and p.suffix.lower() in (".step", ".stp"):
                return p
    return None


# ============================================================
# 13. POST /search — 搜索客户 RAG / 联网信息
#     复用: services.rag_search + services.web_search
# ============================================================
class SearchRequest(BaseModel):
    query: str
    scope: List[str] = ["rag", "web"]
    customer_id: Optional[str] = None


@router.post("/search")
def search(req: SearchRequest) -> JSONResponse:
    """搜索客户 RAG / 联网信息.

    复用 services.rag_search.search (RAG) + services.web_search.search (联网).
    返回 {rag_results, web_results}. 离线时各子项返空 + warning, 不报错.
    """
    if not req.query.strip():
        return JSONResponse({"rag_results": [], "web_results": [],
                             "hint": "query 为空"})

    rag_results: Any = []
    web_results: Any = []

    if "rag" in req.scope:
        try:
            from services import rag_search as rs
            res = rs.search(req.query, top_k=5)
            rag_results = res.get("hits", [])
        except Exception as e:
            rag_results = {"error": repr(e)[:120], "hits": []}

    if "web" in req.scope:
        try:
            from services import web_search as ws
            res = ws.search(req.query, num=5)
            web_results = res.get("hits", [])
        except Exception as e:
            web_results = {"error": repr(e)[:120], "hits": []}

    return JSONResponse({
        "query": req.query,
        "customer_id": req.customer_id,
        "rag_results": rag_results,
        "web_results": web_results,
    })