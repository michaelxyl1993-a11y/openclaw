"""Rule-based 8-dimension product selection scoring."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .opportunity_score import parse_number, parse_percent


DIMENSION_NAMES = {
    "profit_window": "利润窗口期判断",
    "demand_pain": "平台评论 / 需求痛点分析",
    "external_trend": "外部趋势 / 舆论 / 热点",
    "seasonality": "季节判断",
    "competition": "跟卖与竞争判断",
    "merchant_quality": "商家维度判断",
    "aigc_fit": "AIGC 适配判断",
}


def clamp_score(value: int | float) -> int:
    return max(0, min(100, int(round(value))))


def level_for(score: int) -> str:
    if score >= 75:
        return "strong"
    if score >= 55:
        return "medium"
    if score >= 35:
        return "weak"
    return "unknown"


def base_dimension(score: int, reasons: list[str], missing: list[str], action: str) -> dict[str, Any]:
    score = clamp_score(score)
    return {
        "score": score,
        "level": level_for(score),
        "reason": reasons[0] if reasons else "Insufficient local evidence for a stronger rule-based conclusion.",
        "reasons": reasons,
        "missing_evidence": missing,
        "suggested_action": action,
    }


def category_text(product: dict[str, Any], fact_sheet: dict[str, Any]) -> str:
    category = fact_sheet.get("category", {})
    if isinstance(category, dict):
        parts = [category.get("l1", ""), category.get("l2", ""), category.get("l3", "")]
    else:
        parts = [category]
    parts.extend([product.get("category", ""), product.get("product_name", ""), fact_sheet.get("product_name", "")])
    return " ".join(str(part) for part in parts if part).lower()


def performance_values(product: dict[str, Any], fact_sheet: dict[str, Any]) -> dict[str, Any]:
    performance = fact_sheet.get("performance", {}) if isinstance(fact_sheet.get("performance", {}), dict) else {}
    return {
        "sales": parse_number(performance.get("sales", product.get("sold_count", product.get("sales", 0)))),
        "gmv": parse_number(performance.get("gmv", product.get("gmv", 0))),
        "growth_7d": parse_percent(performance.get("growth_7d", product.get("growth_7d", 0))),
        "growth_30d": parse_percent(performance.get("growth_30d", product.get("growth_30d", 0))),
        "related_video_count": parse_number(performance.get("related_video_count", product.get("related_video_count", 0))),
        "related_influencer_count": parse_number(
            performance.get("related_influencer_count", product.get("related_influencer_count", 0))
        ),
        "rating": parse_number(performance.get("rating", product.get("rating", 0))),
        "review_count": parse_number(performance.get("review_count", product.get("review_count", 0))),
        "commission_rate": parse_percent(fact_sheet.get("commission_rate", product.get("commission_rate", 0))),
        "price": parse_number(fact_sheet.get("price", product.get("price", 0))),
        "shop_rating": parse_number(product.get("shop_rating", product.get("seller_rating", 0))),
    }


def hook_types(fact_sheet: dict[str, Any]) -> list[str]:
    hooks = fact_sheet.get("hook_recommendations", []) if isinstance(fact_sheet.get("hook_recommendations", []), list) else []
    values: list[str] = []
    for hook in hooks:
        if isinstance(hook, dict):
            value = hook.get("hook_type") or hook.get("hook_id")
            if value:
                values.append(str(value))
        elif hook:
            values.append(str(hook))
    return values


def has_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def profit_window(product: dict[str, Any], fact_sheet: dict[str, Any], perf: dict[str, Any]) -> dict[str, Any]:
    score = 40
    reasons: list[str] = []
    missing: list[str] = []
    if perf["growth_7d"] > 0.2:
        score += 18
        reasons.append("7-day growth indicates the product is still moving.")
    elif perf["growth_7d"] == 0:
        missing.append("growth_7d")
    if perf["growth_30d"] > 0.3:
        score += 14
        reasons.append("30-day growth supports an active profit window.")
    elif perf["growth_30d"] == 0:
        missing.append("growth_30d")
    if perf["commission_rate"] >= 0.1:
        score += 16
        reasons.append("Commission is attractive for content investment.")
    elif perf["commission_rate"] == 0:
        missing.append("commission_rate")
    elif perf["commission_rate"] < 0.08:
        score -= 10
        reasons.append("Commission is below the preferred threshold.")
    if perf["related_video_count"] > 120:
        score -= 10
        reasons.append("Related videos are high; same-product materials may be crowded.")
    elif perf["related_video_count"] >= 10:
        score += 8
        reasons.append("There is enough related video proof without relying on zero-signal testing.")
    else:
        missing.append("strong related_video_count signal")
    if perf["price"] > 80:
        score -= 12
        reasons.append("High price raises conversion friction for a quick push.")
    return base_dimension(score, reasons, missing, "Push now if content angle is differentiated; otherwise run small controlled test.")


def demand_pain(product: dict[str, Any], fact_sheet: dict[str, Any], perf: dict[str, Any], text: str) -> dict[str, Any]:
    score = 35
    reasons: list[str] = []
    missing: list[str] = ["review text themes", "negative review clusters"]
    if perf["sales"] >= 1000:
        score += 15
        reasons.append("Sales indicate real purchase motivation.")
    if perf["rating"] >= 4.5 and perf["review_count"] >= 100:
        score += 12
        reasons.append("Rating and review count provide buyer validation.")
        if "review text themes" in missing:
            missing.remove("review text themes")
    if has_any(text, ["pet", "cat", "bowl", "litter"]):
        score += 22
        reasons.append("Pet routines create visible daily-use pain points.")
    elif has_any(text, ["fan", "cooling", "summer", "hot"]):
        score += 22
        reasons.append("Heat discomfort is a clear seasonal pain point.")
    elif has_any(text, ["storage", "organis", "kitchen", "home"]):
        score += 14
        reasons.append("Home organisation products can show before/after pain clearly.")
    elif has_any(text, ["beauty", "serum", "skincare"]):
        score += 10
        reasons.append("Beauty products have routine-based content angles but claims need restraint.")
    elif has_any(text, ["treadmill", "fitness"]):
        score -= 8
        reasons.append("Fitness equipment has high purchase friction and needs stronger proof.")
    return base_dimension(score, reasons, missing, "Extract review language before scaling; turn repeated pain into hooks.")


def external_trend(product: dict[str, Any], fact_sheet: dict[str, Any], perf: dict[str, Any], text: str) -> dict[str, Any]:
    score = 35
    reasons: list[str] = []
    missing = ["Google Trends signal", "TikTok hashtag volume", "Instagram/Reels context", "YouTube Shorts context"]
    if has_any(text, ["fan", "cooling", "summer", "hot"]):
        score += 22
        reasons.append("Cooling products have obvious summer search and social context.")
    elif has_any(text, ["pet", "cat", "litter"]):
        score += 16
        reasons.append("Pet care has evergreen social content context.")
    elif has_any(text, ["beauty", "fashion", "snack"]):
        score += 12
        reasons.append("Category has social content context, but external trend data is still needed.")
    if perf["related_video_count"] >= 20:
        score += 10
        reasons.append("Related video count suggests existing TikTok context.")
    return base_dimension(score, reasons, missing, "Validate with Trends and hashtag search before assigning heavy volume.")


def seasonality(product: dict[str, Any], fact_sheet: dict[str, Any], market: str, text: str) -> dict[str, Any]:
    month = datetime.now().month
    score = 45
    reasons: list[str] = [f"Current month is {month}; market={market or fact_sheet.get('market', '')}."]
    missing: list[str] = []
    if has_any(text, ["fan", "cooling", "summer", "hot"]):
        if month in {5, 6, 7, 8}:
            score += 32
            reasons.append("Cooling product is in or near summer demand season.")
        else:
            score += 8
            reasons.append("Cooling product is seasonal but not in peak month.")
    elif has_any(text, ["pet", "cat", "litter"]):
        score += 20
        reasons.append("Pet products are evergreen; shedding and home-care angles can be seasonal.")
        missing.append("market-specific pet season signal")
    elif has_any(text, ["storage", "organis", "home", "kitchen"]):
        score += 14
        reasons.append("Home organisation is evergreen with cleaning/reset moments.")
    elif has_any(text, ["snack", "food"]):
        score += 8
        reasons.append("Snacks are evergreen but need local occasion proof.")
        missing.append("holiday or local occasion signal")
    elif has_any(text, ["treadmill", "fitness"]):
        if month in {1, 2, 11, 12}:
            score += 12
        else:
            score -= 8
            reasons.append("Walking treadmill is not in a clear seasonal push window right now.")
    return base_dimension(score, reasons, missing, "Use season-specific copy only when market timing supports it.")


def competition(product: dict[str, Any], fact_sheet: dict[str, Any], perf: dict[str, Any], text: str) -> dict[str, Any]:
    score = 55
    reasons: list[str] = []
    missing = ["same SKU count", "price range by competitor", "top creative monopoly check"]
    if perf["related_video_count"] > 150:
        score -= 18
        reasons.append("High related video count suggests stronger competition or material fatigue.")
    elif perf["related_video_count"] >= 20:
        score += 8
        reasons.append("Competition exists, but there may still be usable proof and angle space.")
    if perf["related_influencer_count"] > 40:
        score -= 10
        reasons.append("Many creators are already active around this product.")
    elif perf["related_influencer_count"] >= 10:
        score += 6
        reasons.append("Creator activity is healthy without clearly proving saturation.")
    if perf["price"] > 80:
        score -= 12
        reasons.append("Higher price makes price-war comparison and conversion harder.")
    if has_any(text, ["pet", "storage", "fan", "kitchen"]):
        score += 6
        reasons.append("Category still allows differentiated demo or scene framing.")
    return base_dimension(score, reasons, missing, "Use a differentiated hook before scaling into crowded categories.")


def merchant_quality(product: dict[str, Any], fact_sheet: dict[str, Any], perf: dict[str, Any]) -> dict[str, Any]:
    score = 45
    reasons: list[str] = []
    missing: list[str] = []
    seller = fact_sheet.get("seller_info", {}) if isinstance(fact_sheet.get("seller_info", {}), dict) else {}
    if seller.get("seller_name") or product.get("merchant_name") or product.get("seller_name"):
        score += 5
        reasons.append("Seller identity is present.")
    else:
        missing.append("merchant_name")
    if perf["rating"] >= 4.5:
        score += 18
        reasons.append("Product rating is strong.")
    elif perf["rating"] == 0:
        missing.append("rating")
    elif perf["rating"] < 4.2:
        score -= 12
        reasons.append("Product rating is below preferred threshold.")
    if perf["review_count"] >= 100:
        score += 12
        reasons.append("Review count gives basic trust evidence.")
    elif perf["review_count"] == 0:
        missing.append("review_count")
    if perf["shop_rating"] >= 4.5:
        score += 8
        reasons.append("Shop rating is strong.")
    elif perf["shop_rating"] == 0:
        missing.append("shop_rating")
    return base_dimension(score, reasons, missing, "Proceed when rating and fulfillment evidence are acceptable.")


def aigc_fit(product: dict[str, Any], fact_sheet: dict[str, Any], opportunity: dict[str, Any], text: str) -> dict[str, Any]:
    hooks = hook_types(fact_sheet)
    score = 40
    reasons: list[str] = []
    missing: list[str] = []
    if len(hooks) >= 3:
        score += 18
        reasons.append("At least three hook routes are available.")
    else:
        missing.append("3+ recommended hooks")
    if has_any(text, ["pet", "cat", "bowl", "litter", "storage", "organis", "fan", "kitchen"]):
        score += 22
        reasons.append("Product can be shown in concrete daily-use scenes.")
    elif has_any(text, ["beauty", "fashion", "snack"]):
        score += 12
        reasons.append("Product supports lifestyle content but needs stricter claim control.")
    if fact_sheet.get("risk_level") == "low":
        score += 10
        reasons.append("Low rule risk is suitable for AIGC image/video tests.")
    else:
        score -= 8
        reasons.append("Medium or high risk requires human claim review.")
    formats = opportunity.get("suggested_content_formats", {})
    if isinstance(formats, dict) and formats.get("video"):
        score += 6
        reasons.append("Opportunity layer recommends video as an available format.")
    return base_dimension(score, reasons, missing, "Generate photo first unless demo motion is central; keep Product Fact Sheet constraints.")


def final_test_decision(
    dimensions: dict[str, dict[str, Any]],
    opportunity: dict[str, Any],
    text: str,
) -> dict[str, Any]:
    weighted_keys = ["profit_window", "demand_pain", "seasonality", "competition", "merchant_quality", "aigc_fit"]
    avg = sum(dimensions[key]["score"] for key in weighted_keys) / len(weighted_keys)
    score = clamp_score((avg * 0.65) + (parse_number(opportunity.get("opportunity_score", 0)) * 0.35))
    reasons = [f"{key}: {dimensions[key]['level']} ({dimensions[key]['score']})" for key in weighted_keys]
    if score >= 75:
        decision = "main_push"
    elif score >= 55:
        decision = "small_test"
    elif score >= 40:
        decision = "hold"
    else:
        decision = "reject"
    if has_any(text, ["treadmill", "fitness"]) and score < 70:
        decision = "hold" if score >= 40 else "reject"
        reasons.append("High-ticket fitness item requires stronger merchant and conversion proof.")
    formats = ["photo"]
    if dimensions["aigc_fit"]["score"] >= 75 or has_any(text, ["fan", "gadget", "tool"]):
        formats.append("video")
    suggested_daily_posts = {"main_push": 3, "small_test": 2, "hold": 1, "reject": 0}[decision]
    missing_evidence = sorted(
        {
            evidence
            for key in weighted_keys
            for evidence in dimensions[key].get("missing_evidence", [])
            if evidence
        }
    )
    return {
        "decision": decision,
        "score": score,
        "level": level_for(score),
        "reason": reasons[0] if reasons else "Insufficient local evidence for a stronger rule-based conclusion.",
        "reasons": reasons,
        "missing_evidence": missing_evidence,
        "next_action": {
            "main_push": "今天可主推，进入账号分发表",
            "small_test": "小样本测试，先发1-2条验证CTR/转化",
            "hold": "暂缓，不进今日主推池，补齐证据后再测",
            "reject": "不建议当前阶段做",
        }[decision],
        "suggested_daily_posts": suggested_daily_posts,
        "suggested_accounts": account_suggestion(text),
        "suggested_formats": formats,
        "review_after_48h_metrics": ["CTR", "CVR", "add-to-cart rate", "comment objections", "refund or quality complaints"],
    }


def account_suggestion(text: str) -> list[str]:
    if has_any(text, ["electronics", "gadget", "tool", "fan"]):
        return ["male_functional", "home/lifestyle"]
    if has_any(text, ["pet", "cat", "home", "storage", "kitchen"]):
        return ["pet/home/lifestyle", "mature_female_home"]
    if has_any(text, ["beauty", "fashion"]):
        return ["young_female_lifestyle"]
    if has_any(text, ["snack", "food"]):
        return ["young_low_price"]
    return ["general"]


def build_dimension_scores(
    product: dict[str, Any],
    fact_sheet: dict[str, Any],
    opportunity: dict[str, Any],
    market: str = "de",
) -> dict[str, Any]:
    text = category_text(product, fact_sheet)
    perf = performance_values(product, fact_sheet)
    dimensions = {
        "profit_window": profit_window(product, fact_sheet, perf),
        "demand_pain": demand_pain(product, fact_sheet, perf, text),
        "external_trend": external_trend(product, fact_sheet, perf, text),
        "seasonality": seasonality(product, fact_sheet, market, text),
        "competition": competition(product, fact_sheet, perf, text),
        "merchant_quality": merchant_quality(product, fact_sheet, perf),
        "aigc_fit": aigc_fit(product, fact_sheet, opportunity, text),
    }
    dimensions["final_test_decision"] = final_test_decision(dimensions, opportunity, text)
    return dimensions
