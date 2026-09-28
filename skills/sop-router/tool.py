"""sop-router skill tool — SOP 流程联动路由 (Item6 新授权, SOP×reid 联动).

被 skills._runtime 自动发现注册; 只读 services.rfq_state_machine.TRANSITIONS。
铁律: deterministic / 只读不推进状态机 / 不定价 / 不发外部邮件 / 非法状态诚实报错。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

SKILL_META = {"skill": "sop_router", "iron_rule": "deterministic",
              "source": "rfq_state_machine+domain_knowledge",
              "cannot_override_price": True, "advances_state": False}

# 阶段中文说明
STAGE_DESC = {
    "NEW": "新建 (来信/上传待受理)",
    "INTAKE": "受理 (抽取 canonical RFQ)",
    "STRUCTURING": "结构化 (补全缺失字段)",
    "DFM": "可制造性审查 (材料×表面×几何)",
    "QUOTING": "报价 (引擎唯一定价)",
    "VERIFY": "验收 (policy 裁决 PASS/HITL/BLOCKED)",
    "REPLY": "回复草稿 (draft_only)",
    "CRM_MEM": "CRM 记忆沉淀 (飞轮)",
    "HITL": "人工介入 (信息缺失/冲突/高风险)",
    "HUMAN_APPROVAL": "人工批准",
    "BLOCKED": "阻断 (硬冲突/不可履约)",
    "DONE": "完成 (终态)",
    "ARCHIVED": "归档 (终态)",
}

# 阶段 → 应调度 skill 序列 (SOP 联动表; 全部为已注册 skill id)
STAGE_SKILLS = {
    "NEW": ["parse_rfq"],
    "INTAKE": ["rfq_extraction", "parse_rfq", "material_knowledge"],
    "STRUCTURING": ["extract_specs", "material_knowledge"],
    "DFM": ["check_dfm", "dfm_rules", "dfm_conflict", "step_analysis", "process_knowledge"],
    "QUOTING": ["calc_quote", "cnc_quote", "batch_quote", "quote_correction"],
    "VERIFY": ["verify_gate", "verification"],
    "REPLY": ["write_reply", "reply_draft"],
    "CRM_MEM": ["crm_sync", "submit_feedback", "customer_flywheel", "customer_health"],
    "HITL": ["human_review", "reid_triage"],
    "HUMAN_APPROVAL": ["human_review"],
    "BLOCKED": ["human_review", "reid_triage"],
    "DONE": [],
    "ARCHIVED": [],
}

# reid 协议分诊适用阶段 (有自由文本待路由/干预时)
REID_STAGES = {"NEW", "INTAKE", "STRUCTURING", "HITL", "BLOCKED"}
REID_REASON = {
    "NEW": "来信/上传需 reid 复杂度分诊以路由处理协议",
    "INTAKE": "受理阶段对原始文本做 reid 分诊 + 干预块",
    "STRUCTURING": "结构化阶段用 reid 协议模板引导补全",
    "HITL": "人工介入时 reid 提供分诊摘要 + 干预建议",
    "BLOCKED": "阻断时 reid 辅助归因 + 升级协议",
}


def _resolve_state(state: str, context_id: str) -> Dict[str, Any]:
    """解析当前状态: 显式 state > context_id (CRM 读) > default NEW. 只读, 诚实标注来源."""
    from services.rfq_state_machine import ALL_STATES
    if state:
        s = state.strip().upper()
        if s in ALL_STATES:
            return {"state": s, "state_source": "explicit", "valid": True}
        return {"state": s, "state_source": "explicit", "valid": False,
                "all_states": sorted(ALL_STATES)}
    if context_id:
        # 尽力从 CRM 持久化读当前状态 (读不到诚实降级, 不假造)
        try:
            from services.crm_memory import CRMMemory
            row = CRMMemory().get_quote(context_id)
            if row and row.get("state"):
                s = str(row["state"]).upper()
                if s in ALL_STATES:
                    return {"state": s, "state_source": "crm", "valid": True,
                            "context_id": context_id}
        except Exception:
            pass
        return {"state": "NEW", "state_source": "default", "valid": True,
                "context_id": context_id,
                "note": f"CRM 未读到 context_id={context_id} 的状态, 默认 NEW (只读不假造)"}
    return {"state": "NEW", "state_source": "default", "valid": True,
            "note": "未提供 state/context_id, 默认 NEW"}


def run(ctx, state: str = "", context_id: str = "", target: str = "",
        **kwargs) -> Dict[str, Any]:
    """SOP 路由: 当前阶段 + allowed_next + next_skills + reid 联动 (只读)."""
    from services.rfq_state_machine import TRANSITIONS, TERMINAL, ALL_STATES

    resolved = _resolve_state(state, context_id)
    if not resolved.get("valid"):
        return {**SKILL_META, "ok": False, "reason": "invalid_state",
                "requested_state": resolved.get("state"),
                "all_states": resolved.get("all_states", sorted(ALL_STATES))}

    cur = resolved["state"]
    allowed_next = sorted(TRANSITIONS.get(cur, set()))
    reid_applicable = cur in REID_STAGES

    out = {
        **SKILL_META, "ok": True,
        "state": cur,
        "state_source": resolved["state_source"],
        "stage": STAGE_DESC.get(cur, cur),
        "allowed_next": allowed_next,
        "next_skills": STAGE_SKILLS.get(cur, []),
        "is_terminal": cur in TERMINAL,
        "reid": {
            "applicable": reid_applicable,
            "skill": "reid_triage" if reid_applicable else None,
            "reason": REID_REASON.get(cur, "确定性阶段, 无需 reid 分诊") if reid_applicable else "确定性阶段, 无需 reid 分诊",
        },
    }
    if resolved.get("context_id"):
        out["context_id"] = resolved["context_id"]
    if resolved.get("note"):
        out["note"] = resolved["note"]

    # 可选: 校验 state→target 合法性 (只校验, 不执行转移)
    if target:
        t = target.strip().upper()
        if t not in ALL_STATES:
            out["transition_check"] = {"legal": False, "target": t,
                                       "reason": "unknown target state",
                                       "all_states": sorted(ALL_STATES)}
        else:
            legal = t in TRANSITIONS.get(cur, set())
            out["transition_check"] = {
                "legal": legal, "from": cur, "target": t,
                "reason": None if legal else f"非法转移 {cur}→{t} (状态机权威, 本 skill 不推进)",
                "allowed_next": allowed_next,
            }
    return out
