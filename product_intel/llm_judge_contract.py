"""Local-only input and output contracts for a future Product Intel LLM Judge."""

from __future__ import annotations

from typing import Any

from .evidence_pack import DIMENSIONS


CONTRACT_VERSION = "product_intel_llm_judge_v1"
REVIEW_VALUES = {"agree", "challenge", "insufficient_evidence"}
CONFIDENCE_VALUES = {"high", "medium", "low"}
COVERAGE_VALUES = {"strong", "medium", "weak", "missing"}
INPUT_RULES = [
    "只能基于 evidence_pack 判断",
    "不允许使用外部知识脑补",
    "证据不足必须输出 missing_evidence",
    "不能直接覆盖 rule_decision，只能提出 challenge",
]


def require_fields(payload: dict[str, Any], fields: list[str], label: str) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise ValueError(f"{label} missing required fields: {', '.join(missing)}")


def build_llm_judge_input(product: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "contract_version": CONTRACT_VERSION,
        "product_id": str(product.get("product_id", "")),
        "product_name": str(product.get("product_name", "")),
        "market": str(product.get("evidence_pack", {}).get("market") or product.get("market") or ""),
        "source_platform": str(product.get("source_platform", "")),
        "rule_decision": str(product.get("decision", "")),
        "rule_score": int(product.get("opportunity_score", 0) or 0),
        "risk_flags": list(product.get("risk_flags", [])) if isinstance(product.get("risk_flags", []), list) else [],
        "ops_risk_note": str(product.get("ops_risk_note", "")),
        "evidence_pack": product.get("evidence_pack", {}),
        "instruction": {
            "role": "Product Intel LLM Judge",
            "rules": list(INPUT_RULES),
        },
    }
    validate_llm_judge_input(payload)
    return payload


def validate_llm_judge_input(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValueError("LLM Judge input must be a dict")
    require_fields(payload, [
        "contract_version", "product_id", "product_name", "market", "source_platform",
        "rule_decision", "rule_score", "risk_flags", "ops_risk_note", "evidence_pack", "instruction",
    ], "LLM Judge input")
    if payload["contract_version"] != CONTRACT_VERSION:
        raise ValueError(f"unsupported LLM Judge contract version: {payload['contract_version']}")
    if payload["rule_decision"] not in {"main_push", "small_test", "hold", "reject"}:
        raise ValueError(f"invalid rule_decision: {payload['rule_decision']}")
    if not isinstance(payload["rule_score"], int):
        raise ValueError("rule_score must be an int")
    if not isinstance(payload["risk_flags"], list):
        raise ValueError("risk_flags must be a list")
    evidence_pack = payload["evidence_pack"]
    if not isinstance(evidence_pack, dict):
        raise ValueError("evidence_pack must be a dict")
    evidence = evidence_pack.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != set(DIMENSIONS):
        raise ValueError("evidence_pack must contain exactly 8 evidence dimensions")
    for dimension, item in evidence.items():
        if not isinstance(item, dict):
            raise ValueError(f"{dimension}: evidence item must be a dict")
        if item.get("coverage") not in COVERAGE_VALUES:
            raise ValueError(f"{dimension}: invalid coverage")
        if not isinstance(item.get("missing"), list):
            raise ValueError(f"{dimension}: missing must be a list")
    instruction = payload["instruction"]
    if not isinstance(instruction, dict) or instruction.get("role") != "Product Intel LLM Judge":
        raise ValueError("instruction.role must be Product Intel LLM Judge")
    if instruction.get("rules") != INPUT_RULES:
        raise ValueError("instruction.rules must preserve the evidence-bounded Judge rules")


def normalize_dimension_review(value: Any) -> dict[str, Any]:
    review = value if isinstance(value, dict) else {}
    sufficiency = str(review.get("evidence_sufficiency", "missing"))
    if sufficiency not in COVERAGE_VALUES:
        sufficiency = "missing"
    missing = review.get("missing_evidence", [])
    return {
        "evidence_sufficiency": sufficiency,
        "reason": str(review.get("reason", "")),
        "missing_evidence": [str(item) for item in missing] if isinstance(missing, list) else [],
    }


def normalize_llm_judge_output(output: dict[str, Any]) -> dict[str, Any]:
    raw = output if isinstance(output, dict) else {}
    review = str(raw.get("llm_decision_review", "insufficient_evidence"))
    if review not in REVIEW_VALUES:
        review = "insufficient_evidence"
    confidence = str(raw.get("llm_confidence", "low"))
    if confidence not in CONFIDENCE_VALUES:
        confidence = "low"
    raw_dimensions = raw.get("dimension_reviews", {})
    if not isinstance(raw_dimensions, dict):
        raw_dimensions = {}
    normalized = {
        "llm_decision_review": review,
        "llm_confidence": confidence,
        "dimension_reviews": {
            dimension: normalize_dimension_review(raw_dimensions.get(dimension))
            for dimension in DIMENSIONS
        },
        "challenge_rule_decision": bool(raw.get("challenge_rule_decision", False)),
        "challenge_reason": str(raw.get("challenge_reason", "")),
        "suggested_next_evidence": [
            str(item) for item in raw.get("suggested_next_evidence", [])
        ] if isinstance(raw.get("suggested_next_evidence", []), list) else [],
        "llm_ops_note": str(raw.get("llm_ops_note", "")),
    }
    validate_llm_judge_output(normalized)
    return normalized


def validate_llm_judge_output(output: dict[str, Any]) -> None:
    if not isinstance(output, dict):
        raise ValueError("LLM Judge output must be a dict")
    require_fields(output, [
        "llm_decision_review", "llm_confidence", "dimension_reviews",
        "challenge_rule_decision", "challenge_reason", "suggested_next_evidence", "llm_ops_note",
    ], "LLM Judge output")
    if output["llm_decision_review"] not in REVIEW_VALUES:
        raise ValueError(f"invalid llm_decision_review: {output['llm_decision_review']}")
    if output["llm_confidence"] not in CONFIDENCE_VALUES:
        raise ValueError(f"invalid llm_confidence: {output['llm_confidence']}")
    if not isinstance(output["challenge_rule_decision"], bool):
        raise ValueError("challenge_rule_decision must be a bool")
    if output["challenge_rule_decision"] and not output["challenge_reason"]:
        raise ValueError("challenge_reason is required when challenge_rule_decision is true")
    if not isinstance(output["suggested_next_evidence"], list):
        raise ValueError("suggested_next_evidence must be a list")
    dimensions = output["dimension_reviews"]
    if not isinstance(dimensions, dict) or set(dimensions) != set(DIMENSIONS):
        raise ValueError("dimension_reviews must contain exactly 8 dimensions")
    for dimension, review in dimensions.items():
        if not isinstance(review, dict):
            raise ValueError(f"{dimension}: review must be a dict")
        require_fields(review, ["evidence_sufficiency", "reason", "missing_evidence"], f"{dimension} review")
        if review["evidence_sufficiency"] not in COVERAGE_VALUES:
            raise ValueError(f"{dimension}: invalid evidence_sufficiency")
        if not isinstance(review["missing_evidence"], list):
            raise ValueError(f"{dimension}: missing_evidence must be a list")
