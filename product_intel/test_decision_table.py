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


EXPECTED_ACTION_TEXT = {
    "main_push": "今天可主推",
    "small_test": "小样本测试",
    "hold": "暂缓",
    "reject": "不建议",
}


def validate_rows(rows: list[dict]) -> None:
    if not rows:
        raise AssertionError("decision rows must not be empty")
    for index, row in enumerate(rows, start=1):
        for field in [
            "product_name",
            "opportunity_score",
            "decision",
            "dimension_summary",
            "strongest_dimensions",
            "weakest_dimensions",
            "main_push_reason",
            "next_action",
        ]:
            if row.get(field) in ("", None):
                raise AssertionError(f"row {index} missing {field}: {row}")
        expected_action = EXPECTED_ACTION_TEXT[row["decision"]]
        if expected_action not in row["next_action"]:
            raise AssertionError(f"row {index} decision and next_action conflict: {row}")


def main() -> None:
    products = load_products_from_csv(MOCK_CSV_PATH)
    batch = build_batch_fact_sheets(products)
    rows = build_decision_rows(batch["items"])
    validate_rows(rows)
    final_decisions = {
        item["product"]["product_id"]: item["dimension_scores"]["final_test_decision"]["decision"]
        for item in batch["items"]
    }
    for row in rows:
        if row["decision"] != final_decisions[row["product_id"]]:
            raise AssertionError(f"row decision differs from final_test_decision: {row}")
    rows_by_name = {row["product_name"]: row for row in rows}
    treadmill = rows_by_name["Foldable Home Walking Treadmill"]
    if not treadmill["risk_flags"]:
        raise AssertionError(f"treadmill must expose risk flags: {treadmill}")
    serum = rows_by_name["Hydrating Glow Face Serum"]
    if "功效表达需谨慎" not in serum["risk_flags"] or "外部趋势证据" not in serum["risk_flags"]:
        raise AssertionError(f"beauty serum risks are incomplete: {serum}")
    snack = rows_by_name["Crispy Chocolate Wafer Snack Pack"]
    if "食品购买痛点偏弱" not in snack["risk_flags"] or "食品利润窗口偏弱" not in snack["risk_flags"]:
        raise AssertionError(f"snack risks are incomplete: {snack}")
    cat_bowl = rows_by_name["Raised Double Cat Bowl"]
    if cat_bowl["risk_flags"]:
        raise AssertionError(f"main-push cat bowl should not be over-flagged: {cat_bowl}")

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
