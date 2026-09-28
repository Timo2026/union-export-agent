"""services.profile — 用户资料/署名 (顶栏展示 + 报价回复落款 + SMTP 署名 单一数据源)。

存储 data/profile.json (本地, 不入库不外发); 读: 默认值合并 + 损坏回退默认 (不炸链);
写: 全量字段落盘 (ensure_ascii=False)。默认值即当前线上硬编码身份 (王磊/销售主管)。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

log = logging.getLogger(__name__)

PROFILE_FILE = Path("data") / "profile.json"

DEFAULT_PROFILE: Dict[str, Any] = {
    "name": "王磊",
    "title": "销售主管",
    "initials": "WL",
    "signature": "",          # 留空 = 落款自动用 name + title 组
}

# name/title/signature 全空时的兜底 (历史硬编码串, 保证草稿永不留白落款)
_FALLBACK_SIGN_OFF = "Union Export Sales Engineering"


def load_profile() -> Dict[str, Any]:
    """读 profile: 文件缺失/损坏 → 默认值 (与 gmail_api._load_settings 同模式)。"""
    p = dict(DEFAULT_PROFILE)
    if not PROFILE_FILE.exists():
        return p
    try:
        s = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
        if isinstance(s, dict):
            p.update({k: v for k, v in s.items() if k in DEFAULT_PROFILE})
    except Exception as e:
        log.warning("[profile] corrupt %s → defaults: %r", PROFILE_FILE, e)
    return p


def save_profile(fields: Dict[str, Any]) -> bool:
    """全量保存 (调用方负责给齐字段; 与现有 load 结果合并后落盘)。"""
    merged = {**DEFAULT_PROFILE, **{k: v for k, v in (fields or {}).items()
                                    if k in DEFAULT_PROFILE}}
    try:
        PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
        PROFILE_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        return True
    except Exception as e:
        log.warning("[profile] save failed: %r", e)
        return False


def sign_off(profile: Dict[str, Any] | None) -> str:
    """组邮件落款: signature 非空 → 原样; 否则 name + title; 全空 → 兜底串。"""
    p = profile or {}
    sig = str(p.get("signature") or "").strip()
    if sig:
        return sig
    name = str(p.get("name") or "").strip()
    title = str(p.get("title") or "").strip()
    parts = [x for x in (name, title) if x]
    return "\n".join(parts) if parts else _FALLBACK_SIGN_OFF
