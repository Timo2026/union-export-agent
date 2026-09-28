"""tests/test_inbound_scanner_rag.py — 解包产物 RAG 向量化钩子 (Z8, 先红后绿).

断点 4 (方案文档 L23-24): media_api 入库走附件图片/音频; zip 里的 STEP 图纸只有
经过 inbound_scanner→batch_quote 才会做几何+缩略图, 但没有挂 RAG 向量化。
本钩子补上双路中的 C 路一半: 全部有文本的解包产物 → ingest_docs 向量化
(文本 embedding; 图纸 VLM 感知不在本钩子范围 — media_api /v1/rag/media 端口已存在)。

契约 (黑名单先行, 同 ingest_file 防线顺序):
  1) zip 解包后每个有文本产物 → ingest_document, id=inbound:{zip名}:{rel_path}
     (稳定 id → upsert 幂等, 重复入队不翻倍)
  2) 敏感名称先行拦截 (连解析都不做), 敏感正文由 ingest_document 内容防线拦,
     命中项如实记 blocked, 不静默
  3) 嵌套 zip 成员跳过 (extract_zip 已递归展开, 不重复抽取)
  4) 单文件失败/网关异常不阻报价主链 (rag 字段记账, item 状态不受影响)
  5) 无网关 → 显式 no-gateway 跳过, 不炸
  6) 入库后可检索 (search_ingested 命中)
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Dict, List

STEP_HEAD = ("ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION('flange bracket'),"
             "'2;1';\nFILE_NAME('flange.step');\nENDSEC;\n")


def _make_zip(path: Path, members: Dict[str, bytes]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def _mail_zip(tmp_root: Path, mail_id: str, zip_name: str,
              members: Dict[str, bytes]) -> Path:
    """模拟 orchestrator 落盘: data/inbound/{mail_id}/{mail_id}_att_{zip_name}"""
    zpath = tmp_root / "data" / "inbound" / mail_id / f"{mail_id}_att_{zip_name}"
    return _make_zip(zpath, members)


class _FakeGateway:
    """记录 ingest_document 调用的假网关 (不进向量库)。"""

    def __init__(self, boom: bool = False):
        self.calls: List[Dict[str, Any]] = []
        self.boom = boom

    def ingest_document(self, doc_id: str, text: str, customer_id=None,
                        tags=None) -> Dict[str, Any]:
        self.calls.append({"doc_id": doc_id, "text": text,
                           "customer_id": customer_id, "tags": tags})
        if self.boom:
            raise RuntimeError("embed service down")
        return {"ok": True, "id": doc_id}


def _real_gateway():
    """真网关 + 独立内存库 (不用 get_vector_store 单例 — 跨用例会共享污染)。"""
    from services.flywheel.vector_store import InMemoryVectorStore
    from services.rag_layers import LayeredRAGGateway
    return LayeredRAGGateway(store=InMemoryVectorStore())


def _scanner(tmp_root: Path, **kw):
    from services.inbound_scanner import InboundScanner
    return InboundScanner(root=tmp_root, **kw)


# ---------- 1. 无 BOM zip: tick 全链 → 产物向量化 ----------
def test_tick_ingests_extracted_text_docs(tmp_path: Path) -> None:
    # 刻意不放 excel 成员: 任何 .xlsx/.csv 都会被 _process_zip 当 BOM 报价,
    # 本用例只验 RAG 路 (无 BOM → note 分支 → DONE)。.md 亦不行:
    # doc_text 对 unknown 扩展名显式 no-text (既有行为)。
    _mail_zip(tmp_path, "M-RAG-1", "parts.zip", {
        "drawings/flange.step": STEP_HEAD.encode("utf-8"),
        "notes/spec.txt": "flange bracket 6061 表面阳极化".encode("utf-8"),
    })
    gw = _FakeGateway()
    sc = _scanner(tmp_path, rag_gateway=gw)

    r = sc.tick()
    assert r["run"]["processed"] == 1 and r["run"]["done"] == 1

    items = sc._load_items()
    it = items[next(iter(items))]
    assert it["state"] == "DONE"
    rag = it["result"]["rag"]
    assert rag["ingested"] == 2                       # step 头 + txt 两个有文本

    ids = {c["doc_id"] for c in gw.calls}
    assert "inbound:M-RAG-1_att_parts.zip:drawings/flange.step" in ids
    assert "inbound:M-RAG-1_att_parts.zip:notes/spec.txt" in ids
    tags = next(c["tags"] for c in gw.calls
                if c["doc_id"].endswith("spec.txt"))
    assert "inbound" in tags and "mail:M-RAG-1" in tags and "kind:email" in tags


# ---------- 2. 敏感名称先行拦截 (连解析都不做) ----------
def test_sensitive_name_blocked_before_parse(tmp_path: Path) -> None:
    zpath = _mail_zip(tmp_path, "M-RAG-2", "creds.zip", {
        "登录信息表.xlsx": b"not-a-real-xlsx-but-name-guards-first",
        "spec.txt": "法兰件 规格书".encode("utf-8"),
    })
    gw = _FakeGateway()
    sc = _scanner(tmp_path, rag_gateway=gw)
    sc.tick()

    items = sc._load_items()
    rag = items[next(iter(items))]["result"]["rag"]
    assert rag["ingested"] == 1                       # 只有 spec.txt
    assert rag["blocked"] == 1
    blocked = rag["blocked_items"][0]
    assert blocked["reason"] == "sensitive-name"
    assert "登录信息表" in blocked["id"]
    assert all("登录信息表" not in c["doc_id"] for c in gw.calls)


# ---------- 3. 敏感正文由网关内容防线拦 (真网关 + 内存库) ----------
# 注: 用 ASCII 敏感词。中文 "密码:" 在无 MIME 头的 .txt 成员上会被
# doc_text 的 email 解析以 replacement 解坏 (既有行为), 内容防线因此失配 —
# 列为观察项, 不在本钩子范围修 (名称防线对中文名仍有效)。
def test_sensitive_content_blocked_by_gateway(tmp_path: Path) -> None:
    _mail_zip(tmp_path, "M-RAG-3", "mixed.zip", {
        "notes.txt": "server password: abc123456 keep safe".encode("utf-8"),
        "spec.txt": "flange bracket specification 6061".encode("utf-8"),
    })
    gw = _real_gateway()
    sc = _scanner(tmp_path, rag_gateway=gw)
    sc.tick()

    items = sc._load_items()
    rag = items[next(iter(items))]["result"]["rag"]
    assert rag["ingested"] == 1
    assert rag["blocked"] == 1
    assert rag["blocked_items"][0]["reason"] == "sensitive-content"
    assert gw.store.count("ingest_docs") == 1


# ---------- 4. 入库后可检索 ----------
def test_ingested_doc_searchable_after_tick(tmp_path: Path) -> None:
    _mail_zip(tmp_path, "M-RAG-4", "search.zip", {
        "spec.txt": "flange bracket 6061 surface anodized tolerance".encode("utf-8"),
    })
    gw = _real_gateway()
    sc = _scanner(tmp_path, rag_gateway=gw)
    sc.tick()
    hits = gw.search_ingested("flange bracket")
    assert hits, "入库后应可检索"
    assert "flange bracket" in hits[0]["payload"]["text"]


# ---------- 5. 嵌套 zip 成员不重复抽取 ----------
def test_nested_zip_member_skipped(tmp_path: Path) -> None:
    dest = tmp_path / "extracted"
    dest.mkdir()
    (dest / "inner.zip").write_bytes(b"PK\x03\x04 fake")
    (dest / "real.txt").write_text("hello", encoding="utf-8")
    gw = _FakeGateway()
    sc = _scanner(tmp_path, rag_gateway=gw)
    files = [{"rel_path": "inner.zip"}, {"rel_path": "real.txt"}]
    r = sc._ingest_to_rag(tmp_path / "outer.zip", dest, files)
    assert r["ingested"] == 1
    assert r.get("skipped_zip_members") == 1
    assert all(not c["doc_id"].endswith("inner.zip") for c in gw.calls)


# ---------- 6. 单文件失败不阻主链 ----------
def test_ingest_failure_does_not_break_chain(tmp_path: Path) -> None:
    _mail_zip(tmp_path, "M-RAG-5", "boom.zip", {
        "a.txt": "alpha".encode("utf-8"),
        "b.txt": "beta".encode("utf-8"),
    })
    sc = _scanner(tmp_path, rag_gateway=_FakeGateway(boom=True))
    r = sc.tick()
    assert r["run"]["done"] == 1                     # 主链不受 RAG 故障影响
    items = sc._load_items()
    it = items[next(iter(items))]
    assert it["state"] == "DONE"
    rag = it["result"]["rag"]
    assert rag["ingested"] == 0
    assert len(rag.get("failed", [])) == 2
    assert all("embed service down" in f["error"] for f in rag["failed"])


# ---------- 7. 无网关 → 显式跳过不炸 ----------
def test_no_gateway_skips_ingest(tmp_path: Path) -> None:
    from types import SimpleNamespace
    _mail_zip(tmp_path, "M-RAG-6", "nogw.zip", {"a.txt": b"alpha"})
    sc = _scanner(tmp_path, controller=SimpleNamespace())  # 无 rag_gateway 属性
    r = sc.tick()
    assert r["run"]["done"] == 1
    items = sc._load_items()
    rag = items[next(iter(items))]["result"]["rag"]
    assert rag == {"ingested": 0, "blocked": 0, "reason": "no-gateway"}


# ---------- 8. 幂等: 同 doc_id 重复入队不翻倍 ----------
def test_ingest_idempotent_same_doc_id(tmp_path: Path) -> None:
    zpath = _mail_zip(tmp_path, "M-RAG-7", "idem.zip", {"a.txt": b"alpha"})
    dest = zpath.with_name(zpath.name + "_extracted")
    dest.mkdir(parents=True)
    (dest / "a.txt").write_bytes(b"alpha")
    gw = _real_gateway()
    sc = _scanner(tmp_path, rag_gateway=gw)
    files = [{"rel_path": "a.txt"}]
    r1 = sc._ingest_to_rag(zpath, dest, files)
    r2 = sc._ingest_to_rag(zpath, dest, files)
    assert r1["ingested"] == 1 and r2["ingested"] == 1
    assert gw.store.count("ingest_docs") == 1         # upsert 同 id, 不翻倍
