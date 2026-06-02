"""Tests for Product Intel v1.15 opt-in single-file Feishu upload adapter."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from .feishu_upload_adapter_real import (
    load_dry_run_plan,
    run_single_upload,
    write_receipt,
)


PACKAGE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PACKAGE_DIR / "output_next_round"
PLAN = OUTPUT_DIR / "feishu_upload_dry_run_plan.json"
MOCK_RECEIPT = OUTPUT_DIR / "feishu_upload_mock_receipt.json"


class FailIfCalledClient:
    def upload_file(self, **kwargs):
        raise AssertionError("Real Feishu API must not be called.")


class FakeSuccessClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def upload_file(self, **kwargs):
        self.calls.append(kwargs)
        return "fake_file_token_123"


class FeishuUploadAdapterRealTest(unittest.TestCase):
    def setUp(self) -> None:
        self.plan = load_dry_run_plan(PLAN)

    def test_default_disabled_never_calls_real_api(self) -> None:
        receipt = run_single_upload(self.plan, 0, environ={}, client=FailIfCalledClient())
        self.assertFalse(receipt["real_feishu_api_called"])
        self.assertFalse(receipt["real_message_sent"])
        self.assertEqual(receipt["upload_status"], "disabled")
        self.assertIsNone(receipt["file_token"])

    def test_enabled_env_must_equal_true(self) -> None:
        receipt = run_single_upload(
            self.plan,
            0,
            environ={"PRODUCT_INTEL_REAL_FEISHU_UPLOAD_ENABLED": "false"},
            client=FailIfCalledClient(),
        )
        self.assertFalse(receipt["real_feishu_api_called"])
        self.assertEqual(receipt["upload_status"], "disabled")

    def test_missing_plan_and_not_ready_plan_are_blocked(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not exist"):
            load_dry_run_plan("/private/tmp/missing-product-intel-plan.json")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "not-ready.json"
            path.write_text('{"ready_for_upload": false, "attachment_items": []}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not ready_for_upload"):
                load_dry_run_plan(path)

    def test_attachment_index_out_of_range_is_blocked(self) -> None:
        with self.assertRaisesRegex(ValueError, "out of range"):
            run_single_upload(self.plan, 999, environ={})

    def test_missing_or_empty_attachment_is_blocked(self) -> None:
        missing_plan = copy.deepcopy(self.plan)
        missing_plan["attachment_items"][0]["path"] = "/private/tmp/missing-product-intel-file.csv"
        with self.assertRaisesRegex(ValueError, "does not exist"):
            run_single_upload(missing_plan, 0, environ={})
        with tempfile.TemporaryDirectory() as temp_dir:
            empty = Path(temp_dir) / "empty.csv"
            empty.write_bytes(b"")
            empty_plan = copy.deepcopy(self.plan)
            empty_plan["attachment_items"][0]["path"] = str(empty)
            with self.assertRaisesRegex(ValueError, "is empty"):
                run_single_upload(empty_plan, 0, environ={})

    def test_fake_client_upload_success_returns_file_token(self) -> None:
        client = FakeSuccessClient()
        receipt = run_single_upload(
            self.plan,
            0,
            environ={
                "PRODUCT_INTEL_REAL_FEISHU_UPLOAD_ENABLED": "true",
                "FEISHU_APP_ID": "fake-app-id",
                "FEISHU_APP_SECRET": "fake-app-secret",
            },
            client=client,
        )
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(receipt["file_token"], "fake_file_token_123")
        self.assertEqual(receipt["upload_status"], "uploaded")
        self.assertTrue(receipt["real_feishu_api_called"])
        self.assertFalse(receipt["real_message_sent"])

    def test_enabled_without_credentials_returns_error_without_api_call(self) -> None:
        receipt = run_single_upload(
            self.plan,
            0,
            environ={"PRODUCT_INTEL_REAL_FEISHU_UPLOAD_ENABLED": "true"},
            client=FailIfCalledClient(),
        )
        self.assertFalse(receipt["real_feishu_api_called"])
        self.assertEqual(receipt["upload_status"], "error")
        self.assertIn("FEISHU_APP_ID", receipt["error"])

    def test_writes_disabled_receipt(self) -> None:
        receipt = run_single_upload(self.plan, 0, environ={})
        with tempfile.TemporaryDirectory() as temp_dir:
            path = write_receipt(receipt, temp_dir)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["upload_status"], "disabled")
            self.assertFalse(saved["real_feishu_api_called"])

    def test_module_does_not_call_openai_or_send_messages(self) -> None:
        source = (PACKAGE_DIR / "feishu_upload_adapter_real.py").read_text(encoding="utf-8")
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("/im/v1/messages", source)
        self.assertNotIn("reply_feishu", source)

    def test_does_not_modify_v1_13_or_v1_14_outputs(self) -> None:
        plan_before = PLAN.read_bytes()
        mock_before = MOCK_RECEIPT.read_bytes()
        run_single_upload(self.plan, 0, environ={})
        self.assertEqual(PLAN.read_bytes(), plan_before)
        self.assertEqual(MOCK_RECEIPT.read_bytes(), mock_before)

    def test_receipt_never_contains_credentials(self) -> None:
        client = FakeSuccessClient()
        receipt = run_single_upload(
            self.plan,
            0,
            environ={
                "PRODUCT_INTEL_REAL_FEISHU_UPLOAD_ENABLED": "true",
                "FEISHU_APP_ID": "fake-app-id",
                "FEISHU_APP_SECRET": "fake-app-secret",
            },
            client=client,
        )
        serialized = json.dumps(receipt)
        self.assertNotIn("fake-app-id", serialized)
        self.assertNotIn("fake-app-secret", serialized)


if __name__ == "__main__":
    unittest.main()

