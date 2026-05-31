"""Convert EchoTik product detail data into a Product Fact Sheet."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hook_library import select_hooks_by_types


PACKAGE_DIR = Path(__file__).resolve().parent
MOCK_PRODUCT_PATH = PACKAGE_DIR / "mock_echotik_product.json"


def load_mock_echotik_product(path: Path | None = None) -> dict[str, Any]:
    product_path = path or MOCK_PRODUCT_PATH
    return json.loads(product_path.read_text(encoding="utf-8"))


def compact_category(raw_product: dict[str, Any]) -> dict[str, str]:
    fallback_category = str(raw_product.get("category", "")).strip()
    return {
        "l1": str(raw_product.get("category_l1", "")).strip() or fallback_category,
        "l2": str(raw_product.get("category_l2", "")).strip(),
        "l3": str(raw_product.get("category_l3", "")).strip() or fallback_category,
    }


def infer_risk_level(raw_product: dict[str, Any]) -> str:
    category_text = " ".join(
        str(raw_product.get(key, ""))
        for key in ["category_l1", "category_l2", "category_l3", "category", "product_name"]
    ).lower()
    higher_risk_terms = ["supplement", "health", "medical", "baby", "children", "electronics"]
    if any(term in category_text for term in higher_risk_terms):
        return "medium"
    return "low"


def build_visual_identity(raw_product: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": "rule_placeholder",
        "primary_image_url": (raw_product.get("image_urls") or [""])[0],
        "observed_product_type": str(raw_product.get("product_name", "")).strip(),
        "color_material_shape_notes": "",
        "logo_or_packaging_notes": "",
        "future_ai_enrichment_required": True,
    }


def category_search_text(raw_product: dict[str, Any]) -> str:
    return " ".join(
        str(raw_product.get(key, ""))
        for key in ["category_l1", "category_l2", "category_l3", "category", "product_name"]
    ).lower()


def recommend_hook_types(raw_product: dict[str, Any]) -> list[str]:
    text = category_search_text(raw_product)
    if any(term in text for term in ["pet supplies", "cat bowl", "cat bowls", "feeder", "feeders", "cats"]):
        return ["pet_behavior", "problem_solution", "daily_usefulness"]
    if any(term in text for term in ["home appliances", "fan", "fans", "cooling"]):
        return ["pain_point_hot_weather", "no_installation", "small_space_solution"]
    if "electronics" in text:
        return ["is_it_worth_it", "not_an_iq_tax", "daily_usefulness"]
    if "fashion" in text:
        return ["before_after", "problem_solution", "gift_for_her"]
    if "beauty" in text:
        return ["before_after", "daily_usefulness", "gift_for_her"]
    if any(term in text for term in ["food", "snacks"]):
        return ["price_shock", "shelf_value_deal", "daily_usefulness"]
    return ["problem_solution", "daily_usefulness", "shelf_value_deal"]


def build_hook_recommendations(raw_product: dict[str, Any]) -> list[dict[str, Any]]:
    return select_hooks_by_types(recommend_hook_types(raw_product))[:5]


def build_product_fact_sheet(raw_product: dict[str, Any]) -> dict[str, Any]:
    risk_level = infer_risk_level(raw_product)
    return {
        "product_id": raw_product.get("product_id", ""),
        "source": raw_product.get("source_platform") or "echotik_mock_v0.1",
        "market": raw_product.get("market", ""),
        "product_name": raw_product.get("product_name", ""),
        "category": compact_category(raw_product),
        "price": raw_product.get("price", ""),
        "commission_rate": raw_product.get("commission_rate", ""),
        "product_url": raw_product.get("product_url", ""),
        "image_urls": raw_product.get("image_urls", []),
        "seller_info": {
            "seller_id": raw_product.get("seller_id", ""),
            "seller_name": raw_product.get("seller_name", ""),
        },
        "performance": {
            "sales": raw_product.get("sales", raw_product.get("sold_count", 0)),
            "gmv": raw_product.get("gmv", 0),
            "growth_7d": raw_product.get("growth_7d", 0),
            "growth_30d": raw_product.get("growth_30d", 0),
            "related_video_count": raw_product.get("related_video_count", 0),
            "related_influencer_count": raw_product.get("related_influencer_count", 0),
            "rating": raw_product.get("rating", 0),
            "review_count": raw_product.get("review_count", 0),
        },
        "visual_identity": build_visual_identity(raw_product),
        "must_keep": [],
        "must_not_add": [],
        "allowed_claims": [
            "Use only claims supported by the product title, category, images, or seller data."
        ],
        "forbidden_claims": [
            "Do not invent medical, health, safety, durability, certification, discount, or performance claims."
        ],
        "risk_level": risk_level,
        "human_review_required": risk_level in {"medium", "high"},
        "recommended_usage": {
            "manager_image_workflow": True,
            "video_director_workflow": True,
            "product_selection_bot": True,
            "qa_workflow": True,
        },
        "hook_recommendations": build_hook_recommendations(raw_product),
    }


def build_mock_fact_sheet() -> dict[str, Any]:
    return build_product_fact_sheet(load_mock_echotik_product())


def main() -> None:
    print(json.dumps(build_mock_fact_sheet(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
