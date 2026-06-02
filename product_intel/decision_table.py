"""Build team-readable product selection decision rows."""

from __future__ import annotations

from typing import Any


def text_join(values: list[Any]) -> str:
    seen = set()
    parts: list[str] = []
    for value in values:
        if value in ("", None):
            continue
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        parts.append(text)
    return ", ".join(parts)


def category_text(fact_sheet: dict[str, Any], product: dict[str, Any]) -> str:
    category = fact_sheet.get("category", {})
    if isinstance(category, dict):
        return text_join([category.get("l1"), category.get("l2"), category.get("l3")])
    return str(product.get("category", "") or category or "")


def hook_types(fact_sheet: dict[str, Any]) -> list[str]:
    hook_candidates = (
        fact_sheet.get("recommended_hooks")
        or fact_sheet.get("hooks")
        or fact_sheet.get("hook_recommendations")
        or []
    )
    hooks: list[str] = []
    for hook_item in hook_candidates:
        if isinstance(hook_item, dict):
            hook_type = hook_item.get("hook_type") or hook_item.get("hook_id")
            if hook_type:
                hooks.append(str(hook_type))
        elif hook_item:
            hooks.append(str(hook_item))
    return hooks


def suggested_format(opportunity: dict[str, Any], fact_sheet: dict[str, Any], product: dict[str, Any]) -> str:
    explicit = opportunity.get("suggested_format")
    if explicit:
        return str(explicit)

    searchable = " ".join(
        [
            category_text(fact_sheet, product),
            str(product.get("product_name", "")),
            str(fact_sheet.get("product_name", "")),
            " ".join(hook_types(fact_sheet)),
        ]
    ).lower()
    if any(term in searchable for term in ["electronics", "tool", "gadget"]):
        return "photo,video"
    if any(term in searchable for term in ["how to", "tutorial", "installation", "complex", "explain"]):
        return "video"
    if any(term in searchable for term in ["pet", "home", "kitchen", "beauty", "fashion"]):
        return "photo"
    return "both"


def next_action(decision: str) -> str:
    mapping = {
        "main_push": "今天可主推，进入账号分发表",
        "small_test": "小样本测试，先发1-2条验证CTR/转化",
        "hold": "暂缓，不进今日主推池",
        "observe": "暂缓，不进今日主推池",
        "reject": "不建议当前阶段做",
    }
    return mapping.get(decision, "暂缓，不进今日主推池")


def normalize_decision(decision: str) -> str:
    return "hold" if decision == "observe" else decision


def final_public_decision(opportunity: dict[str, Any], dimension_scores: dict[str, Any]) -> str:
    final_dimension = dimension_scores.get("final_test_decision", {})
    if not isinstance(final_dimension, dict):
        final_dimension = {}
    return normalize_decision(str(final_dimension.get("decision") or opportunity.get("decision") or "hold"))


def dimension_items(dimension_scores: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    for key, value in dimension_scores.items():
        if key == "final_test_decision" or not isinstance(value, dict):
            continue
        items.append((key, value))
    return items


def dimension_summary(dimension_scores: dict[str, Any]) -> str:
    final_decision = dimension_scores.get("final_test_decision", {})
    if not isinstance(final_decision, dict):
        final_decision = {}
    parts = []
    for key, value in dimension_items(dimension_scores):
        parts.append(f"{key}:{value.get('level', '')}/{value.get('score', 0)}")
    if final_decision:
        parts.append(f"final:{final_decision.get('decision', '')}/{final_decision.get('score', 0)}")
    return "; ".join(parts)


def strongest_dimensions(dimension_scores: dict[str, Any]) -> str:
    sorted_items = sorted(dimension_items(dimension_scores), key=lambda item: int(item[1].get("score", 0) or 0), reverse=True)
    return text_join([f"{key}({value.get('score', 0)})" for key, value in sorted_items[:3]])


def weakest_dimensions(dimension_scores: dict[str, Any]) -> str:
    sorted_items = sorted(dimension_items(dimension_scores), key=lambda item: int(item[1].get("score", 0) or 0))
    return text_join([f"{key}({value.get('score', 0)})" for key, value in sorted_items[:3]])


def missing_evidence_count(dimension_scores: dict[str, Any]) -> int:
    count = 0
    for _key, value in dimension_items(dimension_scores):
        missing = value.get("missing_evidence", [])
        if isinstance(missing, list):
            count += len(missing)
    return count


DIMENSION_RISK_LABELS = {
    "profit_window": "利润窗口偏弱",
    "demand_pain": "需求痛点证据偏弱",
    "external_trend": "外部趋势证据不足",
    "seasonality": "季节性支撑偏弱",
    "competition": "竞争差异化证据不足",
    "merchant_quality": "商家质量证据不足",
    "aigc_fit": "AIGC 适配需人工复核",
}

RISK_FLAG_TRANSLATIONS = {
    "Medium product risk level.": "中风险商品，建议人工复核",
    "Human review is required.": "需要人工复核后再发布",
}


def risk_flag_category(flag: str) -> str:
    if "外部趋势证据" in flag:
        return "external_trend"
    if "商家质量证据" in flag:
        return "merchant_quality"
    if "小样本" in flag:
        return "small_test"
    return flag


def normalize_risk_flags(flags: list[Any]) -> list[str]:
    normalized: list[str] = []
    seen_categories: set[str] = set()
    for flag in flags:
        text = RISK_FLAG_TRANSLATIONS.get(str(flag).strip(), str(flag).strip())
        if not text:
            continue
        category = risk_flag_category(text)
        if category in seen_categories:
            continue
        seen_categories.add(category)
        normalized.append(text)
    return normalized


def ops_risk_note(flags: list[str], decision: str) -> str:
    if not flags:
        return "无额外风险提醒"
    details = "；".join(flags)
    if any("需要人工复核后再发布" in flag or "功效表达需谨慎" in flag for flag in flags):
        return f"必须人工复核：{details}"
    if decision in {"hold", "reject"}:
        return f"暂缓补证：{details}"
    return f"运营提醒：{details}"


def build_risk_flags(
    product: dict[str, Any],
    fact_sheet: dict[str, Any],
    opportunity: dict[str, Any],
    dimension_scores: dict[str, Any],
    decision: str,
) -> list[str]:
    flags = [
        str(flag)
        for flag in opportunity.get("risk_flags", [])
        if flag
    ] if isinstance(opportunity.get("risk_flags", []), list) else []
    searchable = " ".join(
        [
            category_text(fact_sheet, product),
            str(product.get("product_name", "")),
            str(fact_sheet.get("product_name", "")),
        ]
    ).lower()

    for key, value in dimension_items(dimension_scores):
        level = str(value.get("level", "unknown"))
        if level in {"weak", "unknown"}:
            label = DIMENSION_RISK_LABELS.get(key, f"{key} 证据不足")
            flags.append(f"{label}（{level}）")

    if any(term in searchable for term in ["treadmill", "fitness", "walking pad"]):
        flags.extend(["高客单/重决策商品，转化链路较长", "需补齐商家履约、退货和质量证据"])
    if any(term in searchable for term in ["beauty", "serum", "skincare"]):
        flags.append("功效表达需谨慎，避免缺少证据的效果承诺")
        trend = dimension_scores.get("external_trend", {})
        if isinstance(trend, dict) and trend.get("missing_evidence"):
            flags.append("缺少外部趋势证据，建议先小样本测试")
    if any(term in searchable for term in ["food", "snack", "wafer"]):
        if str(dimension_scores.get("demand_pain", {}).get("level", "")) in {"weak", "unknown"}:
            flags.append("食品购买痛点偏弱")
        if str(dimension_scores.get("profit_window", {}).get("level", "")) in {"weak", "unknown"}:
            flags.append("食品利润窗口偏弱")
        flags.append("食品类需小样本验证转化")
    if decision == "small_test":
        flags.append("建议先小样本验证")

    return normalize_risk_flags(flags)


def main_push_reason(
    decision: str,
    opportunity: dict[str, Any],
    dimension_scores: dict[str, Any],
) -> str:
    final_dimension = dimension_scores.get("final_test_decision", {})
    if not isinstance(final_dimension, dict):
        final_dimension = {}
    reasons = final_dimension.get("reasons", [])
    if not isinstance(reasons, list) or not reasons:
        reasons = opportunity.get("reasons", [])
    if not isinstance(reasons, list) or not reasons:
        return "本地证据不足，建议补齐关键数据后再决定。"
    prefix = "主推依据" if decision == "main_push" else "判断依据"
    return f"{prefix}：" + "；".join(str(reason) for reason in reasons[:3])


def build_decision_rows(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sorted_results = sorted(
        results,
        key=lambda item: int(item.get("opportunity", {}).get("opportunity_score", 0) or 0),
        reverse=True,
    )
    rows: list[dict[str, Any]] = []
    for rank, item in enumerate(sorted_results, start=1):
        product = item.get("product", {}) if isinstance(item.get("product", {}), dict) else {}
        fact_sheet = item.get("fact_sheet", {}) if isinstance(item.get("fact_sheet", {}), dict) else {}
        opportunity = item.get("opportunity", {}) if isinstance(item.get("opportunity", {}), dict) else {}
        dimensions = item.get("dimension_scores", {}) if isinstance(item.get("dimension_scores", {}), dict) else {}
        final_dimension = dimensions.get("final_test_decision", {}) if isinstance(dimensions.get("final_test_decision", {}), dict) else {}
        decision = final_public_decision(opportunity, dimensions)
        product_name = str(product.get("product_name") or fact_sheet.get("product_name") or "")
        risk_flags = build_risk_flags(product, fact_sheet, opportunity, dimensions, decision)
        risk_note = ops_risk_note(risk_flags, decision)
        row = {
            "rank": rank,
            "product_id": str(product.get("product_id") or fact_sheet.get("product_id") or ""),
            "product_name": product_name,
            "category": category_text(fact_sheet, product),
            "source_platform": str(product.get("source_platform") or fact_sheet.get("source") or ""),
            "price": product.get("price") or fact_sheet.get("price") or "",
            "commission_rate": product.get("commission_rate") or fact_sheet.get("commission_rate") or "",
            "sold_count": product.get("sold_count") or fact_sheet.get("performance", {}).get("sales", ""),
            "gmv": product.get("gmv") or fact_sheet.get("performance", {}).get("gmv", ""),
            "opportunity_score": int(opportunity.get("opportunity_score", 0) or 0),
            "decision": decision,
            "suggested_format": suggested_format(opportunity, fact_sheet, product),
            "suggested_daily_posts": final_dimension.get("suggested_daily_posts", opportunity.get("suggested_daily_volume", "")),
            "recommended_hooks": text_join(hook_types(fact_sheet)),
            "content_angle_summary": str(opportunity.get("content_angle_summary", "")),
            "reasons": text_join(opportunity.get("reasons", []) if isinstance(opportunity.get("reasons", []), list) else []),
            "risk_flags": text_join(risk_flags),
            "risk_flags_list": risk_flags,
            "ops_risk_note": risk_note,
            "dimension_summary": dimension_summary(dimensions),
            "strongest_dimensions": strongest_dimensions(dimensions),
            "weakest_dimensions": weakest_dimensions(dimensions),
            "missing_evidence_count": missing_evidence_count(dimensions),
            "main_push_reason": main_push_reason(decision, opportunity, dimensions),
            "next_action": str(final_dimension.get("next_action") or next_action(decision)),
        }
        rows.append(row)
    return rows
