"""tests/test_export_demo_selfcheck.py — export_demo.py deny-list 对抗测试 (TDD).

2026-09-27 事故 (交付前最终完整性 sweep 发现):
  tests/test_node_bootstrap_notebook.py 曾把节点公网 IP / SSH 密码各拆成两截
  字符串拼接 (形如 "A" + "B") 入库 — 注释自辩"规避 export_demo.py deny-list
  误判", 实际效果是三重自检的正则永远拼不完整串, 自检全绿放行, 真值随
  HEAD / github-package / 上传 zip 三处出厂 (无 remote 未外泄)。
  本文件自身 docstring 也因此只准描述形状, 不准复述真值 (守卫会折叠扫描)。

本文件锁死的契约:
  1. 扫描前必须折叠引号拼接 ("..." + "...") — 拆写逃逸必须失效;
  2. 折叠后命中 deny-list (token / 公网 IP) 一律判泄漏, 不自动放过;
  3. loopback / RFC5737 / 私网段仍放行 (加固不引入误报回归);
  4. 入库测试源码折叠后不得含 data/_export_secrets.txt 任一枚记
     (公开克隆无该文件 → skip; 该文件 gitignore, 不含真值);
  5. 泄漏修复后的 test_node_bootstrap_notebook.py 只准经 env 读真值,
     源码不得残留任何节点坐标字面量赋值;
  6. RFC 5737 三段文档段 (192.0.2/198.51.100/203.0.113) 一律豁免 —
     加固不得把文档示例误报成公网 IP; 持节点坐标/邮箱身份的本地运维与
     取证文件必须硬排除出导出面 (EXCLUDE_FILES)。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "export_demo.py"
_spec = importlib.util.spec_from_file_location("export_demo_under_test", _SCRIPT)
ed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ed)

# 合成形状 (不含任何真值): 文档段 198.51.100.0/24 + 假 token
_SPLIT_IP = 'ip = "198.51.100" + ".7"'
_SPLIT_TOKEN = 'tok = "tok" + "en123"'


def test_collapse_joins_split_string_literals():
    joined = ed._collapse_concat(f"{_SPLIT_IP}; {_SPLIT_TOKEN}")
    assert "198.51.100.7" in joined
    assert "token123" in joined


def test_collapsed_split_ip_is_visible_to_ip_regex():
    text = ed._collapse_concat(_SPLIT_IP)
    assert [m.group(0) for m in ed._IP_RE.finditer(text)] == ["198.51.100.7"]


def test_ip_is_public_flags_joined_public_ip():
    # 公网 IP 由八位组算术组装: 本文件随 tests/ 出厂, export 自检的 IP 正则
    # 会扫到任何连续点分串 — 合成字面量即误伤, 算术组装只让被测函数看到。
    pub = ".".join(str(o) for o in (45, 60, 12, 34))
    text = ed._collapse_concat(f'ep = "{pub}"')
    hits = [m.group(0) for m in ed._IP_RE.finditer(text)
            if ed._ip_is_public(*(int(g) for g in m.groups()))]
    assert hits == [pub], hits


def test_loopback_rfc5737_private_still_exempt():
    for ok in ("127.0.0.1", "10.0.0.8", "192.168.1.5", "172.16.0.9",
               "172.31.255.254", "0.0.0.0",
               "192.0.2.1", "192.0.2.255",           # RFC 5737 TEST-NET-1
               "198.51.100.7", "198.51.100.255",     # RFC 5737 TEST-NET-2
               "203.0.113.9", "203.0.113.255"):      # RFC 5737 TEST-NET-3
        a, b, c, d = (int(x) for x in ok.split("."))
        assert ed._ip_is_public(a, b, c, d) is False, ok


def test_local_ops_and_evidence_files_excluded_from_export():
    """契约: 持节点坐标/邮箱身份的本地运维与取证文件必须硬排除出导出面
    (即便 untracked 不入 HEAD, 也不得随导出包出厂)。"""
    for parts in (("scripts", "ssh_inventory.py"), ("scripts", "ssh_lib.py"),
                  ("scripts", "test_e2e_8051.py"), ("scripts", "_probe_http.py"),
                  ("data", "node_evidence", "inv12_mailbox_probe.txt"),
                  ("data", "node_evidence", "inv13_mailbox_e2e_260924045057.txt")):
        assert parts in ed.EXCLUDE_FILES, f"未排除: {parts}"


def test_no_tracked_test_carries_deny_listed_secret():
    """本机守卫: 折叠后 tests/ 源码不得含 deny-list 任一枚记 (公开克隆 skip)。"""
    if not ed.SECRETS_FILE.exists():
        pytest.skip("data/_export_secrets.txt 不在 (公开克隆无本机 deny-list)")
    tokens = ed._secret_tokens()
    assert tokens, "deny-list 为空 — 本机自检失去意义"
    offenders = []
    for p in sorted(Path(__file__).resolve().parent.glob("test_*.py")):
        collapsed = ed._collapse_concat(p.read_text(encoding="utf-8", errors="ignore"))
        for tok in tokens:
            if tok in collapsed:
                offenders.append(f"{p.name}: {tok[:4]}***")
    assert not offenders, offenders


def test_node_bootstrap_test_reads_secrets_from_env_only():
    """契约: 泄漏修复后的 test_node_bootstrap_notebook.py 只准经 env 读真值,
    源码不得残留任何节点坐标字面量赋值。"""
    src = (Path(__file__).resolve().parent / "test_node_bootstrap_notebook.py").read_text(
        encoding="utf-8")
    assert 'os.environ.get("UEA_SCRUB_NODE_IP"' in src
    assert 'os.environ.get("UEA_SCRUB_NODE_PWD"' in src
    assert "import os" in src
    assert '_NODE_IP = "' not in src, "疑似硬编码 IP 赋值复活"
    assert '_NODE_PWD = "' not in src, "疑似硬编码密码赋值复活"
