"""security.py — 上传端口硬化 + 数据脱敏 (维度 6.2 / 7.2 / 15 安全).

- safe_filename: 防路径穿越 (剥离目录/.. /绝对路径/控制字符)
- size_guard: 上传大小上限
- redact: PII/凭证脱敏 (入审计/日志前)
- RateLimiter: 令牌桶限流 (per-client)
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import quote

# ---- 凭证/PII 脱敏模式 ----
_REDACT_PATTERNS = [
    (re.compile(r"(sk-[A-Za-z0-9]{6,})"), "<REDACTED_API_KEY>"),
    (re.compile(r"(AKIA[0-9A-Z]{12,})"), "<REDACTED_AWS_KEY>"),
    (re.compile(r"(ghp_[A-Za-z0-9]{10,})"), "<REDACTED_GH_TOKEN>"),
    (re.compile(r"(xox[baprs]-[A-Za-z0-9-]{6,})"), "<REDACTED_SLACK_TOKEN>"),
    (re.compile(r"(Bearer\s+[A-Za-z0-9\-._~+/]{8,})", re.I), "<REDACTED_BEARER>"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
     "<REDACTED_PRIVATE_KEY>"),
    (re.compile(r"\b([\w.+-]+@[\w-]+\.[\w.]+)\b"), "<REDACTED_EMAIL>"),
    (re.compile(r"\b(1[3-9]\d{9})\b"), "<REDACTED_PHONE>"),          # 中国大陆手机号
    (re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*\S+"), "\\1=<REDACTED>"),
]

MAX_UPLOAD_BYTES = 50 * 1024 * 1024      # 50MB 默认上限
_ALLOWED_NAME = re.compile(r"[^A-Za-z0-9._\-\u4e00-\u9fff]")


def safe_filename(name: Optional[str], fallback: str = "upload.bin") -> str:
    """防路径穿越: 只取 basename, 去 .. / 绝对路径 / 控制字符。"""
    if not name:
        return fallback
    base = Path(name.replace("\\", "/")).name           # 剥离任何目录
    base = base.replace("..", "_").strip()
    base = _ALLOWED_NAME.sub("_", base)
    return base or fallback


def size_guard(nbytes: int, limit: int = MAX_UPLOAD_BYTES) -> None:
    if nbytes > limit:
        raise ValueError(f"upload too large: {nbytes} > {limit} bytes")


def redact(text: Any) -> Any:
    """对字符串做 PII/凭证脱敏; 非字符串原样返回。"""
    if not isinstance(text, str):
        return text
    out = text
    for pat, repl in _REDACT_PATTERNS:
        out = pat.sub(repl, out)
    return out


def redact_dict(d: Dict[str, Any], keys: tuple = ("email", "body", "text", "content",
                                                  "voice_transcript", "raw_text")) -> Dict[str, Any]:
    out = dict(d)
    for k in keys:
        if k in out and isinstance(out[k], str):
            out[k] = redact(out[k])
    return out


class RateLimiter:
    """令牌桶限流 (per-key)。capacity 令牌, refill_rate 令牌/秒。"""
    def __init__(self, capacity: int = 30, refill_rate: float = 5.0):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._buckets: Dict[str, float] = {}
        self._ts: Dict[str, float] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, cost: int = 1) -> bool:
        now = time.time()
        with self._lock:
            tokens = self._buckets.get(key, float(self.capacity))
            last = self._ts.get(key, now)
            tokens = min(self.capacity, tokens + (now - last) * self.refill_rate)
            if tokens >= cost:
                self._buckets[key] = tokens - cost
                self._ts[key] = now
                return True
            self._buckets[key] = tokens
            self._ts[key] = now
            return False

    def reset(self, key: Optional[str] = None):
        with self._lock:
            if key is None:
                self._buckets.clear(); self._ts.clear()
            else:
                self._buckets.pop(key, None); self._ts.pop(key, None)


# ---------------------------------------------------------------------------
# P1-1 公网 API 门禁 (2026-09-25)
# ---------------------------------------------------------------------------
# 背景 (2026-09-23 自审 P1-1 已记录, 2026-09-25 公网复核仍未修):
#   services/api_server.py 零鉴权且绑 0.0.0.0, 经公网 NAT (:8051) 暴露
#   openapi.json 106 条路径。其中 /v1/mail/inbox (客户邮件正文) /
#   /v1/customer/enrich (客户信息) / POST /v1/rag/ingest (污染知识库) /
#   POST /v1/mail/batch (批量触发) 未授权即可读写。
#
# 策略: env UEA_API_TOKEN 非空 → 启用; 为空 → 关闭 (api_server 启动时打 WARNING)。
#   放行: ① 回环客户端 (watchdog/内部脚本/openclaw skills 全走 127.0.0.1, 不受影响)
#         ② Authorization: Bearer <token>
#         ③ GET /__auth?token=... 换发的 HttpOnly cookie
#         ④ 静态资源与 SPA 壳 (不含业务数据; 数据由 /v1/* 守住)
#   拦截: 其余外部请求命中 /v1/* /health /docs /openapi.json /redoc → 401。
#
# 为何用 cookie 而非「前端逐处注入 header」: 工作台 fetch 分散在 index.html /
#   js/app.js / webui/index.html 与 React 构建产物 webui-dist/assets/*.js 共 155 处,
#   逐处改必然漏; cookie 由浏览器自动携带, 前端零改动。

GATE_ENV_TOKEN = "UEA_API_TOKEN"
GATE_ENV_TTL_HOURS = "UEA_API_SESSION_TTL_HOURS"
GATE_COOKIE_NAME = "uea_session"
GATE_PATH = "/__auth"
GATE_DEFAULT_TTL_HOURS = 720          # 30 天: 人工台无需天天登录
GATE_MAX_TTL_HOURS = 24 * 365


def gate_token() -> str:
    """门禁共享密钥 (env UEA_API_TOKEN); 空串 = 门禁关闭。"""
    return (os.environ.get(GATE_ENV_TOKEN) or "").strip()


def gate_enabled() -> bool:
    return bool(gate_token())


def gate_ttl_seconds() -> int:
    raw = (os.environ.get(GATE_ENV_TTL_HOURS) or "").strip()
    try:
        hours = float(raw) if raw else float(GATE_DEFAULT_TTL_HOURS)
    except (TypeError, ValueError):
        hours = float(GATE_DEFAULT_TTL_HOURS)
    hours = max(1.0, min(hours, float(GATE_MAX_TTL_HOURS)))
    return int(hours * 3600)


def needs_gate(path: str) -> bool:
    """该路径是否属于需门禁的 API 面 (SPA 壳/静态资源不需要)。"""
    p = (path or "").rstrip("/") or "/"
    return (
        p.startswith("/v1/") or p == "/health"
        or p.startswith("/docs") or p.startswith("/redoc")
        or p == "/openapi.json"
    )


def is_loopback_host(host: Optional[str]) -> bool:
    """回环客户端判定; 含 TestClient 合成主机名 (starlette 用它跑测试)。"""
    h = (host or "").strip().lower()
    if h.startswith("::ffff:"):          # IPv4-mapped IPv6
        h = h[len("::ffff:"):]
    if not h:
        return True                      # 无客户端信息 = 内部/合成调用
    return h in ("::1", "localhost", "testclient") or h.startswith("127.")


def _sign(payload: str) -> str:
    return hmac.new(gate_token().encode("utf-8"), payload.encode("utf-8"),
                    hashlib.sha256).hexdigest()


def issue_session() -> tuple:
    """发门禁票: 返回 (cookie 值, max_age_seconds); 值 = "<issued_at>.<hmac>"。"""
    issued = str(int(time.time()))
    return "{}.{}".format(issued, _sign(issued)), gate_ttl_seconds()


def session_valid(value: Optional[str], now: Optional[float] = None) -> bool:
    """校验门禁 cookie: HMAC 正确且未过期 (常量时间比较)。"""
    if not value or "." not in value:
        return False
    issued, _, sig = value.rpartition(".")
    if not issued.isdigit() or not sig:
        return False
    if not hmac.compare_digest(_sign(issued), sig):
        return False
    age = (now if now is not None else time.time()) - int(issued)
    return 0 <= age <= gate_ttl_seconds()


def bearer_authorized(header: Optional[str]) -> bool:
    """请求头 Authorization: Bearer <token> 是否有效 (常量时间比较)。"""
    prefix = "bearer "
    if not header or len(header) < len(prefix) or header[:len(prefix)].lower() != prefix:
        return False
    token = header[len(prefix):].strip()
    return bool(token) and hmac.compare_digest(token, gate_token())


def token_matches(supplied: Optional[str]) -> bool:
    """常量时间比对 (登录表单 / query 场景)。"""
    token = gate_token()
    supplied = (supplied or "").strip()
    return bool(token and supplied) and hmac.compare_digest(supplied, token)


GATE_PAGE_TEMPLATE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>访问门禁 · Union Export Agent</title>
<style>
 body{font:15px/1.6 system-ui,"PingFang SC","Microsoft YaHei",sans-serif;background:#0f1115;color:#e6e8ec;
      display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}
 main{width:min(420px,92vw);background:#171a21;border:1px solid #262b36;border-radius:12px;padding:28px}
 h1{font-size:18px;margin:0 0 8px}
 p{color:#9aa3b2;font-size:13px;margin:0 0 18px}
 input{width:100%;box-sizing:border-box;padding:10px 12px;border-radius:8px;border:1px solid #2c3240;
       background:#0f1115;color:#e6e8ec;font-size:14px}
 button{margin-top:14px;width:100%;padding:10px;border:0;border-radius:8px;background:#3b82f6;color:#fff;
        font-size:14px;cursor:pointer}
 code{background:#0f1115;border:1px solid #262b36;border-radius:6px;padding:1px 5px;font-size:12px}
</style></head><body><main>
<h1>&#128274; 访问门禁</h1>
__ERROR__
<p>该实例已启用 API 门禁 (P1-1 安全修复)。输入访问令牌后, 本浏览器 30 天内免登录。</p>
<form method="get" action="/__auth">
 <input name="token" type="password" placeholder="Access token (UEA_API_TOKEN)"
        autocomplete="current-password" required>
 <button type="submit">进入工作台</button>
</form>
<p style="margin-top:18px">程序化调用请带请求头
<code>Authorization: Bearer $UEA_API_TOKEN</code>。</p>
</main></body></html>"""


# ---- 文档导航门禁判定 (P1-1 回归修复 2026-09-25 05:14) ----
# 事故: 前端 bundle 无登录入口, 且 fetch 包装把任何非 2xx 一律当「后端离线」;
#       未登录浏览器打开经 NAT 暴露的工作台 → SPA 壳能加载但每个请求吃裸 401 →
#       全站显示「后端离线」, 用户以为服务宕机 (公网实测, 实为门禁按设计拦截)。
# 策略: 未鉴权时, **浏览器文档导航 (GET + Accept 含 text/html + 非静态资源)** 改投
#       303 → /__auth?next=<原路径>, 登录种 cookie 后自动回到原路径;
#       **程序化调用** (Accept: */* 等, 无 text/html) 仍收裸 401 + error=unauthorized,
#       安全语义与调用方契约完全不变。
GATE_DOC_ASSET_EXT = (".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif",
                      ".ico", ".woff", ".woff2", ".ttf", ".eot", ".map", ".json",
                      ".txt", ".xml", ".pdf", ".zip", ".step", ".stp", ".wav",
                      ".mp3", ".m4a", ".flac", ".html")


def is_document_request(path: str, accept: Optional[str] = None,
                        method: str = "GET") -> bool:
    """是否浏览器文档导航 (需跳登录页); 静态资源/XHR/POST 皆否。

    资产后缀豁免只对非门禁路径生效: /openapi.json 这类「门禁 API 面」即使带资产
    后缀, 浏览器导航也应跳登录页, 而非裸 401 被前端探针当成后端离线 (P1-1 事故同源)。
    """
    if (method or "GET").upper() != "GET":
        return False
    a = (accept or "").lower()
    if "text/html" not in a and "application/xhtml+xml" not in a:
        return False
    p = (path or "/").lower()
    return not (p.endswith(GATE_DOC_ASSET_EXT) and not needs_gate(p))


def document_login_url(path: str = "/", query: str = "") -> str:
    """文档导航被拦时的跳转目标: /__auth?next=<URL 编码后的原路径+查询>。"""
    target = (path or "/") + (("?%s" % query) if query else "")
    return "%s?next=%s" % (GATE_PATH, quote(target, safe=""))


def safe_next(url: Optional[str]) -> str:
    r"""仅接受站内相对路径 (防 /__auth?next=https://evil.com 开放重定向)。

    拒绝: 非 / 开头 (绝对 URL / javascript: / data:) / 协议相对 //host /
    反斜杠绕道 /\host。第二个字符为 "/" 或 反斜杠(chr(92)) 即拒绝
    — 用 chr(92) 而非字面反斜杠, 杜绝转义歧义 (旧写法曾漏拦 /\host)。
    """
    u = (url or "").strip()
    if not u.startswith("/") or u in ("", "/", "//"):
        return "/"
    if u[1] == "/" or u[1] == chr(92):
        return "/"
    return u


def gate_page(error: str = "") -> str:
    """登录/拒绝页 HTML (error 非空时展示红色错误行)。"""
    err = ('<p style="color:#f87171;margin:0 0 12px">%s</p>' % error) if error else ""
    return GATE_PAGE_TEMPLATE.replace("__ERROR__", err)
