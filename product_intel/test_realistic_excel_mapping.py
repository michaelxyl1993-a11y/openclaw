"""Regression tests for realistic third-party and manual Excel exports."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from .csv_profile import profile_csv_rows
from .input_adapter import load_products_from_file, load_raw_product_rows
from .run_product_intel import run_pipeline


PACKAGE_DIR = Path(__file__).resolve().parent
EXPECTED = {
    "mock_echotik_products.xlsx": "echotik",
    "mock_fastmoss_products.xlsx": "fastmoss",
    "mock_kalodata_products.xlsx": "kalodata",
    "mock_manual_products.xlsx": "manual",
}


def main() -> None:
    decision_counts: Counter[str] = Counter()
    for filename, expected_source in EXPECTED.items():
        path = PACKAGE_DIR / filename
        rows, metadata = load_raw_product_rows(path)
        profile = profile_csv_rows(rows, source="auto", **metadata)
        if profile["source_detected"] != expected_source:
            raise AssertionError(f"{filename}: expected source={expected_source}, got {profile}")
        if profile["detected_file_type"] != "xlsx" or not profile["detected_sheet_name"]:
            raise AssertionError(f"{filename}: Excel metadata missing: {profile}")
        if profile["source_platform_value"] != expected_source:
            raise AssertionError(f"{filename}: profile source_platform fallback missing: {profile}")
        expected_platform_source = "explicit" if filename == "mock_manual_products.xlsx" else "inferred"
        if profile["source_platform_source"] != expected_platform_source:
            raise AssertionError(f"{filename}: unexpected source_platform_source: {profile}")
        for field in ["product_id", "product_name", "category", "price", "sold_count", "gmv"]:
            if not profile["mapped_fields"].get(field):
                raise AssertionError(f"{filename}: profile mapping missing {field}: {profile}")
        products, _ = load_products_from_file(path, source="auto")
        if len(products) != 3:
            raise AssertionError(f"{filename}: expected 3 products, got {len(products)}")
        for product in products:
            for field in ["product_id", "product_name", "category", "price", "sold_count", "gmv"]:
                if product.get(field) in ("", None):
                    raise AssertionError(f"{filename}: normalized product missing {field}: {product}")
            if product["source_platform"] != expected_source:
                raise AssertionError(f"{filename}: normalized source fallback missing: {product}")
        with TemporaryDirectory() as output_dir:
            payload = run_pipeline(path, source="auto", output_dir=output_dir)["payload"]
        if any(product.get("source_platform") != expected_source for product in payload["products"]):
            raise AssertionError(f"{filename}: manager payload source_platform fallback missing: {payload}")
        for product in payload["products"]:
            flags = product.get("risk_flags", [])
            if any(flag in {"Medium product risk level.", "Human review is required."} for flag in flags):
                raise AssertionError(f"{filename}: untranslated risk flag: {product}")
            if len([flag for flag in flags if "外部趋势证据" in flag]) > 1:
                raise AssertionError(f"{filename}: duplicate trend risk flag: {product}")
            if len([flag for flag in flags if "商家质量证据" in flag]) > 1:
                raise AssertionError(f"{filename}: duplicate merchant risk flag: {product}")
            if len([flag for flag in flags if "小样本" in flag]) > 1:
                raise AssertionError(f"{filename}: duplicate small-test risk flag: {product}")
            if not product.get("ops_risk_note"):
                raise AssertionError(f"{filename}: missing ops_risk_note: {product}")
            decision_counts[product["decision"]] += 1
    expected_counts = {"main_push": 1, "small_test": 8, "hold": 3}
    if dict(decision_counts) != expected_counts:
        raise AssertionError(f"realistic output decision distribution changed: expected {expected_counts}, got {dict(decision_counts)}")
    print("Realistic Excel mapping tests passed.")


if __name__ == "__main__":
    main()
