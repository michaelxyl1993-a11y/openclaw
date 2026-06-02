"""Local mock LLM Judge for contract testing. This module never calls an API."""

from __future__ import annotations

from typing import Any

from .evidence_pack import DIMENSIONS
from .llm_judge_contract import normalize_llm_judge_output, validate_llm_judge_input


def unique_missing(evidence: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    seen: set[str] = set()
    for dimension in DIMENSIONS:
        item = evidence.get(dimension, {})
        values = item.get("missing", []) if isinstance(item, dict) else []
        for value in values if isinstance(values, list) else []:
            text = str(value)
            if text and text not in seen:
                seen.add(text)
                missing.append(text)
    return missing


def mock_llm_judge(judge_input: dict[str, Any]) -> dict[str, Any]:
    validate_llm_judge_input(judge_input)
    evidence_pack = judge_input["evidence_pack"]
    evidence = evidence_pack["evidence"]
    overall = evidence_pack.get("overall_evidence_coverage", "missing")
    ops_risk_note = str(judge_input.get("ops_risk_note", ""))
    challenge = ops_risk_note.startswith("必须人工复核：")
    if challenge:
        review = "challenge"
        confidence = "medium"
        challenge_reason = "规则结果保留，但运营发布前需要人工复核风险项。"
    elif overall in {"weak", "missing"}:
        review = "insufficient_evidence"
        confidence = "low"
        challenge_reason = ""
    else:
        review = "agree"
        confidence = "high" if overall == "strong" else "medium"
        challenge_reason = ""
    output = {
        "llm_decision_review": review,
        "llm_confidence": confidence,
        "dimension_reviews": {
            dimension: {
                "evidence_sufficiency": evidence[dimension]["coverage"],
                "reason": f"仅基于 evidence_pack：{dimension} 覆盖率为 {evidence[dimension]['coverage']}。",
                "missing_evidence": evidence[dimension]["missing"],
            }
            for dimension in DIMENSIONS
        },
        "challenge_rule_decision": challenge,
        "challenge_reason": challenge_reason,
        "suggested_next_evidence": unique_missing(evidence)[:12],
        "llm_ops_note": (
            "本地 mock judge 仅验证合同，不调用外部 API，也不覆盖规则决策。"
        ),
    }
    return normalize_llm_judge_output(output)
