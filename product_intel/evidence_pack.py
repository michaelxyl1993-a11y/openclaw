"""Build local-only evidence packs for future LLM Judge review."""

from __future__ import annotations

from collections import Counter
from typing import Any


DIMENSION_FIELDS = {
    "profit_window": [
        "price", "commission_rate", "sold_count", "gmv", "growth_7d", "growth_30d",
        "related_video_count", "related_influencer_count",
    ],
    "demand_pain": ["category", "sold_count", "rating", "review_count"],
    "external_trend": ["growth_7d", "growth_30d", "related_video_count", "related_influencer_count"],
    "seasonality": ["category", "market"],
    "competition": ["price", "related_video_count", "related_influencer_count"],
    "merchant_quality": ["shop_name", "rating", "review_count", "product_url"],
    "aigc_fit": ["category", "recommended_hooks", "recommended_formats", "risk_flags"],
    "final": ["opportunity_score", "decision", "next_action"],
}
DIMENSIONS = list(DIMENSION_FIELDS)
COVERAGE_ORDER = {"missing": 0, "weak": 1, "medium": 2, "strong": 3}


def has_evidence(value: Any) -> bool:
    if value in ("", None, 0, 0.0, [], {}):
        return False
    return True


def evidence_coverage_level(evidence_items: Any) -> str:
    if isinstance(evidence_items, dict):
        values = list(evidence_items.values())
    elif isinstance(evidence_items, (list, tuple, set)):
        values = list(evidence_items)
    else:
        values = [evidence_items]
    if not values:
        return "missing"
    present = sum(has_evidence(value) for value in values)
    ratio = present / len(values)
    if ratio >= 0.75:
        return "strong"
    if ratio >= 0.5:
        return "medium"
    if present:
        return "weak"
    return "missing"


def clean_missing(values: list[Any]) -> list[str]:
    missing: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            missing.append(text)
    return missing


def missing_evidence_by_dimension(product: dict[str, Any], dimension_scores: dict[str, Any]) -> dict[str, list[str]]:
    missing_by_dimension: dict[str, list[str]] = {}
    for dimension, fields in DIMENSION_FIELDS.items():
        score_key = "final_test_decision" if dimension == "final" else dimension
        dimension_score = dimension_scores.get(score_key, {})
        scored_missing = dimension_score.get("missing_evidence", []) if isinstance(dimension_score, dict) else []
        inferred_missing = [field for field in fields if not has_evidence(product.get(field))]
        missing_by_dimension[dimension] = clean_missing([*scored_missing, *inferred_missing])
    return missing_by_dimension


def build_dimension_evidence(product: dict[str, Any]) -> dict[str, dict[str, Any]]:
    dimension_scores = product.get("dimension_scores", {})
    if not isinstance(dimension_scores, dict):
        dimension_scores = {}
    missing_by_dimension = missing_evidence_by_dimension(product, dimension_scores)
    evidence: dict[str, dict[str, Any]] = {}
    for dimension, fields in DIMENSION_FIELDS.items():
        available_fields = {
            field: product.get(field)
            for field in fields
            if has_evidence(product.get(field))
        }
        evidence[dimension] = {
            "available_fields": available_fields,
            "coverage": evidence_coverage_level({field: product.get(field) for field in fields}),
            "missing": missing_by_dimension[dimension],
        }
    return evidence


def build_evidence_pack(
    product: dict[str, Any],
    profile: dict[str, Any] | None = None,
    source_detected: str | None = None,
    market: str | None = None,
) -> dict[str, Any]:
    profile = profile or {}
    source = str(
        source_detected
        or profile.get("source_detected")
        or product.get("raw_source")
        or product.get("source_platform")
        or ""
    )
    resolved_market = str(market or product.get("market") or "")
    evidence_product = {**product, "market": resolved_market}
    evidence = build_dimension_evidence(evidence_product)
    missing_total = sum(len(item["missing"]) for item in evidence.values())
    overall = min(
        (item["coverage"] for item in evidence.values()),
        key=lambda coverage: COVERAGE_ORDER[coverage],
        default="missing",
    )
    return {
        "product_id": str(product.get("product_id", "")),
        "product_name": str(product.get("product_name", "")),
        "source_platform": str(product.get("source_platform", "")),
        "source_detected": source,
        "market": resolved_market,
        "evidence": evidence,
        "overall_evidence_coverage": overall,
        "missing_evidence_total": missing_total,
    }


def build_evidence_coverage_summary(evidence_pack: dict[str, Any]) -> dict[str, Any]:
    evidence = evidence_pack.get("evidence", {})
    coverage_counts = Counter(
        item.get("coverage", "missing")
        for item in evidence.values()
        if isinstance(item, dict)
    )
    return {
        "overall_evidence_coverage": evidence_pack.get("overall_evidence_coverage", "missing"),
        "missing_evidence_total": evidence_pack.get("missing_evidence_total", 0),
        "dimension_coverage_counts": {
            coverage: coverage_counts.get(coverage, 0)
            for coverage in ["strong", "medium", "weak", "missing"]
        },
    }
