"""Smoke tests for the Product Intel service handler."""

from __future__ import annotations

import json
from pathlib import Path

from .service_handler import run_product_intel_job


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOCK_CSV = PROJECT_ROOT / "product_intel" / "mock_products.csv"
OUTPUT_DIR = PROJECT_ROOT / "product_intel" / "output"


def assert_file(path_value: str, label: str) -> Path:
    path = Path(path_value)
    if not path.exists():
        raise AssertionError(f"{label} missing: {path}")
    return path


def main() -> None:
    profile_result = run_product_intel_job(
        input_path=str(MOCK_CSV),
        source="auto",
        market="de",
        output_dir=str(OUTPUT_DIR),
        profile_only=True,
    )
    if not profile_result.get("ok"):
        raise AssertionError(f"profile_only job failed: {profile_result.get('errors')}")
    if not profile_result.get("summary_text"):
        raise AssertionError("profile_only summary_text is empty")
    profile_files = profile_result.get("output_files", {})
    assert_file(profile_files.get("csv_profile_json", ""), "csv_profile_json")
    assert_file(profile_files.get("csv_profile_md", ""), "csv_profile_md")

    full_result = run_product_intel_job(
        input_path=str(MOCK_CSV),
        source="auto",
        market="de",
        output_dir=str(OUTPUT_DIR),
        limit=7,
        profile_only=False,
    )
    if not full_result.get("ok"):
        raise AssertionError(f"full_run job failed: {full_result.get('errors')}")
    if not full_result.get("summary_text"):
        raise AssertionError("full_run summary_text is empty")
    full_files = full_result.get("output_files", {})
    assert_file(full_files.get("csv_profile_json", ""), "csv_profile_json")
    assert_file(full_files.get("csv_profile_md", ""), "csv_profile_md")
    assert_file(full_files.get("decision_table_csv", ""), "decision_table_csv")
    assert_file(full_files.get("decision_table_md", ""), "decision_table_md")
    manager_json = assert_file(full_files.get("manager_payload_json", ""), "manager_payload_json")
    payload = json.loads(manager_json.read_text(encoding="utf-8"))
    if not payload.get("products"):
        raise AssertionError("manager payload has no products")

    decision_summary = full_result.get("decision_summary", {})
    if decision_summary.get("total_products", 0) <= 0:
        raise AssertionError("decision_summary total_products must be > 0")
    if not decision_summary.get("top_products"):
        raise AssertionError("decision_summary top_products is empty")

    missing_result = run_product_intel_job(
        input_path=str(PROJECT_ROOT / "product_intel" / "missing.csv"),
        source="auto",
        market="de",
        output_dir=str(OUTPUT_DIR),
    )
    if missing_result.get("ok"):
        raise AssertionError("missing input job should fail")
    if not missing_result.get("errors"):
        raise AssertionError("missing input job should include errors")

    print("Product Intel service handler smoke test passed.")
    print(full_result["summary_text"])


if __name__ == "__main__":
    main()
