"""Smoke test for Product Intel manager payload output."""

from __future__ import annotations

import json
from pathlib import Path

from .batch_fact_sheet import build_batch_fact_sheets
from .csv_loader import load_products_from_csv
from .export_manager_payload import save_manager_payload_json
from .manager_payload import VERSION, build_manager_payload


PACKAGE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PACKAGE_DIR / "output"
MOCK_CSV_PATH = PACKAGE_DIR / "mock_products.csv"


def validate_payload(payload: dict) -> None:
    if payload.get("version") != VERSION:
        raise AssertionError(f"invalid payload version: {payload.get('version')}")
    products = payload.get("products", [])
    if not products:
        raise AssertionError("payload products must not be empty")
    for index, product in enumerate(products, start=1):
        for field in ["product_name", "opportunity_score", "decision", "manager_instruction", "routing"]:
            if product.get(field) in ("", None):
                raise AssertionError(f"product {index} missing {field}: {product}")
        if not isinstance(product.get("routing"), dict):
            raise AssertionError(f"product {index} routing must be a dict")


def main() -> None:
    products = load_products_from_csv(MOCK_CSV_PATH)
    batch = build_batch_fact_sheets(products)
    payload = build_manager_payload(batch["items"], meta={"source": "mock_products_csv"})
    validate_payload(payload)

    output_path = save_manager_payload_json(payload, OUTPUT_DIR / "mock_manager_payload.json")
    if not output_path.exists():
        raise AssertionError(f"manager payload JSON was not created: {output_path}")
    reloaded = json.loads(output_path.read_text(encoding="utf-8"))
    validate_payload(reloaded)

    meta = payload["meta"]
    print(f"total_products: {meta['total_products']}")
    print(
        "counts: "
        f"main_push={meta['main_push_count']} "
        f"small_test={meta['small_test_count']} "
        f"hold={meta['hold_count']} "
        f"reject={meta['reject_count']}"
    )
    print("Top 5 manager payload products:")
    for product in payload["products"][:5]:
        print(
            f"- {product['product_name']} | "
            f"score={product['opportunity_score']} | "
            f"decision={product['decision']}"
        )
    print(f"JSON: {output_path}")
    print("Manager payload smoke test passed.")


if __name__ == "__main__":
    main()
