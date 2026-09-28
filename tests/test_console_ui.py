"""tests/test_console_ui.py — v7.1.0 模块化六工作台控制台 (/webui) 静态接线回归.

断言 (TestClient, 不依赖浏览器):
  1. GET /webui 返 console 壳 (六大 nav + module 入口 + v7.1.0 副标题)
  2. 壳引用的 css/js/vendor 全部 200 (StaticFiles 挂载生效)
  3. legacy v5 单文件 UI 迁到 /webui/v5 仍可达
  4. 各 tab 模块真实接线对应 /v1/* 端点 (禁 MOCK 冒充前端原则的反向保底)
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.api_server import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_webui_serves_console_shell(client):
    r = client.get("/webui")
    assert r.status_code == 200
    html = r.text
    assert "v7.1.0 · 六大工作台" in html
    for tab in ("mail", "orders", "drawings", "intel", "models", "ops"):
        assert f'data-tab="{tab}"' in html, f"nav 缺失工作台: {tab}"
    assert 'src="/webui/console/js/app.js"' in html
    assert 'src="/webui/console/js/vendor/three.min.js"' in html


def test_console_static_assets_mounted(client):
    for path in ("/webui/console/css/app.css",
                 "/webui/console/js/api.js",
                 "/webui/console/js/ui.js",
                 "/webui/console/js/mesh3d.js",
                 "/webui/console/js/vendor/three.min.js",
                 "/webui/console/js/tabs/mail.js",
                 "/webui/console/js/tabs/orders.js",
                 "/webui/console/js/tabs/drawings.js",
                 "/webui/console/js/tabs/intel.js",
                 "/webui/console/js/tabs/models.js",
                 "/webui/console/js/tabs/ops.js"):
        r = client.get(path)
        assert r.status_code == 200, f"静态资源 404: {path}"


def test_legacy_v5_moved_not_deleted(client):
    assert client.get("/webui/v5").status_code == 200
    assert "工业非标外贸工作台" in client.get("/webui/v5").text


def test_tab_modules_wire_real_endpoints(client):
    cases = {
        "/webui/console/js/tabs/mail.js": ["/v1/mail/inbox", "/v1/mail/batch", "/context/"],
        "/webui/console/js/tabs/orders.js": ["/v1/orders/meta", "/v1/orders/bulk", "to_status"],
        "/webui/console/js/tabs/drawings.js": ["/v1/drawings", "/mesh", "/v1/upload/step-with-thumbnail"],
        "/webui/console/js/tabs/intel.js": ["/v1/customer/enrich", "/v1/rag/media/ingest", "/v1/rag/media/docs"],
        "/webui/console/js/tabs/models.js": ["/v1/models/config", "/v1/models/probe", "/v1/skills/config", "/v1/model-router/status"],
        "/webui/console/js/tabs/ops.js": ["/v1/mail/puller/status", "/v1/rag/media/status", "/v1/traces/", "/v1/flywheel/stats"],
    }
    for path, needles in cases.items():
        js = client.get(path).text
        for n in needles:
            assert n in js, f"{path} 未接线端点: {n}"


def test_api_layer_has_mock_detection(client):
    """铁律①前端侧: api.js 必须含 MOCK 扫描 + badge 渲染, 不冒充在线."""
    js = client.get("/webui/console/js/api.js").text
    assert "mockScan" in js and "MOCK" in js
    assert "badge mock" in client.get("/webui/console/js/api.js").text or "badge mock" in js
