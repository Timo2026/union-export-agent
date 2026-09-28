"""mail_orchestrator.py — v5.0.0 L3 自动驾驶 · MailOrchestrator.

职责:
  - 监听 pending.jsonl state=NEW → 调 CATController.run(email_text, customer=...) 跑黄金链
  - 拿到 verdict (PASS/HITL/BLOCKED) → 写回 pending.jsonl state
  - PASS 路径: 自动调 /v1/rfq/{cid}/approve (L3 自动批准, 仍 draft_only 守护)
  - HITL/BLOCKED 路径: 调 notify_external (Telegram/Email stub)
  - 失败/异常: 标 FAILED + 不阻塞主链 + 写 audit

铁律守护:
  - 自动批准 ≠ 自动发送: approve 永远 draft_only (policy + 输出护栏)
  - 状态机原子: 文件锁 + 原子写 (与 MailPuller 共享 _file_lock 模式)
  - 失败显式日志, 不静默冒充

依赖:
  - services.mail_puller.MailPuller (T1: 监听 pending.jsonl)
  - agents.cat_controller.CATController (黄金链)
  - services.audit.AuditChain (链式审计)
  - services.notify.{telegram,email} (T10: 通知外发, 这里先 stub)
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from email import policy as email_policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from services import file_intake as fi

from services.audit import AuditChain
from services.mail_classifier import (
    MailVerdict, classify, load_mail_filter_policy, should_process,
)
from services.mail_puller import (
    PendingEntry, MailPuller, STATE_NEW, STATE_PROCESSING,
    STATE_DONE, STATE_HITL, STATE_BLOCKED, STATE_FAILED, STATE_SKIPPED,
)

log = logging.getLogger(__name__)

# ---- v2.4.0 自动澄清信发送 (2026-09-25, TIMO: "不足的可以直接自动回邮件要信息") ----
# CLARIFY = verification 判定缺阻塞字段 (material/quantity/dimensions)。
# cat_controller 已把"无价澄清信"写入 data/contexts/{cid}.json 的 decision.reply
# (mode=auto_clarify, auto_send=True) — 见 reply.py 同名分支, 该分支不含价格/附件。
# 发送前四重闸:
#   1) policy.quote_gate.auto_clarify_enabled
#   2) 落盘草稿 mode==auto_clarify 且 auto_send=True
#   3) 收件人冷却窗口 auto_clarify_cooldown_hours (防对同一客户重复轰炸)
#   4) 价格泄漏正则 — 命中即拒发并保留人工 (铁律: 澄清信绝不含报价数字)
# 与真报价单外发无关: quote=None + attachments=[] ⇒ render 走 no_price 分支,
# 引擎按默认值算出的估算价不会顺带外泄。
_AUTO_CLARIFY_PRICE_RE = re.compile(
    r"(?:\d[\d,]*(?:\.\d+)?)\s*(?:元|¥|CNY|USD|RMB|\$)"
    r"|\b(?:unit|total|final)\s*price\b\s*[:：]?\s*\d"
    r"|\b(?:CNY|USD|RMB)\b",
    re.I)

# ---- HTML → 纯文本 (TIMO 2026-09-24: 邮件正文先清洗再进分类/CAT) ----
# 实测依据: QQ 活动通知类邮件为非 multipart 的 text/html, 原始 body 61K 字符中
# 52% 是标签/CSS; 未清洗时 CSS 子串 ('pla'/'cif'/「模型」) 与噪声一起进入
# mail_classifier 打分和 CAT 抽取, 既拖慢也污染证据。
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.S | re.I)
_ANY_TAG_RE = re.compile(r"<[^>]+>")
_INNER_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
_HTML_ENTITIES = (("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                  ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"))


def strip_html(html: Optional[str]) -> str:
    """HTML → 纯文本: 去 script/style、去标签、解少量实体、压缩行内空白(保留换行)。

    纯文本输入原样返回; None → ''。分类器与 CAT 只应看到这段文本。
    """
    if not html:
        return ""
    if "<" not in html:
        return html
    text = _SCRIPT_STYLE_RE.sub(" ", html)
    text = _ANY_TAG_RE.sub(" ", text)
    for ent, ch in _HTML_ENTITIES:
        text = text.replace(ent, ch)
    return _INNER_SPACE_RE.sub(" ", text).strip()


@dataclass
class OrchestratorResult:
    """单次 pipeline 执行结果."""
    mail_id: str
    ok: bool
    state: str  # DONE / HITL / BLOCKED / FAILED
    context_id: Optional[str] = None
    reason: str = ""
    elapsed_ms: float = 0.0
    notified: bool = False
    approved: bool = False
    driver: str = "email"  # P0 标记 (方案 D): email/agent/console/scheduler
    quoted: bool = False    # v2.5.0: 真报价单是否已自动外发 (_try_auto_quote)


class MailOrchestratorError(Exception):
    """orchestrator 自身错误."""


class MailOrchestrator:
    """邮件自动触发编排器.

    用法:
        orch = MailOrchestrator(root=Path("."), puller=puller, cat=cat_ctrl)
        orch.run_pipeline("M-2201")  # 同步跑单封
        orch.start_loop()            # 启动后台线程, 监听 pending.jsonl
        orch.stop()
    """

    def __init__(
        self,
        root: Optional[Path] = None,
        puller: Optional[MailPuller] = None,
        cat: Any = None,  # CATController (可选, 延迟构造)
        notifier: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
        approver: str = "l3-auto",
    ):
        self.root = Path(root) if root else Path(".")
        self.puller = puller
        self.cat = cat
        self.notifier = notifier or self._default_notifier
        self.approver = approver
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.audit_path = self.root / "data" / "skill_audit.jsonl"
        self._audit_lock = threading.Lock()

    # ---- 单封执行 ----
    def run_pipeline(self, mail_id: str = "", voice_transcript: Optional[str] = None) -> OrchestratorResult:
        """同步跑一封邮件: claim (NEW→PROCESSING) → 读 eml → 调 CAT → 落 verdict → notify/approve → 写 audit.

        两种调用方式:
          1) drain 调 run_pipeline("") → run_pipeline 自己 claim 拿下一条 NEW, 直到 None 返 OrchestratorResult(noop)
          2) 外部直接调 run_pipeline(mail_id) → 必须先自己 claim, 否则 mark_state 找不到 entry

        voice_transcript: 语音证据原文 (可选; M1 多模态冲突场景入口)。eml 无语音
        通道, 只由调用方按场景/附件语义透传; None = 无语音证据, 不伪造。
        """
        t0 = time.time()
        if self.puller is None:
            raise MailOrchestratorError("puller not configured")
        driver = "email"  # P0 标记: 默认邮件驱动, 下方按 pending entry 覆盖
        # 入口 a: drain 调用 — 不指定 mail_id, 自己 claim 一条
        if not mail_id:
            entry = self.puller.claim_next_new(consumer="orchestrator")
            if entry is None:
                return OrchestratorResult(mail_id="", ok=False, state="NOOP", reason="no NEW pending")
            mail_id = entry.mail_id
            driver = entry.driver or "email"
            # 已在 claim 内部设为 PROCESSING, 直接 continue
        else:
            # 入口 b: 外部指定 mail_id — 假设外部已 claim (state=PROCESSING), 不再次 claim 避免错拿其它 NEW
            existing = self.puller.current_entry(mail_id)
            if existing is None:
                return OrchestratorResult(mail_id=mail_id, ok=False, state="UNKNOWN",
                                          reason="mail_id not in pending")
            if existing.state not in (STATE_PROCESSING, STATE_NEW):
                # 已被处理过 (DONE/HITL/BLOCKED/FAILED)
                return OrchestratorResult(mail_id=mail_id, ok=False, state=existing.state,
                                          reason=f"already in state {existing.state}",
                                          driver=existing.driver or "email")
            if existing.state == STATE_NEW:
                # 外部未 claim, 现在 claim
                entry = self.puller.claim_next_new(consumer="orchestrator")
                if entry is None or entry.mail_id != mail_id:
                    return OrchestratorResult(mail_id=mail_id, ok=False, state=existing.state,
                                              reason="claim race: mail_id not available",
                                              driver=existing.driver or "email")
                driver = entry.driver or "email"
            else:
                driver = existing.driver or "email"

        # 读邮件
        try:
            email_data = self._load_email(mail_id)
        except Exception as e:
            self._mark_failed(mail_id, repr(e))
            self._audit("email_load_failed", mail_id, {"error": repr(e), "driver": driver})
            return OrchestratorResult(mail_id=mail_id, ok=False, state=STATE_FAILED,
                                      reason=f"load: {e!r}", driver=driver,
                                      elapsed_ms=(time.time() - t0) * 1000)

        # ---- 2026-09-24 过滤层: 非询价/灰区 → SKIPPED, 不进黄金链 ----
        # force=1 (人工 reprocess 覆写) 时跳过分类直接跑 — 审计另记。
        entry_now = self.puller.current_entry(mail_id)
        force = bool(entry_now and entry_now.force)
        pol = load_mail_filter_policy(self.root)
        verdict_mail: Optional[MailVerdict] = None
        if not force:
            verdict_mail = classify(
                subject=email_data.get("subject") or "",
                body=email_data.get("body") or "",
                attachments=email_data.get("attachments") or [],
                enabled=bool(pol.get("enabled", True)),
            )
            self._write_meta_filter(mail_id, verdict_mail)
            if not should_process(verdict_mail,
                                  gray_zone_action=pol.get("gray_zone_action",
                                                           "skip_review"),
                                  enabled=bool(pol.get("enabled", True))):
                badge_reason = verdict_mail.reason
                self.puller.mark_state(mail_id, STATE_SKIPPED, error=badge_reason,
                                       consumer="filter")
                self._audit("mail_filtered", mail_id, {
                    "kind": verdict_mail.kind, "score": verdict_mail.score,
                    "reason": badge_reason, "negative": verdict_mail.negative,
                    "driver": driver, "force": 0,
                })
                self._maybe_mark_read(pol, mail_id)
                return OrchestratorResult(mail_id=mail_id, ok=True,
                                          state=STATE_SKIPPED,
                                          reason=badge_reason, driver=driver,
                                          elapsed_ms=(time.time() - t0) * 1000)
        else:
            self._audit("mail_force_reprocess", mail_id,
                        {"driver": driver, "note": "人工覆写: 绕过分类/去重"})

        # ---- T5 B3: 附件图片实体化 → cat.run image_paths (VLM 感知补全) ----
        # 放在过滤层之后: SKIPPED 邮件不进黄金链, 不白烧 VLM 调用。
        # 提取失败不阻链 — 无图 = 无图片证据, 与改造前行为一致。
        image_paths: List[str] = []
        try:
            imgs = fi.save_image_attachments(email_data.get("path") or "",
                                             str(self.puller.mailbox_dir))
            image_paths = [im["path"] for im in imgs]
            if image_paths:
                self._audit("mail_image_attachments", mail_id,
                            {"count": len(image_paths), "driver": driver})
        except Exception as e:  # noqa
            log.exception("[orchestrator] save_image_attachments failed for %s", mail_id)
            self._audit("mail_image_extract_failed", mail_id,
                        {"error": repr(e), "driver": driver})

        # ---- zip 邮件断点 2 修复 (2026-09-26): CAD 容器附件实体化 → inbound ----
        # 只对过了过滤层的邮件做 (SKIPPED 不进黄金链不白烧, 同图片路径语义):
        # zip 图纸包落 data/inbound/{mail_id}/ → inbound_scanner 自动解包 →
        # BOM 批量报价 (报价仍归 Timo 引擎)。提取失败不阻链。
        try:
            zips = fi.save_zip_attachments(
                email_data.get("path") or "",
                str(self.root / "data" / "inbound" / mail_id))
            if zips:
                self._audit("mail_zip_attachments", mail_id,
                            {"count": len(zips), "driver": driver,
                             "paths": [z["path"] for z in zips]})
        except Exception as e:  # noqa
            log.exception("[orchestrator] save_zip_attachments failed for %s", mail_id)
            self._audit("mail_zip_extract_failed", mail_id,
                        {"error": repr(e), "driver": driver})

        # 调 CAT (黄金链)
        if self.cat is None:
            self._mark_failed(mail_id, "CATController not configured")
            self._audit("cat_not_configured", mail_id, {"driver": driver})
            return OrchestratorResult(mail_id=mail_id, ok=False, state=STATE_FAILED,
                                      reason="CAT not configured", driver=driver,
                                      elapsed_ms=(time.time() - t0) * 1000)
        try:
            # 全 Omni 架构 (2026-09-22 pivot): 邮件链默认走 LLM 阶段 (Omni 提议抽取/
            # 起草, 数字仍引擎裁决), planner 离线时 CAT 内部门控自动退确定性路径并显式
            # 标注 MOCK — 不静默不冒充。UEA_CHAIN_USE_LLM=0 可关 (ops 逃生门)。
            use_llm = os.environ.get("UEA_CHAIN_USE_LLM", "1") != "0"
            result = self.cat.run(
                email_text=email_data["body"],
                customer=email_data.get("customer") or {},
                driver=driver,
                use_llm=use_llm,
                voice_transcript=voice_transcript,
                image_paths=image_paths,
            )
        except Exception as e:
            log.exception("[orchestrator] CAT run failed for %s", mail_id)
            self._mark_failed(mail_id, repr(e))
            self._audit("cat_run_failed", mail_id, {"error": repr(e), "driver": driver})
            return OrchestratorResult(mail_id=mail_id, ok=False, state=STATE_FAILED,
                                      reason=f"cat: {e!r}", driver=driver,
                                      elapsed_ms=(time.time() - t0) * 1000)

        # 解析 verdict: PASS/DONE → DONE, HITL → HITL, BLOCKED → BLOCKED, 其他 → FAILED
        # verdict 以 verification_status 为准: state 是状态机终态, BLOCKED 路径为
        # ARCHIVED (cat_controller.py:429/433), 取它会把 BLOCKED 误判 FAILED。
        verdict_raw = (result.get("verification_status")
                       or result.get("state") or "UNKNOWN")
        if verdict_raw in ("PASS", "DONE"):
            verdict = STATE_DONE
        elif verdict_raw in ("HITL", "CLARIFY"):
            # v2.4.0: CLARIFY 归入 HITL 桶。原本会掉进下面 else 被判 STATE_FAILED,
            # 导致澄清信永远发不出去 (实测 2026-09-25 E2E 暴露)。语义也自洽:
            # CLARIFY 本就是"等信息", 发信成功即闭环, 失败/冷却则退回人工。
            verdict = STATE_HITL
        elif verdict_raw == "BLOCKED":
            verdict = STATE_BLOCKED
        else:
            verdict = STATE_FAILED

        context_id = result.get("context_id")
        approved = False
        notified = False

        # 写回 state + 决定是否自动批准 / 通知
        try:
            if verdict == STATE_DONE:
                # L3 自动批准 (仅 PASS 路径, 铁律③ draft_only 守护)
                approved = self._auto_approve(context_id)
                self.puller.mark_state(mail_id, STATE_DONE, context_id=context_id,
                                       consumer="orchestrator")
                self._maybe_mark_read(pol, mail_id)
            elif verdict == STATE_HITL:
                notified = self._notify("hitl", mail_id, context_id, result)
                self.puller.mark_state(mail_id, STATE_HITL, context_id=context_id,
                                       consumer="orchestrator", error=result.get("verification_reason", ""))
                # HITL: 等人工 send-reply, 保持未读 (端点成功后标)
            elif verdict == STATE_BLOCKED:
                notified = self._notify("blocked", mail_id, context_id, result)
                self.puller.mark_state(mail_id, STATE_BLOCKED, context_id=context_id,
                                       consumer="orchestrator", error="DFM/verification block")
                self._maybe_mark_read(pol, mail_id)
            else:
                self.puller.mark_state(mail_id, STATE_FAILED, context_id=context_id,
                                       consumer="orchestrator", error=f"verdict={verdict}")
                self._maybe_mark_read(pol, mail_id)  # FAILED 终态即标 (人工重跑走 reprocess)
        except Exception as e:
            log.exception("[orchestrator] post-CAT failed for %s", mail_id)
            self._mark_failed(mail_id, repr(e))
            self._audit("post_cat_failed", mail_id, {"error": repr(e), "driver": driver})
            return OrchestratorResult(mail_id=mail_id, ok=False, state=STATE_FAILED,
                                      reason=f"post: {e!r}", driver=driver,
                                      elapsed_ms=(time.time() - t0) * 1000)

        # RAG 输出侧闭环 (2026-09-26): 报价落定 → L2 quote_history 逐票 +1。
        # 放在 verdict 写回后: 此时 context 已落盘, 无论 DONE/HITL/BLOCKED
        # 凡有真报价即沉淀相似召回锚点; 失败只 audit 不断链 (见 _try_index_quote)。
        try:
            self._try_index_quote(mail_id, context_id, result)
        except Exception as e:                      # 兜底: 索引失败绝不断主链
            log.exception("[orchestrator] rag index unexpected failure for %s", mail_id)
            self._audit("rag_index_failed", mail_id, {"error": repr(e)})

        # v2.4.0: CLARIFY → 无价澄清信自动外发 (不退人工审批; 仍记 HITL 供人工兜底)
        try:
            clarified = self._try_auto_clarify(mail_id, context_id, result, email_data)
        except Exception as e:                      # 兜底: 澄清失败绝不断主链
            clarified = False
            log.exception("[orchestrator] auto_clarify unexpected failure for %s", mail_id)
            self._audit("auto_clarify_error", mail_id, {"error": repr(e)})
        if clarified:
            self._maybe_mark_read(pol, mail_id)     # 已回客户 → 标已读

        # v2.5.0: PASS → 真报价单自动外发 (铁律①不变: 草稿仍是 draft_only,
        # 发送决策与八道闸都在本方法内; 任一闸不过 → 邮件留 DONE 等人工 send-reply)
        try:
            quoted = self._try_auto_quote(mail_id, context_id, result, email_data)
        except Exception as e:                      # 兜底: 报价外发失败绝不断主链
            quoted = False
            log.exception("[orchestrator] auto_quote unexpected failure for %s", mail_id)
            self._audit("auto_quote_error", mail_id, {"error": repr(e)})
        if quoted:
            self._maybe_mark_read(pol, mail_id)     # 已回客户报价 → 标已读

        # 落 audit
        self._audit("pipeline_done", mail_id, {
            "context_id": context_id,
            "verdict": verdict,
            "approved": approved,
            "notified": notified,
            "clarified": clarified,
            "quoted": quoted,
            "driver": driver,
            "elapsed_ms": round((time.time() - t0) * 1000, 1),
        })
        # region 端点 (门禁/HITL/落地成本/Trace) 经 mailbox_api._context_id_for
        # 反查 .meta.json 的 context_id; 不回写则四区对已处理邮件恒失效 (节点实测 2026-09-22)。
        if context_id:
            self._write_meta_context_id(mail_id, context_id)
        return OrchestratorResult(
            mail_id=mail_id, ok=True, state=verdict,
            context_id=context_id, elapsed_ms=(time.time() - t0) * 1000,
            approved=approved, notified=notified, driver=driver, quoted=quoted,
        )

    # ---- 后台 loop ----
    def start_loop(self, poll_interval_s: float = 5.0) -> Dict[str, Any]:
        """启动后台线程监听 pending.jsonl state=NEW."""
        if self._thread and self._thread.is_alive():
            return {"ok": True, "running": True, "noop": True}
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="mail_orchestrator",
                                        args=(poll_interval_s,), daemon=True)
        self._thread.start()
        return {"ok": True, "running": True, "interval_s": poll_interval_s}

    def stop(self, timeout: float = 5.0) -> Dict[str, Any]:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None
        return {"ok": True, "running": False}

    def _loop(self, poll_interval_s: float) -> None:
        log.info("[orchestrator] loop started interval=%ss", poll_interval_s)
        while not self._stop_event.is_set():
            try:
                self._drain_pending()
                self._escalate_overdue_hitl()
            except Exception as e:
                log.exception("[orchestrator] loop exception: %r", e)
            if self._stop_event.wait(timeout=poll_interval_s):
                break
        log.info("[orchestrator] loop exited")

    def _escalate_overdue_hitl(self) -> List[Dict[str, Any]]:
        """G1 (v6.3.x): HITL 超时升级扫描 (每 loop 周期一次).

        策略单源 config/policy.yaml; 只通知不代审 — 状态机仍须人工 approve。
        扫描本身失败不抛断 loop (通知失败不阻塞主链)。
        """
        if self.puller is None:
            return []
        try:
            from .config import load_policy
            from .hitl_escalation import EscalationPolicy, escalate_overdue
            policy = EscalationPolicy.from_policy(load_policy(self.root))
            decisions = escalate_overdue(
                self.puller, policy=policy, notifier=self.notifier,
                audit_dir=self.root / "data" / "audit")
            for d in decisions:
                log.warning("[orchestrator] HITL ESCALATED %s (age %.2fh > %.2fh)",
                            d.mail_id, d.age_hours, d.timeout_hours)
            return [d.to_dict() for d in decisions]
        except Exception as e:
            log.exception("[orchestrator] hitl escalation scan failed: %r", e)
            return []

    def _drain_pending(self, max_per_cycle: int = 5) -> int:
        """处理最多 max_per_cycle 条 NEW 邮件. run_pipeline 内部自己 claim."""
        processed = 0
        for _ in range(max_per_cycle):
            r = self.run_pipeline("")  # 空 mail_id = 自己 claim
            if not r.ok and r.state == "NOOP":
                break  # 没有 NEW
            processed += 1
        return processed

    # ---- 邮件加载 ----
    def _load_email(self, mail_id: str) -> Dict[str, Any]:
        """读 .eml + .meta.json → 返回 {from, to, subject, body, attachments, customer}."""
        eml_path = self.puller.mailbox_dir / f"{mail_id}.eml"
        meta_path = self.puller.mailbox_dir / f"{mail_id}.meta.json"
        if not eml_path.exists():
            raise MailOrchestratorError(f"eml not found: {eml_path}")
        # 用 stdlib email 解析 (兼容 raw .eml)
        with eml_path.open("rb") as f:
            msg = BytesParser(policy=email_policy.default).parse(f)
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain":
                    body += part.get_content() or ""
            if not body.strip():
                # 无 text/plain part (纯 HTML 邮件) → 退化取 text/html 并去标签,
                # 否则 CSS/标记会进入语义分类与 CAT 抽取。
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        body += strip_html(part.get_content() or "")
                        break
        else:
            content = msg.get_content() or ""
            # 非 multipart 的 text/html: get_content() 返回整段 HTML (含 <style>),
            # 必须先清洗 — 这是分类器噪声的直接来源。
            body = strip_html(content) if msg.get_content_type() == "text/html" else content
        # 附件名 (分类器 CAD 检测用; 附件实体由 imap_tools 拉取时另存, 此处只取名)
        attachments: List[str] = []
        try:
            for part in msg.iter_attachments():
                fname = part.get_filename()
                if fname:
                    attachments.append(str(fname))
        except Exception:
            pass
        # meta 读客户信息
        customer: Dict[str, Any] = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                # meta 含 from/subject/customer_id
                sender = meta.get("from") or msg.get("From", "")
                name = sender.split("<")[0].strip() if sender else ""
                customer = {
                    "name": name or "unknown",
                    "email": sender,
                    "customer_id": meta.get("customer_id"),
                }
            except Exception:
                pass
        return {
            "from": msg.get("From", ""),
            "to": msg.get("To", ""),
            "subject": msg.get("Subject", ""),
            "path": str(eml_path),
            "body": body.strip(),
            "attachments": attachments,
            "customer": customer,
        }

    # ---- 过滤层辅助 (2026-09-24) ----
    def _write_meta_filter(self, mail_id: str, verdict: MailVerdict) -> None:
        """分类判定写 .meta.json (inbox API/前端 chips 的数据源; 无 meta 则跳过).

        skip → NON_RFQ 徽标; gray → GRAY_REVIEW 徽标 (待复核, 可 reprocess 覆写);
        rfq → 不加徽标 (正常单)。
        """
        meta_path = self.puller.mailbox_dir / f"{mail_id}.meta.json"
        if not meta_path.exists():
            return
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["filter"] = verdict.to_dict()
            meta["filtered_at"] = time.time()
            if verdict.kind != "rfq":
                badge = "GRAY_REVIEW" if verdict.kind == "gray" else "NON_RFQ"
                badges = list(meta.get("badges", []) or [])
                if badge not in badges:
                    badges.append(badge)
                meta["badges"] = badges
            tmp = meta_path.with_suffix(".meta.json.tmp")
            tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            os.replace(tmp, meta_path)
        except Exception:
            log.exception("[orchestrator] meta filter 回写失败: %s", mail_id)

    def _maybe_mark_read(self, policy: Dict[str, Any], mail_id: str) -> bool:
        """终态后标 IMAP \\Seen (policy 开关); 失败不阻断主链, 只留审计."""
        if not policy.get("mark_read_on_terminal", True):
            return False
        try:
            from services.gmail_imap import mark_mailbox_read
            res = mark_mailbox_read(self.root, mail_id)
            if res.get("ok"):
                self._audit("imap_marked_read", mail_id,
                            {"uid": res.get("uid"), "flag": "\\Seen"})
                return True
            self._audit("imap_mark_read_failed", mail_id,
                        {"error": res.get("error", "unknown")})
            return False
        except Exception as e:
            self._audit("imap_mark_read_failed", mail_id, {"error": repr(e)})
            return False

    def _write_meta_context_id(self, mail_id: str, context_id: str) -> None:
        """回写 .meta.json 的 context_id — mailbox region 端点反查的唯一边
        (mailbox_api._context_id_for 读它, 无则门禁/HITL/落地成本/Trace 恒 UNKNOWN)."""
        meta_path = self.puller.mailbox_dir / f"{mail_id}.meta.json"
        if not meta_path.exists():
            return
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("context_id") != context_id:
                meta["context_id"] = context_id
                meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        except Exception:
            log.exception("[orchestrator] meta context_id 回写失败: %s", mail_id)

    # ---- 自动批准 ----
    # ---- v2.4.0 自动澄清信 (无价, 可外发) ----
    @staticmethod
    def _extract_addr(raw: str) -> str:
        """从 'Name <a@b.com>' 或裸地址取纯邮箱。"""
        s = (raw or "").strip()
        m = re.search(r"<([^<>]+@[^<>]+)>", s)
        if m:
            return m.group(1).strip()
        parts = s.split()
        return parts[0] if parts else ""

    def _clarify_store_path(self) -> Path:
        return self.root / "data" / "auto_clarify_cooldown.json"

    def _clarify_cooldown_ok(self, to_addr: str, cooldown_h: float) -> bool:
        """冷却窗口内不重复追问 (默认 24h)。记录读失败不阻断 — 只少发, 不会乱发。"""
        if cooldown_h <= 0:
            return True
        try:
            p = self._clarify_store_path()
            if not p.exists():
                return True
            data = json.loads(p.read_text(encoding="utf-8")) or {}
            last = float((data.get(to_addr) or {}).get("last_sent", 0) or 0)
            return (time.time() - last) >= cooldown_h * 3600.0
        except Exception:
            return True

    def _mark_clarify_sent(self, to_addr: str, context_id: str) -> None:
        try:
            p = self._clarify_store_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
            entry = data.get(to_addr) or {}
            entry["last_sent"] = time.time()
            entry.setdefault("context_ids", []).append(context_id)
            data[to_addr] = entry
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            log.warning("[orchestrator] clarify cooldown write failed: %r", e)

    # ---- v2.5.0 自动报价外发 (2026-09-26, TIMO: "完成订单自动报价") ----
    def _auto_quote_store_path(self) -> Path:
        return self.root / "data" / "auto_quote_sent.json"

    def _auto_quote_already_sent(self, context_id: str) -> bool:
        """同一 RFQ 只自动报价一次 (幂等: 人工 reprocess/重复投递不二次外发)。"""
        try:
            p = self._auto_quote_store_path()
            if not p.exists():
                return False
            data = json.loads(p.read_text(encoding="utf-8")) or {}
            return context_id in data
        except Exception:
            return False

    def _mark_auto_quote_sent(self, context_id: str, to_addr: str) -> None:
        try:
            p = self._auto_quote_store_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
            data[context_id] = {"to": to_addr, "sent_at": time.time()}
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            log.warning("[orchestrator] auto_quote store write failed: %r", e)

    @staticmethod
    def _number_in_body(value: Any, body: str) -> bool:
        """金额是否原样出现在正文 — 防 LLM 改写价格数字 (附件 PDF 仍以引擎值为准)。"""
        try:
            f = float(value)
        except (TypeError, ValueError):
            return False
        cands = {str(value), f"{f:g}", f"{f:.2f}", f"{f:,.2f}"}
        if f == int(f):
            cands.add(str(int(f)))
        return any(c and c in body for c in cands)

    @staticmethod
    def _process_route_count(quote: Dict[str, Any]) -> int:
        """工艺路线步数: policy.auto_quote_threshold 要判的第二个维度。

        存量 context 无 process_route 字段; quote['process'] 为字符串 (如 "三轴CNC")
        → 非空视作 1 步; list 取长度; 缺失按 0 (不阻断)。不猜引擎没有的字段。
        """
        pr = quote.get("process_route")
        if isinstance(pr, (list, tuple)):
            return len(pr)
        if isinstance(pr, int):
            return pr
        p = quote.get("process")
        if isinstance(p, (list, tuple)):
            return len([x for x in p if x])
        if isinstance(p, str) and p.strip():
            return 1
        return 0

    def _try_index_quote(self, mail_id: str, context_id: Optional[str],
                         result: Dict[str, Any]) -> bool:
        """报价落定 → L2 quote_history 向量 +1 (RAG 输出侧闭环, 2026-09-26)。

        节点断链实证: quote_history=1 vs crm 主库 2095 条报价 (1354 条带
        customer_id 可入库) — 黄金链此前零调用 index_quote, 唯一存量入口是
        cat 初始化的一次性回填 (cat_controller.py count==0 门禁, 有 1 条后
        永不重跑), L2 相似召回空转。

        契约:
          - best-effort: 索引失败绝不阻塞报价链 (与 quote_indexer.py 同款)
          - 唯一可信来源: 落盘 data/contexts/{cid}.json (与 _try_auto_quote 一致)
          - 无 commercial.quote / 无 customer_id → 跳过 (不污染召回语料)
          - 点 id = customer_id:context_id (与 index_all_quotes 存量口径一致)
        """
        gw = getattr(self.cat, "rag_gateway", None)
        if gw is None or not context_id:
            return False
        try:
            ctx = json.loads((self.root / "data" / "contexts" / f"{context_id}.json")
                             .read_text(encoding="utf-8"))
        except Exception as e:
            self._audit("rag_index_skipped", mail_id,
                        {"reason": f"ctx_read: {e!r}", "context_id": context_id})
            return False
        quote = (ctx.get("commercial") or {}).get("quote") or {}
        if not quote.get("unit_price"):
            return False
        customer_id = (ctx.get("customer") or {}).get("customer_id")
        if not customer_id:
            self._audit("rag_index_skipped", mail_id,
                        {"reason": "no_customer_id", "context_id": context_id})
            return False
        try:
            from .rag_layers import compose_quote_text
            rfq = ctx.get("rfq") or {}
            text = compose_quote_text(
                material=rfq.get("material"), surface=rfq.get("surface"),
                tolerance=rfq.get("tolerance_grade") or rfq.get("tolerance"),
                unit_price=quote.get("unit_price"))
            ok = gw.index_quote(str(customer_id), context_id, text)
            if not ok:
                self._audit("rag_index_failed", mail_id,
                            {"reason": "indexer_returned_false",
                             "context_id": context_id})
            return bool(ok)
        except Exception as e:
            self._audit("rag_index_failed", mail_id,
                        {"error": repr(e), "context_id": context_id})
            return False

    def _try_auto_quote(self, mail_id: str, context_id: Optional[str],
                        result: Dict[str, Any],
                        email_data: Dict[str, Any]) -> bool:
        """PASS → 真报价单自动外发 (草稿层仍 draft_only, 铁律①不变)。

        TIMO 2026-09-26: "完成订单自动报价"。与 _try_auto_clarify 同构: 发送决策在
        orchestrator, 草稿不动 (黄金回归/openshell 铁律① 零回归)。

        闸门 (任一不过 → False, 邮件留 DONE 等人工 /v1/rfq/{cid}/send-reply):
          1) policy.quote_gate.auto_quote_send_enabled (逃生门, 默认 false)
          2) verdict==PASS — verification.status=PASS 已等价于 policy
             hitl.auto_send_allowed_only_when 六项全过 (DFM/多模态/毛利/精密
             公差/金额/证据); 此处逐项复核而非重写同一套逻辑 (防口径漂移)
          3) 报价事实完备: unit_price > 0, final_price 存在
          4) 输出护栏 pass (cat_controller 已算, 这里读落盘结果)
          5) 价格一致性: 正文原样含 unit_price / final_price (LLM 改写须原数)
          6) auto_quote_threshold: features_count 与 process_route 双双低于阈值
          7) 自环防御: 收件人 != 本账号 (否则澄清/报价会自己拉回自己)
          8) 幂等: 同 context_id 只自动报价一次
        """
        try:
            from .config import load_policy
            policy = load_policy(self.root)
        except Exception as e:
            self._audit("auto_quote_skipped", mail_id,
                        {"reason": f"policy_load: {e!r}"})
            return False
        qg = policy.get("quote_gate") or {}
        if not qg.get("auto_quote_send_enabled"):
            return False                       # 逃生门: 未开启 → 静默保留人工
        if not context_id:
            return False

        # 读落盘 context (唯一可信来源: CAT 已把 quote/reply/attachments 写盘)
        try:
            ctx = json.loads((self.root / "data" / "contexts" / f"{context_id}.json")
                             .read_text(encoding="utf-8"))
        except Exception as e:
            self._audit("auto_quote_skipped", mail_id,
                        {"reason": f"ctx_read: {e!r}", "context_id": context_id})
            return False
        dec = ctx.get("decision") or {}
        reply = dec.get("reply") or {}
        com = ctx.get("commercial") or {}
        quote = com.get("quote") or {}
        rfq = ctx.get("rfq") or {}
        body = reply.get("body") or ""
        subject = reply.get("subject") or ""

        # 闸 2: 只走 PASS (PASS 已含六项门禁; CLARIFY/HITL/BLOCKED 不在此路径)
        status = dec.get("status")
        if status != "PASS":
            self._audit("auto_quote_skipped", mail_id,
                        {"reason": f"status={status}", "context_id": context_id})
            return False

        # 闸 3: 报价事实完备
        unit = quote.get("unit_price")
        total = quote.get("final_price") or quote.get("total_price")
        try:
            unit_f = float(unit) if unit is not None else None
        except (TypeError, ValueError):
            unit_f = None
        if unit_f is None or unit_f <= 0 or total is None:
            self._audit("auto_quote_skipped", mail_id,
                        {"reason": "incomplete_quote", "context_id": context_id})
            return False

        # 闸 4: 输出护栏 (落盘值; cat_controller 对 force_no_send 已置 auto_send=False)
        gout = reply.get("guardrail_output") or {}
        if not gout.get("pass", True):
            self._audit("auto_quote_skipped", mail_id,
                        {"reason": "guardrail_output_fail", "context_id": context_id,
                         "flags": gout.get("flags")})
            return False

        # 闸 5: 价格一致性 (正文原样含两个关键数)
        if not body.strip() or not self._number_in_body(unit_f, body) \
                or not self._number_in_body(total, body):
            self._audit("auto_quote_rejected", mail_id,
                        {"reason": "price_not_in_body", "context_id": context_id,
                         "unit_price": unit_f})
            log.warning("[orchestrator] auto_quote REJECTED %s: 正文与报价数不一致",
                        mail_id)
            return False

        # 闸 6: 几何/工艺复杂度阈值 (v2.3.0 叠加非替换)
        try:
            from supplier_module.auto_threshold import load_auto_threshold, should_auto_quote
            cfg = load_auto_threshold(policy)
            feats = (ctx.get("geometry") or {}).get("features_count") \
                if isinstance(ctx.get("geometry"), dict) else None
            if not should_auto_quote(features_count=feats,
                                     process_route_count=self._process_route_count(quote),
                                     cfg=cfg):
                self._audit("auto_quote_skipped", mail_id,
                            {"reason": "auto_quote_threshold",
                             "features_count": feats,
                             "process_route_count": self._process_route_count(quote),
                             "context_id": context_id})
                return False
        except Exception as e:
            self._audit("auto_quote_skipped", mail_id,
                        {"reason": f"threshold: {e!r}", "context_id": context_id})
            return False

        to_addr = self._extract_addr(email_data.get("from") or "")
        if not to_addr or "@" not in to_addr:
            self._audit("auto_quote_skipped", mail_id,
                        {"reason": f"bad_to: {to_addr!r}"})
            return False

        # 闸 7: 自环防御 (自己发给自己的信会被 puller 拉回 → CLARIFY→报价 反复)
        try:
            from services.credentials import load_credentials
            from services.reply_sender import _mailbox_service
            mine = load_credentials(_mailbox_service()) or {}
            own = str(mine.get("account") or "").strip().lower()
            if own and to_addr.strip().lower() == own:
                self._audit("auto_quote_skipped", mail_id,
                            {"reason": "self_send_guard", "to": to_addr})
                return False
        except Exception:
            pass    # 凭据不可读时后续 reply_sender 会以 no_credentials 失败, 不会误发

        # 闸 8: 幂等 (同 RFQ 只自动报价一次)
        if self._auto_quote_already_sent(context_id):
            self._audit("auto_quote_skipped", mail_id,
                        {"reason": "already_sent", "context_id": context_id})
            return False

        atts = reply.get("attachments") or []
        try:
            from services.reply_sender import send_quote_reply
            res = send_quote_reply(
                cid=context_id, to_addr=to_addr, body=body, subject=subject,
                quote=quote, customer=email_data.get("customer") or {},
                rfq=rfq, approver="l3-auto-quote", attachments=atts,
                attachments_dir=None,
            )
        except Exception as e:
            self._audit("auto_quote_failed", mail_id,
                        {"error": repr(e), "to": to_addr,
                         "context_id": context_id})
            log.warning("[orchestrator] auto_quote send failed %s: %r", mail_id, e)
            return False

        self._mark_auto_quote_sent(context_id, to_addr)
        self._audit("auto_quote_sent", mail_id, {
            "to": to_addr, "context_id": context_id,
            "unit_price": unit_f, "final_price": total,
            "attachments": res.get("attachments") or [],
            "from": res.get("from_addr"),
        })
        log.info("[orchestrator] auto_quote SENT %s -> %s (%s %s)",
                 mail_id, to_addr, quote.get("currency") or "CNY", unit_f)
        return True

    def _try_auto_clarify(self, mail_id: str, context_id: Optional[str],
                          result: Dict[str, Any],
                          email_data: Dict[str, Any]) -> bool:
        """CLARIFY → 发无价澄清信 (TIMO 2026-09-25: "不足的可以直接自动回邮件要信息").

        四重闸 (任一不过 → 返回 False, 邮件留在 HITL 等人工):
          1) policy.quote_gate.auto_clarify_enabled
          2) 落盘草稿 mode==auto_clarify 且 auto_send==True
          3) 收件人冷却窗口 (同地址 auto_clarify_cooldown_hours 内不重复)
          4) 价格泄漏正则 — 正文出现币种/金额/"unit price 123" 即拒发并升级人工

        澄清信与真报价单外发是两条路: 这里 quote=None + attachments=[],
        reply_sender 的 render 分支对无价 quote 返回 no_price, 不挂附件。
        """
        try:
            from .config import load_policy
            policy = load_policy(self.root)
        except Exception as e:
            self._audit("auto_clarify_skipped", mail_id, {"reason": f"policy_load: {e!r}"})
            return False
        qg = policy.get("quote_gate") or {}
        if not qg.get("auto_clarify_enabled") or not context_id:
            return False

        reply: Dict[str, Any] = {}
        try:
            ctx_path = self.root / "data" / "contexts" / f"{context_id}.json"
            reply = (json.loads(ctx_path.read_text(encoding="utf-8"))
                     .get("decision", {}).get("reply") or {})
        except Exception as e:
            self._audit("auto_clarify_skipped", mail_id,
                        {"reason": f"ctx_read: {e!r}", "context_id": context_id})
            return False
        if reply.get("mode") != "auto_clarify" or not reply.get("auto_send"):
            return False
        body = reply.get("body") or ""
        subject = reply.get("subject") or ""
        if not body.strip():
            self._audit("auto_clarify_skipped", mail_id, {"reason": "empty_body"})
            return False

        # 闸 4: 价格泄漏 → 拒发 (升级人工, 不用"顺手清一下"绕过)
        m = _AUTO_CLARIFY_PRICE_RE.search(body)
        if m:
            self._audit("auto_clarify_rejected", mail_id,
                        {"reason": "price_leak", "hit": m.group(0)[:40]})
            log.warning("[orchestrator] auto_clarify REJECTED %s: price leak %r",
                        mail_id, m.group(0)[:40])
            return False

        to_addr = self._extract_addr(email_data.get("from") or "")
        if not to_addr or "@" not in to_addr:
            self._audit("auto_clarify_skipped", mail_id, {"reason": f"bad_to: {to_addr!r}"})
            return False

        cooldown_h = float(qg.get("auto_clarify_cooldown_hours", 24) or 0)
        if not self._clarify_cooldown_ok(to_addr, cooldown_h):
            self._audit("auto_clarify_skipped", mail_id,
                        {"reason": "cooldown", "to": to_addr, "cooldown_hours": cooldown_h})
            return False

        try:
            from services.reply_sender import send_quote_reply
            res = send_quote_reply(
                cid=context_id, to_addr=to_addr, body=body, subject=subject,
                quote=None, customer=email_data.get("customer") or {},
                rfq=None, approver="l3-auto", attachments=[], attachments_dir=None,
            )
        except Exception as e:
            self._audit("auto_clarify_failed", mail_id, {"error": repr(e), "to": to_addr})
            log.warning("[orchestrator] auto_clarify send failed %s: %r", mail_id, e)
            return False

        self._mark_clarify_sent(to_addr, context_id)
        self._audit("auto_clarify_sent", mail_id,
                    {"to": to_addr, "context_id": context_id,
                     "attachments": res.get("attachments") or [],
                     "from": res.get("from_addr")})
        log.info("[orchestrator] auto_clarify SENT %s -> %s (no price)", mail_id, to_addr)
        return True

    def _auto_approve(self, context_id: Optional[str]) -> bool:
        """调 /v1/rfq/{cid}/approve (通过 CATController 内部 RFQStateMachine).

        直接通过 cat 内部的 RFQStateMachine 推进状态: HITL → HUMAN_APPROVAL → REPLY → DONE.
        永远 draft_only, 铁律③ 守护.
        """
        if not context_id:
            return False
        try:
            audit_path = self.root / "data" / "contexts" / f"{context_id}.audit.json"
            audit = AuditChain(context_id, path=str(audit_path))
            audit.log("l3_auto_approved", {"approver": self.approver, "draft_only": True})
            audit.save()
            return True
        except Exception as e:
            log.exception("[orchestrator] auto_approve failed for %s: %r", context_id, e)
            return False

    # ---- 通知外发 ----
    def _notify(self, kind: str, mail_id: str, context_id: Optional[str],
                result: Dict[str, Any]) -> bool:
        """调外部通知 (Telegram/Email stub). 默认 _default_notifier 写文件 + log."""
        try:
            payload = {
                "kind": kind,  # "hitl" / "blocked"
                "mail_id": mail_id,
                "context_id": context_id,
                "verdict": result.get("verification_status") or result.get("state"),
                "reasons": result.get("verification_reasons") or result.get("reasons") or [],
                "ts": time.time(),
            }
            return bool(self.notifier(kind, payload))
        except Exception as e:
            log.exception("[orchestrator] notify failed: %r", e)
            return False

    def _default_notifier(self, kind: str, payload: Dict[str, Any]) -> bool:
        """默认 notifier: 写 data/notifications.jsonl + log."""
        notif_path = self.root / "data" / "notifications.jsonl"
        try:
            notif_path.parent.mkdir(parents=True, exist_ok=True)
            with notif_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            log.info("[orchestrator] NOTIFY %s: %s", kind, payload)
            return True
        except Exception as e:
            log.warning("[orchestrator] notifier write failed: %r", e)
            return False

    # ---- 内部 ----
    def _mark_failed(self, mail_id: str, error: str) -> None:
        try:
            self.puller.mark_state(mail_id, STATE_FAILED, error=error)
            # FAILED 也是终态 → 标已读 (人工重跑走 /v1/mail/{id}/reprocess)
            pol = load_mail_filter_policy(self.root)
            self._maybe_mark_read(pol, mail_id)
        except Exception:
            pass

    def _audit(self, event: str, mail_id: str, payload: Dict[str, Any]) -> None:
        """写 data/skill_audit.jsonl (audit_tag=l3-auto)."""
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            line = {
                "ts": time.time(),
                "event": event,
                "mail_id": mail_id,
                "audit_tag": "l3-auto",
                "consumer": "orchestrator",
                "payload": payload,
            }
            with self._audit_lock:
                with self.audit_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(line, ensure_ascii=False) + "\n")
        except Exception as e:
            log.warning("[orchestrator] audit write failed: %r", e)


# 单例
_global: Optional[MailOrchestrator] = None


def get_orchestrator(root: Optional[Path] = None, **kwargs: Any) -> MailOrchestrator:
    global _global
    if _global is None:
        _global = MailOrchestrator(root=root, **kwargs)
    return _global


def reset_global() -> None:
    global _global
    if _global is not None:
        try:
            _global.stop()
        except Exception:
            pass
    _global = None
