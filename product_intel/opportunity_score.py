"""Lightweight product opportunity scoring."""

from __future__ import annotations

import re
from typing import Any


def parse_number(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip().replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return 0.0
    return float(match.group(0))


def parse_percent(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return 0.0
    number = float(match.group(0))
    if "%" in text:
        return number / 100.0
    return number


def score_product_opportunity(fact_sheet: dict[str, Any]) -> dict[str, Any]:
    performance = fact_sheet.get("performance", {})
    score = 35
    reasons: list[str] = []
    risk_flags: list[str] = []

    growth_7d = parse_percent(performance.get("growth_7d", 0))
    growth_30d = parse_percent(performance.get("growth_30d", 0))
    related_video_count = int(parse_number(performance.get("related_video_count", 0)))
    related_influencer_count = int(parse_number(performance.get("related_influencer_count", 0)))
    sales = int(parse_number(performance.get("sales", 0)))
    rating = parse_number(performance.get("rating", 0))
    review_count = int(parse_number(performance.get("review_count", 0)))
    commission_rate = parse_percent(fact_sheet.get("commission_rate", 0))
    risk_level = str(fact_sheet.get("risk_level", "medium")).lower()
    human_review_required = bool(fact_sheet.get("human_review_required", True))

    if growth_7d > 0.2:
        score += 15
        reasons.append("7-day growth is above 20%.")
    if growth_30d > 0.3:
        score += 15
        reasons.append("30-day growth is above 30%.")
    if related_video_count > 10:
        score += 10
        reasons.append("There are more than 10 related videos.")
    if related_influencer_count > 10:
        score += 10
        reasons.append("There are more than 10 related influencers.")
    if commission_rate >= 0.08:
        score += 10
        reasons.append("Commission rate is at least 8%.")
    if sales >= 3000:
        score += 8
        reasons.append("Sales volume is already meaningful.")
    if rating >= 4.5 and review_count >= 100:
        score += 7
        reasons.append("Rating and review count show basic buyer validation.")

    if risk_level == "high":
        score -= 25
        risk_flags.append("High product risk level.")
    elif risk_level == "medium":
        score -= 10
        risk_flags.append("Medium product risk level.")

    if human_review_required:
        score -= 5
        risk_flags.append("Human review is required.")

    score = max(0, min(100, score))

    if sales < 100 and (growth_7d > 0.2 or growth_30d > 0.3):
        decision = "small_test"
        reasons.append("Sales are still low, but growth suggests a small test is reasonable.")
    elif score >= 75:
        decision = "main_push"
    elif score >= 55:
        decision = "small_test"
    elif score >= 40:
        decision = "observe"
    else:
        decision = "reject"

    suggested_daily_volume = "low"
    if decision == "main_push":
        suggested_daily_volume = "high"
    elif decision == "small_test":
        suggested_daily_volume = "medium"

    suggested_content_formats = {
        "photo": True,
        "video": related_video_count > 10 or decision in {"main_push", "small_test"},
    }

    hook_types = [
        str(hook.get("hook_type", ""))
        for hook in fact_sheet.get("hook_recommendations", [])
        if isinstance(hook, dict)
    ]
    hook_summary = ", ".join(hook_types[:3]) or "problem_solution, daily_usefulness"

    return {
        "opportunity_score": score,
        "decision": decision,
        "reasons": reasons,
        "risk_flags": risk_flags,
        "suggested_content_formats": suggested_content_formats,
        "suggested_daily_volume": suggested_daily_volume,
        "content_angle_summary": f"Start with {hook_summary}; keep claims grounded in the Product Fact Sheet.",
    }
