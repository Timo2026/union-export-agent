"""tests/test_node_bootstrap_notebook.py — 交付载具 v2 (node_bootstrap.ipynb) 结构完整性 + 内嵌补丁干跑.

覆盖:
  1. cell 序列完整 (title/config/transport/detect×4/reason×2/exec-guard/stage0-3/final) 且 nbformat 合法
  2. 所有 code cell 可编译 (转义缺陷回归: awk 内引号 / -c \\" 丢失 / 正则 \\2 被转义)
  3. 内嵌脚本 PATCH_SRC/PATCH_SET/REQ_SRC 可编译; WIRE_SRC 过 bash -n
  4. PATCH_SRC 干跑: local-vllm provider + primary; fallbacks/mode/旧 provider 不动; 备份 + 原子写
  5. PATCH_SET 干跑: FAST/VISION/REASON→:8002 Omni-30B; EMBED/ASR/timo.base_url 不动;
     engine_src/engine_python 显式填写; 注释保留; yaml 可解析; 幂等 NO-CHANGE
  6. 零凭证字面量: 节点密码/公网 IP 不出现在 notebook (data-stays-local 铁律①)
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

yaml = pytest.importorskip("yaml")
nbformat = pytest.importorskip("nbformat")

_NB = Path(__file__).resolve().parent.parent / "deploy" / "node_bootstrap.ipynb"

# 交付载具 notebook 为本地运维资产 (.gitignore deploy/ 不入公开包): 公开克隆/
# 新装机无此文件时本文件契约测试整体跳过 — 与 test_tools_physically_exist 同模式。
pytestmark = pytest.mark.skipif(
    not _NB.exists(),
    reason="deploy/node_bootstrap.ipynb 不在本机 (.gitignore 本地交付载具, 公开克隆不含)")

EXPECTED_IDS = [
    "nb-title", "nb-config", "nb-transport",
    "nb-detect-env", "nb-detect-llm", "nb-detect-engine",
    "nb-reason-md", "nb-reason",
    "nb-exec-md", "nb-exec-guard",
    "nb-stage0", "nb-stage1", "nb-stage2", "nb-stage3",
    "nb-final",
]

# 内嵌脚本名 -> 语言 (WIRE_SRC 是 bash, 其余 python)
EMBEDDED = {"PATCH_SRC": "py", "PATCH_SET": "py", "REQ_SRC": "py", "WIRE_SRC": "bash"}

# 节点 IP / 密码真值只经 env 注入 (UEA_SCRUB_NODE_IP / UEA_SCRUB_NODE_PWD):
# 本文件入库公开, 源码内嵌真值 (哪怕拆写) 即泄漏。曾以 "A" + "B" 拆写规避
# export_demo.py 的 deny-list "误判", 结果是真值留在公开 HEAD 与交付包, 而自检
# 正则永远看不到连续串 — 逃免疫等于自免疫失效 (2026-09-27 事故, 见
# tests/test_export_demo_selfcheck.py)。公开克隆无 env → 真值断言自动跳过,
# 结构/正则/反硬编码检查不受影响; 本机 export 前自行 export 两变量即恢复守卫。
_NODE_IP = os.environ.get("UEA_SCRUB_NODE_IP", "")
_NODE_PWD = os.environ.get("UEA_SCRUB_NODE_PWD", "")
SECRET_LITERALS = [s for s in ("NGC_API_KEY", "stepfun-api-key", _NODE_IP, _NODE_PWD) if s]


def _load_cells() -> List[dict]:
    assert _NB.exists(), f"notebook 缺失: {_NB}"
    nb = nbformat.read(_NB, as_version=4)
    nbformat.validate(nb)
    return [{"id": c.get("id"), "type": c.cell_type,
             "src": c.source if isinstance(c.source, str) else "".join(c.source)}
            for c in nb.cells]


def _embedded_scripts(cells: List[dict]) -> Dict[Tuple[str, str], str]:
    """抽取 (cell_id, 变量名) -> 脚本文本."""
    found: Dict[Tuple[str, str], str] = {}
    for c in cells:
        if c["type"] != "code":
            continue
        for node in ast.walk(ast.parse(c["src"], mode="exec")):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if (isinstance(t, ast.Name) and t.id in EMBEDDED
                            and isinstance(node.value, ast.Constant)
                            and isinstance(node.value.value, str)):
                        found[(c["id"], t.id)] = node.value.value
    return found


# ---------- 1. cell 序列 ----------
def test_cell_sequence_and_nbformat_valid() -> None:
    cells = _load_cells()
    ids = [c["id"] for c in cells]
    assert ids == EXPECTED_IDS, ids
    kinds = {c["id"]: c["type"] for c in cells}
    assert kinds["nb-title"] == "markdown" and kinds["nb-reason-md"] == "markdown"
    assert kinds["nb-exec-md"] == "markdown"
    assert sum(1 for c in cells if c["type"] == "code") == 12


# ---------- 2. code cell 全部可编译 ----------
def test_all_code_cells_compile() -> None:
    cells = _load_cells()
    for c in cells:
        if c["type"] != "code":
            continue
        try:
            compile(c["src"], c["id"], "exec")
        except SyntaxError as e:
            pytest.fail(f"cell {c['id']} 语法错误: {e!r}")


# ---------- 3. 内嵌脚本编译 / bash -n ----------
def test_embedded_scripts_present_and_compile() -> None:
    cells = _load_cells()
    found = _embedded_scripts(cells)
    for (cid, name) in [("nb-stage1", "PATCH_SRC"), ("nb-stage3", "PATCH_SET"),
                        ("nb-stage2", "REQ_SRC"), ("nb-stage2", "WIRE_SRC")]:
        assert (cid, name) in found, f"内嵌脚本缺失: {cid}/{name}"
    for (cid, name), text in found.items():
        if EMBEDDED[name] == "bash":
            continue
        try:
            compile(text, f"{cid}/{name}", "exec")
        except SyntaxError as e:
            pytest.fail(f"内嵌脚本 {cid}/{name} 语法错误: {e!r}")


def test_wire_env_sh_bash_syntax() -> None:
    cells = _load_cells()
    found = _embedded_scripts(cells)
    text = found[("nb-stage2", "WIRE_SRC")]
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("无 bash, 跳过 bash -n")
    p = subprocess.run([bash, "-n"], input=text, text=True,
                       capture_output=True, timeout=30)
    assert p.returncode == 0, f"WIRE_SRC bash 语法错误: {p.stderr}"


# ---------- 4. PATCH_SRC 干跑 ----------
def _run_py(text: str, args: List[str], tmp_path: Path, name: str):
    script = tmp_path / name
    script.write_text(text, encoding="utf-8")
    return subprocess.run([sys.executable, str(script)] + args,
                          capture_output=True, text=True, timeout=60)


def _openclaw_fixture() -> dict:
    return {
        "models": {"mode": "merge",
                   "providers": {"stepfun-plan": {"baseUrl": "https://api.stepfun.com",
                                                  "models": ["step-5-preview"]}}},
        "agents": {"entries": {"main": {"model": {
            "primary": "stepfun-plan/step-5-preview",
            "fallbacks": ["stepfun-plan/step-5", "stepfun-plan/step-3"]}}}},
    }


def test_patch_openclaw_wires_local_vllm(tmp_path: Path) -> None:
    cells = _load_cells()
    src = _embedded_scripts(cells)[("nb-stage1", "PATCH_SRC")]
    cfg = tmp_path / "openclaw.json"
    cfg.write_text(json.dumps(_openclaw_fixture(), ensure_ascii=False, indent=2),
                   encoding="utf-8")
    r = _run_py(src, [str(cfg), "http://127.0.0.1:8002/v1",
                      "nemotron-omni-30b-a3b", "apply"], tmp_path, "patch_oc.py")
    assert r.returncode == 0, r.stderr
    after = json.loads(cfg.read_text(encoding="utf-8"))
    provs = after["models"]["providers"]
    assert provs["local-vllm"] == {"baseUrl": "http://127.0.0.1:8002/v1",
                                   "api": "openai-completions",
                                   "models": ["nemotron-omni-30b-a3b"]}
    mdl = after["agents"]["entries"]["main"]["model"]
    assert mdl["primary"] == "local-vllm/nemotron-omni-30b-a3b"
    assert mdl["fallbacks"] == ["stepfun-plan/step-5", "stepfun-plan/step-3"]
    assert after["models"]["mode"] == "merge"
    assert "stepfun-plan" in provs
    assert len(list(tmp_path.glob("openclaw.json.bak-uea-*"))) == 1
    assert not list(tmp_path.glob("*.tmp-uea"))


def test_patch_openclaw_dry_run_does_not_write(tmp_path: Path) -> None:
    cells = _load_cells()
    src = _embedded_scripts(cells)[("nb-stage1", "PATCH_SRC")]
    fixture = _openclaw_fixture()
    cfg = tmp_path / "openclaw.json"
    cfg.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
    r = _run_py(src, [str(cfg), "http://127.0.0.1:8002/v1", "m", "dry"],
                tmp_path, "patch_oc.py")
    assert r.returncode == 0, r.stderr
    assert json.loads(cfg.read_text(encoding="utf-8")) == fixture


# ---------- 5. PATCH_SET 干跑 ----------
def _settings_fixture(tmp_path: Path) -> Path:
    src = (Path(__file__).resolve().parent.parent / "config" / "settings.yaml")
    dst = tmp_path / "settings.yaml"
    shutil.copy2(src, dst)
    return dst


def _patch_settings(cells, tmp_path, cfg, embed_ep="", embed_model="",
                    eng="/e/Timo_CNC-AI-Brain-v12.0-Fusion", eng_py="/p/occ/bin/python"):
    src = _embedded_scripts(cells)[("nb-stage3", "PATCH_SET")]
    return _run_py(src, [str(cfg), "http://127.0.0.1:8002/v1", "nemotron-omni-30b-a3b",
                         embed_ep, embed_model, eng, eng_py],
                   tmp_path, "patch_set.py")


def test_patch_settings_roles_and_engine(tmp_path: Path) -> None:
    cells = _load_cells()
    cfg = _settings_fixture(tmp_path)
    pre = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    pre_roles = pre["model_router"]["roles"]
    pre_untouched = {
        "EMBED": pre_roles["EMBED"]["endpoint"],
        "ASR": pre_roles["ASR"]["endpoint"],
        "timo.base_url": pre["timo"]["base_url"],
        "egress.allow": pre["egress"]["allow"],
        "funasr.vlm_url": pre["funasr"]["vlm_url"],
    }
    r = _patch_settings(cells, tmp_path, cfg)
    assert r.returncode == 0, r.stderr
    assert "PATCHED" in r.stdout
    d = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    roles = d["model_router"]["roles"]
    for role in ("FAST", "VISION", "REASON"):
        assert roles[role]["endpoint"] == "http://127.0.0.1:8002/v1", role
        assert roles[role]["model"] == "nemotron-omni-30b-a3b", role
    # 未探活/非本版辖域字段一律不动 — 断言"与 fixture 预值一致"而非硬编码具体值:
    # fixture 即 config/settings.yaml, 开发机 profile 与节点 profile 端点取值不同
    assert roles["EMBED"]["endpoint"] == pre_untouched["EMBED"]       # 未探活不动
    assert roles["ASR"]["endpoint"] == pre_untouched["ASR"]           # 不动
    assert d["timo"]["engine_src"] == "/e/Timo_CNC-AI-Brain-v12.0-Fusion"
    assert d["timo"]["engine_python"] == "/p/occ/bin/python"
    assert d["timo"]["base_url"] == pre_untouched["timo.base_url"]    # PRD 6.3: 不动
    txt = cfg.read_text(encoding="utf-8")
    assert "# ---- Model Router (L3 Model Mesh) ----" in txt           # 注释保留
    assert d["egress"]["allow"] == pre_untouched["egress.allow"]      # 铁律①不动
    assert d["funasr"]["vlm_url"] == pre_untouched["funasr.vlm_url"]  # funasr 段不动
    assert len(list(tmp_path.glob("settings.yaml.bak-uea-*"))) == 1
    assert not list(tmp_path.glob("*.tmp-uea"))


def test_patch_settings_embed_when_probed_live(tmp_path: Path) -> None:
    cells = _load_cells()
    cfg = _settings_fixture(tmp_path)
    r = _patch_settings(cells, tmp_path, cfg,
                        embed_ep="http://127.0.0.1:8011/v1",
                        embed_model="nvidia/nv-embedqa-e5-v5")
    assert r.returncode == 0, r.stderr
    d = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    emb = d["model_router"]["roles"]["EMBED"]
    assert emb["endpoint"] == "http://127.0.0.1:8011/v1"
    assert emb["model"] == "nvidia/nv-embedqa-e5-v5"


def test_patch_settings_idempotent(tmp_path: Path) -> None:
    cells = _load_cells()
    cfg = _settings_fixture(tmp_path)
    assert _patch_settings(cells, tmp_path, cfg).returncode == 0
    r2 = _patch_settings(cells, tmp_path, cfg)
    assert r2.returncode == 0
    assert "NO-CHANGE" in r2.stdout


def test_req_check_runs(tmp_path: Path) -> None:
    cells = _load_cells()
    src = _embedded_scripts(cells)[("nb-stage2", "REQ_SRC")]
    req = Path(__file__).resolve().parent.parent / "requirements.txt"
    r = _run_py(src, [str(req)], tmp_path, "check_reqs.py")
    assert r.returncode == 0, r.stderr
    line = r.stdout.strip().splitlines()[-1]
    assert line == "ALL-PRESENT" or line.startswith("MISSING:")


# ---------- 6. 零凭证字面量 ----------
def test_notebook_has_no_secret_literals() -> None:
    raw = _NB.read_text(encoding="utf-8")
    for s in SECRET_LITERALS:
        assert s not in raw, f"notebook 疑似凭据字面量: {s}"
    # 坐标只经 env: code cell 不得把坐标变量赋成字面量 (赋值右侧须为 os.environ.get;
    # 错误提示文案里出现 env 变量名属正常, 不算硬编码)
    assign_re = re.compile(
        r"^\s*(SSH_HOST|SSH_PORT|SSH_USER|SSH_PWD|SSH_KEY|HOST|PORT|USER|PWD)\s*=\s*(?!os\.environ)"
        r"['\"\d]")
    ip_re = re.compile(
        r"\b(?!127\.)(?!10\.)(?!192\.168\.)(?!172\.(?:1[6-9]|2\d|3[01])\.)"
        r"(?!0\.)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
    for c in _load_cells():
        if c["type"] != "code":
            continue
        for line in c["src"].splitlines():
            if assign_re.search(line) or ip_re.search(line):
                pytest.fail(f"疑似硬编码坐标: {line.strip()[:120]}")


# ---------- 7. pivot v2: 全 Omni 口径 (2026-09-22 user 拍板「放弃 30B, 全部接 Omni 30B」) ----------
# 30B (:8000) 与 Omni (:8002) unified-memory 不可共存 (30B 任何 util 配方 KV cache
# 分配期 crash-loop, watchdog 22 次重启)。驻留收缩为 Omni 唯一推理端点后, 笔记本
# 的默认接线/侦测口径/补丁调用点必须同步, 否则 freshly-bootstrap 的节点仍按 30B 时代
# 口径校验 (ok_router 认 :8000) 并误报缺口。
def _cell_src(cells: List[dict], cid: str) -> str:
    for c in cells:
        if c["id"] == cid:
            return c["src"]
    raise AssertionError(f"cell 缺失: {cid}")


def test_vllm_defaults_point_to_omni_8002() -> None:
    src = _cell_src(_load_cells(), "nb-config")
    m = re.search(r'VLLM_URL\s*=\s*os\.environ\.get\(\s*"UEA_VLLM_URL"\s*,\s*"([^"]+)"', src)
    assert m, "nb-config 未定义 VLLM_URL 默认值"
    assert ":8002" in m.group(1), f"VLLM_URL 默认应指 Omni :8002, 实际 {m.group(1)}"
    m2 = re.search(r'VLLM_MODEL\s*=\s*os\.environ\.get\(\s*"UEA_VLLM_MODEL"\s*,\s*"([^"]+)"', src)
    assert m2, "nb-config 未定义 VLLM_MODEL 默认值"
    assert m2.group(1) == "nemotron-omni-30b-a3b", (
        f"VLLM_MODEL 默认应为 nemotron-omni-30b-a3b, 实际 {m2.group(1)}")


def test_watch_ports_drop_abandoned_topology() -> None:
    src = _cell_src(_load_cells(), "nb-config")
    m = re.search(r"WATCH_PORTS\s*=\s*\[([^\]]+)\]", src)
    assert m, "nb-config 未定义 WATCH_PORTS"
    ports = {p.strip() for p in m.group(1).split(",") if p.strip()}
    for dead in ("8000", "8001", "8020", "8021"):
        assert dead not in ports, f"WATCH_PORTS 残留弃用拓扑端口 {dead} (30B/NIM 线)"
    for live in ("8002", "8011", "7862", "8888"):
        assert live in ports, f"WATCH_PORTS 失常驻端口 {live}"


def test_detect_router_check_expects_omni_8002() -> None:
    src = _cell_src(_load_cells(), "nb-detect-engine")
    assert '":8002" in fast_ep' in src, "detect 路由检查应期望 Omni :8002"
    assert '":8000" in fast_ep' not in src, "detect 路由检查不得再认 :8000 (30B 弃用)"
    assert "(→ :8000" not in src, "detect 修复提示不得指向 :8000"


def test_stage3_patch_call_site_uses_vllm_url() -> None:
    src = _cell_src(_load_cells(), "nb-stage3")
    assert '"http://127.0.0.1:8000/v1"' not in src, "阶段3 补丁调用点不得硬编码 :8000"
    assert "SETTINGS, VLLM_URL, VLLM_MODEL" in src, (
        "阶段3 补丁调用点应走 VLLM_URL/VLLM_MODEL (env 可覆盖 Omni 端点)")


def test_execute_wiring_has_no_8000_literal() -> None:
    cells = _load_cells()
    for cid in ("nb-config", "nb-detect-engine", "nb-stage1", "nb-stage3"):
        src = _cell_src(cells, cid)
        assert ":8000" not in src, f"cell {cid} 残留 :8000 字面量 (30B 弃用 pivot)"
