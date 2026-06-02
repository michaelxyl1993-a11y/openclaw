"""Build the strict JSON prompt for a future Product Intel LLM Judge."""

from __future__ import annotations

import json
from typing import Any

from .llm_judge_contract import validate_llm_judge_input


def build_llm_judge_prompt(judge_input: dict[str, Any]) -> str:
    validate_llm_judge_input(judge_input)
    return "\n".join([
        "你是 Product Intel LLM Judge。",
        "只能基于 evidence_pack 中的 JSON 证据判断。",
        "不允许脑补，不允许使用外部知识，不允许使用外部实时信息。",
        "证据不足时必须明确输出 missing_evidence。",
        "不允许直接修改或覆盖 rule_decision，只能通过 challenge_rule_decision 提出 challenge。",
        "输出必须是严格 JSON，不要输出 Markdown，不要输出 JSON 之外的解释。",
        "",
        "LLM Judge 输入 JSON：",
        json.dumps(judge_input, ensure_ascii=False, indent=2),
    ])
