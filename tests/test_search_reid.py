"""tests/test_search_reid.py — #/search 尽调增强 (Item D): search_reid 汇报 + 点云投影.

铁律:
  - 决策层 (复杂度/分诊/模板/干预) 确定性离线; LLM 协议执行诚实降级, 不伪造分析文本。
  - 报价永远由 Timo 引擎裁决 (铁律②): 证据 snippet 禁含报价字段, 汇报不产报价。

本测试覆盖三类契约:
  A. LLMPlanner.chat_raw (新增通用 raw chat 缝) 离线/live 行为
  B. services.search_reid.reid_report 决策层 + LLM 协议执行 + 铁律② 证据洁净
  C. services.search_reid.pointcloud PCA 3D + kNN 语义边 + 颜色类稳定 + 边界

所有测试用替身引擎 / Mock Planner, 不依赖任何真实模型端点。
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import llm_planner as llm_planner_mod
from services.llm_planner import LLMPlanner


ROOT = Path(__file__).resolve().parent.parent


# ============================================================================
# 替身引擎 (reid-operating-system v1.5 决策层 API + 干预触发)
# ============================================================================
FAKE_ENGINE_V15 = '''\
"""Reid决策操作系统 v1.5 — 决策层测试替身 (干预可触发版)"""
import os

MODEL = "fake-local-1.5b"
CLOUD_MODEL = "fake-cloud"
OLLAMA_BASE = "http://127.0.0.1:59998"
TIMEOUT = 4
# 通过环境开关强制 triage 抛 ModuleNotFoundError (复刻节点 occ 实况)
TEMPLATES_DIR = None    # load_template 用此解析路径; 测试用 _TEMPLATES 兜底
_TEMPLATES = {
    "work_protocol.txt": "WORK_PROTOCOL::你是一位报价前尽调专家。基于证据给出 A稳妥 / B强硬 / C止损 三档建议。\\n\\n证据:\\n{evidence}",
    "family_protocol.txt": "FAMILY_PROTOCOL::家庭决策。",
    "quick_qa_protocol.txt": "QUICK_QA_PROTOCOL::快速问答。",
    "daily_protocol.txt": "DAILY_PROTOCOL::日报。",
    "deep_research_protocol.txt": "DEEP::深度研究。",
}


def detect_complexity(text):
    return False, 1, "简单(0分): 无复杂信号"


def load_template(name):
    return _TEMPLATES.get(name, "TEMPLATE::" + str(name))


def select_template(tr):
    return "work_protocol.txt"


def build_intervention_block(flags):
    triggered = [k for k, v in (flags or {}).items() if v]
    if not triggered:
        return ""
    return "## 拉闸干预\\n信号: " + ", ".join(triggered)


def _keyword_detect(text):
    return "work" if any(w in text for w in ("报价", "工艺", "订单")) else None


def _default_triage(kw=None):
    return {"domain": "general", "type": "quick_qa", "flags": {},
            "complexity": "low", "template": "快速问答"}


def triage(text):
    if os.environ.get("FAKE_TRIAGE_BOOM") == "1":
        raise ModuleNotFoundError("No module named 'requests'")
    kw = _keyword_detect(text)
    tr = _default_triage(kw)
    if kw:
        tr["domain"] = "work"
        tr["type"] = "deep_research"
        tr["template"] = "深度研究"
        # 注入可触发干预的标志 (供测试 5)
        if os.environ.get("FAKE_FLAGS_TRIGGER") == "1":
            tr["flags"] = {"emotional": True, "control": False}
    return tr


def execute_protocol(user_input, tr):
    return None
'''


def _write_engine(tmp_path: Path, src: str) -> str:
    p = tmp_path / "reid_engine.py"
    p.write_text(src, encoding="utf-8")
    return str(p)


# ============================================================================
# 替身 Planner: RecordingPlanner 记录 LLM 调用; OfflinePlanner 模拟离线
# ============================================================================
class RecordingPlanner(LLMPlanner):
    """online() 恒 True; chat_raw 把 system/user 记下后返回 canned content。"""
    def __init__(self, content: str, **kwargs):
        super().__init__(endpoint="http://mock/v1", model="mock-llm",
                         backend="local", allow_mock=True, **kwargs)
        self._content = content
        self.calls = []

    def online(self):
        return True

    def chat_raw(self, system_prompt, user_text, **kw):
        self.calls.append({"system": system_prompt, "user": user_text, "kw": kw})
        return {"ok": True, "_mock": False,
                "_source": f"live:{self._active_model()}",
                "data": self._content, "model": "mock-llm"}


class OfflinePlanner(LLMPlanner):
    """online() 恒 False; chat_raw 应走 MOCK 诚实降级路径。"""
    def __init__(self, **kwargs):
        super().__init__(endpoint="http://mock/v1", model="mock-llm",
                         backend="local", allow_mock=True, **kwargs)

    def online(self):
        return False


# ============================================================================
# Fixtures
# ============================================================================
@pytest.fixture
def engine(tmp_path, monkeypatch):
    path = _write_engine(tmp_path, FAKE_ENGINE_V15)
    monkeypatch.setenv("REID_SCRIPT", path)
    monkeypatch.delenv("FAKE_TRIAGE_BOOM", raising=False)
    monkeypatch.delenv("FAKE_FLAGS_TRIGGER", raising=False)
    import services.reid_bridge as rb
    rb._CACHE.clear()
    yield path
    rb._CACHE.clear()


def _rag_hit(doc_id: str, text: str = "", **extra):
    payload = {"text": text, "id": doc_id, "tags": ["inbound"], "customer_id": None}
    payload.update(extra)
    return {"id": doc_id, "score": 0.5, "payload": payload}


def _web_hit(title: str, snippet: str = ""):
    return {"title": title, "snippet": snippet, "url": f"https://x/{title}"}


# ============================================================================
# A. LLMPlanner.chat_raw
# ============================================================================
class _MockPostPlanner(LLMPlanner):
    """online() True; _post_chat 返回 canned 结构 (与 chat_json 测试缝一致)。"""
    def __init__(self, content: str, **kwargs):
        super().__init__(endpoint="http://mock/v1", model="mock-llm",
                         backend="local", allow_mock=True, **kwargs)
        self._content = content
        self.last_payload = None

    def online(self):
        return True

    def _post_chat(self, payload):
        self.last_payload = payload
        return {"model": "mock-llm",
                "choices": [{"message": {"content": self._content}}]}


def test_chat_raw_offline_returns_mock():
    p = OfflinePlanner()
    r = p.chat_raw("sys", "usr")
    assert r["ok"] is False and r["_mock"] is True
    assert "MOCK" in r["_source"]
    assert r["data"] is None


def test_chat_raw_live_passes_messages_and_returns_content():
    p = _MockPostPlanner("## 汇报正文")
    r = p.chat_raw("系统提示A", "用户消息B", temperature=0.0, max_tokens=800)
    assert r["ok"] is True and r["_mock"] is False
    assert r["data"] == "## 汇报正文"
    assert r["_source"] == "live:mock-llm"
    msgs = p.last_payload["messages"]
    assert msgs[0]["role"] == "system" and msgs[0]["content"] == "系统提示A"
    assert msgs[1]["role"] == "user" and msgs[1]["content"] == "用户消息B"
    assert p.last_payload["temperature"] == 0.0


# ============================================================================
# B. search_reid.reid_report
# ============================================================================
def _import_sr():
    from services import search_reid
    return search_reid


def test_report_engine_missing_returns_honest_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("REID_SCRIPT", str(tmp_path / "absent.py"))
    import services.reid_bridge as rb
    rb._CACHE.clear()
    sr = _import_sr()
    r = sr.reid_report("6061 报价", [], [], planner=None)
    assert r["ok"] is False
    assert r["reason"] == "reid_not_installed"
    assert "REID_SCRIPT" in r["note"]
    rb._CACHE.clear()


def test_report_decision_layer_with_fake_engine_no_planner(engine):
    sr = _import_sr()
    r = sr.reid_report("6061 阳极氧化 报价 50 件", [_rag_hit("d1", "历史工艺记录")], [], planner=None)
    assert r["ok"] is True
    # 决策层字段 (确定性)
    assert r["decision"]["complexity"]["score"] == 1
    assert r["decision"]["triage"]["domain"] == "work"
    assert r["decision"]["triage"]["type"] == "deep_research"
    assert r["decision"]["protocol_template"] == "work_protocol.txt"
    assert r["decision"]["triage_source"] == "engine"
    assert "reid-operating-system" in r["engine"]
    # 无 planner → 诚实降级
    assert r["degraded"] is True
    assert r["analysis"] is None
    assert r["llm"] is None


def test_report_offline_planner_marks_degraded_and_source(engine):
    sr = _import_sr()
    r = sr.reid_report("6061 阳极氧化 报价", [_rag_hit("d1", "工艺 A")],
                       [_web_hit("行情")], planner=OfflinePlanner())
    assert r["ok"] is True
    assert r["degraded"] is True
    assert r["analysis"] is None
    assert r["llm"] is not None and r["llm"]["_mock"] is True
    assert "MOCK" in r["llm"]["_source"]


def test_report_live_planner_uses_engine_template(engine):
    sr = _import_sr()
    p = RecordingPlanner("## 尽调: 历史案例相关; 工艺匹配; 建议参考历史报价区间 (区间值须 Timo 裁决)。")
    r = sr.reid_report("6061 阳极氧化 报价", [_rag_hit("d1", "工艺 6061 阳极氧化 历史报价区间 50-80 元")],
                       [_web_hit("市场行情")], planner=p)
    assert r["ok"] is True
    assert r["degraded"] is False
    assert r["analysis"] == p._content
    # 关键: system prompt 必须含引擎模板内容 (work_protocol.txt) + 路由类型替换
    assert len(p.calls) == 1
    sp = p.calls[0]["system"]
    assert "WORK_PROTOCOL::" in sp
    assert "深度研究" in sp or "quick_qa" in sp or "{routing_type}" not in sp
    # user_text 包含 query + 至少一条证据 id
    ut = p.calls[0]["user"]
    assert "6061" in ut
    assert "d1" in ut


def test_report_intervention_block_injected_when_flags_set(engine, monkeypatch):
    monkeypatch.setenv("FAKE_FLAGS_TRIGGER", "1")
    import services.reid_bridge as rb
    rb._CACHE.clear()
    sr = _import_sr()
    p = RecordingPlanner("ok")
    r = sr.reid_report("报价 6061", [_rag_hit("d1", "x")], [], planner=p)
    assert r["ok"] is True
    assert r["decision"]["intervention"] != ""
    assert "拉闸干预" in r["decision"]["intervention"]
    assert "emotional" in r["decision"]["intervention"]
    # 干预应注入到 system_prompt
    assert "拉闸干预" in p.calls[0]["system"]
    rb._CACHE.clear()


def test_report_no_pricing_field_leak_in_evidence(engine):
    """铁律②: 证据 snippet 禁含报价数字/键。即使 RAG 命中 payload 含有 unit_price/amount,
    reid_report 构造的 user_text (送入 LLM) 也必须不出现这些字段 — 报价永远由 Timo 裁决。"""
    sr = _import_sr()
    p = RecordingPlanner("ok")
    # 命中 payload 故意带报价字段
    h = {
        "id": "quote-leak",
        "score": 0.9,
        "payload": {
            "text": "工艺 6061 阳极氧化",
            "tags": ["quote-history"],
            "customer_id": "C1",
            "unit_price": 999.5,        # 绝对不能泄露
            "amount": 12345,             # 绝对不能泄露
            "total": 67890,              # 绝对不能泄露
        },
    }
    sr.reid_report("6061 报价", [h], [], planner=p)
    ut = p.calls[0]["user"]
    # 价格数字 / 字段名都不得出现
    for forbidden in ("999.5", "12345", "67890", "unit_price", "amount", "total"):
        assert forbidden not in ut, f"报价字段 {forbidden} 泄露进 LLM 输入 (铁律②)"


def test_report_empty_query_rejected(engine):
    sr = _import_sr()
    r = sr.reid_report("   ", [], [], planner=None)
    assert r["ok"] is False and r["reason"] == "empty_query"


def test_report_evidence_count_recorded(engine):
    sr = _import_sr()
    r = sr.reid_report("6061 报价",
                       [_rag_hit("a"), _rag_hit("b")],
                       [_web_hit("w1"), _web_hit("w2")], planner=None)
    assert r["evidence"] == {"rag": 2, "web": 2}


# ============================================================================
# C. search_reid.pointcloud
# ============================================================================
def _vec(*vals):
    return [float(v) for v in vals]


def _cluster_points(cls_label: str, base, n: int, dim: int = 8, spread: float = 0.05):
    pts = []
    for i in range(n):
        v = [base[j % len(base)] + (i * 0.001) + (spread * ((i * (j + 1)) % 3 - 1))
             for j in range(dim)]
        pts.append({"id": f"{cls_label}-{i}", "vector": v,
                    "payload": {"tags": [cls_label], "text": f"doc {cls_label} {i}",
                                "customer_id": None}})
    return pts


def test_pointcloud_pca_shape_and_normalized():
    sr = _import_sr()
    pts = _cluster_points("A", [1.0, 0.0], 10) + _cluster_points("B", [0.0, 1.0], 8)
    out = sr.pointcloud(pts, k=3)
    assert out["n"] == 18
    for node in out["nodes"]:
        for c in ("x", "y", "z"):
            assert -1.0 <= node[c] <= 1.0
    # edges 必须合法 (i<j, 落在 [0,n))
    n = out["n"]
    for e in out["edges"]:
        assert 0 <= e[0] < n and 0 <= e[1] < n
        assert e[0] < e[1]
        assert 0.0 <= e[2] <= 1.0          # cosine 权重


def test_pointcloud_deterministic():
    sr = _import_sr()
    pts = _cluster_points("A", [1.0, 0.0], 6) + _cluster_points("B", [0.0, 1.0], 6)
    a = sr.pointcloud(pts, k=3)
    b = sr.pointcloud(pts, k=3)
    assert a["nodes"] == b["nodes"]
    assert a["edges"] == b["edges"]
    assert a["classes"] == b["classes"]


def test_pointcloud_knn_edges_prefer_within_cluster():
    sr = _import_sr()
    a = _cluster_points("A", [1.0, 0.0], 12)
    b = _cluster_points("B", [0.0, 0.0, 0.0, 1.0], 12)
    out = sr.pointcloud(a + b, k=3)
    cls_by_id = {nd["id"]: nd["cls"] for nd in out["nodes"]}
    same = 0
    total = len(out["edges"])
    for i, j, _ in out["edges"]:
        if cls_by_id[out["nodes"][i]["id"]] == cls_by_id[out["nodes"][j]["id"]]:
            same += 1
    # 强聚类: 多数边应在同簇内
    assert same >= int(0.6 * total), f"同簇边占比 {same}/{total} 偏低"


def test_pointcloud_color_classes_stable():
    sr = _import_sr()
    pts = _cluster_points("inbound", [1.0], 4) + _cluster_points("media:image", [2.0], 3)
    out = sr.pointcloud(pts)
    classes = sorted({nd["cls_label"] for nd in out["nodes"]})
    assert "inbound" in classes and "media:image" in classes
    # cls 索引须落在 classes 列表内
    for nd in out["nodes"]:
        assert 0 <= nd["cls"] < len(out["classes"])


def test_pointcloud_skips_vectorless_points():
    sr = _import_sr()
    pts = _cluster_points("A", [1.0], 3)
    pts.append({"id": "no-vec", "vector": None, "payload": {"tags": ["x"]}})
    pts.append({"id": "empty-vec", "vector": [], "payload": {"tags": ["x"]}})
    out = sr.pointcloud(pts)
    assert out["n"] == 3
    ids = {nd["id"] for nd in out["nodes"]}
    assert "no-vec" not in ids and "empty-vec" not in ids


def test_pointcloud_tiny_input_safe():
    sr = _import_sr()
    pts = _cluster_points("A", [1.0], 1)
    out = sr.pointcloud(pts)
    assert out["n"] == 1
    assert out["edges"] == []
    # 单点坐标应退化 (全 0 或 接近 0)
    assert all(abs(out["nodes"][0][c]) < 1e-6 for c in ("x", "y", "z"))


def test_pointcloud_max_points_caps():
    sr = _import_sr()
    pts = _cluster_points("A", [1.0], 50)
    out = sr.pointcloud(pts, max_points=10)
    assert out["n"] == 10


# ============================================================================
# D. api_server 端点契约: /v1/search/reid + /v1/rag/projection
# ============================================================================
from fastapi.testclient import TestClient                                    # noqa: E402

import services.api_server as api_server                                      # noqa: E402


def _build_ctrl(planner=None, rag_docs=None, embedder=None):
    """造 _CTRL: rag_gateway 装好 N 个文档 + 一个可注入的 planner。"""
    from services.flywheel.vector_store import VectorStore
    from services.rag_layers import HybridEmbedder, LayeredRAGGateway

    gw = LayeredRAGGateway(store=VectorStore(backend="memory"),
                           crm=None, funasr=None,
                           embedder=embedder or HybridEmbedder(url="http://127.0.0.1:59999/v1"))
    for doc_id, text in (rag_docs or {"doc-d1": "6061 阳极氧化 历史工艺"}).items():
        gw.ingest_document(doc_id, text, customer_id="C-D")
    return SimpleNamespace(timo=None, funasr=None, settings={},
                           rag_gateway=gw, planner=planner)


def test_search_reid_endpoint_offline_planner_degrades(engine, monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "")           # 离线 web lane, 必返空
    api_server._CTRL = _build_ctrl(planner=OfflinePlanner())
    try:
        with TestClient(api_server.app) as c:
            r = c.get("/v1/search/reid", params={"q": "6061 阳极氧化"})
        assert r.status_code == 200
        b = r.json()
        assert b["ok"] is True
        assert b["degraded"] is True
        assert b["decision"]["triage"]["domain"] == "work"
        assert b["llm"] is not None and b["llm"]["_mock"] is True
        assert b["evidence"] == {"rag": 1, "web": 0}
        assert b["iron_rule"] == "due-diligence-only"
    finally:
        api_server._CTRL = None


def test_search_reid_endpoint_recording_planner_uses_template(engine, monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "")
    p = RecordingPlanner("## 汇报")
    api_server._CTRL = _build_ctrl(planner=p)
    try:
        with TestClient(api_server.app) as c:
            r = c.get("/v1/search/reid", params={"q": "6061 工艺"})
        assert r.status_code == 200
        b = r.json()
        assert b["degraded"] is False
        assert b["analysis"] == "## 汇报"
        assert len(p.calls) == 1
        assert "WORK_PROTOCOL::" in p.calls[0]["system"]
        assert "6061" in p.calls[0]["user"]
    finally:
        api_server._CTRL = None


def test_search_reid_endpoint_empty_query_rejected(engine, monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "")
    api_server._CTRL = _build_ctrl(planner=OfflinePlanner())
    try:
        with TestClient(api_server.app) as c:
            r = c.get("/v1/search/reid", params={"q": "  "})
        assert r.status_code == 200
        b = r.json()
        assert b["ok"] is False and b["reason"] == "empty_query"
    finally:
        api_server._CTRL = None


def test_search_reid_endpoint_no_engine_returns_honest(engine, tmp_path, monkeypatch):
    monkeypatch.setenv("REID_SCRIPT", str(tmp_path / "absent.py"))
    import services.reid_bridge as rb
    rb._CACHE.clear()
    monkeypatch.setenv("SEARXNG_URL", "")
    api_server._CTRL = _build_ctrl(planner=OfflinePlanner())
    try:
        with TestClient(api_server.app) as c:
            r = c.get("/v1/search/reid", params={"q": "6061"})
        assert r.status_code == 200
        b = r.json()
        assert b["ok"] is False and b["reason"] == "reid_not_installed"
    finally:
        api_server._CTRL = None
        rb._CACHE.clear()


def test_search_reid_endpoint_without_rag_gateway_graceful(engine, monkeypatch):
    """无 rag_gateway 时不抛 500: 决策层 + 0 rag 命中 + 联网 (离线) 都安全降级。"""
    monkeypatch.setenv("SEARXNG_URL", "")
    api_server._CTRL = SimpleNamespace(timo=None, funasr=None, settings={},
                                       rag_gateway=None, planner=OfflinePlanner())
    try:
        with TestClient(api_server.app) as c:
            r = c.get("/v1/search/reid", params={"q": "6061"})
        assert r.status_code == 200
        b = r.json()
        assert b["ok"] is True and b["degraded"] is True
        assert b["evidence"]["rag"] == 0 and b["evidence"]["web"] == 0
    finally:
        api_server._CTRL = None


def test_rag_projection_endpoint_returns_nodes_and_edges(engine, monkeypatch):
    monkeypatch.setenv("SEARXNG_URL", "")
    api_server._CTRL = _build_ctrl(planner=None)
    try:
        with TestClient(api_server.app) as c:
            r = c.get("/v1/rag/projection")
        assert r.status_code == 200
        b = r.json()
        assert b["n"] == 1
        assert len(b["nodes"]) == 1
        assert all(k in b["nodes"][0] for k in ("id", "x", "y", "z", "cls", "cls_label"))
    finally:
        api_server._CTRL = None


def test_rag_projection_endpoint_no_rag_gateway_degrades(engine, monkeypatch):
    api_server._CTRL = SimpleNamespace(timo=None, funasr=None, settings={},
                                       rag_gateway=None, planner=None)
    try:
        with TestClient(api_server.app) as c:
            r = c.get("/v1/rag/projection")
        assert r.status_code == 200
        b = r.json()
        assert b["n"] == 0 and b["nodes"] == [] and b["edges"] == []
    finally:
        api_server._CTRL = None