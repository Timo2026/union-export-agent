"""sandbox.py — 客户沙箱隔离引擎.

每个客户拥有独立 SQLite 数据库, 完全数据隔离。
跨沙箱只读聚合统计, 不暴露个体数据。
"""
from __future__ import annotations

import re
import sqlite3
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SANDBOX_DIR = Path("data/crm_sandboxes")
_GLOBAL_DB = Path("data/crm.sqlite3")
# 合法 customer_id = 短横线分段 token (CUST-0001 / CUST-A-SBX)。杂散 sqlite 文件
# (.sqlite3 隐藏文件 / None / global / NEW / X 等坏 cid 写入产物) 不匹配, 据之过滤,
# 否则 glob('*.sqlite3').stem 会把它们当幽灵客户漏进 /v1/flywheel/customers。
_VALID_CID = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9._]+)+$")
_lock = threading.Lock()


def _resolve_alias(customer_id: str) -> str:
    """旧 ID → canonical ID (customer_id_aliases 表); 未登记/无表 → 原样。

    BUG-3 归一后磁盘上的历史 context JSON / 外部引用仍可能带旧 ID; 不解析
    会把旧 ID 当新客户建空沙箱, 非规范 ID 经 API 复活。
    """
    cid = str(customer_id or "").strip()
    if not cid or not _GLOBAL_DB.exists():
        return cid
    try:
        conn = sqlite3.connect(str(_GLOBAL_DB))
        try:
            row = conn.execute(
                "SELECT canonical_id FROM customer_id_aliases WHERE old_id=?",
                (cid,)).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return cid
    return row[0] if row and row[0] else cid

_SANDBOX_SCHEMA = """
CREATE TABLE IF NOT EXISTS customers(
  customer_id TEXT PRIMARY KEY, name TEXT, contact_name TEXT, email TEXT,
  country TEXT, updated_at REAL);
CREATE TABLE IF NOT EXISTS rfqs(
  context_id TEXT PRIMARY KEY, customer_id TEXT, material TEXT, surface TEXT,
  quantity INTEGER, tolerance TEXT, state TEXT, created_at REAL, payload TEXT);
CREATE TABLE IF NOT EXISTS quotes(
  context_id TEXT PRIMARY KEY, unit_price REAL, final_price REAL, currency TEXT,
  lead_time_days INTEGER, margin_pct REAL, source TEXT, verification_status TEXT,
  reply_subject TEXT, auto_send INTEGER, created_at REAL);
CREATE TABLE IF NOT EXISTS postmortems(
  id INTEGER PRIMARY KEY AUTOINCREMENT, context_id TEXT, outcome TEXT,
  actual_cost REAL, note TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS pricing_model(
  customer_id TEXT PRIMARY KEY, material_coeff REAL DEFAULT 0.0,
  surface_coeff REAL DEFAULT 0.0, tolerance_coeff REAL DEFAULT 0.0,
  quantity_discount REAL DEFAULT 0.0, avg_deviation REAL DEFAULT 0.0,
  win_rate REAL DEFAULT 0.5, total_quotes INTEGER DEFAULT 0,
  total_won INTEGER DEFAULT 0, total_lost INTEGER DEFAULT 0,
  updated_at REAL);
CREATE TABLE IF NOT EXISTS knowledge_base(
  id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id TEXT, category TEXT,
  keyword TEXT, insight TEXT, severity TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS followups(
  id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id TEXT, action TEXT,
  trigger TEXT, result TEXT, created_at REAL);
"""


class CustomerSandbox:
    """每个客户独立沙箱, 数据完全隔离。"""

    def __init__(self, customer_id: str):
        self.customer_id = _resolve_alias(customer_id)
        self.db_path = SANDBOX_DIR / f"{self.customer_id}.sqlite3"
        self._local_conn: Optional[sqlite3.Connection] = None
        self._ensure_sandbox()

    def _ensure_sandbox(self) -> None:
        """创建沙箱数据库 (含全部表)。"""
        SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
        with _lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.executescript(_SANDBOX_SCHEMA)
            conn.commit()
            conn.close()

    @property
    def conn(self) -> sqlite3.Connection:
        """获取本地连接 (线程安全)。"""
        if self._local_conn is None:
            self._local_conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        return self._local_conn

    def upsert_customer(self, customer: Dict[str, Any]) -> str:
        """写入客户信息到沙箱。"""
        cid = customer.get("customer_id") or self.customer_id
        self.conn.execute(
            "INSERT INTO customers(customer_id,name,contact_name,email,country,updated_at) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(customer_id) DO UPDATE SET "
            "name=excluded.name, contact_name=excluded.contact_name, email=excluded.email,"
            "country=excluded.country, updated_at=excluded.updated_at",
            (cid, customer.get("name"), customer.get("contact_name"),
             customer.get("email"), customer.get("country"), __import__("time").time()))
        self.conn.commit()
        return cid

    def write_quote(self, context_id: str, quote_data: Dict[str, Any]) -> None:
        """写入报价到沙箱。"""
        self.conn.execute(
            "INSERT OR REPLACE INTO quotes(context_id,unit_price,final_price,currency,"
            "lead_time_days,margin_pct,source,verification_status,reply_subject,"
            "auto_send,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (context_id, quote_data.get("unit_price"), quote_data.get("final_price"),
             quote_data.get("currency", "CNY"), quote_data.get("lead_time_days"),
             quote_data.get("margin_pct"), quote_data.get("_source"),
             quote_data.get("verification_status"), quote_data.get("reply_subject"),
             1 if quote_data.get("auto_send") else 0, __import__("time").time()))
        self.conn.commit()

    def write_rfq(self, context_id: str, rfq: Dict[str, Any]) -> None:
        """写入 RFQ 到沙箱。"""
        self.conn.execute(
            "INSERT OR REPLACE INTO rfqs(context_id,customer_id,material,surface,"
            "quantity,tolerance,state,created_at,payload) VALUES(?,?,?,?,?,?,?,?,?)",
            (context_id, self.customer_id, rfq.get("material"), rfq.get("surface"),
             rfq.get("quantity"), rfq.get("tolerance_grade"), rfq.get("state", "NEW"),
             __import__("time").time(), __import__("json").dumps(rfq, ensure_ascii=False, default=str)))
        self.conn.commit()

    def record_postmortem(self, context_id: str, outcome: str,
                           actual_cost: Optional[float] = None, note: str = "") -> None:
        """记录复盘到沙箱。"""
        self.conn.execute(
            "INSERT INTO postmortems(context_id,outcome,actual_cost,note,created_at) VALUES(?,?,?,?,?)",
            (context_id, outcome, actual_cost, note, __import__("time").time()))
        self.conn.commit()

    def get_history(self, limit: int = 20) -> Dict[str, Any]:
        """获取客户历史 (沙箱内)。"""
        quotes = [dict(zip(
            ["context_id", "unit_price", "final_price", "margin_pct",
             "verification_status", "created_at"], r))
            for r in self.conn.execute(
                "SELECT q.context_id,q.unit_price,q.final_price,q.margin_pct,"
                "q.verification_status,q.created_at FROM quotes q "
                "JOIN rfqs r ON r.context_id=q.context_id "
                "WHERE r.customer_id=? ORDER BY q.created_at DESC LIMIT ?",
                (self.customer_id, limit)).fetchall()]
        pms = [dict(zip(
            ["context_id", "outcome", "actual_cost", "note", "created_at"], r))
            for r in self.conn.execute(
                "SELECT context_id,outcome,actual_cost,note,created_at FROM postmortems "
                "WHERE context_id IN (SELECT context_id FROM quotes) "
                "ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()]
        return {"quotes": quotes, "postmortems": pms, "n": len(quotes)}

    def real_counts(self) -> Dict[str, int]:
        """从实表统计本客户报价/成交/丢单数 (pricing_model 计数是 stale 缓存)。

        生产链路只写 quotes/rfqs/postmortems, 从不回写 pricing_model 计数器
        (write_quote 无计数逻辑), 节点存量 model 计数全 0 而 quotes 表 3110 行 —
        总览页读模型计数即"历史报价 0"。实表才是真相。
        outcome 大小写不敏感 (历史 'Won' 写法); 无对应 rfq 的孤儿复盘不计。
        """
        try:
            quotes = self.conn.execute(
                "SELECT COUNT(*) FROM quotes q JOIN rfqs r "
                "ON r.context_id=q.context_id WHERE r.customer_id=?",
                (self.customer_id,)).fetchone()[0]
            won = self.conn.execute(
                "SELECT COUNT(*) FROM postmortems WHERE LOWER(TRIM(outcome))='won' "
                "AND context_id IN (SELECT context_id FROM rfqs WHERE customer_id=?)",
                (self.customer_id,)).fetchone()[0]
            lost = self.conn.execute(
                "SELECT COUNT(*) FROM postmortems WHERE LOWER(TRIM(outcome))='lost' "
                "AND context_id IN (SELECT context_id FROM rfqs WHERE customer_id=?)",
                (self.customer_id,)).fetchone()[0]
        except sqlite3.Error:
            return {"quotes": 0, "won": 0, "lost": 0}
        return {"quotes": int(quotes or 0), "won": int(won or 0), "lost": int(lost or 0)}

    def get_pricing_model(self) -> Dict[str, Any]:
        """获取客户专属定价模型。"""
        row = self.conn.execute(
            "SELECT * FROM pricing_model WHERE customer_id=?",
            (self.customer_id,)).fetchone()
        if row:
            cols = ["customer_id", "material_coeff", "surface_coeff", "tolerance_coeff",
                    "quantity_discount", "avg_deviation", "win_rate", "total_quotes",
                    "total_won", "total_lost", "updated_at"]
            return dict(zip(cols, row))
        return {"customer_id": self.customer_id, "material_coeff": 0.0,
                "surface_coeff": 0.0, "tolerance_coeff": 0.0,
                "quantity_discount": 0.0, "avg_deviation": 0.0,
                "win_rate": 0.5, "total_quotes": 0, "total_won": 0,
                "total_lost": 0}

    def update_pricing_model(self, material_coeff: float, surface_coeff: float,
                              tolerance_coeff: float, deviation: float,
                              won: bool) -> Dict[str, Any]:
        """更新定价模型 — 飞轮核心。"""
        existing = self.get_pricing_model()
        n = existing["total_quotes"] + 1

        # 指数移动平均更新系数
        alpha = 0.3 if n < 5 else 0.1  # 前期学习快, 后期稳定
        material_coeff = existing["material_coeff"] * (1 - alpha) + material_coeff * alpha
        surface_coeff = existing["surface_coeff"] * (1 - alpha) + surface_coeff * alpha
        tolerance_coeff = existing["tolerance_coeff"] * (1 - alpha) + tolerance_coeff * alpha

        # 更新平均偏差
        avg_dev = (existing["avg_deviation"] * existing["total_quotes"] + deviation) / n
        win_rate = (existing["total_won"] + (1 if won else 0)) / n

        self.conn.execute(
            "INSERT OR REPLACE INTO pricing_model(customer_id,material_coeff,"
            "surface_coeff,tolerance_coeff,quantity_discount,avg_deviation,"
            "win_rate,total_quotes,total_won,total_lost,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (self.customer_id, round(material_coeff, 4), round(surface_coeff, 4),
             round(tolerance_coeff, 4), existing["quantity_discount"], round(avg_dev, 4),
             round(win_rate, 4), n, existing["total_won"] + (1 if won else 0),
             existing["total_lost"] + (0 if won else 1), __import__("time").time()))
        self.conn.commit()
        return self.get_pricing_model()

    def add_knowledge(self, category: str, keyword: str, insight: str,
                       severity: str = "info") -> None:
        """添加知识条目到沙箱知识库。"""
        self.conn.execute(
            "INSERT INTO knowledge_base(customer_id,category,keyword,insight,severity,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (self.customer_id, category, keyword, insight, severity, __import__("time").time()))
        self.conn.commit()

    def add_followup(self, action: str, trigger: str, result: str) -> None:
        """记录跟进动作。"""
        self.conn.execute(
            "INSERT INTO followups(customer_id,action,trigger,result,created_at) "
            "VALUES(?,?,?,?,?)",
            (self.customer_id, action, trigger, result, __import__("time").time()))
        self.conn.commit()

    def get_knowledge_base(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取客户专属知识库。"""
        rows = self.conn.execute(
            "SELECT category,keyword,insight,severity,created_at FROM knowledge_base "
            "WHERE customer_id=? ORDER BY created_at DESC LIMIT ?",
            (self.customer_id, limit)).fetchall()
        return [dict(zip(["category", "keyword", "insight", "severity", "created_at"], r)) for r in rows]

    def cross_reference_aggregate(self, query: str, params: Tuple = ()) -> Optional[Tuple]:
        """跨沙箱只读聚合查询 (不暴露个体数据)。

        仅用于统计: 如'同材料平均报价', 不返回其他客户个体数据。
        """
        try:
            with sqlite3.connect(str(_GLOBAL_DB)) as conn:
                return conn.execute(query, params).fetchone()
        except Exception:
            return None

    def export_sandbox(self) -> bytes:
        """导出沙箱数据为 zip (仅本客户)。"""
        import tempfile, zipfile, io
        tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        tmp.close()
        shutil.make_archive(tmp.name.replace(".zip", ""), "zip", str(self.db_path.parent), f"{self.customer_id}.sqlite3")
        with open(tmp.name, "rb") as f:
            data = f.read()
        os_unlink(tmp.name)
        return data

    def close(self) -> None:
        """关闭连接。"""
        if self._local_conn:
            self._local_conn.close()
            self._local_conn = None


import os

def get_sandbox(customer_id: str) -> CustomerSandbox:
    """获取或创建客户沙箱 (单例)。"""
    return CustomerSandbox(customer_id)


def init_all_sandboxes() -> List[str]:
    """初始化所有已有客户的沙箱。"""
    if not _GLOBAL_DB.exists():
        return []
    conn = sqlite3.connect(str(_GLOBAL_DB))
    customer_ids = [r[0] for r in conn.execute(
        "SELECT DISTINCT customer_id FROM customers").fetchall()]
    conn.close()
    for cid in customer_ids:
        CustomerSandbox(cid)
    return customer_ids


def list_all_sandboxes() -> List[Dict[str, Any]]:
    """列出所有沙箱及基本信息。"""
    if not SANDBOX_DIR.exists():
        return []
    results = []
    for db_file in sorted(SANDBOX_DIR.glob("*.sqlite3")):
        cid = db_file.stem
        if not _VALID_CID.match(cid):
            continue
        try:
            sandbox = CustomerSandbox(cid)
            model = sandbox.get_pricing_model()
            counts = sandbox.real_counts()
            sandbox.close()
            results.append({
                "customer_id": cid, **model,
                # 计数器一律以实表为准 (模型行是 stale 缓存); quote_count 同源,
                # 不再用 get_history(limit=1)["n"] (恒封顶 1)。
                "total_quotes": counts["quotes"],
                "total_won": counts["won"],
                "total_lost": counts["lost"],
                "quote_count": counts["quotes"],
            })
        except Exception:
            results.append({"customer_id": cid, "error": "init_failed"})
    return results
