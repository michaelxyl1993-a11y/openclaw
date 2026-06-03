"""Tests for v1.21.2 Feishu runtime token source builder."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from . import feishu_product_intel_bot as bot
from .feishu_multi_attachment_download_real import load_runtime_token_context
from .feishu_private_event_capture import (
    LATEST_EVENT_PATH,
    build_private_attachment_event,
    capture_private_attachment_event,
)
from .feishu_runtime_token_source_builder import (
    DEFAULT_OUTPUT,
    MODE,
    PRIVATE_RUNTIME_DIR,
    RuntimeTokenSourceBuilderError,
    build_from_event_file,
    build_runtime_token_source,
    main,
)


PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
PROTECTED_FILES = [
    PACKAGE_DIR / "feishu_product_intel_bot.py",
    REPO_ROOT / "tiktok_insight" / "pm2_services" / "run_cloudflare_tunnel.sh",
    REPO_ROOT / "tiktok_insight" / "pm2_services" / "run_anglekit_feishu_bot.sh",
    PACKAGE_DIR / "job_queue.py",
]


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _mock_event() -> dict:
    return {
        "event": {
            "message": {
                "message_id": "om_runtime_test_message",
                "attachments": [
                    {
                        "file_name": "mock_echotik_products.xlsx",
                        "file_token": "file_token_runtime_echotik",
                    },
                    {
                        "file_name": "mock_fastmoss_products.xlsx",
                        "file_token": "file_token_runtime_fastmoss",
                    },
                ],
            }
        }
    }


def _callback_event() -> dict:
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1", "event_id": "evt_runtime_capture"},
        "event": {
            "message": {
                "message_id": "om_runtime_capture",
                "chat_id": "oc_runtime_capture_secret",
                "message_type": "text",
                "content": json.dumps({"text": "multi attachment upload"}),
                "attachments": [
                    {
                        "file_name": "mock_echotik_products.xlsx",
                        "file_token": "file_token_callback_echotik",
                        "size_bytes": 123,
                        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    },
                    {
                        "file_name": "mock_fastmoss_products.xlsx",
                        "file_token": "file_token_callback_fastmoss",
                        "size_bytes": 456,
                        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    },
                ],
            }
        },
    }


class RuntimeTokenSourceBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protected_digests = {
            path: _digest(path) for path in PROTECTED_FILES if path.exists()
        }

    @classmethod
    def tearDownClass(cls) -> None:
        for path, expected in cls.protected_digests.items():
            if _digest(path) != expected:
                raise AssertionError(f"Protected source was modified: {path}")

    def test_mock_event_builds_message_id_and_tokens_by_hash(self) -> None:
        source = build_runtime_token_source(_mock_event())
        self.assertEqual(source["mode"], MODE)
        self.assertEqual(source["message_id"], "om_runtime_test_message")
        self.assertEqual(source["attachment_count"], 2)
        self.assertEqual(len(source["tokens_by_hash"]), 2)
        self.assertIn(
            sha256("file_token_runtime_echotik".encode("utf-8")).hexdigest(),
            source["tokens_by_hash"],
        )

    def test_cli_output_does_not_print_real_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            event_path = Path(temp_dir) / "event.json"
            event_path.write_text(json.dumps(_mock_event()), encoding="utf-8")
            output_path = PRIVATE_RUNTIME_DIR / "test_runtime_token_source.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--event-json",
                        str(event_path),
                        "--output",
                        str(output_path),
                    ]
                )
        text = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("token_hashes", text)
        self.assertNotIn("file_token_runtime_echotik", text)
        self.assertNotIn("file_token_runtime_fastmoss", text)
        self.assertNotIn("om_runtime_test_message", text)

    def test_missing_message_id_raises_clear_error(self) -> None:
        with self.assertRaisesRegex(RuntimeTokenSourceBuilderError, "message_id"):
            build_runtime_token_source({"attachments": [{"file_token": "real"}]})

    def test_redacted_token_raises_error(self) -> None:
        event = {
            "message_id": "om_runtime_test_message",
            "attachments": [{"file_token": "REDACTED_FILE_TOKEN"}],
        }
        with self.assertRaisesRegex(RuntimeTokenSourceBuilderError, "REDACTED_FILE_TOKEN"):
            build_runtime_token_source(event)

    def test_missing_real_token_raises_error(self) -> None:
        event = {
            "message_id": "om_runtime_test_message",
            "attachments": [{"file_name": "missing.xlsx"}],
        }
        with self.assertRaisesRegex(RuntimeTokenSourceBuilderError, "without file_token"):
            build_runtime_token_source(event)

    def test_private_runtime_path_and_loader_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            event_path = Path(temp_dir) / "event.json"
            event_path.write_text(json.dumps(_mock_event()), encoding="utf-8")
            output_path = PRIVATE_RUNTIME_DIR / "test_loader_runtime_token_source.json"
            summary = build_from_event_file(event_path, output_path)
            context = load_runtime_token_context(output_path)
        self.assertEqual(summary["attachment_count"], 2)
        self.assertEqual(context["message_id"], "om_runtime_test_message")
        self.assertEqual(len(context["tokens_by_hash"]), 2)

    def test_callback_capture_writes_private_runtime_event(self) -> None:
        summary = capture_private_attachment_event(_callback_event())
        path = Path(summary["latest_path"])
        private_event = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "captured")
        self.assertEqual(private_event["message_id"], "om_runtime_capture")
        self.assertEqual(private_event["source"], "product_intel_feishu_callback")
        self.assertEqual(private_event["chat_id_redacted"], "REDACTED_CHAT_ID")
        self.assertNotIn("oc_runtime_capture_secret", json.dumps(private_event))
        self.assertEqual(len(private_event["attachments"]), 2)
        self.assertEqual(
            private_event["attachments"][0]["file_token"],
            "file_token_callback_echotik",
        )
        self.assertTrue(private_event["attachments"][0]["file_token_hash"])

    def test_callback_stdout_does_not_contain_raw_token(self) -> None:
        original_enqueue = bot.enqueue_job
        original_reply = bot.reply_feishu_text
        queued_jobs: list[tuple[dict, object]] = []
        stdout = io.StringIO()
        try:
            bot.PROCESSED_MESSAGE_IDS.clear()
            bot.PROCESSED_MESSAGE_ORDER.clear()
            bot.IN_FLIGHT_DEDUPE_KEYS.clear()
            bot.ACTIVE_FILE_KEYS.clear()
            bot.JOB_STATUSES.clear()
            bot.enqueue_job = lambda job, handler: queued_jobs.append((job, handler))  # type: ignore[assignment]
            bot.reply_feishu_text = lambda chat_id, text: {"ok": True, "status_code": 200, "data": {"code": 0}}  # type: ignore[assignment]
            with contextlib.redirect_stdout(stdout), bot.app.test_client() as client:
                response = client.post("/feishu/events", json=_callback_event())
        finally:
            bot.enqueue_job = original_enqueue  # type: ignore[assignment]
            bot.reply_feishu_text = original_reply  # type: ignore[assignment]
        self.assertEqual(response.status_code, 200)
        text = stdout.getvalue()
        self.assertIn("private_attachment_event_capture", text)
        self.assertNotIn("file_token_callback_echotik", text)
        self.assertNotIn("file_token_callback_fastmoss", text)

    def test_builder_can_consume_generated_private_event(self) -> None:
        capture_private_attachment_event(_callback_event())
        source = build_runtime_token_source(
            json.loads(LATEST_EVENT_PATH.read_text(encoding="utf-8"))
        )
        self.assertEqual(source["message_id"], "om_runtime_capture")
        self.assertEqual(source["attachment_count"], 2)

    def test_private_capture_missing_message_id_blocks_clearly(self) -> None:
        event = _callback_event()
        event["event"]["message"].pop("message_id")
        private_event = build_private_attachment_event(event)
        self.assertEqual(private_event["status"], "blocked")
        self.assertIn("message_id missing", private_event["errors"])

    def test_private_capture_missing_file_token_blocks_clearly(self) -> None:
        event = _callback_event()
        event["event"]["message"]["attachments"][0].pop("file_token")
        private_event = build_private_attachment_event(event)
        self.assertEqual(private_event["status"], "blocked")
        self.assertIn("file_token missing", private_event["errors"])

    def test_output_outside_private_runtime_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            event_path = Path(temp_dir) / "event.json"
            event_path.write_text(json.dumps(_mock_event()), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeTokenSourceBuilderError, "private_runtime"):
                build_from_event_file(event_path, Path(temp_dir) / "runtime.json")

    def test_private_runtime_is_gitignored(self) -> None:
        output_path = PRIVATE_RUNTIME_DIR / "gitignore_probe_runtime_token_source.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("{}", encoding="utf-8")
        result = subprocess.run(
            ["git", "check-ignore", "-q", str(output_path.relative_to(REPO_ROOT))],
            cwd=REPO_ROOT,
            check=False,
        )
        self.assertEqual(result.returncode, 0)

    def test_default_output_is_private_runtime(self) -> None:
        self.assertEqual(DEFAULT_OUTPUT.parent, PRIVATE_RUNTIME_DIR)

    def test_protected_sources_are_not_modified(self) -> None:
        for path, expected in self.protected_digests.items():
            self.assertEqual(_digest(path), expected)


if __name__ == "__main__":
    unittest.main()
