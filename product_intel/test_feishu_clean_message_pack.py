"""Tests for Product Intel v1.18 clean Feishu message pack."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from .feishu_clean_message_pack import (
    FORBIDDEN_TERMS,
    build_clean_message,
    build_plan,
    contains_forbidden_terms,
    load_final_rows,
    load_summary,
    write_outputs,
)


PACKAGE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PACKAGE_DIR / "output_next_round"
HANDOFF_MESSAGE = OUTPUT_DIR / "feishu_ops_handoff_message.md"
FINAL_SUMMARY = OUTPUT_DIR / "final_ops_action_summary.json"
FINAL_TABLE = OUTPUT_DIR / "final_ops_decision_table.csv"
V17_RECEIPT = OUTPUT_DIR / "feishu_message_send_real_receipt.json"


class FeishuCleanMessagePackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = load_final_rows(FINAL_TABLE)
        self.summary = load_summary(FINAL_SUMMARY)
        self.message = build_clean_message(self.rows, OUTPUT_DIR)
        self.plan = build_plan(
            self.message,
            HANDOFF_MESSAGE,
            FINAL_SUMMARY,
            FINAL_TABLE,
            OUTPUT_DIR,
        )

    def test_reads_final_ops_decision_table(self) -> None:
        self.assertEqual(len(self.rows), 12)

    def test_generates_three_non_empty_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_outputs(self.message, self.plan, temp_dir)
            self.assertEqual(set(paths), {"message_preview", "message_plan", "checklist"})
            for path in paths.values():
                self.assertTrue(path.exists())
                self.assertGreater(path.stat().st_size, 0)

    def test_message_contains_manual_3_and_challenge_warning(self) -> None:
        self.assertIn("manual-3 手工桌面风扇", self.message)
        self.assertIn("规则建议 main_push，但 LLM Judge challenge", self.message)

    def test_message_lists_eight_executable_products(self) -> None:
        for product_id in ["echo-1", "echo-2", "echo-3", "fm-1", "fm-2", "kalo-1", "kalo-3", "manual-1"]:
            self.assertIn(product_id, self.message)
        self.assertIn("今日可执行：8", self.message)

    def test_message_lists_three_hold_products(self) -> None:
        for product_id in ["fm-3", "kalo-2", "manual-2"]:
            self.assertIn(product_id, self.message)
        self.assertIn("暂缓补证：3", self.message)

    def test_message_has_no_forbidden_test_terms(self) -> None:
        self.assertFalse(contains_forbidden_terms(self.message))
        lowered = self.message.lower()
        for term in FORBIDDEN_TERMS:
            self.assertNotIn(term.lower(), lowered)

    def test_plan_ready_for_real_text_send(self) -> None:
        self.assertFalse(self.plan["contains_mock_terms"])
        self.assertTrue(self.plan["message_ready"])
        self.assertTrue(self.plan["ready_for_real_text_send"])
        self.assertFalse(self.plan["attachment_send_enabled"])
        self.assertEqual(self.plan["attachments_sent"], 0)

    def test_attachment_paths_are_listed_without_tokens(self) -> None:
        self.assertIn("final_ops_decision_table.csv", self.message)
        self.assertIn("final_ops_action_summary.md", self.message)
        self.assertIn("final_challenge_products.csv", self.message)
        self.assertIn("final_review_note.md", self.message)
        self.assertNotIn("token", self.message.lower())

    def test_module_has_no_openai_or_feishu_api_dependency(self) -> None:
        source = (PACKAGE_DIR / "feishu_clean_message_pack.py").read_text(encoding="utf-8")
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("requests.", source)
        self.assertNotIn("urllib", source.lower())
        self.assertNotIn("/im/v1/", source)

    def test_does_not_modify_v17_receipt(self) -> None:
        before = V17_RECEIPT.read_bytes()
        with tempfile.TemporaryDirectory() as temp_dir:
            write_outputs(self.message, self.plan, temp_dir)
        self.assertEqual(V17_RECEIPT.read_bytes(), before)

    def test_saved_plan_is_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_outputs(self.message, self.plan, temp_dir)
            saved = json.loads(paths["message_plan"].read_text(encoding="utf-8"))
        self.assertFalse(saved["contains_mock_terms"])
        self.assertTrue(saved["ready_for_real_text_send"])


if __name__ == "__main__":
    unittest.main()

