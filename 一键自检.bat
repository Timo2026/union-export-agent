@echo off
chcp 65001 >nul
setlocal ENABLEEXTENSIONS
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ============================================================
echo   Union Export Agent - 一键自检 (pytest + demo + notebooks)
echo ============================================================
echo.

echo [1/4] 环境自检 (各后端在线状态) ...
python bootstrap.py
echo.

echo [2/4] 回归测试 pytest (期望 95 passed) ...
python -m pytest tests/ -q
echo.

echo [3/4] 黄金链 demo (在线 + 离线 byte-identical) ...
python scripts\run_demo.py
python scripts\run_demo.py --offline
echo.

echo [4/4] Notebook exec 验证 (期望 ALL NOTEBOOKS PASS) ...
python scripts\verify_notebooks.py
echo.

echo ============================================================
echo   自检完成。若以上均为 passed / 6-6 / ALL PASS 即全绿。
echo ============================================================
pause
endlocal
