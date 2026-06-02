"""Tests for the Product Intel v1.10 real LLM Judge batch runner."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from .evidence_pack import DIMENSIONS
from .llm_judge_merger import merge_llm_judge_results
from .real_llm_judge_runner import run_batch, write_runner_outputs


PACKAGE_DIR = Path(__file__).resolve().parent


def evidence_payload() -> dict:
    path = PACKAGE_DIR / "output_next_round" / "all_evidence.json"
    return json.loads(path.read_text(encoding="utf-8"))


def valid_response_json(product: dict) -> str:
    evidence = product["evidence_pack"]["evidence"]
    return json.dumps(
        {
            "llm_decision_review": "agree",
            "llm_confidence": "high",
            "dimension_reviews": {
                dimension: {
                    "evidence_sufficiency": evidence[dimension]["coverage"],
                    "reason": "仅基于 evidence_pack 测试。",
                    "missing_evidence": list(evidence[dimension]["missing"]),
                }
                for dimension in DIMENSIONS
            },
            "challenge_rule_decision": False,
            "challenge_reason": "",
            "suggested_next_evidence": [],
            "llm_ops_note": "保持规则结果。",
        },
        ensure_ascii=False,
    )


class FakeResponses:
    def __init__(self, products: list[dict], fail_on_call: int | None = None) -> None:
        self.products = products
        self.fail_on_call = fail_on_call
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        call_number = len(self.calls)
        if call_number == self.fail_on_call:
            raise RuntimeError("fake request failed with key test-key-not-real")
        return SimpleNamespace(
            output_text=valid_response_json(self.products[call_number - 1])
        )


class FakeClient:
    def __init__(self, products: list[dict], fail_on_call: int | None = None) -> None:
        self.responses = FakeResponses(products, fail_on_call=fail_on_call)


class FailIfCalledClient:
    class Responses:
        def create(self, **kwargs):
            raise AssertionError("OpenAI API must not be called.")

    responses = Responses()


class RealLLMJudgeRunnerTest(unittest.TestCase):
    def test_default_dry_run_never_calls_client(self) -> None:
        results, _, summary = run_batch(
            evidence_payload(),
            limit=2,
            client=FailIfCalledClient(),
            environ={},
        )
        self.assertEqual(summary["attempted_products"], 2)
        self.assertEqual(summary["real_llm_called_count"], 0)
        self.assertEqual(summary["disabled_count"], 2)
        self.assertTrue(all(not item["real_llm_called"] for item in results["results"]))

    def test_real_requested_without_enabled_env_never_calls_client(self) -> None:
        results, _, summary = run_batch(
            evidence_payload(),
            real_llm_requested=True,
            limit=1,
            client=FailIfCalledClient(),
            environ={"OPENAI_API_KEY": "test-key-not-real"},
        )
        self.assertEqual(summary["real_llm_called_count"], 0)
        self.assertIn("未设置为 true", results["results"][0]["recommended_human_action"])

    def test_real_requested_without_api_key_never_calls_client(self) -> None:
        results, _, summary = run_batch(
            evidence_payload(),
            real_llm_requested=True,
            limit=1,
            client=FailIfCalledClient(),
            environ={"PRODUCT_INTEL_REAL_LLM_ENABLED": "true"},
        )
        self.assertEqual(summary["real_llm_called_count"], 0)
        self.assertIn("OPENAI_API_KEY", results["results"][0]["recommended_human_action"])

    def test_limit_one_processes_one_product(self) -> None:
        results, samples, summary = run_batch(evidence_payload(), limit=1, environ={})
        self.assertEqual(len(results["results"]), 1)
        self.assertEqual(len(samples["samples"]), 1)
        self.assertEqual(summary["attempted_products"], 1)
        self.assertEqual(summary["skipped_count"], 11)

    def test_start_index_skips_previous_products(self) -> None:
        payload = evidence_payload()
        results, _, summary = run_batch(payload, limit=1, start_index=2, environ={})
        self.assertEqual(results["results"][0]["product_id"], payload["products"][2]["product_id"])
        self.assertEqual(summary["start_index"], 2)

    def test_fake_client_success_sets_real_called_and_success(self) -> None:
        payload = evidence_payload()
        selected = payload["products"][:1]
        client = FakeClient(selected)
        results, _, summary = run_batch(
            payload,
            real_llm_requested=True,
            limit=1,
            client=client,
            environ={
                "PRODUCT_INTEL_REAL_LLM_ENABLED": "true",
                "OPENAI_API_KEY": "test-key-not-real",
            },
        )
        self.assertEqual(len(client.responses.calls), 1)
        self.assertTrue(results["results"][0]["real_llm_called"])
        self.assertEqual(results["results"][0]["runner_status"], "success")
        self.assertEqual(summary["success_count"], 1)

    def test_fake_client_failure_records_error_and_continues(self) -> None:
        payload = evidence_payload()
        selected = payload["products"][:2]
        client = FakeClient(selected, fail_on_call=1)
        results, _, summary = run_batch(
            payload,
            real_llm_requested=True,
            limit=2,
            client=client,
            environ={
                "PRODUCT_INTEL_REAL_LLM_ENABLED": "true",
                "OPENAI_API_KEY": "test-key-not-real",
            },
        )
        self.assertEqual(len(client.responses.calls), 2)
        self.assertEqual(results["results"][0]["runner_status"], "error")
        self.assertFalse(results["results"][0]["real_llm_called"])
        self.assertNotIn("test-key-not-real", results["results"][0]["runner_error"])
        self.assertEqual(results["results"][1]["runner_status"], "success")
        self.assertEqual(summary["error_count"], 1)
        self.assertEqual(summary["success_count"], 1)

    def test_output_files_exist_and_prompt_samples_do_not_include_key(self) -> None:
        payload = evidence_payload()
        results, samples, summary = run_batch(payload, limit=1, environ={})
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_runner_outputs(results, samples, summary, temp_dir)
            for path in paths.values():
                self.assertTrue(path.exists())
                self.assertGreater(path.stat().st_size, 0)
            prompt_text = paths["prompt_samples"].read_text(encoding="utf-8")
            self.assertNotIn("OPENAI_API_KEY", prompt_text)
            self.assertNotIn("test-key-not-real", prompt_text)

    def test_runner_does_not_modify_rule_fields(self) -> None:
        payload = evidence_payload()
        original = copy.deepcopy(payload)
        run_batch(payload, limit=2, environ={})
        for current, before in zip(payload["products"], original["products"]):
            self.assertEqual(current["decision"], before["decision"])
            self.assertEqual(current["opportunity_score"], before["opportunity_score"])
            self.assertEqual(current["next_action"], before["next_action"])

    def test_real_results_can_be_merged(self) -> None:
        payload = evidence_payload()
        results, samples, summary = run_batch(payload, limit=2, environ={})
        merged = merge_llm_judge_results(payload, results)
        self.assertEqual(merged["product_count"], 12)
        self.assertEqual(merged["products"][0]["llm_review_result"], "insufficient_evidence")
        self.assertEqual(merged["products"][2]["llm_review_result"], "not_reviewed")
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_runner_outputs(
                results,
                samples,
                summary,
                temp_dir,
                merge=True,
                evidence_payload=payload,
            )
            self.assertIn("merge_merged_json", paths)
            self.assertTrue(paths["merge_merged_json"].exists())


if __name__ == "__main__":
    unittest.main()

