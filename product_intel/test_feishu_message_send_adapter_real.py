"""Tests for Product Intel v1.17 opt-in single Feishu text-message adapter."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from .feishu_message_send_adapter_real import (
    load_message_preview,
    load_mock_plan,
    run_single_text_send,
    write_receipt,
)


PACKAGE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PACKAGE_DIR / "output_next_round"
PREVIEW = OUTPUT_DIR / "feishu_message_send_mock_preview.md"
MOCK_PLAN = OUTPUT_DIR / "feishu_message_send_mock_plan.json"
MOCK_RECEIPT = OUTPUT_DIR / "feishu_message_send_mock_receipt.json"


class FailIfCalledClient:
    def send_text(self, **kwargs):
        raise AssertionError("Real Feishu message API must not be called.")


class FakeSuccessClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def send_text(self, **kwargs):
        self.calls.append(kwargs)
        return "om_secret_message_id"


class FeishuMessageSendAdapterRealTest(unittest.TestCase):
    def setUp(self) -> None:
        self.message = load_message_preview(PREVIEW)
        self.plan = load_mock_plan(MOCK_PLAN)

    def test_default_disabled_never_calls_real_message_api(self) -> None:
        receipt = run_single_text_send(
            self.message,
            self.plan,
            preview_path=PREVIEW,
            chat_id="TEST_CHAT_ID",
            environ={},
            client=FailIfCalledClient(),
        )
        self.assertFalse(receipt["real_feishu_message_api_called"])
        self.assertFalse(receipt["real_message_sent"])
        self.assertEqual(receipt["send_status"], "disabled")

    def test_enabled_env_must_equal_true(self) -> None:
        receipt = run_single_text_send(
            self.message,
            self.plan,
            preview_path=PREVIEW,
            chat_id="TEST_CHAT_ID",
            environ={"PRODUCT_INTEL_REAL_FEISHU_MESSAGE_SEND_ENABLED": "false"},
            client=FailIfCalledClient(),
        )
        self.assertFalse(receipt["real_feishu_message_api_called"])
        self.assertEqual(receipt["send_status"], "disabled")

    def test_missing_chat_id_is_blocked(self) -> None:
        receipt = run_single_text_send(
            self.message,
            self.plan,
            preview_path=PREVIEW,
            environ={
                "PRODUCT_INTEL_REAL_FEISHU_MESSAGE_SEND_ENABLED": "true",
                "FEISHU_APP_ID": "fake-id",
                "FEISHU_APP_SECRET": "fake-secret",
            },
            client=FailIfCalledClient(),
        )
        self.assertEqual(receipt["send_status"], "error")
        self.assertIn("chat_id", receipt["error"])
        self.assertFalse(receipt["real_feishu_message_api_called"])

    def test_missing_credentials_is_blocked(self) -> None:
        receipt = run_single_text_send(
            self.message,
            self.plan,
            preview_path=PREVIEW,
            chat_id="TEST_CHAT_ID",
            environ={"PRODUCT_INTEL_REAL_FEISHU_MESSAGE_SEND_ENABLED": "true"},
            client=FailIfCalledClient(),
        )
        self.assertEqual(receipt["send_status"], "error")
        self.assertIn("FEISHU_APP_ID", receipt["error"])
        self.assertFalse(receipt["real_feishu_message_api_called"])

    def test_missing_or_empty_preview_is_blocked(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not exist"):
            load_message_preview("/private/tmp/missing-product-intel-preview.md")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "empty.md"
            path.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "is empty"):
                load_message_preview(path)

    def test_fake_client_success_marks_sent_and_redacts_message_id(self) -> None:
        client = FakeSuccessClient()
        receipt = run_single_text_send(
            self.message,
            self.plan,
            preview_path=PREVIEW,
            chat_id="oc_test_chat_123456",
            environ={
                "PRODUCT_INTEL_REAL_FEISHU_MESSAGE_SEND_ENABLED": "true",
                "FEISHU_APP_ID": "fake-id",
                "FEISHU_APP_SECRET": "fake-secret",
            },
            client=client,
        )
        self.assertEqual(len(client.calls), 1)
        self.assertTrue(receipt["real_feishu_message_api_called"])
        self.assertTrue(receipt["real_message_sent"])
        self.assertEqual(receipt["send_status"], "sent")
        self.assertEqual(receipt["message_id"], "REDACTED_MESSAGE_ID")
        self.assertNotIn("oc_test_chat_123456", json.dumps(receipt))

    def test_attachments_are_always_disabled(self) -> None:
        receipt = run_single_text_send(
            self.message,
            self.plan,
            preview_path=PREVIEW,
            chat_id="TEST_CHAT_ID",
            environ={},
        )
        self.assertFalse(receipt["attachment_send_enabled"])
        self.assertEqual(receipt["attachments_sent"], 0)

    def test_writes_disabled_receipt(self) -> None:
        receipt = run_single_text_send(
            self.message,
            self.plan,
            preview_path=PREVIEW,
            chat_id="TEST_CHAT_ID",
            environ={},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_receipt(receipt, temp_dir)
            saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["send_status"], "disabled")
        self.assertFalse(saved["real_message_sent"])

    def test_module_does_not_call_openai_or_upload_files(self) -> None:
        source = (PACKAGE_DIR / "feishu_message_send_adapter_real.py").read_text(encoding="utf-8")
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("/im/v1/files", source)
        self.assertNotIn("files={", source)

    def test_does_not_modify_v1_16_outputs(self) -> None:
        preview_before = PREVIEW.read_bytes()
        plan_before = MOCK_PLAN.read_bytes()
        receipt_before = MOCK_RECEIPT.read_bytes()
        run_single_text_send(
            self.message,
            self.plan,
            preview_path=PREVIEW,
            chat_id="TEST_CHAT_ID",
            environ={},
        )
        self.assertEqual(PREVIEW.read_bytes(), preview_before)
        self.assertEqual(MOCK_PLAN.read_bytes(), plan_before)
        self.assertEqual(MOCK_RECEIPT.read_bytes(), receipt_before)

    def test_mock_plan_must_have_disabled_real_flags(self) -> None:
        bad_plan = {**self.plan, "real_message_sent": True}
        with self.assertRaisesRegex(ValueError, "sent flag must be false"):
            run_single_text_send(
                self.message,
                bad_plan,
                preview_path=PREVIEW,
                chat_id="TEST_CHAT_ID",
                environ={},
            )


if __name__ == "__main__":
    unittest.main()

