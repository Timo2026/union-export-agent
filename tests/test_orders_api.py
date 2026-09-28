"""test_orders_api.py — v7.0 订单端点契约 (状态机/筛选分页/批量/降级).

DB_PATH 全部指向 tmp_path, 不触真实 data/orders.json。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services import orders_store
from services.api_server import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(orders_store, "DB_PATH", tmp_path / "orders.json")
    return TestClient(app)


def _mk(client, **over):
    body = {"customer_id": "ACME", "customer_name": "ACME GmbH",
            "title": "1010003 法兰", "quantity": 50, "amount_usd": 1234.5}
    body.update(over)
    r = client.post("/v1/orders", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_meta(client):
    r = client.get("/v1/orders/meta")
    assert r.status_code == 200
    m = r.json()
    assert m["statuses"] == ["inquiry", "quote", "sample", "batch", "shipped", "closed", "lost"]
    assert "lost" in m["transitions"]["quote"]
    assert m["transitions"]["closed"] == []


def test_crud_lifecycle(client):
    o = _mk(client)
    assert o["status"] == "inquiry" and o["id"].startswith("ORD-")
    got = client.get(f"/v1/orders/{o['id']}")
    assert got.status_code == 200 and got.json()["title"] == "1010003 法兰"

    r = client.patch(f"/v1/orders/{o['id']}", json={"to_status": "quote"})
    assert r.status_code == 200 and r.json()["status"] == "quote"
    # 非法跨级: quote → shipped 必须 409
    r = client.patch(f"/v1/orders/{o['id']}", json={"to_status": "shipped"})
    assert r.status_code == 409
    # 字段编辑与迁移可同请求
    r = client.patch(f"/v1/orders/{o['id']}",
                     json={"note": "客户确认材质", "to_status": "sample"})
    assert r.status_code == 200 and r.json()["status"] == "sample"
    assert r.json()["note"] == "客户确认材质"

    assert client.patch("/v1/orders/ORD-00000000-999", json={"to_status": "quote"}).status_code == 404
    assert client.get("/v1/orders/ORD-NOPE").status_code == 404
    assert client.delete(f"/v1/orders/{o['id']}").status_code == 200
    assert client.get(f"/v1/orders/{o['id']}").status_code == 404


def test_create_validation(client):
    assert client.post("/v1/orders", json={"title": "无客户"}).status_code == 400
    assert client.post("/v1/orders",
                       json={"customer_id": "X", "status": "外星态"}).status_code == 400


def test_filter_sort_pagination(client):
    for i in range(5):
        _mk(client, customer_id=f"CUST{i % 2}", title=f"件 {i}", amount_usd=i * 10)
    r = client.get("/v1/orders", params={"customer": "CUST1"}).json()
    assert r["total"] == 2 and all("CUST1" in o["customer_id"] for o in r["items"])
    r = client.get("/v1/orders", params={"q": "件 4"}).json()
    assert r["total"] == 1
    r = client.get("/v1/orders", params={"status": "inquiry,quote", "page": 1, "size": 2}).json()
    assert r["total"] == 5 and r["pages"] == 3 and len(r["items"]) == 2
    r2 = client.get("/v1/orders", params={"page": 3, "size": 2}).json()
    assert len(r2["items"]) == 1


def test_bulk_transition_partial(client):
    ids = [_mk(client)["id"] for _ in range(3)]
    r = client.post("/v1/orders/bulk",
                    json={"ids": ids + ["ORD-NOPE"], "action": "transition",
                          "target_status": "quote"}).json()
    assert len(r["ok"]) == 3 and r["failed"] == [{"id": "ORD-NOPE", "reason": "not_found"}]
    statuses = {client.get(f"/v1/orders/{i}").json()["status"] for i in ids}
    assert statuses == {"quote"}

    r = client.post("/v1/orders/bulk",
                    json={"ids": ids[:1], "action": "transition",
                          "target_status": "closed"}).json()  # inquiry 起点已变 quote→closed 非法
    assert r["ok"] == [] and "非法流转" in r["failed"][0]["reason"]
    assert client.post("/v1/orders/bulk", json={"ids": [], "action": "delete"}).status_code == 400
    assert client.post("/v1/orders/bulk", json={"ids": ids, "action": "delete"}).status_code == 200
    assert client.get("/v1/orders").json()["total"] == 0


def test_store_transition_table_direct():
    assert orders_store.can_transition("batch", "shipped")
    assert not orders_store.can_transition("batch", "inquiry")
    assert not orders_store.can_transition("lost", "quote")
