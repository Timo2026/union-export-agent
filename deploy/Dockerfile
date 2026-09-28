# Union Export Agent — 上传端口 API 镜像 (Profile B/C 基础)
# 只装主干轻量依赖; 制造内核 (OCP/cadquery) 由独立 engine 镜像/服务提供 (见 docker-compose.yml)。
FROM python:3.11-slim

ENV PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 主干依赖 (黄金链 + 上传端口 + 平台层)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码 (不含引擎 .venv / data 运行产物)
COPY adapters/ ./adapters/
COPY agents/ ./agents/
COPY services/ ./services/
COPY config/ ./config/
COPY schemas/ ./schemas/
COPY bootstrap.py ./
RUN mkdir -p data/contexts data/traces data/artifacts data/demo

EXPOSE 8900
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8900/health',timeout=4).status==200 else 1)"

# 制造内核地址由环境注入 (CNC_BRAIN_URL); 未提供则自动离线 byte-identical 兜底
CMD ["python", "-m", "uvicorn", "services.api_server:app", "--host", "0.0.0.0", "--port", "8900"]
