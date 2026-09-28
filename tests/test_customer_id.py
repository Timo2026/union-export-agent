"""test_customer_id.py — BUG-3 客户 ID 归一: 派生规则 + upsert 别名 + 读路径解析.

覆盖生产单元:
  - services/customer_id.py: normalize_email / derive_customer_id / 规范性 / 垃圾 ID 识别
  - services/crm_memory.py: upsert_customer email 优先派生 + 别名表合并 + 读路径解析
"""
from __future__ import annotations

import re

import pytest

from services.crm_memory import CRMMemory
from services.customer_id import (
    CANONICAL_RE,
    derive_customer_id,
    is_canonical_customer_id,
    is_junk_customer_id,
    normalize_email,
)


class TestNormalizeEmail:
    def test_plain(self):
        assert normalize_email("Alice@Example.COM") == "alice@example.com"

    def test_name_addr_wrapped(self):
        assert normalize_email('"h.keller" <ameskill@example.de>') == "ameskill@example.de"

    def test_display_name_only_kept_lowered(self):
        assert normalize_email("Grossrahmen Kunde") == "grossrahmen kunde"

    def test_empty(self):
        assert normalize_email(None) == ""
        assert normalize_email("") == ""
        assert normalize_email("   ") == ""

    def test_strips_surrounding_space(self):
        assert normalize_email("  a@b.com ") == "a@b.com"


class TestDeriveCustomerId:
    def test_format_canonical(self):
        cid = derive_customer_id({"email": "a@x.com"})
        assert re.match(r"^CUST-[0-9A-F]{8}$", cid), cid

    def test_email_beats_name(self):
        by_email = derive_customer_id({"name": "Northwind Robotics", "email": "n@x.com"})
        by_name_only = derive_customer_id({"name": "Northwind Robotics"})
        assert by_email != by_name_only
        assert by_email == derive_customer_id({"name": "anything", "email": "N@X.com"})

    def test_name_addr_email_normalized(self):
        a = derive_customer_id({"email": "h.keller <ameskill@example.de>"})
        b = derive_customer_id({"email": "ameskill@example.de"})
        assert a == b

    def test_deterministic(self):
        assert derive_customer_id({"email": "a@x.com"}) == derive_customer_id({"email": "a@x.com"})

    def test_name_fallback_when_no_email(self):
        cid = derive_customer_id({"name": "Northwind Robotics"})
        assert cid == "CUST-" + __import__("hashlib").md5(
            "northwind robotics".encode()).hexdigest()[:8].upper()

    def test_anon_fallback(self):
        cid = derive_customer_id({})
        assert is_canonical_customer_id(cid)


class TestJunkDetection:
    @pytest.mark.parametrize("cid", [
        "", "None", "none", "CUST-NEW", "CUST-T1", "sop-test-01", "sop1@x",
        "probe-geo-a_big", "probe-fix-verify@probe.local", "formal-e1@probe.local",
        "geofix", "harness@example.com", "harness@example.de", "http@example.com",
        "final@example.de", "global", "new",
    ])
    def test_junk(self, cid):
        assert is_junk_customer_id(cid) is True

    @pytest.mark.parametrize("cid", [
        "CUST-ABCD1234", "CUST-0001", "CUST-3DB265", "gpumarke@xsuper-557003ae",
        "alice@acme.com", "memtest@qq-1a2b3c4d",
    ])
    def test_not_junk(self, cid):
        assert is_junk_customer_id(cid) is False

    def test_canonical_regex(self):
        assert CANONICAL_RE.match("CUST-0123ABCD")
        assert not CANONICAL_RE.match("CUST-0123abc")   # 小写 hex 不认
        assert not CANONICAL_RE.match("CUST-123")


class TestUpsertDerivation:
    def test_no_id_derives_from_email(self, tmp_path):
        crm = CRMMemory(str(tmp_path / "crm.sqlite3"))
        got = crm.upsert_customer({"name": "Northwind Robotics", "email": "n@x.com"})
        assert got == derive_customer_id({"email": "n@x.com"})
        assert is_canonical_customer_id(got)

    def test_no_id_derives_from_name_when_no_email(self, tmp_path):
        crm = CRMMemory(str(tmp_path / "crm.sqlite3"))
        got = crm.upsert_customer({"name": "Northwind Robotics"})
        assert got == derive_customer_id({"name": "Northwind Robotics"})

    def test_explicit_canonical_id_kept(self, tmp_path):
        crm = CRMMemory(str(tmp_path / "crm.sqlite3"))
        got = crm.upsert_customer({"customer_id": "CUST-DEADBEEF", "name": "A"})
        assert got == "CUST-DEADBEEF"

    def test_explicit_custom_id_kept(self, tmp_path):
        """演示/脚本显式传的自定义 ID (CUST-A/JIEVO...) 原样保留, 不强制归一."""
        crm = CRMMemory(str(tmp_path / "crm.sqlite3"))
        assert crm.upsert_customer({"customer_id": "CUST-A", "name": "A"}) == "CUST-A"
        assert crm.upsert_customer({"customer_id": "JIEVO", "name": "J"}) == "JIEVO"

    def test_registered_alias_merges_into_canonical(self, tmp_path):
        crm = CRMMemory(str(tmp_path / "crm.sqlite3"))
        canon = derive_customer_id({"email": "a@x.com"})
        crm.register_alias("gpumarke@xsuper-557003ae", canon)
        got = crm.upsert_customer({"customer_id": "gpumarke@xsuper-557003ae",
                                   "name": "gpu.market@xsuperzone.com",
                                   "email": "gpu.market@xsuperzone.com"})
        assert got == canon
        rows = [r[0] for r in crm._conn.execute(
            "SELECT customer_id FROM customers").fetchall()]
        assert rows == [canon], "旧 ID 不得另起一行"

    def test_alias_table_created_by_schema(self, tmp_path):
        crm = CRMMemory(str(tmp_path / "crm.sqlite3"))
        crm.register_alias("OLD", "CUST-00000001")
        assert crm.resolve_customer_id("OLD") == "CUST-00000001"


class TestResolve:
    def test_unknown_id_passthrough(self, tmp_path):
        crm = CRMMemory(str(tmp_path / "crm.sqlite3"))
        assert crm.resolve_customer_id("WHATEVER") == "WHATEVER"

    def test_none_passthrough(self, tmp_path):
        crm = CRMMemory(str(tmp_path / "crm.sqlite3"))
        assert crm.resolve_customer_id(None) is None

    def test_history_resolves_alias(self, tmp_path):
        crm = CRMMemory(str(tmp_path / "crm.sqlite3"))
        canon = crm.upsert_customer({"name": "A", "email": "a@x.com"})
        crm.register_alias("CUST-0001", canon)
        crm.write_rfq({"context_id": "RFQ-1",
                       "rfq": {"customer": {"customer_id": canon}, "material": "6061"},
                       "state": "QUOTED"})
        crm.write_quote({"context_id": "RFQ-1",
                         "commercial": {"quote": {"unit_price": 10.0}, "margin_pct": 20.0}},
                        {"status": "ok"}, {"subject": "s", "auto_send": False})
        hist = crm.list_customer_history("CUST-0001")
        assert hist["n"] == 1
        assert hist["quotes"][0]["context_id"] == "RFQ-1"

    def test_pending_for_resolves_alias(self, tmp_path):
        crm = CRMMemory(str(tmp_path / "crm.sqlite3"))
        canon = crm.upsert_customer({"name": "A", "email": "a@x.com"})
        crm.register_alias("CUST-0002", canon)
        crm.write_rfq({"context_id": "RFQ-2",
                       "rfq": {"customer": {"customer_id": canon}, "material": "6061"},
                       "state": "NEW"})
        assert crm.pending_for(customer_id="CUST-0002")[0]["context_id"] == "RFQ-2"
