"""tests/test_profile.py — 用户资料/署名设置 (顶栏 + 邮件落款 + SMTP 署名一体).

覆盖 (先红后绿, 2026-09-25):
  services/profile.py:
    1) 无文件 → 默认 profile (王磊/销售主管/WL)
    2) 部分字段 → 与默认合并 (未写字段不丢)
    3) 文件损坏 → 回退默认, 不炸
    4) save → load  round-trip (ensure_ascii=False 落盘中文)
    5) sign_off: signature 非空 → 原样; 空 → name+title 组; 全空 → 兜底串
  services/reply.py build_reply:
    6) 默认 (无显式 profile) → 落款用默认 profile
    7) 显式 profile → 落款用显式值
    8) 损坏 profile 文件 → 默认落款, 不炸
  API:
    9) GET /v1/profile → 200 默认值
    10) POST /v1/profile → 保存回显; GET 反映
    11) POST 部分字段 → 合并不丢
  services/reply_sender.py:
    12) From 头 = "王磊 <account>"; 审计落 from_name
    13) name 空 → From 裸 account (行为不回退)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import profile as prof
from services.api_server import app


@pytest.fixture
def profile_file(tmp_path, monkeypatch):
    """隔离 profile 存储文件 (指向 tmp, 不存在)。"""
    f = tmp_path / "profile.json"
    monkeypatch.setattr(prof, "PROFILE_FILE", f)
    return f


@pytest.fixture
def api_client():
    with TestClient(app) as c:
        yield c


# ---------- 1) 存储 ----------

def test_load_profile_missing_file_returns_defaults(profile_file):
    p = prof.load_profile()
    assert p["name"] == "王磊"
    assert p["title"] == "销售主管"
    assert p["initials"] == "WL"
    assert p["signature"] == ""


def test_load_profile_merges_partial(profile_file):
    profile_file.write_text(json.dumps({"name": "张三"}, ensure_ascii=False), encoding="utf-8")
    p = prof.load_profile()
    assert p["name"] == "张三"
    assert p["title"] == "销售主管"      # 未写字段保留默认
    assert p["initials"] == "WL"


def test_load_profile_corrupt_file_falls_back(profile_file):
    profile_file.write_text("{not json", encoding="utf-8")
    p = prof.load_profile()
    assert p["name"] == "王磊" and p["title"] == "销售主管"


def test_save_profile_roundtrip(profile_file):
    ok = prof.save_profile({"name": "王磊", "title": "销售主管",
                            "initials": "WL", "signature": "王磊 | 销售主管"})
    assert ok is True
    assert profile_file.exists()
    raw = json.loads(profile_file.read_text(encoding="utf-8"))
    assert raw["signature"] == "王磊 | 销售主管"   # 中文不转义
    assert prof.load_profile()["signature"] == "王磊 | 销售主管"


# ---------- 2) sign_off 组款 ----------

def test_sign_off_custom_signature_verbatim():
    s = prof.sign_off({"name": "王磊", "title": "销售主管",
                       "signature": "王磊 | 销售主管\nUnion Export"})
    assert s == "王磊 | 销售主管\nUnion Export"


def test_sign_off_name_title_composed():
    s = prof.sign_off({"name": "张三", "title": "经理", "signature": ""})
    assert s == "张三\n经理"


def test_sign_off_all_empty_uses_fallback():
    s = prof.sign_off({"name": "", "title": "", "signature": ""})
    assert "Union Export" in s


# ---------- 3) build_reply 落款 ----------

CTX_DICT = {
    "context_id": "RFQ-PROFILE-1",
    "rfq": {"material": "6061", "quantity": 50, "surface": "anodized",
            "tolerance_grade": "IT7"},
    "customer": {"name": "Acme", "email": "buyer@acme.cn"},
    "commercial": {"quote": {"unit_price": 100.0, "final_price": 5000.0,
                             "total_price": 5000.0, "currency": "CNY",
                             "lead_time_days": 7}},
}


def test_build_reply_uses_default_profile_when_unspecified(profile_file):
    from services.reply import build_reply
    r = build_reply(CTX_DICT, {"status": "PASS"})
    assert r["body"].endswith("Best regards,\n王磊\n销售主管")


def test_build_reply_uses_explicit_profile(profile_file):
    from services.reply import build_reply
    r = build_reply(CTX_DICT, {"status": "PASS"},
                    profile={"name": "李四", "title": "销售", "signature": ""})
    assert r["body"].endswith("Best regards,\n李四\n销售")


def test_build_reply_uses_signature_field(profile_file):
    from services.reply import build_reply
    r = build_reply(CTX_DICT, {"status": "PASS"},
                    profile={"name": "王磊", "title": "销售主管",
                             "signature": "王磊 | 销售主管 | +86-21-0000"})
    assert r["body"].endswith("Best regards,\n王磊 | 销售主管 | +86-21-0000")


def test_build_reply_corrupt_profile_file_falls_back_to_defaults(profile_file):
    from services.reply import build_reply
    profile_file.write_text("<<<broken", encoding="utf-8")
    r = build_reply(CTX_DICT, {"status": "PASS"})
    assert r["body"].endswith("Best regards,\n王磊\n销售主管")


# ---------- 4) API 端点 ----------

def test_api_get_profile_defaults(api_client, profile_file):
    r = api_client.get("/v1/profile")
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["name"] == "王磊" and p["title"] == "销售主管" and p["initials"] == "WL"


def test_api_post_profile_then_get(api_client, profile_file):
    payload = {"name": "王磊", "title": "销售主管", "initials": "WL",
               "signature": "王磊 | 销售主管"}
    r = api_client.post("/v1/profile", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["saved"] is True
    assert r.json()["profile"]["signature"] == "王磊 | 销售主管"
    g = api_client.get("/v1/profile").json()
    assert g["signature"] == "王磊 | 销售主管"


def test_api_post_profile_partial_merges(api_client, profile_file):
    prof.save_profile({"name": "王磊", "title": "销售主管", "initials": "WL", "signature": ""})
    r = api_client.post("/v1/profile", json={"name": "赵六"})
    assert r.status_code == 200, r.text
    assert r.json()["profile"]["name"] == "赵六"
    assert r.json()["profile"]["title"] == "销售主管"   # 未写字段保留


# ---------- 5) SMTP From 显示名 ----------

def test_from_header_display_name():
    import services.reply_sender as rs
    assert rs._from_header("sender@qq.com", {"name": "王磊"}) == "王磊 <sender@qq.com>"
    assert rs._from_header("sender@qq.com", {"name": "  "}) == "sender@qq.com"
    assert rs._from_header("sender@qq.com", {}) == "sender@qq.com"


def test_send_quote_reply_uses_profile_from_header(profile_file, tmp_path, monkeypatch):
    import services.egress_gate as eg
    import services.reply_sender as rs
    from services.egress_gate import EgressDecision

    prof.save_profile({"name": "王磊", "title": "销售主管", "initials": "WL", "signature": ""})
    monkeypatch.setattr(eg, "check", lambda ch, **kw: EgressDecision(ch, True, "test-open"))
    monkeypatch.setattr(rs, "load_credentials",
                        lambda svc: {"service": svc, "account": "sender@qq.com",
                                     "password": "fake"})
    monkeypatch.setattr(rs, "_send_log_dir", tmp_path / "sends")
    sent = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=15):
            sent["host"] = host
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def login(self, user, password):
            sent["user"] = user
        def send_message(self, msg):
            sent["from"] = msg["From"]

    monkeypatch.setattr(rs.smtplib, "SMTP_SSL", _FakeSMTP)

    out = rs.send_quote_reply(cid="RFQ-PROFILE-SMTP-1", to_addr="buyer@acme.cn",
                              body="Dear customer, ...", subject="Quotation",
                              quote={})
    assert out["ok"] is True
    assert sent["from"] == "王磊 <sender@qq.com>"
    # 审计落 from_name
    log = list((tmp_path / "sends").glob("*.jsonl"))
    assert log, "send audit not written"
    rec = json.loads(log[0].read_text(encoding="utf-8").strip())
    assert rec["from_name"] == "王磊"
