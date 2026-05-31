"""Smoke test for Product Intel decision table exports."""

from __future__ import annotations

from pathlib import Path

from .batch_fact_sheet import build_batch_fact_sheets
from .csv_loader import load_products_from_csv
from .decision_table import build_decision_rows
from .export_decision_table import save_decision_csv, save_decision_markdown


PACKAGE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PACKAGE_DIR / "output"
MOCK_CSV_PATH = PACKAGE_DIR / "mock_products.csv"


def validate_rows(rows: list[dict]) -> None:
    if not rows:
        raise AssertionError("decision rows must not be empty")
    for index, row in enumerate(rows, start=1):
        for field in ["product_name", "opportunity_score", "decision", "next_action"]:
            if row.get(field) in ("", None):
                raise AssertionError(f"row {index} missing {field}: {row}")


def main() -> None:
    products = load_products_from_csv(MOCK_CSV_PATH)
    batch = build_batch_fact_sheets(products)
    rows = build_decision_rows(batch["items"])
    validate_rows(rows)

    csv_path = save_decision_csv(rows, OUTPUT_DIR / "mock_decision_table.csv")
    md_path = save_decision_markdown(rows, OUTPUT_DIR / "mock_decision_table.md")
    if not csv_path.exists():
        raise AssertionError(f"CSV output was not created: {csv_path}")
    if not md_path.exists():
        raise AssertionError(f"Markdown output was not created: {md_path}")

    print("Product Intel decision table Top 5:")
    for row in rows[:5]:
        print(
            f"- #{row['rank']} {row['opportunity_score']} {row['decision']} | "
            f"{row['product_name']} | {row['suggested_format']} | {row['next_action']}"
        )
    print(f"CSV: {csv_path}")
    print(f"Markdown: {md_path}")
    print(f"Decision table smoke test passed: {len(rows)} rows.")


if __name__ == "__main__":
    main()
