"""list_all_sandboxes / flywheel_stats 必须从实表计数 (BUG-1 巡检修复).

背景 (2026-09-25 订单邮箱总览页巡检报告): 总览页"历史报价 0 / 成交 0 / 胜率 0%"
而节点沙箱 quotes 表实有 3110 行。根因: 生产链路只写 quotes/rfqs/postmortems
三张实表, 从不回写 pricing_model 计数器 (write_quote 无计数逻辑), 摘要层把
stale 模型计数当真值聚合; 且 quote_count 取 get_history(limit=1)["n"], 恒封顶 1。

实表口径: quotes JOIN rfqs (本客户) = 总报价数; postmortems.outcome
(won/lost, 大小写不敏感) = 成交/丢单数。
"""
from __future__ import annotations

import time

from fastapi.testclient import TestClient

import services.sandbox as sbx
import services.flywheel_api as fa
from services.api_server import app

client = TestClient(app)


def _mk_sandbox(cid: str = "CUST-STAT1", n_quotes: int = 3,
                won: int = 1, lost: int = 2) -> sbx.CustomerSandbox:
    sb = sbx.CustomerSandbox(cid)
    for i in range(n_quotes):
        ctx = f"CTX-{cid}-{i}"
        sb.write_rfq(ctx, {"material": "AL6061", "surface": "anodized",
                           "context_id": ctx})
        sb.write_quote(ctx, {"unit_price": 10.0 + i, "final_price": 12.0 + i,
                             "margin_pct": 0.2, "_source": "test"})
    for i in range(won):
        sb.record_postmortem(f"CTX-{cid}-{i}", "won", 12.0)
    for i in range(lost):
        sb.record_postmortem(f"CTX-{cid}-{won + i}", "lost", 12.0)
    sb.close()
    return sb


def _stale_model(sb: sbx.CustomerSandbox) -> None:
    """模拟节点存量: pricing_model 计数器全 0 (历史行从未被回写)。"""
    sb.conn.execute(
        "INSERT OR REPLACE INTO pricing_model(customer_id,win_rate,total_quotes,"
        "total_won,total_lost,updated_at) VALUES(?,0.5,0,0,0,?)",
        (sb.customer_id, time.time()))
    sb.conn.commit()
    sb.close()


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(sbx, "SANDBOX_DIR", tmp_path)
    monkeypatch.setattr(sbx, "_GLOBAL_DB", tmp_path / "no-such-crm.sqlite3")


def test_summary_counts_from_real_tables_not_stale_model(tmp_path, monkeypatch):
    """BUG-1 核心: 摘要层用 stale 模型计数 → 总览页全零。须改从实表计数。"""
    _isolate(tmp_path, monkeypatch)
    sb = _mk_sandbox("CUST-STAT1", n_quotes=3, won=1, lost=2)
    _stale_model(sb)

    rows = {r["customer_id"]: r for r in sbx.list_all_sandboxes()}
    row = rows["CUST-STAT1"]

    assert row["total_quotes"] == 3      # 实表 3 行, 非 stale 模型的 0
    assert row["total_won"] == 1
    assert row["total_lost"] == 2
    assert row["quote_count"] == 3       # 不再被 get_history(limit=1) 封顶为 1


def test_flywheel_stats_equals_sum_of_real_sandbox_counts(tmp_path, monkeypatch):
    """报告要求的 stats vs 沙箱合计一致性单测 (防聚合层再次归零)。"""
    _isolate(tmp_path, monkeypatch)
    sb = _mk_sandbox("CUST-STAT2", n_quotes=4, won=1, lost=1)
    _stale_model(sb)

    rows = sbx.list_all_sandboxes()
    stats = fa.flywheel_stats()

    assert stats["total_customers"] == 1
    assert stats["total_quotes"] == sum(r.get("total_quotes", 0) for r in rows) == 4
    assert stats["total_won"] == 1 and stats["total_lost"] == 1
    assert stats["overall_win_rate"] == 0.5
    r = client.get("/v1/flywheel/stats")
    assert r.status_code == 200 and r.json()["total_quotes"] == 4


def test_won_lost_case_insensitive_and_orphan_postmortem_excluded(tmp_path, monkeypatch):
    """outcome 大小写不敏感 (历史 'Won' 亦计); 无对应 rfq 的孤儿复盘不计。"""
    _isolate(tmp_path, monkeypatch)
    sb = _mk_sandbox("CUST-STAT3", n_quotes=2, won=0, lost=0)
    sb.record_postmortem("CTX-CUST-STAT3-0", "Won")
    sb.record_postmortem("CTX-CUST-STAT3-1", "LOST")
    sb.record_postmortem("ORPHAN-CTX", "won")
    sb.close()

    rows = {r["customer_id"]: r for r in sbx.list_all_sandboxes()}
    row = rows["CUST-STAT3"]
    assert row["total_won"] == 1
    assert row["total_lost"] == 1
    assert row["total_quotes"] == 2
