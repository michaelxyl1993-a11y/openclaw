"""Tests for Product Intel v1.16 Feishu message send adapter mock."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from .feishu_message_send_adapter_mock import (
    MODE,
    build_preview,
    build_send_plan,
    load_handoff_message,
    load_mock_tokens,
    load_upload_receipt,
    write_outputs,
)


PACKAGE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PACKAGE_DIR / "output_next_round"
MESSAGE = OUTPUT_DIR / "feishu_ops_handoff_message.md"
UPLOAD_RECEIPT = OUTPUT_DIR / "feishu_real_upload_single_receipt.json"
MOCK_TOKEN_CSV = OUTPUT_DIR / "feishu_upload_mock_attachment_tokens.csv"


class FeishuMessageSendAdapterMockTest(unittest.TestCase):
    def setUp(self) -> None:
        self.message = load_handoff_message(MESSAGE)
        self.upload_receipt = load_upload_receipt(UPLOAD_RECEIPT)
        self.mock_tokens = load_mock_tokens(MOCK_TOKEN_CSV)
        self.plan = build_send_plan(self.message, self.upload_receipt, self.mock_tokens)

    def test_reads_handoff_message(self) -> None:
        self.assertIn("Product Intel 选品虾｜最终运营交付", self.message)

    def test_reads_real_upload_receipt(self) -> None:
        self.assertEqual(self.upload_receipt["mode"], "feishu_upload_adapter_real_v1.15")

    def test_redacted_real_token_falls_back_to_mock_tokens(self) -> None:
        self.assertFalse(self.plan["real_file_token_available"])
        self.assertTrue(self.plan["using_mock_tokens_for_preview"])
        self.assertEqual(len(self.plan["attachment_tokens"]), len(self.mock_tokens))
        self.assertTrue(
            all(item["token_source"] == "mock_token_fallback" for item in self.plan["attachment_tokens"])
        )

    def test_available_real_token_is_preferred(self) -> None:
        receipt = {**self.upload_receipt, "upload_status": "uploaded", "file_token": "real-file-token"}
        plan = build_send_plan(self.message, receipt, self.mock_tokens)
        self.assertTrue(plan["real_file_token_available"])
        self.assertFalse(plan["using_mock_tokens_for_preview"])
        self.assertEqual(plan["attachment_tokens"][0]["file_token"], "real-file-token")

    def test_preview_contains_manual_3_and_mock_warning(self) -> None:
        preview = build_preview(self.message, self.plan)
        self.assertIn("manual-3", preview)
        self.assertIn("不会发送真实飞书消息", preview)
        self.assertIn("mock_file_token_", preview)

    def test_plan_disables_real_message_api(self) -> None:
        self.assertEqual(self.plan["mode"], MODE)
        self.assertFalse(self.plan["real_message_send_enabled"])
        self.assertFalse(self.plan["real_feishu_message_api_called"])
        self.assertFalse(self.plan["real_message_sent"])
        self.assertEqual(self.plan["send_status"], "mock_only")

    def test_generates_three_output_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths, receipt = write_outputs(
                self.plan,
                build_preview(self.message, self.plan),
                temp_dir,
            )
            self.assertEqual(
                set(paths),
                {"send_plan_json", "message_preview_md", "send_receipt_json"},
            )
            for path in paths.values():
                self.assertTrue(path.exists())
                self.assertGreater(path.stat().st_size, 0)
            self.assertFalse(receipt["real_message_sent"])
            self.assertEqual(receipt["send_status"], "mock_only")

    def test_module_has_no_openai_or_real_feishu_message_dependency(self) -> None:
        source = (PACKAGE_DIR / "feishu_message_send_adapter_mock.py").read_text(encoding="utf-8")
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("requests.", source)
        self.assertNotIn("/im/v1/messages", source)
        self.assertNotIn("urllib", source.lower())

    def test_does_not_modify_v1_15_upload_receipt(self) -> None:
        before_bytes = UPLOAD_RECEIPT.read_bytes()
        before_receipt = copy.deepcopy(self.upload_receipt)
        with tempfile.TemporaryDirectory() as temp_dir:
            write_outputs(self.plan, build_preview(self.message, self.plan), temp_dir)
        self.assertEqual(UPLOAD_RECEIPT.read_bytes(), before_bytes)
        self.assertEqual(self.upload_receipt, before_receipt)

    def test_receipt_has_error_null(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            _, receipt = write_outputs(
                self.plan,
                build_preview(self.message, self.plan),
                temp_dir,
            )
        self.assertIsNone(receipt["error"])
        self.assertFalse(receipt["real_feishu_message_api_called"])

    def test_saved_plan_is_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths, _ = write_outputs(
                self.plan,
                build_preview(self.message, self.plan),
                temp_dir,
            )
            saved = json.loads(paths["send_plan_json"].read_text(encoding="utf-8"))
        self.assertTrue(saved["message_ready"])
        self.assertTrue(saved["attachment_ready"])


if __name__ == "__main__":
    unittest.main()

