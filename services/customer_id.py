"""customer_id.py — 客户 ID 统一派生 (巡检报告 BUG-3 归一基座).

规则 (2026-09-26 拍板):
  - 派生种子: email 优先 → name 兜底 → "anon"; 归一后 md5[:8] 大写, 前缀 CUST-
  - email 归一: 剥 "Name <addr>" 包裹 / 去首尾空白 / 小写
  - 规范 ID = CUST-<8位大写hex>; 演示/测试/脚本显式传的自定义 ID 原样保留,
    但登记进别名表的旧 ID 在 upsert 时合并回规范 ID (见 CRMMemory.register_alias)
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Optional

CANONICAL_PREFIX = "CUST-"
CANONICAL_RE = re.compile(r"^CUST-[0-9A-F]{8}$")

_ADDR_RE = re.compile(r"<([^<>]+)>")

# 测试/探针 synthetic 身份 (无业务数据的空壳): 迁移时只清理零引用者, 有历史的
# 一律按 email/name 归一保留, 不删数据。
_JUNK_EXACT = {"", "none", "null", "global", "new", "x", "y", "z", "t", "t1", "anon"}
_JUNK_PREFIXES = (
    "probe-", "probe_", "formal-e", "sop-test", "sop1@", "geofix",
    "harness@", "http@", "final@", "cust-new", "cust-t1",
)


def normalize_email(raw: Optional[str]) -> str:
    """邮件地址归一: 'Name <addr>' → addr; 去空白/引号; 小写。"""
    if not raw:
        return ""
    s = str(raw).strip()
    m = _ADDR_RE.search(s)
    if m:
        s = m.group(1)
    return s.strip().strip('"').strip().lower()


def derive_customer_id(customer: Dict[str, Any]) -> str:
    """email 优先 → name 兜底 → 'anon'; md5[:8] 大写, CUST- 前缀。"""
    seed = (normalize_email(customer.get("email"))
            or str(customer.get("name") or "").strip().lower()
            or "anon")
    return CANONICAL_PREFIX + hashlib.md5(seed.encode("utf-8")).hexdigest()[:8].upper()


def is_canonical_customer_id(cid: Optional[str]) -> bool:
    return bool(cid) and bool(CANONICAL_RE.match(str(cid)))


def is_junk_customer_id(cid: Optional[str]) -> bool:
    s = str(cid or "").strip().lower()
    if s in _JUNK_EXACT:
        return True
    return s.startswith(_JUNK_PREFIXES)
