"""旧 ID 别名解析 — BUG-3 归一后的沙箱入口防复活 (S4-8 公网 E2E 发现).

背景: 节点 migrate 后 GET /v1/flywheel/customers/CUST-0001 (旧 ID) 返回 200,
且 _ensure_sandbox 按传入 ID 无条件建文件 → 磁盘上新生成 CUST-0001.sqlite3,
非规范 ID 经 API 复活。修复: 构造沙箱前先过 customer_id_aliases 解析。
"""
import sqlite3

import services.sandbox as sbx


def _mk_global(path, aliases):
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE IF NOT EXISTS customer_id_aliases("
                 "old_id TEXT PRIMARY KEY, canonical_id TEXT, created_at REAL)")
    for old, new in aliases.items():
        conn.execute("INSERT OR REPLACE INTO customer_id_aliases"
                     "(old_id,canonical_id,created_at) VALUES(?,?,?)",
                     (old, new, 1.0))
    conn.commit()
    conn.close()


def test_old_id_resolves_to_canonical_sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(sbx, "SANDBOX_DIR", tmp_path)
    monkeypatch.setattr(sbx, "_GLOBAL_DB", tmp_path / "crm.sqlite3")
    _mk_global(tmp_path / "crm.sqlite3", {"CUST-0001": "CUST-C4CD93DD"})
    # 规范沙箱已在盘上 (代表迁移合并后的真数据)
    (tmp_path / "CUST-C4CD93DD.sqlite3").write_bytes(b"")

    sb = sbx.CustomerSandbox("CUST-0001")

    assert sb.customer_id == "CUST-C4CD93DD"
    assert sb.db_path.name == "CUST-C4CD93DD.sqlite3"
    assert not (tmp_path / "CUST-0001.sqlite3").exists(), \
        "旧 ID 被当新客户建了空沙箱 (非规范 ID 复活)"


def test_unaliased_id_passes_through(tmp_path, monkeypatch):
    monkeypatch.setattr(sbx, "SANDBOX_DIR", tmp_path)
    monkeypatch.setattr(sbx, "_GLOBAL_DB", tmp_path / "crm.sqlite3")
    _mk_global(tmp_path / "crm.sqlite3", {"CUST-0001": "CUST-C4CD93DD"})

    sb = sbx.CustomerSandbox("sop-test-01")

    assert sb.customer_id == "sop-test-01"
    assert sb.db_path.name == "sop-test-01.sqlite3"


def test_no_global_db_or_no_table_is_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(sbx, "SANDBOX_DIR", tmp_path)
    monkeypatch.setattr(sbx, "_GLOBAL_DB", tmp_path / "absent.sqlite3")

    sb = sbx.CustomerSandbox("CUST-0001")

    assert sb.customer_id == "CUST-0001"
