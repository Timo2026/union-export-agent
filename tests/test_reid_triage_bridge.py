"""tests/test_reid_triage_bridge.py — #41 reid_triage 激活回归 (桥 + 两种调用点同源).

背景 (节点实测踩坑): skills/reid-triage/tool.py 与 services/api_server.py 的 Item5 analyze
端点曾各自内联加载 reid 引擎, 且对引擎调用零防护。节点 occ env 无 requests 时引擎 triage()
内 `import requests` 抛 ModuleNotFoundError 冒泡成 HTTP 500; 而节点 staged 的引擎又是 v1.0
(缺 detect_complexity), 直接设 REID_SCRIPT 会让两处一起 AttributeError。两份内联逻辑已漂移。

本文件用测试替身引擎固化四种形态, 保证任何 REID_SCRIPT 指向的引擎都不会把请求打成 500:
  1. v1.5 兼容 + triage 正常      → 确定性决策层全字段, triage_source=engine
  2. v1.5 兼容 + triage 抛 ModuleNotFoundError (occ 无 requests 实况复刻)
                                → triage_source=deterministic_fallback + triage_error 如实标注, 仍 200
  3. v1.0 形 (缺 detect_complexity) → ok=false, reason=reid_engine_incompatible, 列出缺失 API
  4. 脚本不存在                   → ok=false, reason=reid_not_installed
  5. run_protocol 且 LLM 不可达    → degraded=true, analysis=null (不伪造)
另: Item5 /v1/rag/docs/{id}/analyze 与 skill 同走 services.reid_bridge (端点级 200 回归)。
"""
from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import services.api_server as api_server
import services.reid_bridge as rb

ROOT = Path(__file__).resolve().parent.parent

# 测试替身引擎: 复刻 reid-operating-system v1.5 决策层 API 与自带降级路径。
# FAKE_TRIAGE_BOOM=1 → triage() 抛 ModuleNotFoundError, 复刻节点 occ 无 requests 的实况。
FAKE_ENGINE = '''\
"""Reid决策操作系统 v1.5 — 分诊台 + 协议执行器 (测试替身)"""
import os

MODEL = os.environ.get("REID_MODEL", "fake-local-1.5b")
CLOUD_MODEL = os.environ.get("REID_CLOUD_MODEL", "fake-cloud")
OLLAMA_BASE = "http://127.0.0.1:59998"   # 必不通 → LLM 探测快速失败
TIMEOUT = 4


def detect_complexity(user_input):
    if len(user_input) > 40:
        return True, 7, "长文本(41字)"
    return False, 1, "简单(0分): 无复杂信号"


def load_template(name):
    return "系统提示::" + str(name)


def select_template(tr):
    if (tr or {}).get("domain") == "family":
        return "family_education_protocol.txt"
    return "work_protocol.txt"


def build_intervention_block(flags):
    return ""


def _keyword_detect(user_input):
    if "孩子" in user_input:
        return "family"
    if "报价" in user_input:
        return "work"
    return None


def _default_triage(kw=None):
    if kw == "family":
        return {"domain": "family", "type": "family_education", "flags": {},
                "complexity": "low", "template": "教育决策"}
    return {"domain": "general", "type": "quick_qa", "flags": {},
            "complexity": "low", "template": "快速问答"}


def triage(user_input):
    if os.environ.get("FAKE_TRIAGE_BOOM") == "1":
        raise ModuleNotFoundError("No module named 'requests'")
    kw = _keyword_detect(user_input)
    tr = _default_triage(kw)
    if kw:                                  # 引擎内联语义: 关键词覆盖模型误判
        tr["domain"] = kw
    if kw == "work":
        tr["type"] = "deep_research"
        tr["template"] = "深度研究"
        tr["flags"] = {}
    return tr


def execute_protocol(user_input, tr):
    if os.environ.get("FAKE_PROTOCOL_BOOM") == "1":
        raise RuntimeError("boom")
    return None
'''

# v1.0 形替身: 缺 detect_complexity (节点 staged 引擎实况)
FAKE_ENGINE_V10 = '''\
"""Reid决策操作系统 v1.0 — 分诊台 + 协议执行器 (测试替身, 缺 detect_complexity)"""
import os

MODEL = "fake-local"
CLOUD_MODEL = "fake-cloud"
OLLAMA_BASE = "http://127.0.0.1:59998"
TIMEOUT = 4


def load_template(name):
    return "系统提示::" + str(name)


def select_template(tr):
    return "work_protocol.txt"


def build_intervention_block(flags):
    return ""


def _keyword_detect(user_input):
    return "work" if "报价" in user_input else None


def _default_triage(kw=None):
    return {"domain": "general", "type": "quick_qa", "flags": {},
            "complexity": "low", "template": "快速问答"}


def triage(user_input):
    return _default_triage(_keyword_detect(user_input))


def execute_protocol(user_input, tr):
    return None
'''


def _write_engine(tmp_path: Path, src: str) -> str:
    p = tmp_path / "reid_engine.py"
    p.write_text(src, encoding="utf-8")
    return str(p)


@pytest.fixture
def engine(tmp_path, monkeypatch):
    """把 REID_SCRIPT 指向替身引擎并清桥缓存; 返回脚本路径。"""
    path = _write_engine(tmp_path, FAKE_ENGINE)
    monkeypatch.setenv("REID_SCRIPT", path)
    monkeypatch.delenv("FAKE_TRIAGE_BOOM", raising=False)
    monkeypatch.delenv("FAKE_PROTOCOL_BOOM", raising=False)
    rb._CACHE.clear()
    yield path
    rb._CACHE.clear()


def _tool():
    spec = importlib.util.spec_from_file_location(
        "_test_reid_triage_tool", ROOT / "skills" / "reid-triage" / "tool.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeCtx:
    def get_ctrl(self):
        return None


# ---- 1. v1.5 兼容: 决策层全字段确定性 ----
def test_decision_layer_full_when_engine_ok(engine):
    r = _tool().run(FakeCtx(), text="6061 法兰盘 50 件 阳极氧化 报价", run_protocol=False)
    assert r["ok"] is True
    assert r["iron_rule"] == "deterministic"
    c = r["reid"]["complexity"]
    assert c["score"] == 1 and c["cloud"] is False and c["model"] == "fake-local-1.5b"
    t = r["reid"]["triage"]
    assert t["domain"] == "work" and t["type"] == "deep_research"
    assert t["flags"] == []                       # 无 flags → 不产干预块
    assert r["reid"]["intervention"] == ""
    assert r["reid"]["protocol_template"] == "work_protocol.txt"
    assert r["reid"]["system_prompt_preview"].startswith("系统提示::")
    assert r["reid"]["triage_source"] == "engine"
    assert r["reid"]["triage_error"] is None
    assert r["reid"]["engine"] == "reid-operating-system v1.5"
    assert r["reid"]["degraded"] is True and r["reid"]["analysis"] is None   # 未请求协议


def test_complexity_long_text_routes_cloud(engine):
    r = _tool().run(FakeCtx(), text="客" * 60)
    c = r["reid"]["complexity"]
    assert c["cloud"] is True and c["score"] == 7 and c["model"] == "fake-cloud"
    assert r["reid"]["provider"] == "cloud"


def test_family_domain_and_family_template(engine):
    r = _tool().run(FakeCtx(), text="孩子最近不想去幼儿园怎么办")
    t = r["reid"]["triage"]
    assert t["domain"] == "family" and t["type"] == "family_education"
    assert r["reid"]["protocol_template"] == "family_education_protocol.txt"


def test_empty_text_rejected(engine):
    r = _tool().run(FakeCtx(), text="   ")
    assert r["ok"] is False and r["reason"] == "empty_text"


# ---- 2. 节点实况复刻: triage() 抛 ModuleNotFoundError → 引擎自带确定性降级, 不 500 ----
def test_triage_module_error_degrades_deterministically(engine, monkeypatch):
    """occ env 无 requests → call_ollama import 失败; 必须走 _default_triage 且如实标注。"""
    monkeypatch.setenv("FAKE_TRIAGE_BOOM", "1")
    rb._CACHE.clear()
    r = _tool().run(FakeCtx(), text="6061 法兰盘 50 件 阳极氧化 报价")
    assert r["ok"] is True, "环境缺口绝不允许冒泡成 500"
    assert r["reid"]["triage_source"] == "deterministic_fallback"
    assert "ModuleNotFoundError" in r["reid"]["triage_error"]
    assert "requests" in r["reid"]["triage_error"]
    # 降级仍给确定性领域 (关键词预检测覆盖, 同引擎 triage() 内联语义), 不伪造 LLM 分诊
    assert r["reid"]["triage"]["domain"] == "work"
    assert r["reid"]["triage"]["type"] == "quick_qa"     # 缺 LLM → 默认类型, 不冒充分诊
    # 复杂度层不受 triage 影响 (纯规则)
    assert r["reid"]["complexity"]["score"] == 1


def test_analyze_endpoint_200_when_triage_degrades(engine, monkeypatch):
    """Item5 /v1/rag/docs/{id}/analyze 与 skill 同源: 同样不许 500。"""
    from services.flywheel.vector_store import VectorStore
    from services.rag_layers import HybridEmbedder, LayeredRAGGateway

    monkeypatch.setenv("FAKE_TRIAGE_BOOM", "1")
    rb._CACHE.clear()
    gw = LayeredRAGGateway(store=VectorStore(backend="memory"), crm=None, funasr=None,
                           embedder=HybridEmbedder(url="http://127.0.0.1:59999/v1"))
    gw.ingest_document("doc-41", "6061 阳极氧化 报价 50 件", customer_id="C-41")
    api_server._CTRL = SimpleNamespace(timo=None, funasr=None, settings={}, rag_gateway=gw)
    try:
        with TestClient(api_server.app) as c:
            resp = c.post("/v1/rag/docs/doc-41/analyze")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["reid"]["triage_source"] == "deterministic_fallback"
        assert body["reid"]["degraded"] is True and body["reid"]["analysis"] is None
        assert body["summary"]["chars"] > 0
    finally:
        api_server._CTRL = None
        rb._CACHE.clear()


# ---- 3. v1.0 形引擎: 缺决策层 API → 明确不兼容, 不静默 ----
def test_incompatible_engine_reports_missing_api(tmp_path, monkeypatch):
    path = _write_engine(tmp_path, FAKE_ENGINE_V10)
    monkeypatch.setenv("REID_SCRIPT", path)
    rb._CACHE.clear()
    r = _tool().run(FakeCtx(), text="报价 6061")
    assert r["ok"] is False
    assert r["reason"] == "reid_engine_incompatible"
    assert "detect_complexity" in r["missing"]
    assert "v1.5" in r["note"]
    assert r["reid_script"] == path
    rb._CACHE.clear()


def test_incompatible_engine_endpoint_also_honest(tmp_path, monkeypatch):
    path = _write_engine(tmp_path, FAKE_ENGINE_V10)
    monkeypatch.setenv("REID_SCRIPT", path)
    rb._CACHE.clear()
    from services.flywheel.vector_store import VectorStore
    from services.rag_layers import HybridEmbedder, LayeredRAGGateway

    gw = LayeredRAGGateway(store=VectorStore(backend="memory"), crm=None, funasr=None,
                           embedder=HybridEmbedder(url="http://127.0.0.1:59999/v1"))
    gw.ingest_document("doc-v10", "6061 报价", customer_id="C-1")
    api_server._CTRL = SimpleNamespace(timo=None, funasr=None, settings={}, rag_gateway=gw)
    try:
        with TestClient(api_server.app) as c:
            resp = c.post("/v1/rag/docs/doc-v10/analyze")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False and body["reason"] == "reid_engine_incompatible"
    finally:
        api_server._CTRL = None
        rb._CACHE.clear()


# ---- 4. 引擎缺失 → 诚实报错 (带期望路径) ----
def test_missing_engine_reports_expected_path(tmp_path, monkeypatch):
    monkeypatch.setenv("REID_SCRIPT", str(tmp_path / "absent.py"))
    rb._CACHE.clear()
    r = _tool().run(FakeCtx(), text="报价")
    assert r["ok"] is False and r["reason"] == "reid_not_installed"
    assert "REID_SCRIPT" in r["note"]
    rb._CACHE.clear()


# ---- 5. LLM 协议执行: 不可达 → degraded, 不伪造 ----
def test_run_protocol_degrades_without_llm(engine):
    r = _tool().run(FakeCtx(), text="6061 报价", run_protocol=True)
    assert r["ok"] is True
    assert r["reid"]["degraded"] is True
    assert r["reid"]["analysis"] is None
    assert r["run_protocol"] is True


def test_run_protocol_boom_still_degrades(engine, monkeypatch):
    monkeypatch.setenv("FAKE_PROTOCOL_BOOM", "1")
    rb._CACHE.clear()
    r = _tool().run(FakeCtx(), text="6061 报价", run_protocol=True)
    assert r["ok"] is True and r["reid"]["degraded"] is True
    assert r["reid"]["analysis"] is None
    rb._CACHE.clear()


# ---- 6. 桥自身: 版本提取不写死 ----
def test_engine_version_extracted_from_docstring(engine):
    mod, err = rb.load_engine()
    assert err is None
    assert rb.engine_version(mod) == "reid-operating-system v1.5"


def test_engine_version_unknown_when_unannotated():
    m = SimpleNamespace(__doc__="no version here")
    assert rb.engine_version(m) == "reid-operating-system (版本未标注)"


def test_load_engine_cached_per_path(engine):
    a, _ = rb.load_engine()
    b, _ = rb.load_engine()
    assert a is b


def test_reid_script_prefers_env(monkeypatch):
    monkeypatch.setenv("REID_SCRIPT", "C:/abs/path/reid_engine.py")
    assert rb.reid_script() == "C:/abs/path/reid_engine.py"
