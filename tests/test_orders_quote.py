"""test_orders_quote.py — 订单自动报价契约 (铁律①: 金额唯一权威 = Timo 引擎).

模式 A (context): order.context_id → data/contexts/{cid}.json 已由黄金链产出的 quote.
模式 B (params):  调用方给材料/数量/表面/公差 → ctrl().timo.quote 引擎直裁 (byte-identical).
铁律:
  - LLM 不生成数字; 引擎失败 → 订单不动, 不写假数 (诚实失败).
  - quote_* 溯源字段引擎专属, 手工 PATCH 覆写不了 (EDITABLE_FIELDS 不含).
  - 每次报价落 history {action: auto_quote} 审计.
"""
from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from services import orders_store
from services import api_server
from services.api_server import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(orders_store, "DB_PATH", tmp_path / "orders.json")
    api_server._STORE.clear()
    return TestClient(app)


def _mk(client, **over):
    body = {"customer_id": "ACME", "customer_name": "ACME GmbH",
            "title": "6061 支架", "quantity": 1, "amount_usd": 0}
    body.update(over)
    r = client.post("/v1/orders", json=body)
    assert r.status_code == 200, r.text
    return r.json()


class _StubTimo:
    def __init__(self, result=None, exc=None):
        self.result = result
        self.exc = exc
        self.calls = []

    def quote(self, rfq, dynamic_adjustments=None):
        self.calls.append(dict(rfq))
        if self.exc:
            raise self.exc
        return dict(self.result)


def _inject_context(cid, quote, quantity=100, state="REPLY", customer=None):
    """按 data/contexts/{cid}.json 形状注入 _STORE (与 _rehydrate_from_disk 同构)."""
    api_server._STORE[cid] = {
        "inputs": {}, "customer": customer or {"name": "ACME GmbH", "customer_id": "ACME"},
        "email_text": "6061 bracket 100 pcs anodizing",
        "result": {
            "context_id": cid, "state": state,
            "rfq": {"material": "6061", "quantity": quantity,
                    "surface": "阳极氧化", "tolerance_grade": "IT7"},
            "quote": quote,
            "verification_status": "PASS",
        },
    }


# ---------------- 模式 A: context 已产出报价 ----------------

def test_quote_from_context(client, monkeypatch):
    cid = "RFQ-20260926-CTX001"
    _inject_context(cid, {"final_price": 24678.22, "unit_price": 172.57,
                          "total_price": 24678.22, "currency": "CNY"})
    o = _mk(client, context_id=cid)
    r = client.post(f"/v1/orders/{o['id']}/quote")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    order = body["order"]
    assert order["amount_usd"] == 24678.22
    assert order["unit_price"] == 172.57
    assert order["currency"] == "CNY"
    assert order["quote_source"].startswith("context:")
    assert len(order["quote_sha16"]) == 16
    assert order["quoted_at"]
    # history 审计: auto_quote 动作在栈顶
    assert order["history"][-1]["action"] == "auto_quote"
    # 数量不被报价动作静默改写
    assert order["quantity"] == 1


def test_quote_context_no_valid_quote(client):
    cid = "RFQ-20260926-CTX002"
    _inject_context(cid, {}, state="BLOCKED")
    o = _mk(client, context_id=cid)
    r = client.post(f"/v1/orders/{o['id']}/quote")
    assert r.status_code == 409
    got = client.get(f"/v1/orders/{o['id']}").json()
    assert got["amount_usd"] == 0 and "quoted_at" not in got
    assert not any(h["action"] == "auto_quote" for h in got["history"])


def test_quote_context_missing(client):
    o = _mk(client, context_id="RFQ-NOPE")
    r = client.post(f"/v1/orders/{o['id']}/quote")
    assert r.status_code == 404


# ---------------- 模式 B: 引擎直裁 ----------------

def test_quote_params_engine(client, monkeypatch):
    stub = _StubTimo(result={"final_price": 9950.0, "unit_price": 199.0,
                             "total_price": 9950.0, "currency": "CNY",
                             "_source": "live:/api/quote"})
    monkeypatch.setattr(api_server, "ctrl", lambda: type("C", (), {"timo": stub})())
    o = _mk(client)
    r = client.post(f"/v1/orders/{o['id']}/quote",
                    json={"material": "7075", "quantity": 50, "surface": "喷涂",
                          "tolerance_grade": "IT6"})
    assert r.status_code == 200, r.text
    order = r.json()["order"]
    assert order["amount_usd"] == 9950.0
    assert order["unit_price"] == 199.0
    assert order["quote_source"] == "live:/api/quote"
    # 传给引擎的是 canonical rfq 形状
    assert stub.calls and stub.calls[0]["material"] == "7075"
    assert stub.calls[0]["quantity"] == 50
    assert stub.calls[0]["surface"] == "喷涂"
    assert stub.calls[0]["tolerance"] == "IT6"


def test_quote_engine_failure_no_fake_number(client, monkeypatch):
    stub = _StubTimo(exc=RuntimeError("engine :7862 unreachable"))
    monkeypatch.setattr(api_server, "ctrl", lambda: type("C", (), {"timo": stub})())
    o = _mk(client, amount_usd=0)
    r = client.post(f"/v1/orders/{o['id']}/quote",
                    json={"material": "6061", "quantity": 10})
    assert r.status_code == 502
    got = client.get(f"/v1/orders/{o['id']}").json()
    assert got["amount_usd"] == 0 and "quoted_at" not in got
    assert not any(h["action"] == "auto_quote" for h in got["history"])


def test_quote_params_missing_material(client):
    o = _mk(client)
    r = client.post(f"/v1/orders/{o['id']}/quote", json={"quantity": 10})
    assert r.status_code == 400


# ---------------- 溯源字段引擎专属 ----------------

def test_quote_fields_not_patchable(client, monkeypatch):
    stub = _StubTimo(result={"final_price": 500.0, "unit_price": 50.0,
                             "total_price": 500.0, "currency": "CNY",
                             "_source": "offline:calc_quote"})
    monkeypatch.setattr(api_server, "ctrl", lambda: type("C", (), {"timo": stub})())
    o = _mk(client)
    client.post(f"/v1/orders/{o['id']}/quote",
                json={"material": "6061", "quantity": 10})
    r = client.patch(f"/v1/orders/{o['id']}",
                     json={"quote_source": "hand-typed", "unit_price": 1,
                           "quote_sha16": "0" * 16, "quoted_at": "1999-01-01T00:00:00"})
    assert r.status_code == 200
    got = r.json()
    assert got["quote_source"] == "offline:calc_quote"  # 引擎字段拒手工覆写
    assert got["unit_price"] == 50.0
    # amount_usd 允许人工调整 (留痕), 但溯源仍在
    r2 = client.patch(f"/v1/orders/{o['id']}", json={"amount_usd": 480.0})
    assert r2.json()["amount_usd"] == 480.0
    assert r2.json()["quote_source"] == "offline:calc_quote"


# ---------------- 建单即报价 ----------------

def test_create_with_auto_quote_context(client):
    cid = "RFQ-20260926-CTX003"
    _inject_context(cid, {"final_price": 12345.67, "unit_price": 123.46,
                          "total_price": 12345.67, "currency": "CNY"})
    r = client.post("/v1/orders", json={
        "customer_name": "ACME GmbH", "context_id": cid, "auto_quote": True,
        "title": "转订单自报", "source": "email"})
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["amount_usd"] == 12345.67
    assert o["quote_source"].startswith("context:")
    assert o["history"][-1]["action"] == "auto_quote"


def test_create_with_auto_quote_params(client, monkeypatch):
    stub = _StubTimo(result={"final_price": 777.0, "unit_price": 77.7,
                             "total_price": 777.0, "currency": "CNY",
                             "_source": "live:/api/quote"})
    monkeypatch.setattr(api_server, "ctrl", lambda: type("C", (), {"timo": stub})())
    r = client.post("/v1/orders", json={
        "customer_name": "ACME GmbH", "auto_quote": True, "quantity": 10,
        "material": "6061", "surface": "阳极氧化"})
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["amount_usd"] == 777.0
    assert o["quote_source"] == "live:/api/quote"
    assert stub.calls and stub.calls[0]["quantity"] == 10


def test_create_without_auto_quote_keeps_manual_amount(client):
    o = _mk(client, amount_usd=999.0)
    assert o["amount_usd"] == 999.0
    assert "quoted_at" not in o
    assert o["history"][-1]["action"] == "create"


def test_quote_order_not_found(client):
    assert client.post("/v1/orders/ORD-00000000-999/quote").status_code == 404


def test_quote_sha16_stable(client):
    """同一 quote 内容 → sha16 确定 (byte-identical 语义)."""
    cid = "RFQ-20260926-CTX004"
    quote = {"final_price": 100.0, "unit_price": 10.0, "total_price": 100.0,
             "currency": "CNY"}
    _inject_context(cid, quote)
    o = _mk(client, context_id=cid)
    r = client.post(f"/v1/orders/{o['id']}/quote").json()["order"]
    core = {k: quote[k] for k in ("final_price", "unit_price", "total_price", "currency")}
    want = hashlib.sha256(json.dumps(core, sort_keys=True, ensure_ascii=False)
                          .encode()).hexdigest()[:16]
    assert r["quote_sha16"] == want
