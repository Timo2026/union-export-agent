"""screenshot_ui_13tabs.py — 真后端 13 标签 UI 演示截图 (v6.3.1 交付证据).

流程:
  1. 子进程启动真实 API 服务 (uvicorn services.api_server:app, 离线内核兜底);
  2. Playwright (chromium headless) 打开 http://127.0.0.1:8900/webui;
  3. 根 index.html + 13 个 nav 标签 + /docs API 目录, 逐一真实截图;
  4. 落 docs/screenshots/, 自检 (数量/尺寸/非空白) 后 kill 服务。

用法:
    python scripts/screenshot_ui_13tabs.py [--port 8900] [--out docs/screenshots]

铁律: 截图全部来自真后端真浏览器, 无 HTML mockup; 服务失败/标签异常不静默冒充 (计入 failures)。
"""
from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_ROOT = Path(__file__).resolve().parent.parent

TABS = [
    ("01_workbench", "workbench", "三栏智能体协作台 (黄金链 7 步 + 审批 + Chat)"),
    ("02_models", "models", "模型注册表 + A/B 路由 + Fallback"),
    ("03_demo", "demo", "黄金链场景 S1–S5+M1 一键跑"),
    ("04_endpoints", "endpoints", "API 端点目录"),
    ("05_threeD", "threeD", "3D STEP 上传 + 缩略图"),
    ("06_rag", "rag", "分层 RAG 知识入库/检索"),
    ("07_feedback", "feedback", "反馈邮箱"),
    ("08_skills", "skills", "Skill 控制台 + Dispatcher 试调度"),
    ("09_mailbox", "mailbox", "邮件台 (Gmail 主入口)"),
    ("10_v12", "v12", "V12 内核实时仪表板"),
    ("11_rfq", "rfq", "RFQ 管线全生命周期"),
    ("12_flywheel", "flywheel", "客户飞轮"),
    ("13_ops", "ops", "运维诊断"),
]


def _wait_health(port: int, timeout_s: float = 60.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(1.0)
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8900)
    ap.add_argument("--out", default="docs/screenshots")
    a = ap.parse_args()

    out = (_ROOT / a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    own_outputs = {"00_root_index", "14_api_docs"} | {name for name, _, _ in TABS}
    for old in out.glob("*.png"):
        if old.stem in own_outputs:  # 只清理本脚本产物, 不动目录内其他截图
            old.unlink()

    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [sys.executable, "-m", "uvicorn", "services.api_server:app",
           "--host", "127.0.0.1", "--port", str(a.port), "--log-level", "warning"]
    print("[server]", " ".join(cmd))
    proc = subprocess.Popen(cmd, cwd=str(_ROOT), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    failures: list[str] = []
    try:
        if not _wait_health(a.port):
            print("[server] ❌ health 未就绪 (60s 超时)")
            return 2
        print(f"[server] health ok → http://127.0.0.1:{a.port}")

        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1600, "height": 1000},
                                    device_scale_factor=1)
            base = f"http://127.0.0.1:{a.port}"

            def shot(name: str, url: str, click_tab: str | None = None) -> None:
                try:
                    page.goto(url, wait_until="networkidle", timeout=30000)
                    if click_tab:
                        page.click(f'nav button[data-tab="{click_tab}"]', timeout=8000)
                        page.wait_for_timeout(1500)  # 等标签内数据加载
                    path = out / f"{name}.png"
                    page.screenshot(path=str(path), full_page=False)
                    size = path.stat().st_size
                    print(f"  [ok] {name}.png ({size // 1024} KB)")
                    if size < 20_000:
                        failures.append(f"{name}: 截图过小 ({size}B), 疑似空白")
                except Exception as e:
                    failures.append(f"{name}: {e!r}")
                    print(f"  [FAIL] {name}: {e!r}")

            print("[shots] 根 index.html ...")
            shot("00_root_index", f"{base}/")
            print(f"[shots] webui 13 标签 ...")
            for name, tab, desc in TABS:
                print(f"  - {tab}: {desc}")
                shot(name, f"{base}/webui", click_tab=tab)
            print("[shots] /docs API 目录 ...")
            shot("14_api_docs", f"{base}/docs")

            browser.close()

        pngs = sorted(out.glob("*.png"))
        print("\n================ SCREENSHOT SELF-CHECK ================")
        print(f"  screenshots : {len(pngs)} (期望 15)")
        print(f"  failures    : {len(failures)}")
        for f in failures:
            print(f"    - {f}")
        print("=======================================================")
        return 0 if (len(pngs) == 15 and not failures) else 3
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        print("[server] stopped")


if __name__ == "__main__":
    sys.exit(main())
