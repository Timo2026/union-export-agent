"""model_router.py — L3 Model Mesh 路由 (FAST/VISION/REASON/EMBED/ASR/DETERMINISTIC).

对齐冻结 PRD 第 4 节 +  映射:
  backend = local(funasr/ollama) | nvidia(NIM) | mock
  DETERMINISTIC 角色**永远路由到 Timo 内核**, 不走 LLM (报价/冲突/状态机/毛利)。
  每个角色解析 endpoint+model, 健康探测, 在线/离线显式标注, 不冒充。

v2.3.1 接入 model_config.choose_route() 实现 A/B 路由 + fallback。
  - resolve() 返回的 route dict 多 ab_selected / source / strategy 字段
  - pick(role, request_id=None) 接受 request_id 用于 hash 策略
"""
from __future__ import annotations

import time
import urllib.request
from typing import Any, Dict, Optional

from services.model_config import choose_route, load as load_model_config

ROLES = ["FAST", "VISION", "REASON", "EMBED", "ASR", "DETERMINISTIC"]

# NIM 推理平台 参考端点 (Nemotron 全家族 v3 · 2026-09-20 节点实测栈对齐)
# 模型 ID = hf-mirror API 实测仓库 (200 OK, 体积/文件数见 docs/PRD-MASTER-UEA-DELIVERY.md §1.2-F)
# 端口对齐 deploy/nim/docker-compose.yml + config/models.nvidia-fullstack.yaml:
# 节点真实拓扑 (vLLM 进程级, 单卡统一编排, 2026-09-25 对齐):
#   FAST/VISION/REASON/ASR -> :8002  nemotron-omni-30b-a3b   (Omni-30B any-to-any, 统一走)
#   EMBED                  -> :8011  nemotron-embed-1b        (Embed-1B 专端口)
# 注意: spark-51 docker daemon 无权限 -> NIM 容器线仅为有 docker 权限的目标环境的参考编排;
#       节点实跑 = vLLM 进程级 (config/models.nvidia-fullstack.yaml), :8002=Omni-30B 统一走, backend=local 走 choose_route。
_NIM_DEFAULTS = {
    "FAST": {"endpoint": "http://127.0.0.1:8002/v1", "model": "nemotron-omni-30b-a3b"},
    "VISION": {"endpoint": "http://127.0.0.1:8002/v1", "model": "nemotron-omni-30b-a3b"},
    "REASON": {"endpoint": "http://127.0.0.1:8002/v1", "model": "nemotron-omni-30b-a3b"},
    "EMBED": {"endpoint": "http://127.0.0.1:8011/v1", "model": "nemotron-embed-1b"},
    "ASR": {"endpoint": "http://127.0.0.1:8002/v1", "model": "nemotron-omni-30b-a3b"},
}


class ModelRouter:
    def __init__(self, settings: Dict[str, Any], timo=None):
        mr = (settings or {}).get("model_router", {})
        self.backend: str = str(mr.get("backend", "local"))
        self.roles_cfg: Dict[str, Any] = mr.get("roles", {}) or {}
        self.timo = timo
        # (monotonic_ts, ok) 元组; 无 TTL 的旧版写死首探结果, 后端崩溃后
        # status 仍报 online (节点实测: 30B 死后冒充)。默认 10s 过期。
        self._probe_cache: Dict[str, Any] = {}
        self._probe_ttl: float = float(mr.get("probe_ttl_s", 10))
        # A/B 路由 counter (进程级; 单实例够用)
        self._rr_counter: Dict[str, int] = {}
        # 加载 models.yaml 用于 choose_route
        try:
            self._model_cfg = load_model_config()
        except Exception:
            self._model_cfg = {}

    def _probe(self, endpoint: str, path: str = "/models") -> bool:
        key = endpoint + path
        cached = self._probe_cache.get(key)
        if cached is not None and time.monotonic() - cached[0] <= self._probe_ttl:
            return cached[1]
        ok = False
        try:
            url = endpoint.rstrip("/")
            url = url + path if url.endswith("/v1") else url + "/v1" + path
            with urllib.request.urlopen(url, timeout=3) as r:
                ok = r.status == 200
        except Exception:
            ok = False
        self._probe_cache[key] = (time.monotonic(), ok)
        return ok

    def _role_to_model_key(self, role: str) -> Optional[str]:
        """ROLES → models.yaml key 的映射。"""
        m = {"FAST": "llm", "VISION": "vlm", "REASON": "llm",
             "EMBED": "embedding", "ASR": "asr", "DETERMINISTIC": "deterministic"}
        return m.get(role)

    def _resolve_local(self, role: str, mkey: str,
                       request_id: Optional[str] = None) -> Dict[str, Any]:
        """local backend 路由 (含 C4 A/B fallback 切换)。

        choose_route() 只返回 primary/fallback 元数据 (它自己不在线探测);
        primary 离线 → 调用方责任 = 本方法探测并切 fallback, source=fallback
        诚实标注; 全挂 → 显式 MOCK note (P1 巡检: 节点 Omni :8002 单点)。
        """
        decision = choose_route(mkey, cfg=self._model_cfg, request_id=request_id,
                                round_robin_counter=self._rr_counter)
        ep = decision.get("endpoint") or ""
        strategy = decision.get("strategy")
        if ep and self._probe(ep):
            return {"role": role, "backend": "local", "endpoint": ep,
                    "model": decision.get("model"), "online": True,
                    "source": decision.get("source"), "strategy": strategy, "note": ""}
        fb = decision.get("fallback")
        if isinstance(fb, dict) and fb.get("endpoint") and self._probe(str(fb["endpoint"])):
            return {"role": role, "backend": "local", "endpoint": fb["endpoint"],
                    "model": fb.get("model"), "online": True,
                    "source": "fallback", "strategy": strategy,
                    "note": f"primary 离线 → fallback: {fb.get('model')} @ {fb['endpoint']}"}
        return {"role": role, "backend": "local", "endpoint": ep,
                "model": decision.get("model"), "online": False,
                "source": decision.get("source"), "strategy": strategy,
                "note": "本地端点未就绪 → 显式 MOCK"}

    def resolve(self, role: str) -> Dict[str, Any]:
        if role == "DETERMINISTIC":
            online = bool(self.timo and self.timo.online)
            return {"role": role, "backend": "timo-kernel", "endpoint": getattr(self.timo, "base_url", ""),
                    "model": "calc_quote+ConflictChecker", "online": online,
                    "source": "deterministic", "strategy": "primary_only",
                    "note": "确定性内核, 不走 LLM (报价/冲突/毛利/状态机); 不可配置 A/B"}
        if self.backend == "mock":
            return {"role": role, "backend": "mock", "endpoint": "", "model": "mock",
                    "online": False, "source": "mock", "strategy": "primary_only",
                    "note": "MOCK backend, 显式降级"}
        if self.backend == "nvidia":
            cfg = _NIM_DEFAULTS.get(role, {})
            ep, model = cfg.get("endpoint", ""), cfg.get("model", "")
            online = self._probe(ep) if ep else False
            return {"role": role, "backend": "nvidia-nim", "endpoint": ep, "model": model,
                    "online": online, "source": "nvidia", "strategy": "primary_only",
                    "note": "" if online else "NIM 未就绪 (本机无 NVIDIA 硬件/未部署) → 调用方应降级"}
        # local — 接入 A/B (primary 离线切 fallback)
        return self._resolve_local(role, self._role_to_model_key(role) or role)

    def status(self) -> Dict[str, Any]:
        routes = {r: self.resolve(r) for r in ROLES}
        return {"backend": self.backend,
                "online_roles": [r for r, v in routes.items() if v["online"]],
                "routes": routes}

    def pick(self, role: str, request_id: Optional[str] = None) -> Dict[str, Any]:
        """业务侧取用某角色的当前路由 (含 A/B source / strategy 标注)。"""
        if role == "DETERMINISTIC" or self.backend != "local":
            return self.resolve(role)
        return self._resolve_local(role, self._role_to_model_key(role) or role, request_id)


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from services.config import load_settings
    from adapters.timo_adapter import TimoAdapter
    s = load_settings()
    t = TimoAdapter(s)
    mr = ModelRouter(s, timo=t)
    print(json.dumps(mr.status(), ensure_ascii=False, indent=2))
