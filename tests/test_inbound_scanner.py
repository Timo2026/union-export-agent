"""test_inbound_scanner.py — inbound 自动扫描 + 幂等 + ZIP 解包 + BOM 报价入口.

覆盖 2026-09-23 新增的 services/inbound_scanner.py:
  1) discover: 发现 zip / BOM xlsx, 跳过 *_extracted/ 子树 (防重复报价)
  2) item_key: 内容级幂等键 (path+mtime_ns+size)
  3) scan 幂等: 同内容二次扫描 → skipped_done, 不重复入队; 文件改动 → 重新入队
  4) run_pending: 状态机 NEW→PROCESSING→DONE/FAILED, 异常不外溢
  5) ZIP 路径: extract_zip 解包 + 产物内 BOM 报价, 无 BOM 时只登记清单
  6) kind=bom 直达路径: 对 inbound/**/*BOM*.xlsx 直接报价

全部用假 controller / 临时目录, 不跑真实 410 项, 零网络。
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from services import inbound_scanner as ibs


class _FakeTimo:
    """假 timo: step_geometry 只回显参数并谎称失败 → parse_step 得 ok=False,
    以此验证 STEP 缺失/解析失败时批处理仍可继续 (显式标注, 不崩)。"""

    def step_geometry(self, path, material="6061"):
        return {"error": "fake: no geometry"}

    def step_features(self, path):
        return {"error": "fake: no features"}


class _FakeCtrl:
    """记录 run() 调用的假控制器, 避免真跑黄金链。"""

    def __init__(self):
        self.calls = []
        self.timo = _FakeTimo()

    def run(self, email_text="", customer=None, step_facts=None, **kw):
        self.calls.append({"email_text": email_text, "customer": customer,
                           "step_facts": step_facts, **kw})
        return {"state": "DONE", "quote": {"unit_price": 1.0}}


@pytest.fixture
def sc(tmp_path, monkeypatch):
    """隔离 root: inbound/ 与 data/inbound_scanner/ 都在 tmp 下。"""
    (tmp_path / "data" / "inbound").mkdir(parents=True)
    s = ibs.InboundScanner(root=tmp_path, controller=_FakeCtrl())
    return s


def _mk_bom_xlsx(p: Path) -> Path:
    """最小 BOM xlsx (openpyxl), 表头含 物料编码/名称/规格/数量。"""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["序号", "物料编码", "名称", "规格", "数量", "单价", "总价", "备注"])
    ws.append([1, "1010001", "测试外壳", "6061铝合金+喷砂", 2, None, None, None])
    ws.append([2, "1010002", "测试臂座", "6061铝合金+阳极氧化", 1, None, None, None])
    p.parent.mkdir(parents=True, exist_ok=True)
    wb.save(p)
    return p


def _mk_step(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
    return p


# ---------- 1) discover ----------
def test_discover_finds_bom_and_zip(sc, tmp_path):
    _mk_bom_xlsx(tmp_path / "data" / "inbound" / "proj" / "批次BOM.xlsx")
    z = tmp_path / "data" / "inbound" / "proj" / "图纸包.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a.stp", "ISO-10303-21;")
    found = sc.discover()
    kinds = {f["kind"] for f in found}
    assert kinds == {"bom", "zip"}, kinds
    assert len(found) == 2


def test_discover_skips_extracted_subtree(sc, tmp_path):
    """*_extracted/ 是解包产物, 必须跳过, 否则同一份 BOM 被两条路径重复报价。"""
    _mk_bom_xlsx(tmp_path / "data" / "inbound" / "p.zip_extracted" / "BOM.xlsx")
    assert sc.discover() == []


def test_discover_ignores_non_bom_excel(sc, tmp_path):
    """文件名不含 bom/报价/物料 的 xlsx 不当 BOM (如随机表格)。"""
    _mk_bom_xlsx(tmp_path / "data" / "inbound" / "随机资料.xlsx")
    assert sc.discover() == []


# ---------- 2) item_key ----------
def test_item_key_changes_with_content(sc, tmp_path):
    f = tmp_path / "a.xlsx"
    _mk_bom_xlsx(f)
    k1 = ibs.item_key(f)
    assert len(k1) == 16 and k1
    k2 = ibs.item_key(f)
    assert k1 == k2, "同文件同键"
    # 内容变化 → mtime_ns 变 → key 变 → 自然重新入队
    import os
    st = f.stat()
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    assert ibs.item_key(f) != k1


# ---------- 3) scan 幂等 ----------
def test_scan_is_idempotent(sc, tmp_path):
    f = _mk_bom_xlsx(tmp_path / "data" / "inbound" / "BOM.xlsx")
    r1 = sc.scan()
    assert r1 == {"discovered": 1, "new": 1, "requeued": 0,
                  "skipped_done": 0, "pending": 1}, r1
    r2 = sc.scan()
    assert r2["new"] == 0 and r2["skipped_done"] == 1, r2

    # 文件被改 → mtime 变 → key 变 → 新 item 入队 (旧 key 仍留在 NEW/终态保留)
    import os
    st = f.stat()
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    r3 = sc.scan()
    assert r3["new"] == 1 and r3["skipped_done"] == 0, r3
    assert len(sc._load_items()) == 2, r3


def test_scan_dry_run_writes_nothing(sc, tmp_path):
    _mk_bom_xlsx(tmp_path / "data" / "inbound" / "BOM.xlsx")
    r = sc.scan(dry_run=True)
    assert r["new"] == 1 and r["pending"] == 0
    assert not sc.pending_path.exists(), "dry-run 不得落状态文件"
    assert sc.status()["total"] == 0


# ---------- 4) run_pending 状态机 ----------
def test_run_pending_bom_done(sc, tmp_path, monkeypatch):
    """kind=bom: 直接报价 → DONE, 报告落盘, stats 正确。"""
    bom = _mk_bom_xlsx(tmp_path / "data" / "inbound" / "BOM.xlsx")
    _mk_step(bom.parent / "1010001-测试外壳-V1.0.STEP")
    _mk_step(bom.parent / "1010002-测试臂座-V1.0.STEP")
    monkeypatch.setattr(ibs.time, "time", lambda: 1790000000.0)
    sc.scan()
    r = sc.run_pending()
    assert r["processed"] == 1 and r["done"] == 1 and r["failed"] == 0, r
    items = list(sc._load_items().values())
    assert items[0]["state"] == "DONE"
    res = items[0]["result"]
    assert res["ok"] is True and res["state"] == "DONE"
    assert res["n_rows"] == 2, res          # 假 controller 让两行都出价
    assert res["sum_total"] == 3.0, res     # (1+2)*1.0
    assert Path(res["report"]).is_file()
    rep = json.loads(Path(res["report"]).read_text(encoding="utf-8"))
    assert rep["stats"]["n_rows"] == 2 and rep["stats"]["n_quoted"] == 2


def test_run_pending_failure_recorded_not_raised(sc, tmp_path, monkeypatch):
    """报价抛异常 → FAILED 落状态, 不外溢 (扫描器不能因单项崩掉)。"""
    _mk_bom_xlsx(tmp_path / "data" / "inbound" / "BOM.xlsx")

    class _Boom:
        @property
        def timo(self):
            raise RuntimeError("控制器构建失败")

        def run(self, *a, **kw):
            raise RuntimeError("控制器构建失败")

    s2 = ibs.InboundScanner(root=tmp_path, controller=_Boom())
    s2.scan()
    r = s2.run_pending()
    assert r["processed"] == 1 and r["failed"] == 1, r
    it = list(s2._load_items().values())[0]
    assert it["state"] == "FAILED"
    assert "控制器构建失败" in str(it["error"]), it["error"]


def test_run_pending_empty_when_nothing_new(sc):
    r = sc.run_pending()
    assert r == {"processed": 0, "done": 0, "failed": 0}


# ---------- 5) ZIP 路径 ----------
def test_zip_extract_and_quote(sc, tmp_path):
    """ZIP 内含 BOM + STEP → 解包 → 报价 → DONE; 解包目录带 _extracted 后缀。"""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["序号", "物料编码", "名称", "规格", "数量"])
    ws.append([1, "1010001", "ZIP件", "6061铝合金", 3])
    import io
    buf = io.BytesIO()
    wb.save(buf)
    z = tmp_path / "data" / "inbound" / "图纸包.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("bom/BOM.xlsx", buf.getvalue())
        zf.writestr("drawings/1010001-ZIP件-V1.0.STEP", "ISO-10303-21;")
    sc.scan()
    r = sc.run_pending()
    assert r["done"] == 1, r
    res = list(sc._load_items().values())[0]["result"]
    assert res["n_files"] == 2 and res["n_step"] == 1
    assert res["extract_dir"].endswith("_extracted")
    # ZIP 内 BOM 已被报价
    assert res["quotes"] and res["quotes"][0]["report"]["n_rows"] == 1
    assert res["quotes"][0]["report"]["sum_total"] == 3.0
    # 解包产物不得再被发现 (否则同一份 BOM 被两条路径重复报价)
    # discover() 仍返回原始 zip 本身, 但不得出现 bom/excel 类解包产物
    rediscovered = [f for f in sc.discover() if f["kind"] != "zip"]
    assert rediscovered == [], rediscovered


def test_zip_without_bom_only_registers_files(sc, tmp_path):
    """解包成功但无 BOM → DONE + note, 不报错 (只有 STEP/PDF 也合法投递)。"""
    z = tmp_path / "data" / "inbound" / "只有图纸.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a.stp", "ISO-10303-21;")
        zf.writestr("b.pdf", "%PDF-1.4")
    sc.scan()
    r = sc.run_pending()
    assert r["done"] == 1, r
    res = list(sc._load_items().values())[0]["result"]
    assert res["n_files"] == 2 and "note" in res


# ---------- 6) status / tick ----------
def test_status_counts(sc, tmp_path):
    _mk_bom_xlsx(tmp_path / "data" / "inbound" / "BOM.xlsx")
    sc.scan()
    st = sc.status()
    assert st["total"] == 1 and st["by_state"] == {"NEW": 1}
    assert st["inbound_exists"] is True


def test_tick_scan_then_run(sc, tmp_path):
    _mk_bom_xlsx(tmp_path / "data" / "inbound" / "BOM.xlsx")
    out = sc.tick()
    assert out["scan"]["new"] == 1
    assert out["run"]["done"] == 1
    assert sc.status()["by_state"]["DONE"] == 1
