"""Smoke test for Product Fact Sheet generation."""

from __future__ import annotations

import json

from .opportunity_score import score_product_opportunity
from .product_fact_sheet import build_mock_fact_sheet


REQUIRED_FIELDS = [
    "product_id",
    "source",
    "market",
    "product_name",
    "category",
    "price",
    "commission_rate",
    "product_url",
    "image_urls",
    "seller_info",
    "performance",
    "visual_identity",
    "must_keep",
    "must_not_add",
    "allowed_claims",
    "forbidden_claims",
    "risk_level",
    "human_review_required",
    "recommended_usage",
    "hook_recommendations",
]


def validate_required_fields(fact_sheet: dict) -> None:
    for field in REQUIRED_FIELDS:
        if field not in fact_sheet:
            raise AssertionError(f"missing required field: {field}")
        if fact_sheet[field] in ("", None):
            raise AssertionError(f"empty required field: {field}")

    if not fact_sheet["category"].get("l1"):
        raise AssertionError("empty required field: category.l1")
    if not fact_sheet["seller_info"].get("seller_id"):
        raise AssertionError("empty required field: seller_info.seller_id")
    if not fact_sheet["image_urls"]:
        raise AssertionError("empty required field: image_urls")


def main() -> None:
    fact_sheet = build_mock_fact_sheet()
    opportunity = score_product_opportunity(fact_sheet)
    validate_required_fields(fact_sheet)
    if not fact_sheet["hook_recommendations"]:
        raise AssertionError("hook_recommendations must include at least one hook")
    if not 0 <= opportunity["opportunity_score"] <= 100:
        raise AssertionError("opportunity_score must be between 0 and 100")
    if opportunity["decision"] not in {"main_push", "small_test", "observe", "reject"}:
        raise AssertionError(f"invalid decision: {opportunity['decision']}")

    print(json.dumps({"fact_sheet": fact_sheet, "opportunity": opportunity}, ensure_ascii=False, indent=2))
    print("Product Fact Sheet smoke test passed.")


if __name__ == "__main__":
    main()
