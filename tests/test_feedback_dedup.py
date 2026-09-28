"""BUG-3 巡检修复: feedback 内容签名去重 + 测试源隔离.

背景 (2026-09-25 订单邮箱总览页巡检): 节点 feedback 表 109 条"未读",
其中 76 条 source=skill_dispatcher 的冒烟测试灌入 (同名内容一条重复 38 次),
真实 webui 反馈 33 条被淹没; rate limiter 只按 IP 计, 不拦同内容重复提交。

口径:
  - source 归一化 (lower + 非字母数字转 _) 后, testclient/skill_dispatcher 前缀
    视为测试源 → 入库即 hidden=1, 不计 unread, 不进 list
  - (source,title,body) 内容签名 sha256 去重: 同签名再提交返回已存在行, 不插新行
  - schema v2: hidden 列 (老库 ALTER 迁移, 幂等); 存量 quarantine_noise() 一次性
    标记 (测试源 + 重复多余条目), 只标记不删, 可逆
"""
from __future__ import annotations

import os
import sqlite3

import pytest

from services import feedback_store as fs


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_DB_PATH", tmp_path / "feedback_dedup.sqlite3")
    fs._ip_buckets.clear()
    yield
    try:
        os.remove(fs._DB_PATH)
    except Exception:
        pass


def _payload(**kw):
    base = {"type": "bug", "title": "按钮错位反馈标题", "body": "提交按钮在窄屏下错位重叠"}
    base.update(kw)
    return base


def _raw_rows():
    con = sqlite3.connect(f"file:{fs._DB_PATH}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT id,source,title,body,hidden FROM feedback ORDER BY id").fetchall()
        cols = ["id", "source", "title", "body", "hidden"]
        return [dict(zip(cols, r)) for r in rows]
    finally:
        con.close()


# ---------- 内容签名去重 ----------

def test_duplicate_signature_not_inserted_twice(_isolated_db):
    r1 = fs.submit(_payload(), ip="10.0.0.1")
    assert r1["ok"] is True and r1.get("duplicate") is not True
    r2 = fs.submit(_payload(), ip="10.0.0.2")
    assert r2["ok"] is True
    assert r2.get("duplicate") is True
    assert r2["id"] == r1["id"]            # 回显已存在行, 不插新行
    assert fs.count_unread() == 1


def test_distinct_bodies_both_kept(_isolated_db):
    fs.submit(_payload(body="第一种问题描述内容详情"), ip="10.0.0.1")
    fs.submit(_payload(body="第二种不同的问题描述内容"), ip="10.0.0.2")
    assert fs.count_unread() == 2


# ---------- 测试源隔离 ----------

def test_test_source_hidden_from_unread_and_list(_isolated_db):
    r = fs.submit(_payload(source="skill-dispatcher/3.0"), ip="10.0.0.1")
    assert r["ok"] is True
    assert fs.count_unread() == 0
    assert fs.list_recent(limit=10) == []


def test_testclient_source_hidden(_isolated_db):
    fs.submit(_payload(source="testclient"), ip="10.0.0.1")
    assert fs.count_unread() == 0


def test_source_normalized_on_insert(_isolated_db):
    fs.submit(_payload(source="Skill-Dispatcher/3.0"), ip="10.0.0.1")
    row = _raw_rows()[0]
    assert row["source"] == "skill_dispatcher_3_0"
    assert row["hidden"] == 1


def test_webui_source_visible(_isolated_db):
    fs.submit(_payload(source="webui"), ip="10.0.0.1")
    assert fs.count_unread() == 1
    assert len(fs.list_recent(limit=10)) == 1


# ---------- schema v2 迁移 ----------

def test_hidden_column_added_to_v1_schema(_isolated_db):
    """老库 (无 hidden 列) init_db 后: 补列 + 存量 webui 行仍计未读。"""
    con = sqlite3.connect(str(fs._DB_PATH))
    con.executescript(
        "CREATE TABLE feedback(id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "created_at TEXT NOT NULL,type TEXT NOT NULL,title TEXT NOT NULL,"
        "body TEXT NOT NULL,email TEXT,user_agent TEXT,"
        "source TEXT NOT NULL DEFAULT 'webui',status TEXT NOT NULL DEFAULT 'new',"
        "assigned_to TEXT,notes TEXT);"
        "INSERT INTO feedback(created_at,type,title,body,source) "
        "VALUES('2026-09-25 00:00:00','bug','老库标题足够长','老库描述足够长足够长','webui');")
    con.commit()
    con.close()

    fs.init_db()  # 幂等迁移
    cols = {r[1] for r in sqlite3.connect(str(fs._DB_PATH)).execute(
        "PRAGMA table_info(feedback)")}
    assert "hidden" in cols and "sig" in cols
    assert fs.count_unread() == 1


# ---------- 存量一次性降噪 ----------

def test_quarantine_marks_test_sources_and_dup_extras_hidden(_isolated_db):
    con = sqlite3.connect(str(fs._DB_PATH))
    con.executescript(
        "CREATE TABLE feedback(id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "created_at TEXT NOT NULL,type TEXT NOT NULL,title TEXT NOT NULL,"
        "body TEXT NOT NULL,email TEXT,user_agent TEXT,"
        "source TEXT NOT NULL DEFAULT 'webui',status TEXT NOT NULL DEFAULT 'new',"
        "assigned_to TEXT,notes TEXT);"
        "INSERT INTO feedback(created_at,type,title,body,source) VALUES"
        "('2026-09-25 00:00:01','bug','冒烟标题足够长','skill panel 可搜索过滤','skill-dispatcher/3.0'),"
        "('2026-09-25 00:00:02','bug','冒烟标题足够长','skill panel 可搜索过滤','skill-dispatcher/3.0'),"
        "('2026-09-25 00:00:03','bug','真实反馈标题','真实用户描述内容','webui'),"
        "('2026-09-25 00:00:04','bug','真实反馈标题','真实用户描述内容','webui'),"
        "('2026-09-25 00:00:05','bug','真实反馈标题','真实用户描述内容','webui');")
    con.commit()
    con.close()

    report = fs.quarantine_noise()

    assert report["marked_test"] == 2        # 两条冒烟测试灌入
    assert report["marked_duplicate"] == 2   # 真实反馈保留最早 1 条, 余 2 条降噪
    assert fs.count_unread() == 1            # 只剩真实去重后的 1 条
    assert len(fs.list_recent(limit=10)) == 1
