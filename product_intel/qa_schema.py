"""Product Intel QA schema definitions."""

from __future__ import annotations

from typing import Any


QA_SCHEMA: dict[str, Any] = {
    "qa_status": "pass | review | fail",
    "visual_match_score": "integer 0-100",
    "claim_match_score": "integer 0-100",
    "risk_level": "low | medium | high",
    "issues": [
        {
            "issue_type": "string",
            "severity": "low | medium | high",
            "evidence": "string",
            "suggestion": "string",
        }
    ],
    "human_review_required": "boolean",
    "final_publishable": "boolean",
}


def empty_qa_result() -> dict[str, Any]:
    return {
        "qa_status": "review",
        "visual_match_score": 0,
        "claim_match_score": 0,
        "risk_level": "medium",
        "issues": [],
        "human_review_required": True,
        "final_publishable": False,
    }
