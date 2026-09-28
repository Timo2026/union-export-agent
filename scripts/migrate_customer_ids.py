"""migrate_customer_ids.py — BUG-3 存量客户 ID 归一迁移 (巡检报告 2026-09-25).

把 crm.sqlite3 / crm_sandboxes/ / rag_vectors.json / orders.json / media/docs.json
里的历史客户 ID 统一到规范口径 CUST-<md8(email 优先→name 兜底)[:8] 大写>:

  1. 重复实体合并: 同 email / 同 name 的多行历史 ID → 单一规范行 (计数器相加)
  2. 表引用重写: rfqs/follow_ups/quote_calibration/calibrations/interactions/
     sandbox_quotes/customer_health/preference_profile 的 customer_id 全部改写
  3. 沙箱文件: <old>.sqlite3 → <canonical>.sqlite3, 同规范多文件按 context_id 合并
  4. 测试/探针空壳 ID (None/CUST-NEW/CUST-T1/probe-*...): 零引用才删, 有历史的一律
     按 email/name 归一保留 — 不删业务数据
  5. 别名登记 customer_id_aliases: 旧 ID (含磁盘上历史 context JSON) 仍可解析
  6. 向量库 payload / orders / media / mailbox meta 的 customer_id 同步改写

用法:
  python scripts/migrate_customer_ids.py                 # dry-run (默认, 不落盘)
  python scripts/migrate_customer_ids.py --apply         # 自动备份后执行
  python scripts/migrate_customer_ids.py --root <dir>    # 数据根 (默认 <repo>/data)

回滚: --apply 前把 <root>/backups/customer_ids_<ts>/ 内容拷回 data/ 即可。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from services.customer_id import (  # noqa: E402
    derive_customer_id,
    is_canonical_customer_id,
    is_junk_customer_id,
    normalize_email,
)

# crm.sqlite3 里带 customer_id 列的业务表 (按主键类型分两类处理)
_PLAIN_REF_TABLES = ("rfqs", "follow_ups", "quote_calibration",
                     "calibrations", "interactions")
_PK_TABLES = ("customer_health", "preference_profile")   # customer_id 主键
_PK_SUM_TABLES = ("sandbox_quotes",)                     # (customer_id, context_id) 主键

_SANDBOX_DATA_TABLES = ("rfqs", "quotes", "postmortems", "knowledge_base", "followups")
_SANDBOX_CID_COLS = (
    ("customers", "customer_id"), ("rfqs", "customer_id"),
    ("knowledge_base", "customer_id"), ("followups", "customer_id"),
    ("pricing_model", "customer_id"),
)


def _canonical_for_row(row: Dict[str, Any],
                       aliases: Optional[Dict[str, str]] = None) -> str:
    """email 优先 → name → 旧 ID 自身 (身份缺失的历史壳按旧 ID 派生, 不并桶)。

    身份缺失的壳: 已登记过别名/已是规范格式的 ID 原样保留 — 否则每跑一次
    legacy 派生都会再漂移一次 (非幂等)。
    """
    aliases = aliases or {}
    cid = row["customer_id"]
    seed = (normalize_email(row.get("email"))
            or str(row.get("name") or "").strip().lower())
    if seed:
        return "CUST-" + hashlib.md5(seed.encode("utf-8")).hexdigest()[:8].upper()
    if cid in aliases:
        return aliases[cid]
    if is_canonical_customer_id(cid):
        return cid
    return "CUST-" + hashlib.md5(f"legacy:{cid}".encode("utf-8")).hexdigest()[:8].upper()


def _as_float(v: Any) -> float:
    """SQLite 动态类型: 历史行可能是字符串/None, 排序前统一转 float。"""
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _table_exists(conn: sqlite3.Connection, table: str, db: str = "main") -> bool:
    return conn.execute(
        f"SELECT 1 FROM {db}.sqlite_master WHERE type='table' AND name=?",
        (table,)).fetchone() is not None


def _sandbox_has_data(path: Path) -> bool:
    try:
        con = sqlite3.connect(str(path))
    except sqlite3.Error:
        return True   # 打不开当有数据, 保守不删
    try:
        for t in _SANDBOX_DATA_TABLES:
            if _table_exists(con, t) and con.execute(
                    f"SELECT 1 FROM {t} LIMIT 1").fetchone():
                return True
        return False
    finally:
        con.close()


def build_plan(root: Path) -> Dict[str, Any]:
    crm_path = root / "crm.sqlite3"
    if not crm_path.exists():
        raise SystemExit(f"crm.sqlite3 不存在: {crm_path}")
    conn = sqlite3.connect(str(crm_path))
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM customers")]

    rfq_counts: Dict[str, int] = {}
    if _table_exists(conn, "rfqs"):
        for r in conn.execute("SELECT customer_id, COUNT(*) c FROM rfqs GROUP BY customer_id"):
            rfq_counts[r["customer_id"]] = r["c"]
    aliases: Dict[str, str] = {}
    if _table_exists(conn, "customer_id_aliases"):
        for old, canon in conn.execute(
                "SELECT old_id, canonical_id FROM customer_id_aliases"):
            aliases[old] = canon
    conn.close()

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        row["_canonical"] = _canonical_for_row(row, aliases)
        row["_rfqs"] = rfq_counts.get(row["customer_id"], 0)
        row["_is_junk"] = is_junk_customer_id(row["customer_id"])
        groups.setdefault(row["_canonical"], []).append(row)

    mapping: Dict[str, str] = {}
    deleted: List[str] = []
    plan_groups: List[Dict[str, Any]] = []
    for canon, members in sorted(groups.items()):
        members.sort(key=lambda r: (-r["_rfqs"], -_as_float(r.get("updated_at")),
                                    r["customer_id"] != canon, r["customer_id"]))
        survivor = members[0]
        # 垃圾空壳: 全组唯一成员且零引用 → 删 (组内多人时不删, 走合并)
        if (len(members) == 1 and survivor["_is_junk"] and survivor["_rfqs"] == 0):
            deleted.append(survivor["customer_id"])
            plan_groups.append({"canonical": canon, "survivor": None,
                                "members": [survivor["customer_id"]],
                                "action": "delete"})
            continue
        for m in members:
            mapping[m["customer_id"]] = canon
        plan_groups.append({
            "canonical": canon, "survivor": survivor["customer_id"],
            "members": [m["customer_id"] for m in members],
            "action": "keep" if (len(members) == 1
                                 and survivor["customer_id"] == canon) else "merge",
        })
    return {"root": str(root), "mapping": mapping, "deleted": deleted,
            "groups": plan_groups,
            "changed_customers": sum(1 for o, c in mapping.items() if o != c)}


def _merged_customer_row(members: List[Dict[str, Any]]) -> tuple:
    """组内字段合并: 计数相加 / 时间取最大 / 文本取首个非空 (survivor 优先)。"""
    def first_non_null(key):
        for m in members:
            if m.get(key) is not None:
                return m[key]
        return None

    def max_of(key):
        vals = [(_as_float(m[key]), m[key]) for m in members if m.get(key) is not None]
        return max(vals, key=lambda t: t[0])[1] if vals else None

    def sum_of(key):
        return sum(int(_as_float(m.get(key) or 0)) for m in members)

    return (
        first_non_null("name"), first_non_null("contact_name"),
        first_non_null("email"), first_non_null("country"),
        first_non_null("lifecycle_state"),
        max_of("last_interaction_at"), max_of("last_order_at"),
        sum_of("total_orders"), sum_of("total_revenue"),
        max_of("health_score"), max_of("updated_at"),
    )


def _merge_sandbox_file(src: Path, dst: Path, canonical: str) -> str:
    """src 沙箱并入 dst (canonical)。返回 renamed/merged。"""
    if not dst.exists():
        src.replace(dst)
        con = sqlite3.connect(str(dst))
        for table, col in _SANDBOX_CID_COLS:
            if _table_exists(con, table):
                con.execute(f"UPDATE {table} SET {col}=? WHERE {col}=?",
                            (canonical, src.stem))
        con.commit()
        con.close()
        return "renamed"
    con = sqlite3.connect(str(dst))
    con.execute("ATTACH DATABASE ? AS aux", (str(src),))
    # 先改 aux 侧 customer_id 列再并库: 若并入后统一 UPDATE, 会与已规范的
    # main 行撞 customers.customer_id 主键
    for table, col in _SANDBOX_CID_COLS:
        if _table_exists(con, table, "aux"):
            con.execute(f"UPDATE aux.{table} SET {col}=? WHERE {col}=?",
                        (canonical, src.stem))
    for table in ("customers", "rfqs", "quotes"):
        if _table_exists(con, table) and _table_exists(con, table, "aux"):
            con.execute(f"INSERT OR REPLACE INTO main.{table} SELECT * FROM aux.{table}")
    # postmortems/knowledge_base/followups 自增 id: 弃旧 id 重插, 避免撞主键
    for table in ("postmortems", "knowledge_base", "followups"):
        if _table_exists(con, table) and _table_exists(con, table, "aux"):
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
            data_cols = [c for c in cols if c != "id"]
            collist = ",".join(data_cols)
            con.execute(
                f"INSERT INTO main.{table}({collist}) SELECT {collist} FROM aux.{table}")
    # pricing_model: 取样本多的一方 (训练更充分)
    if _table_exists(con, "pricing_model") and _table_exists(con, "pricing_model", "aux"):
        dst_row = con.execute(
            "SELECT total_quotes FROM main.pricing_model LIMIT 1").fetchone()
        src_row = con.execute(
            "SELECT total_quotes FROM aux.pricing_model LIMIT 1").fetchone()
        if dst_row is None or (src_row and (src_row[0] or 0) > (dst_row[0] or 0)):
            con.execute("INSERT OR REPLACE INTO main.pricing_model SELECT * FROM aux.pricing_model")
    con.commit()
    con.execute("DETACH DATABASE aux")
    con.close()
    src.unlink()
    return "merged"


def _rewrite_json_customer_ids(path: Path, mapping: Dict[str, str],
                                key: str = "customer_id") -> int:
    if not path.exists() or not mapping:
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    n = 0

    def fix(obj):
        nonlocal n
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == key and isinstance(v, str) and v in mapping:
                    obj[k] = mapping[v]
                    n += 1
                else:
                    fix(v)
        elif isinstance(obj, list):
            for it in obj:
                fix(it)

    fix(data)
    if n:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    return n


def _rewrite_vector_json(path: Path, mapping: Dict[str, str]) -> Dict[str, int]:
    out = {"payloads": 0, "collections_renamed": 0}
    if not path.exists() or not mapping:
        return out
    try:
        colls = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    for cname, points in list(colls.items()):
        if cname.startswith("tenant_"):
            for old, new in mapping.items():
                if old == new:
                    continue
                prefix = f"tenant_{old}_"
                if cname.startswith(prefix):
                    target = f"tenant_{new}_" + cname[len(prefix):]
                    if target not in colls:
                        colls[target] = {}
                    colls[target].update(points)
                    del colls[cname]
                    out["collections_renamed"] += 1
                    points = colls[target]
                    break
        for p in (points or {}).values():
            payload = p.get("payload") or {}
            cid = payload.get("customer_id")
            if cid in mapping:
                payload["customer_id"] = mapping[cid]
                out["payloads"] += 1
            tenant = payload.get("tenant_id")
            if tenant in mapping:
                payload["tenant_id"] = mapping[tenant]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(colls, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return out


def _rewrite_qdrant(root: Path, mapping: Dict[str, str]) -> Dict[str, int]:
    """Qdrant local 模式: 只改 payload (集合重命名涉重建, 收益低不动)。"""
    out = {"payloads": 0}
    qdir = root / ".qdrant"
    if not qdir.exists() or not mapping:
        return out
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(path=str(qdir))
        for cname in [c.name for c in client.get_collections().collections]:
            offset = None
            while True:
                points, offset = client.scroll(cname, offset=offset, limit=256,
                                               with_payload=True)
                for p in points:
                    payload = dict(p.payload or {})
                    cid = payload.get("customer_id")
                    if cid in mapping:
                        payload["customer_id"] = mapping[cid]
                        client.upsert(cname, [{
                            "id": p.id, "vector": p.vector, "payload": payload}])
                        out["payloads"] += 1
                if offset is None:
                    break
    except Exception as e:  # qdrant 不可用/无库 → 静默跳过 (JSON 后端为主路径)
        print(f"  [vector-qdrant] 跳过: {e!r}")
    return out


def _backup(root: Path) -> Path:
    ts = time.strftime("%Y%m%d_%H%M%S")
    bak = root / "backups" / f"customer_ids_{ts}"
    n = 1
    while bak.exists():   # 同一秒内二次 apply (幂等测试) 撞名
        bak = root / "backups" / f"customer_ids_{ts}_{n}"
        n += 1
    bak.mkdir(parents=True)
    for name in ("crm.sqlite3", "rag_vectors.json", "orders.json",
                 "media_docs.json"):
        p = root / name
        if p.exists():
            shutil.copy2(p, bak / name)
    media = root / "media" / "docs.json"
    if media.exists():
        (bak / "media").mkdir()
        shutil.copy2(media, bak / "media" / "docs.json")
    sb = root / "crm_sandboxes"
    if sb.exists():
        shutil.copytree(sb, bak / "crm_sandboxes")
    mb = root / "mailbox"
    if mb.exists():
        shutil.copytree(mb, bak / "mailbox")
    return bak


def apply_migration(root: Path, plan: Dict[str, Any]) -> Dict[str, Any]:
    mapping: Dict[str, str] = plan["mapping"]
    deleted: List[str] = plan["deleted"]
    rep: Dict[str, Any] = {"renamed_sandboxes": 0, "merged_sandboxes": 0,
                           "deleted_sandbox_files": 0, "vector": {"payloads": 0},
                           "orders": 0, "media": 0, "mailbox": 0, "tables_rewritten": {}}

    conn = sqlite3.connect(str(root / "crm.sqlite3"), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")

    # 0. 别名表 (幂等)
    conn.execute("CREATE TABLE IF NOT EXISTS customer_id_aliases("
                 "old_id TEXT PRIMARY KEY, canonical_id TEXT, created_at REAL)")

    # 1.  deletions: 垃圾空壳行 + 其空壳沙箱文件
    for cid in deleted:
        conn.execute("DELETE FROM customers WHERE customer_id=?", (cid,))
    conn.commit()

    # 2. 合并组: customers 行
    for g in plan["groups"]:
        canon = g["canonical"]
        members = [m for m in g["members"] if m != canon]
        if not members:
            continue
        rows = [conn.execute("SELECT * FROM customers WHERE customer_id=?", (m,)
                             ).fetchone() for m in [canon] + members]
        rows = [dict(r) for r in rows if r is not None]
        if not rows:
            continue
        merged = _merged_customer_row(rows)
        conn.execute(
            "INSERT OR REPLACE INTO customers(customer_id,name,contact_name,email,"
            "country,updated_at,lifecycle_state,last_interaction_at,last_order_at,"
            "total_orders,total_revenue,health_score) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (canon, *merged))
        conn.execute(f"DELETE FROM customers WHERE customer_id IN "
                     f"({','.join('?' * len(members))})", members)

    # 3. 普通引用表
    for table in _PLAIN_REF_TABLES:
        if not _table_exists(conn, table):
            continue
        n = 0
        for old, new in mapping.items():
            if old == new:
                continue
            n += conn.execute(f"UPDATE {table} SET customer_id=? WHERE customer_id=?",
                              (new, old)).rowcount
        rep["tables_rewritten"][table] = n

    # 4. PK 表: customer_health / preference_profile (合并计数)
    for table in _PK_TABLES:
        if not _table_exists(conn, table):
            continue
        for g in plan["groups"]:
            canon, members = g["canonical"], [m for m in g["members"] if m != canon]
            if not members:
                continue
            rows = [conn.execute(f"SELECT * FROM {table} WHERE customer_id=?", (m,)
                                 ).fetchone() for m in [canon] + members]
            rows = [r for r in rows if r is not None]
            if not rows:
                continue
            base = dict(rows[0])
            base["customer_id"] = canon   # 否则按旧 ID 重插后被下一步 DELETE 抹掉
            if table == "customer_health":
                base["total_quotes"] = sum(r["total_quotes"] or 0 for r in rows)
                base["won_quotes"] = sum(r["won_quotes"] or 0 for r in rows)
                base["lost_quotes"] = sum(r["lost_quotes"] or 0 for r in rows)
            else:
                base["sample_count"] = sum(r["sample_count"] or 0 for r in rows)
            cols = list(base.keys())
            conn.execute(
                f"INSERT OR REPLACE INTO {table}({','.join(cols)}) "
                f"VALUES({','.join('?' * len(cols))})", tuple(base.values()))
            conn.execute(f"DELETE FROM {table} WHERE customer_id IN "
                         f"({','.join('?' * len(members))})", members)

    # 5. sandbox_quotes (cid,ctx 主键 → OR REPLACE 去重)
    if _table_exists(conn, "sandbox_quotes"):
        n = 0
        for old, new in mapping.items():
            if old == new:
                continue
            n += conn.execute("UPDATE sandbox_quotes SET customer_id=? WHERE customer_id=?",
                              (new, old)).rowcount
        rep["tables_rewritten"]["sandbox_quotes"] = n

    # 6. 别名登记
    for old, new in mapping.items():
        if old != new:
            conn.execute("INSERT OR REPLACE INTO customer_id_aliases"
                         "(old_id,canonical_id,created_at) VALUES(?,?,?)",
                         (old, new, time.time()))
    conn.commit()
    conn.close()

    # 7. 沙箱文件
    sb_dir = root / "crm_sandboxes"
    if sb_dir.exists():
        for g in plan["groups"]:
            canon = g["canonical"]
            srcs = [sb_dir / f"{m}.sqlite3" for m in g["members"]
                    if m != canon and (sb_dir / f"{m}.sqlite3").exists()]
            dst = sb_dir / f"{canon}.sqlite3"
            for src in srcs:
                how = _merge_sandbox_file(src, dst, canon)
                rep["renamed_sandboxes" if how == "renamed"
                    else "merged_sandboxes"] += 1
        for cid in deleted:
            f = sb_dir / f"{cid}.sqlite3"
            if f.exists():
                if _sandbox_has_data(f):
                    # 有数据的壳: 保留 — 改名到 legacy 派生规范 ID
                    canon = _canonical_for_row({"customer_id": cid, "email": None,
                                                "name": None})
                    _merge_sandbox_file(f, sb_dir / f"{canon}.sqlite3", canon)
                    rep["renamed_sandboxes"] += 1
                else:
                    f.unlink()
                    rep["deleted_sandbox_files"] += 1
        # 无 customers 行的孤儿沙箱文件
        for f in sorted(sb_dir.glob("*.sqlite3")):
            cid = f.stem
            if cid in mapping or cid in deleted or is_canonical_customer_id(cid):
                continue
            if is_junk_customer_id(cid) and not _sandbox_has_data(f):
                f.unlink()
                rep["deleted_sandbox_files"] += 1
            elif _sandbox_has_data(f):
                canon = _canonical_for_row({"customer_id": cid, "email": None,
                                            "name": None})
                if canon != cid:
                    _merge_sandbox_file(f, sb_dir / f"{canon}.sqlite3", canon)
                    rep["renamed_sandboxes"] += 1

    # 8. 向量库 / orders / media / mailbox
    vec_json = root / "rag_vectors.json"
    if vec_json.exists():
        rep["vector"] = _rewrite_vector_json(vec_json, mapping)
    rep["vector"]["qdrant"] = _rewrite_qdrant(root, mapping)["payloads"]
    rep["orders"] = _rewrite_json_customer_ids(root / "orders.json", mapping)
    # media 注册表两处路径: data/media_docs.json (media_api.REGISTRY 实际路径) +
    # 旧布局 data/media/docs.json (不存在则跳过)
    rep["media"] = _rewrite_json_customer_ids(root / "media_docs.json", mapping)
    rep["media"] += _rewrite_json_customer_ids(root / "media" / "docs.json", mapping)
    mb_dir = root / "mailbox"
    if mb_dir.exists():
        for meta in mb_dir.glob("*.meta.json"):
            rep["mailbox"] += _rewrite_json_customer_ids(meta, mapping)
    return rep


def migrate(root: Path, apply: bool = False) -> Dict[str, Any]:
    plan = build_plan(root)
    report = {**{k: v for k, v in plan.items() if k != "groups"},
              "dry_run": not apply}
    if not apply:
        return report
    backup = _backup(root)
    rep = apply_migration(root, plan)
    report.update(rep)
    report["backup"] = str(backup)
    after = sqlite3.connect(str(root / "crm.sqlite3"))
    report["customers_after"] = after.execute(
        "SELECT COUNT(*) FROM customers").fetchone()[0]
    report["customers_before"] = sum(len(g["members"]) for g in plan["groups"])
    after.close()
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="BUG-3 客户 ID 归一迁移")
    ap.add_argument("--apply", action="store_true", help="执行 (默认 dry-run)")
    ap.add_argument("--root", default="", help="数据根目录 (默认 <repo>/data)")
    args = ap.parse_args()
    root = Path(args.root).resolve() if args.root else _REPO_ROOT / "data"
    report = migrate(root, apply=args.apply)
    out = _REPO_ROOT / "deploy" / "_s4_migrate_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] root={root}")
    print(f"  mapping={len(report['mapping'])} deleted={len(report['deleted'])} "
          f"changed={report['changed_customers']}")
    if args.apply:
        print(f"  backup={report.get('backup')}")
        print(f"  customers: {report['customers_before']} -> {report['customers_after']}")
        print(f"  sandbox renamed={report['renamed_sandboxes']} "
              f"merged={report['merged_sandboxes']} deleted_files={report['deleted_sandbox_files']}")
        print(f"  vector={report['vector']} orders={report['orders']} "
              f"media={report['media']} mailbox={report['mailbox']}")
        print(f"  tables_rewritten={report['tables_rewritten']}")
    print(f"  report -> {out}")


if __name__ == "__main__":
    main()
