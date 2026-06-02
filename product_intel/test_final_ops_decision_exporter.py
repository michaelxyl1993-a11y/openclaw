"""Tests for Product Intel v1.11 final operations decision exporter."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from .final_ops_decision_exporter import (
    OUTPUT_FIELDS,
    build_final_rows,
    build_summary,
    load_review_rows,
    write_outputs,
)


PACKAGE_DIR = Path(__file__).resolve().parent
INPUT_CSV = PACKAGE_DIR / "output_next_round" / "all_evidence_with_real_llm_review.csv"


class FinalOpsDecisionExporterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.input_rows = load_review_rows(INPUT_CSV)
        self.final_rows = build_final_rows(self.input_rows)
        self.by_id = {row["product_id"]: row for row in self.final_rows}

    def test_twelve_input_rows_generate_twelve_final_rows(self) -> None:
        self.assertEqual(len(self.input_rows), 12)
        self.assertEqual(len(self.final_rows), 12)

    def test_manual_3_is_human_review_first(self) -> None:
        row = self.by_id["manual-3"]
        self.assertEqual(row["final_ops_action"], "human_review_first")
        self.assertEqual(row["final_ops_priority"], "P0_review")

    def test_agree_small_test_is_p1_small_test(self) -> None:
        row = self.by_id["echo-1"]
        self.assertEqual(row["llm_review_result"], "agree")
        self.assertEqual(row["rule_decision"], "small_test")
        self.assertEqual(row["final_ops_priority"], "P1_small_test")

    def test_agree_hold_is_p2_hold(self) -> None:
        row = self.by_id["fm-3"]
        self.assertEqual(row["llm_review_result"], "agree")
        self.assertEqual(row["rule_decision"], "hold")
        self.assertEqual(row["final_ops_priority"], "P2_hold")

    def test_rule_fields_are_preserved(self) -> None:
        source_by_id = {row["product_id"]: row for row in self.input_rows}
        for row in self.final_rows:
            source = source_by_id[row["product_id"]]
            self.assertEqual(row["rule_decision"], source["rule_decision"])
            self.assertEqual(row["opportunity_score"], source["opportunity_score"])
            self.assertEqual(row["next_action"], source["next_action"])

    def test_outputs_exist_and_are_non_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths, _ = write_outputs(self.final_rows, temp_dir)
            self.assertEqual(
                set(paths),
                {"final_table_csv", "final_table_md", "action_summary_json", "action_summary_md"},
            )
            for path in paths.values():
                self.assertTrue(path.exists())
                self.assertGreater(path.stat().st_size, 0)

    def test_summary_contains_manual_3_challenge(self) -> None:
        summary = build_summary(self.final_rows)
        self.assertEqual(summary["human_review_first_count"], 1)
        self.assertEqual(summary["challenge_products"][0]["product_id"], "manual-3")
        self.assertIn("不能直接放大", summary["recommended_today_plan"]["manual_3_note"])

    def test_exporter_has_no_openai_dependency(self) -> None:
        module_text = (PACKAGE_DIR / "final_ops_decision_exporter.py").read_text(encoding="utf-8")
        self.assertNotIn("openai", module_text.lower())
        self.assertNotIn("run_openai_llm_judge", module_text)

    def test_utf8_sig_csv_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "input.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(self.input_rows[0]))
                writer.writeheader()
                writer.writerow(self.input_rows[0])
            rows = load_review_rows(path)
            self.assertEqual(rows[0]["product_id"], self.input_rows[0]["product_id"])
            self.assertIn("product_id", rows[0])

    def test_action_counts_equal_total(self) -> None:
        summary = build_summary(self.final_rows)
        self.assertEqual(
            sum(summary["final_ops_action_counts"].values()),
            summary["total_products"],
        )
        self.assertEqual(summary["total_products"], 12)

    def test_output_columns_are_stable(self) -> None:
        self.assertIn("final_ops_action", OUTPUT_FIELDS)
        self.assertIn("final_ops_priority", OUTPUT_FIELDS)
        self.assertIn("final_ops_reason", OUTPUT_FIELDS)


if __name__ == "__main__":
    unittest.main()

