"""Tests for v1.23 Feishu multi-file evidence to LLM ops runner."""

from __future__ import annotations

import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from .feishu_multi_file_llm_ops_runner import (
    FeishuMultiFileLLMOpsRunnerError,
    run_feishu_multi_file_llm_ops,
)
from .multi_file_batch_runner import run_multi_file_batch


PACKAGE_DIR = Path(__file__).resolve().parent
PROTECTED_FILES = [
    PACKAGE_DIR / "run_product_intel.py",
    PACKAGE_DIR / "multi_file_batch_runner.py",
    PACKAGE_DIR / "feishu_product_intel_bot.py",
    PACKAGE_DIR / "job_queue.py",
]


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


class FailIfCalledClient:
    def create(self, **kwargs):  # pragma: no cover - defensive fake
        raise AssertionError("Real LLM client must not be called.")


class FeishuMultiFileLLMOpsRunnerTests(unittest.TestCase):
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

    def _build_evidence(self, temp_dir: str) -> Path:
        output = Path(temp_dir) / "multi"
        run_multi_file_batch(
            inputs=[
                PACKAGE_DIR / "mock_echotik_products.xlsx",
                PACKAGE_DIR / "mock_fastmoss_products.xlsx",
            ],
            source="auto",
            market="de",
            output_dir=output,
        )
        return output / "multi_file_all_evidence.json"

    def test_dry_run_limit_one_generates_final_outputs_without_real_llm(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence = self._build_evidence(temp_dir)
            output = Path(temp_dir) / "ops"
            summary = run_feishu_multi_file_llm_ops(
                evidence=evidence,
                output_dir=output,
                model="gpt-5.5",
                limit=1,
                real_llm=False,
                environ={},
                client=FailIfCalledClient(),
            )
            self.assertEqual(summary["total_products"], 6)
            self.assertFalse(summary["real_llm_requested"])
            self.assertEqual(summary["real_llm_called_count"], 0)
            self.assertEqual(summary["llm_review_result_counts"], {"insufficient_evidence": 1})
            self.assertTrue((output / "all_evidence_real_llm_judge_results.json").exists())
            self.assertTrue((output / "all_evidence_real_llm_judge_prompt_samples.json").exists())
            self.assertTrue((output / "all_evidence_with_real_llm_review.csv").exists())
            self.assertTrue((output / "final_ops_decision_table.csv").exists())
            self.assertTrue((output / "final_ops_action_summary.json").exists())
            self.assertTrue((output / "final_challenge_products.csv").exists())
            self.assertTrue((output / "final_review_note.md").exists())
            self.assertTrue((output / "feishu_multi_file_llm_ops_summary.json").exists())

    def test_resume_preserves_existing_real_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            evidence = self._build_evidence(temp_dir)
            products = json.loads(evidence.read_text(encoding="utf-8"))["products"]
            first = products[0]
            output = Path(temp_dir) / "ops"
            output.mkdir()
            existing = {
                "results": [
                    {
                        "product_id": first["product_id"],
                        "product_name": first["product_name"],
                        "rule_decision": first["decision"],
                        "review_result": "agree",
                        "confidence": "high",
                        "challenge_reason": "",
                        "missing_evidence": [],
                        "dimension_reviews": {},
                        "recommended_human_action": "",
                        "real_llm_called": True,
                        "runner_status": "success",
                        "runner_error": "",
                    }
                ]
            }
            (output / "all_evidence_real_llm_judge_results.json").write_text(
                json.dumps(existing), encoding="utf-8"
            )
            summary = run_feishu_multi_file_llm_ops(
                evidence=evidence,
                output_dir=output,
                limit=1,
                resume=True,
                real_llm=False,
                environ={},
                client=FailIfCalledClient(),
            )
            results = json.loads(
                (output / "all_evidence_real_llm_judge_results.json").read_text(
                    encoding="utf-8"
                )
            )["results"]
        first_result = next(
            item for item in results if item["product_id"] == first["product_id"]
        )
        self.assertTrue(first_result["real_llm_called"])
        self.assertEqual(first_result["runner_status"], "success")
        self.assertEqual(summary["real_llm_called_count"], 0)

    def test_missing_evidence_path_is_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(
                FeishuMultiFileLLMOpsRunnerError, "Evidence file does not exist"
            ):
                run_feishu_multi_file_llm_ops(
                    evidence=Path(temp_dir) / "missing.json",
                    output_dir=Path(temp_dir) / "ops",
                )


if __name__ == "__main__":
    unittest.main()
