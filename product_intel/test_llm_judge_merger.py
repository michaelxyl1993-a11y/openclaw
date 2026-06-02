"""Tests for the Product Intel v1.9 LLM Judge result merger."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from .llm_judge_merger import (
    build_ops_summary,
    human_review_priority,
    merge_llm_judge_results,
    merge_product,
    write_outputs,
)


PACKAGE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PACKAGE_DIR / "output_next_round"


def load_fixture(name: str) -> dict:
    return json.loads((OUTPUT_DIR / name).read_text(encoding="utf-8"))


def sample_product() -> dict:
    return copy.deepcopy(load_fixture("all_evidence.json")["products"][0])


def real_style_result(
    product: dict,
    review_result: str = "agree",
    confidence: str = "high",
    challenge_reason: str = "",
) -> dict:
    evidence = product["evidence_pack"]["evidence"]
    return {
        "product_id": product["product_id"],
        "product_name": product["product_name"],
        "rule_decision": product["decision"],
        "review_result": review_result,
        "confidence": confidence,
        "challenge_reason": challenge_reason,
        "missing_evidence": [],
        "dimension_reviews": {
            key: {
                "evidence_sufficiency": value["coverage"],
                "reason": "test",
                "missing_evidence": value["missing"],
            }
            for key, value in evidence.items()
        },
        "recommended_human_action": "test action",
        "real_llm_called": True,
    }


class LLMJudgeMergerTest(unittest.TestCase):
    def test_agree_high_confidence_is_low_priority(self) -> None:
        product = sample_product()
        merged = merge_product(product, real_style_result(product))
        self.assertEqual(merged["llm_review_result"], "agree")
        self.assertEqual(merged["final_human_review_priority"], "low")

    def test_challenge_is_high_priority(self) -> None:
        product = sample_product()
        result = real_style_result(product, "challenge", "medium", "test challenge")
        merged = merge_product(product, result)
        self.assertEqual(merged["final_human_review_priority"], "high")

    def test_insufficient_evidence_and_weak_coverage_is_high_priority(self) -> None:
        product = sample_product()
        result = real_style_result(product, "insufficient_evidence", "low")
        merged = merge_product(product, result)
        self.assertEqual(merged["overall_evidence_coverage"], "weak")
        self.assertEqual(merged["final_human_review_priority"], "high")

    def test_missing_result_is_not_reviewed_and_medium_priority(self) -> None:
        merged = merge_product(sample_product(), None)
        self.assertEqual(merged["llm_review_result"], "not_reviewed")
        self.assertEqual(merged["llm_confidence"], "missing")
        self.assertEqual(merged["final_human_review_priority"], "medium")

    def test_main_push_challenge_has_explicit_reason(self) -> None:
        product = sample_product()
        product["decision"] = "main_push"
        result = real_style_result(product, "challenge", "medium", "test challenge")
        merged = merge_product(product, result)
        self.assertEqual(merged["final_human_review_priority"], "high")
        self.assertEqual(
            merged["final_human_review_reason"],
            "规则建议主推，但 LLM Judge 提出挑战，需人工复核",
        )

    def test_merge_does_not_modify_rule_fields(self) -> None:
        product = sample_product()
        original = copy.deepcopy(product)
        merged = merge_product(product, real_style_result(product))
        self.assertEqual(product, original)
        self.assertEqual(merged["decision"], original["decision"])
        self.assertEqual(merged["rule_decision"], original["decision"])
        self.assertEqual(merged["opportunity_score"], original["opportunity_score"])
        self.assertEqual(merged["next_action"], original["next_action"])

    def test_mock_judge_fixture_is_supported(self) -> None:
        evidence = load_fixture("all_evidence.json")
        judge_results = load_fixture("all_evidence_mock_llm_judge_results.json")
        merged = merge_llm_judge_results(evidence, judge_results)
        summary = build_ops_summary(merged["products"])
        self.assertEqual(merged["product_count"], 12)
        self.assertEqual(summary["total_products"], 12)
        self.assertEqual(summary["missing_judge_result_count"], 0)
        self.assertEqual(
            sum(summary["rule_decision_counts"].values()),
            summary["total_products"],
        )

    def test_missing_judge_item_is_counted(self) -> None:
        evidence = {"products": [sample_product()]}
        merged = merge_llm_judge_results(evidence, {"products": []})
        summary = build_ops_summary(merged["products"])
        self.assertEqual(summary["missing_judge_result_count"], 1)

    def test_write_outputs_generates_json_csv_and_markdown(self) -> None:
        product = sample_product()
        merged = merge_llm_judge_results(
            {"products": [product]},
            {"products": [real_style_result(product)]},
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_outputs(merged, temp_dir)
            self.assertEqual(set(paths), {"merged_json", "merged_csv", "summary_json", "summary_md"})
            for path in paths.values():
                self.assertTrue(path.exists())
                self.assertGreater(path.stat().st_size, 0)
            markdown = paths["summary_md"].read_text(encoding="utf-8")
            self.assertIn("# Product Intel v1.9 LLM Review Ops Summary", markdown)

    def test_priority_helper_does_not_promote_hold_agree(self) -> None:
        priority, _ = human_review_priority("hold", "agree", "high", "strong")
        self.assertEqual(priority, "low")


if __name__ == "__main__":
    unittest.main()

