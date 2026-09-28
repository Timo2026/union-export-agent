"""seed_orders.py — 从 flywheel 客户沙箱历史报价初始化订单库 (幂等).

映射规则 (以 context_id 为幂等键):
  有 postmortem.won  → closed    有 postmortem.lost → lost
  其余 (PASS/HITL/BLOCKED 报价记录) → quote
已存在同 context_id 的订单则跳过, 可重复执行。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from services import orders_store
from services.sandbox import CustomerSandbox, list_all_sandboxes


def seed() -> dict:
    created, skipped = [], []
    existing_ctx = {o.get("context_id") for o in orders_store.load()}
    for info in list_all_sandboxes():
        cid = info.get("customer_id", "")
        if not cid or info.get("error"):
            continue
        try:
            sb = CustomerSandbox(cid)
            history = sb.get_history(limit=50)
            sb.close()
        except Exception as e:  # 沙箱损坏不阻塞种子
            print(f"[seed] skip {cid}: {e}", file=sys.stderr)
            continue
        pm_by_ctx = {p["context_id"]: p for p in history.get("postmortems", [])}
        for q in history.get("quotes", []):
            ctx = q.get("context_id")
            if not ctx or ctx in existing_ctx:
                skipped.append(ctx)
                continue
            pm = pm_by_ctx.get(ctx)
            if pm and pm.get("outcome") == "won":
                status = "closed"
            elif pm and pm.get("outcome") == "lost":
                status = "lost"
            else:
                status = "quote"
            amount = float(q.get("final_price") or q.get("unit_price") or 0.0)
            order = orders_store.create({
                "customer_id": cid, "customer_name": cid,
                "title": f"飞轮历史报价 {ctx}", "status": status,
                "amount_usd": amount, "context_id": ctx, "source": "seed",
                "note": (pm or {}).get("note", ""),
            })
            # 种子单沿用报价时间戳, 保证列表排序贴近真实
            order["created_at"] = q.get("created_at") or order["created_at"]
            alls = orders_store.load()
            for o in alls:
                if o["id"] == order["id"]:
                    o["created_at"] = order["created_at"]
            orders_store._save(alls)
            existing_ctx.add(ctx)
            created.append(order["id"])
    return {"created": created, "skipped": skipped}


if __name__ == "__main__":
    result = seed()
    print(f"[seed_orders] 新建 {len(result['created'])} 单, "
          f"跳过 {len(result['skipped'])} 条已有 context")
