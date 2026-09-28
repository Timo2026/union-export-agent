"""inbound_scanner.py — data/inbound 自动扫描 + ZIP 安全解包 + BOM 批量报价入口.

背景 (2026-09-23): file_intake 的 ZIP 解包 (GBK名/嵌套递归/zip-slip 拒绝) 与
scripts/batch_quote 的 BOM 批量报价都已是完备的一等公民, 但全仓零处扫描
data/inbound → ZIP/BOM 丢进该目录后无人处理, 只能靠人工 unzip + 手工跑脚本。
本服务补上这个自动化入口:

  1) 扫描 inbound/**/*.zip            → file_intake.extract_zip 安全解包
  2) 解包产物内发现 BOM xlsx + STEP/PDF → batch_quote.quote_bom 走 OCP 几何报价
  3) inbound/**/*BOM*.xlsx (未打包)   → 同上, assets 取其所在目录

幂等: item key = sha256(abspath+mtime_ns+size), 状态机沿用 mail_puller 词表
(NEW/PROCESSING/DONE/FAILED/HITL/BLOCKED)。同 key 且已 DONE 不重跑; 文件被改动
→ key 变 → 自然重新入队。

发现阶段跳过 *_extracted/ 子树 (那是本服务自己的解包产物, 已在父 zip item 内处理),
避免同一份 BOM 被两条路径重复报价。

铁律: data-stays-local — 只读本机语料, 零网络; 解析失败显式标注, 绝不静默伪造。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# 状态机词表 (与 data/mail_puller/pending.jsonl 保持一致)
STATE_NEW = "NEW"
STATE_PROCESSING = "PROCESSING"
STATE_DONE = "DONE"
STATE_FAILED = "FAILED"
STATE_HITL = "HITL"
STATE_BLOCKED = "BLOCKED"
TERMINAL = {STATE_DONE, STATE_FAILED, STATE_BLOCKED}

# HITL 态 (waiting_human): 需人工介入但不视为失败
STATE_HITL_WAIT = "WAIT_HITL"

# PROCESSING 超过该时长视为 worker 卡死/重启残留 → 允许重入队 (否则重复报价)
STALE_PROCESSING_SEC = 15 * 60


def _atomic_write(path: Path, text: str) -> None:
    """先写临时文件再 rename, 避免半行 JSON 把状态文件写坏。"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def item_key(path: Path) -> str:
    """内容级幂等键: 路径 + mtime_ns + size。文件一变 → key 变 → 重新入队。"""
    st = path.stat()
    h = hashlib.sha256()
    h.update(str(path.resolve()).encode("utf-8"))
    h.update(str(st.st_mtime_ns).encode())
    h.update(str(st.st_size).encode())
    return h.hexdigest()[:16]


class InboundScanner:
    """inbound 目录扫描 + 处理。controller 惰性构建 (只在真正要报价时加载)。"""

    def __init__(self, root: Optional[Path] = None,
                 state_dir: Optional[Path] = None,
                 controller: Any = None, concurrency: int = 4,
                 rag_gateway: Any = None) -> None:
        self.root = Path(root) if root else Path.cwd()
        self.inbound = self.root / "data" / "inbound"
        self.state_dir = Path(state_dir) if state_dir else self.root / "data" / "inbound_scanner"
        self.pending_path = self.state_dir / "pending.jsonl"
        self.state_path = self.state_dir / "state.json"
        self.report_dir = self.state_dir / "reports"
        self._ctrl = controller
        self.concurrency = max(1, int(concurrency))
        # RAG 网关 (zip 邮件断点 4 修复): 显式注入优先 (worker/测试), 否则惰性
        # 借 controller 的 — 与 _quote_bom 同一个 controller, 不另建实例。
        self.rag_gateway = rag_gateway

    # ---------- 状态持久化 ----------
    def _load_items(self) -> Dict[str, Dict[str, Any]]:
        if not self.pending_path.exists():
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        for line in self.pending_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue  # 半行脏数据跳过, 不炸整个扫描器
            iid = d.get("item_id")
            if iid:
                out[iid] = d
        return out

    def _save_items(self, items: Dict[str, Dict[str, Any]]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        # 按入队时间排序写回, 保持文件稳定可 diff
        ordered = sorted(items.values(), key=lambda d: d.get("queued_at", 0))
        _atomic_write(self.pending_path,
                      "".join(json.dumps(d, ensure_ascii=False) + "\n" for d in ordered))

    def _save_state(self, **kw: Any) -> None:
        st: Dict[str, Any] = {"updated_at": time.time()}
        if self.state_path.exists():
            try:
                st.update(json.loads(self.state_path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass
        st.update(kw)
        st["updated_at"] = time.time()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.state_path, json.dumps(st, ensure_ascii=False, indent=1))

    # ---------- 发现 ----------
    def discover(self) -> List[Dict[str, Any]]:
        """扫 inbound, 产出待处理清单 (zip / BOM xlsx)。

        跳过 *_extracted/ 子树 —— 那是本服务自己的解包产物, 已归入父 zip item,
        避免同一份 BOM 被 zip 路径和直接路径重复报价。
        """
        found: List[Dict[str, Any]] = []
        if not self.inbound.exists():
            return found
        for p in sorted(self.inbound.rglob("*")):
            if not p.is_file():
                continue
            if any(part.endswith("_extracted") for part in p.parts):
                continue
            low = p.name.lower()
            kind: Optional[str] = None
            if low.endswith(".zip"):
                kind = "zip"
            elif low.endswith((".xlsx", ".xls", ".csv")) and (
                    "bom" in low or "报价" in p.name or "物料" in p.name):
                kind = "bom"
            if not kind:
                continue
            found.append({
                "kind": kind,
                "path": str(p),
                "name": p.name,
                "size": p.stat().st_size,
                "item_id": item_key(p),
            })
        return found

    # ---------- 入队 (幂等) ----------
    def scan(self, dry_run: bool = False) -> Dict[str, Any]:
        items = self._load_items()
        discovered = self.discover()
        new_n = requeue_n = skip_n = 0
        for d in discovered:
            old = items.get(d["item_id"])
            if old:
                old_state = old.get("state")
                if old_state in TERMINAL | {STATE_HITL_WAIT}:
                    skip_n += 1      # 同内容已终态 → 不重跑
                    continue
                if old_state == STATE_NEW:
                    # 已入队未处理 → 不重复排队。调度器每轮都会 scan, 若把 NEW
                    # 也当 requeue, 每扫一次 attempts 就虚涨一次。
                    skip_n += 1
                    continue
                if old_state == STATE_PROCESSING:
                    started = float(old.get("started_at") or 0)
                    if started and (time.time() - started) <= STALE_PROCESSING_SEC:
                        skip_n += 1  # 可能仍在处理, 不重复入队 (避免双跑)
                        continue
                    requeue_n += 1   # 卡死残留 → 重入队重试
                    continue
                # FAILED → 允许外部重跑后重新入队
                requeue_n += 1
            else:
                new_n += 1
            if not dry_run:
                items[d["item_id"]] = {
                    "item_id": d["item_id"],
                    "kind": d["kind"],
                    "path": d["path"],
                    "name": d["name"],
                    "size": d["size"],
                    "state": STATE_NEW,
                    "queued_at": time.time(),
                    "started_at": None,
                    "finished_at": None,
                    "context_id": None,
                    "error": None,
                    "result": None,
                    "attempts": int((old or {}).get("attempts", 0)) + (0 if not old else 1),
                    "consumer": "inbound_scanner",
                    "driver": "inbound",
                    "source_ref": d["path"],
                }
                self._save_items(items)
        return {"discovered": len(discovered), "new": new_n, "requeued": requeue_n,
                "skipped_done": skip_n,
                "pending": sum(1 for i in items.values() if i.get("state") == STATE_NEW)}

    # ---------- 处理 ----------
    def _get_controller(self):
        if self._ctrl is None:
            from bootstrap import build_controller
            self._ctrl = build_controller()
        return self._ctrl

    def _get_rag_gateway(self):
        """RAG 网关: 显式注入优先; 否则借 controller 的 (同一实例, 不另建)。"""
        if self.rag_gateway is not None:
            return self.rag_gateway
        try:
            gw = getattr(self._get_controller(), "rag_gateway", None)
        except Exception:
            return None
        if gw is not None:
            self.rag_gateway = gw       # 命中后缓存, 不重复借
        return gw

    def _ingest_to_rag(self, zip_path: Path, dest: Path,
                       files: List[Dict[str, Any]]) -> Dict[str, Any]:
        """解包产物 → ingest_docs 向量化 (zip 邮件断点 4 修复, 2026-09-26)。

        黑名单先行 (与 rag_layers.ingest_file 同序): 名称防线先于解析 —
        连 doc_text 都不做; 正文防线在网关 ingest_document 内, 命中项如实记
        blocked 不静默。图纸 VLM 感知不在本钩子范围 (media_api /v1/rag/media
        端口已另行存在); 本钩子只做文本 embedding: BOM/PDF/docx/CSV 正文 +
        STEP 文件头。doc_id = inbound:{zip名}:{rel_path} 稳定 ⇒ upsert 幂等。
        """
        gw = self._get_rag_gateway()
        if gw is None:
            return {"ingested": 0, "blocked": 0, "reason": "no-gateway"}
        from services import file_intake as fi
        from services.rag_layers import sensitive_reason
        base = Path(zip_path).name
        mail_id = Path(zip_path).parent.name
        ingested = 0
        skipped_zip = 0
        blocked: List[Dict[str, str]] = []
        failed: List[Dict[str, str]] = []
        for f in files:
            rel = str(f.get("rel_path") or "")
            if not rel:
                continue
            fp = dest / rel
            if not fp.is_file():
                continue
            doc_id = f"inbound:{base}:{rel}"
            nr = sensitive_reason(doc_id, "")   # 名称防线: 连解析都不做
            if nr:
                blocked.append({"id": doc_id, "reason": nr})
                continue
            if fi.classify(str(fp)) == "zip":
                skipped_zip += 1                # 嵌套 zip 已被 extract_zip 递归展开
                continue
            try:
                dt = fi.doc_text(str(fp))
            except Exception as e:  # noqa: BLE001
                failed.append({"id": doc_id, "error": repr(e)})
                continue
            if not dt.get("ok"):
                continue                        # 图片/二进制无文本, 显式跳过
            try:
                r = gw.ingest_document(
                    doc_id, dt["text"],
                    tags=["inbound", f"mail:{mail_id}", f"kind:{dt.get('kind')}"])
            except Exception as e:  # noqa: BLE001
                failed.append({"id": doc_id, "error": repr(e)})
                continue
            if r.get("ok"):
                ingested += 1
            elif str(r.get("reason", "")).startswith("sensitive"):
                blocked.append({"id": doc_id, "reason": str(r.get("reason"))})
            else:
                failed.append({"id": doc_id,
                               "error": str(r.get("reason") or "rejected")})
        out: Dict[str, Any] = {"ingested": ingested, "blocked": len(blocked)}
        if blocked:
            out["blocked_items"] = blocked
        if failed:
            out["failed"] = failed
        if skipped_zip:
            out["skipped_zip_members"] = skipped_zip
        return out

    def _process_zip(self, path: Path) -> Dict[str, Any]:
        """解包 → 在解包产物里找 BOM + 资产 → 报价。无 BOM 则只出文件清单。"""
        from services import file_intake as fi
        dest = path.with_name(path.name + "_extracted")
        ex = fi.extract_zip(str(path), str(dest))
        if not ex.get("ok"):
            return {"ok": False, "error": ex.get("error"), "stage": "extract_zip"}
        files = ex.get("files") or []
        kinds: Dict[str, int] = {}
        for f in files:
            k = str(f.get("kind") or "unknown")
            kinds[k] = kinds.get(k, 0) + 1
        boms = [f for f in files if f.get("kind") == "excel"]
        steps = [f for f in files if f.get("kind") == "step"]
        pdfs = [f for f in files if f.get("kind") == "pdf"]
        out: Dict[str, Any] = {
            "ok": True, "stage": "extract_zip", "extract_dir": str(dest),
            "n_files": len(files), "kinds": kinds,
            "n_step": len(steps), "n_pdf": len(pdfs),
            "rejected": ex.get("rejected") or [],
            "total_bytes": ex.get("total_bytes"),
        }
        # 双路 C 路 (断点 4 修复): 全部解包产物 → RAG 向量化。无论有无 BOM 都做;
        # RAG 故障只记账不阻报价主链。
        try:
            out["rag"] = self._ingest_to_rag(path, dest, files)
        except Exception as e:  # noqa: BLE001
            out["rag"] = {"ingested": 0, "blocked": 0, "error": repr(e)}
        if not boms:
            out["note"] = "解包成功但未发现 BOM 表格 → 仅登记文件清单, 不报价"
            return out
        # BOM 可能有多个: 逐个报价, 资产目录取其所在目录
        quotes = []
        for b in boms:
            bom_path = dest / str(b.get("rel_path"))
            if not bom_path.is_file():
                continue
            r = self._quote_bom(bom_path, assets_dir=bom_path.parent)
            quotes.append({"bom": str(bom_path), "report": r})
            if r.get("state") == STATE_FAILED:
                out["state"] = STATE_FAILED
                out["error"] = r.get("error")
                out["quotes"] = quotes
                return out
        out["quotes"] = quotes
        out["state"] = STATE_DONE
        return out

    def _quote_bom(self, bom_path: Path, assets_dir: Optional[Path] = None) -> Dict[str, Any]:
        """BOM → 批量报价 (batch_quote 全链: STEP 几何驱动 + 汇总)。"""
        from scripts import batch_quote as bq
        ctrl = self._get_controller()
        try:
            rows = bq.bom_rows(str(bom_path))
            if not rows:
                return {"ok": False, "state": STATE_FAILED,
                        "error": "BOM 无有效行 (表头/物料编码缺失?)"}
            results = bq.quote_bom(rows, ctrl, assets_dir=str(assets_dir) if assets_dir else None,
                                   customer_name="inbound 批量询价")
            stats = bq.summarize(results)
            report = bq.write_report(
                {"bom": str(bom_path), "assets": str(assets_dir) if assets_dir else None,
                 "stats": stats,
                 "results": results},
                str(self.report_dir / f"{item_key(bom_path)}.json"))
            return {"ok": True, "state": STATE_DONE, "report": report, "stats": stats,
                    "n_rows": stats.get("n_rows"), "n_quoted": stats.get("n_quoted"),
                    "sum_total": stats.get("sum_total")}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "state": STATE_FAILED, "error": repr(e)}

    def _process_item(self, it: Dict[str, Any]) -> Dict[str, Any]:
        kind = it.get("kind")
        p = Path(str(it.get("path")))
        if kind == "zip":
            return self._process_zip(p)
        if kind == "bom":
            r = self._quote_bom(p, assets_dir=p.parent)
            st = r.get("stats") or {}
            # 2026-09-23: 此前只透传 ok/state/error/report, 把 n_rows/sum_total 等
            # 统计字段丢了 → 调用方从 item.result 里读不到报价规模, 与 zip 分支不一致。
            return {"ok": bool(r.get("ok")), "state": r.get("state"),
                    "error": r.get("error"), "report": r.get("report"),
                    "stats": st,
                    "n_rows": st.get("n_rows"), "n_quoted": st.get("n_quoted"),
                    "quote_rate": st.get("quote_rate"),
                    "sum_total": st.get("sum_total"),
                    "n_with_step": st.get("n_with_step")}
        return {"ok": False, "state": STATE_BLOCKED, "error": f"unknown kind {kind}"}

    def run_pending(self, limit: int = 0) -> Dict[str, Any]:
        items = self._load_items()
        todo = [i for i in items.values() if i.get("state") == STATE_NEW]
        todo.sort(key=lambda d: d.get("queued_at", 0))
        if limit:
            todo = todo[:limit]
        done_n = fail_n = 0
        for it in todo:
            iid = it["item_id"]
            items[iid]["state"] = STATE_PROCESSING
            items[iid]["started_at"] = time.time()
            self._save_items(items)
            try:
                res = self._process_item(it)
            except Exception as e:  # noqa: BLE001
                res = {"ok": False, "state": STATE_FAILED, "error": repr(e)}
            st = res.get("state") or (STATE_DONE if res.get("ok") else STATE_FAILED)
            # HITL 类 (命中 amount_gate / 需人工确认) 单独标记, 不算失败
            items[iid]["state"] = st
            items[iid]["finished_at"] = time.time()
            items[iid]["result"] = {k: v for k, v in res.items() if k != "results"}
            items[iid]["error"] = res.get("error")
            if res.get("report"):
                items[iid]["context_id"] = Path(str(res["report"])).stem
            self._save_items(items)
            if st == STATE_DONE:
                done_n += 1
            elif st in (STATE_FAILED, STATE_BLOCKED):
                fail_n += 1
        sumry = {"processed": len(todo), "done": done_n, "failed": fail_n}
        self._save_state(last_run_at=time.time(), last_run=sumry,
                         total_items=len(items),
                         pending=sum(1 for i in items.values() if i.get("state") == STATE_NEW))
        return sumry

    def tick(self, limit: int = 0, dry_run: bool = False) -> Dict[str, Any]:
        """扫一次 + 处理一次。调度器/cron 的最小调用单元。"""
        s = self.scan(dry_run=dry_run)
        if dry_run:
            return {"scan": s, "run": None}
        r = self.run_pending(limit=limit)
        return {"scan": s, "run": r}

    def status(self) -> Dict[str, Any]:
        items = self._load_items()
        by: Dict[str, int] = {}
        for i in items.values():
            by[i.get("state", "?")] = by.get(i.get("state", "?"), 0) + 1
        st: Dict[str, Any] = {}
        if self.state_path.exists():
            try:
                st = json.loads(self.state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"total": len(items), "by_state": by, "state_file": str(self.state_path),
                "last_run": st.get("last_run"), "last_run_at": st.get("last_run_at"),
                "inbound_exists": self.inbound.exists()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=None, help="项目根 (默认 cwd)")
    ap.add_argument("--scan", action="store_true", help="只发现+入队, 不处理")
    ap.add_argument("--run", action="store_true", help="只处理已入队项")
    ap.add_argument("--tick", action="store_true", help="扫描 + 处理 (默认)")
    ap.add_argument("--status", action="store_true", help="只打印状态")
    ap.add_argument("--limit", type=int, default=0, help="最多处理 N 项")
    ap.add_argument("--dry-run", action="store_true", help="只发现不入队")
    args = ap.parse_args()

    root = Path(args.root) if args.root else Path.cwd()
    sc = InboundScanner(root=root)
    if args.status:
        print(json.dumps(sc.status(), ensure_ascii=False, indent=1))
        return 0
    if args.scan and not args.run:
        print(json.dumps(sc.scan(dry_run=args.dry_run), ensure_ascii=False, indent=1))
        return 0
    if args.run and not args.scan:
        print(json.dumps(sc.run_pending(limit=args.limit), ensure_ascii=False, indent=1))
        return 0
    print(json.dumps(sc.tick(limit=args.limit, dry_run=args.dry_run), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
