"""tests/test_v6_root_index.py — 根路由契约守卫 (v6 单文件 → v7.1 React 工作台壳).

文件名/旧断言保留历史可追溯性; 当前契约 (v7.1) 已变:
  根 / 服务 webui-dist 的 React SPA 壳 (轻量, <div id="root">), v6 融合单文件 index.html
  已退役不再由根路由服务 (68KB 内联 CSS/JS 的旧形态)。

守卫点:
  1. 根 / 服务 React 工作台壳, 不是 webui 单文件 (207KB) 也不是 v6 单文件 (68KB)
  2. 壳引用构建产物 /assets/index-*.css (Vite outDir 对齐)
  3. 根路由不得回退成 v6 单文件 (防回归): 不出现 v6 单文件专属 ID/内联标记
  4. /webui 六工作台控制台壳仍可达 (与 test_console_ui.py 互为保底)
  5. /webui/v5 legacy 单文件仍可达 (模型设置等旧面板)
"""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# v6 融合单文件专属 ID (根壳是 React SPA, 不应内联这些 DOM ID)
_V6_ONLY_IDS = ("wbInboxList", "wbChatText", 'id="inspectorBody"')

# 根壳引用的构建产物 (任意 base 前缀): <script src="/B/assets/index-*.js"> <link href="/B/assets/index-*.css">
_SHELL_ASSET_RE = re.compile(r'(?:src|href)="(/[^"]+\.(?:js|css))"')


def test_root_serves_react_workbench_shell() -> None:
    """根 / 服务 React 工作台壳, 不应返 webui 单文件 207KB / v6 单文件 68KB."""
    from fastapi.testclient import TestClient
    from services.api_server import app
    with TestClient(app) as c:
        r = c.get("/")
    assert r.status_code == 200
    text = r.text
    # React SPA 壳标识
    assert '<div id="root">' in text, "根路由未服务 React 工作台壳 (缺 <div id=\"root\">)"
    assert "/assets/index-" in text, "根壳未引用 Vite 构建产物 assets"
    # 轻量壳: webui 单文件 207KB / v6 单文件 68KB 都远超此限
    assert len(text) < 2_000, f"根壳异常增大 ({len(text)} bytes) — 可能误用了单文件 UI"


def test_root_shell_references_built_assets() -> None:
    """壳必须引用真实构建产物 (webui-dist/assets), 否则白屏。

    前缀不写死: base 由 vite.config.ts(VITE_BASE) 决定 (当前 /B/), 守卫点是
    "引用的产物必须真的被挂载服务", 不是某个具体前缀。
    """
    from fastapi.testclient import TestClient
    from services.api_server import app
    with TestClient(app) as c:
        r = c.get("/")
        css = [u for u in _SHELL_ASSET_RE.findall(r.text) if u.endswith(".css")]
        assert css, "根壳未引用 index-*.css"
        for url in css:
            assert c.get(url).status_code == 200, f"构建产物 {url} 未挂载 (404)"


def test_shell_assets_serve_real_js_css_not_html() -> None:
    """白屏守卫: 壳引用的每个构建产物必须返回真 JS/CSS, 不得是 HTML。

    根因回归 (2026-09-25 公网 :8051 大白板): 前端 .env.production 设 VITE_BASE=/B/,
    index.html 引 /B/assets/index-*.js, 但 api_server 只挂 /assets 且 SPA fallback
    未排除 B/ 前缀 → 资产请求被 fallback 吞成 index.html (text/html) → 模块脚本
    MIME 不符加载失败 → 白屏。旧守卫只查 "/assets/index-" 子串, 对 /B/ 前缀假阴性。
    """
    from fastapi.testclient import TestClient
    from services.api_server import app
    with TestClient(app) as c:
        shell = c.get("/").text
        assets = _SHELL_ASSET_RE.findall(shell)
        assert assets, "根壳未引用任何 /...js|css 构建产物"
        for url in assets:
            r = c.get(url)
            assert r.status_code == 200, f"构建产物 {url} 未挂载 ({r.status_code}) — 前端白屏"
            ctype = r.headers.get("content-type", "")
            assert "html" not in ctype, (
                f"{url} 返回 {ctype} (HTML) — SPA fallback 吞掉构建产物, 浏览器白屏"
            )
            assert "javascript" in ctype or "css" in ctype, f"{url} content-type 异常: {ctype}"


def test_root_not_regressed_to_v6_single_file() -> None:
    """防回归: 根 / 不得回退成 v6 融合单文件 (其专属 DOM ID 不得内联进根壳)。"""
    from fastapi.testclient import TestClient
    from services.api_server import app
    with TestClient(app) as c:
        text = c.get("/").text
    for marker in _V6_ONLY_IDS:
        assert marker not in text, f"根壳出现 v6 单文件专属标记 {marker} — 疑似回退"
    # v6 单文件的黄金链步骤 DOM 不应出现在轻量壳里
    for step in ("INTAKE", "PARSE", "VERIFY"):
        assert step not in text, f"根壳含 v6 黄金链步骤 {step} — 疑似把单文件当根路由服务"


def test_console_shell_still_served_at_webui() -> None:
    """v7.0 六工作台控制台壳仍可达: /webui 服务 webui/console/index.html (与 test_console_ui.py 互为保底)。"""
    from fastapi.testclient import TestClient
    from services.api_server import app
    with TestClient(app) as c:
        r = c.get("/webui")
        assert r.status_code == 200
        assert "六大工作台" in r.text
        # 模块化静态资源经 Mount 可达 (壳引用 css/js)
        assert c.get("/webui/console/index.html").status_code == 200


def test_legacy_v5_single_file_still_served() -> None:
    """legacy /webui/v5 单文件仍可达 (模型设置等旧面板未随重设计丢失)。"""
    from fastapi.testclient import TestClient
    from services.api_server import app
    with TestClient(app) as c:
        r = c.get("/webui/v5")
    assert r.status_code == 200
    assert "模型设置" in r.text
