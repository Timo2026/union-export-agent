"""list_all_sandboxes 必须过滤杂散/隐藏/非客户 sqlite 文件 (B3 缺陷修复 #30).

回归背景: data/crm_sandboxes 里曾出现 .sqlite3 / .sqlite3.sqlite3 / None.sqlite3 /
global.sqlite3 / NEW.sqlite3 / X.sqlite3 等杂散文件 (坏 cid 写入产物)。
glob('*.sqlite3').stem 把它们当成 customer_id, 导致 /v1/flywheel/customers
返回 customer_id='.sqlite3' 的幽灵客户。

合法 customer_id 形如 CUST-0001 / CUST-A-SBX (短横线分段 token)。
"""
import services.sandbox as sbx


def _mk(dirpath, name):
    (dirpath / name).write_bytes(b"")


def test_stray_hidden_and_junk_sqlite_excluded(tmp_path, monkeypatch):
    monkeypatch.setattr(sbx, "SANDBOX_DIR", tmp_path)
    for junk in [".sqlite3", ".sqlite3.sqlite3", "None.sqlite3",
                 "global.sqlite3", "NEW.sqlite3", "X.sqlite3"]:
        _mk(tmp_path, junk)
    cids = {r["customer_id"] for r in sbx.list_all_sandboxes()}
    assert ".sqlite3" not in cids
    assert "None" not in cids
    assert "global" not in cids
    assert "NEW" not in cids
    assert "X" not in cids
    assert all(not c.startswith(".") for c in cids)


def test_valid_customer_sandboxes_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(sbx, "SANDBOX_DIR", tmp_path)
    _mk(tmp_path, ".sqlite3")
    _mk(tmp_path, "CUST-0001.sqlite3")
    _mk(tmp_path, "CUST-A-SBX.sqlite3")
    cids = {r["customer_id"] for r in sbx.list_all_sandboxes()}
    assert "CUST-0001" in cids
    assert "CUST-A-SBX" in cids
    assert ".sqlite3" not in cids
