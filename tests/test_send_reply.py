"""tests/test_send_reply.py — B3: 报价单下载端点 + send-reply 真 SMTP 闭环.

铁律①工程化: 发送必须过 egress 集中闸 + 人类批准门槛 + 凭据 (QQ 授权码 Fernet);
审计落 data/sends/{cid}.jsonl; 闸关/未批准 → 诚实拒绝 (不降级静默)。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.api_server import app, _STORE
from services.egress_gate import EgressDecision

CID = "RFQ-TEST-SEND-1"

QUOTE = {"unit_price": 100.0, "final_price": 5000.0, "total_price": 5000.0,
         "currency": "CNY", "lead_time_days": 7, "_source": "test-engine"}
REPLY_FULL = {"subject": "Re: RFQ — quotation", "body": "Dear customer, ...",
              "auto_send": False, "mode": "draft_only",
              "attachments": [{"kind": "quote_pdf", "path": "", "draft_only": True}]}


@pytest.fixture(scope="module")
def api_client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def approved_ctx(tmp_path, monkeypatch):
    """注入已批准 (DONE) context: _STORE + 磁盘 context 文件 + 附件目录."""
    import services.api_server as api
    # 磁盘 context (发送时读全文 reply)
    ctx_dir = tmp_path / "contexts"
    ctx_dir.mkdir(parents=True, exist_ok=True)
    ctx = {
        "context_id": CID, "state": "DONE",
        "rfq": {"material": "6061", "quantity": 50, "surface": "anodized",
                "tolerance_grade": "IT7"},
        "customer": {"name": "Acme", "email": "buyer@acme.cn"},
        "commercial": {"quote": QUOTE},
        "decision": {"reply": dict(REPLY_FULL)},
    }
    (ctx_dir / f"{CID}.json").write_text(json.dumps(ctx, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(api, "_CONTEXTS_DIR_ON_DISK", ctx_dir, raising=False)
    orig = api._rehydrate_from_disk

    def _rehydrate(cid):
        p = ctx_dir / f"{cid}.json"
        if not p.exists():
            return None
        d = json.loads(p.read_text(encoding="utf-8"))
        return {"inputs": {}, "result": {"context_id": cid, "state": d["state"],
                                         "reply": d["decision"]["reply"],
                                         "quote": d["commercial"]["quote"]},
                "customer": d.get("customer") or {}, "email_text": ""}
    monkeypatch.setattr(api, "_rehydrate_from_disk", _rehydrate)
    yield ctx_dir
    _STORE.pop(CID, None)


def _inject_store():
    _STORE[CID] = {
        "inputs": {},
        "result": {"context_id": CID, "state": "DONE",
                   "reply": {"subject": REPLY_FULL["subject"], "auto_send": False,
                             "mode": "draft_only", "attachments_count": 1,
                             "attachment_kinds": ["quote_pdf"], "attachment_error": None},
                   "quote": QUOTE},
        "customer": {"name": "Acme", "email": "buyer@acme.cn"},
        "email_text": "请报价 6061 x50",
    }


# ---- 1) 下载端点 ----

def test_quote_pdf_endpoint(api_client, approved_ctx, monkeypatch, tmp_path):
    import services.api_server as api
    import services.quote_pdf as qp
    monkeypatch.setattr(qp, "DEFAULT_ARTIFACTS_DIR", tmp_path)
    _inject_store()
    r = api_client.get(f"/v1/rfq/{CID}/quote-pdf")
    assert r.status_code == 200, r.text
    assert r.content[:5] == b"%PDF-"
    assert "attachment" in r.headers.get("content-disposition", "")


def test_quote_xlsx_endpoint(api_client, approved_ctx, monkeypatch, tmp_path):
    import services.api_server as api
    import services.quote_xlsx as qx
    monkeypatch.setattr(qx, "DEFAULT_ARTIFACTS_DIR", tmp_path)
    _inject_store()
    r = api_client.get(f"/v1/rfq/{CID}/quote-xlsx")
    assert r.status_code == 200, r.text
    assert r.content[:2] == b"PK"


def test_quote_pdf_unknown_context_404(api_client):
    r = api_client.get("/v1/rfq/RFQ-NOPE-X/quote-pdf")
    assert r.status_code == 404


# ---- 2) send-reply 门槛 ----

def test_send_requires_approval(api_client, approved_ctx):
    """无 human_approved → 409 (铁律①: 无人工授权不外发)."""
    _inject_store()
    r = api_client.post(f"/v1/rfq/{CID}/send-reply",
                        data={"to_addr": "buyer@acme.cn"})
    assert r.status_code == 409
    assert "批准" in r.json()["detail"]


def test_send_blocked_when_egress_closed(api_client, approved_ctx, monkeypatch):
    """闸关闭态 (注入 closed settings, 不依赖本地 settings.yaml 口径) → 409 egress_blocked."""
    import services.config as config
    monkeypatch.setattr(config, "load_settings",
                        lambda: {"egress": {"allow": False, "channels": {"smtp": True}}})
    _inject_store()
    _STORE[CID]["result"]["human_approved"] = {"approver": "human", "ts": 1}
    r = api_client.post(f"/v1/rfq/{CID}/send-reply",
                        data={"to_addr": "buyer@acme.cn"})
    assert r.status_code == 409
    assert "egress_blocked" in r.json()["detail"]


def test_send_ok_with_gate_open(api_client, approved_ctx, monkeypatch, tmp_path):
    """闸开 + 已批准 + 凭据在 + SMTP fake → 200 + 审计落盘."""
    import services.api_server as api
    import services.egress_gate as eg
    import services.reply_sender as rs
    # 附件: 预渲染 PDF, 让 reply.attachments[].path 指向真文件
    from services.quote_pdf import render_quote_pdf
    art = render_quote_pdf(QUOTE, CID, out_dir=tmp_path,
                           customer={"name": "Acme"},
                           rfq={"material": "6061", "quantity": 50})
    ctx_path = approved_ctx / f"{CID}.json"
    d = json.loads(ctx_path.read_text(encoding="utf-8"))
    d["decision"]["reply"]["attachments"][0]["path"] = art["path"]
    ctx_path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(eg, "check", lambda ch, **kw: EgressDecision(ch, True, "test-open"))
    monkeypatch.setattr(rs, "load_credentials",
                        lambda svc: {"service": svc, "account": "sender@qq.com",
                                     "password": "fake-auth-code"})
    sent = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=15):
            sent["host"], sent["port"] = host, port
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def login(self, user, password):
            sent["user"] = user
        def send_message(self, msg):
            sent["to"] = msg["To"]
            sent["subject"] = msg["Subject"]
            sent["payloads"] = [p.get_content_type() for p in msg.get_payload()]

    monkeypatch.setattr(rs.smtplib, "SMTP_SSL", _FakeSMTP)
    monkeypatch.setattr(rs, "_send_log_dir", tmp_path / "sends")

    _inject_store()
    _STORE[CID]["result"]["human_approved"] = {"approver": "human", "ts": 1}
    r = api_client.post(f"/v1/rfq/{CID}/send-reply",
                        data={"to_addr": "buyer@acme.cn", "approver": "human"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True and out["to"] == "buyer@acme.cn"
    assert sent["user"] == "sender@qq.com"
    assert sent["to"] == "buyer@acme.cn"
    assert "text/plain" in sent["payloads"]
    assert "application/pdf" in sent["payloads"]
    # 审计
    log = list((tmp_path / "sends").glob("*.jsonl"))
    assert log and json.loads(log[0].read_text(encoding="utf-8").strip())["to"] == "buyer@acme.cn"
