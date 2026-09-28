"""backfill_conversations.py — 存量往来回填进上层 RAG (客户对话层).

背景: index_conversation 只在新邮件链路生效; 393 个已处理 context 的往来
从未入库 → 老客户的 conversations 层是空的, "消灭信息孤岛"对老客户不成立。

口径 (诚实优先):
  inbox    → rfq.raw_text           (客户真实来信)
  reply    → decision.reply.body    (我们起草的回复)
reply 一律标注 direction="reply" 而非 "sent": 现状 draft_only, 邮件并未真发;
把它冒充成已发送会让后续"订单跟进"判断失真。真·发送记录由发件箱
(Sent Messages) 拉取补入, direction="sent"。

执行顺序铁律: 必须在重启 livekernel 之前跑。运行中的 livekernel 持有旧的
内存态, 它的下一次 upsert 会把整份 rag_vectors.json 按旧内存覆写, 冲掉本次
回填的 conversations 集合。

用法: python scripts/backfill_conversations.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.ERROR)
log = logging.getLogger("backfill")

# __file__ = <root>/scripts/backfill_conversations.py → root 是上一级
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _build_gateway():
    """按 config/settings.yaml 的 rag_layers 段构建与 livekernel 同源的网关。

    不用 get_gateway(): 那是进程内单例, 且 LayeredRAGGateway 不收 settings
    关键字 — 必须显式给 store/embedder, 否则会 TypeError 或静默降级成
    HashEmbedder(mock)。
    """
    from services.config import load_settings
    from services.flywheel.vector_store import get_vector_store
    from services.rag import RAGEvidence
    from services.rag_layers import HybridEmbedder, LayeredRAGGateway

    settings = load_settings(ROOT)
    cfg = settings.get("rag_layers", {}) or {}
    fu = str((settings.get("funasr", {}) or {}).get("embed_url",
                                                    "http://127.0.0.1:1278")).rstrip("/")
    emb = HybridEmbedder(
        url=cfg.get("embed_url") or f"{fu}/v1",
        timeout=float(cfg.get("timeout_s", 15.0)),
        degrade_cooldown_s=float(cfg.get("degrade_cooldown_s", 60.0)),
        model=str(cfg.get("embed_model", "qwen3-embedding")),
        query_prefix=str(cfg.get("embed_query_prefix", "")),
        passage_prefix=str(cfg.get("embed_passage_prefix", "")),
    )
    store = get_vector_store(backend=str(cfg.get("vector_backend", "file")))
    gw = LayeredRAGGateway(store=store, crm=None, funasr=None,
                           rag=RAGEvidence(None), embedder=emb)
    return gw, emb


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    gw, emb = _build_gateway()
    if gw is None or gw.store is None:
        print("FATAL: rag gateway/store 不可用", file=sys.stderr)
        return 2
    print(f"embedder: url={emb.url} degraded={emb.degraded} backend={getattr(gw.store, '_mode', '?')}")

    files = [f for f in sorted((ROOT / "data" / "contexts").glob("*.json"))
             if not f.name.endswith(".audit.json")]
    if args.limit:
        files = files[: args.limit]

    n_in = n_re = n_skip_cid = n_skip_text = 0
    t0 = time.time()
    for i, f in enumerate(files, 1):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [skip] 解析失败 {f.name}: {e!r}")
            continue
        cust = d.get("customer") or {}
        cid = cust.get("customer_id")
        if not cid or str(cid).lower() in ("none", "null"):
            n_skip_cid += 1
            continue
        ctx_id = d.get("context_id") or f.stem
        subj = (cust.get("subject") or (d.get("rfq") or {}).get("subject") or "")[:200]
        raw = (d.get("rfq") or {}).get("raw_text") or ""
        if raw.strip():
            if not args.dry_run:
                gw.index_conversation(cid, ctx_id, text=raw[:4000],
                                      direction="inbox", subject=subj)
            n_in += 1
        else:
            n_skip_text += 1
        reply = (d.get("decision") or {}).get("reply") or {}
        body = (reply.get("body") or "").strip()
        if body:
            if not args.dry_run:
                gw.index_conversation(cid, f"{ctx_id}:reply", text=body[:4000],
                                      direction="reply",
                                      subject=(reply.get("subject") or "")[:200])
            n_re += 1
        if i % 100 == 0:
            el = time.time() - t0
            print(f"  ...{i}/{len(files)} in={n_in} reply={n_re} {el:.0f}s", flush=True)

    dt = time.time() - t0
    print(f"\n回填完成: 扫描 {len(files)} | inbox {n_in} | reply {n_re} | "
          f"跳过(无客户ID) {n_skip_cid} | 跳过(空来信) {n_skip_text} | {dt:.0f}s")
    if not args.dry_run:
        from services.rag_layers import CONVERSATIONS_COLLECTION
        # 2026-09-23 修复: 原来写 gw.store._collections — VectorStore 门面上没有
        # 该属性, 真实数据在门面._backend (JsonFileBackend 常驻内存, _save() 全量
        # 写回 data/rag_vectors.json)。原写法最后那行统计必崩 AttributeError,
        # 回填其实已跑完, 属收尾代码 bug。
        store = gw.store
        holder = store._backend if hasattr(store, "_backend") else store
        coll = getattr(holder, "_collections", {}).get(CONVERSATIONS_COLLECTION, {})
        cids = {p.get("payload", {}).get("customer_id")
                for p in coll.values() if isinstance(p, dict)}
        print(f"向量库 {CONVERSATIONS_COLLECTION}: {len(coll)} 点, 覆盖客户 {len(cids)} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
