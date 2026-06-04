"""Tests for v1.21.10 Feishu raw event attachment batch builder."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from .feishu_attachment_event_batch_builder import (
    DEFAULT_OUTPUT,
    build_and_write_batch,
    build_attachment_event_batch,
    main,
)
from .feishu_callback_capture_verifier import verify_capture_event
from .feishu_multi_attachment_download_real import run_multi_download
from .feishu_multi_attachment_dry_run import (
    build_download_plan,
    build_dry_run_manifest,
    load_attachment_items,
)
from .feishu_runtime_token_source_builder import (
    PRIVATE_RUNTIME_DIR,
    build_runtime_token_source,
)


PACKAGE_DIR = Path(__file__).resolve().parent
PROTECTED_FILES = [
    PACKAGE_DIR / "run_product_intel.py",
    PACKAGE_DIR / "multi_file_batch_runner.py",
    PACKAGE_DIR / "feishu_product_intel_bot.py",
    PACKAGE_DIR / "job_queue.py",
]


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _raw_event(message_id: str, filename: str, token: str) -> dict:
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_batch_sender"}},
            "message": {
                "message_id": message_id,
                "chat_id": "oc_batch_chat",
                "message_type": "file",
                "content": json.dumps(
                    {
                        "body": {
                            "content": [
                                [
                                    {
                                        "tag": "file",
                                        "file_key": token,
                                        "file_name": filename,
                                    }
                                ]
                            ]
                        }
                    }
                ),
            },
        },
        "raw_event_detected": True,
    }


def _compact_event() -> dict:
    return {
        "mode": "feishu_private_attachment_event_v1.21.9",
        "message_id": "om_short_compact",
        "attachments": [
            {"file_name": "compact_1.xlsx", "file_token": "file_token_compact_1"},
            {"file_name": "compact_2.xlsx", "file_token": "file_token_compact_2"},
        ],
    }


def _multi_raw_event(message_id: str) -> dict:
    event = _raw_event(message_id, "multi_first.xlsx", "file_token_multi_1")
    event["event"]["message"]["content"] = json.dumps(
        {
            "body": {
                "content": [
                    [
                        {
                            "tag": "file",
                            "file_key": "file_token_multi_1",
                            "file_name": "multi_first.xlsx",
                        },
                        {
                            "tag": "file",
                            "file_key": "file_token_multi_2",
                            "file_name": "multi_second.xlsx",
                        },
                    ]
                ]
            }
        }
    )
    return event


class FakePerFileDownloadClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def download_file(self, **kwargs) -> None:
        self.calls.append(kwargs)
        target = Path(kwargs["target_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"downloaded:{target.name}".encode("utf-8"))


class FeishuAttachmentEventBatchBuilderTests(unittest.TestCase):
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

    def _write_events(self, events_dir: Path) -> tuple[str, str]:
        message_1 = "om_batch_open_message_id_000000000001"
        message_2 = "om_batch_open_message_id_000000000002"
        (events_dir / "001_raw_event.json").write_text(
            json.dumps(
                _raw_event(message_1, "mock_echotik_products.xlsx", "file_token_batch_1")
            ),
            encoding="utf-8",
        )
        (events_dir / "002_raw_event.json").write_text(
            json.dumps(
                _raw_event(message_2, "mock_fastmoss_products.xlsx", "file_token_batch_2")
            ),
            encoding="utf-8",
        )
        (events_dir / "003_compact_event.json").write_text(
            json.dumps(_compact_event()),
            encoding="utf-8",
        )
        return message_1, message_2

    def test_two_raw_events_are_aggregated_and_invalid_compact_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            events_dir = Path(temp_dir)
            self._write_events(events_dir)
            batch, summary = build_attachment_event_batch(
                events_dir, lookback_seconds=0
            )
        self.assertTrue(summary["batch_created"])
        self.assertEqual(summary["valid_event_count"], 2)
        self.assertEqual(summary["ignored_event_count"], 1)
        self.assertEqual(batch["event_count"], 2)
        self.assertEqual(batch["attachment_count"], 2)
        self.assertEqual(
            summary["batch_selection_strategy"],
            "strict_single_attachment_raw_events",
        )
        self.assertEqual(summary["single_attachment_event_count"], 2)
        self.assertEqual(summary["multi_attachment_event_count"], 0)
        self.assertEqual(summary["ignored_compact_event_count"], 1)
        self.assertEqual(summary["per_attachment_message_id_unique_count"], 2)
        self.assertFalse(summary["repeated_message_id_warning"])
        self.assertEqual(
            [item["filename"] for item in batch["attachments"]],
            ["mock_echotik_products.xlsx", "mock_fastmoss_products.xlsx"],
        )
        self.assertEqual(len(set(batch["selected_source_event_paths"])), 2)

    def test_stdout_summary_does_not_leak_raw_token_or_message_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            events_dir = Path(temp_dir)
            message_1, _ = self._write_events(events_dir)
            output = PRIVATE_RUNTIME_DIR / "test_latest_attachment_batch.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--events-dir",
                        str(events_dir),
                        "--lookback-seconds",
                        "0",
                        "--output",
                        str(output),
                    ]
                )
        text = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("token_hashes", text)
        self.assertNotIn("file_token_batch_1", text)
        self.assertNotIn(message_1, text)
        self.assertTrue(output.exists())

    def test_multi_event_is_not_selected_when_single_events_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            events_dir = Path(temp_dir)
            (events_dir / "000_http_raw_event.json").write_text(
                json.dumps(_multi_raw_event("om_batch_multi_message_id_000000000001")),
                encoding="utf-8",
            )
            self._write_events(events_dir)
            batch, summary = build_attachment_event_batch(
                events_dir, lookback_seconds=0
            )
        self.assertEqual(summary["single_attachment_event_count"], 2)
        self.assertEqual(summary["multi_attachment_event_count"], 1)
        self.assertEqual(summary["ignored_multi_attachment_event_count"], 1)
        self.assertEqual(batch["attachment_count"], 2)
        self.assertNotIn("multi_first.xlsx", summary["filenames"])
        self.assertTrue(
            all("raw_event" in path for path in batch["selected_source_event_paths"])
        )

    def test_only_multi_event_is_not_ready_in_strict_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            events_dir = Path(temp_dir)
            (events_dir / "000_http_raw_event.json").write_text(
                json.dumps(_multi_raw_event("om_batch_multi_message_id_000000000001")),
                encoding="utf-8",
            )
            batch, summary = build_attachment_event_batch(
                events_dir, lookback_seconds=0
            )
        self.assertFalse(summary["batch_created"])
        self.assertFalse(summary["ready_for_real_download"])
        self.assertEqual(summary["multi_attachment_event_count"], 1)
        self.assertEqual(batch["attachment_count"], 0)

    def test_allow_multi_event_warns_when_message_id_is_shared(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            events_dir = Path(temp_dir)
            (events_dir / "000_http_raw_event.json").write_text(
                json.dumps(_multi_raw_event("om_batch_multi_message_id_000000000001")),
                encoding="utf-8",
            )
            batch, summary = build_attachment_event_batch(
                events_dir,
                lookback_seconds=0,
                allow_multi_attachment_events=True,
            )
        self.assertTrue(summary["batch_created"])
        self.assertFalse(summary["ready_for_real_download"])
        self.assertEqual(batch["attachment_count"], 2)
        self.assertTrue(summary["repeated_message_id_warning"])
        self.assertEqual(summary["repeated_message_id_count"], 1)

    def test_dry_run_and_runtime_source_support_batch_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            events_dir = Path(temp_dir)
            self._write_events(events_dir)
            output = PRIVATE_RUNTIME_DIR / "test_latest_attachment_batch.json"
            summary = build_and_write_batch(
                events_dir,
                lookback_seconds=0,
                output=output,
            )
            self.assertTrue(summary["ready_for_real_download"])
            attachments = load_attachment_items(output)
            manifest = build_dry_run_manifest(
                attachments, download_dir=Path(temp_dir) / "downloads"
            )
            plan = build_download_plan(manifest)
            source = build_runtime_token_source(
                json.loads(output.read_text(encoding="utf-8"))
            )
        self.assertEqual(len(plan["download_tasks"]), 2)
        self.assertTrue(
            all(task["message_id_len"] >= 30 for task in plan["download_tasks"])
        )
        self.assertEqual(source["per_file_message_context_count"], 2)
        self.assertEqual(len(source["download_context_by_file_hash"]), 2)

    def test_real_downloader_uses_each_task_message_id_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            events_dir = Path(temp_dir) / "events"
            events_dir.mkdir()
            message_1, message_2 = self._write_events(events_dir)
            output = PRIVATE_RUNTIME_DIR / "test_latest_attachment_batch.json"
            build_and_write_batch(events_dir, lookback_seconds=0, output=output)
            attachments = load_attachment_items(output)
            manifest = build_dry_run_manifest(
                attachments, download_dir=Path(temp_dir) / "downloads"
            )
            plan = build_download_plan(manifest)
            source = build_runtime_token_source(
                json.loads(output.read_text(encoding="utf-8"))
            )
            client = FakePerFileDownloadClient()
            receipt = run_multi_download(
                plan,
                environ={
                    "PRODUCT_INTEL_REAL_FEISHU_MULTI_DOWNLOAD_ENABLED": "true",
                    "FEISHU_APP_ID": "fake-app-id",
                    "FEISHU_APP_SECRET": "fake-app-secret",
                },
                token_context=source,
                client=client,
            )
        self.assertEqual(receipt["success_count"], 2)
        self.assertEqual([call["message_id"] for call in client.calls], [message_1, message_2])
        self.assertTrue(
            all(
                result["used_per_file_message_context"]
                for result in receipt["download_results"]
            )
        )

    def test_real_downloader_reports_repeated_message_id_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            events_dir = Path(temp_dir) / "events"
            events_dir.mkdir()
            same_message = "om_batch_same_message_id_000000000001"
            (events_dir / "001_raw_event.json").write_text(
                json.dumps(
                    _raw_event(
                        same_message,
                        "mock_echotik_products.xlsx",
                        "file_token_same_1",
                    )
                ),
                encoding="utf-8",
            )
            (events_dir / "002_raw_event.json").write_text(
                json.dumps(
                    _raw_event(
                        same_message,
                        "mock_fastmoss_products.xlsx",
                        "file_token_same_2",
                    )
                ),
                encoding="utf-8",
            )
            output = PRIVATE_RUNTIME_DIR / "test_latest_attachment_batch.json"
            build_and_write_batch(events_dir, lookback_seconds=0, output=output)
            attachments = load_attachment_items(output)
            manifest = build_dry_run_manifest(
                attachments, download_dir=Path(temp_dir) / "downloads"
            )
            plan = build_download_plan(manifest)
            source = build_runtime_token_source(
                json.loads(output.read_text(encoding="utf-8"))
            )
            receipt = run_multi_download(
                plan,
                environ={
                    "PRODUCT_INTEL_REAL_FEISHU_MULTI_DOWNLOAD_ENABLED": "true",
                    "FEISHU_APP_ID": "fake-app-id",
                    "FEISHU_APP_SECRET": "fake-app-secret",
                },
                token_context=source,
                client=FakePerFileDownloadClient(),
            )
        self.assertTrue(receipt["repeated_message_id_warning"])
        self.assertEqual(receipt["repeated_message_id_count"], 1)

    def test_invalid_short_message_id_is_not_valid_for_download(self) -> None:
        result = verify_capture_event(_compact_event())
        self.assertFalse(result["capture_valid_for_download"])


if __name__ == "__main__":
    unittest.main()
