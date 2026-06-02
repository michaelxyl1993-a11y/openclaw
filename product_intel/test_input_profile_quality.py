"""Regression tests for input profile quality diagnostics."""

from __future__ import annotations

from pathlib import Path

from .csv_profile import profile_csv_rows
from .input_adapter import load_raw_product_rows


PACKAGE_DIR = Path(__file__).resolve().parent


def main() -> None:
    complete = [{
        "product_id": "p1", "product_name": "Complete", "category": "Home", "price": 10,
        "sold_count": 20, "gmv": 200, "commission_rate": "8%", "product_url": "https://example.com",
        "shop_name": "Shop", "source_platform": "manual", "growth_7d": "5%", "growth_30d": "10%",
        "related_video_count": 4, "related_influencer_count": 2, "rating": 4.7, "review_count": 30,
    }]
    complete_profile = profile_csv_rows(complete)
    if complete_profile["field_quality_score"] != 100 or complete_profile["mapping_confidence"] != "high":
        raise AssertionError(f"complete profile should be high quality: {complete_profile}")

    sparse = [{"title": "Sparse", "category": "Home", "price": 10}]
    sparse_profile = profile_csv_rows(sparse)
    if sparse_profile["mapping_confidence"] != "low":
        raise AssertionError(f"sparse profile should be low confidence: {sparse_profile}")
    warning_text = "\n".join(sparse_profile["warnings"])
    for field in ["product_url", "shop_name", "commission_rate", "rating/review_count"]:
        if field not in warning_text:
            raise AssertionError(f"missing operator-readable warning for {field}: {warning_text}")

    duplicate = [{"title": "", "title__duplicate_2": "Fallback title", "category": "Home", "product_id": "p2", "extra": "x"}]
    duplicate_profile = profile_csv_rows(duplicate)
    if duplicate_profile["mapped_fields"]["product_name"] != "title__duplicate_2":
        raise AssertionError(f"duplicate selection did not prefer populated column: {duplicate_profile}")
    if duplicate_profile["duplicate_columns"] != ["title"] or "extra" not in duplicate_profile["unmapped_columns"]:
        raise AssertionError(f"duplicate/unmapped diagnostics missing: {duplicate_profile}")

    for filename in ["mock_echotik_products.xlsx", "mock_fastmoss_products.xlsx"]:
        rows, metadata = load_raw_product_rows(PACKAGE_DIR / filename)
        profile = profile_csv_rows(rows, source="auto", **metadata)
        if profile["mapping_confidence"] != "high":
            raise AssertionError(f"{filename}: core field mappings should be high confidence: {profile}")
        if not 70 <= profile["field_quality_score"] < complete_profile["field_quality_score"]:
            raise AssertionError(f"{filename}: evidence score should remain below manual complete profile: {profile}")
    print("Input profile quality tests passed.")


if __name__ == "__main__":
    main()
