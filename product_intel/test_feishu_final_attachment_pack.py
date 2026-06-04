"""Tests for v1.25 final Feishu attachment pack and upload."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from .feishu_final_attachment_pack import build_pack, build_upload_plan
from .feishu_final_attachment_upload_real import run_final_attachment_upload


class FailIfCalledClient:
    def upload_file(self, **kwargs):
        raise AssertionError("Real Feishu API must not be called.")


class FakeUploadClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def upload_file(self, **kwargs):
        self.calls.append(kwargs)
        return f"raw_file_token_should_not_leak_{len(self.calls)}"


def _write_attachments(root: Path) -> list[Path]:
    names = [
        "final_ops_decision_table.csv",
        "final_ops_action_summary.md",
        "final_challenge_products.csv",
        "final_review_note.md",
    ]
    paths = []
    for name in names:
        path = root / name
        path.write_text(f"content for {name}\n", encoding="utf-8")
        paths.append(path)
    return paths


class FeishuFinalAttachmentPackTests(unittest.TestCase):
    def test_pack_generates_four_attachment_plan_and_preview(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            attachments = _write_attachments(root)
            summary = build_pack(attachments, root)
            plan = json.loads((root / "feishu_final_attachment_upload_plan.json").read_text(encoding="utf-8"))
            preview = (root / "feishu_final_attachment_message_preview.md").read_text(encoding="utf-8")
        self.assertEqual(summary["attachment_count"], 4)
        self.assertEqual(summary["existing_attachment_count"], 4)
        self.assertEqual(summary["missing_attachment_count"], 0)
        self.assertTrue(summary["ready_for_upload"])
        self.assertEqual(plan["attachment_count"], 4)
        self.assertIn("final_ops_decision_table.csv", preview)
        self.assertIn("附件已生成", preview)

    def test_missing_file_is_counted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            existing = root / "final_ops_decision_table.csv"
            existing.write_text("ok\n", encoding="utf-8")
            plan = build_upload_plan([existing, root / "missing.csv"])
        self.assertFalse(plan["ready_for_upload"])
        self.assertEqual(plan["existing_attachment_count"], 1)
        self.assertEqual(plan["missing_attachment_count"], 1)

    def test_disabled_upload_never_calls_real_api(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan = build_upload_plan(_write_attachments(root))
            receipt = run_final_attachment_upload(
                plan, environ={}, client=FailIfCalledClient()
            )
        self.assertFalse(receipt["real_feishu_api_called"])
        self.assertEqual(receipt["upload_status"], "disabled")
        self.assertEqual(receipt["success_count"], 0)

    def test_fake_upload_success_is_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan = build_upload_plan(_write_attachments(root))
            client = FakeUploadClient()
            receipt = run_final_attachment_upload(
                plan,
                environ={
                    "PRODUCT_INTEL_REAL_FEISHU_UPLOAD_ENABLED": "true",
                    "FEISHU_APP_ID": "fake-app-id",
                    "FEISHU_APP_SECRET": "fake-app-secret",
                },
                client=client,
            )
        self.assertEqual(len(client.calls), 4)
        self.assertTrue(receipt["real_feishu_api_called"])
        self.assertEqual(receipt["success_count"], 4)
        self.assertEqual(receipt["error_count"], 0)
        self.assertTrue(receipt["ready_for_attachment_message"])
        serialized = json.dumps(receipt)
        self.assertNotIn("raw_file_token_should_not_leak", serialized)
        self.assertNotIn("fake-app-secret", serialized)
        self.assertEqual(
            {item["file_token_redacted"] for item in receipt["uploaded_files"]},
            {"REDACTED_FILE_TOKEN"},
        )


if __name__ == "__main__":
    unittest.main()
