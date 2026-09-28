"""test_b4_rag_config.py — B4 settings.yaml rag_layers 配置段 + 去硬编码 (任务 #26).

铁律: 端点从配置读取 — rag_layers.embed_url 显式配置优先,
缺省派生自 funasr.embed_url (单一来源, 不再第二处硬编码 :1278)。
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from bootstrap import build_controller
from services.config import load_settings

_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def base_settings(tmp_path):
    s = load_settings(_ROOT)
    s.setdefault("storage", {})["crm_db"] = str(tmp_path / "crm-b4.sqlite3")
    return s


def test_settings_yaml_has_rag_layers_section():
    s = load_settings(_ROOT)
    rl = s.get("rag_layers")
    assert isinstance(rl, dict), "settings.yaml 缺 rag_layers 段"
    assert rl.get("enabled") is True
    assert rl["vector_backend"] in ("memory", "qdrant", "auto", "file")
    # 单一来源不变量 (agents/cat_controller.py:58-61): rag_layers.embed_url 显式配置
    # 必须与 funasr.embed_url 派生值一致。不断言字面端口 — 开发机 :1278 与节点
    # :8011 两 profile 均须成立 (节点 settings.yaml 由部署有意改写, 非缺陷)。
    fu = str(s["funasr"]["embed_url"]).rstrip("/")
    expect = fu if fu.endswith("/v1") else f"{fu}/v1"
    assert rl["embed_url"] == expect, (
        f"rag_layers.embed_url 与 funasr.embed_url 单一来源不一致: "
        f"{rl['embed_url']} != {expect}")


def test_gateway_embed_url_derives_from_funasr_config(base_settings):
    """rag_layers 不写 embed_url → 派生 funasr.embed_url + /v1 (单一配置来源)."""
    base_settings["funasr"]["embed_url"] = "http://127.0.0.1:1999"
    base_settings["rag_layers"] = {"enabled": True, "vector_backend": "memory"}
    ctrl = build_controller(settings_override=base_settings)
    assert ctrl.rag_gateway is not None
    assert ctrl.rag_gateway.embedder.url == "http://127.0.0.1:1999/v1"
    assert ctrl.rag_gateway.store.mode == "memory"


def test_gateway_explicit_embed_url_wins(base_settings):
    base_settings["rag_layers"] = {"enabled": True, "vector_backend": "memory",
                                   "embed_url": "http://127.0.0.1:59999/v1",
                                   "timeout_s": 7}
    ctrl = build_controller(settings_override=base_settings)
    assert ctrl.rag_gateway.embedder.url == "http://127.0.0.1:59999/v1"
    assert ctrl.rag_gateway.embedder.timeout == 7.0


def test_gateway_embed_model_and_prefixes_from_config(base_settings):
    """节点 Profile: embed_model/query/passage 前缀/timeout 全部配置驱动 (v6.3.2)."""
    base_settings["rag_layers"] = {"enabled": True, "vector_backend": "memory",
                                   "embed_url": "http://127.0.0.1:59999/v1",
                                   "timeout_s": 15,
                                   "embed_model": "nemotron-embed-1b",
                                   "embed_query_prefix": "query: ",
                                   "embed_passage_prefix": "passage: "}
    ctrl = build_controller(settings_override=base_settings)
    emb = ctrl.rag_gateway.embedder
    assert emb.model == "nemotron-embed-1b"
    assert emb.query_prefix == "query: "
    assert emb.passage_prefix == "passage: "
    assert emb.timeout == 15.0


def test_gateway_disabled_yields_legacy_path(base_settings):
    base_settings["rag_layers"] = {"enabled": False}
    ctrl = build_controller(settings_override=base_settings)
    assert ctrl.rag_gateway is None


def test_gateway_backfills_stale_history_on_cat_init(base_settings, tmp_path,
                                                     monkeypatch):
    """节点断链修复 (2026-09-26): crm 上千可入库报价 vs quote_history 1 条 —
    cat 初始化必须用落后阈值门禁回填, 追平后幂等不重复烧 embed。

    2026-09-26 起回填转后台 daemon 线程 (同步全量 embed 会卡死 api startup —
    见 tests/test_cat_backfill_nonblocking.py), 故断言改为轮询等追平。"""
    from services.crm_memory import CRMMemory
    from services.flywheel.vector_store import (VectorStore, get_vector_store,
                                                reset_global)
    base_settings["rag_layers"] = {"enabled": True, "vector_backend": "file",
                                   "embed_url": "http://127.0.0.1:59999/v1"}
    db = base_settings["storage"]["crm_db"]
    crm = CRMMemory(db)
    for i in range(3):
        crm.write_rfq({"context_id": f"CTX-BF-{i}", "state": "DONE",
                       "rfq": {"customer": {"customer_id": f"C-BF-{i}"},
                               "material": "6061", "surface": "阳极氧化",
                               "quantity": 50, "tolerance_grade": "IT7"}})
        crm.write_quote({"context_id": f"CTX-BF-{i}",
                         "commercial": {"quote": {"unit_price": 42.0,
                                                  "final_price": 2100.0}}},
                        {"status": "VERIFIED"}, {"subject": "bf"})
    vdb = tmp_path / "vectors-bf.json"
    monkeypatch.setenv("UEA_VECTOR_DB_PATH", str(vdb))
    pre = VectorStore(backend="file")            # 预置 1 条老数据 = 节点现状
    pre.upsert("quote_history", "C-9:CTX-LEGACY", [0.0] * 64,
               {"kind": "quote", "customer_id": "C-9"})
    assert pre.count("quote_history") == 1
    try:
        reset_global()                          # 清会话级单例, 让 file 后端生效
        ctrl = build_controller(settings_override=base_settings)
        assert ctrl.rag_gateway is not None
        assert ctrl.rag_gateway.store.mode == "file"
        # 回填在后台 daemon: 轮询等追平 (embed 不可达 → HashEmbedder 本地降级, 秒级)
        deadline = time.time() + 15
        while (ctrl.rag_gateway.store.count("quote_history") < 4
               and time.time() < deadline):
            time.sleep(0.1)
        assert ctrl.rag_gateway.store.count("quote_history") == 4  # 1 老 + 3 存量
        # 追平后再建 controller: 阈值门禁不重复回填 (count 不变, idempotent)
        ctrl2 = build_controller(settings_override=base_settings)
        deadline = time.time() + 5
        while time.time() < deadline:
            time.sleep(0.1)
        assert ctrl2.rag_gateway.store.count("quote_history") == 4
    finally:
        reset_global()                          # 还清, 别污染后续测试的单例
