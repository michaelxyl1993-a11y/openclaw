"""Tests for v1.26 real Feishu final attachment file-message sender."""

from __future__ import annotations

import json
import unittest

from .feishu_final_attachment_file_send_real import run_file_message_send


def _public_receipt(count: int = 4) -> dict:
    return {
        "uploaded_files": [
            {
                "filename": f"file_{index}.csv",
                "upload_status": "uploaded",
                "file_token_redacted": "REDACTED_FILE_TOKEN",
                "file_token_hash": f"hash_{index}",
                "size_bytes": 10,
            }
            for index in range(count)
        ]
    }


def _secure_receipt(count: int = 4) -> dict:
    return {
        "uploaded_files": [
            {
                "filename": f"file_{index}.csv",
                "upload_status": "uploaded",
                "file_token": f"raw_file_token_should_not_leak_{index}",
                "file_token_hash": f"hash_{index}",
            }
            for index in range(count)
        ]
    }


class FailIfCalledClient:
    def send_file(self, **kwargs):
        raise AssertionError("Real Feishu file send API must not be called.")


class FakeFileSendClient:
    def __init__(self, fail_index: int | None = None) -> None:
        self.calls: list[dict] = []
        self.fail_index = fail_index

    def send_file(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_index is not None and len(self.calls) - 1 == self.fail_index:
            raise RuntimeError(
                f"failed {kwargs['file_token']} fake-app-secret fake-chat-id"
            )
        return f"om_file_message_{len(self.calls)}"


class FeishuFinalAttachmentFileSendRealTests(unittest.TestCase):
    def _enabled_env(self) -> dict[str, str]:
        return {
            "PRODUCT_INTEL_REAL_FEISHU_FILE_SEND_ENABLED": "true",
            "FEISHU_APP_ID": "fake-app-id",
            "FEISHU_APP_SECRET": "fake-app-secret",
        }

    def test_disabled_never_calls_real_api(self) -> None:
        receipt = run_file_message_send(
            _public_receipt(),
            _secure_receipt(),
            chat_id="fake-chat-id",
            environ={},
            client=FailIfCalledClient(),
        )
        self.assertFalse(receipt["real_feishu_api_called"])
        self.assertEqual(receipt["attempted_file_send_count"], 0)
        self.assertEqual(receipt["success_count"], 0)
        self.assertTrue(receipt["file_message_send_supported"])

    def test_mock_receipt_four_files_send_success(self) -> None:
        client = FakeFileSendClient()
        receipt = run_file_message_send(
            _public_receipt(),
            _secure_receipt(),
            chat_id="fake-chat-id",
            environ=self._enabled_env(),
            client=client,
        )
        self.assertEqual(len(client.calls), 4)
        self.assertTrue(receipt["real_feishu_api_called"])
        self.assertEqual(receipt["success_count"], 4)
        self.assertEqual(receipt["error_count"], 0)
        self.assertTrue(receipt["all_files_sent"])
        serialized = json.dumps(receipt)
        self.assertNotIn("raw_file_token_should_not_leak", serialized)
        self.assertNotIn("fake-app-secret", serialized)
        self.assertNotIn("fake-chat-id", serialized)

    def test_missing_raw_file_token_is_blocked(self) -> None:
        receipt = run_file_message_send(
            _public_receipt(),
            {"uploaded_files": []},
            chat_id="fake-chat-id",
            environ=self._enabled_env(),
            client=FailIfCalledClient(),
        )
        self.assertFalse(receipt["real_feishu_api_called"])
        self.assertFalse(receipt["file_message_send_supported"])
        self.assertIn("Raw file_token is unavailable", receipt["error"])
        self.assertEqual(
            receipt["required_next_action"],
            "rerun_v1_25_upload_to_create_private_secure_receipt",
        )

    def test_single_file_failure_keeps_batch_going(self) -> None:
        client = FakeFileSendClient(fail_index=1)
        receipt = run_file_message_send(
            _public_receipt(),
            _secure_receipt(),
            chat_id="fake-chat-id",
            environ=self._enabled_env(),
            client=client,
        )
        self.assertEqual(len(client.calls), 4)
        self.assertEqual(receipt["success_count"], 3)
        self.assertEqual(receipt["error_count"], 1)
        self.assertFalse(receipt["all_files_sent"])
        serialized = json.dumps(receipt)
        self.assertNotIn("raw_file_token_should_not_leak", serialized)
        self.assertNotIn("fake-app-secret", serialized)
        self.assertNotIn("fake-chat-id", serialized)


if __name__ == "__main__":
    unittest.main()
