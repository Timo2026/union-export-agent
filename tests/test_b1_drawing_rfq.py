"""test_b1_drawing_rfq.py — 方案B1 图纸感知→RFQ 契约回归.

背景 (2026-09-25 节点 E2E 实证, deploy/_e2e_b1_intake3.py):
  Omni :8002 读图成功, 但 services/media_api._CHAT_IMG_PROMPT 只问六类事实
  (零件类型/尺寸/材料/表面/公差/孔特征, 不含数量) → 图纸-only RFQ 的 quantity
  恒缺 → 黄金链 reasons: ['RFQ 信息缺失: quantity'] → HITL;
  且 schemas/rfq.schema.json 的 dimensions_mm type 不含 null → extract_rfq 对
  无 AxBxC 文本的合法产出 None 恒报 schema error。
"""
from __future__ import annotations

import services.media_api as ma
from services.intake import (_extract_quantity, _norm_material, _norm_surface,
                             extract_rfq)
from services.schema_validator import validate_rfq

# 节点 E2E 实收感知文字的形状 (数量行为改进提示词补上)
_PERCEPTION_PROSE = (
    "[Drawing perception]: 基于图像内容，提取如下信息：\n"
    "*   **零件类型**: 法兰 (FLANGE DRAWING)\n"
    "*   **可见尺寸**:\n"
    "    *   外径 (OD): 100 mm\n"
    "    *   内径 (ID): 50 mm\n"
    "    *   厚度 (THK): 10 mm\n"
    "*   **数量/批量**: QTY: 50 PCS\n"
    "*   **材料线索**: 6061-T6 (位于左下角)\n"
    "*   **表面处理线索**: SURFACE ANODIZE (位于右侧)\n"
    "*   **公差/粗糙度标注**: TOL: IT7 (位于内径附近)\n"
)


def test_chat_img_prompt_asks_quantity():
    """感知提示词必须问数量 — 否则图纸-only RFQ 永远缺 quantity (节点 E2E 实测)。"""
    assert "数量" in ma._CHAT_IMG_PROMPT


def test_adapter_default_prompt_asks_quantity():
    """upload/intake 路径走 funasr_adapter 默认提示词 (与 media_api 的是两份, 都会漂移) — 也必须问数量。"""
    from adapters.funasr_adapter import VLM_IMG_PROMPT_DEFAULT
    assert "数量" in VLM_IMG_PROMPT_DEFAULT


def test_perception_prose_quantity_extractable():
    """VLM 散文感知 → _extract_quantity 命中 (50 PCS / 50 件 两种书写)。"""
    assert _extract_quantity(_PERCEPTION_PROSE) == 50
    assert _extract_quantity("**数量**: 30 件") == 30


def test_rfq_schema_allows_null_dimensions():
    """图纸-only RFQ: dimensions_mm=None 合法 (可选字段, 类型须含 null)。"""
    rfq = extract_rfq("数量: 50 件, 材料 6061, 表面 阳极氧化, 公差 IT7")
    res = validate_rfq(rfq)
    assert res["valid"] is True, res["errors"]


def test_drawing_only_rfq_full_contract():
    """端到端契约: 感知散文 → extract_rfq → schema 全字段过 (quantity 不再缺)。"""
    rfq = extract_rfq(_PERCEPTION_PROSE)
    assert rfq["material"] == "6061"
    assert rfq["quantity"] == 50
    assert rfq["surface"] == "阳极氧化"
    assert rfq["tolerance_grade"] == "IT7"
    assert "quantity" not in rfq["missing_information"]
    assert validate_rfq(rfq)["valid"] is True


# ---- 别名词界匹配 (节点 2026-09-25 E2E 500 实证: 英文感知 "50 PCS" 的 "pc" 子串
# 被材质别名 "pc"(聚碳酸酯) 误命中 → guardrail invalid_material → dfm-conflict 被拦 → 500) ----

def test_quantity_suffix_not_matched_as_material():
    """'50 PCS' 的子串 'pc' 不得误命中材质 PC — 词界匹配, 非裸子串。"""
    assert _norm_material("Quantity/Volume: 50 PCS") is None


def test_temperature_not_matched_as_surface():
    """'temperature' 的子串 'temper' (调质别名) 不得误命中表面处理。"""
    assert _norm_surface("storage temperature 60C") is None


def test_material_grade_suffix_still_matches():
    """回归守护: 数字代号别名维持子串匹配 — '6061-T6'/'6061T6'/'Q235A' 均须命中。"""
    assert _norm_material("MATERIAL: 6061-T6") == "6061"
    assert _norm_material("material 6061T6 aluminum") == "6061"
    assert _norm_material("Q235A steel plate") == "Q235"


def test_word_alias_still_matches_standalone():
    """回归守护: 独立成词的英文别名仍命中 (词界不误杀真阳性)。"""
    assert _norm_material("made of brass") == "黄铜"
    assert _norm_surface("surface: anodized, black oxide") == "发黑"  # 长别名优先
    assert _norm_surface("surface: anodized only") == "阳极氧化"
