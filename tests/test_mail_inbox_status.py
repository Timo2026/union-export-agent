"""BUG-4 巡检修复: /v1/mail/inbox 每项补顶层 status 聚合字段.

背景 (2026-09-25 订单邮箱总览页巡检): 邮件列表状态列对已过滤邮件显示空 —
inbox 项无顶层 status, 前端 `status ?? pending.state` 兜底链在 pending 被清后
落到 ""。后端按 pending ledger → 分类 filter → 默认 NEW 三级聚合补齐。

口径:
  pending ledger 有 state  → 原样 (NEW/PROCESSING/DONE/HITL/BLOCKED/FAILED/DEAD/SKIPPED)
  无台账 且 filter.kind=skip → SKIPPED (非询价, 等同终态过滤)
  无台账 且 filter.kind=gray → GRAY    (灰区待复核)
  其余 (rfq 分类未入账 / 无分类无台账)  → NEW (未处理)
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from services.api_server import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mailbox_factory(tmp_path, monkeypatch):
    """注入 .eml + meta (可选 filter) + patch pending_index (可选台账)。"""
    import services.mailbox_api as mb
    from services.mail_puller import MailPuller
    mb._MAILBOX_DIR = tmp_path

    def _mk(mail_id, *, filter_kind=None, pending=None):
        (tmp_path / f"{mail_id}.eml").write_bytes(
            b"From: bob@acme.com\r\nTo: sales@union.io\r\n"
            b"Subject: Inquiry AL6061\r\n\r\nPlease quote 100pcs.\r\n")
        meta = {"context_id": f"RFQ-{mail_id}", "badges": ["NEW"]}
        if filter_kind:
            meta["filter"] = {"kind": filter_kind, "score": 1, "reason": "test"}
        (tmp_path / f"{mail_id}.meta.json").write_text(
            json.dumps(meta), encoding="utf-8")
        index = {mail_id: pending} if pending is not None else {}
        monkeypatch.setattr(MailPuller, "pending_index", lambda self: index)

    return _mk


def _item(client, mail_id):
    r = client.get("/v1/mail/inbox")
    assert r.status_code == 200
    return next(i for i in r.json()["items"] if i["mail_id"] == mail_id)


def test_status_from_pending_state(client, mailbox_factory):
    mailbox_factory("st_pend", pending={"state": "HITL", "driver": "email"})
    assert _item(client, "st_pend")["status"] == "HITL"


def test_status_skipped_when_filter_kind_skip_and_no_pending(client, mailbox_factory):
    mailbox_factory("st_skip", filter_kind="skip")
    assert _item(client, "st_skip")["status"] == "SKIPPED"


def test_status_gray_when_filter_kind_gray(client, mailbox_factory):
    mailbox_factory("st_gray", filter_kind="gray")
    assert _item(client, "st_gray")["status"] == "GRAY"


def test_status_new_when_no_filter_no_pending(client, mailbox_factory):
    mailbox_factory("st_new")
    assert _item(client, "st_new")["status"] == "NEW"


def test_status_new_when_rfq_classified_but_no_ledger(client, mailbox_factory):
    mailbox_factory("st_rfq", filter_kind="rfq")
    assert _item(client, "st_rfq")["status"] == "NEW"


def test_pending_state_takes_precedence_over_filter(client, mailbox_factory):
    """台账在 (即使 filter 说 skip, 如 reprocess 覆写后) → 以台账为准。"""
    mailbox_factory("st_mix", filter_kind="skip",
                    pending={"state": "DONE", "driver": "email"})
    assert _item(client, "st_mix")["status"] == "DONE"
