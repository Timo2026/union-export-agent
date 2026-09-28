"""feedback_store.py — 用户反馈存储 (sqlite).

v2.4.0 控制台反馈邮箱后端; v2.5.0 (BUG-3 巡检修复) 加内容签名去重 + 测试源隔离。
纯 sqlite, schema v2:
  id (autoinc) | created_at | type (bug/feature/consult/other)
  | title | body | email | user_agent | source (webui/email/api)
  | status (new/in_progress/closed) | assigned_to | notes
  | hidden (0/1, v2 降噪标记: 测试源/重复多余条目) | sig (内容签名 sha256)

防滥用:
  - honeypot 字段 (前端不可见) — bot 填了就拒
  - 速率限制: 同 IP 每分钟 ≤ 5 条
  - 内容签名 (source,title,body) 去重: 同签名再提交回显已存在行, 不插新行
  - source 归一化 (lower + 非字母数字转 _); testclient/skill_dispatcher 前缀
    视为测试源 → 入库即 hidden=1, 不计 unread, 不进 list (冒烟灌入不再淹没真实反馈)
  - 存量一次性降噪 quarantine_noise(): 只标记 hidden=1 不删行, 可逆

v1→v2 迁移: init_db 检测缺失列 ALTER ADD COLUMN (幂等), 存量行 sig 由
quarantine_noise 回填。
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = _ROOT / "data" / "feedback.sqlite3"
_LOCK = Lock()

_VALID_TYPES = {"bug", "feature", "consult", "other"}
_VALID_STATUSES = {"new", "in_progress", "closed"}

# 简易速率限制: 同 IP 时间窗口
_RATE_WINDOW_S = 60
_RATE_MAX = 5
_ip_buckets: Dict[str, List[float]] = {}

_SOURCE_NORM = re.compile(r"[^a-z0-9]+")
# 测试/冒烟来源标记 (归一化后的前缀): testclient / skill-dispatcher/3.0 → skill_dispatcher_3_0
_TEST_SOURCE_MARKERS = ("testclient", "skill_dispatcher")


def _norm_source(source: str) -> str:
    s = _SOURCE_NORM.sub("_", (source or "").strip().lower()).strip("_")
    return s or "webui"


def _is_test_source(norm_source: str) -> bool:
    return any(norm_source == m or norm_source.startswith(m)
               for m in _TEST_SOURCE_MARKERS)


def _signature(source: str, title: str, body: str) -> str:
    raw = f"{source}\n{(title or '').strip()}\n{(body or '').strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(_DB_PATH), timeout=5)
    c.row_factory = sqlite3.Row
    return c


def _migrate_v2(conn: sqlite3.Connection) -> None:
    """v1→v2 幂等补列: hidden / sig (老库无这两列)。"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(feedback)")}
    if "hidden" not in cols:
        conn.execute("ALTER TABLE feedback ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0")
    if "sig" not in cols:
        conn.execute("ALTER TABLE feedback ADD COLUMN sig TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_feedback_sig ON feedback(sig)")


def init_db() -> None:
    """幂等建表 (含 v2 迁移)。"""
    with _LOCK:
        c = _conn()
        try:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    email TEXT,
                    user_agent TEXT,
                    source TEXT NOT NULL DEFAULT 'webui',
                    status TEXT NOT NULL DEFAULT 'new',
                    assigned_to TEXT,
                    notes TEXT,
                    hidden INTEGER NOT NULL DEFAULT 0,
                    sig TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_feedback_status  ON feedback(status);
            """)
            _migrate_v2(c)
            c.commit()
        finally:
            c.close()


def _check_rate(ip: str) -> bool:
    """滑动窗口限流: 60s 内最多 5 次。"""
    now = time.time()
    bucket = _ip_buckets.setdefault(ip, [])
    bucket[:] = [t for t in bucket if now - t < _RATE_WINDOW_S]
    if len(bucket) >= _RATE_MAX:
        return False
    bucket.append(now)
    return True


def submit(payload: Dict[str, Any], *, ip: str = "unknown",
           user_agent: str = "") -> Dict[str, Any]:
    """提交一条反馈。返回 {ok, id} 或 {ok:false, error} 或 {ok, duplicate, id}。

    payload 字段:
      type, title, body (必填), email (可选), honeypot (必须为空)
    同内容签名重复提交: 不插新行, 回显已存在行 id/created_at (duplicate=True)。
    """
    init_db()
    honeypot = (payload.get("honeypot") or "").strip()
    if honeypot:
        return {"ok": False, "error": "honeypot triggered (bot?)"}
    if not _check_rate(ip):
        return {"ok": False, "error": f"rate limited ({_RATE_MAX}/{_RATE_WINDOW_S}s)"}

    typ = (payload.get("type") or "").strip().lower()
    title = (payload.get("title") or "").strip()
    body = (payload.get("body") or "").strip()
    email = (payload.get("email") or "").strip() or None

    if typ not in _VALID_TYPES:
        return {"ok": False, "error": f"type 必须 ∈ {_VALID_TYPES}"}
    if len(title) < 4:
        return {"ok": False, "error": "title 至少 4 字符"}
    if len(body) < 10:
        return {"ok": False, "error": "body 至少 10 字符"}
    if email and ("@" not in email or "." not in email.split("@")[-1]):
        return {"ok": False, "error": "email 格式无效"}

    source = _norm_source(payload.get("source"))
    hidden = 1 if _is_test_source(source) else 0
    sig = _signature(source, title, body)
    created = time.strftime("%Y-%m-%d %H:%M:%S")

    with _LOCK:
        c = _conn()
        try:
            if not hidden:
                dup = c.execute(
                    "SELECT id,created_at FROM feedback WHERE sig=? AND hidden=0",
                    (sig,)).fetchone()
                if dup:
                    return {"ok": True, "duplicate": True,
                            "id": dup["id"], "created_at": dup["created_at"]}
            cur = c.execute(
                "INSERT INTO feedback(created_at,type,title,body,email,user_agent,"
                "source,hidden,sig) VALUES(?,?,?,?,?,?,?,?,?)",
                (created, typ, title, body, email, user_agent[:200], source,
                 hidden, sig))
            new_id = cur.lastrowid
            c.commit()
        finally:
            c.close()
    return {"ok": True, "id": new_id, "created_at": created}


def list_recent(limit: int = 20, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """最近反馈 (倒序; 不含 hidden 降噪行)。"""
    init_db()
    with _LOCK:
        c = _conn()
        try:
            if status and status in _VALID_STATUSES:
                rows = c.execute(
                    "SELECT id,created_at,type,title,body,email,user_agent,status,source "
                    "FROM feedback WHERE status=? AND hidden=0 ORDER BY id DESC LIMIT ?",
                    (status, int(limit))).fetchall()
            else:
                rows = c.execute(
                    "SELECT id,created_at,type,title,body,email,user_agent,status,source "
                    "FROM feedback WHERE hidden=0 ORDER BY id DESC LIMIT ?",
                    (int(limit),)).fetchall()
        finally:
            c.close()
    return [dict(r) for r in rows]


def count_unread() -> int:
    """待办未读数 (status='new' 且非 hidden 降噪行)。"""
    init_db()
    with _LOCK:
        c = _conn()
        try:
            row = c.execute(
                "SELECT COUNT(*) AS n FROM feedback WHERE status='new' AND hidden=0"
            ).fetchone()
        finally:
            c.close()
    return int(row["n"] if row else 0)


def quarantine_noise() -> Dict[str, int]:
    """一次性降噪存量 (BUG-3): 测试源 + 内容签名重复多余条目标 hidden=1。

    只标记不删行 (可逆); 同签名保留 id 最小 (最早) 的一条; 顺便回填 sig 供
    后续 submit 去重。返回 {marked_test, marked_duplicate}。
    """
    init_db()
    marked_test = 0
    marked_dup = 0
    with _LOCK:
        c = _conn()
        try:
            rows = c.execute(
                "SELECT id,source,title,body,hidden,sig FROM feedback ORDER BY id"
            ).fetchall()
            seen: set = set()
            for r in rows:
                norm = _norm_source(r["source"])
                sig = _signature(norm, r["title"], r["body"])
                updates = []
                if not r["sig"]:
                    updates.append(("sig", sig))
                if _is_test_source(norm):
                    if not r["hidden"]:
                        updates.append(("hidden", 1))
                        marked_test += 1
                elif r["hidden"]:
                    pass  # 已降噪行不占签名
                elif sig in seen:
                    updates.append(("hidden", 1))
                    marked_dup += 1
                else:
                    seen.add(sig)
                if updates:
                    setters = ", ".join(f"{k}=?" for k, _ in updates)
                    c.execute(f"UPDATE feedback SET {setters} WHERE id=?",
                              [v for _, v in updates] + [r["id"]])
            c.commit()
        finally:
            c.close()
    return {"marked_test": marked_test, "marked_duplicate": marked_dup}


if __name__ == "__main__":
    init_db()
    print(json.dumps(list_recent(5), ensure_ascii=False, indent=2))
