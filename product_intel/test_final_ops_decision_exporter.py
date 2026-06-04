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
    summary_markdown,
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
        notes = summary["recommended_today_plan"]["challenge_notes"]
        self.assertEqual(notes[0]["product_id"], "manual-3")
        self.assertIn("LLM Judge challenge", notes[0]["note"])
        self.assertNotIn("manual_3_note", summary)
        self.assertNotIn("manual_3_note", summary["recommended_today_plan"])

    def test_no_challenge_has_no_stale_manual_3_note(self) -> None:
        rows = [
            row
            for row in self.final_rows
            if row["product_id"].startswith(("echo-", "fm-"))
            and row["llm_review_result"] != "challenge"
        ]
        summary = build_summary(rows)
        text = summary_markdown(summary)
        self.assertNotIn("manual-3", text)
        self.assertNotIn("手工桌面风扇", text)
        self.assertNotIn("manual_3_note", text)
        self.assertIn("## 特殊说明", text)
        self.assertIn("- 无", text)

    def test_old_output_dir_does_not_pollute_new_summary(self) -> None:
        rows = [
            row
            for row in self.final_rows
            if row["product_id"].startswith(("echo-", "fm-"))
            and row["llm_review_result"] != "challenge"
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            stale_json = Path(temp_dir) / "final_ops_action_summary.json"
            stale_md = Path(temp_dir) / "final_ops_action_summary.md"
            stale_json.write_text('{"manual_3_note":"manual-3"}', encoding="utf-8")
            stale_md.write_text("manual-3 手工桌面风扇", encoding="utf-8")
            paths, summary = write_outputs(rows, temp_dir)
            new_json = paths["action_summary_json"].read_text(encoding="utf-8")
            new_md = paths["action_summary_md"].read_text(encoding="utf-8")
        self.assertNotIn("manual-3", new_json)
        self.assertNotIn("手工桌面风扇", new_json)
        self.assertNotIn("manual_3_note", new_json)
        self.assertNotIn("manual-3", new_md)
        self.assertNotIn("手工桌面风扇", new_md)
        self.assertEqual(summary["challenge_products"], [])

    def test_markdown_title_is_not_stale_v1_11(self) -> None:
        summary = build_summary(self.final_rows)
        text = summary_markdown(summary)
        self.assertIn("# Product Intel Final Ops Action Summary", text)
        self.assertNotIn("v1.11 Final Ops Action Summary", text)

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
