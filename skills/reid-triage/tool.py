"""reid-triage skill tool — Reid 决策操作系统分诊 (Item6 新授权, SOP×reid 联动).

被 skills._runtime 自动发现注册; 引擎加载/能力校验/降级统一走 services.reid_bridge —
与 Item5 services/api_server.py:/v1/rag/docs/{id}/analyze 同源, 避免两份内联逻辑再次漂移。
铁律: 决策层 deterministic 离线 / LLM 协议执行诚实降级不伪造 / 不定价 / 不改状态机 /
引擎缺失或版本不匹配时诚实报错, 不静默不冒充。
"""
from __future__ import annotations

from typing import Any, Dict

from services.reid_bridge import analyze, load_engine, reid_script

SKILL_META = {"skill": "reid_triage", "iron_rule": "deterministic",
              "engine": "reid-operating-system",
              "cannot_override_price": True, "advances_state": False}


def run(ctx, text: str = "", run_protocol: bool = False, **kwargs) -> Dict[str, Any]:
    """Reid 分诊: 复杂度/路由/领域/模板/干预 (确定性) + 可选 LLM 协议执行 (诚实降级)."""
    if not text or not str(text).strip():
        return {**SKILL_META, "ok": False, "reason": "empty_text",
                "error": "text 必填 (待分诊的来信/文档/RFQ 文本)"}

    mod, err = load_engine()
    if mod is None:
        return {**SKILL_META, "ok": False, **err}

    snippet = str(text)[:4000]
    reid_out = analyze(mod, snippet, run_protocol=bool(run_protocol))
    return {**SKILL_META, "ok": True, "reid": reid_out,
            "run_protocol": bool(run_protocol), "chars": len(snippet),
            "reid_script": reid_script()}
