"""services.reply_sender — G2c: 报价回复真 SMTP 发送 (egress 主闸内).

铁律①工程化 (与 services/egress_gate.py 对齐):
  1. 任何真实外发必须先过集中闸 check("smtp") — 闸关 → ReplySendError, 不静默降级;
  2. 发件凭据复用邮箱 IMAP 授权码 (services.credentials Fernet 本地解密, 不出本机);
  3. 调用方必须已完成人工批准 (端点层校验 human_approved) — 无人工授权不外发;
  4. 每次发送落审计 data/sends/{cid}.jsonl (收件人/发件人/附件名/闸裁决原因)。
"""
from __future__ import annotations

import json
import logging
import os
import smtplib
import time
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

from services import egress_gate as eg
from services.credentials import load_credentials
from services.profile import load_profile

log = logging.getLogger(__name__)

_send_log_dir = Path("data") / "sends"
_SERVICE_DEFAULT = "qq"
_SMTP_SSL_PORT = 465


class ReplySendError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _mailbox_settings() -> Dict[str, Any]:
    try:
        from services.gmail_api import _load_settings
        return _load_settings() or {}
    except Exception:
        return {}


def _smtp_host() -> str:
    host = (os.environ.get("UEA_MAIL_SMTP_HOST")
            or os.environ.get("EMAIL_SMTP_HOST") or "").strip()
    if host:
        return host
    imap_host = (_mailbox_settings().get("host") or "").strip()
    if imap_host.startswith("imap."):       # imap.qq.com → smtp.qq.com
        return "smtp." + imap_host[len("imap."):]
    return ""


def _mailbox_service() -> str:
    return _mailbox_settings().get("service") or _SERVICE_DEFAULT


def _from_header(account: str, profile: Optional[Dict[str, Any]]) -> str:
    """From 显示名: 有署名 "王磊 <account>", 无则裸 account (行为不回退)."""
    name = str((profile or {}).get("name") or "").strip()
    return f"{name} <{account}>" if name else account


_MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".eml": "message/rfc822",
}


def _attach_file(msg: MIMEMultipart, path: str) -> None:
    p = Path(path)
    mime = _MIME_BY_SUFFIX.get(p.suffix.lower(), "application/octet-stream")
    maintype, subtype = mime.split("/", 1)
    part = MIMEBase(maintype, subtype)
    part.set_payload(p.read_bytes())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename=p.name)
    msg.attach(part)


def send_quote_reply(
    cid: str,
    to_addr: str,
    body: str,
    subject: str,
    quote: Optional[Dict[str, Any]] = None,
    customer: Optional[Dict[str, Any]] = None,
    rfq: Optional[Dict[str, Any]] = None,
    approver: str = "human",
    attachments: Optional[List[Dict[str, Any]]] = None,
    attachments_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """发送报价回复 (草稿全文 + 报价单 PDF/XLSX 附件)。

    门槛 (按序): egress 闸 → 凭据 → SMTP 主机; 人工批准由端点层校验。
    附件: 传入路径优先; 无则按需确定性渲染 (同一 content_sha, 幂等)。
    """
    if not to_addr or "@" not in to_addr:
        raise ReplySendError("bad_to_addr", f"无效收件人: {to_addr!r}")

    decision = eg.check("smtp")
    if not decision.allowed:
        raise ReplySendError("egress_blocked", decision.reason)

    service = _mailbox_service()
    creds = load_credentials(service)
    if not creds:
        raise ReplySendError("no_credentials",
                             f"未找到 {service} 邮箱凭据 (铁律①: 本地 Fernet 加密存储)")

    host = _smtp_host()
    if not host:
        raise ReplySendError("smtp_host_unknown",
                             "无法推导 SMTP 主机 (可设 UEA_MAIL_SMTP_HOST)")

    paths: List[str] = []
    for a in attachments or []:
        p = a.get("path") if isinstance(a, dict) else None
        if p and Path(p).exists():
            paths.append(p)
    if not paths:
        from services.quote_pdf import render_quote_pdf
        from services.quote_xlsx import render_quote_xlsx
        for render in (render_quote_pdf, render_quote_xlsx):
            r = render(quote or {}, cid, out_dir=attachments_dir,
                       customer=customer, rfq=rfq)
            if r.get("ok"):
                paths.append(r["path"])

    profile = load_profile()
    from_name = str(profile.get("name") or "").strip()

    msg = MIMEMultipart("mixed")
    msg["Subject"] = Header(subject or f"Quotation {cid}", "utf-8")
    msg["From"] = _from_header(creds["account"], profile)
    msg["To"] = to_addr
    msg.attach(MIMEText(body or "(empty draft)", "plain", "utf-8"))
    for p in paths:
        _attach_file(msg, p)

    try:
        with smtplib.SMTP_SSL(host, _SMTP_SSL_PORT, timeout=15) as s:
            s.login(creds["account"], creds["password"])
            s.send_message(msg)
    except Exception as e:
        raise ReplySendError("smtp_failed", repr(e))

    record = {"ts": round(time.time(), 3), "context_id": cid, "to": to_addr,
              "from": creds["account"], "from_name": from_name or None,
              "approver": approver, "service": service,
              "smtp_host": host, "subject": str(msg["Subject"]),
              "attachments": [Path(p).name for p in paths],
              "egress_reason": decision.reason}
    try:
        _send_log_dir.mkdir(parents=True, exist_ok=True)
        with (_send_log_dir / f"{cid}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa
        log.warning("[reply-sender] audit write failed: %r", e)

    log.info("[reply-sender] sent %s → %s (%d attachments)", cid, to_addr, len(paths))
    return {"ok": True, "context_id": cid, "to": to_addr, "from_addr": creds["account"],
            "attachments": [Path(p).name for p in paths],
            "audit": str(_send_log_dir / f"{cid}.jsonl")}
