"""mail_classifier.py — 询价意图分类器 (mail filter layer, 2026-09-24).

动机 (节点实测 inv12): QQ 收件箱 50 封仅 1 封真询价, 但 orchestrator 对每封
邮件都跑 cat.run() 生成 RFQ context — NVIDIA 通知/黑客松/报名信全部停在 HITL,
且同一封报名信被解读 5 遍生成 5 个 context。本模块在入链前做确定性意图判定。

判定 (纯关键词打分, 不依赖 LLM, 可测试可复现):
  score = Σ正信号(询价/报价/quotation/RFQ/Anfrage/数量/图纸/CNC/...) − Σ负信号
  强负信号 (noreply/unsubscribe/推广/退订/报价交付...) 权重 3, 弱负信号权重 1;
  带 CAD 附件 (.step/.stp/.igs/.stl/.dxf/...) 记 +2 (客户常只写"见图纸报价")。
  CAD 容器附件 (.zip/.pdf/.dwg 图纸包, 2026-09-26): 弱负叠加本会整封 skip,
  豁免把地板抬到 gray (或按 mail_filter.cad_container_action=rfq 直接入链) —
  节点实测 zip 询价邮件被弱负叠加打死的断点修复; 强负仍决定性 skip。
  score >= +1 → rfq    入黄金链
  score <= −1 → skip   非询价 (通知/营销/我方外发), 不建 context
  score ==  0 → gray   灰区, 动作由 policy mail_filter.gray_zone_action 决定
                    (用户 2026-09-24 拍板: 默认 skip_review 跳过+待复核徽标,
                     可经 POST /v1/mail/{id}/reprocess 人工强制重跑)

fail-safe: 配置缺失/损坏 → 全默认 (enabled=true, 默认词表); enabled=false →
不过滤全部放行 (丢真询价比多处理垃圾邮件更糟)。

策略单源: config/policy.yaml 的 mail_filter 节 (与 hitl escalation 同源)。
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# 询价正信号 (中/英/德) — 机加工外贸询盘常用词
POSITIVE_TERMS = [
    # 中文
    "询价", "询盘", "求购", "采购", "报价", "数量", "图纸", "图号", "工件", "配件",
    "零件", "加工", "定制", "打样", "样品", "公差", "材质", "表面处理", "阳极氧化",
    "电镀", "喷涂", "精度", "批量", "单价", "交期", "货期", "产能", "报价单", "起订量",
    # English
    "quote", "quotation", "rfq", "inquiry", "enquiry", "pricing",
    "machined", "machining", "cnc", "tolerance", "lead time", "prototype",
    "anodiz", "pcs", "pieces", "samples", "brackets", "bracket",
    # Deutsch
    "anfrage", "angebot", "zeichnung", "stück", "stueck", "werkstück",
]

# 强负信号 (通知/营销/退订/我方外发) — 权重 3, 出现即压倒正信号
STRONG_NEGATIVE_TERMS = [
    "noreply", "no-reply", "no_reply", "donotreply", "do-not-reply", "do_not_reply",
    "newsletter", "unsubscribe", "list-unsubscribe", "退订", "推广", "广告", "营销",
    "报价交付", "投递确认", "delivery probe", "自动回复", "out of office",
]

# 弱负信号 (系统通知/赛事/活动类) — 权重 1
WEAK_NEGATIVE_TERMS = [
    "notify", "notification", "通知", "报名", "入选", "感谢信", "验证", "提醒",
    "截止", "倒计时", "确认", "审核", "大赛", "挑战赛", "竞赛", "赛事", "hackathon",
    "winner", "prize", "award", "contest", "competition", "keynote", "forum",
    "webinar", "workshop", "enrolled", "enrolling", "enrollment", "认证", "招募",
    "专属", "登录链接", "即将", "培训班", "开发者日", "线下展示", "权益", "额度",
    "领取", "查收", "thank you for", "活动", "获奖", "邀请", "注册成功", "生效",
]

CAD_EXTENSIONS = [
    ".step", ".stp", ".igs", ".iges", ".stl", ".dxf", ".sldprt", ".sldasm",
    ".prt", ".x_t", ".sat", ".model", ".3dm",
]

# CAD 容器附件 (2026-09-26 zip 断点修复): 图纸包/图纸文档, 本身即是询价信号 —
# 客户常只写"资料包见附件"。命中弱负叠加 (赛事/通知/权益, 权重 1) 时豁免,
# 把判定地板抬到 gray; 强负标记 (noreply/退订/我方外发) 仍决定性 skip。
CAD_CONTAINER_EXTENSIONS = [".zip", ".pdf", ".dwg"]

_STRONG_WEIGHT = 3
_WEAK_WEIGHT = 1
_CAD_BONUS = 2
_DEFAULT_BODY_SCAN_CHARS = 4000

_DEFAULTS: Dict[str, Any] = {
    "enabled": True,
    "gray_zone_action": "skip_review",   # skip_review (用户拍板默认) | process
    "mark_read_on_terminal": True,
    "cad_container_action": "gray",      # gray (默认, 待复核徽标) | rfq (直接入链)
    "positive_terms": list(POSITIVE_TERMS),
    "strong_negative_terms": list(STRONG_NEGATIVE_TERMS),
    "weak_negative_terms": list(WEAK_NEGATIVE_TERMS),
    "cad_extensions": list(CAD_EXTENSIONS),
    "cad_container_extensions": list(CAD_CONTAINER_EXTENSIONS),
    "body_scan_chars": _DEFAULT_BODY_SCAN_CHARS,
}


@dataclass
class MailVerdict:
    """单封邮件的询价意图判定结果."""
    kind: str                      # rfq | skip | gray
    score: int
    positive: List[str] = field(default_factory=list)
    negative: List[str] = field(default_factory=list)
    cad_attachment: bool = False
    reason: str = ""

    @property
    def needs_review(self) -> bool:
        """灰区跳过 → 需人工复核徽标 (可 reprocess 覆写)."""
        return self.kind == "gray"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "score": self.score,
            "positive": self.positive,
            "negative": self.negative,
            "cad_attachment": self.cad_attachment,
            "reason": self.reason,
        }


def load_mail_filter_policy(root: Optional[Path] = None) -> Dict[str, Any]:
    """读 config/policy.yaml 的 mail_filter 节, 与默认合并; 损坏 → 全默认."""
    pol = dict(_DEFAULTS)
    pol["positive_terms"] = list(_DEFAULTS["positive_terms"])
    pol["strong_negative_terms"] = list(_DEFAULTS["strong_negative_terms"])
    pol["weak_negative_terms"] = list(_DEFAULTS["weak_negative_terms"])
    pol["cad_extensions"] = list(_DEFAULTS["cad_extensions"])
    pol["cad_container_extensions"] = list(_DEFAULTS["cad_container_extensions"])
    try:
        from services.config import load_policy
        raw = (load_policy(root) or {}).get("mail_filter") or {}
        if isinstance(raw, dict):
            for key in ("enabled", "gray_zone_action", "mark_read_on_terminal",
                        "body_scan_chars", "cad_container_action"):
                if key in raw and raw[key] is not None:
                    pol[key] = raw[key]
            for key in ("positive_terms", "strong_negative_terms",
                        "weak_negative_terms", "cad_extensions",
                        "cad_container_extensions"):
                val = raw.get(key)
                if isinstance(val, list) and val:
                    pol[key] = [str(t) for t in val]
    except Exception as e:  # fail-safe: 配置坏 → 默认词表继续过滤
        log.warning("[mail_classifier] policy 读取失败, 用默认: %r", e)
    return pol


def _hits(text: str, terms: List[str]) -> List[str]:
    return [t for t in terms if t and t.lower() in text]


def classify(
    subject: str = "",
    body: str = "",
    attachments: Optional[List[str]] = None,
    *,
    policy: Optional[Dict[str, Any]] = None,
    enabled: bool = True,
) -> MailVerdict:
    """询价意图判定. enabled=False → 直接 rfq (fail-safe 不过滤)."""
    if policy is None:
        policy = _DEFAULTS
    if not enabled:
        return MailVerdict(kind="rfq", score=0, reason="filter disabled")
    scan_chars = int(policy.get("body_scan_chars") or _DEFAULT_BODY_SCAN_CHARS)
    text = f"{subject or ''}\n{(body or '')[:scan_chars]}".lower()

    positive = _hits(text, policy.get("positive_terms") or [])
    strong_neg = _hits(text, policy.get("strong_negative_terms") or [])
    weak_neg = _hits(text, policy.get("weak_negative_terms") or [])

    cad = False
    container = False
    cad_exts = set(policy.get("cad_extensions") or [])
    cont_exts = set(policy.get("cad_container_extensions") or [])
    for name in attachments or []:
        suf = Path(str(name)).suffix.lower()
        if suf in cad_exts:
            cad = True
        if suf in cont_exts:
            container = True

    score = (len(positive)
             + (_CAD_BONUS if cad else 0)
             - _STRONG_WEIGHT * len(strong_neg)
             - _WEAK_WEIGHT * len(weak_neg))

    # 强负信号是决定性的: 机器发件人(noreply/unsubscribe)/退订/我方外发标记
    # 出现即跳过, 正信号不救 — 真客户不会从 noreply 地址发询盘。
    if strong_neg:
        return MailVerdict(kind="skip", score=score, positive=positive,
                           negative=strong_neg + weak_neg, cad_attachment=cad,
                           reason=f"非询价: 命中强负标记 {strong_neg}")
    if score >= 1:
        return MailVerdict(kind="rfq", score=score, positive=positive,
                           negative=strong_neg + weak_neg, cad_attachment=cad,
                           reason=f"+{len(positive)} 询价信号"
                                  + (" +CAD附件" if cad else ""))
    # CAD 容器附件豁免 (2026-09-26): 弱负叠加 (赛事/通知/权益) 本会整封 skip,
    # 但 zip/pdf/dwg 图纸包常伴"见图纸报价" — 客户不写询价词。豁免把地板抬到
    # gray (人工复核徽标,  reprocess 可强制入链) 或按策略直接 rfq。
    if score <= -1 and container:
        action = str(policy.get("cad_container_action") or "gray")
        if action == "rfq":
            return MailVerdict(kind="rfq", score=score, positive=positive,
                               negative=strong_neg + weak_neg, cad_attachment=True,
                               reason="CAD 容器附件豁免: 图纸包直入黄金链 "
                                      "(cad_container_action=rfq)")
        return MailVerdict(kind="gray", score=score, positive=positive,
                           negative=strong_neg + weak_neg, cad_attachment=True,
                           reason="CAD 容器附件豁免: 弱负叠加降为灰区待复核")
    if score <= -1:
        return MailVerdict(kind="skip", score=score, positive=positive,
                           negative=strong_neg + weak_neg, cad_attachment=cad,
                           reason=f"非询价: 命中 {weak_neg}")
    return MailVerdict(kind="gray", score=0, positive=positive,
                       negative=strong_neg + weak_neg, cad_attachment=cad,
                       reason="灰区: 无明确信号, 待复核")


def should_process(
    verdict: MailVerdict,
    *,
    gray_zone_action: str = "skip_review",
    enabled: bool = True,
) -> bool:
    """判定 → 是否入黄金链. 灰区动作由策略决定 (默认 skip_review)."""
    if not enabled:
        return True
    if verdict.kind == "rfq":
        return True
    if verdict.kind == "gray":
        return gray_zone_action == "process"
    return False


def content_signature(from_: str, subject: str, body: str, limit: int = 8000) -> str:
    """内容指纹 (EDRM MIH 思路): 忽略 Message-ID/Date 等传输头, 只哈希
    (发件人, 主题, 正文前 limit 字符的归一化空白). 同一内容换个 UID 重投 → 同指纹."""
    norm = " ".join(f"{from_ or ''}\n{subject or ''}\n{(body or '')[:limit]}".split())
    return hashlib.sha256(norm.encode("utf-8", errors="ignore")).hexdigest()[:16]
