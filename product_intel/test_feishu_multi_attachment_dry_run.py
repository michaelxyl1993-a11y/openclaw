"""Tests for Product Intel v1.20 Feishu multi-attachment download dry run."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from .feishu_multi_attachment_dry_run import (
    MultiAttachmentDryRunError,
    build_download_plan,
    build_dry_run_manifest,
    build_summary,
    load_attachment_items,
    write_outputs,
)


PACKAGE_DIR = Path(__file__).resolve().parent
FIXTURE = PACKAGE_DIR / "mock_feishu_multi_attachment_event.json"
PROTECTED_FILES = [
    PACKAGE_DIR / "run_product_intel.py",
    PACKAGE_DIR / "multi_file_batch_runner.py",
    PACKAGE_DIR / "feishu_product_intel_bot.py",
    PACKAGE_DIR / "job_queue.py",
]


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


class FeishuMultiAttachmentDryRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protected_digests = {
            path: _digest(path) for path in PROTECTED_FILES if path.exists()
        }
        cls.raw = load_attachment_items(FIXTURE)
        cls.manifest = build_dry_run_manifest(cls.raw)
        cls.summary = build_summary(cls.manifest)

    @classmethod
    def tearDownClass(cls) -> None:
        for path, expected in cls.protected_digests.items():
            if _digest(path) != expected:
                raise AssertionError(f"Protected source was modified: {path}")

    def test_reads_mock_event_fixture(self) -> None:
        self.assertEqual(len(self.raw), 5)

    def test_accepts_attachments_files_and_list_formats(self) -> None:
        cases = [
            {"attachments": self.raw[:1]},
            {"files": self.raw[:1]},
            self.raw[:1],
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            for index, payload in enumerate(cases):
                path = Path(temp_dir) / f"case-{index}.json"
                path.write_text(json.dumps(payload), encoding="utf-8")
                self.assertEqual(len(load_attachment_items(path)), 1)

    def test_recognizes_supported_csv_xlsx_and_xls(self) -> None:
        manifest = build_dry_run_manifest(
            [
                {"token": "a", "name": "a.csv", "size": 1},
                {"token": "b", "filename": "b.xlsx", "file_size": 2},
                {"file_token": "c", "file_name": "c.xls", "size_bytes": 3},
            ]
        )
        self.assertEqual(manifest["supported_attachment_count"], 3)
        self.assertTrue(all(item["supported"] for item in manifest["attachments"]))

    def test_unsupported_file_is_excluded_from_batch_inputs(self) -> None:
        unsupported = self.manifest["unsupported_attachments"]
        self.assertEqual(len(unsupported), 1)
        self.assertEqual(unsupported[0]["filename"], "readme.pdf")
        self.assertFalse(unsupported[0]["planned_batch_input"])
        self.assertNotIn(
            unsupported[0]["planned_download_path"],
            self.summary["planned_input_files"],
        )

    def test_supported_counts_and_readiness(self) -> None:
        self.assertEqual(self.manifest["supported_attachment_count"], 4)
        self.assertEqual(self.manifest["unsupported_attachment_count"], 1)
        self.assertTrue(self.manifest["ready_for_real_download"])
        self.assertTrue(self.manifest["ready_for_multi_file_batch_runner"])
        self.assertEqual(len(self.summary["planned_input_files"]), 4)

    def test_duplicate_filename_paths_are_deduplicated(self) -> None:
        manifest = build_dry_run_manifest(
            [
                {"file_token": "first", "file_name": "file.xlsx", "size_bytes": 1},
                {"file_token": "second", "file_name": "file.xlsx", "size_bytes": 1},
                {"file_token": "third", "file_name": "file.xlsx", "size_bytes": 1},
            ]
        )
        paths = [item["planned_download_path"] for item in manifest["attachments"]]
        self.assertEqual(
            paths,
            [
                "product_intel/feishu_downloads/file.xlsx",
                "product_intel/feishu_downloads/file_2.xlsx",
                "product_intel/feishu_downloads/file_3.xlsx",
            ],
        )
        self.assertEqual(manifest["duplicate_filename_count"], 2)

    def test_duplicate_file_tokens_are_counted(self) -> None:
        manifest = build_dry_run_manifest(
            [
                {"file_token": "same", "file_name": "a.xlsx", "size_bytes": 1},
                {"file_token": "same", "file_name": "b.xlsx", "size_bytes": 1},
            ]
        )
        self.assertEqual(manifest["duplicate_file_token_count"], 1)

    def test_outputs_never_include_raw_tokens_or_sensitive_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_outputs(self.manifest, temp_dir)
            rendered = "\n".join(
                path.read_text(encoding="utf-8-sig") for path in paths.values()
            )
        for item in self.raw:
            self.assertNotIn(item["file_token"], rendered)
        for forbidden in ["FEISHU_APP_SECRET", "FEISHU_APP_ID", "chat_id", "oc_"]:
            self.assertNotIn(forbidden, rendered)
        self.assertIn("REDACTED_FILE_TOKEN", rendered)

    def test_download_plan_is_local_only_and_redacted(self) -> None:
        plan = build_download_plan(self.manifest)
        self.assertFalse(plan["real_download_enabled"])
        self.assertFalse(plan["real_feishu_api_called"])
        self.assertEqual(len(plan["download_tasks"]), 4)
        self.assertTrue(
            all(task["file_token_redacted"] == "REDACTED_FILE_TOKEN" for task in plan["download_tasks"])
        )

    def test_generates_all_six_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_outputs(self.manifest, temp_dir)
            self.assertEqual(
                set(paths),
                {
                    "manifest_json",
                    "summary_json",
                    "summary_md",
                    "download_plan_json",
                    "file_list_csv",
                    "checklist_md",
                },
            )
            for path in paths.values():
                self.assertTrue(path.exists(), path)
                self.assertGreater(path.stat().st_size, 0, path)
            with paths["file_list_csv"].open(
                encoding="utf-8-sig", newline=""
            ) as file:
                self.assertEqual(len(list(csv.DictReader(file))), 5)

    def test_missing_attachment_list_is_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "empty.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(MultiAttachmentDryRunError, "non-empty"):
                load_attachment_items(path)

    def test_missing_supported_token_blocks_real_download(self) -> None:
        manifest = build_dry_run_manifest(
            [{"file_name": "a.xlsx", "size_bytes": 1}]
        )
        self.assertFalse(manifest["ready_for_real_download"])
        self.assertFalse(manifest["ready_for_multi_file_batch_runner"])

    def test_module_has_no_api_client_dependencies(self) -> None:
        source = (PACKAGE_DIR / "feishu_multi_attachment_dry_run.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("requests.", source)
        self.assertNotIn("urllib", source.lower())
        self.assertNotIn("run_pipeline", source)

    def test_protected_sources_are_not_modified(self) -> None:
        for path, expected in self.protected_digests.items():
            self.assertEqual(_digest(path), expected)


if __name__ == "__main__":
    unittest.main()
