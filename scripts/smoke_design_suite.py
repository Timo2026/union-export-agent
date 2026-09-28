"""design-suite 冒烟截图: /webui/admim 页面加载 + 七模块切换 + 控制台错误捕获."""
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8900"
OUT = Path("docs/design-suite")
OUT.mkdir(parents=True, exist_ok=True)

VIEWS = {
    "mail": "邮件中心", "orders": "订单列表", "cad": "图纸预览",
    "rag": "RAG 搜索", "raglib": "RAG 库", "models": "模型设置", "status": "本地状态",
}
SELECTORS = {
    "mail": ('#view-mail', 'button[data-view="mail"]'),
    "orders": ('#view-orders', 'button[data-view="orders"]'),
    "cad": ('#view-cad', 'button[data-view="cad"]'),
    "rag": ('#view-rag', 'button[data-view="rag"]'),
    "raglib": ('#view-raglib', 'button[data-view="raglib"]'),
    "models": ('#view-models', 'button[data-view="models"]'),
    "status": ('#view-status', 'button[data-view="status"]'),
}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    errors: list[str] = []
    page.on("console", lambda m: errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))

    page.goto(f"{BASE}/webui/admin", wait_until="networkidle", timeout=30_000)
    page.wait_for_timeout(2500)
    page.screenshot(path=str(OUT / "07_00_overview_mail.png"))

    for key, (container, nav_btn) in SELECTORS.items():
        page.click(nav_btn)
        page.wait_for_timeout(1800)
        page.screenshot(path=str(OUT / f"07_{key}.png"))
        assert page.locator(container).is_visible(), f"view {key} not visible"

    # RAG 搜索交互: 真实打一发检索
    page.click('button[data-view="rag"]')
    page.fill("#ragQ", "6061 铝合金")
    page.click("#view-rag button.primary")
    page.wait_for_timeout(2800)
    page.screenshot(path=str(OUT / "07_rag_result.png"))
    n = page.locator("#ragResults .search-hit").count()
    print(f"[smoke] rag search hits rendered: {n}")

    # 邮件详情交互: 打开第一封邮件
    page.click('button[data-view="mail"]')
    page.wait_for_timeout(600)
    rows = page.locator("#mailTbody tr[data-mid]")
    if rows.count():
        rows.first.click()
        page.wait_for_timeout(2200)
        page.screenshot(path=str(OUT / "07_mail_detail.png"))
        print(f"[smoke] mail detail regions: {page.locator('#mailDetail .region').count()}")

    print(f"[smoke] console errors: {len(errors)}")
    for e in errors[:10]:
        print("   ", e[:160])
    browser.close()
