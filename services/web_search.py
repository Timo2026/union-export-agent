"""services.web_search — 联网搜索接入点 (直接调用本地 SearXNG 引擎).

SearXNG 是项目自管的元搜索引擎 (聚合 Bing/Baidu/360/Sogou/Mojeek).
部署形态 (节点): 源码 + 定制 settings.yml 在 ~/searxng, 专用 venv 运行,
由 node_services.sh 以 searxng 服务 (:8080, 仅环回) 托管, watchdog 守护;
livekernel 经 SEARXNG_URL=http://127.0.0.1:8080 消费。
本地 Windows 开发机历史上用 tools/searxng/SearXNG.exe (已不入节点)。

铁律:
  - 不可达时返空 + log warning, 不静默冒充
  - 隐私优先: SearXNG 本地部署, 搜索记录不外发
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

DEFAULT_SEARXNG_URL = os.environ.get("SEARXNG_URL", "")
DEFAULT_TIMEOUT_S = 10


def health(base_url: str = DEFAULT_SEARXNG_URL, timeout_s: float = 3.0) -> bool:
    """检查本地 SearXNG 服务."""
    if not base_url:
        log.warning("[web_search] SEARXNG_URL 未配置 — 联网 lane 关闭")
        return False
    try:
        with urllib.request.urlopen(f"{base_url}/", timeout=timeout_s) as r:
            return r.status == 200
    except Exception:
        return False


def search(query: str, num: int = 5, category: str = "general",
          base_url: str = DEFAULT_SEARXNG_URL, timeout_s: float = DEFAULT_TIMEOUT_S) -> Dict[str, Any]:
    """SearXNG 联网搜索.

    输入: query (搜索词), num (结果数), category (general/news/images/videos)
    输出: {hits: [{title, url, snippet, engine}], mock: bool, _source}
    """
    if not base_url:
        log.warning("[web_search] SEARXNG_URL 未配置 — 联网 lane 关闭")
        return {"hits": [], "mock": False, "_source": "searxng-offline",
                "warning": "SEARXNG_URL 未配置 — 在 livekernel 环境指向本地 SearXNG "
                           "(如 http://127.0.0.1:8080; 节点由 node_services.sh 托管 searxng 服务)"}
    if not health(base_url, timeout_s=2.0):
        log.warning("[web_search] SearXNG 不可达 (%s), 返空", base_url)
        return {"hits": [], "mock": False, "_source": "searxng-offline",
                "warning": f"SearXNG 服务未响应 ({base_url}) — 检查 searxng 服务 "
                           f"(node_services.sh status searxng; 日志 ~/nvidia/logs/searxng.log)"}

    params = f"q={urllib.parse.quote(query)}&format=json&categories={category}"
    try:
        req = urllib.request.Request(f"{base_url}/search?{params}")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read())
            hits = [
                {"title": r.get("title", ""), "url": r.get("url", ""),
                 "snippet": r.get("content", ""), "engine": r.get("engine", "")}
                for r in data.get("results", [])[:num]
            ]
            return {"hits": hits, "mock": False, "_source": f"searxng@{base_url}"}
    except Exception as e:
        log.warning("[web_search] HTTP 失败: %r", e)
        return {"hits": [], "mock": False, "_source": "searxng-error",
                "warning": repr(e)}


def page_summary(url: str, base_url: str = DEFAULT_SEARXNG_URL,
                timeout_s: float = DEFAULT_TIMEOUT_S) -> Optional[str]:
    """调 SearXNG 提取网页摘要 (给 LLM 提供上下文)."""
    if not health(base_url, timeout_s=2.0):
        return None
    try:
        params = f"url={urllib.parse.quote(url)}&format=json"
        req = urllib.request.Request(f"{base_url}/summary?{params}")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            data = json.loads(resp.read())
            return data.get("summary", "")
    except Exception as e:
        log.warning("[web_search] summary 失败: %r", e)
        return None
