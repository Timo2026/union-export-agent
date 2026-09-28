"""services/search_reid.py — #/search 尽调增强: reid 汇报合成 + 知识库点云数据 (Item D).

铁律:
  - 决策层 (复杂度/分诊/模板/干预) 确定性离线, 复用 services.reid_bridge;
  - LLM 协议执行经 LLMPlanner.chat_raw 走 Omni:8002 lane, 离线诚实降级 (不伪造分析文本);
  - 报价永远由 Timo 引擎裁决 (铁律②): 证据 snippet 禁含报价字段, 汇报不产报价。

不修改 services.reid_bridge / llm_planner 的核心契约; 仅消费其公共 API。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger("search_reid")

# 报告 user_text 截断 + 最多证据数 — 控制 LLM prompt 体量, 节点推理模型 budget 紧张
_SNIPPET_CHARS = 240
_MAX_EVIDENCE = 6
_MAX_SNIPPET_TOTAL = 4000          # 送进决策层 + LLM 的 snippet 上限 (reid_bridge 同口径)
_MAX_BLANK_QUERY = False           # 空 query 显式拒绝

# ---------------------------------------------------------------------------
# 证据净化 (铁律②): 只取 id + 截断文本, 不把 payload 整对象送给 LLM — 避免
# unit_price / amount / total / total_amount 等报价字段泄露。
# ---------------------------------------------------------------------------
_FORBIDDEN_HINT_KEYS = ("unit_price", "amount", "total", "total_amount",
                        "price", "cost", "fee", "subtotal")


def _clean_payload_text(p: Dict[str, Any]) -> str:
    """从 hit payload 抽白名单字段的纯文本, 不出现任何报价/金额键名或数字串。"""
    text = (p.get("text") or "").strip()
    return text[:_SNIPPET_CHARS]


def _compose_evidence(query: str, rag_hits: List[Dict[str, Any]],
                       web_hits: List[Dict[str, Any]]) -> str:
    """把 query + 检索证据拼成纯文本 snippet, 截断到 _MAX_SNIPPET_TOTAL。"""
    parts: List[str] = [f"[QUERY] {query.strip()}"]
    n_rag = 0
    for h in rag_hits or []:
        if n_rag >= _MAX_EVIDENCE:
            break
        pl = h.get("payload") or {}
        tid = h.get("id") or pl.get("id") or "-"
        text = _clean_payload_text(pl)
        if not text:
            continue
        parts.append(f"[RAG:{tid}] {text}")
        n_rag += 1
    n_web = 0
    for h in web_hits or []:
        if n_web >= _MAX_EVIDENCE:
            break
        title = (h.get("title") or "").strip()
        snippet = (h.get("snippet") or h.get("content") or "").strip()[:_SNIPPET_CHARS]
        if not (title or snippet):
            continue
        parts.append(f"[WEB] {title} — {snippet}".strip(" —"))
        n_web += 1
    snippet = "\n".join(parts)
    return snippet[:_MAX_SNIPPET_TOTAL]


# ---------------------------------------------------------------------------
# reid_report: 决策层 (reid_bridge) + LLM 协议执行 (LLMPlanner.chat_raw)
# ---------------------------------------------------------------------------
def reid_report(query: str, rag_hits: List[Dict[str, Any]],
                web_hits: List[Dict[str, Any]],
                planner: Optional[Any] = None) -> Dict[str, Any]:
    """一次拿全: 引擎决策层 (确定) + LLM 协议执行 (诚实降级) + 证据溯源。

    planner: duck-typed (任何有 chat_raw 属性的对象); None 时跳过 LLM 调用,
    决策层仍完整返回, degraded=True 诚实标注。
    """
    from services import reid_bridge               # 惰性导入, 测试替身 REID_SCRIPT 必须先生效

    if not (query or "").strip():
        return {"ok": False, "reason": "empty_query", "query": query}

    mod, err = reid_bridge.load_engine()
    if mod is None:
        return {"ok": False, "query": query, **err}

    snippet = _compose_evidence(query, rag_hits, web_hits)
    decision, tr = reid_bridge.decision_layer(mod, snippet)

    # 引擎选中的协议模板 + 路由类型替换 (复刻 execute_protocol 的 prompt 构造)
    tmpl_name = decision["protocol_template"]
    system_prompt = (mod.load_template(tmpl_name) or "")
    system_prompt = system_prompt.replace("{routing_type}", tr.get("template") or "快速问答")
    # 拉闸干预: 决策层如有, 注入到 system prompt 尾部
    intervention = decision.get("intervention") or ""
    if intervention:
        system_prompt = f"{system_prompt}\n\n{intervention}".strip()

    llm_out: Optional[Dict[str, Any]] = None
    if planner is not None:
        try:
            llm_out = planner.chat_raw(system_prompt, snippet)
        except Exception as e:                                       # noqa: BLE001
            log.warning("[search_reid] planner.chat_raw 异常: %r", e)
            llm_out = {"ok": False, "_mock": True,
                       "_source": f"MOCK(planner exception: {e!r})", "data": None}

    analysis = (llm_out or {}).get("data")
    degraded = (planner is None) or (llm_out is None) \
        or (not llm_out.get("ok", False)) or bool(llm_out.get("_mock"))

    return {
        "ok": True,
        "query": query,
        "decision": decision,
        "protocol_template": tmpl_name,
        "system_prompt_preview": system_prompt[:600],
        "llm": llm_out,                         # 完整来源链 (live/MOCK + 模型)
        "analysis": analysis,                   # 渲染正文 (null = 已降级)
        "degraded": degraded,
        "engine": reid_bridge.engine_version(mod),
        "evidence": {"rag": len(rag_hits or []), "web": len(web_hits or [])},
        "iron_rule": "due-diligence-only",      # 铁律②: 不产报价
    }


# ===========================================================================
# pointcloud: embedding 3D 投影 + kNN 余弦边 (知识图谱点云数据)
# ===========================================================================
def pointcloud(points: List[Dict[str, Any]], k: int = 3,
                max_points: int = 600) -> Dict[str, Any]:
    """把 INGEST_COLLECTION 的点 (id/vector/payload) 投影到 3D + kNN 语义边。

    - PCA via SVD (numpy, 零新依赖, 确定性);
    - 每轴归一化到 [-1, 1] (安全除);
    - kNN 余弦: 每节点连接 top-k (排除自身), 权重为 cosine;
    - 颜色类: payload.tags[0] (空则 "-"), sorted unique → classes 索引;
    - 跳过 vector=None/[]/维数不匹配的点;
    - numpy 不可用时返回 degraded (前端可降级为静态图)。
    """
    out: Dict[str, Any] = {"n": 0, "nodes": [], "edges": [], "classes": [], "degraded": False}
    if not points:
        return out
    try:
        import numpy as np
    except Exception as e:                                       # noqa: BLE001
        log.warning("[search_reid] numpy 不可用, pointcloud 降级: %r", e)
        out["degraded"] = True
        out["reason"] = f"numpy-unavailable: {e!r}"
        return out

    # 过滤可用点
    valid: List[Dict[str, Any]] = []
    for p in points:
        v = p.get("vector")
        if not v:
            continue
        try:
            _ = [float(x) for x in v]
        except Exception:
            continue
        valid.append(p)
    if not valid:
        return out
    if len(valid) > max_points:
        valid = valid[:max_points]

    # 统一维数 (取首个有效维数, 维数不匹配者剔除)
    dim = len(valid[0]["vector"])
    filtered = [p for p in valid if len(p["vector"]) == dim]
    if not filtered:
        return out

    X = np.array([p["vector"] for p in filtered], dtype=np.float64)   # (n, dim)
    n = X.shape[0]
    if n == 0:
        return out

    # 中心化 → SVD → 投影到 3D
    if n == 1:
        coords3 = np.zeros((1, 3), dtype=np.float64)
    else:
        center = X.mean(axis=0, keepdims=True)
        Xc = X - center
        # full_matrices=False; Vt 形状 (min(n,dim), dim)
        try:
            _, _, Vt = np.linalg.svd(Xc, full_matrices=False)
        except np.linalg.LinAlgError as e:
            log.warning("[search_reid] SVD 失败, 退回随机投影: %r", e)
            rng = np.random.default_rng(0)
            Vt = rng.standard_normal((dim, dim))
        k3 = min(3, Vt.shape[0])
        coords3 = Xc @ Vt[:k3].T          # (n, k3)
        if k3 < 3:
            pad = np.zeros((n, 3 - k3))
            coords3 = np.hstack([coords3, pad])

    # 每轴归一化到 [-1, 1]
    for axis in range(3):
        col = coords3[:, axis]
        lo, hi = float(col.min()), float(col.max())
        rng = hi - lo
        if rng > 1e-9:
            coords3[:, axis] = 2.0 * (col - lo) / rng - 1.0
        else:
            coords3[:, axis] = 0.0

    # 颜色类 (稳定排序)
    class_labels: List[str] = []
    seen: Dict[str, None] = {}
    for p in filtered:
        tags = p.get("payload", {}).get("tags") or []
        lbl = tags[0] if tags else "-"
        if lbl not in seen:
            seen[lbl] = None
            class_labels.append(lbl)
    class_labels.sort()
    cls_index = {lbl: i for i, lbl in enumerate(class_labels)}

    nodes: List[Dict[str, Any]] = []
    for i, p in enumerate(filtered):
        tags = p.get("payload", {}).get("tags") or []
        lbl = tags[0] if tags else "-"
        pl = p.get("payload") or {}
        nodes.append({
            "i": i,
            "id": p.get("id"),
            "x": round(float(coords3[i, 0]), 4),
            "y": round(float(coords3[i, 1]), 4),
            "z": round(float(coords3[i, 2]), 4),
            "cls": cls_index[lbl],
            "cls_label": lbl,
            "label": (pl.get("text") or "").strip()[:60],
            "customer_id": pl.get("customer_id"),
            "chars": len(pl.get("text") or ""),
        })

    # kNN 余弦边 (L2 归一化后点积 = 余弦)
    edges: List[List[float]] = []
    if n >= 2 and k >= 1:
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        norms[norms < 1e-9] = 1.0
        Xn = X / norms
        sim = Xn @ Xn.T                       # (n, n) 对角 = 1
        np.fill_diagonal(sim, -2.0)            # 排除自身
        kk = min(k, n - 1)
        # 对每行取 top-k 最大相似度; 同分按行索引稳定 tiebreak (np 默认已稳定)
        idx = np.argpartition(-sim, kk, axis=1)[:, :kk]
        for i in range(n):
            row = idx[i]
            order = np.argsort(-sim[i, row], kind="stable")
            cand = row[order]
            for j in cand:
                a, b = (i, int(j)) if i < j else (int(j), i)
                if a == b:
                    continue
                # 同一对边只入一次 (无向)
                w = float(sim[a, b])
                edges.append([a, b, round(w, 4)])
        # 去重 (按 [a,b] 排序后键)
        seen_e: Dict[tuple, None] = {}
        uniq: List[List[float]] = []
        for e in edges:
            k = (e[0], e[1])
            if k in seen_e:
                continue
            seen_e[k] = None
            uniq.append(e)
        edges = uniq

    out.update({"n": n, "nodes": nodes, "edges": edges, "classes": class_labels})
    return out