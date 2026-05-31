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
        decision = str(opportunity.get("decision", "observe"))
        product_name = str(product.get("product_name") or fact_sheet.get("product_name") or "")
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
            "suggested_daily_posts": opportunity.get("suggested_daily_volume", ""),
            "recommended_hooks": text_join(hook_types(fact_sheet)),
            "content_angle_summary": str(opportunity.get("content_angle_summary", "")),
            "reasons": text_join(opportunity.get("reasons", []) if isinstance(opportunity.get("reasons", []), list) else []),
            "risk_flags": text_join(opportunity.get("risk_flags", []) if isinstance(opportunity.get("risk_flags", []), list) else []),
            "dimension_summary": dimension_summary(dimensions),
            "strongest_dimensions": strongest_dimensions(dimensions),
            "weakest_dimensions": weakest_dimensions(dimensions),
            "missing_evidence_count": missing_evidence_count(dimensions),
            "next_action": str(final_dimension.get("next_action") or next_action(decision)),
        }
        rows.append(row)
    return rows
