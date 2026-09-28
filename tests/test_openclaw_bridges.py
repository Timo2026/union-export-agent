"""test_openclaw_bridges.py — #102 T6: OpenClaw 三薄桥 (cnc-quote/dfm-check/email-quote) 契约.

薄桥纪律 (PLAN-email-agent-openclaw-skill-console.md:193): OpenClaw Skill = 薄封装 →
HTTP 调 livekernel API; 禁止把 Timo 引擎逻辑拆进 skill 目录。铁律①: 报价永远由
livekernel 确定性引擎裁决, 回复 draft_only, 无自动外发。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
BRIDGES_DIR = ROOT / "openclaw-skills"
BRIDGE_NAMES = ["cnc-quote", "dfm-check", "email-quote", "text2cad"]

# OpenClaw SKILL.md frontmatter (参考 skills/union-export 既有桥 + openclaw 2026.9.5)
_REQUIRED_FM = ["name", "description", "license", "allowed-tools", "compatibility", "metadata"]
# 薄桥只允许读文件 + curl; 不允许别的执行面
_ALLOWED_TOOLS = {"Read", "Bash(curl *)"}
# 公网 IP 字面量 (节点坐标必须走 env UEA_LIVEKERNEL_URL; loopback 豁免)
_IP_RE = re.compile(r"(?<!\.)(?<!\d)((?:\d{1,3}\.){3}\d{1,3})(?!\d)")


def _load_fm(name: str) -> dict:
    text = (BRIDGES_DIR / name / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    assert m, f"{name}: SKILL.md 缺 YAML frontmatter"
    return yaml.safe_load(m.group(1)) or {}, text


@pytest.mark.parametrize("name", BRIDGE_NAMES)
def test_bridge_exists_with_frontmatter(name: str):
    fm, _ = _load_fm(name)
    for key in _REQUIRED_FM:
        assert key in fm, f"{name}: frontmatter 缺 {key}"


@pytest.mark.parametrize("name", BRIDGE_NAMES)
def test_fm_name_matches_dir(name: str):
    fm, _ = _load_fm(name)
    assert fm.get("name") == name, f"frontmatter name 必须等于目录名 {name}"


@pytest.mark.parametrize("name", BRIDGE_NAMES)
def test_allowed_tools_restricted_to_curl(name: str):
    fm, _ = _load_fm(name)
    raw = str(fm.get("allowed-tools") or "")
    # OpenClaw 格式: "Read Bash(curl *)" — tool 或 tool(模式), 括号内可含空格
    entries = set(re.findall(r"[A-Za-z][A-Za-z0-9_-]*(?:\([^)]*\))?", raw))
    assert entries, f"{name}: allowed-tools 为空"
    assert entries <= _ALLOWED_TOOLS, f"{name}: 越权工具 {entries - _ALLOWED_TOOLS}"


@pytest.mark.parametrize("name", BRIDGE_NAMES)
def test_no_public_ip_literal(name: str):
    _, text = _load_fm(name)
    for hit in _IP_RE.findall(text):
        assert hit.startswith("127."), f"{name}: 出现公网/非 loopback IP 字面量 {hit} (须走 UEA_LIVEKERNEL_URL)"


@pytest.mark.parametrize("name", BRIDGE_NAMES)
def test_env_override_pattern(name: str):
    _, text = _load_fm(name)
    assert "${UEA_LIVEKERNEL_URL:-http://127.0.0.1:8888}" in text, \
        f"{name}: 必须用 env 覆写模式 (默认 loopback :8888)"


@pytest.mark.parametrize("name", BRIDGE_NAMES)
def test_iron_rule_language(name: str):
    _, text = _load_fm(name)
    low = text.lower()
    assert "iron-rule" in low or "铁律" in text, f"{name}: 缺铁律①声明"
    assert "never" in low or "永不" in text, f"{name}: 必须明示 LLM 永不自行出价"


# ---- 分桥端点契约 (转发的 livekernel API, 已 Read/Grep + 节点实证) ----

def test_cnc_quote_bridge_targets_agent_task():
    fm, text = _load_fm("cnc-quote")
    assert "/v1/agent/task" in text
    assert "/health" in text
    # 确定性报价证据字段 (节点实证响应形状)
    for field in ("final_price", "_source", "verification_status"):
        assert field in text, f"cnc-quote: 桥指令缺实证字段 {field}"
    # use_llm=false → 规则路由六技能全链 (节点实测; auto 策略下 LLM 只会选 calc_quote 单技能,
    # result=最后技能输出, 没有 verify_gate/write_reply 的 draft/verification 字段)
    assert "use_llm" in text, "cnc-quote: 必须显式 use_llm=false 走规则路由全链"
    # result 是末位技能输出 (write_reply): 报价 Provenance 在 trace[calc_quote].output
    assert "trace" in text, "cnc-quote: 必须指示从 trace[] 取 calc_quote/check_dfm/verify_gate 输出"
    assert "draft_only" in text.lower()


def test_dfm_check_bridge_requires_material():
    fm, text = _load_fm("dfm-check")
    assert "/v1/agent/task" in text
    # check_dfm tool.py:14 实证: 无 material 报 "material required"
    assert "material" in text, "dfm-check: 必须指示调用方传 material (缺它 skill 报错)"
    assert "conflicts" in text or "冲突" in text
    # 引擎在线时 _source 实证为 live:/api/conflict-check (timo_adapter.py:149)
    assert "live:/api/conflict-check" in text, "dfm-check: 缺 live 引擎 provenance 字段"
    assert "use_llm" in text, "dfm-check: 必须显式 use_llm=false 走规则路由"


def test_email_quote_bridge_is_draft_only():
    fm, text = _load_fm("email-quote")
    assert "/v1/mail/inbox" in text
    assert "/v1/mail/{mail_id}/reprocess" in text
    low = text.lower()
    # 铁律①: 邮件外发永远 draft_only + HITL, 禁自动发送
    assert "draft_only" in low and "auto_send" in low
    assert "smtp" in low  # 必须显式声明 SMTP 默认禁
    # 节点实证: hitl 面板返回 draft(mode/auto_send) + quote + locked, 非 reply.* 嵌套
    assert "context/hitl" in text, "email-quote: 必须走 /context/hitl 面板端点"
    assert "draft.mode" in text or "`mode`" in text, "email-quote: draft 字段路径须与实证一致"


def test_text2cad_bridge_targets_cad_endpoint():
    fm, text = _load_fm("text2cad")
    assert "/v1/cad/text2step" in text, "text2cad: 桥目标端点必须是 /v1/cad/text2step"
    assert "/v1/cad/shapes" in text, "text2cad: 必须先列可用形状族"
    # 缺参 → HITL 槽位填充 (引擎不兜底默认尺寸 — services/text2cad.py:252)
    assert "missing-params" in text, "text2cad: 必须指示缺参返回 missing-params 走槽位填充"
    # cadquery 缺席诚实降级 (开发机 MOCK, 零落盘零冒充 — text2cad.py:259)
    assert "cadquery-unavailable" in text, "text2cad: 必须声明 cadquery-unavailable 诚实降级"
    # 铁律②: text2cad 只画图不定价, 报价永远 Timo 引擎
    low = text.lower()
    assert "timo" in low, "text2cad: 必须声明定价归 Timo 引擎 (只画图不定价)"
    assert "sha256_16" in text, "text2cad: 必须透传真实文件哈希指纹"


def test_bridge_set_exact():
    dirs = {p.name for p in BRIDGES_DIR.iterdir() if p.is_dir()}
    assert dirs == set(BRIDGE_NAMES), f"openclaw-skills/ 目录集漂移: {dirs}"
