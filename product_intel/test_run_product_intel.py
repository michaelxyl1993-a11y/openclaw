"""Smoke test for the Product Intel CLI runner."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .manager_payload import VERSION
from .run_product_intel import run_product_intel


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = PROJECT_ROOT / "product_intel"
OUTPUT_DIR = PACKAGE_DIR / "output"


def assert_common_outputs(result: dict, expected_file_type: str) -> dict:
    output_files = result["output_files"]
    csv_path = Path(output_files["decision_csv"])
    md_path = Path(output_files["decision_md"])
    json_path = Path(output_files["manager_json"])
    profile_json_path = Path(output_files["csv_profile_json"])
    profile_md_path = Path(output_files["csv_profile_md"])

    for path in [csv_path, md_path, json_path, profile_json_path, profile_md_path]:
        if not path.exists():
            raise AssertionError(f"output file missing: {path}")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if payload.get("version") != VERSION:
        raise AssertionError(f"invalid payload version: {payload.get('version')}")
    if not payload.get("products"):
        raise AssertionError("manager payload has no products")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        raise AssertionError("decision table CSV has no rows")

    if not md_path.read_text(encoding="utf-8").strip():
        raise AssertionError("decision table markdown is empty")
    profile = json.loads(profile_json_path.read_text(encoding="utf-8"))
    if not profile.get("source_detected"):
        raise AssertionError("profile JSON missing source_detected")
    if profile.get("detected_file_type") != expected_file_type:
        raise AssertionError(f"expected detected_file_type={expected_file_type}, got {profile.get('detected_file_type')}")
    if expected_file_type == "xlsx" and not profile.get("detected_sheet_name"):
        raise AssertionError("xlsx profile missing detected_sheet_name")
    if not profile.get("mapped_fields"):
        raise AssertionError("profile JSON missing mapped_fields")
    return payload


def assert_mock_decisions(payload: dict) -> None:
    meta = payload.get("meta", {})
    actual_counts = {
        "main_push_count": meta.get("main_push_count"),
        "small_test_count": meta.get("small_test_count"),
        "hold_count": meta.get("hold_count"),
        "reject_count": meta.get("reject_count"),
    }
    expected_counts = {
        "main_push_count": 3,
        "small_test_count": 4,
        "hold_count": 1,
        "reject_count": 0,
    }
    if actual_counts != expected_counts:
        raise AssertionError(f"mock decision distribution changed: expected {expected_counts}, got {actual_counts}")
    products = {item["product_name"]: item for item in payload.get("products", [])}
    for name in ["Raised Double Cat Bowl", "Waterproof Cat Litter Mat", "Portable Mini Handheld Fan"]:
        decision = products.get(name, {}).get("decision")
        if decision not in {"main_push", "small_test"}:
            raise AssertionError(f"expected {name} to be main_push/small_test, got {decision}")
    treadmill_decision = products.get("Foldable Home Walking Treadmill", {}).get("decision")
    if treadmill_decision not in {"hold", "reject"}:
        raise AssertionError(f"expected treadmill hold/reject, got {treadmill_decision}")
    snack_decision = products.get("Crispy Chocolate Wafer Snack Pack", {}).get("decision")
    if snack_decision not in {"small_test", "hold"}:
        raise AssertionError(f"expected snack small_test/hold, got {snack_decision}")


def main() -> None:
    csv_result = run_product_intel(
        input_path=PACKAGE_DIR / "mock_products.csv",
        source="mock",
        market="de",
        output_dir=OUTPUT_DIR,
        output_format="all",
    )
    csv_payload = assert_common_outputs(csv_result, "csv")
    assert_mock_decisions(csv_payload)

    xlsx_result = run_product_intel(
        input_path=PACKAGE_DIR / "mock_products.xlsx",
        source="mock",
        market="de",
        output_dir=OUTPUT_DIR,
        output_format="all",
    )
    xlsx_payload = assert_common_outputs(xlsx_result, "xlsx")
    assert_mock_decisions(xlsx_payload)

    print("Product Intel runner smoke test passed.")
    print(f"CSV products: {len(csv_payload['products'])}")
    print(f"XLSX products: {len(xlsx_payload['products'])}")


if __name__ == "__main__":
    main()
