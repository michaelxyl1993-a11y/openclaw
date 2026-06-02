"""Tests for Product Intel v1.12 local Feishu operations handoff pack."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from .feishu_ops_handoff_pack import (
    VERSION,
    build_brief,
    build_handoff_message,
    build_manifest,
    load_final_rows,
    load_summary,
    write_handoff_pack,
)


PACKAGE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PACKAGE_DIR / "output_next_round"
FINAL_TABLE = OUTPUT_DIR / "final_ops_decision_table.csv"
SUMMARY = OUTPUT_DIR / "final_ops_action_summary.json"


class FeishuOpsHandoffPackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = load_final_rows(FINAL_TABLE)
        self.summary = load_summary(SUMMARY)

    def test_utf8_sig_final_table_is_readable(self) -> None:
        self.assertEqual(len(self.rows), 12)
        self.assertIn("product_id", self.rows[0])
        with FINAL_TABLE.open(encoding="utf-8-sig", newline="") as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), 12)

    def test_generates_four_non_empty_handoff_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths, _, _ = write_handoff_pack(
                self.rows, self.summary, FINAL_TABLE, SUMMARY, temp_dir
            )
            self.assertEqual(set(paths), {"handoff_message", "manifest", "brief", "checklist"})
            for path in paths.values():
                self.assertTrue(path.exists())
                self.assertGreater(path.stat().st_size, 0)

    def test_manifest_is_ready_and_requires_manual_review(self) -> None:
        manifest = build_manifest(self.rows, FINAL_TABLE, SUMMARY, OUTPUT_DIR)
        self.assertEqual(manifest["version"], VERSION)
        self.assertEqual(manifest["total_products"], 12)
        self.assertTrue(manifest["ready_for_feishu_upload"])
        self.assertTrue(manifest["requires_manual_review"])

    def test_manifest_manual_review_products_contains_manual_3(self) -> None:
        manifest = build_manifest(self.rows, FINAL_TABLE, SUMMARY, OUTPUT_DIR)
        self.assertEqual(
            [item["product_id"] for item in manifest["manual_review_products"]],
            ["manual-3"],
        )

    def test_message_contains_manual_3_and_challenge_warning(self) -> None:
        brief = build_brief(self.rows, OUTPUT_DIR)
        message = build_handoff_message(self.rows, brief)
        self.assertIn("manual-3", message)
        self.assertIn("规则建议 main_push，但 LLM Judge challenge", message)

    def test_brief_counts_are_consistent(self) -> None:
        brief = build_brief(self.rows, OUTPUT_DIR)
        self.assertEqual(brief["total_products"], 12)
        self.assertEqual(brief["today_executable_count"], 8)
        self.assertEqual(brief["human_review_first_count"], 1)
        self.assertEqual(brief["hold_count"], 3)
        self.assertEqual(brief["challenge_count"], 1)
        self.assertEqual(
            brief["today_executable_count"]
            + brief["human_review_first_count"]
            + brief["hold_count"],
            brief["total_products"],
        )

    def test_module_does_not_call_openai_or_feishu(self) -> None:
        source = (PACKAGE_DIR / "feishu_ops_handoff_pack.py").read_text(encoding="utf-8")
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("requests.", source)
        self.assertNotIn("lark", source.lower())

    def test_input_final_table_is_not_modified(self) -> None:
        before = FINAL_TABLE.read_bytes()
        with tempfile.TemporaryDirectory() as temp_dir:
            write_handoff_pack(self.rows, self.summary, FINAL_TABLE, SUMMARY, temp_dir)
        self.assertEqual(FINAL_TABLE.read_bytes(), before)

    def test_manifest_output_files_contains_four_paths(self) -> None:
        manifest = build_manifest(self.rows, FINAL_TABLE, SUMMARY, OUTPUT_DIR)
        self.assertEqual(len(manifest["output_files"]), 4)

    def test_attachment_paths_contains_required_files(self) -> None:
        brief = build_brief(self.rows, OUTPUT_DIR)
        names = {Path(path).name for path in brief["attachment_paths"]}
        self.assertEqual(
            names,
            {
                "final_ops_decision_table.csv",
                "final_ops_decision_table.md",
                "final_ops_action_summary.json",
                "final_ops_action_summary.md",
                "final_challenge_products.csv",
                "final_review_note.md",
            },
        )

    def test_written_brief_json_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths, _, _ = write_handoff_pack(
                self.rows, self.summary, FINAL_TABLE, SUMMARY, temp_dir
            )
            brief = json.loads(paths["brief"].read_text(encoding="utf-8"))
            self.assertEqual(brief["human_review_products"][0]["product_id"], "manual-3")


if __name__ == "__main__":
    unittest.main()

