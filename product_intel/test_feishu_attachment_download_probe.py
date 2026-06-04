"""Tests for v1.21.12 Feishu attachment download validation probe."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from .feishu_attachment_download_probe import main, run_probe
from .feishu_attachment_event_batch_builder import build_and_write_batch
from .feishu_multi_attachment_download_real import (
    FeishuDownloadHTTPError,
    run_multi_download,
)
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


def _raw_multi_event(message_id: str) -> dict:
    return {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_probe_sender"}},
            "message": {
                "message_id": message_id,
                "chat_id": "oc_probe_chat",
                "message_type": "file",
                "content": json.dumps(
                    {
                        "body": {
                            "content": [
                                [
                                    {
                                        "tag": "file",
                                        "file_key": "file_token_probe_ok_1",
                                        "file_name": "probe_ok_1.xlsx",
                                    },
                                    {
                                        "tag": "file",
                                        "file_key": "file_token_probe_fail_1",
                                        "file_name": "probe_fail_1.xlsx",
                                    },
                                ]
                            ]
                        }
                    }
                ),
            },
        },
        "raw_event_detected": True,
    }


def _raw_single_event(message_id: str) -> dict:
    event = _raw_multi_event(message_id)
    event["event"]["message"]["content"] = json.dumps(
        {
            "body": {
                "content": [
                    [
                        {
                            "tag": "file",
                            "file_key": "file_token_probe_ok_2",
                            "file_name": "probe_ok_2.xlsx",
                        },
                        {
                            "tag": "file",
                            "file_key": "file_token_probe_fail_2",
                            "file_name": "probe_fail_2.xlsx",
                        },
                    ]
                ]
            }
        }
    )
    return event


class ProbeFakeClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def download_file(self, **kwargs) -> None:
        self.calls.append(kwargs)
        if "fail" in kwargs["file_token"]:
            raise FeishuDownloadHTTPError(
                response_status_code=400,
                response_body=json.dumps(
                    {
                        "code": 99992354,
                        "msg": "invalid open message id",
                        "debug_token": kwargs["file_token"],
                        "debug_message": kwargs["message_id"],
                        "debug_secret": "fake-app-secret",
                    }
                ),
                response_content_type="application/json",
            )
        target = Path(kwargs["target_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"probe-ok")


class DownloadFakeClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def download_file(self, **kwargs) -> None:
        self.calls.append(kwargs)
        target = Path(kwargs["target_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"download-ok")


class FeishuAttachmentDownloadProbeTests(unittest.TestCase):
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
        message_1 = "om_probe_open_message_id_000000000001"
        message_2 = "om_probe_open_message_id_000000000002"
        (events_dir / "001_http_raw_event.json").write_text(
            json.dumps(_raw_multi_event(message_1)), encoding="utf-8"
        )
        (events_dir / "002_http_raw_event.json").write_text(
            json.dumps(_raw_single_event(message_2)), encoding="utf-8"
        )
        return message_1, message_2

    def _enabled_env(self) -> dict[str, str]:
        return {
            "PRODUCT_INTEL_REAL_FEISHU_MULTI_DOWNLOAD_ENABLED": "true",
            "FEISHU_APP_ID": "fake-app-id",
            "FEISHU_APP_SECRET": "fake-app-secret",
        }

    def test_probe_validates_success_pairs_and_records_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            events_dir = Path(temp_dir) / "events"
            events_dir.mkdir()
            self._write_events(events_dir)
            output = PRIVATE_RUNTIME_DIR / "test_validated_download_pairs.json"
            payload, summary = run_probe(
                events_dir,
                lookback_seconds=0,
                output=output,
                probe_dir=PRIVATE_RUNTIME_DIR / "test_probe_downloads",
                environ=self._enabled_env(),
                client=ProbeFakeClient(),
            )
        self.assertEqual(payload["candidate_pair_count"], 4)
        self.assertEqual(payload["validated_pair_count"], 2)
        self.assertEqual(payload["failed_pair_count"], 2)
        self.assertTrue(summary["ready_for_validated_batch"])
        self.assertEqual(len(payload["validated_pairs"]), 2)
        self.assertEqual(len(payload["failed_pairs"]), 2)

    def test_probe_stdout_does_not_leak_raw_token_or_message_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            events_dir = Path(temp_dir) / "events"
            events_dir.mkdir()
            message_1, _ = self._write_events(events_dir)
            output = PRIVATE_RUNTIME_DIR / "test_validated_download_pairs.json"
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
        self.assertIn("candidate_pair_count", text)
        self.assertNotIn("file_token_probe_ok_1", text)
        self.assertNotIn("file_token_probe_fail_1", text)
        self.assertNotIn(message_1, text)

    def test_validated_pairs_build_batch_runtime_source_and_download(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            events_dir = Path(temp_dir) / "events"
            events_dir.mkdir()
            self._write_events(events_dir)
            pairs_output = PRIVATE_RUNTIME_DIR / "test_validated_download_pairs.json"
            run_probe(
                events_dir,
                lookback_seconds=0,
                output=pairs_output,
                probe_dir=PRIVATE_RUNTIME_DIR / "test_probe_downloads",
                environ=self._enabled_env(),
                client=ProbeFakeClient(),
            )
            batch_output = PRIVATE_RUNTIME_DIR / "test_latest_attachment_batch.json"
            batch_summary = build_and_write_batch(
                events_dir,
                lookback_seconds=0,
                output=batch_output,
                validated_pairs=pairs_output,
            )
            attachments = load_attachment_items(batch_output)
            manifest = build_dry_run_manifest(
                attachments, download_dir=Path(temp_dir) / "downloads"
            )
            plan = build_download_plan(manifest)
            source = build_runtime_token_source(
                json.loads(batch_output.read_text(encoding="utf-8"))
            )
            client = DownloadFakeClient()
            receipt = run_multi_download(
                plan,
                environ=self._enabled_env(),
                token_context=source,
                client=client,
            )
        self.assertEqual(batch_summary["batch_selection_strategy"], "validated_download_pairs")
        self.assertEqual(batch_summary["attachment_count"], 2)
        self.assertTrue(batch_summary["ready_for_real_download"])
        self.assertEqual(source["per_file_message_context_count"], 2)
        self.assertEqual(receipt["success_count"], 2)
        self.assertEqual(len(client.calls), 2)
        self.assertTrue(
            all(
                result["used_per_file_message_context"]
                for result in receipt["download_results"]
            )
        )


if __name__ == "__main__":
    unittest.main()
