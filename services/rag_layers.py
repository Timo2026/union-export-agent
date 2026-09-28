"""rag_layers.py — B1 分层 RAG 网关 (LayeredRAGGateway).

四层 (核查报告 PRD 2026-09-19, 决策"完整版A"):
  L1 customer      客户信息层  — crm_memory SQL (结构化画像)
  L2 quotes        历史报价层  — VectorStore "quote_history" 集合 (语义相似锚点)
  L3 conversations 客户对话层  — funasr-gui /rag/search (外部进程, 缺则 degraded)
  L4 craft         工艺知识层  — services/rag.py (在线转发 funasr / 离线内置案例)

Embedding: HybridEmbedder 优先 :8011 OpenAI 兼容 /embeddings;
不可达 → HashEmbedder 确定性伪向量, 显式 MOCK 标注 (离线铁律, 不冒充在线).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .flywheel.vector_store import HashEmbedder
from .rag import RAGEvidence

log = logging.getLogger(__name__)

QUOTES_COLLECTION = "quote_history"
INGEST_COLLECTION = "ingest_docs"


def compose_quote_text(material: Any = None, surface: Any = None,
                       tolerance: Any = None, unit_price: Any = None) -> str:
    """报价向量文本 — index_all_quotes 存量回填与 orchestrator 逐票实时钩子
    共用同一口径, 防两处漂移 (2026-09-26 RAG 输出侧闭环)."""
    return (f"材料:{material or ''} 表面:{surface or ''} "
            f"公差:{tolerance or ''} 单价:{unit_price}")


DEFAULT_EMBED_URL = os.environ.get("UEA_EMBED_URL", "http://127.0.0.1:8011/v1")
ALL_LAYERS = ("customer", "quotes", "conversations", "craft")

# BUG-1 P0 敏感入库黑名单: 凭据/密码文档禁入向量库 (公网 /v1/rag/search 可检索全文)。
# 事故原型: 邮件附件 Timo.zip:登录信息表.xlsx (主机名/IP/端口映射/明文密码) 曾以 0.436 顶分可检索。
_SENSITIVE_NAME = re.compile(
    r"(?i)(登录信息|账号信息|密码表|口令表|credential|password|passwd|secret|"
    r"private[_-]?key|id_rsa|access[_-]?key)")
# 正文键值单元格形态: "密码,xxx" / 'password": "xxx' / "密码: xxx" (xlsx 密码列 / 配置段)
_SENSITIVE_TEXT = re.compile(
    r"(?i)(密码|口令|password|passwd|secret)\s*[\"']?\s*[,:：=\t]")


def sensitive_reason(doc_id: str, text: str) -> Optional[str]:
    """敏感文档识别 (BUG-1 P0): 命中返回 reason, 否则 None。

    两道防线: doc_id 名称关键词 (zip 成员 doc_id 含相对路径) + 正文键值单元格。
    CNC 报价/工艺文档不含这些 token 组合, 误伤面可预期; 拦截面全部 log warning。
    """
    if _SENSITIVE_NAME.search(doc_id or ""):
        return "sensitive-name"
    if _SENSITIVE_TEXT.search((text or "")[:2000]):
        return "sensitive-content"
    return None


class HybridEmbedder:
    """OpenAI 兼容 /embeddings 在线 embedding + HashEmbedder 确定性降级. 首次 embed 后定维度.

    粘性降级: 在线失败后冷却 degrade_cooldown_s 秒内直接用 fallback,
    不重复探测 (否则每次 embed 白付 ~2s 连接超时税)。

    非对称双塔 (Nemotron-3-Embed-1B 等) 必须配 query_prefix/passage_prefix:
    缺前缀时检索排序是错的 (节点实测: 相关文档 0.3758 垫底 vs 加前缀 0.5209 第一)。
    对称塔 (Qwen3-Embedding) 留空即存量行为。
    """

    def __init__(self, url: str = DEFAULT_EMBED_URL,
                 transport: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
                 fallback: Optional[HashEmbedder] = None, timeout: float = 3.0,
                 degrade_cooldown_s: float = 60.0,
                 model: str = "qwen3-embedding",
                 query_prefix: str = "", passage_prefix: str = ""):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.degrade_cooldown_s = degrade_cooldown_s
        self.model = model
        self.query_prefix = query_prefix
        self.passage_prefix = passage_prefix
        self._next_probe_at = 0.0
        self._transport = transport
        self._fallback = fallback or HashEmbedder()
        self.degraded: Optional[bool] = None
        self.source: str = "pending"
        self.dim: Optional[int] = None

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self._transport:
            return self._transport(payload)
        req = urllib.request.Request(
            f"{self.url}/embeddings",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _do_fallback(self, text: str) -> List[float]:
        vec = self._fallback.embed(text)
        self.degraded = True
        self.source = "MOCK:hash-embedder"
        self.dim = len(vec)
        return vec

    def embed(self, text: str, kind: str = "passage") -> List[float]:
        """kind: "query"(检索侧) / "passage"(入库侧) — 非对称塔按此注前缀."""
        now = time.monotonic()
        if now < self._next_probe_at:
            return self._do_fallback(text)
        prefix = self.query_prefix if kind == "query" else self.passage_prefix
        try:
            j = self._post({"input": prefix + text, "model": self.model})
            vec = j["data"][0]["embedding"]
            if not isinstance(vec, list) or not vec:
                raise ValueError("empty embedding")
            self.degraded = False
            self.source = f"live:{self.url}"
            self.dim = len(vec)
            self._next_probe_at = 0.0
            return vec
        except Exception as e:
            log.debug("[rag_layers] %s 不可达, 降级 HashEmbedder: %r", self.url, e)
            self._next_probe_at = now + self.degrade_cooldown_s
            return self._do_fallback(text)


class LayeredRAGGateway:
    """统一分层检索入口 (黄金链 B3 改调本类; UI/C2 入库走 index_*)."""

    def __init__(self, store=None, crm=None, funasr=None, rag=None,
                 embedder: Optional[HybridEmbedder] = None):
        self.store = store
        self.crm = crm
        self.funasr = funasr
        self.rag = rag if rag is not None else RAGEvidence(funasr)
        self.embedder = embedder or HybridEmbedder()

    # ---- L2 写入 (B1 提供接口, B2 灌 crm quotes 数据) ----
    def index_quote(self, customer_id: str, quote_id: str, text: str) -> bool:
        if self.store is None:
            return False
        vec = self.embedder.embed(text)
        return self.store.upsert(
            QUOTES_COLLECTION, f"{customer_id}:{quote_id}", vec,
            {"kind": "quote", "customer_id": customer_id,
             "quote_id": quote_id, "text": text},
        )

    # ---- 级联检索 ----
    def index_all_quotes(self) -> int:
        """B2: crm quotes×rfqs 存量回填 quote_history 集合.

        点 id 稳定 (customer_id:context_id), upsert 幂等; 缺 customer_id 的行跳过.
        """
        if self.store is None or self.crm is None:
            return 0
        n = 0
        for d in self.crm.iter_quote_docs():
            if not d.get("customer_id"):
                continue
            text = compose_quote_text(material=d.get("material"),
                                      surface=d.get("surface"),
                                      tolerance=d.get("tolerance"),
                                      unit_price=d.get("unit_price"))
            vec = self.embedder.embed(text)
            self.store.upsert(
                QUOTES_COLLECTION, f"{d['customer_id']}:{d['context_id']}", vec,
                {"kind": "quote", "customer_id": d["customer_id"],
                 "quote_id": d["context_id"], "text": text,
                 "material": d.get("material"), "surface": d.get("surface"),
                 "tolerance": d.get("tolerance"), "unit_price": d.get("unit_price"),
                 "margin_pct": d.get("margin_pct")})
            n += 1
        return n

    def backfill_if_stale(self, stale_ratio: float = 0.9) -> Dict[str, Any]:
        """存量落后阈值回填 (2026-09-26): indexed < eligible × stale_ratio → 全量回填。

        取代 cat 初始化处 count("quote_history")==0 的一次性门禁 — 节点实证该门禁
        使 quote_history 永停在 1 条 (crm 有上千可入库报价), L2 相似召回空转。
        upsert 点 id 稳定 ⇒ 幂等; 追平后不重复烧 embed (在线 embed 首调 ~10s)。
        """
        if self.store is None or self.crm is None:
            return {"backfilled": False, "processed": 0, "eligible": 0,
                    "count": 0, "reason": "no-store-or-crm"}
        eligible = sum(1 for d in self.crm.iter_quote_docs()
                       if d.get("customer_id"))
        before = self.store.count(QUOTES_COLLECTION)
        if eligible == 0:
            return {"backfilled": False, "processed": 0, "eligible": 0,
                    "count": before, "reason": "empty-crm"}
        if before >= eligible * stale_ratio:
            return {"backfilled": False, "processed": 0, "eligible": eligible,
                    "count": before, "reason": "caught-up"}
        n = self.index_all_quotes()
        after = self.store.count(QUOTES_COLLECTION)
        log.info("[rag_layers] quote_history 落后回填: %d→%d (eligible=%d)",
                 before, after, eligible)
        return {"backfilled": True, "processed": n, "eligible": eligible,
                "count": after, "added": after - before, "reason": "stale"}

    def list_similar_quotes(self, query: str, customer_id: Optional[str] = None,
                            limit: int = 5) -> List[Dict[str, Any]]:
        """L2 语义锚点查询 (B3 报价矫正 / 演示引用用)."""
        return self._layer_quotes(query, customer_id, limit)["hits"]

    # ---- C2 文档 ingestion (上传→RAG, L2.5 语义文档集合) ----
    def ingest_document(self, doc_id: str, text: str,
                        customer_id: Optional[str] = None,
                        tags: Optional[List[str]] = None) -> Dict[str, Any]:
        if self.store is None:
            return {"ok": False, "reason": "no-store"}
        text = (text or "").strip()
        if not text:
            return {"ok": False, "id": doc_id, "reason": "empty"}
        reason = sensitive_reason(doc_id, text)
        if reason:
            log.warning("[rag_layers] 拒绝敏感文档入库 (%s): %s", reason, doc_id)
            return {"ok": False, "id": doc_id, "reason": reason}
        vec = self.embedder.embed(text)
        self.store.upsert(
            INGEST_COLLECTION, doc_id, vec,
            {"kind": "doc", "id": doc_id, "text": text,
             "customer_id": customer_id, "tags": tags or [],
             "embed_source": self.embedder.source})
        return {"ok": True, "id": doc_id}

    def ingest_file(self, path: str, customer_id: Optional[str] = None,
                    tags: Optional[List[str]] = None,
                    extract_dir: Optional[str] = None,
                    doc_name: Optional[str] = None) -> Dict[str, Any]:
        """把落盘文件抽文本入库; zip 递归解出的每个文件各成一条 doc, slip 项拒绝不入库。

        doc_name: 上传端口用原始文件名做 id (落盘路径带时间戳前缀)。
        BUG-1 P0: 敏感名称/凭据内容的文档在被拦项 blocked 中如实列出, 不静默。
        """
        from services import file_intake as fi
        kind = fi.classify(path)
        base = (doc_name or Path(path).name)
        if kind == "zip":
            dest = extract_dir or str(Path(path).with_suffix("")) + "_extracted"
            ex = fi.extract_zip(path, dest)
            docs: List[Tuple[str, str]] = []
            blocked: List[Dict[str, str]] = []
            for f in ex["files"]:
                fp = str(Path(dest) / f["rel_path"])
                did = f"{base}:{f['rel_path']}"
                nr = sensitive_reason(did, "")   # 名称防线: 连解析都不做
                if nr:
                    blocked.append({"name": did, "reason": nr})
                    continue
                dt = fi.doc_text(fp)
                if dt["ok"]:
                    docs.append((did, dt["text"]))
            n = 0
            for did, txt in docs:
                r = self.ingest_document(did, txt, customer_id=customer_id, tags=tags)
                if r["ok"]:
                    n += 1
                elif r.get("reason", "").startswith("sensitive"):
                    blocked.append({"name": did, "reason": r["reason"]})
            return {"ok": bool(n), "n_docs": n, "rejected": ex["rejected"],
                    "blocked": blocked, "embed_source": self.embedder.source}
        nr = sensitive_reason(base, "")           # 名称防线先于解析
        if nr:
            log.warning("[rag_layers] 拒绝敏感文件入库 (%s): %s", nr, base)
            return {"ok": False, "n_docs": 0, "reason": nr, "rejected": [],
                    "blocked": [{"name": base, "reason": nr}]}
        dt = fi.doc_text(path)
        if not dt["ok"]:
            return {"ok": False, "n_docs": 0, "reason": dt.get("reason") or "no-text",
                    "rejected": [], "blocked": []}
        r = self.ingest_document(base, dt["text"], customer_id=customer_id, tags=tags)
        out: Dict[str, Any] = {
            "ok": r["ok"], "n_docs": 1 if r["ok"] else 0, "rejected": [],
            "blocked": [], "embed_source": self.embedder.source}
        if not r["ok"] and r.get("reason", "").startswith("sensitive"):
            out["reason"] = r["reason"]
            out["blocked"] = [{"name": base, "reason": r["reason"]}]
        return out

    def search_ingested(self, query: str, customer_id: Optional[str] = None,
                        limit: int = 5) -> List[Dict[str, Any]]:
        if self.store is None:
            return []
        vec = self.embedder.embed(query, kind="query")
        extra = {"customer_id": customer_id} if customer_id else None
        return self.store.search(INGEST_COLLECTION, vec, limit=limit, extra_filter=extra)

    def delete_ingested_doc(self, doc_id: str) -> bool:
        if self.store is None:
            return False
        return self.store.delete(INGEST_COLLECTION, doc_id)

    def list_ingested_docs(self, customer_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """已入库文档清单 (只回元数据, 不回全文)。"""
        if self.store is None:
            return []
        out = []
        for p in self.store.list_points(INGEST_COLLECTION):
            pl = p.get("payload", {})
            if customer_id and pl.get("customer_id") != customer_id:
                continue
            text = pl.get("text", "") or ""
            out.append({"id": p.get("id"), "customer_id": pl.get("customer_id"),
                        "tags": pl.get("tags") or [], "chars": len(text),
                        "indexed_at": pl.get("_indexed_at") or 0})
        return sorted(out, key=lambda d: d["indexed_at"])

    def search(self, query: str, customer_id: Optional[str] = None,
               layers=ALL_LAYERS, top_k: int = 3) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if "customer" in layers:
            out["customer"] = self._layer_customer(query, customer_id)
        if "quotes" in layers:
            out["quotes"] = self._layer_quotes(query, customer_id, top_k)
        if "conversations" in layers:
            out["conversations"] = self._layer_conversations(query, top_k)
        if "craft" in layers:
            out["craft"] = self._layer_craft(query, customer_id, top_k)
        evidence: List[Dict[str, Any]] = []
        for name, lay in out.items():
            lay_src = lay.get("source") or lay.get("_source") or ""
            for h in lay["hits"]:
                ev = dict(h)
                ev["layer"] = name
                # 归一化正文: vector store 命中正文在 payload.text, 单层 hit 用
                # text/note; 统一提到顶层, 否则消费方 (workbench /rag/search 投影)
                # 读顶层 text 恒得 content:"" — 检索到却读不到内容。
                if not (ev.get("text") or ev.get("snippet") or ev.get("note")):
                    payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
                    for key in ("text", "snippet", "note", "content"):
                        if payload.get(key):
                            ev["text"] = payload[key]
                            break
                # 归一化来源: 命中自身不带 source 时回填层来源 (payload 孤立无出处)
                if not (ev.get("source") or ev.get("_source")):
                    ev["source"] = lay_src
                evidence.append(ev)
        return {
            "ok": True,
            "query": query,
            "customer_id": customer_id,
            "layers": out,
            "evidence": evidence,
            "degraded": any(l.get("degraded") for l in out.values()),
        }

    # ---- 各层实现 ----
    def _layer_customer(self, query: str, customer_id: Optional[str]) -> Dict[str, Any]:
        if self.crm is None:
            return {"hits": [], "source": "crm:none", "degraded": True}
        cid = customer_id
        if not cid:
            try:
                cid = self.crm.customer_id_by_name(query)
            except Exception:
                cid = None
        if not cid:
            return {"hits": [], "source": "crm:sql", "degraded": False}
        profile = self.crm.get_customer_profile(cid)
        return {"hits": [{"id": cid, "profile": profile}],
                "source": "crm:sql", "degraded": False}

    def _layer_quotes(self, query: str, customer_id: Optional[str],
                      top_k: int) -> Dict[str, Any]:
        if self.store is None:
            return {"hits": [], "source": "vector:none", "degraded": True}
        vec = self.embedder.embed(query, kind="query")
        extra = {"customer_id": customer_id} if customer_id else None
        hits = self.store.search(QUOTES_COLLECTION, vec, limit=top_k,
                                 extra_filter=extra)
        return {"hits": hits, "source": f"vector:{QUOTES_COLLECTION}",
                "degraded": self.embedder.degraded or False,
                "embed_source": self.embedder.source}

    def _layer_conversations(self, query: str, top_k: int) -> Dict[str, Any]:
        f = self.funasr
        if f is None or not getattr(f, "online", False):
            return {"hits": [], "source": "MOCK:conversations-offline",
                    "degraded": True}
        try:
            r = f.rag_search(query, limit=top_k)
            return {"hits": r.get("hits", []),
                    "source": r.get("_source", "live:/rag/search"),
                    "degraded": bool(r.get("_mock", False))}
        except Exception as e:
            log.warning("[rag_layers] conversations 层失败: %r", e)
            return {"hits": [], "source": "error:conversations", "degraded": True}

    def _layer_craft(self, query: str, customer_id: Optional[str],
                     top_k: int) -> Dict[str, Any]:
        r = self.rag.search(query, limit=top_k, customer_id=customer_id)
        hits = r.get("hits", []) if isinstance(r, dict) else list(r or [])
        return {"hits": hits,
                "source": (r.get("_source", "?") if isinstance(r, dict) else "?"),
                "degraded": bool(r.get("_mock", False)) if isinstance(r, dict) else False}


_gateway: Optional[LayeredRAGGateway] = None


def get_gateway(**kwargs) -> LayeredRAGGateway:
    global _gateway
    if _gateway is None:
        _gateway = LayeredRAGGateway(**kwargs)
    return _gateway


def reset_global() -> None:
    global _gateway
    _gateway = None
