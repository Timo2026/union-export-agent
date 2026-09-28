@echo off
chcp 65001 >nul
setlocal ENABLEEXTENSIONS
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ============================================================
echo   Union Manufacturing Export Agent - 一键启动
echo   主干: union-export-agent-livekernel (canonical)
echo ============================================================
echo.

REM ---- 0. 定位 python (系统 3.11) ----
where python >nul 2>nul
if errorlevel 1 (
  echo [ERR] 未找到 python, 请安装 Python 3.11 并加入 PATH
  pause & exit /b 1
)

REM ---- 1. 制造内核 :7862 (在线则跳过, 否则后台启动) ----
echo [1/4] 检查制造内核 :7862 ...
python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:7862/api/health',timeout=3);print('  already ONLINE')" >nul 2>nul
if errorlevel 1 (
  echo   未在线 -^> 后台启动 cnc-ai-brain (引擎 .venv, 首次约 10-30s) ...
  python scripts\start_engine.py --background
) else (
  echo   已在线, 跳过启动
)

REM ---- 2. 上传端口 API :8900 ----
echo [2/4] 启动上传端口 API :8900 ...
python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8900/health',timeout=3)" >nul 2>nul
if errorlevel 1 (
  python scripts\start_api.py --port 8900 --background
) else (
  echo   :8900 已在线, 跳过
)

REM ---- 3. 健康检查 ----
echo [3/4] 健康检查 ...
python -c "import urllib.request,json;print('  API   :',json.loads(urllib.request.urlopen('http://127.0.0.1:8900/health',timeout=6).read().decode()))" 2>nul
python -c "import urllib.request;print('  Engine:',urllib.request.urlopen('http://127.0.0.1:7862/api/health',timeout=6).status)" 2>nul || echo   Engine: 离线 (将自动用 byte-identical 离线内核兜底)

REM ---- 4. 打开 Swagger ----
echo [4/4] 打开 Swagger UI: http://127.0.0.1:8900/docs
start "" http://127.0.0.1:8900/docs

echo.
echo ============================================================
echo   启动完成。常用端点:
echo     POST /v1/upload/{email,step,audio,pdf,excel,image,auto}
echo     POST /v1/rfq/intake   (全模态一次收 -^> 黄金链)
echo     GET  /v1/model-router/status   GET /v1/agent-spec
echo   演示: python scripts\demo_uploads.py
echo   自检: 一键自检.bat
echo ============================================================
echo.
pause
endlocal
