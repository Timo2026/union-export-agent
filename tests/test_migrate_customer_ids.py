"""test_migrate_customer_ids.py — BUG-3 存量迁移: 合成 fixture 全链验证.

 fixture = 简化版节点数据根:
   data/crm.sqlite3 (customers/rfqs/sandbox_quotes/customer_health/preference_profile)
   data/crm_sandboxes/<cid>.sqlite3 × 若干
   data/rag_vectors.json (ingest collection payload + tenant_ 集合)
   data/orders.json / data/media_docs.json (media_api.REGISTRY 实际路径)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.migrate_customer_ids import migrate  # noqa: E402
from services.customer_id import derive_customer_id  # noqa: E402
from services.crm_memory import CRMMemory  # noqa: E402

SANDBOX_SCHEMA = """
CREATE TABLE IF NOT EXISTS customers(
  customer_id TEXT PRIMARY KEY, name TEXT, contact_name TEXT, email TEXT,
  country TEXT, updated_at REAL);
CREATE TABLE IF NOT EXISTS rfqs(
  context_id TEXT PRIMARY KEY, customer_id TEXT, material TEXT, surface TEXT,
  quantity INTEGER, tolerance TEXT, state TEXT, created_at REAL, payload TEXT);
CREATE TABLE IF NOT EXISTS quotes(
  context_id TEXT PRIMARY KEY, unit_price REAL, final_price REAL, currency TEXT,
  lead_time_days INTEGER, margin_pct REAL, source TEXT, verification_status TEXT,
  reply_subject TEXT, auto_send INTEGER, created_at REAL);
CREATE TABLE IF NOT EXISTS postmortems(
  id INTEGER PRIMARY KEY AUTOINCREMENT, context_id TEXT, outcome TEXT,
  actual_cost REAL, note TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS pricing_model(
  customer_id TEXT PRIMARY KEY, material_coeff REAL DEFAULT 0.0,
  surface_coeff REAL DEFAULT 0.0, tolerance_coeff REAL DEFAULT 0.0,
  quantity_discount REAL DEFAULT 0.0, avg_deviation REAL DEFAULT 0.0,
  win_rate REAL DEFAULT 0.5, total_quotes INTEGER DEFAULT 0,
  total_won INTEGER DEFAULT 0, total_lost INTEGER DEFAULT 0,
  updated_at REAL);
CREATE TABLE IF NOT EXISTS knowledge_base(
  id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id TEXT, category TEXT,
  keyword TEXT, insight TEXT, severity TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS followups(
  id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id TEXT, action TEXT,
  trigger TEXT, result TEXT, created_at REAL);
"""


@pytest.fixture()
def root(tmp_path):
    r = tmp_path / "repo"
    (r / "data").mkdir(parents=True)
    crm = CRMMemory(str(r / "data" / "crm.sqlite3"))
    # 实体A: Northwind Robotics 两个历史 ID (同一 name, 无 email) → 应合并
    crm.upsert_customer({"customer_id": "CUST-0001", "name": "Northwind Robotics",
                         "contact_name": "Alice", "country": "US"})
    crm.upsert_customer({"customer_id": "CUST-3DB265", "name": "Northwind Robotics",
                         "country": "US"})
    # 实体B: gpu.market 两个 ID (同 email, 一个规范格式一个自由格式) → 应合并
    crm.upsert_customer({"customer_id": "CUST-6D3C40",
                         "name": "gpu.market@xsuperzone.com",
                         "email": "gpu.market@xsuperzone.com"})
    crm.upsert_customer({"customer_id": "gpumarke@xsuper-557003ae",
                         "name": "gpu.market@xsuperzone.com",
                         "email": "gpu.market@xsuperzone.com"})
    # 实体C: 干净邮件客户
    crm.upsert_customer({"customer_id": "CUST-45123D",
                         "name": "weixindeveloper@tencent.com",
                         "email": "weixindeveloper@tencent.com"})
    # 垃圾壳: 无历史 → 删
    crm.upsert_customer({"customer_id": "CUST-NEW", "name": "", "email": ""})
    crm.upsert_customer({"customer_id": "CUST-T1", "name": "", "email": ""})
    # 垃圾ID 但有历史 → 归一保留 (不删数据)
    crm.upsert_customer({"customer_id": "harness@example.com", "name": "", "email": ""})
    crm.write_rfq({"context_id": "RFQ-N1", "rfq": {"customer": {"customer_id": "CUST-0001"},
                                                  "material": "6061"}, "state": "QUOTED"})
    crm.write_rfq({"context_id": "RFQ-N2", "rfq": {"customer": {"customer_id": "CUST-3DB265"},
                                                  "material": "6061"}, "state": "NEW"})
    crm.write_rfq({"context_id": "RFQ-G1", "rfq": {"customer": {"customer_id": "CUST-6D3C40"},
                                                  "material": "7075"}, "state": "QUOTED"})
    crm.write_rfq({"context_id": "RFQ-G2", "rfq": {"customer": {"customer_id": "gpumarke@xsuper-557003ae"},
                                                  "material": "7075"}, "state": "NEW"})
    crm.write_rfq({"context_id": "RFQ-H1", "rfq": {"customer": {"customer_id": "harness@example.com"},
                                                  "material": "6061"}, "state": "NEW"})
    crm.add_sandbox_quote("CUST-6D3C40", "RFQ-G1", "7075", "AN", 12.0)
    crm.add_sandbox_quote("gpumarke@xsuper-557003ae", "RFQ-G2", "7075", "AN", 11.0)
    crm.upsert_health("CUST-6D3C40", 70, "low", 3, 2, 1)
    crm.upsert_health("gpumarke@xsuper-557003ae", 60, "med", 1, 0, 1)
    crm.upsert_profile("gpumarke@xsuper-557003ae", price_sensitivity="high")
    crm.close()

    # 沙箱文件: CUST-0001 / CUST-3DB265 (合并) + CUST-6D3C40 / 自由ID (合并)
    # + probe- 空壳 (删) + 无名孤儿非垃圾文件 (改名保留)
    sb_dir = r / "data" / "crm_sandboxes"
    sb_dir.mkdir(parents=True)
    for cid, ctx, email, disp in [
        ("CUST-0001", "RFQ-N1", None, "Northwind Robotics"),
        ("CUST-3DB265", "RFQ-N2", None, "Northwind Robotics"),
        ("CUST-6D3C40", "RFQ-G1", "gpu.market@xsuperzone.com", "gpu.market@xsuperzone.com"),
        ("gpumarke@xsuper-557003ae", "RFQ-G2", "gpu.market@xsuperzone.com", "gpu.market@xsuperzone.com"),
    ]:
        con = sqlite3.connect(str(sb_dir / f"{cid}.sqlite3"))
        con.executescript(SANDBOX_SCHEMA)
        con.execute("INSERT INTO customers(customer_id,name,email,updated_at) VALUES(?,?,?,?)",
                    (cid, disp, email, 1000.0))
        con.execute("INSERT INTO rfqs(context_id,customer_id,material,created_at) VALUES(?,?,?,?)",
                    (ctx, cid, "6061", 1000.0))
        con.commit()
        con.close()
    probe = sb_dir / "probe-geo-a_big.sqlite3"
    con = sqlite3.connect(str(probe))
    con.executescript(SANDBOX_SCHEMA)
    con.commit()
    con.close()

    # 向量库 (JsonFileBackend 格式): ingest payload + tenant_ 旧集合
    (r / "data" / "rag_vectors.json").write_text(json.dumps({
        "ingest_docs": {"media:x": {"id": "media:x", "vector": [0.1],
                                    "payload": {"customer_id": "gpumarke@xsuper-557003ae"}}},
        "tenant_CUST-0001_quotes": {"p1": {"id": "p1", "vector": [0.2],
                                           "payload": {"customer_id": "CUST-0001"}}},
    }), encoding="utf-8")
    # orders / media registry (实际路径: data/media_docs.json = media_api.REGISTRY)
    (r / "data" / "orders.json").write_text(json.dumps(
        {"orders": [{"id": "O1", "customer_id": "CUST-0001"}]}), encoding="utf-8")
    (r / "data" / "media_docs.json").write_text(json.dumps(
        {"docs": [{"id": "d1", "customer_id": "gpumarke@xsuper-557003ae"}]}),
        encoding="utf-8")
    return r / "data"   # migrate() 以数据根为参数


class TestPlan:
    def test_plan_merges_same_email_and_name(self, root):
        rep = migrate(root, apply=False)
        mapping = rep["mapping"]
        canon_n = derive_customer_id({"name": "Northwind Robotics"})
        canon_g = derive_customer_id({"email": "gpu.market@xsuperzone.com"})
        assert mapping["CUST-0001"] == canon_n
        assert mapping["CUST-3DB265"] == canon_n
        assert mapping["CUST-6D3C40"] == canon_g
        assert mapping["gpumarke@xsuper-557003ae"] == canon_g
        assert "CUST-NEW" in rep["deleted"]
        assert "CUST-T1" in rep["deleted"]
        assert "harness@example.com" in mapping   # 有历史 → 归一不删

    def test_dry_run_changes_nothing(self, root):
        before = (root / "crm.sqlite3").read_bytes()
        migrate(root, apply=False)
        assert (root / "crm.sqlite3").read_bytes() == before


class TestApply:
    def test_references_rewritten_and_merged(self, root):
        migrate(root, apply=True)
        crm = CRMMemory(str(root / "crm.sqlite3"))
        canon_n = derive_customer_id({"name": "Northwind Robotics"})
        canon_g = derive_customer_id({"email": "gpu.market@xsuperzone.com"})
        ids = [r[0] for r in crm._conn.execute(
            "SELECT customer_id FROM customers ORDER BY customer_id")]
        assert "CUST-NEW" not in ids and "CUST-T1" not in ids
        assert "CUST-0001" not in ids and "gpumarke@xsuper-557003ae" not in ids
        assert canon_n in ids and canon_g in ids
        rfq_cids = [r[0] for r in crm._conn.execute("SELECT customer_id FROM rfqs")]
        assert set(rfq_cids) <= set(ids)
        sq = [r[0] for r in crm._conn.execute("SELECT customer_id FROM sandbox_quotes")]
        assert set(sq) == {canon_g}
        health = crm.get_health(canon_g)
        assert health["total_quotes"] == 4 and health["won_quotes"] == 2   # 3+1 合并
        prof = crm.get_profile(canon_g)
        assert prof["price_sensitivity"] == "high"   # 合并保留非空偏好
        assert crm.resolve_customer_id("CUST-0001") == canon_n
        assert crm.resolve_customer_id("gpumarke@xsuper-557003ae") == canon_g
        crm.close()

    def test_sandbox_files_merged_renamed_shells_deleted(self, root):
        migrate(root, apply=True)
        sb = root / "crm_sandboxes"
        canon_n = derive_customer_id({"name": "Northwind Robotics"})
        canon_g = derive_customer_id({"email": "gpu.market@xsuperzone.com"})
        assert not (sb / "CUST-0001.sqlite3").exists()
        assert not (sb / "CUST-3DB265.sqlite3").exists()
        assert not (sb / "gpumarke@xsuper-557003ae.sqlite3").exists()
        assert not (sb / "probe-geo-a_big.sqlite3").exists()
        con = sqlite3.connect(str(sb / f"{canon_n}.sqlite3"))
        ctxs = [r[0] for r in con.execute("SELECT context_id FROM rfqs")]
        con.close()
        assert sorted(ctxs) == ["RFQ-N1", "RFQ-N2"]
        con = sqlite3.connect(str(sb / f"{canon_g}.sqlite3"))
        ctxs = [r[0] for r in con.execute("SELECT context_id FROM rfqs")]
        con.close()
        assert sorted(ctxs) == ["RFQ-G1", "RFQ-G2"]

    def test_vector_orders_media_rewritten(self, root):
        migrate(root, apply=True)
        canon_g = derive_customer_id({"email": "gpu.market@xsuperzone.com"})
        canon_n = derive_customer_id({"name": "Northwind Robotics"})
        vec = json.loads((root / "rag_vectors.json").read_text(encoding="utf-8"))
        assert vec["ingest_docs"]["media:x"]["payload"]["customer_id"] == canon_g
        assert f"tenant_{canon_n}_quotes" in vec
        assert "tenant_CUST-0001_quotes" not in vec
        orders = json.loads((root / "orders.json").read_text(encoding="utf-8"))
        assert orders["orders"][0]["customer_id"] == canon_n
        media = json.loads((root / "media_docs.json").read_text(encoding="utf-8"))
        assert media["docs"][0]["customer_id"] == canon_g

    def test_backup_created(self, root):
        rep = migrate(root, apply=True)
        bak = Path(rep["backup"])
        assert bak.exists()
        names = {p.name for p in bak.iterdir()}
        assert "crm.sqlite3" in names

    def test_idempotent_second_run(self, root):
        migrate(root, apply=True)
        rep2 = migrate(root, apply=True)
        assert rep2["changed_customers"] == 0
        assert rep2["deleted"] == []
        assert rep2["renamed_sandboxes"] == 0
