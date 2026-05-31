"""Smoke tests for CSV input adapter and batch Fact Sheet generation."""

from __future__ import annotations

from pathlib import Path

from .batch_fact_sheet import build_batch_fact_sheets
from .csv_loader import load_products_from_csv
from .input_adapter import normalize_product_row


PACKAGE_DIR = Path(__file__).resolve().parent
MOCK_CSV_PATH = PACKAGE_DIR / "mock_products.csv"
VALID_DECISIONS = {"main_push", "small_test", "observe", "reject"}


def validate_normalized_product(product: dict, index: int) -> None:
    for field in ["product_id", "product_name", "category"]:
        if not product.get(field):
            raise AssertionError(f"product {index} missing {field}: {product}")


def validate_batch_item(item: dict, index: int) -> None:
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
    sample = normalize_product_row(
        {
            "商品ID": "sample_001",
            "商品标题": "Sample Product",
            "类目": "Home > Storage",
            "售价": "£9.99",
            "达人佣金率": "12%",
            "已售": "120",
            "销售额": "1198.8",
            "来源": "manual",
        }
    )
    validate_normalized_product(sample, 0)

    products = load_products_from_csv(MOCK_CSV_PATH)
    if not products:
        raise AssertionError("mock CSV did not load any products")
    for index, product in enumerate(products, start=1):
        validate_normalized_product(product, index)

    batch = build_batch_fact_sheets(products)
    items = batch["items"]
    for index, item in enumerate(items, start=1):
        validate_batch_item(item, index)

    ranked = sorted(items, key=lambda item: item["opportunity"]["opportunity_score"], reverse=True)
    print("Product Intel CSV adapter summary by opportunity_score:")
    for item in ranked:
        fact_sheet = item["fact_sheet"]
        opportunity = item["opportunity"]
        category = fact_sheet["category"].get("l3") or fact_sheet["category"].get("l1")
        print(
            f"- {opportunity['opportunity_score']:>3} "
            f"{opportunity['decision']:<10} "
            f"{fact_sheet['product_id']} | "
            f"{fact_sheet['product_name']} | "
            f"{category}"
        )

    print(f"Input adapter smoke test passed: {len(products)} products.")


if __name__ == "__main__":
    main()
