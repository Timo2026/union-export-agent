"""gmail_api.py — /v1/gmail/* 端点: IMAP 连接 + 拉信 + 设置.

铁律①对齐:
- 默认禁用 (gmail_settings.enabled=False). 显式 POST /settings {enabled:true} 才允许 connect.
- 凭据 Fernet 加密存 services/credentials.py, 不存 plaintext, 不外发.
- IMAP 不可达 → 返 error, 不冒充成功.
- 拉信只写 data/mailbox/*.eml (sandbox 内), 跟 v3.0 现有邮件台共享目录.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from .credentials import delete_credentials, list_services, status as cred_status
from .gmail_imap import GmailMailbox

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/gmail", tags=["gmail"])

SETTINGS_FILE = Path("data/gmail_settings.json")
DEFAULT_SETTINGS: Dict[str, Any] = {"enabled": False, "host": "imap.gmail.com", "port": 993, "folder": "INBOX"}


def _load_settings() -> Dict[str, Any]:
    if not SETTINGS_FILE.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        s = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return {**DEFAULT_SETTINGS, **s}
    except Exception:
        return dict(DEFAULT_SETTINGS)


def _save_settings(s: Dict[str, Any]) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


_MAILBOX: Optional[GmailMailbox] = None


def _reset_mailbox() -> None:
    """settings 变更后丢弃缓存的 mailbox (service/host/port 可能已变)."""
    global _MAILBOX
    if _MAILBOX is not None:
        try:
            _MAILBOX.disconnect()
        except Exception:
            pass
    _MAILBOX = None


def _get_mailbox() -> GmailMailbox:
    """按当前 settings 构建 mailbox: service/host/port 可变, 支持 qq/gmail 等多账户切换.

    铁律①: 仅 IMAP 入站, 凭据走 load_credentials(service) Fernet 解密; 不碰 SMTP/egress.
    """
    global _MAILBOX
    s = _load_settings()
    service = s.get("service") or "gmail"
    host = s.get("host") or ("imap.qq.com" if service == "qq" else "imap.gmail.com")
    port = int(s.get("port") or 993)
    if (_MAILBOX is None or _MAILBOX.service != service
            or _MAILBOX.host != host or _MAILBOX.port != port):
        if _MAILBOX is not None:
            try:
                _MAILBOX.disconnect()
            except Exception:
                pass
        _MAILBOX = GmailMailbox(service=service, host=host, port=port)
    return _MAILBOX


@router.get("/settings")
def get_settings():
    return JSONResponse({"settings": _load_settings(), "credentials": cred_status()})


@router.post("/settings")
async def post_settings(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "invalid json body")
    s = _load_settings()
    if "enabled" in body:
        s["enabled"] = bool(body["enabled"])
    if "host" in body and isinstance(body["host"], str):
        s["host"] = body["host"]
    if "port" in body:
        s["port"] = int(body["port"])
    if "folder" in body and isinstance(body["folder"], str):
        s["folder"] = body["folder"]
    if "service" in body and isinstance(body["service"], str):
        s["service"] = body["service"].strip() or "gmail"
    _save_settings(s)
    _reset_mailbox()  # settings 变更后重建 mailbox (service/host/port 可能变)
    return JSONResponse({"saved": True, "settings": s})


@router.post("/connect")
async def connect(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "invalid json body")
    s = _load_settings()
    if not s.get("enabled"):
        raise HTTPException(403, "gmail disabled. POST /v1/gmail/settings {\"enabled\": true} first")
    email = (body.get("email") or "").strip()
    app_password = (body.get("app_password") or "").strip()
    if not email or not app_password:
        raise HTTPException(400, "missing email or app_password")
    from .credentials import save_credentials
    service = s.get("service") or "gmail"
    save_credentials(service, email, app_password)
    mb = _get_mailbox()
    res = mb.connect()
    return JSONResponse(res)


@router.post("/disconnect")
def disconnect():
    s = _load_settings()
    service = s.get("service") or "gmail"
    delete_credentials(service)
    mb = _get_mailbox()
    mb.disconnect()
    return JSONResponse({"ok": True, "disconnected": True, "service": service})


@router.post("/sync")
def sync(folder: Optional[str] = None, limit: int = 50):
    s = _load_settings()
    if not s.get("enabled"):
        raise HTTPException(403, "gmail disabled")
    mb = _get_mailbox()
    res = mb.sync(folder=folder or s.get("folder", "INBOX"), limit=limit)
    # LINK-3 (E1 #34): 手动 sync 也要入 pending 队列, 否则黄金链无人消费
    try:
        if isinstance(res, dict) and res.get("ok") and res.get("fetched"):
            from .mail_puller import get_puller
            res["enqueued"] = get_puller()._enqueue_pending_from_mailbox()
    except Exception as e:
        log.warning("[gmail/sync] enqueue pending 失败 (不冒充成功): %r", e)
        res = {**res, "enqueued": 0, "enqueue_error": repr(e)}
    return JSONResponse(res)


def _puller_block(s: Dict[str, Any]) -> Dict[str, Any]:
    """后台 puller 真相 (2026-09-25 Fix A).

    为什么不能拿 mailbox 单例的 connected 冒充: 那个实例只反映 API 进程临时
    会话 (connect/sync 时才连), 与后台轮询线程是两个东西 — 事故日状态页
    "未连接·最近同步 0 封" 即是读了它。真相三要素:
      settings_enabled — 配置意图 (gmail_settings.enabled)
      credentials_ok   — 解密级真相 (load_credentials 返回 None = 密钥不匹配)
      thread_alive     — 本进程后台线程活性 (get_puller() 单例, lifespan 注册)
    state.running 同样按线程纠偏 (state.json 可能是上个进程的遗留值)。
    """
    from .credentials import load_credentials
    from .mail_puller import get_puller

    service = s.get("service") or "gmail"
    try:
        credentials_ok = load_credentials(service) is not None
    except Exception:
        credentials_ok = False
    settings_enabled = bool(s.get("enabled"))
    p = get_puller()
    thread_alive = bool(getattr(p, "_thread", None) is not None and p._thread.is_alive())
    st = p._read_state().to_dict()
    st["running"] = thread_alive  # 遗留值纠偏, 只信线程
    return {
        "service": service,
        "settings_enabled": settings_enabled,
        "credentials_ok": credentials_ok,
        "enabled": settings_enabled and credentials_ok,
        "thread_alive": thread_alive,
        "state": st,
    }


@router.get("/status")
def status():
    s = _load_settings()
    mb = _get_mailbox()
    return JSONResponse({
        "settings": s,
        "credentials": cred_status(),
        "mailbox": mb.status(),           # 仅 API 进程临时会话, 非后台 puller 健康度
        "puller": _puller_block(s),       # 后台邮件链路真相 (见 docstring)
    })