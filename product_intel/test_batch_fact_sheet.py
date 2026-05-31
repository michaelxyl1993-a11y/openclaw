"""Smoke test for batch Product Fact Sheet generation."""

from __future__ import annotations

from .batch_fact_sheet import build_mock_batch_fact_sheets


VALID_DECISIONS = {"main_push", "small_test", "observe", "reject"}


def validate_item(item: dict, index: int) -> None:
    fact_sheet = item.get("fact_sheet", {})
    opportunity = item.get("opportunity", {})
    if not fact_sheet.get("product_id"):
        raise AssertionError(f"item {index} missing product_id")
    if not fact_sheet.get("hook_recommendations"):
        raise AssertionError(f"item {index} missing hook_recommendations")
    score = opportunity.get("opportunity_score")
    if not isinstance(score, int) or not 0 <= score <= 100:
        raise AssertionError(f"item {index} invalid opportunity_score: {score}")
    if opportunity.get("decision") not in VALID_DECISIONS:
        raise AssertionError(f"item {index} invalid decision: {opportunity.get('decision')}")


def main() -> None:
    batch = build_mock_batch_fact_sheets()
    items = batch.get("items", [])
    if not items:
        raise AssertionError("batch output has no items")

    for index, item in enumerate(items, start=1):
        validate_item(item, index)

    ranked = sorted(items, key=lambda item: item["opportunity"]["opportunity_score"], reverse=True)
    print("Product Intel batch summary by opportunity_score:")
    for item in ranked:
        fact_sheet = item["fact_sheet"]
        opportunity = item["opportunity"]
        hooks = ", ".join(hook["hook_type"] for hook in fact_sheet["hook_recommendations"])
        print(
            f"- {opportunity['opportunity_score']:>3} "
            f"{opportunity['decision']:<10} "
            f"{fact_sheet['market']:<2} "
            f"{fact_sheet['product_id']} | "
            f"{fact_sheet['product_name']} | hooks: {hooks}"
        )

    print(f"Batch Product Fact Sheet smoke test passed: {len(items)} items.")


if __name__ == "__main__":
    main()
