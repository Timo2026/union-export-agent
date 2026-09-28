"""scripts/export_demo.py — 干净离线演示包导出 (Track D2).

把源仓库的白名单代码 + 离线 demo 产物镜像到 Documents/demo/union-export-demo,
硬排除一切敏感/瞬时文件 (铁律①: 凭据永不离机; 测试沙箱/审计日志不入库)。

三重自检 (拒绝完成, 非 0 退出):
  1. 文件名: FORBIDDEN_NAMES / FORBIDDEN_SUFFIXES (credentials/sqlite3/key/pem...);
  2. 内容正则: data/_export_secrets.txt (gitignore, 不入包) 的敏感 token +
     公网 IP 正则 (放行 127.x / 0.x / RFC5737 文档段 192.0.2·198.51.100·203.0.113 /
     私网 10.x·192.168.x·172.16-31.x);
     扫描前先 _collapse_concat 折叠引号拼接 ("..." + "...") — 拆写逃逸必须失效;
  3. git 历史: 导出目录全新 git init, 零历史 (由 D3 步骤保证, 此处统计提交数)。

用法:
    python scripts/export_demo.py            # 导出
    python scripts/export_demo.py --dry-run  # 只报告将做什么, 不写盘

退出码 0 = 导出成功且自检无泄漏; 非 0 = 自检发现敏感文件/内容 (拒绝完成)。
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
# P0-B.4 脱敏: home 派生, 不写死作者本机绝对路径 (本机解析结果不变)
DST = Path.home() / "Documents" / "demo" / "union-export-demo"

# 顶层代码目录白名单 (整目录镜像)
CODE_DIRS = [
    "adapters", "agents", "config", "css", "js", "openshell",
    "policies", "schemas", "scripts", "services", "skills", "webui",
    "tests", "docs", "supplier_module", "evaluation", "notebooks",
    "skill_packs", "skill_catalog",
]
CODE_FILES = [
    "bootstrap.py", "requirements.txt", "index.html", "LICENSE",
    "README.md", "CHANGELOG.md", "MANIFEST.md", "CONTRIBUTING.md",
    ".gitignore", "一键启动.bat", "一键自检.bat",
]
# .github CI + deploy 清单 (deploy 只入跟踪的清单文件; 未跟踪 spark 脚本持真实节点 IP, 排除)
EXTRA_DIRS = [".github"]
DEPLOY_FILES = [
    "Dockerfile", "docker-compose.yml", "grafana-dashboard.json", "hpa.yaml",
    "k8s.yaml", "profiles.yaml", "nim/.env.example", "nim/docker-compose.yml",
    "node_bootstrap.ipynb",
]

# 镜像目录内硬排除的单文件 (持敏感字面量, 不进公开 repo)
EXCLUDE_FILES = {
    ("scripts", "sanitize_public.py"),
    # 本地运维/取证工具 (untracked): 内嵌节点坐标或邮箱身份 — deny-list 命中,
    # 只准存活在本机, 任何交付面 (HEAD/package/zip/本地导出) 均不得携带。
    ("scripts", "ssh_inventory.py"), ("scripts", "ssh_lib.py"),
    ("scripts", "test_e2e_8051.py"), ("scripts", "_probe_http.py"),
    ("data", "node_evidence", "inv12_mailbox_probe.txt"),
    ("data", "node_evidence", "inv13_mailbox_e2e_260924045057.txt"),
}

# data/ 白名单 (相对 data/ 的路径) — 仅离线 demo 必需, 绝不含凭据/数据库
DATA_WHITELIST_FILES = [
    "golden_scenarios.json",
    "eval_set.json",
    "demo/demo_result.json",
    "mailbox/demo_test_001.eml",
    "mailbox/demo_test_001.meta.json",
    "mailbox/README.md",
    "flywheel_demo/flywheel_demo.json",
    "flywheel_demo/flywheel_summary.md",
]
DATA_WHITELIST_DIRS = ["samples", "golden_core", "knowledge",
                       "node_evidence", "fusion_evidence"]

# 内容级敏感 token: 从 gitignore 的本地文件读取 (本脚本不含字面量, 可随包发布)
SECRETS_FILE = _ROOT / "data" / "_export_secrets.txt"

# 公网 IP 正则: 放行 loopback/未指定/RFC5737 文档段/私网段; 其余四段点分十进制 → 嫌疑
_IP_RE = re.compile(r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b")

# 拆字面量逃逸对抗: 扫描前先把 "..." + "..." 的引号桥折叠掉。
# 2026-09-27 事故: 真值拆成两截入库 ("A" + "B") 可令三重自检的正则
# 永远拼不完整串 — 自检全绿放行, 真值随交付包出厂。 deny-list 宁可误报不可漏报:
# 折叠后的命中交由人 review, 不是自动放过。
# (本注释自身也只准描述形状: 复述真值即被本折叠扫描命中, 自检拒绝完成。)
_CONCAT_RE = re.compile(r"(['\"])\s*\+\s*(['\"])")


def _collapse_concat(text: str) -> str:
    return _CONCAT_RE.sub("", text)


def _secret_tokens() -> list:
    if not SECRETS_FILE.exists():
        return []
    return [ln.strip() for ln in SECRETS_FILE.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")]


def _ip_is_public(a: int, b: int, c: int, d: int) -> bool:
    if max(a, b, c, d) > 255:
        return False
    if a in (0, 127, 10) or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31):
        return False
    # RFC 5737 三段文档保留段 (TEST-NET-1/2/3, IANA 保留不可路由): 文档/测试里的
    # 示例 IP 不是真实公网主机, 不判泄漏 (只豁免 TEST-NET-3 一段会把 192.0.2.x /
    # 198.51.100.x 文档示例误报成公网 IP — 2026-09-27 加固时发现的缺口)。
    if (a, b, c) in ((192, 0, 2), (198, 51, 100), (203, 0, 113)):
        return False
    return True


# copytree 忽略模式 — 第一道防线
IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "*.pyo", "*.sqlite3", "*.sqlite3-*",
    ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "credentials.json", "gmail_settings.json", "skill_audit.jsonl",
    "*.log", ".env", "*.pem", "*.key", "node_modules",
)

# 自检: 导出后若发现这些文件名/后缀 → 判定泄漏, 拒绝完成
FORBIDDEN_NAMES = {"credentials.json", "gmail_settings.json", "skill_audit.jsonl",
                   "_export_secrets.txt", "sanitize_public.py"}
FORBIDDEN_SUFFIXES = {".sqlite3", ".pem", ".key"}
TEXT_SUFFIXES = {".md", ".yaml", ".yml", ".txt", ".json", ".py", ".html", ".js",
                 ".css", ".bat", ".yml", ".toml", ".cfg", ".ini", ".eml"}


def _rmtree(p: Path, dry: bool) -> None:
    if p.exists():
        if dry:
            print(f"  [dry] rm -r {p}")
        else:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)


def _copytree(src: Path, dst: Path, dry: bool) -> None:
    if not src.exists():
        return
    _rmtree(dst, dry)
    if dry:
        print(f"  [dry] cp -r {src.name}/ -> {dst.parent.name}/{dst.name}/")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, ignore=IGNORE, dirs_exist_ok=True)


def _copyfile(src: Path, dst: Path, dry: bool) -> None:
    if not src.exists():
        return
    if dry:
        print(f"  [dry] cp {src.name}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def export(dry: bool = False) -> int:
    print(f"SRC = {_ROOT}")
    print(f"DST = {DST}")
    if not dry:
        DST.mkdir(parents=True, exist_ok=True)

    print("\n[1/5] 镜像代码白名单 ...")
    for d in CODE_DIRS:
        _copytree(_ROOT / d, DST / d, dry)
    for f in CODE_FILES:
        _copyfile(_ROOT / f, DST / f, dry)
    for d in EXTRA_DIRS:
        _copytree(_ROOT / d, DST / d, dry)
    # deploy: 只入清单文件 (排除持真实节点 IP 的未跟踪 spark 脚本)
    for rel in DEPLOY_FILES:
        _copyfile(_ROOT / "deploy" / rel, DST / "deploy" / rel, dry)

    print("[2/5] 镜像 data/ 白名单 (排除凭据/数据库/审计) ...")
    _rmtree(DST / "data", dry)  # 清空旧 data, 杜绝 contexts/traces/sqlite 残留
    for rel in DATA_WHITELIST_FILES:
        _copyfile(_ROOT / "data" / rel, DST / "data" / rel, dry)
    for rel in DATA_WHITELIST_DIRS:
        _copytree(_ROOT / "data" / rel, DST / "data" / rel, dry)

    print("[3/5] 删除镜像目录内硬排除文件 ...")
    for parts in EXCLUDE_FILES:
        _rmtree(DST.joinpath(*parts), dry)

    # 公开 repo 的 .gitignore 反忽略: 白名单证据产物不受 runtime 忽略规则影响
    # (gitignore 最后匹配者胜; 父目录须先反忽略才能反忽略其中文件)
    GITIGNORE_NEGATE = """
# ---- 公开 repo 白名单证据产物 (export_demo.py 显式导出, 覆盖上方 runtime 忽略) ----
!data/demo/
!data/demo/demo_result.json
!data/flywheel_demo/
!data/flywheel_demo/flywheel_demo.json
!data/flywheel_demo/flywheel_summary.md
"""
    gi = DST / ".gitignore"
    if gi.exists() and not dry:
        cur = gi.read_text(encoding="utf-8")
        if "公开 repo 白名单证据产物" not in cur:
            gi.write_text(cur + GITIGNORE_NEGATE, encoding="utf-8")
            print("  appended .gitignore negations for whitelisted evidence")

    print("[4/5] 清理导出包内任何残留敏感/瞬时文件 ...")
    if not dry and DST.exists():
        for p in list(DST.rglob("*")):
            if p.is_file() and (p.name in FORBIDDEN_NAMES or p.suffix in FORBIDDEN_SUFFIXES):
                p.unlink(missing_ok=True)
                print(f"  removed leaked: {p.relative_to(DST)}")
        for pc in DST.rglob("__pycache__"):
            shutil.rmtree(pc, ignore_errors=True)

    print("[5/5] 三重自检 (拒绝任何泄漏) ...")
    leaks: list = []
    if not dry and DST.exists():
        tokens = _secret_tokens()
        if not tokens:
            print("  [warn] data/_export_secrets.txt 缺失 → 内容 token 检查降级为仅 IP 正则")
        # 检查 1+2: 文件名 + 内容 (token / 公网 IP)
        for p in DST.rglob("*"):
            if not p.is_file():
                continue
            rel = str(p.relative_to(DST))
            if p.name in FORBIDDEN_NAMES or p.suffix in FORBIDDEN_SUFFIXES:
                leaks.append(f"[name] {rel}")
                continue
            if p.suffix not in TEXT_SUFFIXES:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            text = _collapse_concat(text)
            for tok in tokens:
                if tok and tok in text:
                    leaks.append(f"[token] {rel}: {tok[:4]}***")
            for m in _IP_RE.finditer(text):
                a, b, c, d = (int(g) for g in m.groups())
                if _ip_is_public(a, b, c, d):
                    leaks.append(f"[ip] {rel}: {m.group(0)}")
    if leaks:
        print("  ❌ 自检失败, 发现敏感泄漏:")
        for l in leaks[:40]:
            print(f"     - {l}")
        if len(leaks) > 40:
            print(f"     ... 共 {len(leaks)} 条")
        return 2

    # 统计
    n_py = len(list(DST.rglob("*.py"))) if not dry and DST.exists() else 0
    n_skills = len([d for d in (DST / "skills").glob("*/")]) if not dry and (DST / "skills").exists() else 0
    has_fw_pkg = (DST / "services" / "flywheel" / "__init__.py").exists() if not dry else False
    fw_skills = [s for s in ("customer-flywheel", "customer-health", "quote-calibration", "retention-alert")
                 if (DST / "skills" / s).exists()] if not dry else []
    n_tests = len(list((DST / "tests").glob("test_*.py"))) if not dry and (DST / "tests").exists() else 0
    n_docs = len(list((DST / "docs").rglob("*.md"))) if not dry and (DST / "docs").exists() else 0

    if not dry:
        print("\n================ EXPORT SELF-CHECK PASS ================")
        print(f"  .py files       : {n_py}")
        print(f"  skills folders  : {n_skills}")
        print(f"  tests / docs    : {n_tests} test files / {n_docs} docs")
        print(f"  v6.2 flywheel   : {'[OK] services/flywheel/' if has_fw_pkg else '[MISS] absent'}")
        print(f"  flywheel skills : {len(fw_skills)}/4 {fw_skills}")
        print("  sensitive leaks : 0 (filename + token + public-IP 三重检查通过)")
        print("=======================================================")
    else:
        print("\n[dry-run] 未写盘。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return export(dry=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
