"""tests/test_node_service_scripts.py — 节点驻留层脚本架构口径锁.

背景 (2026-09-22 pivot, user 拍板「放弃 30B, 全部接 Omni 30B」):
  Omni :8002 与 30B :8000 同代同宗, 但 GB10 unified-memory 不可共存 —— Omni EngineCore
  实占 73.5GB (配置 0.45 已超计), 30B 任何 util 配方 (0.30/0.22/0.20) 都在 KV cache
  分配期崩溃 (watchdog 22 次重启, 721MB free vs 966MB needed)。故驻留服务从 5 个收缩
  为 4 个: reason30b 除名, serve30b.sh 删除 —— 既断 crash-loop, 也防未来运维误重启
  30B 把 Omni 挤下 unified memory。

契约 (本测试钉死):
  - node_services.sh SERVICES_ALL == "embed qwen06 omni timo searxng livekernel" (6 驻留);
    node_watchdog.sh == "embed qwen06 omni timo livekernel" (5 托管; searxng 非推理命门不托管)
    (2026-09-26 C4: qwen06 :8902 fallback lane 双侧加入)
  - reason30b / serve30b / :8000 零残留; 端口表覆盖 8002/8011/7862/8888/8902
  - serve30b.sh 不存在于 deploy/nvidia/
  - 两脚本 bash -n 语法合法 (节点侧直跑, 无 CI 编译兜底)
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SERVICES = _ROOT / "deploy" / "node_services.sh"
_WATCHDOG = _ROOT / "deploy" / "node_watchdog.sh"
_SERVE30B = _ROOT / "deploy" / "nvidia" / "serve30b.sh"

_EXPECTED = {
    _SERVICES.name: "embed qwen06 omni timo searxng livekernel",
    _WATCHDOG.name: "embed qwen06 omni timo livekernel",
}

# 节点驻留脚本为本地运维资产 (.gitignore deploy/ 不入公开包; 节点执行副本在
# union-deploy/): 公开克隆无此脚本时本文件契约测试整体跳过 — 与
# test_tools_physically_exist / test_batch_quote 语料守卫同模式。
_OPS_SKIP = pytest.mark.skipif(
    not (_SERVICES.exists() and _WATCHDOG.exists()),
    reason="节点驻留脚本 deploy/node_services.sh|node_watchdog.sh 不在本机 "
           "(.gitignore 本地运维资产, 公开克隆/新装机不含)")


def _text(p: Path) -> str:
    assert p.exists(), f"脚本缺失: {p}"
    return p.read_text(encoding="utf-8")


# ---------- 1. 30B 服务除名 ----------

def _code_lines(p: Path) -> str:
    """脚本正文去掉注释行 (头注可合法记述 pivot 历史, 代码行零残留)."""
    lines = [l for l in _text(p).splitlines() if not l.lstrip().startswith("#")]
    return "\n".join(lines)


@_OPS_SKIP
def test_no_reason30b_in_service_scripts() -> None:
    for f in (_SERVICES, _WATCHDOG):
        txt = _code_lines(f)
        assert "reason30b" not in txt, f"{f.name} 代码行残留 reason30b 服务 (30B 弃用 pivot)"
        assert "serve30b" not in txt.lower(), f"{f.name} 代码行残留 serve30b 引用 (30B 弃用 pivot)"
        assert ":8000" not in txt, f"{f.name} 代码行残留 30B 端口 :8000 (30B 弃用 pivot)"


@_OPS_SKIP
def test_services_all_topology() -> None:
    for f in (_SERVICES, _WATCHDOG):
        m = re.search(r'SERVICES_ALL="([^"]+)"', _text(f))
        assert m, f"{f.name} 未定义 SERVICES_ALL"
        assert m.group(1) == _EXPECTED[f.name], (
            f"{f.name} SERVICES_ALL={m.group(1)} 应为 '{_EXPECTED[f.name]}'")


# ---------- 2. 端口表覆盖存活拓扑 ----------

@_OPS_SKIP
def test_port_maps_cover_live_topology() -> None:
    for f in (_SERVICES, _WATCHDOG):
        txt = _text(f)
        for port in ("8011", "8002", "7862", "8888", "8902"):
            assert f") echo {port} ;;" in txt, f"{f.name} 端口表缺 {port}"
        assert ") echo 8000 ;;" not in txt, f"{f.name} 端口表残留 30B :8000"


@_OPS_SKIP
def test_watchdog_summary_counts_five() -> None:
    txt = _text(_WATCHDOG)
    assert "all 5 services UP" in txt, "watchdog 汇总文案应数 5 个托管服务 (C4: qwen06 入列)"
    assert "all 4 services" not in txt, "watchdog 汇总文案残留 4 服务口径"


# ---------- 3. serve30b.sh 删除 ----------

def test_serve30b_launcher_deleted() -> None:
    assert not _SERVE30B.exists(), (
        "serve30b.sh 应随 30B 弃用删除 — 防未来误重启 30B 挤爆 Omni (unified-memory)")


# ---------- 4. 语法 ----------

@_OPS_SKIP
def test_service_scripts_bash_syntax() -> None:
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("无 bash, 跳过 bash -n")
    for f in (_SERVICES, _WATCHDOG):
        p = subprocess.run([bash, "-n", str(f)], capture_output=True, text=True, timeout=30)
        assert p.returncode == 0, f"{f.name} bash 语法错误: {p.stderr}"
