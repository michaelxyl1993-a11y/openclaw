"""Opt-in OpenAI Responses API adapter for Product Intel LLM Judge reviews."""

from __future__ import annotations

import json
import os
from typing import Any, Mapping

from .evidence_pack import DIMENSIONS
from .llm_judge_contract import (
    build_llm_judge_input,
    normalize_llm_judge_output,
    validate_llm_judge_input,
    validate_llm_judge_output,
)
from .llm_judge_prompt import build_llm_judge_prompt


DEFAULT_MODEL = "gpt-5.5"
REAL_LLM_ENABLED_ENV = "PRODUCT_INTEL_REAL_LLM_ENABLED"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_MODEL_ENV = "OPENAI_MODEL"

RESULT_FIELDS = {
    "product_id",
    "product_name",
    "rule_decision",
    "review_result",
    "confidence",
    "challenge_reason",
    "missing_evidence",
    "dimension_reviews",
    "recommended_human_action",
    "real_llm_called",
}


class OpenAILLMJudgeError(RuntimeError):
    """Raised when an enabled real LLM review cannot produce a valid result."""


def is_real_llm_enabled(environ: Mapping[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    return env.get(REAL_LLM_ENABLED_ENV, "").strip().lower() == "true"


def build_openai_judge_input(evidence_item: dict[str, Any]) -> dict[str, Any]:
    """Build the bounded judge input from one product evidence item."""
    if not isinstance(evidence_item, dict):
        raise ValueError("OpenAI LLM Judge requires one product evidence item.")
    if "products" in evidence_item:
        raise ValueError(
            "OpenAI LLM Judge accepts one product evidence item, not an aggregate payload."
        )
    if not isinstance(evidence_item.get("evidence_pack"), dict):
        raise ValueError("OpenAI LLM Judge requires an evidence_pack for one product.")

    return build_llm_judge_input(evidence_item)


def build_openai_response_schema() -> dict[str, Any]:
    dimension_review_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "evidence_sufficiency": {
                "type": "string",
                "enum": ["strong", "medium", "weak", "missing"],
            },
            "reason": {"type": "string"},
            "missing_evidence": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["evidence_sufficiency", "reason", "missing_evidence"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "llm_decision_review": {
                "type": "string",
                "enum": ["agree", "challenge", "insufficient_evidence"],
            },
            "llm_confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
            },
            "dimension_reviews": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    dimension: dimension_review_schema for dimension in DIMENSIONS
                },
                "required": list(DIMENSIONS),
            },
            "challenge_rule_decision": {"type": "boolean"},
            "challenge_reason": {"type": "string"},
            "suggested_next_evidence": {
                "type": "array",
                "items": {"type": "string"},
            },
            "llm_ops_note": {"type": "string"},
        },
        "required": [
            "llm_decision_review",
            "llm_confidence",
            "dimension_reviews",
            "challenge_rule_decision",
            "challenge_reason",
            "suggested_next_evidence",
            "llm_ops_note",
        ],
    }


def build_openai_request(
    judge_input: dict[str, Any],
    *,
    model: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Create a Responses API request containing only the bounded judge input."""
    validate_llm_judge_input(judge_input)
    env = environ if environ is not None else os.environ
    selected_model = model or env.get(OPENAI_MODEL_ENV) or DEFAULT_MODEL
    return {
        "model": selected_model,
        "input": build_llm_judge_prompt(judge_input),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "product_intel_llm_judge_output",
                "strict": True,
                "schema": build_openai_response_schema(),
            }
        },
    }


def parse_openai_response(response: Any) -> dict[str, Any]:
    output_text = (
        response.get("output_text")
        if isinstance(response, dict)
        else getattr(response, "output_text", None)
    )
    if not isinstance(output_text, str) or not output_text.strip():
        raise OpenAILLMJudgeError("OpenAI Responses API returned no JSON output_text.")
    try:
        raw_output = json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise OpenAILLMJudgeError(
            "OpenAI LLM Judge returned non-JSON output."
        ) from exc

    try:
        validate_llm_judge_output(raw_output)
        normalized = normalize_llm_judge_output(raw_output)
        validate_llm_judge_output(normalized)
    except (TypeError, ValueError) as exc:
        raise OpenAILLMJudgeError(
            f"OpenAI LLM Judge output failed contract validation: {exc}"
        ) from exc
    return normalized


def validate_openai_llm_judge_result(result: dict[str, Any]) -> None:
    if not isinstance(result, dict):
        raise ValueError("OpenAI LLM Judge result must be a dict.")
    if set(result) != RESULT_FIELDS:
        raise ValueError("OpenAI LLM Judge result fields do not match the adapter contract.")
    if result["review_result"] not in {"agree", "challenge", "insufficient_evidence"}:
        raise ValueError("Invalid review_result.")
    if result["confidence"] not in {"high", "medium", "low"}:
        raise ValueError("Invalid confidence.")
    if not isinstance(result["real_llm_called"], bool):
        raise ValueError("real_llm_called must be a boolean.")
    validate_llm_judge_output(
        {
            "llm_decision_review": result["review_result"],
            "llm_confidence": result["confidence"],
            "dimension_reviews": result["dimension_reviews"],
            "challenge_rule_decision": result["review_result"] == "challenge",
            "challenge_reason": result["challenge_reason"],
            "suggested_next_evidence": result["missing_evidence"],
            "llm_ops_note": result["recommended_human_action"],
        }
    )


def run_openai_llm_judge(
    evidence_item: dict[str, Any],
    *,
    client: Any | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run an explicitly enabled real review or return a clear disabled result."""
    env = environ if environ is not None else os.environ
    judge_input = build_openai_judge_input(evidence_item)

    if not is_real_llm_enabled(env):
        return _build_not_called_result(
            judge_input,
            "真实 GPT-5.5 Judge 默认关闭；设置 PRODUCT_INTEL_REAL_LLM_ENABLED=true 后才会调用。",
        )

    api_key = env.get(OPENAI_API_KEY_ENV, "").strip()
    if not api_key:
        return _build_not_called_result(
            judge_input,
            "未配置 OPENAI_API_KEY，未调用真实 GPT-5.5 Judge。",
        )

    if client is None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise OpenAILLMJudgeError(
                "The openai package is required for enabled real LLM reviews."
            ) from exc
        client = OpenAI(api_key=api_key)

    request = build_openai_request(judge_input, environ=env)
    try:
        response = client.responses.create(**request)
    except Exception as exc:
        raise OpenAILLMJudgeError(f"OpenAI Responses API call failed: {exc}") from exc

    contract_output = parse_openai_response(response)
    result = _build_called_result(judge_input, contract_output)
    validate_openai_llm_judge_result(result)
    return result


def _build_called_result(
    judge_input: dict[str, Any], contract_output: dict[str, Any]
) -> dict[str, Any]:
    return {
        "product_id": judge_input["product_id"],
        "product_name": judge_input["product_name"],
        "rule_decision": judge_input["rule_decision"],
        "review_result": contract_output["llm_decision_review"],
        "confidence": contract_output["llm_confidence"],
        "challenge_reason": contract_output["challenge_reason"],
        "missing_evidence": contract_output["suggested_next_evidence"],
        "dimension_reviews": contract_output["dimension_reviews"],
        "recommended_human_action": contract_output["llm_ops_note"],
        "real_llm_called": True,
    }


def _build_not_called_result(
    judge_input: dict[str, Any], message: str
) -> dict[str, Any]:
    evidence = judge_input["evidence_pack"]["evidence"]
    dimension_reviews = {
        dimension: {
            "evidence_sufficiency": evidence[dimension]["coverage"],
            "reason": message,
            "missing_evidence": list(evidence[dimension]["missing"]),
        }
        for dimension in DIMENSIONS
    }
    result = {
        "product_id": judge_input["product_id"],
        "product_name": judge_input["product_name"],
        "rule_decision": judge_input["rule_decision"],
        "review_result": "insufficient_evidence",
        "confidence": "low",
        "challenge_reason": "",
        "missing_evidence": sorted(
            {
                missing
                for review in dimension_reviews.values()
                for missing in review["missing_evidence"]
            }
        ),
        "dimension_reviews": dimension_reviews,
        "recommended_human_action": message,
        "real_llm_called": False,
    }
    validate_openai_llm_judge_result(result)
    return result
