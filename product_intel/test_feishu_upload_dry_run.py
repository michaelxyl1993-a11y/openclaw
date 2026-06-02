"""Tests for Product Intel v1.13 Feishu upload dry run."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from .feishu_upload_dry_run import (
    build_dry_run_plan,
    load_manifest,
    unique_attachment_paths,
    write_outputs,
)


PACKAGE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PACKAGE_DIR / "output_next_round"
MANIFEST = OUTPUT_DIR / "feishu_ops_handoff_manifest.json"
MESSAGE = OUTPUT_DIR / "feishu_ops_handoff_message.md"


class FeishuUploadDryRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = load_manifest(MANIFEST)
        self.plan = build_dry_run_plan(self.manifest, MESSAGE)

    def test_reads_v1_12_manifest(self) -> None:
        self.assertEqual(
            self.manifest["version"],
            "product_intel_feishu_ops_handoff_v1.12",
        )

    def test_recognizes_all_manifest_attachment_files(self) -> None:
        paths = unique_attachment_paths(self.manifest)
        self.assertEqual(len(paths), 6)
        self.assertEqual(self.plan["total_attachments"], 6)

    def test_all_attachments_exist_and_are_non_empty(self) -> None:
        self.assertEqual(self.plan["valid_attachment_count"], 6)
        self.assertEqual(self.plan["invalid_attachment_count"], 0)
        self.assertTrue(all(item["exists"] for item in self.plan["attachment_items"]))
        self.assertTrue(all(item["non_empty"] for item in self.plan["attachment_items"]))

    def test_message_exists_and_contains_manual_3(self) -> None:
        self.assertTrue(self.plan["message_check"]["exists"])
        self.assertTrue(self.plan["message_check"]["non_empty"])
        self.assertTrue(self.plan["message_ready"])
        self.assertTrue(self.plan["message_check"]["marker_checks"]["manual-3"])

    def test_plan_never_calls_feishu_or_sends_message(self) -> None:
        self.assertFalse(self.plan["will_call_feishu_api"])
        self.assertFalse(self.plan["will_send_message"])

    def test_ready_for_upload_is_true(self) -> None:
        self.assertTrue(self.plan["ready_for_upload"])

    def test_generates_json_markdown_and_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_outputs(self.plan, temp_dir)
            self.assertEqual(set(paths), {"plan_json", "report_md", "attachment_csv"})
            for path in paths.values():
                self.assertTrue(path.exists())
                self.assertGreater(path.stat().st_size, 0)

    def test_csv_rows_equal_attachment_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_outputs(self.plan, temp_dir)
            with paths["attachment_csv"].open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), self.plan["total_attachments"])

    def test_missing_attachment_sets_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.csv"
            manifest = {"source_files": [str(missing)], "output_files": []}
            plan = build_dry_run_plan(manifest, MESSAGE)
            self.assertFalse(plan["ready_for_upload"])
            self.assertEqual(plan["invalid_attachment_count"], 1)

    def test_module_has_no_openai_or_feishu_api_dependencies(self) -> None:
        source = (PACKAGE_DIR / "feishu_upload_dry_run.py").read_text(encoding="utf-8")
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("requests.", source)
        self.assertNotIn("lark", source.lower())
        self.assertNotIn("urllib", source.lower())

    def test_report_states_no_real_actions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_outputs(self.plan, temp_dir)
            report = paths["report_md"].read_text(encoding="utf-8")
            self.assertIn("本次不会调用飞书 API", report)
            self.assertIn("本次不会发送消息", report)


if __name__ == "__main__":
    unittest.main()

