"""services/reid_bridge.py — reid-operating-system 引擎桥 (Item5 /v1/rag/docs/{id}/analyze × reid-triage skill 共用).

铁律: 决策层 (复杂度/分诊/模板/干预) 确定性离线; LLM 协议执行诚实降级, 不伪造分析文本。

为什么需要本模块 (踩过的坑): 两个调用点曾各自内联加载逻辑 (已漂移成两份缓存), 且对引擎调用零防护。
节点 occ env 没有 requests 时, 引擎 triage() 内 call_ollama 的 `import requests` 会抛
ModuleNotFoundError 并直接冒泡成 HTTP 500 —— 比"诚实降级"更糟。本模块统一三件事:
  1. 能力校验: 缺 detect_complexity 等决策层 API → 明确 reason=reid_engine_incompatible, 不静默不冒充;
  2. triage() 抛异常 → 走引擎自带确定性降级路径 _default_triage(_keyword_detect()), 并如实标注来源;
  3. LLM 协议执行探测: requests 不可用 / 模型端点不可达 → degraded=true, analysis=null。
"""
from __future__ import annotations

import importlib.util
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger("reid_bridge")

# 桥必收绝对路径 (相对路径→段错误); 部署用 REID_SCRIPT 指向 staged 副本。
# 默认指向仓库内可选外挂副本 <repo>/external/reid-operating-system/...;
# 未安装时 load_engine() 返回 reason=reid_not_installed 并诚实降级 (不伪造分析)。
_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_SCRIPT = str(_REPO_ROOT / "external" / "reid-operating-system" / "scripts" / "reid_engine.py")
# reid-triage skill 契约要求的决策层 API (对应 reid-operating-system v1.5)
_REQUIRED_ATTRS = ("detect_complexity", "triage", "select_template", "load_template")

# path → (module|None, err|None)
_CACHE: Dict[str, Tuple[Optional[Any], Optional[Dict[str, Any]]]] = {}


def reid_script() -> str:
    return os.environ.get("REID_SCRIPT") or _DEFAULT_SCRIPT


def load_engine() -> Tuple[Optional[Any], Optional[Dict[str, Any]]]:
    """惰性加载 reid 引擎并校验决策层能力; 返回 (module, err)。err 非空即不可用。"""
    path = reid_script()
    if path in _CACHE:
        return _CACHE[path]
    p = Path(path)
    if not p.exists():
        res: Tuple[Optional[Any], Optional[Dict[str, Any]]] = (None, {
            "reason": "reid_not_installed", "reid_script": path,
            "note": "reid 引擎脚本不存在; 设 REID_SCRIPT 指向绝对路径 (节点用 staged 副本)"})
    else:
        try:
            spec = importlib.util.spec_from_file_location("reid_engine_bridge", str(p))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.TIMEOUT = int(os.environ.get("REID_TIMEOUT", "4"))   # 离线快速失败, 不挂起
        except Exception as e:                                       # noqa: BLE001
            log.warning("[reid] 加载失败 %s: %r", p, e)
            res = (None, {"reason": "reid_load_failed", "reid_script": path, "error": repr(e)})
        else:
            missing = [a for a in _REQUIRED_ATTRS if not hasattr(mod, a)]
            if missing:
                res = (None, {
                    "reason": "reid_engine_incompatible", "reid_script": path, "missing": missing,
                    "note": "引擎缺决策层 API; 期望 reid-operating-system v1.5, "
                            "把 REID_SCRIPT 指向版本匹配的 staged 副本"})
            else:
                res = (mod, None)
    _CACHE[path] = res
    return res


def engine_version(mod: Any) -> str:
    """从引擎 docstring 提取版本号 — 不写死猜测 (v1.0/v1.5 都有自己的版权行)."""
    doc = (getattr(mod, "__doc__", "") or "").strip()
    m = re.search(r"v\d+(?:\.\d+)*", doc.splitlines()[0] if doc else "")
    return f"reid-operating-system {m.group(0)}" if m else "reid-operating-system (版本未标注)"


def decision_layer(mod: Any, snippet: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """确定性决策层, 返回 (对外结果, 原始 triage 字典)。

    triage() 抛异常 (如 occ env 无 requests → call_ollama import 失败) 时不冒泡:
    按引擎自带降级路径 _default_triage(_keyword_detect()) 产出确定性结果, 并在
    triage_source/triage_error 里如实标注, 绝不伪造 LLM 分诊。
    """
    is_cloud, score, reason = mod.detect_complexity(snippet)
    triage_error: Optional[str] = None
    try:
        tr = mod.triage(snippet) or {}
        triage_source = "engine"
    except Exception as e:                                       # noqa: BLE001
        triage_source = "deterministic_fallback"
        triage_error = f"{type(e).__name__}: {e}"
        log.warning("[reid] triage() 不可用, 走引擎确定性降级路径: %s", triage_error)
        kw = mod._keyword_detect(snippet) if hasattr(mod, "_keyword_detect") else None
        dflt = getattr(mod, "_default_triage", None)
        tr = (dflt(kw) if callable(dflt) else {}) or {}
        # 引擎 triage() 内联语义 "关键词覆盖: 模型可能误判, 关键词更可靠" — 降级时同样套用,
        # 否则关键词预检测的成果会被丢掉 (只剩 general)。
        if kw and isinstance(tr, dict):
            tr["domain"] = kw

    flags = tr.get("flags", {}) or {}
    intervention = mod.build_intervention_block(flags) if any(flags.values()) else ""
    tmpl_name = mod.select_template(tr)
    tmpl = mod.load_template(tmpl_name) or ""
    out = {
        "complexity": {"score": score, "reason": reason, "cloud": bool(is_cloud),
                       "model": (getattr(mod, "CLOUD_MODEL", "") if is_cloud
                                 else getattr(mod, "MODEL", ""))},
        "triage": {"domain": tr.get("domain"), "type": tr.get("type"),
                   "complexity": tr.get("complexity"), "template": tr.get("template"),
                   "flags": [k for k, v in flags.items() if v]},
        "intervention": intervention,
        "protocol_template": tmpl_name,
        "system_prompt_preview": tmpl[:600],
        "triage_source": triage_source,
        "triage_error": triage_error,
    }
    return out, tr


def llm_analysis(mod: Any, snippet: str, tr: Dict[str, Any]) -> Tuple[Optional[str], bool]:
    """LLM 协议执行; 不可用 → (None, True) 诚实降级, 绝不伪造分析文本。"""
    try:
        import requests
        requests.get(f"{mod.OLLAMA_BASE}/api/tags", timeout=2)
        analysis = mod.execute_protocol(snippet, tr)
        degraded = (analysis is None) or ("Reid引擎错误" in analysis) or ("Ollama不可用" in analysis)
        return analysis, degraded
    except Exception as e:                                       # noqa: BLE001
        log.info("[reid] LLM 协议执行不可用 (degraded): %r", e)
        return None, True


def analyze(mod: Any, snippet: str, run_protocol: bool = False) -> Dict[str, Any]:
    """一次拿全: 决策层 (确定) + 可选 LLM 协议执行 (诚实降级) + 版本/来源标注。"""
    out, tr = decision_layer(mod, snippet)
    analysis: Optional[str] = None
    degraded = True
    if run_protocol:
        analysis, degraded = llm_analysis(mod, snippet, tr)
    out["analysis"] = analysis
    out["degraded"] = degraded
    out["provider"] = "cloud" if out["complexity"]["cloud"] else "local"
    out["engine"] = engine_version(mod)
    return out
