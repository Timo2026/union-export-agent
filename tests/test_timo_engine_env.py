"""test_timo_engine_env.py — CNC_BRAIN_SRC / CNC_BRAIN_PY 环境变量覆盖 + 平台缺省三规则.

DGX Spark 节点部署时 settings.yaml 里的 Windows 引擎路径不存在, 用环境变量
把离线内核指向节点上的引擎 venv (或 OCC 环境) — 免改配置文件.

P0-B (PRD-DELIVERY §2) 平台自适应三规则 (adapters.timo_adapter.resolve_engine_paths):
  1. env CNC_BRAIN_SRC / CNC_BRAIN_PY 显式覆盖 (最高优先);
  2. 无 env 且配置路径本机存在 → 原样使用;
  3. 无 env 且配置路径缺失 → 平台缺省: Windows 走 home 派生路径, POSIX 走
     /workspace/_timo_engine/... (公开包脱敏, 不写死作者本机绝对路径);
  4. 仍不可达 → 显式 raise (kernel-absent), 不静默不冒充.
"""
from __future__ import annotations

import os

import pytest

from adapters.timo_adapter import (
    PLATFORM_DEFAULT_ENGINE_PY,
    PLATFORM_DEFAULT_ENGINE_SRC,
    WINDOWS_ENGINE_DIR,
    TimoAdapter,
)

#  synthetic Windows 配置 (脱敏: 不含作者用户名; 本机不存在 → 触发平台缺省)
_CFG = {"timo": {"engine_src": "/win/engine",
                 "engine_python": "/win/engine/.venv/python.exe"}}
_WIN_CFG = {"timo": {"engine_src": "C:/Users/uea/_timo_engine/Timo_CNC-AI-Brain-v12.0-Fusion",
                     "engine_python": "C:/Users/uea/_timo_engine/Timo_CNC-AI-Brain-v12.0-Fusion/.venv/Scripts/python.exe"}}


def test_engine_paths_platform_default_when_config_absent(monkeypatch):
    """无 env 且配置路径本机不存在 → 平台缺省 (规则 3, 两平台)."""
    monkeypatch.delenv("CNC_BRAIN_SRC", raising=False)
    monkeypatch.delenv("CNC_BRAIN_PY", raising=False)
    t = TimoAdapter(_CFG)
    if os.name == "posix":
        assert t.engine_src == PLATFORM_DEFAULT_ENGINE_SRC
        assert t.engine_python == PLATFORM_DEFAULT_ENGINE_PY
    else:
        assert t.engine_src == str(WINDOWS_ENGINE_DIR)
        assert t.engine_python == str(WINDOWS_ENGINE_DIR / ".venv" / "Scripts" / "python.exe")


def test_engine_paths_env_override(monkeypatch):
    monkeypatch.setenv("CNC_BRAIN_SRC", "/opt/cnc-ai-brain")
    monkeypatch.setenv("CNC_BRAIN_PY", "/opt/cnc-ai-brain/.venv/bin/python")
    t = TimoAdapter(_CFG)
    assert t.engine_src == "/opt/cnc-ai-brain"
    assert t.engine_python == "/opt/cnc-ai-brain/.venv/bin/python"


def test_engine_paths_partial_env_override(monkeypatch):
    """只设 CNC_BRAIN_PY (OCC 场景: 引擎源码已在 PYTHONPATH) 时 src 走平台缺省."""
    monkeypatch.delenv("CNC_BRAIN_SRC", raising=False)
    monkeypatch.setenv("CNC_BRAIN_PY", "/home/Developer/miniconda3/envs/occ/bin/python")
    t = TimoAdapter(_CFG)
    if os.name == "posix":
        assert t.engine_src == PLATFORM_DEFAULT_ENGINE_SRC
    else:
        assert t.engine_src == str(WINDOWS_ENGINE_DIR)
    assert t.engine_python == "/home/Developer/miniconda3/envs/occ/bin/python"


# ---- P0-B 新增: 平台缺省三规则 ----

def test_existing_config_path_preserved(monkeypatch):
    """规则 2 优先于规则 3: 配置路径本机存在 → 原样使用 (平台无关, 无需 patch).

    必须先 delenv: 规则 1 (env 覆盖) 优先级最高 — 节点部署态 livekernel.env
    常驻 CNC_BRAIN_SRC/PY, 不清 env 本用例会被 env 值击沉 (非 hermetic)。
    """
    monkeypatch.delenv("CNC_BRAIN_SRC", raising=False)
    monkeypatch.delenv("CNC_BRAIN_PY", raising=False)
    here = os.path.dirname(os.path.abspath(__file__))
    cfg = {"timo": {"engine_src": here, "engine_python": ""}}
    t = TimoAdapter(cfg)
    assert t.engine_src == here


def test_posix_platform_default_when_config_absent(monkeypatch):
    """POSIX + 配置为不存在的 Windows 路径 → /workspace 平台缺省, 不含 Windows 字面量."""
    monkeypatch.delenv("CNC_BRAIN_SRC", raising=False)
    monkeypatch.delenv("CNC_BRAIN_PY", raising=False)
    monkeypatch.setattr("adapters.timo_adapter.os.name", "posix")
    t = TimoAdapter(_WIN_CFG)
    assert t.engine_src == PLATFORM_DEFAULT_ENGINE_SRC
    assert t.engine_python == PLATFORM_DEFAULT_ENGINE_PY
    for p in (t.engine_src, t.engine_python):
        assert "\\" not in p and "C:" not in p


def test_env_override_beats_posix_platform_default(monkeypatch):
    """env 显式覆盖优先于平台缺省 (规则 1 最高)."""
    monkeypatch.setenv("CNC_BRAIN_SRC", "/opt/cnc-ai-brain")
    monkeypatch.setenv("CNC_BRAIN_PY", "/opt/cnc-ai-brain/.venv/bin/python")
    monkeypatch.setattr("adapters.timo_adapter.os.name", "posix")
    t = TimoAdapter(_WIN_CFG)
    assert t.engine_src == "/opt/cnc-ai-brain"
    assert t.engine_python == "/opt/cnc-ai-brain/.venv/bin/python"


def test_posix_unreachable_engine_raises_explicitly(monkeypatch):
    """平台缺省也不可达 → _offline 显式 RuntimeError (kernel-absent), 不静默成功."""
    monkeypatch.delenv("CNC_BRAIN_SRC", raising=False)
    monkeypatch.delenv("CNC_BRAIN_PY", raising=False)
    monkeypatch.setattr("adapters.timo_adapter.os.name", "posix")
    t = TimoAdapter(_WIN_CFG)
    assert t.engine_src == PLATFORM_DEFAULT_ENGINE_SRC
    with pytest.raises(RuntimeError, match="engine_src not found"):
        t._offline("conflict_check", {"material": "304", "surface": "无"})
