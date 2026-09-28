"""test_flywheel_mount.py — E1 挂载 flywheel_api router 冒烟 (任务 #34).

router 此前从未 include (AUDIT-v7 F2)。沙箱函数在端点模块属性上打桩, 不触真实 sqlite。
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from services.api_server import app
import services.flywheel_api as fa

client = TestClient(app)


class FakeSandbox:
    def __init__(self):
        self.calls = []

    def get_history(self, limit=20):
        return {"quotes": [{"unit_price": 100.0}], "contexts": []}

    def get_pricing_model(self):
        return {"total_quotes": 1}

    def get_knowledge_base(self, limit=10):
        return []

    def write_rfq(self, cid, rfq):
        self.calls.append(("rfq", cid))

    def write_quote(self, cid, quote):
        self.calls.append(("quote", cid))

    def record_postmortem(self, cid, outcome, cost, note):
        self.calls.append(("postmortem", cid, outcome))

    def update_pricing_model(self, a, b, c, dev, won):
        self.calls.append(("model", dev, won))

    def close(self):
        self.calls.append(("close",))


def _patch(monkeypatch):
    fake = FakeSandbox()
    monkeypatch.setattr(fa, "get_sandbox", lambda cid: fake)
    monkeypatch.setattr(fa, "list_all_sandboxes", lambda: [
        {"customer_id": "C1", "total_quotes": 2, "total_won": 1, "total_lost": 1}])
    return fake


def test_flywheel_customers_and_stats_mounted(monkeypatch):
    _patch(monkeypatch)
    r = client.get("/v1/flywheel/customers")
    assert r.status_code == 200 and r.json()["count"] == 1
    s = client.get("/v1/flywheel/stats")
    assert s.status_code == 200
    assert s.json()["total_customers"] == 1 and s.json()["overall_win_rate"] == 0.5


def test_flywheel_record_quote_and_outcome(monkeypatch):
    fake = _patch(monkeypatch)
    q = client.post("/v1/flywheel/customers/C1/quote",
                    json={"rfq": {"context_id": "X1"}, "quote": {"unit_price": 100.0}})
    assert q.status_code == 200 and q.json()["context_id"] == "X1"
    o = client.post("/v1/flywheel/customers/C1/outcome",
                    json={"context_id": "X1", "outcome": "won", "actual_cost": 80.0})
    assert o.status_code == 200
    assert ("model", 25.0, True) in fake.calls       # 偏差 (100-80)/80*100=25%


def test_get_customer_echoes_resolved_id(monkeypatch):
    """BUG-3 归一响应: 旧 ID 请求落到规范沙箱后, 响应须回显规范 ID (S4-8).

    沙箱构造时已过别名解析 (CUST-0001 -> CUST-C4CD93DD); 若端点仍回显
    路径里的旧 ID, 工作台显示与数据来源自相矛盾 (同 BUG-2 前后端状态不一类)。
    """
    fake = FakeSandbox()
    fake.customer_id = "CUST-C4CD93DD"           # 沙箱解析后的规范 ID
    monkeypatch.setattr(fa, "get_sandbox", lambda cid: fake)

    r = client.get("/v1/flywheel/customers/CUST-0001")

    assert r.status_code == 200
    assert r.json()["customer_id"] == "CUST-C4CD93DD"
