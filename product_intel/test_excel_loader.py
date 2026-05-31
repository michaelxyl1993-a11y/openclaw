"""Smoke tests for Product Intel Excel loader."""

from __future__ import annotations

from pathlib import Path

from .excel_loader import load_products_from_excel, load_raw_excel_rows


PACKAGE_DIR = Path(__file__).resolve().parent


def main() -> None:
    rows, sheet_name = load_raw_excel_rows(PACKAGE_DIR / "mock_products.xlsx")
    if sheet_name != "Candidates":
        raise AssertionError(f"expected first non-empty sheet Candidates, got {sheet_name}")
    if not rows:
        raise AssertionError("Excel loader returned no rows")
    if not rows[0].get("title") and not rows[0].get("商品名称"):
        raise AssertionError(f"Excel row missing product name fields: {rows[0]}")

    products = load_products_from_excel(PACKAGE_DIR / "mock_products.xlsx", source="mock")
    if not products:
        raise AssertionError("Excel product normalization returned no products")
    first = products[0]
    for field in ["product_id", "product_name", "category"]:
        if not first.get(field):
            raise AssertionError(f"normalized Excel product missing {field}: {first}")

    print("Excel loader smoke test passed.")
    print(f"sheet_name: {sheet_name}")
    print(f"rows: {len(rows)}")


if __name__ == "__main__":
    main()
