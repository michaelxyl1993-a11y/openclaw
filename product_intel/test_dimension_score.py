"""Smoke tests for Product Intel v1.2 dimension scores."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .dimension_score import build_dimension_scores
from .input_adapter import load_products_from_file
from .opportunity_score import score_product_opportunity
from .product_fact_sheet import build_product_fact_sheet


PACKAGE_DIR = Path(__file__).resolve().parent
MOCK_CSV = PACKAGE_DIR / "mock_products.csv"


def build_scores(product: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    fact_sheet = build_product_fact_sheet(product)
    opportunity = score_product_opportunity(fact_sheet)
    dimensions = build_dimension_scores(product, fact_sheet, opportunity, market=str(product.get("market") or "de"))
    return fact_sheet, opportunity, dimensions


def product_by_name(products: list[dict[str, Any]], name_part: str) -> dict[str, Any]:
    needle = name_part.lower()
    for product in products:
        if needle in str(product.get("product_name", "")).lower():
            return product
    raise AssertionError(f"missing product containing {name_part!r}")


def assert_dimension_shape(dimensions: dict[str, Any]) -> None:
    expected = {
        "profit_window",
        "demand_pain",
        "external_trend",
        "seasonality",
        "competition",
        "merchant_quality",
        "aigc_fit",
        "final_test_decision",
    }
    if set(dimensions) != expected:
        raise AssertionError(f"unexpected dimension keys: {sorted(dimensions)}")
    for key in expected - {"final_test_decision"}:
        value = dimensions[key]
        for field in ["score", "level", "reason", "reasons", "missing_evidence", "suggested_action"]:
            if field not in value:
                raise AssertionError(f"{key} missing {field}: {value}")
    final_decision = dimensions["final_test_decision"]
    for field in [
        "decision",
        "score",
        "level",
        "reason",
        "reasons",
        "missing_evidence",
        "next_action",
        "suggested_daily_posts",
        "suggested_accounts",
        "suggested_formats",
        "review_after_48h_metrics",
    ]:
        if field not in final_decision:
            raise AssertionError(f"final_test_decision missing {field}: {final_decision}")


def main() -> None:
    products = load_products_from_file(MOCK_CSV, source="auto")[0]

    cat_bowl = product_by_name(products, "Cat Bowl")
    _fact, _opp, cat_dims = build_scores(cat_bowl)
    assert_dimension_shape(cat_dims)
    if cat_dims["aigc_fit"]["score"] < 75 or cat_dims["demand_pain"]["score"] < 75:
        raise AssertionError(f"cat bowl should have strong AIGC and demand fit: {cat_dims}")

    litter_mat = product_by_name(products, "Litter Mat")
    _fact, _opp, litter_dims = build_scores(litter_mat)
    if litter_dims["aigc_fit"]["score"] < 75 or litter_dims["demand_pain"]["score"] < 75:
        raise AssertionError(f"litter mat should have strong AIGC and demand fit: {litter_dims}")

    mini_fan = product_by_name(products, "Handheld Fan")
    _fact, _opp, fan_dims = build_scores(mini_fan)
    if fan_dims["aigc_fit"]["score"] < 75 or fan_dims["demand_pain"]["score"] < 70:
        raise AssertionError(f"mini fan should have strong AIGC and demand fit: {fan_dims}")

    treadmill = product_by_name(products, "Treadmill")
    _fact, _opp, treadmill_dims = build_scores(treadmill)
    if treadmill_dims["final_test_decision"]["decision"] not in {"hold", "reject"}:
        raise AssertionError(f"treadmill should be hold or reject: {treadmill_dims['final_test_decision']}")

    snack = product_by_name(products, "Wafer Snack")
    _fact, _opp, snack_dims = build_scores(snack)
    assert_dimension_shape(snack_dims)

    beauty = product_by_name(products, "Face Serum")
    _fact, _opp, beauty_dims = build_scores(beauty)
    assert_dimension_shape(beauty_dims)

    sparse_product = {"product_id": "sparse_001", "product_name": "Unknown Test Product"}
    _fact, _opp, sparse_dims = build_scores(sparse_product)
    missing_count = sum(
        len(value.get("missing_evidence", []))
        for key, value in sparse_dims.items()
        if key != "final_test_decision" and isinstance(value, dict)
    )
    if missing_count <= 0:
        raise AssertionError(f"sparse product should report missing evidence: {sparse_dims}")
    weak_or_unknown = [
        value
        for key, value in sparse_dims.items()
        if key != "final_test_decision" and isinstance(value, dict) and value.get("level") in {"weak", "unknown"}
    ]
    if not weak_or_unknown or not any(value.get("missing_evidence") for value in weak_or_unknown):
        raise AssertionError(f"weak or unknown dimensions should retain missing evidence: {sparse_dims}")

    print("Product Intel dimension score smoke test passed.")


if __name__ == "__main__":
    main()
