"""tests/test_file_intake_zip_attach.py — 邮件 zip 附件实体化 (Z4, 先红后绿).

缺口 (代码实证): mail_orchestrator.run_pipeline 只调 save_image_attachments
(file_intake.py:96) — zip 图纸包附件零实体化, ZIP→BOM→批量报价链在邮箱路径
上从未触发 (zip 邮件断点 2)。

契约 (与 save_image_attachments 同型, 窄 API):
  1) .zip 附件 → 落盘 {stem}_att_{safe}.zip (字节一致 + sha16 + size)
  2) 非 zip 附件 (.png/.pdf/.txt) → 不提 (pdf/dwg 走豁免灰区人工复核, 不自动解包)
  3) 路径穿越名 → safe_filename 清洗, 不出 out 目录
  4) 超限大小 → 拒 (budget, 不炸)
  5) 超过张数上限 → 只提前 N 个
  6) 无附件/eml 不存在 → []
"""
from __future__ import annotations

import email as email_mod
import json
from pathlib import Path
from typing import Any, Dict, List

ZIP_BYTES = b"PK\x03\x04" + b"fake-zip-payload" * 16   # 魔数 + 填充 (只走字节链路)


def _eml_with_zip(tmp: Path, mail_id: str, *,
                  attachments: List[Dict[str, Any]],
                  body: str = "资料包见附件, 请查收。") -> Path:
    """构造带 zip 附件的真实 multipart .eml (maintype=application)."""
    eml_path = tmp / f"{mail_id}.eml"
    eml_path.parent.mkdir(parents=True, exist_ok=True)
    msg = email_mod.message.EmailMessage()
    msg["From"] = "alice@northwind.com"
    msg["To"] = "sales@union-mfg.com"
    msg["Subject"] = f"{mail_id} 赛事资料发放"
    msg["Date"] = "Mon, 21 Sep 2026 10:00:00 +0800"
    msg.set_content(body)
    for att in attachments:
        msg.add_attachment(att["data"], maintype="application", subtype="zip",
                           filename=att["name"])
    eml_path.write_bytes(msg.as_bytes())
    return eml_path


# ---------- 1. zip 附件落盘 ----------
def test_save_zip_attachments_extracts_bytes(tmp_path: Path) -> None:
    from services.file_intake import save_zip_attachments
    eml = _eml_with_zip(tmp_path, "M-ZIP-1",
                        attachments=[{"name": "Timo.zip", "data": ZIP_BYTES}])
    out = tmp_path / "inbound" / "M-ZIP-1"
    got = save_zip_attachments(str(eml), str(out))
    assert len(got) == 1
    a = got[0]
    assert a["name"] == "Timo.zip"
    assert Path(a["path"]).read_bytes() == ZIP_BYTES      # 字节一致
    assert a["sha16"]                                       # 内容指纹在
    assert a["size"] == len(ZIP_BYTES)
    assert Path(a["path"]).parent == out                    # 落在指定 inbound 目录


# ---------- 2. 非 zip 不提 ----------
def test_save_zip_attachments_skips_non_zip(tmp_path: Path) -> None:
    from services.file_intake import save_zip_attachments
    eml = _eml_with_zip(tmp_path, "M-ZIP-2", attachments=[
        {"name": "drawing.png", "data": b"\x89PNG fake"},
        {"name": "spec.pdf", "data": b"%PDF-1.4 fake"},
        {"name": "notes.txt", "data": b"hello"},
    ])
    assert save_zip_attachments(str(eml), str(tmp_path / "atts")) == []


# ---------- 3. 路径穿越名清洗 ----------
def test_save_zip_attachments_sanitizes_traversal_name(tmp_path: Path) -> None:
    from services.file_intake import save_zip_attachments
    eml = _eml_with_zip(tmp_path, "M-ZIP-3",
                        attachments=[{"name": "../../evil.zip", "data": ZIP_BYTES}])
    out = tmp_path / "inbound" / "M-ZIP-3"
    got = save_zip_attachments(str(eml), str(out))
    assert len(got) == 1
    p = Path(got[0]["path"]).resolve()
    assert out.resolve() in p.parents     # safe_filename: 不出 out 目录
    assert ".." not in p.name


# ---------- 4. 超限拒收 ----------
def test_save_zip_attachments_rejects_oversize(tmp_path: Path, monkeypatch) -> None:
    from services import file_intake as fi
    monkeypatch.setattr(fi, "MAX_MAIL_ZIP_BYTES", 64)
    eml = _eml_with_zip(tmp_path, "M-ZIP-4",
                        attachments=[{"name": "big.zip", "data": b"x" * 512}])
    assert fi.save_zip_attachments(str(eml), str(tmp_path / "atts")) == []


# ---------- 5. 张数预算 ----------
def test_save_zip_attachments_caps_count(tmp_path: Path, monkeypatch) -> None:
    from services import file_intake as fi
    monkeypatch.setattr(fi, "MAX_MAIL_ZIPS", 2)
    eml = _eml_with_zip(
        tmp_path, "M-ZIP-5",
        attachments=[{"name": f"a{i}.zip", "data": ZIP_BYTES} for i in range(5)])
    got = fi.save_zip_attachments(str(eml), str(tmp_path / "atts"))
    assert len(got) == 2      # 只提前 N 个 (budget)


# ---------- 6. 无附件 / eml 缺失 ----------
def test_save_zip_attachments_no_attachments(tmp_path: Path) -> None:
    from services.file_intake import save_zip_attachments
    eml = _eml_with_zip(tmp_path, "M-ZIP-6", attachments=[])
    assert save_zip_attachments(str(eml), str(tmp_path / "atts")) == []
    # eml 不存在 → 不炸, 空列表 (与 save_image_attachments 一致)
    assert save_zip_attachments(str(tmp_path / "nope.eml"),
                                str(tmp_path / "atts")) == []


# ---------- 7. orchestrator 接线: 过过滤层的邮件 → zip 落 data/inbound/{mail_id} ----------

class _CapturingCAT:
    """记录 cat.run 收到的 kwargs (zip 链路透传验证)。"""

    def __init__(self):
        self.kwargs: Dict[str, Any] = {}

    def run(self, email_text, customer=None, **kwargs):
        self.kwargs = dict(kwargs, email_text=email_text, customer=customer)
        return {"state": "DONE", "context_id": "RFQ-ZIP-1",
                "verification_status": "PASS", "reasons": []}


def _orch_env(tmp_root: Path):
    from services.mail_puller import MailPuller, PendingEntry, STATE_NEW
    from services.mail_orchestrator import MailOrchestrator
    (tmp_root / "data" / "mailbox").mkdir(parents=True, exist_ok=True)
    puller = MailPuller(root=tmp_root, interval_s=0.5, limit=10, mailbox_factory=None)
    return puller, PendingEntry, STATE_NEW, MailOrchestrator


def test_orchestrator_saves_zip_to_inbound(tmp_root: Path) -> None:
    """真询价 + zip 图纸包 → zip 落 data/inbound/{mail_id}/ (scanner 接手)。"""
    puller, PendingEntry, STATE_NEW, MailOrchestrator = _orch_env(tmp_root)
    eml = _eml_with_zip(tmp_root / "data" / "mailbox", "M-ZORC-1",
                        attachments=[{"name": "Timo.zip", "data": ZIP_BYTES}],
                        body="请报价, 附件是图纸包, 数量 50 件, 6061。")
    (tmp_root / "data" / "mailbox" / "M-ZORC-1.meta.json").write_text(
        json.dumps({"from": "alice@northwind.com", "subject": "RFQ"}), encoding="utf-8")
    puller._append_pending([PendingEntry(mail_id="M-ZORC-1", state=STATE_NEW)])
    orch = MailOrchestrator(root=tmp_root, puller=puller, cat=_CapturingCAT())
    r = orch.run_pipeline("M-ZORC-1")
    assert r.ok is True
    inbound = tmp_root / "data" / "inbound" / "M-ZORC-1"
    zips = list(inbound.glob("*.zip"))
    assert len(zips) == 1
    assert zips[0].read_bytes() == ZIP_BYTES


def test_orchestrator_skipped_mail_saves_no_zip(tmp_root: Path) -> None:
    """非询价 (过滤器判 skip) → 不落 zip: SKIPPED 不进黄金链不白烧 (既有语义)。"""
    puller, PendingEntry, STATE_NEW, MailOrchestrator = _orch_env(tmp_root)
    _eml_with_zip(tmp_root / "data" / "mailbox", "M-ZORC-2",
                  attachments=[{"name": "Timo.zip", "data": ZIP_BYTES}],
                  body="感谢您的参与。")
    (tmp_root / "data" / "mailbox" / "M-ZORC-2.meta.json").write_text(
        json.dumps({"from": "noreply@nvidia.com", "subject": "验证您的电子邮箱地址"}),
        encoding="utf-8")
    puller._append_pending([PendingEntry(mail_id="M-ZORC-2", state=STATE_NEW)])
    orch = MailOrchestrator(root=tmp_root, puller=puller, cat=_CapturingCAT())
    r = orch.run_pipeline("M-ZORC-2")
    assert r.state == "SKIPPED"
    assert not (tmp_root / "data" / "inbound").exists() or not any(
        (tmp_root / "data" / "inbound").rglob("*.zip"))
