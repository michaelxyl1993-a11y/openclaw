"""Tests for Product Intel v1.14 Feishu upload adapter mock."""

from __future__ import annotations

import csv
import copy
import json
import tempfile
import unittest
from pathlib import Path

from .feishu_upload_adapter_mock import (
    MODE,
    build_message_preview,
    build_mock_attachment_tokens,
    build_receipt,
    load_dry_run_plan,
    stable_mock_file_token,
    write_outputs,
)


PACKAGE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PACKAGE_DIR / "output_next_round"
PLAN = OUTPUT_DIR / "feishu_upload_dry_run_plan.json"
MESSAGE = OUTPUT_DIR / "feishu_ops_handoff_message.md"


class FeishuUploadAdapterMockTest(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = load_dry_run_plan(PLAN)
        self.tokens = build_mock_attachment_tokens(self.plan)

    def test_reads_v1_13_dry_run_plan(self) -> None:
        self.assertTrue(self.plan["ready_for_upload"])
        self.assertEqual(self.plan["total_attachments"], 6)

    def test_ready_plan_builds_mock_receipt(self) -> None:
        receipt = build_receipt(self.tokens, "preview.md")
        self.assertEqual(receipt["mode"], MODE)
        self.assertTrue(receipt["ready_for_mock_send"])

    def test_not_ready_plan_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "blocked.json"
            path.write_text('{"ready_for_upload": false, "attachment_items": []}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not ready_for_upload"):
                load_dry_run_plan(path)

    def test_mock_token_is_stable(self) -> None:
        item = self.plan["attachment_items"][0]
        self.assertEqual(stable_mock_file_token(item), stable_mock_file_token(item))
        self.assertTrue(stable_mock_file_token(item).startswith("mock_file_token_"))

    def test_token_count_matches_total_attachments(self) -> None:
        self.assertEqual(len(self.tokens), self.plan["total_attachments"])

    def test_every_token_marks_real_upload_false(self) -> None:
        self.assertTrue(all(not item["real_upload_called"] for item in self.tokens))
        self.assertTrue(all(item["upload_status"] == "mock_uploaded" for item in self.tokens))

    def test_receipt_marks_real_actions_false(self) -> None:
        receipt = build_receipt(self.tokens, "preview.md")
        self.assertFalse(receipt["real_feishu_api_called"])
        self.assertFalse(receipt["real_message_sent"])

    def test_message_preview_contains_manual_3_and_tokens(self) -> None:
        preview = build_message_preview(MESSAGE, self.tokens)
        self.assertIn("manual-3", preview)
        self.assertIn("本次为 mock/sandbox，不会发送飞书消息", preview)
        self.assertIn(self.tokens[0]["mock_file_token"], preview)

    def test_generates_json_markdown_and_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths, receipt = write_outputs(self.plan, MESSAGE, temp_dir)
            self.assertEqual(
                set(paths),
                {"receipt_json", "message_preview_md", "attachment_tokens_csv"},
            )
            for path in paths.values():
                self.assertTrue(path.exists())
                self.assertGreater(path.stat().st_size, 0)
            with paths["attachment_tokens_csv"].open(
                encoding="utf-8-sig", newline=""
            ) as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), receipt["total_attachments"])

    def test_module_has_no_openai_or_real_feishu_dependencies(self) -> None:
        source = (PACKAGE_DIR / "feishu_upload_adapter_mock.py").read_text(encoding="utf-8")
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("requests.", source)
        self.assertNotIn("urllib", source.lower())
        self.assertNotIn("lark", source.lower())

    def test_does_not_modify_v1_13_plan_file(self) -> None:
        before_bytes = PLAN.read_bytes()
        before_plan = copy.deepcopy(self.plan)
        with tempfile.TemporaryDirectory() as temp_dir:
            write_outputs(self.plan, MESSAGE, temp_dir)
        self.assertEqual(PLAN.read_bytes(), before_bytes)
        self.assertEqual(self.plan, before_plan)

    def test_receipt_token_count_matches_mock_uploaded_count(self) -> None:
        receipt = build_receipt(self.tokens, "preview.md")
        self.assertEqual(receipt["total_attachments"], receipt["mock_uploaded_count"])
        self.assertEqual(len(receipt["attachment_tokens"]), receipt["mock_uploaded_count"])


if __name__ == "__main__":
    unittest.main()

