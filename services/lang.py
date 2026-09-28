"""lang.py — 语种探测与业务模板 (多语言回复 P0-B)

数据源优先级 (审计结论: rfq.country 在 388 个 context 中恒为空, 不可依赖):
  1. 正文语种探测 (字符集 + 商务礼貌语特征)
  2. 邮箱域名 TLD 兜底 (.de→DE, .cn→ZH, .es→ES, 默认 EN)

铁律③: 本模块只提供措辞模板与字段名, 不含任何价格/交期数字。
        数字一律由调用方从确定性引擎 digest 注入。
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

SUPPORTED = ("de", "en", "es", "zh")

# ---- 语种特征 ----
# 德语: 变音/ß + 高频商务礼貌语 (询盘开头几乎固定)
_DE_MARKERS = ("sehr geehrte", "damen und herren", "mit freundlichen",
               "wir benötigen", "wir benoetigen", "benötigen", "benoetigen",
               "stück", "stueck", "anhang", "anhängend", "grüße", "grueße",
               "ihnen", "bitte um", "angebot", "zeichnung")
# 西班牙语: 变音 + 特有倒问号/词
_ES_MARKERS = ("estimados", "estimadas", "saludos", "atentamente",
               "necesitamos", "solicitamos", " adjunto", "presupuesto",
               "favor de", "gracias")
# 中文
_ZH_RE = re.compile(r"[\u4e00-\u9fff]")
# 拉丁变音 (de/es 通用初筛)
_DIA_RE = re.compile(r"[äöüñáéíóú¿¡ß]")


def detect_language(text: str = "", email: str = "", country: str = "") -> str:
    """返回 SUPPORTED 之一。探测失败默认 'en' (商务保守默认)。"""
    # 0) 显式 country / TLD 优先 (最可信)
    c = (country or "").strip().upper()
    # CH 已移除: 瑞士可能是 de/fr/it, TLD 无法判定, 落安全默认 en
    tld_map = {"DE": "de", "ES": "es", "CN": "zh", "AT": "de"}
    if c in tld_map:
        return tld_map[c]

    t = (text or "").strip()
    if t:
        low = t.lower()
        # 中文: 只要有汉字即判中文 (含中英混排)
        if _ZH_RE.search(t):
            return "zh"
        # 德语: 标记词命中数最多者胜
        de_hits = sum(1 for m in _DE_MARKERS if m in low)
        es_hits = sum(1 for m in _ES_MARKERS if m in low)
        if de_hits and de_hits >= es_hits:
            return "de"
        if es_hits and es_hits > de_hits:
            return "es"
        # 无商务词但有变音: 区分 äöüß(de) vs áéíóúñ(es)
        if _DIA_RE.search(t):
            if re.search(r"[äöüß]", t):
                return "de"
            if re.search(r"[áéíóúñ¿¡]", t):
                return "es"

    # 1) 邮箱域名 TLD 兜底
    m = re.search(r"@([\w.-]+)", email or "")
    if m:
        host = m.group(1).lower()
        # 注意: tld_map 键为大写, 必须 .upper() 后比对 (修过的 Bug: 原实现
        # 直接拿小写 tail 比大写键, 导致所有 TLD 兜底静默失效)
        tail = host.rsplit(".", 1)[-1].upper() if "." in host else ""
        if tail in tld_map:
            return tld_map[tail]
    return "en"


# ---- 字段标签 (四语种) ----
LABELS: Dict[str, Dict[str, str]] = {
    "material":       {"de": "Werkstoff", "en": "Material", "es": "Material", "zh": "材料"},
    "quantity":       {"de": "Stückzahl", "en": "Quantity", "es": "Cantidad", "zh": "数量"},
    "quantity_unit":  {"de": "Stk.", "en": "pcs", "es": "uds.", "zh": "件"},
    "surface":        {"de": "Oberfläche", "en": "Surface finish", "es": "Acabado superficial", "zh": "表面处理"},
    "tolerance":      {"de": "Toleranz", "en": "Tolerance", "es": "Tolerancia", "zh": "公差"},
    "unit_price":     {"de": "Stückpreis", "en": "Unit price", "es": "Precio unitario", "zh": "单价"},
    "total":          {"de": "Gesamtpreis", "en": "Total", "es": "Total", "zh": "总价"},
    "lead_time":      {"de": "Lieferzeit", "en": "Lead time", "es": "Plazo de entrega", "zh": "交期"},
    "days":           {"de": "Tage", "en": "days", "es": "días", "zh": "天"},
    "greeting":       {"de": "Sehr geehrte Damen und Herren", "en": "Dear customer", "es": "Estimados señores:", "zh": "尊敬的客户"},
    "thanks":         {"de": "vielen Dank für Ihre Anfrage", "en": "Thank you for your inquiry", "es": "gracias por su consulta", "zh": "感谢您的询盘"},
    "pleased":        {"de": "wir unterbreiten Ihnen folgendes Angebot", "en": "we are pleased to quote as follows", "es": "tenemos el agrado de cotizar", "zh": "我们很乐意为您报价如下"},
    "estimate_note":  {"de": "Diese Schätzung wurde von unserem deterministischen Fertigungssystem erstellt [{src}]; 14 Tage gültig, vorbehaltlich der endgültigen Zeichnungsfreigabe.",
                       "en": "Estimate produced by our deterministic manufacturing engine [{src}]; valid 14 days, subject to final drawing confirmation.",
                       "es": "Estimación generada por nuestro motor de fabricación determinista [{src}]; válida 14 días, sujeta a confirmación final del plano.",
                       "zh": "本报价由我方确定性制造引擎生成 [{src}]；有效期 14 天，以最终图纸确认为准。"},
    "regards":        {"de": "Mit freundlichen Grüßen\nUnion Export Sales Engineering",
                       "en": "Best regards,\nUnion Export Sales Engineering",
                       "es": "Atentamente,\nUnion Export Sales Engineering",
                       "zh": "此致\nUnion Export 销售工程部"},
    "review_reason":  {"de": "Ihre Anfrage befindet sich in technischer/kaufmännischer Prüfung ({reasons}). Wir melden uns in Kürze mit einem verbindlichen Angebot.",
                       "en": "Your request is currently under engineering/commercial review ({reasons}). We will revert with a firm quotation shortly.",
                       "es": "Su consulta está en revisión técnica/comercial ({reasons}). Le responderemos a la brevedad con una cotización firme.",
                       "zh": "您的需求正在技术/商务审核中（{reasons}）。我们将尽快提供正式报价。"},
    "pricing_follow": {"de": "Preisgestaltung folgt.", "en": "Pricing to follow.", "es": "Precio a confirmar.", "zh": "价格稍后确认。"},
    "quote_subject":  {"de": "Angebot — {mat} {qty} {qu}", "en": "Quotation — {mat} {qty} pcs", "es": "Cotización — {mat} {qu} {qty}", "zh": "报价 — {mat} {qty}件"},
    "review_subject": {"de": "Ihre Anfrage — in Prüfung", "en": "Your inquiry — under review", "es": "Su consulta — en revisión", "zh": "您的询盘 — 审核中"},
    "clarify_subject":{"de": "Rückfrage zu Ihrer Anfrage — {ctx}", "en": "Clarification needed for your inquiry — {ctx}", "es": "Aclaración sobre su consulta — {ctx}", "zh": "关于您的询盘 — 需补充信息"},

    # ---- 苏格拉底五要素追问 (P0-C) ----
    "clarify_intro":  {"de": "Damit wir Ihnen ein verbindliches Angebot erstellen können, benötigen wir noch folgende Angaben:",
                       "en": "To prepare a firm quotation, we still need the following details:",
                       "es": "Para preparar una cotización firme, necesitamos los siguientes datos:",
                       "zh": "为便于我们出具正式报价，还需请您补充以下信息："},
    "clarify_outro":  {"de": "Sobald uns diese Angaben vorliegen, erstellen wir umgehend ein Angebot.",
                       "en": "Once we have these details, we will issue a quotation without delay.",
                       "es": "En cuanto recibamos estos datos, emitiremos la cotización de inmediato.",
                       "zh": "收到上述信息后，我们将立即为您报价。"},
    "elem_material":  {"de": "Werkstoff (z. B. Aluminium 6061, Edelstahl 304)",
                       "en": "Material (e.g. aluminium 6061, stainless 304)",
                       "es": "Material (p. ej. aluminio 6061, acero inoxidable 304)",
                       "zh": "材料（如铝 6061、不锈钢 304）"},
    "elem_quantity":  {"de": "Stückzahl", "en": "Quantity", "es": "Cantidad", "zh": "数量"},
    "elem_dimensions":{"de": "Abmessungen oder beigefügte Zeichnung (STEP/DWG/PDF)",
                       "en": "Dimensions or attached drawing (STEP/DWG/PDF)",
                       "es": "Dimensiones o plano adjunto (STEP/DWG/PDF)",
                       "zh": "尺寸或附图（STEP/DWG/PDF）"},
    "elem_surface":   {"de": "Oberflächenbehandlung (z. B. Eloxieren, Passivieren)",
                       "en": "Surface finish (e.g. anodising, passivation)",
                       "es": "Acabado superficial (p. ej. anodizado, pasivado)",
                       "zh": "表面处理（如阳极氧化、钝化）"},
    "elem_tolerance": {"de": "Toleranzklasse (z. B. IT7) und Rauheit (z. B. Ra 1.6)",
                       "en": "Tolerance grade (e.g. IT7) and roughness (e.g. Ra 1.6)",
                       "es": "Grado de tolerancia (p. ej. IT7) y rugosidad (p. ej. Ra 1.6)",
                       "zh": "公差等级（如 IT7）与粗糙度（如 Ra 1.6）"},
    "elem_part_name": {"de": "Verwendungszweck / Teilebezeichnung (optional)",
                       "en": "Intended use / part name (optional)",
                       "es": "Uso previsto / denominación (opcional)",
                       "zh": "用途/零件名称（选填）"},

    # ---- 客户记忆 / 订单跟进感 (双层 RAG 注入回信) ----
    # 数据源: 上层 conversations 层 (收件箱+发件箱, 按 email-ID 隔离) +
    # crm 历史报价 + 待跟进事项。只引用事实, 不造数字 (报价仍由引擎裁决)。
    "repeat_opener":   {"de": "Wir freuen uns, wieder mit Ihnen zusammenzuarbeiten.",
                        "en": "Good to be working with you again.",
                        "es": "Nos alegra volver a trabajar con usted.",
                        "zh": "很高兴再次与您合作。"},
    "last_ref":        {"de": "In Ihrem letzten Angebot ({ref}) lagen wir bei {price}.",
                        "en": "Your previous quotation ({ref}) was priced at {price}.",
                        "es": "Su cotización anterior ({ref}) fue de {price}.",
                        "zh": "您上一次报价（{ref}）为 {price}。"},
    "followup_ref":    {"de": "Zu Ihrer offenen Anfrage ({ref}): der aktuelle Stand ist in Bearbeitung.",
                        "en": "Regarding your open inquiry ({ref}): it is currently being processed.",
                        "es": "Respecto a su consulta pendiente ({ref}): está en proceso.",
                        "zh": "关于您此前的询盘（{ref}）：目前正在处理中。"},
    "shared_ref":      {"de": "Als Orientierung: vergleichbare Teile liegen aktuell bei {price}.",
                        "en": "For reference: comparable parts are currently around {price}.",
                        "es": "A modo de referencia: piezas similares rondan {price}.",
                        "zh": "仅供参考：同类零件的近期报价水平在 {price} 左右。"},
    # ---- 大件转人工 (用户 2026-09-23: 7862 只适合中小件, 太大件算不准) ----
    # verification 按 policy.oversize.max_dim_hitl_mm 判定, 写入 rfq._oversize;
    # reply 的 HITL 分支用 oversize_reason 本地化理由, 只注明尺寸不出价。
    # 若沿用中文 reason 直塞模板, 德文客户会收到中德混排邮件 (实测缺陷)。
    "oversize_reason": {"de": "Ihr Teil ({dim}mm) übersteigt unseren automatischen "
                        "Kalkulationsbereich ({limit}mm) und wird von unserem Fertigungsteam "
                        "einzeln kalkuliert",
                        "en": "your part ({dim}mm) exceeds our automatic quotation range "
                        "({limit}mm) and will be prepared individually by our production team",
                        "es": "su pieza ({dim}mm) supera nuestro rango de cotización automática "
                        "({limit}mm) y será calculada individualmente por nuestro equipo de producción",
                        "zh": "您的零件最大尺寸 ({dim}mm) 超出我们自动报价的适用范围 ({limit}mm)，"
                        "需由生产团队单独核价"},
    "oversize_note":   {"de": "Bitte beachten Sie: Ihr Teil hat eine maximale Abmessung von {dim}mm. "
                        "Für Bauteile dieser Größe erfolgt die Kalkulation durch unser "
                        "Fertigungsteam, da große Verfahrwege und gesonderte Aufspannungen "
                        "zu berücksichtigen sind. Wir melden uns mit einem geprüften Angebot.",
                        "en": "Please note: your part has a maximum dimension of {dim}mm. "
                        "For parts of this size our production team prepares the quotation "
                        "individually, as large travel ranges and dedicated fixturing have "
                        "to be taken into account. We will come back with a verified offer.",
                        "es": "Tenga en cuenta: su pieza tiene una dimensión máxima de {dim}mm. "
                        "Para piezas de este tamaño nuestro equipo de producción elabora la "
                        "cotización de forma individual, ya que deben considerarse recorridos "
                        "largos y utillajes específicos. Le responderemos con una oferta verificada.",
                        "zh": "需要说明：您的零件最大尺寸为 {dim}mm。该尺寸超出我们自动报价的适用范围，"
                        "此类大件需由生产团队单独核价（涉及大行程机床与专用工装）。"
                        "我们会在核实后提供正式报价。"},
    # ---- 多模态冲突 (文字↔语音↔图纸 不一致) 本地化 ----
    # 成因: verification 的"推"维度发现冲突 → HITL. 内部 reason 是中文串
    # ("多模态冲突(语音↔邮件): ..."), 直塞模板会让德文客户收到中德混排邮件
    # (与 oversize 同一个实测缺陷, 2026-09-23 一并修复)。
    # 只说明"数据不一致待核", 不带任何价格/GEO_TEXT 尺寸值之外的细节。
    "conflict_reason": {"de": "die uns vorliegenden Angaben zu Ihrem Projekt stimmen nicht "
                        "ganz überein, daher prüft unser Team die technischen Details noch "
                        "einmal gemeinsam mit der Fertigung",
                        "en": "the details we have on file for your project do not fully "
                        "match, so our team is re-checking the technical points together "
                        "with production",
                        "es": "los datos que tenemos de su proyecto no coincen por completo, "
                        "por ello nuestro equipo está revisando los detalles técnicos junto "
                        "con producción",
                        "zh": "我们手上的项目信息存在不一致，我们的团队正在与生产部门一起"
                        "重新核对技术细节"},
}


def L(key: str, lang: str) -> str:
    """取标签; 缺失语种回退 en, 再退回 key 本身。"""
    d = LABELS.get(key) or {}
    return d.get(lang) or d.get("en") or key


# ---- 五要素分组 (苏格拉底追问) ----
# missing_information 里的原始字段名 → 询问要素
_ELEM_MAP = {
    "material": "elem_material",
    "material_missing": "elem_material",
    "quantity": "elem_quantity",
    "dimensions": "elem_dimensions",
    "dimensions_mm": "elem_dimensions",
    "surface": "elem_surface",
    "surface_finish": "elem_surface",
    "tolerance": "elem_tolerance",
    "tolerance_grade": "elem_tolerance",
    "roughness": "elem_tolerance",
}


def missing_to_elements(missing: list) -> list:
    """把引擎产出的 missing_information 归一为五要素标签 key 列表。

    保留固定五要素顺序, 去重。未识别项忽略 (不臆造要素)。
    """
    out = []
    seen = set()
    for m in missing or []:
        key = str(m).strip().lower()
        key = key.split(":")[0].strip()          # 兼容 "material: xxx" 形态
        elem = _ELEM_MAP.get(key)
        if elem and elem not in seen:
            seen.add(elem)
            out.append(elem)
    return out
