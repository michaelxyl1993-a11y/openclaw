"""Build machine-readable Product Intel payloads for managers and bots."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .decision_table import build_decision_rows, category_text, hook_types, suggested_format
from .llm_summary import attach_summary_to_payload


VERSION = "product_intel_v0.6"


def split_formats(value: Any, fallback: str) -> list[str]:
    raw = value if value not in ("", None) else fallback
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, dict):
        values = [key for key in ["photo", "video"] if raw.get(key)]
    else:
        values = str(raw).replace("/", ",").split(",")

    formats: list[str] = []
    for item in values:
        normalized = str(item).strip().lower()
        if normalized == "both":
            for fmt in ["photo", "video"]:
                if fmt not in formats:
                    formats.append(fmt)
            continue
        if normalized in {"photo", "video"} and normalized not in formats:
            formats.append(normalized)
    return formats or ["photo"]


def decision_label(decision: str) -> str:
    return {
        "main_push": "今天可主推",
        "small_test": "小样本测试",
        "hold": "暂缓观察",
        "observe": "暂缓观察",
        "reject": "不建议当前阶段做",
    }.get(decision, "暂缓观察")


def manager_instruction(decision: str) -> str:
    return {
        "main_push": "进入今日主推池，优先生成图文素材",
        "small_test": "进入小样本测试池，先生成1-2条素材验证CTR/转化",
        "hold": "暂缓进入今日生产，可继续观察数据",
        "observe": "暂缓进入今日生产，可继续观察数据",
        "reject": "不进入当前生产池",
    }.get(decision, "暂缓进入今日生产，可继续观察数据")


def daily_posts(value: Any) -> int:
    mapping = {"high": 3, "medium": 2, "low": 1}
    if isinstance(value, int):
        return value
    return mapping.get(str(value).strip().lower(), 1)


def account_type_for_category(category: str) -> str:
    text = category.lower()
    if "pet" in text or "cat" in text or "dog" in text:
        return "pet/home/lifestyle"
    if "kitchen" in text or "home" in text:
        return "mature_female_home"
    if any(term in text for term in ["electronics", "gadget", "tool"]):
        return "male_functional"
    if "beauty" in text or "fashion" in text:
        return "young_female_lifestyle"
    if "snack" in text or "food" in text:
        return "young_low_price"
    return "general"


def build_routing(category: str, hooks: list[str], formats: list[str], meta: dict[str, Any]) -> dict[str, Any]:
    searchable = " ".join([category, " ".join(hooks)]).lower()
    photo = "photo" in formats
    video = "video" in formats
    if any(term in searchable for term in ["electronics", "tool", "gadget", "high_explanation", "complex_demo"]):
        photo = True
        video = True

    market = str(meta.get("market", "")).strip().lower()
    return {
        "photo": photo,
        "video": video,
        "de": market in {"", "de"},
        "fr": market in {"", "fr"},
        "account_type": account_type_for_category(category),
    }


def normalize_decision(decision: str) -> str:
    if decision == "observe":
        return "hold"
    return decision


def build_product_payload(item: dict[str, Any], row: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    product = item.get("product", {}) if isinstance(item.get("product", {}), dict) else {}
    fact_sheet = item.get("fact_sheet", {}) if isinstance(item.get("fact_sheet", {}), dict) else {}
    opportunity = item.get("opportunity", {}) if isinstance(item.get("opportunity", {}), dict) else {}
    dimension_scores = item.get("dimension_scores", {}) if isinstance(item.get("dimension_scores", {}), dict) else {}
    category = category_text(fact_sheet, product)
    hooks = hook_types(fact_sheet)
    decision = normalize_decision(str(row.get("decision", "hold")))
    formats = split_formats(opportunity.get("suggested_format"), suggested_format(opportunity, fact_sheet, product))
    return {
        "rank": row["rank"],
        "product_id": row["product_id"],
        "product_name": row["product_name"],
        "category": category,
        "source_platform": row["source_platform"],
        "price": row["price"],
        "commission_rate": row["commission_rate"],
        "sold_count": row["sold_count"],
        "gmv": row["gmv"],
        "opportunity_score": row["opportunity_score"],
        "decision": decision,
        "decision_label": decision_label(decision),
        "recommended_formats": formats,
        "recommended_hooks": hooks,
        "content_angle_summary": row["content_angle_summary"],
        "suggested_daily_posts": daily_posts(row["suggested_daily_posts"]),
        "risk_flags": row.get("risk_flags_list", opportunity.get("risk_flags", [])),
        "reasons": opportunity.get("reasons", []),
        "dimension_scores": dimension_scores,
        "dimension_summary": row.get("dimension_summary", ""),
        "strongest_dimensions": row.get("strongest_dimensions", ""),
        "weakest_dimensions": row.get("weakest_dimensions", ""),
        "missing_evidence_count": row.get("missing_evidence_count", 0),
        "main_push_reason": row.get("main_push_reason", ""),
        "next_action": row["next_action"],
        "manager_instruction": manager_instruction(decision),
        "routing": build_routing(category, hooks, formats, meta),
    }


def summary_product(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": product["rank"],
        "product_id": product["product_id"],
        "product_name": product["product_name"],
        "opportunity_score": product["opportunity_score"],
        "decision": product["decision"],
    }


def build_dimension_distribution(products: list[dict[str, Any]]) -> dict[str, Any]:
    distribution: dict[str, dict[str, int]] = {}
    for product in products:
        dimensions = product.get("dimension_scores", {})
        if not isinstance(dimensions, dict):
            continue
        for key, value in dimensions.items():
            if key == "final_test_decision" or not isinstance(value, dict):
                continue
            bucket = distribution.setdefault(key, {"strong": 0, "medium": 0, "weak": 0, "unknown": 0})
            level = str(value.get("level", "unknown"))
            bucket[level if level in bucket else "unknown"] += 1
    return distribution


def build_main_push_reasons_summary(products: list[dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    seen = set()
    for product in products:
        if product.get("decision") != "main_push":
            continue
        for reason in product.get("reasons", []) if isinstance(product.get("reasons", []), list) else []:
            text = str(reason)
            if text and text not in seen:
                seen.add(text)
                reasons.append(text)
            if len(reasons) >= 8:
                return reasons
    return reasons


def build_common_missing_evidence(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for product in products:
        dimensions = product.get("dimension_scores", {})
        if not isinstance(dimensions, dict):
            continue
        for key, value in dimensions.items():
            if key == "final_test_decision" or not isinstance(value, dict):
                continue
            missing = value.get("missing_evidence", [])
            if not isinstance(missing, list):
                continue
            for item in missing:
                label = f"{key}: {item}"
                counts[label] = counts.get(label, 0) + 1
    return [
        {"evidence": label, "count": count}
        for label, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:10]
    ]


def build_manager_payload(results: list[dict[str, Any]], meta: dict[str, Any] | None = None) -> dict[str, Any]:
    payload_meta = dict(meta or {})
    rows = build_decision_rows(results)
    sorted_results = sorted(
        results,
        key=lambda item: int(item.get("opportunity", {}).get("opportunity_score", 0) or 0),
        reverse=True,
    )
    products = [
        build_product_payload(item, row, payload_meta)
        for item, row in zip(sorted_results, rows)
    ]

    counts = {
        "main_push_count": sum(1 for product in products if product["decision"] == "main_push"),
        "small_test_count": sum(1 for product in products if product["decision"] == "small_test"),
        "hold_count": sum(1 for product in products if product["decision"] == "hold"),
        "reject_count": sum(1 for product in products if product["decision"] == "reject"),
    }
    final_meta = {
        "source": payload_meta.get("source", "product_intel"),
        "market": payload_meta.get("market", ""),
        "generated_at": payload_meta.get("generated_at", datetime.now(timezone.utc).isoformat()),
        "total_products": len(products),
        **counts,
    }
    payload = {
        "version": VERSION,
        "meta": final_meta,
        "summary": {
            "top_products": [summary_product(product) for product in products[:5]],
            "main_push_products": [summary_product(product) for product in products if product["decision"] == "main_push"],
            "small_test_products": [summary_product(product) for product in products if product["decision"] == "small_test"],
            "risk_heavy_products": [summary_product(product) for product in products if product["risk_flags"]],
            "dimension_distribution": build_dimension_distribution(products),
            "main_push_reasons_summary": build_main_push_reasons_summary(products),
            "common_missing_evidence": build_common_missing_evidence(products),
        },
        "products": products,
    }
    return attach_summary_to_payload(payload, market=str(final_meta.get("market") or "de"), use_llm=False)
