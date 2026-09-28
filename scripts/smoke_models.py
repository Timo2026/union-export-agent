from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:8900/webui/admin", wait_until="domcontentloaded", timeout=30000)
    pg.click('button[data-view="models"]')
    pg.wait_for_timeout(20000)
    print("model cards:", pg.locator("#modelCards .model-card").count())
    pg.screenshot(path="docs/design-suite/07_models_loaded.png")
    print("pageerrors:", errs)
