"""test_customer_api.py — /v1/customer/enrich 联网情报 + 显式 MOCK 降级.

web_search 与沙箱列表打桩 (测试不触网、不依赖沙箱存量)。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.api_server import app
import services.customer_api as ca


@pytest.fixture()
def client():
    return TestClient(app)


FAKE_SANDBOXES = [{"customer_id": "ACME-GMBH", "total_quotes": 3},
                  {"customer_id": "OTHER-CORP", "total_quotes": 1}]


class FakeSandbox:
    def get_history(self, limit=5):
        return {"quotes": [{"context_id": "RFQ-1", "unit_price": 88.0}],
                "postmortems": []}

    def get_pricing_model(self):
        return {"win_rate": 0.5}

    def close(self):
        pass


def test_enrich_online_hits(client, monkeypatch):
    monkeypatch.setattr(ca, "_CRM_DB", Path("__no_crm_db__.sqlite3"))
    monkeypatch.setattr(ca, "list_all_sandboxes", lambda: FAKE_SANDBOXES)
    monkeypatch.setattr(ca, "CustomerSandbox", lambda cid: FakeSandbox())
    monkeypatch.setattr(ca.web_search, "search", lambda q, num=5: {
        "hits": [{"title": "ACME GmbH — CNC parts", "url": "https://x", "snippet": "s", "engine": "bing"}],
        "mock": False, "_source": "searxng@http://127.0.0.1:8888"})
    r = client.get("/v1/customer/enrich", params={"name": "ACME"})
    assert r.status_code == 200
    body = r.json()
    assert body["web"]["mock"] is False and len(body["web"]["hits"]) == 1
    assert body["profile"]["match_count"] == 1
    assert body["profile"]["matched"][0]["recent_quotes"][0]["unit_price"] == 88.0


def test_enrich_offline_explicit_mock(client, monkeypatch):
    monkeypatch.setattr(ca, "_CRM_DB", Path("__no_crm_db__.sqlite3"))
    monkeypatch.setattr(ca, "list_all_sandboxes", lambda: FAKE_SANDBOXES)
    monkeypatch.setattr(ca, "CustomerSandbox", lambda cid: FakeSandbox())
    monkeypatch.setattr(ca.web_search, "search", lambda q, num=5: {
        "hits": [], "mock": False, "_source": "searxng-offline", "warning": "不可达"})
    body = client.get("/v1/customer/enrich", params={"name": "ACME"}).json()
    assert body["web"]["mock"] is True          # 离线必须显式标注
    assert body["web"]["hits"] == []
    assert body["profile"]["match_count"] == 1  # 本地画像不受联网影响


def test_enrich_crm_name_lookup(tmp_path, client, monkeypatch):
    """CRM customers 表按名称 LIKE 反查 (v7.1 真接通): 沙箱只有 id, 名称查询必须走 crm.sqlite3."""
    import sqlite3
    db = tmp_path / "crm.sqlite3"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE customers (customer_id TEXT, name TEXT, country TEXT,"
                " lifecycle_state TEXT, total_orders INT, total_revenue REAL,"
                " health_score REAL, updated_at TEXT)")
    con.execute("INSERT INTO customers VALUES ('CUST-T1','Northwind Robotics','US','active',3,9.9,0.8,'2026-09-22')")
    con.commit()
    con.close()
    monkeypatch.setattr(ca, "_CRM_DB", db)
    monkeypatch.setattr(ca, "list_all_sandboxes", lambda: [])
    monkeypatch.setattr(ca.web_search, "search", lambda q, num=5: {
        "hits": [], "mock": True, "_source": "searxng-offline"})
    body = client.get("/v1/customer/enrich", params={"name": "northwind"}).json()
    m = body["profile"]["matched"]
    assert body["profile"]["match_count"] == 1
    assert m[0]["customer_id"] == "CUST-T1" and m[0]["name"] == "Northwind Robotics"


def test_customer_matches(client, monkeypatch):
    monkeypatch.setattr(ca, "list_all_sandboxes", lambda: FAKE_SANDBOXES)
    assert client.get("/v1/customer/matches", params={"q": "acme"}).json()["items"] \
        == [{"customer_id": "ACME-GMBH", "total_quotes": 3}]
    assert len(client.get("/v1/customer/matches", params={"q": ""}).json()["items"]) == 2


def test_web_search_module_has_urllib_parse():
    import importlib
    m = importlib.reload(importlib.import_module("services.web_search"))
    assert hasattr(m, "urllib") and hasattr(m.urllib, "parse")
