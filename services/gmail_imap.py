"""gmail_imap.py — Gmail IMAP 拉信封装 (imap_tools, Apache-2.0).

铁律①对齐:
- 凭据从 services.credentials 读 (Fernet 解密), 不存 plaintext, 不外发
- 默认禁用 (services/skill_config + settings 双重门禁)
- 拉的邮件只写本地 data/mailbox/*.eml, 不外发
- IMAP 不可达 → 返回 error, 不静默冒充
- 测试用 monkeypatch imap_tools.MailBox 注入 mock, 不真连
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from .credentials import load_credentials

log = logging.getLogger(__name__)
SERVICE_NAME = "gmail"
DEFAULT_HOST = "imap.gmail.com"
QQ_HOST = "imap.qq.com"
DEFAULT_PORT = 993
DEFAULT_FOLDER = "INBOX"
# Round C (2026-09-24): 全会话 socket 级超时. imaplib 用 socket.create_connection
# 建同一 socket 贯穿 login/fetch/flag, 故 timeout 一旦设定即覆盖整条会话 —
# 半开连接 (TCP 通了但对端永不应答) 不再能挂死 puller 线程.
IMAP_TIMEOUT_S = 30.0


class GmailMailbox:
    """IMAP 拉信封装. service 参数 = credentials 键 + 来源标签 (gmail/qq/...)."""

    def __init__(
        self,
        mailbox_dir: Optional[Path] = None,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        mailbox_factory: Optional[Callable[[str, int], Any]] = None,
        service: str = SERVICE_NAME,
        timeout: Optional[float] = IMAP_TIMEOUT_S,
    ):
        self.mailbox_dir = Path(mailbox_dir) if mailbox_dir else Path("data/mailbox")
        self.host = host
        self.port = port
        self.service = service
        self.timeout = timeout
        self._factory = mailbox_factory
        self._client = None
        self.last_sync_at: Optional[float] = None
        self.last_error: Optional[str] = None
        self.last_count: int = 0
        self.last_account: Optional[str] = None

    def _make_client(self):
        if self._factory:
            return self._factory(self.host, self.port)
        from imap_tools import MailBox
        return MailBox(self.host, port=self.port, timeout=self.timeout)

    def connect(self) -> Dict[str, Any]:
        cred = load_credentials(self.service)
        if not cred:
            self.last_error = "no credentials saved"
            return {"ok": False, "error": self.last_error}
        try:
            client = self._make_client()
            client.login(cred["account"], cred["password"])
            self._client = client
            self.last_account = cred["account"]
            self.last_error = None
            return {"ok": True, "account": cred["account"], "host": self.host, "port": self.port}
        except Exception as e:
            self.last_error = repr(e)
            self._client = None
            return {"ok": False, "error": repr(e), "host": self.host}

    def disconnect(self) -> None:
        if self._client is not None:
            try:
                self._client.logout()
            except Exception:
                pass
            self._client = None

    def _mail_id_for(self, uid: str, msg_date: str, msg_from: str) -> str:
        raw = f"{uid}|{msg_date}|{msg_from}".encode("utf-8", errors="ignore")
        return self.service + "_" + hashlib.sha256(raw).hexdigest()[:16]

    @staticmethod
    def _addr_to_str(addr: Any) -> str:
        # imap_tools>=1.10 返回 EmailAddress(name, email) 对象而非 str
        name = getattr(addr, "name", None)
        email = getattr(addr, "email", None)
        if email is None:
            return str(addr)
        return f"{name} <{email}>" if name else str(email)

    @staticmethod
    def _clean_header(value: Any) -> str:
        # RFC2047 折叠头解码后可能含 \r\n, email 库拒绝 → 压平防头注入
        return " ".join(str(value or "").split())

    @classmethod
    def _msg_to_eml_bytes(cls, msg) -> bytes:
        em = EmailMessage()
        em["From"] = cls._clean_header(msg.from_)
        if msg.to_values:
            em["To"] = cls._clean_header(", ".join(cls._addr_to_str(a) for a in msg.to_values))
        if msg.cc_values:
            em["Cc"] = cls._clean_header(", ".join(cls._addr_to_str(a) for a in msg.cc_values))
        em["Subject"] = cls._clean_header(msg.subject)
        if msg.date_str:
            em["Date"] = cls._clean_header(msg.date_str)
        body = msg.text or msg.html or ""
        em.set_content(body)
        # T5 B3: 附件字节实体化。此前只写正文 + meta 计数, 图纸/图片附件在
        # IMAP 同步时被整体丢弃 → "见图纸报价" 的图片证据在邮件链根本不存在。
        for att in getattr(msg, "attachments", None) or []:
            try:
                payload = getattr(att, "payload", None)
                fname = getattr(att, "filename", None)
                if not payload or not fname:
                    continue
                if isinstance(payload, (bytes, bytearray)):
                    data = bytes(payload)
                else:
                    data = str(payload).encode("utf-8", "ignore")
                maintype, subtype = cls._att_content_type(att, str(fname))
                em.add_attachment(data, maintype=maintype, subtype=subtype,
                                  filename=cls._clean_header(fname))
            except Exception as e:  # noqa — 单附件失败不拖垮整封信落盘
                log.warning("[gmail_imap] attachment %r dropped: %r",
                            getattr(att, "filename", "?"), repr(e))
        return em.as_bytes()

    @staticmethod
    def _att_content_type(att: Any, fname: str) -> Tuple[str, str]:
        """附件 content-type: 优先 imap_tools 头值, 回落扩展名猜测, 兜底 octet-stream。"""
        ct = str(getattr(att, "content_type", "") or "").strip().lower()
        if "/" in ct:
            maintype, _, subtype = ct.partition("/")
            if maintype and subtype:
                return maintype, subtype
        import mimetypes
        guessed, _ = mimetypes.guess_type(fname)
        if guessed and "/" in guessed:
            maintype, _, subtype = guessed.partition("/")
            if maintype and subtype:
                return maintype, subtype
        return "application", "octet-stream"

    def sync(self, folder: str = DEFAULT_FOLDER, limit: int = 50,
             dedup_check: Optional[Callable[[str, str, str], bool]] = None,
             note_content: Optional[Callable[[str, str], None]] = None) -> Dict[str, Any]:
        """拉取未读邮件 → 落 .eml + .meta.json.

        2026-09-24 邮件接口修复 (用户: "完成报价回复后再标记已读, 避免重复"):
          - criteria='UNSEEN' + mark_seen=False: 只拉未读, 且**拉取阶段绝不提前
            标 \\Seen — 处理成功后才由 mark_read 标, 崩溃重启可重拉不丢信。
          - dedup_check(signature, from, subject) -> bool: 内容指纹回调 (由
            MailPuller 注入 content_index); 命中 → 判定为重复投递, 不建 .eml,
            直接服务器端标 \\Seen (无需处理), 计入 deduped。
          - note_content(signature, mail_id): 新邮件落盘后回调, 让同批次后到的
            同内容邮件也能即时判重。
        """
        if self._client is None:
            r = self.connect()
            if not r.get("ok"):
                return {"ok": False, "error": r.get("error"), "fetched": 0, "skipped": 0}
        self.mailbox_dir.mkdir(parents=True, exist_ok=True)
        fetched = 0
        skipped = 0
        deduped = 0
        try:
            self._client.folder.set(folder)
            for msg in self._client.fetch(criteria="UNSEEN", mark_seen=False,
                                          limit=limit, reverse=True):
                uid = str(msg.uid)
                mid = self._mail_id_for(uid, msg.date_str or "", msg.from_ or "")
                eml_path = self.mailbox_dir / f"{mid}.eml"
                meta_path = self.mailbox_dir / f"{mid}.meta.json"
                if eml_path.exists():
                    skipped += 1
                    continue
                # 内容去重: 同内容换 UID 重投 → 直接标已读, 不建副本 (EDRM MIH 思路)
                sig = ""
                if dedup_check is not None:
                    try:
                        from services.mail_classifier import content_signature
                        sig = content_signature(msg.from_ or "", msg.subject or "",
                                                msg.text or msg.html or "")
                        if dedup_check(sig, msg.from_ or "", msg.subject or ""):
                            self._client.flag(uid, ("\\Seen",), True)
                            deduped += 1
                            continue
                    except Exception as e:
                        log.warning("[gmail_imap] dedup_check failed for %s: %r", uid, e)
                eml_bytes = self._msg_to_eml_bytes(msg)
                eml_path.write_bytes(eml_bytes)
                meta = {
                    "uid": uid,
                    "folder": folder,
                    "account": self.last_account,
                    "received_at": time.time(),
                    "context_id": None,
                    "customer_id": None,
                    "badges": ["NEW", self.service.upper() + "_PULLED"],
                    "source": self.service + "-imap",
                    "from": msg.from_ or "",
                    "subject": msg.subject or "",
                    "size_bytes": len(eml_bytes),
                    "attachments_count": len(msg.attachments or []),
                }
                meta_path.write_text(
                    json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                fetched += 1
                if note_content is not None and sig:
                    try:
                        note_content(sig, mid)
                    except Exception as e:
                        log.warning("[gmail_imap] note_content failed for %s: %r",
                                    mid, e)
        except Exception as e:
            self.last_error = repr(e)
            return {
                "ok": False,
                "error": repr(e),
                "fetched": fetched,
                "skipped": skipped,
                "deduped": deduped,
                "folder": folder,
            }
        self.last_sync_at = time.time()
        self.last_count = fetched
        self.last_error = None
        return {
            "ok": True,
            "fetched": fetched,
            "skipped": skipped,
            "deduped": deduped,
            "folder": folder,
            "mailbox_dir": str(self.mailbox_dir),
        }

    def mark_read(self, uid: str, folder: str = DEFAULT_FOLDER) -> Dict[str, Any]:
        """显式标记已读: STORE \\Seen=True (imap_tools flag).

        只在邮件处理到终态后调用 (orchestrator / send-reply 端点) — 拉取阶段
        绝不调用 (sync 用 mark_seen=False)。失败显式返回 ok=False, 不静默。
        """
        if self._client is None:
            r = self.connect()
            if not r.get("ok"):
                return {"ok": False, "error": r.get("error", "connect failed"),
                        "uid": uid}
        try:
            self._client.folder.set(folder)
            self._client.flag(uid, ("\\Seen",), True)
            return {"ok": True, "uid": uid, "folder": folder, "flag": "\\Seen"}
        except Exception as e:
            self.last_error = repr(e)
            return {"ok": False, "error": repr(e), "uid": uid, "folder": folder}

    def status(self) -> Dict[str, Any]:
        return {
            "service": self.service,
            "host": self.host,
            "port": self.port,
            "connected": self._client is not None,
            "last_account": self.last_account,
            "last_sync_at": self.last_sync_at,
            "last_count": self.last_count,
            "last_error": self.last_error,
            "mailbox_dir": str(self.mailbox_dir),
        }


_global: Optional[GmailMailbox] = None


def mark_mailbox_read(root: Path, mail_id: str,
                      factory: Optional[Callable[[str, int], Any]] = None) -> Dict[str, Any]:
    """按 mail_id 标记 IMAP 已读 (供 orchestrator 终态 / send-reply 成功后调用).

    读 data/mailbox/{mail_id}.meta.json 的 uid/folder + data/gmail_settings.json
    的 service/host/port → 单次连接 select+flag+logout → 回写 meta.imap_read_at。
    meta 缺失 (mock 上传件无 uid) → ok=False 显式, 不猜。
    """
    root = Path(root)
    meta_path = root / "data" / "mailbox" / f"{mail_id}.meta.json"
    if not meta_path.exists():
        return {"ok": False, "error": f"meta not found: {mail_id}", "mail_id": mail_id}
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"meta unreadable: {e!r}", "mail_id": mail_id}
    uid = str(meta.get("uid") or "")
    folder = str(meta.get("folder") or DEFAULT_FOLDER)
    if not uid:
        return {"ok": False, "error": "meta has no uid (mock 上传件)",
                "mail_id": mail_id}
    service, host, port = "gmail", DEFAULT_HOST, DEFAULT_PORT
    settings_path = root / "data" / "gmail_settings.json"
    if settings_path.exists():
        try:
            cfg = json.loads(settings_path.read_text(encoding="utf-8"))
            service = cfg.get("service") or service
            host = cfg.get("host") or host
            port = int(cfg.get("port") or port)
        except Exception:
            pass
    if service == "qq" and host == DEFAULT_HOST:
        host = QQ_HOST
    mb = GmailMailbox(mailbox_dir=root / "data" / "mailbox", host=host,
                      port=port, service=service, mailbox_factory=factory)
    try:
        mb.connect()
        res = mb.mark_read(uid, folder=folder)
    finally:
        mb.disconnect()
    res["mail_id"] = mail_id
    if res.get("ok"):
        try:
            meta["imap_read_at"] = time.time()
            meta["imap_read_uid"] = uid
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        except Exception as e:
            log.warning("[gmail_imap] meta imap_read_at 回写失败 %s: %r", mail_id, e)
    return res


def get_mailbox(mailbox_dir: Optional[Path] = None, **kwargs) -> GmailMailbox:
    global _global
    if _global is None:
        _global = GmailMailbox(mailbox_dir=mailbox_dir, **kwargs)
    return _global


def reset_global() -> None:
    global _global
    if _global is not None:
        _global.disconnect()
    _global = None