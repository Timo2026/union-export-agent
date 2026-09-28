"""tests/test_mail_classifier.py — 询价意图分类器 (mail filter layer, 2026-09-24).

判定样本全部来自节点实测 (data/node_evidence/inv12_mailbox_probe.txt):
  - 真询价: 客户样例邮箱 "询价报价c2123 工件 铝合金6061..." (唯一应处理的)
  - 德语句子: "Anfrage: 60 Stueck Halter Aluminium 6061, Zeichnung im Anhang"
  - 垃圾样本: NVIDIA 通知 / 黑客松 / 报名成功 / 验证邮件 / 我方外发报价交付

fail-safe 原则: 配置损坏 → 不过滤 (按询价处理), 绝不静默丢邮件。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# ---- 真实样本 (inv12 实测) ----
GENUINE_RFQ_SUBJECT = (
    "询价报价c2123 工件 铝合金6061，数量：9，精度：0.1普通，阳极氧化黑，"
    "RA值：3.2 完成报价后，回传给我报价模板.XSLX，PDF都可以行"
)
GENUINE_RFQ_BODY = "请报价，附件是图纸，数量 9 件，6061 阳极氧化黑。"
GERMAN_RFQ_SUBJECT = "Anfrage: 60 Stueck Halter Aluminium 6061, Zeichnung im Anhang"
JUNK_SUBJECTS = [
    "「中客松」活动即将结束",
    "API Key 额度即将耗尽",
    "HACKATHONS just for you, Timo2026",
    "2026 AMD锐龙AI智能体创新应用大赛-采访视频内容授权确认",
    "9 月 17 日 NVIDIA AI 培训班 | 加速计算基础 —— CUDA C++ 前沿技术",
    "【入选通知】恭喜！你的作品已入选云栖大会线下展示｜千问办公AI生产力大赛",
    "【重要】距 9/20 提交截止仅剩一周 · openvela AI 硬件开发者大赛作品提交提醒与自查清单",
    "[DIA赛事通知] 2026中国设计智造大奖复评作品寄送提醒",
    "针对您的物理 AI 用例对 NVIDIA Cosmos 进行后训练",
    "FDE 实战松｜报名成功与专属登录链接",
    "Watch Ming-Yu Liu's keynote at Fellows Forum 2026",
    "验证您的电子邮箱地址",
    "Thank you for enrolling in 规模化部署 RAG 工作流!",
    "FDE工程师认证×伙伴招募双启动，五维权益加持",
    "【审核通过】2026 NVIDIA 中国开发者日",
    "ClawHub blocked a skill version",
    "报名倒计时｜线上解锁 Agent Skills，线下见证黑客松巅峰对决",
    "回复：曹冬冬交作业麻烦审核补充验证，谢谢",
    "MTZ260171获奖项目奖金及奖品确认单",
    "中客松致选手感谢信",
    "平台",
    "2",
    "回复：中客松致选手感谢信",
]
SELF_OUTBOUND_SUBJECT = (
    "【报价交付】直齿圆柱齿轮 12齿Ø80×3mm 304不锈钢｜图号 GEAR-12T-80M-3-304 "
    "/ Quotation: Spur Gear 12T Ø80x3mm, 304 SS — GEAR-12T-80M-3-304"
)
GRAY_SUBJECT = "平台"


def _clf():
    from services.mail_classifier import classify
    return classify


# ---- 1. 真询价 → rfq ----
def test_genuine_rfq_chinese() -> None:
    v = _clf()(subject=GENUINE_RFQ_SUBJECT, body=GENUINE_RFQ_BODY)
    assert v.kind == "rfq"
    assert v.score >= 1
    assert "询价" in v.positive


def test_genuine_rfq_german_with_cad_attachment() -> None:
    v = _clf()(subject=GERMAN_RFQ_SUBJECT, body="Do you quote 60 pcs?",
               attachments=["halter_zeichnung.step"])
    assert v.kind == "rfq"
    assert v.cad_attachment is True
    assert "anfrage" in v.positive


def test_cad_attachment_alone_is_positive_signal() -> None:
    """无关键词但带 STEP 图纸 → 视为询价 (客户常只写"见图纸")."""
    v = _clf()(subject="Re: your visit", body="see attached drawing",
               attachments=["part.stp"])
    assert v.cad_attachment is True
    assert v.score >= 1
    assert v.kind == "rfq"


# ---- 2. 垃圾/通知样本 → skip 或 gray (都不入黄金链) ----
@pytest.mark.parametrize("subject", JUNK_SUBJECTS)
def test_junk_mail_not_rfq(subject: str) -> None:
    v = _clf()(subject=subject, body="感谢您的参与，详情请点击链接查看。")
    assert v.kind in ("skip", "gray"), f"{subject!r} 被判为 {v.kind} (score={v.score})"


def test_self_outbound_quote_delivery_is_skip() -> None:
    """我方外发报价交付信 (含'报价交付'强负标记) → 跳过, 不重复解读."""
    v = _clf()(subject=SELF_OUTBOUND_SUBJECT, body="Quotation attached.")
    assert v.kind == "skip"


def test_gray_zone_no_signals() -> None:
    v = _clf()(subject=GRAY_SUBJECT, body="")
    assert v.kind == "gray"
    assert v.score == 0


def test_strong_negative_is_decisive() -> None:
    """含询价词但来自机器发件人标记 (noreply) → 仍跳过, 正信号不救."""
    v = _clf()(subject="询价报价 6061 工件", body="数量 100",
               attachments=[])
    assert v.kind == "rfq"
    v2 = _clf()(subject="【自动回复】询价报价 6061 工件", body="数量 100")
    assert v2.kind == "skip"
    assert v2.negative


# ---- 3. should_process: 策略映射 ----
def test_should_process_rfq_always() -> None:
    from services.mail_classifier import classify, should_process
    v = classify(subject=GENUINE_RFQ_SUBJECT, body=GENUINE_RFQ_BODY)
    assert should_process(v) is True


def test_should_process_gray_respects_policy() -> None:
    from services.mail_classifier import classify, should_process
    v = classify(subject=GRAY_SUBJECT, body="")
    # 默认灰区动作为 skip_review (用户 2026-09-24 拍板)
    assert should_process(v) is False
    # 显式改 process 策略则放行
    assert should_process(v, gray_zone_action="process") is True


def test_skip_never_processed() -> None:
    from services.mail_classifier import classify, should_process
    v = classify(subject="验证您的电子邮箱地址", body="")
    assert should_process(v, gray_zone_action="process") is False


# ---- 4. 配置加载: 默认值 + 覆盖 + fail-safe ----
def test_load_policy_defaults(tmp_path: Path) -> None:
    from services.mail_classifier import load_mail_filter_policy
    pol = load_mail_filter_policy(tmp_path)  # 无 policy.yaml → 默认
    assert pol["enabled"] is True
    assert pol["gray_zone_action"] == "skip_review"
    assert pol["mark_read_on_terminal"] is True
    assert "询价" in pol["positive_terms"]
    assert ".step" in pol["cad_extensions"]


def test_load_policy_override_and_fail_safe(tmp_path: Path) -> None:
    from services.mail_classifier import load_mail_filter_policy
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "policy.yaml").write_text(
        "mail_filter:\n  enabled: false\n  positive_terms: [bespoke]\n", encoding="utf-8")
    pol = load_mail_filter_policy(tmp_path)
    assert pol["enabled"] is False
    assert "bespoke" in pol["positive_terms"]
    # 损坏 YAML → 全默认 (不过滤), 不炸
    (tmp_path / "config" / "policy.yaml").write_text("mail_filter: [broken", encoding="utf-8")
    pol2 = load_mail_filter_policy(tmp_path)
    assert pol2["enabled"] is True


def test_disabled_policy_processes_everything() -> None:
    """fail-safe: enabled=false → 不过滤, 全部按询价 (绝不静默丢邮件)."""
    from services.mail_classifier import classify, should_process
    v = classify(subject="验证您的电子邮箱地址", body="", enabled=False)
    assert v.kind == "rfq"
    assert should_process(v, enabled=False) is True


# ---- 5. CAD 容器附件豁免 (2026-09-26, zip 邮件断点修复) ----
# 节点实测: 带 zip 图纸包的询价邮件主题命中弱负标记 (赛事/通知/权益, 权重 1 可
# 叠加) → 整封 skip, zip 从未进黄金链。豁免: CAD 容器附件 (zip/pdf/dwg/7z)
# 把判定地板抬到 gray (人工复核徽标) 或按策略直接 rfq; 强负仍决定性 skip。
CAD_ZIP_MAIL_SUBJECT = "第三届 NVIDIA DGX Spark 黑客松赛事资料发放通知"
CAD_ZIP_MAIL_BODY = "赛事资料包见附件 Timo.zip, 请查收。"


def test_zip_container_floors_weak_negatives_to_gray() -> None:
    """zip 图纸包 + 弱负叠加主题 → gray 待复核, 不再整封打死 (断点 1 修复)."""
    v = _clf()(subject=CAD_ZIP_MAIL_SUBJECT, body=CAD_ZIP_MAIL_BODY,
               attachments=["Timo.zip"])
    assert v.cad_attachment is True
    assert v.kind == "gray", f"应豁免为灰区, 实判 {v.kind} (score={v.score})"


def test_container_exemption_covers_pdf_dwg() -> None:
    for name in ("zeichnung.pdf", "teil.dwg"):
        v = _clf()(subject="API Key 额度即将耗尽", body="额度通知",
                   attachments=[name])
        assert v.kind == "gray", f"{name} 未获豁免: {v.kind}"


def test_strong_negative_still_skip_with_zip_container() -> None:
    """强负 (我方外发报价交付/退订/noreply) 机器信 → 豁免不救, 仍 skip."""
    v = _clf()(subject=SELF_OUTBOUND_SUBJECT, body="Quotation attached.",
               attachments=["GEAR-12T.zip"])
    assert v.kind == "skip"
    v2 = _clf()(subject="unsubscribe newsletter no-reply",
                body="附件 parts.zip", attachments=["parts.zip"])
    assert v2.kind == "skip"


def test_container_exemption_action_rfq_via_policy(tmp_path: Path) -> None:
    """策略 cad_container_action: rfq → 容器附件直接入黄金链 (全自动档)."""
    from services.mail_classifier import classify, load_mail_filter_policy
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "policy.yaml").write_text(
        "mail_filter:\n  cad_container_action: rfq\n", encoding="utf-8")
    pol = load_mail_filter_policy(tmp_path)
    assert pol["cad_container_action"] == "rfq"
    v = classify(subject=CAD_ZIP_MAIL_SUBJECT, body=CAD_ZIP_MAIL_BODY,
                 attachments=["Timo.zip"], policy=pol)
    assert v.kind == "rfq"


def test_container_exemption_not_triggered_without_attachment() -> None:
    """无附件 → 豁免不生效: 弱负叠加仍 skip (豁免不是万能放行)."""
    v = _clf()(subject=CAD_ZIP_MAIL_SUBJECT, body=CAD_ZIP_MAIL_BODY)
    assert v.kind == "skip"


def test_load_policy_cad_container_action_default(tmp_path: Path) -> None:
    from services.mail_classifier import load_mail_filter_policy
    pol = load_mail_filter_policy(tmp_path)
    assert pol["cad_container_action"] == "gray"   # 默认灰区待复核, 不自动入链
