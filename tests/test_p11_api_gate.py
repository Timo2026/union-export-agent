# -*- coding: utf-8 -*-
"""P1-1 公网 API 门禁 回归测试 (2026-09-25)。

覆盖 services/security.py gate_* 与 api_server._gate_middleware / /__auth:
  1. 未配置 UEA_API_TOKEN → 门禁关闭, 既有行为不变 (防把用户锁在门外)
  2. 配置后: 回环放行 / 外部 401 / Bearer 放行 / /__auth 换 cookie / cookie 放行
  3. 静态资源与 SPA 壳不需门禁 (工作台壳可加载, 数据由 /v1/* 守住)
  4. 单元级: needs_gate / is_loopback_host / token_matches / session_valid (篡改·过期·换 token)

对端地址注入: TestClient(app, client=(host, port)) — starlette 用它构造 scope["client"],
即 request.client.host; 不注入时默认 "testclient" 主机名 (is_loopback_host 视为回环,
这保证仓库既有全部 TestClient 用例不受门禁影响)。
"""
from __future__ import annotations

import inspect
import time

import pytest
from fastapi.testclient import TestClient

# conftest 已置 UEA_MAIL_AUTOSTART=0 (禁止 lifespan 拉真实 mail 后台线程)

_EXTERNAL = ("203.0.113.9", 54321)      # TEST-NET-3: 非回环客户端
_LOOPBACK = ("127.0.0.1", 54321)
_TOKEN = "t0p-s3cret-test-token"

# TestClient 的 client= 对端注入自 starlette 0.41 起提供; 本地 venv (0.27) 没有,
# 其 transport 把 scope["client"] 硬编码为 ["testclient", 50000]。
_HAS_CLIENT_KWARG = "client" in inspect.signature(TestClient.__init__).parameters


class _PeerOverride:
    """ASGI 包装: 把 scope["client"] 改写为指定对端 (starlette<0.41 注入替代)。"""

    def __init__(self, app, peer):
        self._app = app
        self._peer = peer

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            scope = dict(scope)
            scope["client"] = self._peer
        await self._app(scope, receive, send)


def _open(app, peer=_EXTERNAL):
    """构造并进入 lifespan 的 TestClient; peer 指定对端地址。"""
    if _HAS_CLIENT_KWARG:
        return TestClient(app, client=peer)
    return TestClient(_PeerOverride(app, peer))


@pytest.fixture()
def app_module(monkeypatch):
    """导入 api_server; 必须为 function 作用域 — 各用例需自行 monkeypatch UEA_API_TOKEN,
    而 module-scoped fixture 不能依赖 function-scoped 的 monkeypatch (ScopeMismatch)。"""
    monkeypatch.setenv("UEA_MAIL_AUTOSTART", "0")
    import services.api_server as m
    return m


# ══════════════ 1. 门禁关闭时保持旧行为 ══════════════
def test_gate_disabled_preserves_behavior(app_module, monkeypatch):
    monkeypatch.delenv("UEA_API_TOKEN", raising=False)
    with _open(app_module.app) as c:
        assert c.get("/v1/rag/docs").status_code == 200
        assert c.get("/v1/models/config").status_code == 200
        assert c.get("/openapi.json").status_code == 200


# ══════════════ 2. 门禁启用后：外部被拦 ══════════════
def test_external_api_rejected(app_module, monkeypatch):
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app) as c:
        r = c.get("/v1/rag/docs")
        assert r.status_code == 401
        assert r.json()["error"] == "unauthorized"


@pytest.mark.parametrize("path", ["/openapi.json", "/health", "/v1/skills", "/v1/mail/inbox"])
def test_external_sensitive_paths_rejected(app_module, monkeypatch, path):
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app) as c:
        assert c.get(path).status_code == 401, path


def test_external_write_endpoint_rejected(app_module, monkeypatch):
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app) as c:
        r = c.post("/v1/rag/ingest", json={"id": "x", "text": "pollute"})
        assert r.status_code == 401


# ══════════════ 3. 门禁启用后：回环 / Bearer / cookie 放行 ══════════════
def test_loopback_allowed(app_module, monkeypatch):
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app, peer=_LOOPBACK) as c:
        assert c.get("/v1/rag/docs").status_code == 200


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER"])
def test_bearer_correct_allowed(app_module, monkeypatch, scheme):
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app) as c:
        r = c.get("/v1/rag/docs", headers={"Authorization": f"{scheme} {_TOKEN}"})
        assert r.status_code == 200


def test_bearer_wrong_rejected(app_module, monkeypatch):
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app) as c:
        assert c.get("/v1/rag/docs", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert c.get("/v1/rag/docs", headers={"Authorization": _TOKEN}).status_code == 401
        assert c.get("/v1/rag/docs", headers={"Authorization": "Basic " + _TOKEN}).status_code == 401


# ══════════════ 4. 静态资源与 SPA 壳不设门禁 ══════════════
@pytest.mark.parametrize("path", ["/", "/B/", "/webui/", "/css/", "/js/"])
def test_static_and_spa_not_gated(app_module, monkeypatch, path):
    """SPA 壳/静态路由不碰业务数据; 若设门禁工作台直接白屏 (2026-09-25 :8051 事故同源)。"""
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app) as c:
        r = c.get(path)
        assert r.status_code in (200, 307, 404), f"{path} -> {r.status_code}"


# ══════════════ 5. /__auth 换 cookie ══════════════
def test_auth_login_issues_cookie(app_module, monkeypatch):
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app) as c:
        r = c.get("/__auth", params={"token": _TOKEN}, follow_redirects=False)
        assert r.status_code == 303
        assert r.cookies.get("uea_session", "").count(".") == 1


@pytest.mark.parametrize("bad", [("nope", 403), ("__MISSING__", 403)])
def test_auth_login_rejects_bad_token(app_module, monkeypatch, bad):
    token, status = bad
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app) as c:
        params = {} if token == "__MISSING__" else {"token": token}
        r = c.get("/__auth", params=params, follow_redirects=False)
        assert r.status_code == status
        if status == 403:
            assert "令牌不正确" in r.text


def test_cookie_unlocks_api(app_module, monkeypatch):
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app) as c:
        login = c.get("/__auth", params={"token": _TOKEN}, follow_redirects=False)
        ticket = login.cookies.get("uea_session")
        r = c.get("/v1/rag/docs", cookies={"uea_session": ticket})
        assert r.status_code == 200


def test_stolen_cookie_without_ticket_rejected(app_module, monkeypatch):
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app) as c:
        assert c.get("/v1/rag/docs", cookies={"uea_session": "123.garbage"}).status_code == 401


def test_auth_disabled_when_no_token(app_module, monkeypatch):
    monkeypatch.delenv("UEA_API_TOKEN", raising=False)
    with _open(app_module.app) as c:
        assert "门禁未启用" in c.get("/__auth", params={"token": "x"}).text


# ══════════════ 6. 单元级 gate_* ══════════════
@pytest.mark.parametrize("path,expected", [
    ("/v1/rag/docs", True), ("/health", True), ("/docs", True),
    ("/docs/oauth2-redirect", True), ("/openapi.json", True), ("/redoc", True),
    ("/", False), ("/B/index.html", False), ("/css/workbench.css", False),
    ("/webui/console/", False), ("/__auth", False), ("/generate", False),
])
def test_needs_gate(app_module, path, expected):
    assert app_module.sec.needs_gate(path) is expected, path


@pytest.mark.parametrize("host,expected", [
    ("127.0.0.1", True), ("127.8.9.9", True), ("::1", True),
    ("::ffff:127.0.0.1", True), ("localhost", True), ("testclient", True),
    ("", True), (None, True),
    ("203.0.113.9", False), ("203.0.113.10", False), ("example.com", False),
])
def test_is_loopback_host(app_module, host, expected):
    assert app_module.sec.is_loopback_host(host) is expected, host


def test_session_valid_rejects_tampered(app_module, monkeypatch):
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    value, _ = app_module.sec.issue_session()
    assert app_module.sec.session_valid(value)
    issued, sig = value.split(".", 1)
    assert not app_module.sec.session_valid(issued + ".deadbeef")
    assert not app_module.sec.session_valid("garbage")
    assert not app_module.sec.session_valid(issued)          # 缺少 .sig
    assert not app_module.sec.session_valid("")
    assert not app_module.sec.session_valid(None)
    assert not app_module.sec.session_valid("notadigit." + sig)


def test_session_valid_expires(app_module, monkeypatch):
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    monkeypatch.setenv("UEA_API_SESSION_TTL_HOURS", "1")
    now = time.time()
    old = str(int(now - 7200))                       # 2h > 1h ttl
    sig = app_module.sec._sign(old)
    assert not app_module.sec.session_valid(old + "." + sig, now=now)


def test_session_valid_fresh_within_ttl(app_module, monkeypatch):
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    monkeypatch.setenv("UEA_API_SESSION_TTL_HOURS", "2")
    now = time.time()
    issued = str(int(now - 3600))                    # 1h < 2h ttl
    sig = app_module.sec._sign(issued)
    assert app_module.sec.session_valid(issued + "." + sig, now=now)


def test_future_issued_rejected(app_module, monkeypatch):
    """issued 在未来 = 伪造/时钟异常, 拒绝。"""
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    now = time.time()
    future = str(int(now + 600))
    sig = app_module.sec._sign(future)
    assert not app_module.sec.session_valid(future + "." + sig, now=now)


def test_token_matches(app_module, monkeypatch):
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    f = app_module.sec.token_matches
    assert f(_TOKEN) is True
    assert f("  " + _TOKEN + "  ") is True
    assert f(_TOKEN + "x") is False
    assert f("") is False
    assert f(None) is False


def test_token_change_invalidates_old_session(app_module, monkeypatch):
    """换 UEA_API_TOKEN 后旧票必须失效 — 否则 token 更换无法踢掉已登录会话。"""
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    value, _ = app_module.sec.issue_session()
    assert app_module.sec.session_valid(value)
    monkeypatch.setenv("UEA_API_TOKEN", "a-brand-new-token")
    assert not app_module.sec.session_valid(value)


def test_gate_enabled_tracks_env(app_module, monkeypatch):
    assert not app_module.sec.gate_enabled()
    monkeypatch.setenv("UEA_API_TOKEN", "k")
    assert app_module.sec.gate_enabled()
    monkeypatch.setenv("UEA_API_TOKEN", "   ")
    assert not app_module.sec.gate_enabled()


@pytest.mark.parametrize("raw,expected_hours", [
    ("", 720), ("1", 1), ("24", 24), ("0", 1), ("999999", 8760),
    ("not-a-number", 720), ("-5", 1),
])
def test_gate_ttl_clamps(app_module, monkeypatch, raw, expected_hours):
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    from services import security as sec
    monkeypatch.setenv("UEA_API_SESSION_TTL_HOURS", raw)
    assert sec.gate_ttl_seconds() == expected_hours * 3600


def test_gate_page_renders(app_module):
    html = app_module.sec.gate_page("boom")
    assert "boom" in html and "访问门禁" in html and "/__auth" in html
    assert app_module.sec.gate_page("") .find("#f87171") == -1     # 无错误时不渲染红行


# ══════════════ 7. P1-1 回归修复: 未鉴权浏览器 → 303 跳登录 (50514 TIMO 报「8051 离线」) ══════════════
# 根因: 前端 bundle 无登录入口, 且 fetch 包装把任何非 2xx 一律当「后端离线」
#       → 裸 401 让未登录浏览器看到的工作台看似宕机。
# 修法: GET + Accept 含 text/html + 非静态资源 → 303 /__auth?next=<原路径>;
#       程序化调用仍裸 401 (安全契约不变)。
_HTML = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
_API = {"Accept": "*/*"}                      # curl / urllib / fetch XHR 的典型头


@pytest.mark.parametrize("path", ["/", "/v1/rag/docs", "/health", "/v1/mail/inbox",
                                  "/openapi.json", "/docs"])
def test_document_navigation_redirects_to_login(app_module, monkeypatch, path):
    """未鉴权浏览器文档导航 → 303 跳登录页 (而非裸 401 被前端当成离线)。"""
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app) as c:
        r = c.get(path, headers=_HTML, follow_redirects=False)
        assert r.status_code == 303, f"{path} -> {r.status_code}"
        assert r.headers["location"].startswith("/__auth?next=")


def test_document_redirect_preserves_next_target(app_module, monkeypatch):
    """next 必须带回原路径 (含查询), 登录后用户落回原处。"""
    from urllib.parse import unquote, urlsplit, parse_qs
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app) as c:
        loc = c.get("/v1/rag/docs?limit=5", headers=_HTML,
                    follow_redirects=False).headers["location"]
        nxt = parse_qs(urlsplit(loc).query)["next"][0]
        assert unquote(nxt) == "/v1/rag/docs?limit=5", nxt


def test_programmatic_call_still_gets_bare_401(app_module, monkeypatch):
    """安全契约不退化: 非 HTML 请求仍收裸 401 + error=unauthorized。"""
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app) as c:
        for path in ("/health", "/v1/rag/docs"):
            r = c.get(path, headers=_API)
            assert r.status_code == 401, path
            assert r.json() == {
                "ok": False, "error": "unauthorized",
                "detail": ("API 门禁已启用 (P1-1)。请带 Authorization: Bearer <UEA_API_TOKEN> "
                           "请求头; 或在浏览器打开 /__auth?token=<UEA_API_TOKEN> 换取会话 cookie。"),
            }


def test_no_accept_header_treated_as_programmatic(app_module, monkeypatch):
    """浏览器总带 Accept; 完全不带 = 程序化 → 裸 401。"""
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app) as c:
        r = c.get("/health", headers={"Accept": ""})
        assert r.status_code == 401


def test_static_assets_not_redirected(app_module, monkeypatch):
    """静态资源不属 needs_gate, 保持 200 — 否则 bundle 加载失败即白屏。"""
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app) as c:
        for path in ("/B/index.html", "/favicon.svg", "/css/workbench.css"):
            r = c.get(path, headers=_HTML, follow_redirects=False)
            assert r.status_code in (200, 404), f"{path} -> {r.status_code}"


def test_document_navigation_allowed_after_cookie(app_module, monkeypatch):
    """登录拿到 cookie 后, 文档导航返回真实内容 (不再跳登录页)。"""
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app) as c:
        ticket = c.get("/__auth", params={"token": _TOKEN},
                       follow_redirects=False).cookies.get("uea_session")
        r = c.get("/v1/rag/docs", headers=_HTML, cookies={"uea_session": ticket},
                  follow_redirects=False)
        assert r.status_code == 200
        assert r.headers.get("location") is None


def test_document_navigation_allowed_by_bearer(app_module, monkeypatch):
    """带 Bearer 的浏览器/脚本也直接放行, 不跳登录。"""
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app) as c:
        r = c.get("/v1/rag/docs", headers={**_HTML, "Authorization": "Bearer " + _TOKEN},
                  follow_redirects=False)
        assert r.status_code == 200


def test_login_next_rejects_open_redirect(app_module, monkeypatch):
    """P1-1 新增: /__auth?next=https://evil.com 不得开放重定向 (钓鱼面)。"""
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    bad = ["https://evil.com", "//evil.com/x", "/\\evil.com", "javascript:alert(1)"]
    with _open(app_module.app) as c:
        for nxt in bad:
            r = c.get("/__auth", params={"token": _TOKEN, "next": nxt},
                      follow_redirects=False)
            assert r.status_code == 303, nxt
            assert r.headers["location"] == "/", nxt


def test_login_next_accepts_relative(app_module, monkeypatch):
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app) as c:
        r = c.get("/__auth", params={"token": _TOKEN, "next": "/v1/rag/docs?limit=2"},
                  follow_redirects=False)
        assert r.headers["location"] == "/v1/rag/docs?limit=2"


def test_document_redirect_not_used_for_loopback(app_module, monkeypatch):
    """回环 (watchdog/内部脚本/openclaw skills) 直接放行, 不跳登录。"""
    monkeypatch.setenv("UEA_API_TOKEN", _TOKEN)
    with _open(app_module.app, peer=_LOOPBACK) as c:
        r = c.get("/health", headers=_HTML, follow_redirects=False)
        assert r.status_code == 200
        assert r.headers.get("location") is None


@pytest.mark.parametrize("accept,expected", [
    ("text/html", True),
    ("application/xhtml+xml", True),
    ("text/html,application/xhtml+xml,*/*", True),        # 真实浏览器 Accept 尾部即 */*;q=0.8, 必须算文档导航
    ("*/*", False),
    ("application/json", False),
    ("", False),
    (None, False),
])
def test_is_document_request(app_module, accept, expected):
    f = app_module.sec.is_document_request
    assert f("/v1/rag/docs", accept) is expected, accept


def test_is_document_request_excludes_assets_and_methods(app_module):
    f = app_module.sec.is_document_request
    assert f("/B/assets/index-abc.js", "text/html") is False
    assert f("/favicon.svg", "text/html") is False
    assert f("/api/openapi.json", "text/html") is False
    assert f("/v1/rag/docs", "text/html", method="POST") is False
    assert f("/v1/rag/docs", "text/html", method="delete") is False


def test_document_login_url_encodes_target(app_module):
    u = app_module.sec.document_login_url("/v1/rag/docs", "limit=5&q=6061")
    assert u.startswith("/__auth?next=")
    from urllib.parse import unquote, urlsplit, parse_qs
    nxt = parse_qs(urlsplit(u).query)["next"][0]
    assert unquote(nxt) == "/v1/rag/docs?limit=5&q=6061", nxt


def test_document_login_url_no_query(app_module):
    assert app_module.sec.document_login_url("/health") == "/__auth?next=%2Fhealth"
    assert app_module.sec.document_login_url("") == "/__auth?next=%2F"


@pytest.mark.parametrize("raw,expected", [
    ("/v1/rag/docs", "/v1/rag/docs"),
    ("/", "/"),
    ("/deep/path?q=1", "/deep/path?q=1"),
    ("", "/"), (None, "/"), ("   ", "/"),
    ("https://evil.com", "/"), ("//evil.com", "/"), ("/\\evil.com", "/"),
    ("javascript:alert(1)", "/"), ("data:text/html,x", "/"),
])
def test_safe_next(app_module, raw, expected):
    assert app_module.sec.safe_next(raw) == expected, raw
