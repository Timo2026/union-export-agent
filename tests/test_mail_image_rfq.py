"""tests/test_mail_image_rfq.py — T5 方案B3: 邮件附件图片 VLM→RFQ 补全 (先红后绿, 2026-09-26).

缺口 (代码实证):
  - gmail_imap._msg_to_eml_bytes 只写正文, 附件字节在 IMAP 同步时被丢弃
    (meta 只留 attachments_count) — 生产链附件实体根本不存在。
  - 邮件链无 VLM 图片感知: 上传链 (api_server /v1/analyze) 有
    "[Drawing perception] 并入 body_text" 模式, 邮件黄金链没有 → 客户
    "见图纸报价"只发图片时正文 material/quantity 全空, 只能 HITL。

覆盖 (先红后绿):
  A. file_intake.save_image_attachments 安全落盘 (1-6)
     1) 图片附件 → 提取落盘 (字节一致 + sha16)
     2) 非图片附件 (.pdf) → 不提
     3) 路径穿越名 → safe_filename 清洗不出目录
     4) 超限大小 → 拒 (budget, 不炸)
     5) 超过张数上限 → 只提前 N 张
     6) 无附件 → []
  B. gmail_imap._msg_to_eml_bytes 保留附件 MIME 部件 (7)
  C. CATController.run(image_paths=...) 感知补全 (8-12)
     8) 非 MOCK 感知 → material 从感知文本补齐 (extract_rfq 路由)
     9) MOCK/离线感知 → 不污染抽取输入 (material 仍 None), 证据诚实 mock=True
     10) perceive 抛异常 → 不炸链, 无图片证据
     11) image_paths=None → 无图片证据 (向后兼容)
     12) 多张图片 → 全部感知
  D. orchestrator 附件落盘 → cat.run image_paths (13-14)
  E. mailbox_api GET /v1/mail/{mail_id}/context/image (15-17)
     15) 有图片附件 → images[] 带 _source/_mock 诚实标注
     16) 无图片附件 → ok + reason, 不建 controller (轻路径)
     17) mail 不存在 → 404
"""
from __future__ import annotations

import email as email_mod
import json
from email import policy as email_policy
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient

from services.api_server import app


# ---------- 工具 ----------

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-png-payload" * 8   # 魔数 + 填充 (内容无所谓, 只走字节链路)


def _eml_with_attachment(tmp: Path, mail_id: str, *, attachments: List[Dict[str, Any]],
                         body: str = "Please quote, see attached drawing.") -> Path:
    """构造带附件的真实 multipart .eml (stdlib EmailMessage)."""
    eml_path = tmp / f"{mail_id}.eml"
    eml_path.parent.mkdir(parents=True, exist_ok=True)
    msg = email_mod.message.EmailMessage()
    msg["From"] = "alice@northwind.com"
    msg["To"] = "sales@union-mfg.com"
    msg["Subject"] = f"{mail_id} RFQ bracket"
    msg["Date"] = "Mon, 19 Sep 2026 10:00:00 +0800"
    msg.set_content(body)
    for att in attachments:
        msg.add_attachment(att["data"],
                           maintype="image", subtype="png",
                           filename=att["name"])
    eml_path.write_bytes(msg.as_bytes())
    return eml_path


class FakeFunasr:
    """ perceive_image fake: 固定感知文本 / 显式 MOCK / 可选抛异常。"""

    def __init__(self, perception: str = "Material: 6061 aluminum, quantity 50 pcs, IT7",
                 *, mock: bool = False, raise_exc: Optional[Exception] = None):
        self.perception = perception
        self.mock = mock
        self.raise_exc = raise_exc
        self.calls: List[str] = []

    def perceive_image(self, path: str, prompt: Optional[str] = None) -> Dict[str, Any]:
        self.calls.append(path)
        if self.raise_exc:
            raise self.raise_exc
        return {"ok": True, "perception": self.perception, "_mock": self.mock,
                "_source": "MOCK:offline" if self.mock else "live:vlm:fake-8002"}


class FakeTimo:
    """conflict_check/quote 最小 fake (黄金链后半段不依赖真引擎)。"""

    def conflict_check(self, material, surface, tol, **kw):
        return {"valid": True, "conflicts": [], "_source": "fake"}

    def quote(self, rfq, **kw):
        return {"unit_price": 10.0, "final_price": 500.0, "total_price": 500.0,
                "profit": 100.0, "margin_pct": 20.0, "lead_time_days": 7,
                "_source": "fake"}

    def source_label(self):
        return "fake"


def _make_cat(tmp_path: Path, funasr: Any, timo: Any = None) -> Any:
    from agents.cat_controller import CATController
    return CATController(
        timo=timo if timo is not None else FakeTimo(),
        funasr=funasr,
        policy={},
        settings={"storage": {"contexts_dir": str(tmp_path / "contexts"),
                              "traces_dir": str(tmp_path / "traces")}},
    )


# ---------- A. save_image_attachments ----------

def test_save_image_attachments_extracts_bytes(tmp_path: Path) -> None:
    from services.file_intake import save_image_attachments
    eml = _eml_with_attachment(tmp_path, "M-IMG-1",
                               attachments=[{"name": "drawing.png", "data": PNG_BYTES}])
    out = tmp_path / "atts"
    got = save_image_attachments(str(eml), str(out))
    assert len(got) == 1
    a = got[0]
    assert a["name"] == "drawing.png"
    assert Path(a["path"]).read_bytes() == PNG_BYTES     # 字节一致
    assert a["sha16"]                                     # 内容指纹在
    assert a["size"] == len(PNG_BYTES)


def test_save_image_attachments_skips_non_image(tmp_path: Path) -> None:
    from services.file_intake import save_image_attachments
    eml = _eml_with_attachment(tmp_path, "M-IMG-2",
                               attachments=[{"name": "spec.pdf", "data": b"%PDF-1.4 fake"}])
    got = save_image_attachments(str(eml), str(tmp_path / "atts"))
    assert got == []


def test_save_image_attachments_sanitizes_traversal_name(tmp_path: Path) -> None:
    from services.file_intake import save_image_attachments
    eml = _eml_with_attachment(tmp_path, "M-IMG-3",
                               attachments=[{"name": "../../evil.png", "data": PNG_BYTES}])
    out = tmp_path / "atts"
    got = save_image_attachments(str(eml), str(out))
    assert len(got) == 1
    # safe_filename: 不出 out 目录
    p = Path(got[0]["path"]).resolve()
    assert out.resolve() in p.parents
    assert ".." not in p.name


def test_save_image_attachments_rejects_oversize(tmp_path: Path, monkeypatch) -> None:
    from services import file_intake as fi
    monkeypatch.setattr(fi, "MAX_MAIL_IMAGE_BYTES", 64)
    eml = _eml_with_attachment(tmp_path, "M-IMG-4",
                               attachments=[{"name": "big.png", "data": b"x" * 512}])
    got = fi.save_image_attachments(str(eml), str(tmp_path / "atts"))
    assert got == []          # 超限不落盘, 不炸


def test_save_image_attachments_caps_count(tmp_path: Path, monkeypatch) -> None:
    from services import file_intake as fi
    monkeypatch.setattr(fi, "MAX_MAIL_IMAGES", 2)
    eml = _eml_with_attachment(
        tmp_path, "M-IMG-5",
        attachments=[{"name": f"a{i}.png", "data": PNG_BYTES} for i in range(5)])
    got = fi.save_image_attachments(str(eml), str(tmp_path / "atts"))
    assert len(got) == 2      # 只提前 N 张 (budget)


def test_save_image_attachments_no_attachments(tmp_path: Path) -> None:
    from services.file_intake import save_image_attachments
    eml = _eml_with_attachment(tmp_path, "M-IMG-6", attachments=[])
    got = save_image_attachments(str(eml), str(tmp_path / "atts"))
    assert got == []


# ---------- B. eml 转换保留附件 ----------

def test_msg_to_eml_bytes_keeps_attachments() -> None:
    from services.gmail_imap import GmailMailbox
    msg = type("M", (), {})()
    msg.from_ = "alice@northwind.com"
    msg.to_values = ["sales@union-mfg.com"]
    msg.cc_values = []
    msg.subject = "RFQ with drawing"
    msg.date_str = "Mon, 19 Sep 2026 10:00:00 +0800"
    msg.text = "See attached drawing, please quote."
    msg.html = None
    att = type("A", (), {})()
    att.filename = "drawing.png"
    att.payload = PNG_BYTES
    msg.attachments = [att]

    raw = GmailMailbox._msg_to_eml_bytes(msg)
    parsed = email_mod.message_from_bytes(raw, policy=email_policy.default)
    names = [p.get_filename() for p in parsed.iter_attachments()]
    assert "drawing.png" in names
    # 附件字节可完整取回
    for p in parsed.iter_attachments():
        if p.get_filename() == "drawing.png":
            assert p.get_payload(decode=True) == PNG_BYTES


# ---------- C. CATController.run image_paths ----------

def _ctx_after(cat: Any, result: Dict[str, Any]):
    """run 返回 context_id → engine 工作内存中的 Context (rfq/evidence 真身)。"""
    ctx = cat.ctx_engine.get(result.get("context_id"))
    assert ctx is not None, "run 后 context 必须在 engine 工作内存中"
    return ctx


def _image_evi(ctx: Any) -> List[Any]:
    return [e for e in ctx.evidence if e.source_type == "image"]


def test_cat_run_image_perception_fills_material(tmp_path: Path) -> None:
    cat = _make_cat(tmp_path, FakeFunasr(
        perception="Material: 6061 aluminum. Quantity 50 pcs."))
    img = tmp_path / "d.png"
    img.write_bytes(PNG_BYTES)
    result = cat.run(email_text="Please quote the attached bracket.",
                     customer={"name": "Acme"},
                     image_paths=[str(img)])
    rfq = _ctx_after(cat, result).rfq
    assert rfq.get("material") == "6061"          # 感知文本经 extract_rfq 补齐
    assert rfq.get("quantity") == 50


def test_cat_run_mock_image_does_not_pollute(tmp_path: Path) -> None:
    cat = _make_cat(tmp_path, FakeFunasr(mock=True))
    img = tmp_path / "d.png"
    img.write_bytes(PNG_BYTES)
    result = cat.run(email_text="Please quote the attached bracket.",
                     customer={"name": "Acme"},
                     image_paths=[str(img)])
    ctx = _ctx_after(cat, result)
    # MOCK 感知不进抽取输入 — 不拿假感知当真值
    assert ctx.rfq.get("material") is None
    evi = _image_evi(ctx)
    assert evi and all(e.mock for e in evi)


def test_cat_run_image_perceive_exception_no_crash(tmp_path: Path) -> None:
    cat = _make_cat(tmp_path, FakeFunasr(raise_exc=RuntimeError("vlm exploded")))
    img = tmp_path / "d.png"
    img.write_bytes(PNG_BYTES)
    result = cat.run(email_text="Please quote the attached bracket.",
                     customer={"name": "Acme"},
                     image_paths=[str(img)])
    assert result.get("state") is not None        # 链不断
    assert _image_evi(_ctx_after(cat, result)) == []   # 异常不上假证据


def test_cat_run_image_paths_none_backward_compat(tmp_path: Path) -> None:
    cat = _make_cat(tmp_path, FakeFunasr())
    result = cat.run(email_text="RFQ 6061 50 pcs IT7", customer={"name": "Acme"})
    assert result.get("state") is not None
    assert _image_evi(_ctx_after(cat, result)) == []


def test_cat_run_multiple_images_all_perceived(tmp_path: Path) -> None:
    funasr = FakeFunasr()
    cat = _make_cat(tmp_path, funasr)
    imgs = []
    for i in range(2):
        p = tmp_path / f"d{i}.png"
        p.write_bytes(PNG_BYTES)
        imgs.append(str(p))
    result = cat.run(email_text="Please quote.", customer={"name": "Acme"},
                     image_paths=imgs)
    assert len(funasr.calls) == 2


# ---------- D. orchestrator 接附件 ----------

def _orch_env(tmp_root: Path):
    """puller + orchestrator 环境 (复用既有约定形状)."""
    from services.mail_puller import MailPuller, PendingEntry, STATE_NEW
    from services.mail_orchestrator import MailOrchestrator
    (tmp_root / "data" / "mailbox").mkdir(parents=True, exist_ok=True)
    puller = MailPuller(root=tmp_root, interval_s=0.5, limit=10, mailbox_factory=None)
    return puller, PendingEntry, STATE_NEW, MailOrchestrator


class CapturingCAT:
    """记录 cat.run 收到的 kwargs (图片链路透传验证)。"""

    def __init__(self):
        self.kwargs: Dict[str, Any] = {}

    def run(self, email_text, customer=None, **kwargs):
        self.kwargs = dict(kwargs, email_text=email_text, customer=customer)
        return {"state": "DONE", "context_id": "RFQ-CAP-1",
                "verification_status": "PASS", "reasons": []}


def test_orchestrator_passes_image_paths(tmp_root: Path) -> None:
    from services.mail_puller import STATE_NEW, PendingEntry  # noqa: F401
    puller, PendingEntry, STATE_NEW, MailOrchestrator = _orch_env(tmp_root)
    eml = _eml_with_attachment(tmp_root / "data" / "mailbox", "M-ORC-1",
                               attachments=[{"name": "bracket.png", "data": PNG_BYTES}])
    (tmp_root / "data" / "mailbox" / "M-ORC-1.meta.json").write_text(
        json.dumps({"from": "alice@northwind.com", "subject": "RFQ"}), encoding="utf-8")
    puller._append_pending([PendingEntry(mail_id="M-ORC-1", state=STATE_NEW)])
    cat = CapturingCAT()
    orch = MailOrchestrator(root=tmp_root, puller=puller, cat=cat)
    r = orch.run_pipeline("M-ORC-1")
    assert r.ok is True
    paths = cat.kwargs.get("image_paths") or []
    assert len(paths) == 1
    assert Path(paths[0]).exists() and Path(paths[0]).read_bytes() == PNG_BYTES


def test_orchestrator_no_image_no_paths(tmp_root: Path) -> None:
    puller, PendingEntry, STATE_NEW, MailOrchestrator = _orch_env(tmp_root)
    _eml_with_attachment(tmp_root / "data" / "mailbox", "M-ORC-2", attachments=[])
    (tmp_root / "data" / "mailbox" / "M-ORC-2.meta.json").write_text(
        json.dumps({"from": "alice@northwind.com", "subject": "RFQ"}), encoding="utf-8")
    puller._append_pending([PendingEntry(mail_id="M-ORC-2", state=STATE_NEW)])
    cat = CapturingCAT()
    orch = MailOrchestrator(root=tmp_root, puller=puller, cat=cat)
    r = orch.run_pipeline("M-ORC-2")
    assert r.ok is True
    assert (cat.kwargs.get("image_paths") or []) == []


# ---------- E. mailbox_api context/image 端点 ----------

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mailbox_dir(tmp_path, monkeypatch):
    import services.mailbox_api as mb
    mb._MAILBOX_DIR = tmp_path
    monkeypatch.setattr(mb, "_MAILBOX_DIR", tmp_path, raising=False)
    return tmp_path


def test_context_image_zone_with_image(client, mailbox_dir, monkeypatch) -> None:
    import services.mailbox_api as mb
    mb_dir = mailbox_dir
    _eml_with_attachment(mb_dir, "IMG-ZONE-1",
                         attachments=[{"name": "drawing.png", "data": PNG_BYTES}])
    (mb_dir / "IMG-ZONE-1.meta.json").write_text(json.dumps({"badges": ["NEW"]}), encoding="utf-8")
    monkeypatch.setattr(mb, "_image_funasr", lambda: FakeFunasr(), raising=False)
    r = client.get("/v1/mail/IMG-ZONE-1/context/image")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert d["count"] == 1
    assert d["images"][0]["name"] == "drawing.png"
    assert d["images"][0]["_source"] == "live:vlm:fake-8002"
    assert d["images"][0]["_mock"] is False


def test_context_image_zone_no_image(client, mailbox_dir) -> None:
    _eml_with_attachment(mailbox_dir, "IMG-ZONE-2", attachments=[])
    (mailbox_dir / "IMG-ZONE-2.meta.json").write_text(json.dumps({"badges": ["NEW"]}), encoding="utf-8")
    r = client.get("/v1/mail/IMG-ZONE-2/context/image")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert d["count"] == 0
    assert d["images"] == []
    assert d["reason"] == "no image attachment"


def test_context_image_zone_mail_404(client, mailbox_dir) -> None:
    r = client.get("/v1/mail/NOPE-404/context/image")
    assert r.status_code == 404
