"""test_demo_out_paths.py — P0-B.3 演示产物目录平台自适应.

scripts/run_flywheel_demo.py + scripts/run_golden_core.py 原硬编
C:\\Users\\<user>\\Documents\\demo\\... 绝对路径: 在 Linux 上被当相对路径,
节点仓库内长出字面 C:\\Users\\... 幽灵目录 (巡检报告根因 2).

三规则 (与 resolve_engine_paths 同构), 经纯函数 _resolve_demo_out 显式注入:
  1. env UEA_DEMO_OUT 显式覆盖 (最高优先);
  2. Windows → 原 Documents/demo 路径 (本地产物位置不变);
  3. POSIX → 仓库内 data/demo_out/ (无绝对路径, 无幽灵目录).

注: 不在测试里 monkeypatch os.name — Windows 上 pathlib 按 os.name 选风味,
全局 patch 成 posix 会让后续 Path() 实例化 PosixPath 直接 NotImplementedError.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.run_flywheel_demo import _resolve_demo_out as flywheel_resolve
from scripts.run_flywheel_demo import demo_out_dir as flywheel_demo_out
from scripts.run_golden_core import _resolve_demo_out as golden_resolve
from scripts.run_golden_core import demo_out_dir as golden_demo_out

_ROOT = Path(__file__).resolve().parent.parent
_SUB = "union-core-scenario"
_RESOLVERS = (flywheel_resolve, golden_resolve)


@pytest.mark.parametrize("resolve", _RESOLVERS)
def test_env_override_wins(resolve):
    """规则 1: env UEA_DEMO_OUT 显式覆盖, 压过平台缺省."""
    assert resolve(_SUB, is_nt=True, env_base="/tmp/uea-demo") == Path("/tmp/uea-demo") / _SUB
    assert resolve(_SUB, is_nt=False, env_base="/tmp/uea-demo") == Path("/tmp/uea-demo") / _SUB


@pytest.mark.parametrize("resolve", _RESOLVERS)
def test_windows_default_unchanged(resolve):
    """规则 2: Windows → 原 Documents/demo 路径 (home 派生, 本地产物位置不动)."""
    assert resolve(_SUB, is_nt=True, env_base=None) == Path.home() / "Documents" / "demo" / _SUB


@pytest.mark.parametrize("resolve", _RESOLVERS)
def test_posix_default_repo_relative(resolve):
    """规则 3: POSIX → 仓库内相对路径 (根治 Linux 幽灵目录)."""
    assert resolve(_SUB, is_nt=False, env_base=None) == _ROOT / "data" / "demo_out" / _SUB


@pytest.mark.parametrize("fn", (flywheel_demo_out, golden_demo_out))
def test_wrapper_reads_env(monkeypatch, fn):
    """壳函数 demo_out_dir 透传 env 覆盖 (不 patch 平台, 只 patch env)."""
    monkeypatch.setenv("UEA_DEMO_OUT", "/tmp/uea-demo-wrap")
    assert fn(_SUB) == Path("/tmp/uea-demo-wrap") / _SUB


@pytest.mark.parametrize("fn", (flywheel_demo_out, golden_demo_out))
def test_wrapper_native_platform(fn):
    """壳函数在本机平台的缺省行为: nt → Documents/demo (home 派生); posix → 仓库内."""
    p = fn(_SUB)
    if os.name == "nt":
        assert p == Path.home() / "Documents" / "demo" / _SUB
    else:
        assert p == _ROOT / "data" / "demo_out" / _SUB
