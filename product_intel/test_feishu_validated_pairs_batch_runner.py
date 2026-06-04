"""Tests for v1.22 Feishu validated pairs to multi-file batch handoff."""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from .feishu_validated_pairs_batch_runner import (
    load_validated_pairs,
    main,
    resolve_input_files,
    run_validated_pairs_batch,
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


def _pairs_payload(extra_missing: bool = False) -> dict:
    pairs = [
        {
            "filename": "mock_echotik_products.xlsx",
            "file_token": "file_token_should_not_print_echotik",
            "message_id": "om_should_not_print_echotik_000000000001",
            "probe_download_path": str(PACKAGE_DIR / "mock_echotik_products.xlsx"),
        },
        {
            "filename": "mock_fastmoss_products.xlsx",
            "file_token": "file_token_should_not_print_fastmoss",
            "message_id": "om_should_not_print_fastmoss_000000000002",
            "probe_download_path": str(PACKAGE_DIR / "mock_fastmoss_products.xlsx"),
        },
    ]
    if extra_missing:
        pairs.append(
            {
                "filename": "missing.xlsx",
                "file_token": "file_token_should_not_print_missing",
                "message_id": "om_should_not_print_missing_000000000003",
                "probe_download_path": str(PACKAGE_DIR / "does_not_exist.xlsx"),
            }
        )
    return {
        "mode": "feishu_validated_download_pairs_v1.21.12",
        "validated_pair_count": len(pairs),
        "validated_pairs": pairs,
    }


class FeishuValidatedPairsBatchRunnerTests(unittest.TestCase):
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

    def test_existing_probe_download_paths_run_multi_file_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pairs_path = Path(temp_dir) / "validated_pairs.json"
            output_dir = Path(temp_dir) / "output"
            pairs_path.write_text(
                json.dumps(_pairs_payload()), encoding="utf-8"
            )
            summary = run_validated_pairs_batch(
                validated_pairs=pairs_path,
                source="auto",
                market="de",
                output_dir=output_dir,
            )
        self.assertEqual(summary["validated_pair_count"], 2)
        self.assertEqual(summary["input_file_count"], 2)
        self.assertEqual(summary["missing_input_count"], 0)
        self.assertGreater(summary["total_products"], 0)
        self.assertEqual(
            summary["source_detected_counts"], {"echotik": 1, "fastmoss": 1}
        )
        self.assertEqual(
            sum(summary["decision_counts"].values()),
            summary["total_products"],
        )
        self.assertEqual(summary["error_count"], 0)
        self.assertTrue(summary["ready_for_llm_judge"])

    def test_missing_file_is_counted_and_not_passed_to_batch(self) -> None:
        pairs = load_validated_pairs_from_payload(_pairs_payload(extra_missing=True))
        input_files, missing_count = resolve_input_files(pairs)
        self.assertEqual(len(input_files), 2)
        self.assertEqual(missing_count, 1)

    def test_summary_outputs_exist_and_are_non_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pairs_path = Path(temp_dir) / "validated_pairs.json"
            output_dir = Path(temp_dir) / "output"
            pairs_path.write_text(
                json.dumps(_pairs_payload()), encoding="utf-8"
            )
            summary = run_validated_pairs_batch(
                validated_pairs=pairs_path,
                source="auto",
                market="de",
                output_dir=output_dir,
            )
            summary_json = output_dir / "feishu_validated_pairs_batch_runner_summary.json"
            summary_md = output_dir / "feishu_validated_pairs_batch_runner_summary.md"
            self.assertTrue(summary_json.exists())
            self.assertGreater(summary_json.stat().st_size, 0)
            self.assertTrue(summary_md.exists())
            self.assertGreater(summary_md.stat().st_size, 0)
            self.assertIn("summary_json", summary["output_files"])

    def test_stdout_does_not_leak_raw_token_or_message_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pairs_path = Path(temp_dir) / "validated_pairs.json"
            output_dir = Path(temp_dir) / "output"
            pairs_path.write_text(
                json.dumps(_pairs_payload()), encoding="utf-8"
            )
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "--validated-pairs",
                        str(pairs_path),
                        "--source",
                        "auto",
                        "--market",
                        "de",
                        "--output-dir",
                        str(output_dir),
                    ]
                )
        text = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertNotIn("file_token_should_not_print", text)
        self.assertNotIn("om_should_not_print", text)
        self.assertIn("ready_for_llm_judge", text)


def load_validated_pairs_from_payload(payload: dict) -> list[dict]:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "pairs.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return load_validated_pairs(path)


if __name__ == "__main__":
    unittest.main()
