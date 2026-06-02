"""Regression tests for the local-only Product Intel v1.19 multi-file runner."""

from __future__ import annotations

import csv
import json
import unittest
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from .multi_file_batch_runner import MultiFileBatchError, run_multi_file_batch


PACKAGE_DIR = Path(__file__).resolve().parent
SOURCE_FILES = [
    PACKAGE_DIR / "mock_echotik_products.xlsx",
    PACKAGE_DIR / "mock_fastmoss_products.xlsx",
    PACKAGE_DIR / "mock_kalodata_products.xlsx",
    PACKAGE_DIR / "mock_manual_products.xlsx",
]
EXPECTED_SOURCES = ["echotik", "fastmoss", "kalodata", "manual"]
EXPECTED_DECISIONS = {
    "main_push": 1,
    "small_test": 8,
    "hold": 3,
    "reject": 0,
}
PER_FILE_OUTPUTS = [
    "product_intel_csv_profile.json",
    "product_intel_csv_profile.md",
    "product_intel_decision_table.csv",
    "product_intel_decision_table.md",
    "product_intel_manager_payload.json",
]
MERGED_OUTPUTS = [
    "multi_file_batch_manifest.json",
    "multi_file_batch_summary.json",
    "multi_file_batch_summary.md",
    "multi_file_combined_manager_payload.json",
    "multi_file_combined_decision_table.csv",
    "multi_file_combined_decision_table.md",
    "multi_file_all_evidence.json",
]
PROTECTED_FILES = [
    PACKAGE_DIR / "run_product_intel.py",
    PACKAGE_DIR / "feishu_product_intel_bot.py",
]


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


class MultiFileBatchRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protected_digests = {
            path: _digest(path) for path in PROTECTED_FILES if path.exists()
        }
        cls.temp_dir = TemporaryDirectory()
        cls.output_dir = Path(cls.temp_dir.name) / "batch"
        cls.result = run_multi_file_batch(
            inputs=SOURCE_FILES,
            source="auto",
            market="de",
            output_dir=cls.output_dir,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        for path, before in cls.protected_digests.items():
            if _digest(path) != before:
                raise AssertionError(f"Protected source was modified: {path}")
        cls.temp_dir.cleanup()

    def test_four_mock_files_and_sources(self) -> None:
        manifest = self.result["manifest"]
        self.assertEqual(manifest["input_count"], 4)
        self.assertEqual(
            [item["source_detected"] for item in manifest["inputs"]],
            EXPECTED_SOURCES,
        )
        self.assertTrue(
            all(item["mapping_confidence"] == "high" for item in manifest["inputs"])
        )

    def test_combined_totals_and_decisions(self) -> None:
        summary = self.result["summary"]
        self.assertEqual(summary["total_products"], 12)
        self.assertEqual(summary["decision_counts"], EXPECTED_DECISIONS)
        self.assertEqual(summary["next_action_conflicts"], 0)
        self.assertEqual(summary["duplicate_product_id_count"], 0)
        self.assertEqual(summary["error_count"], 0)

    def test_combined_products_retain_evidence_and_original_ids(self) -> None:
        combined = self.result["combined_manager_payload"]["products"]
        self.assertEqual(len(combined), 12)
        self.assertEqual(len({item["batch_product_key"] for item in combined}), 12)
        for product in combined:
            self.assertTrue(product.get("product_id"))
            self.assertTrue(product.get("batch_product_key"))
            self.assertIsInstance(product.get("evidence_pack"), dict)

        original_ids = []
        for item in self.result["manifest"]["inputs"]:
            payload_path = Path(item["output_dir"]) / "product_intel_manager_payload.json"
            payload = json.loads(payload_path.read_text(encoding="utf-8"))
            original_ids.extend(product["product_id"] for product in payload["products"])
        self.assertCountEqual(
            [product["product_id"] for product in combined],
            original_ids,
        )

    def test_per_file_and_combined_outputs_exist(self) -> None:
        for item in self.result["manifest"]["inputs"]:
            for filename in PER_FILE_OUTPUTS:
                path = Path(item["output_dir"]) / filename
                self.assertTrue(path.exists(), path)
                self.assertGreater(path.stat().st_size, 0, path)

        for filename in MERGED_OUTPUTS:
            path = self.output_dir / filename
            self.assertTrue(path.exists(), path)
            self.assertGreater(path.stat().st_size, 0, path)

        with (self.output_dir / "multi_file_combined_decision_table.csv").open(
            "r", encoding="utf-8-sig", newline=""
        ) as file:
            rows = list(csv.DictReader(file))
        self.assertEqual(len(rows), 12)

    def test_all_evidence_output_has_products_and_batch_keys(self) -> None:
        payload = json.loads(
            (self.output_dir / "multi_file_all_evidence.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload["product_count"], 12)
        self.assertEqual(len(payload["products"]), 12)
        for product in payload["products"]:
            self.assertIsInstance(product.get("evidence_pack"), dict)
            self.assertTrue(product.get("batch_product_key"))

    def test_input_dir_pattern_mode(self) -> None:
        with TemporaryDirectory() as output_dir:
            result = run_multi_file_batch(
                input_dir=PACKAGE_DIR,
                pattern="mock_*_products.xlsx",
                source="auto",
                market="de",
                output_dir=output_dir,
            )
        self.assertEqual(result["summary"]["total_input_files"], 4)
        self.assertEqual(result["summary"]["total_products"], 12)
        self.assertEqual(result["summary"]["decision_counts"], EXPECTED_DECISIONS)

    def test_single_file_mode(self) -> None:
        with TemporaryDirectory() as output_dir:
            result = run_multi_file_batch(
                inputs=[SOURCE_FILES[0]],
                source="auto",
                market="de",
                output_dir=output_dir,
            )
        self.assertEqual(result["summary"]["total_input_files"], 1)
        self.assertEqual(result["summary"]["total_products"], 3)
        self.assertEqual(
            result["manifest"]["inputs"][0]["source_detected"],
            "echotik",
        )

    def test_duplicate_product_ids_are_counted_and_keys_stay_unique(self) -> None:
        with TemporaryDirectory() as output_dir:
            result = run_multi_file_batch(
                inputs=[SOURCE_FILES[0], SOURCE_FILES[0]],
                source="auto",
                market="de",
                output_dir=output_dir,
            )
        products = result["combined_manager_payload"]["products"]
        self.assertEqual(result["summary"]["duplicate_product_id_count"], 3)
        self.assertEqual(len({item["batch_product_key"] for item in products}), 6)

    def test_missing_file_is_clear_error(self) -> None:
        with self.assertRaisesRegex(MultiFileBatchError, "does not exist"):
            run_multi_file_batch(
                inputs=[PACKAGE_DIR / "missing_products.xlsx"],
                output_dir=PACKAGE_DIR / "unused-output",
            )

    def test_runner_is_local_only_and_does_not_modify_protected_sources(self) -> None:
        runner_source = (PACKAGE_DIR / "multi_file_batch_runner.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("openai", runner_source.lower())
        self.assertNotIn("feishu", runner_source.lower())
        for path, before in self.protected_digests.items():
            self.assertEqual(_digest(path), before)


def main() -> None:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MultiFileBatchRunnerTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
