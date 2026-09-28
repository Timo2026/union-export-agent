"""config.py — 配置加载 (禁止硬编码, 全部从 YAML 读取)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

_ROOT = Path(__file__).resolve().parent.parent


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "需要 PyYAML: 请 `python -m pip install pyyaml`") from e


def load_settings(root: Path | str | None = None) -> Dict[str, Any]:
    root = Path(root) if root else _ROOT
    return _load_yaml(root / "config" / "settings.yaml")


def load_policy(root: Path | str | None = None) -> Dict[str, Any]:
    root = Path(root) if root else _ROOT
    return _load_yaml(root / "config" / "policy.yaml")


def load_commercial(root: Path | str | None = None) -> Dict[str, Any]:
    root = Path(root) if root else _ROOT
    return _load_yaml(root / "config" / "commercial.yaml")


def target_margin_pct(fallback: float = 25.0) -> float:
    """基础目标毛利单源 (E1-d): settings.yaml pricing.target_margin_pct。

    配置缺失/损坏时显式回退 fallback, 不抛断报价链路。
    """
    try:
        s = load_settings()
        return float((s.get("pricing") or {}).get("target_margin_pct", fallback))
    except Exception:
        return fallback
