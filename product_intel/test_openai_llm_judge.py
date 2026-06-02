"""Tests for the opt-in OpenAI LLM Judge adapter."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from .evidence_pack import DIMENSIONS
from .openai_llm_judge import (
    OpenAILLMJudgeError,
    RESULT_FIELDS,
    build_openai_judge_input,
    build_openai_request,
    run_openai_llm_judge,
    validate_openai_llm_judge_result,
)


PACKAGE_DIR = Path(__file__).resolve().parent


class FakeResponses:
    def __init__(self, output_text: str | None = None) -> None:
        self.calls: list[dict] = []
        self.output_text = output_text

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.output_text is None:
            raise AssertionError("OpenAI API must not be called.")
        return SimpleNamespace(output_text=self.output_text)


class FakeClient:
    def __init__(self, output_text: str | None = None) -> None:
        self.responses = FakeResponses(output_text)


def _sample_product() -> dict:
    payload_path = PACKAGE_DIR / "output_echotik" / "product_intel_manager_payload.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    return payload["products"][0]


def _valid_openai_json(product: dict) -> str:
    evidence = product["evidence_pack"]["evidence"]
    output = {
        "llm_decision_review": "agree",
        "llm_confidence": "medium",
        "dimension_reviews": {
            dimension: {
                "evidence_sufficiency": evidence[dimension]["coverage"],
                "reason": "仅基于 evidence_pack 复核。",
                "missing_evidence": list(evidence[dimension]["missing"]),
            }
            for dimension in DIMENSIONS
        },
        "challenge_rule_decision": False,
        "challenge_reason": "",
        "suggested_next_evidence": [],
        "llm_ops_note": "保持规则决策，按现有流程执行。",
    }
    return json.dumps(output, ensure_ascii=False)


class OpenAILLMJudgeTest(unittest.TestCase):
    def test_default_disabled_never_calls_openai(self) -> None:
        client = FakeClient()
        result = run_openai_llm_judge(_sample_product(), client=client, environ={})

        self.assertEqual(client.responses.calls, [])
        self.assertFalse(result["real_llm_called"])
        self.assertIn("默认关闭", result["recommended_human_action"])
        self.assertEqual(set(result), RESULT_FIELDS)

    def test_missing_api_key_never_calls_openai(self) -> None:
        client = FakeClient()
        result = run_openai_llm_judge(
            _sample_product(),
            client=client,
            environ={"PRODUCT_INTEL_REAL_LLM_ENABLED": "true"},
        )

        self.assertEqual(client.responses.calls, [])
        self.assertFalse(result["real_llm_called"])
        self.assertIn("OPENAI_API_KEY", result["recommended_human_action"])

    def test_request_is_bounded_to_judge_input_and_evidence_pack(self) -> None:
        product = _sample_product()
        product["secret_raw_source_row"] = "must-not-leak"
        judge_input = build_openai_judge_input(product)
        request = build_openai_request(judge_input, environ={})
        request_text = json.dumps(request, ensure_ascii=False)

        self.assertEqual(request["model"], "gpt-5.5")
        self.assertIn("evidence_pack", request_text)
        self.assertIn("只能基于 evidence_pack", request_text)
        self.assertNotIn("must-not-leak", request_text)
        self.assertNotIn("secret_raw_source_row", request_text)
        self.assertEqual(request["text"]["format"]["type"], "json_schema")
        self.assertTrue(request["text"]["format"]["strict"])

    def test_mocked_json_response_parses_into_adapter_contract(self) -> None:
        product = _sample_product()
        client = FakeClient(_valid_openai_json(product))
        result = run_openai_llm_judge(
            product,
            client=client,
            environ={
                "PRODUCT_INTEL_REAL_LLM_ENABLED": "true",
                "OPENAI_API_KEY": "test-key-not-real",
            },
        )
        self.assertEqual(len(client.responses.calls), 1)
        self.assertTrue(result["real_llm_called"])
        self.assertEqual(result["review_result"], "agree")
        self.assertEqual(result["rule_decision"], product["decision"])
        validate_openai_llm_judge_result(result)

    def test_non_json_response_raises_clear_error(self) -> None:
        product = _sample_product()
        client = FakeClient("not-json")
        with self.assertRaisesRegex(OpenAILLMJudgeError, "non-JSON"):
            run_openai_llm_judge(
                product,
                client=client,
                environ={
                    "PRODUCT_INTEL_REAL_LLM_ENABLED": "true",
                    "OPENAI_API_KEY": "test-key-not-real",
                },
            )

    def test_invalid_schema_response_raises_clear_error(self) -> None:
        product = _sample_product()
        client = FakeClient(json.dumps({"llm_decision_review": "agree"}))
        with self.assertRaisesRegex(OpenAILLMJudgeError, "contract validation"):
            run_openai_llm_judge(
                product,
                client=client,
                environ={
                    "PRODUCT_INTEL_REAL_LLM_ENABLED": "true",
                    "OPENAI_API_KEY": "test-key-not-real",
                },
            )

    def test_adapter_does_not_modify_rule_fields(self) -> None:
        product = _sample_product()
        original = copy.deepcopy(product)
        client = FakeClient(_valid_openai_json(product))
        result = run_openai_llm_judge(
            product,
            client=client,
            environ={
                "PRODUCT_INTEL_REAL_LLM_ENABLED": "true",
                "OPENAI_API_KEY": "test-key-not-real",
            },
        )

        self.assertEqual(product["decision"], original["decision"])
        self.assertEqual(product["opportunity_score"], original["opportunity_score"])
        self.assertEqual(product["next_action"], original["next_action"])
        self.assertEqual(result["rule_decision"], original["decision"])

    def test_aggregate_all_evidence_payload_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "not an aggregate payload"):
            build_openai_judge_input({"products": [_sample_product()]})


if __name__ == "__main__":
    unittest.main()
