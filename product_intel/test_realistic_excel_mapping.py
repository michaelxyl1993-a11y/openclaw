"""Regression tests for realistic third-party and manual Excel exports."""

from __future__ import annotations

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
    print("Realistic Excel mapping tests passed.")


if __name__ == "__main__":
    main()
