"""Batch Product Fact Sheet generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .dimension_score import build_dimension_scores
from .opportunity_score import score_product_opportunity
from .product_fact_sheet import PACKAGE_DIR, build_product_fact_sheet


MOCK_PRODUCTS_PATH = PACKAGE_DIR / "mock_echotik_products.json"


def load_mock_products(path: Path | None = None) -> list[dict[str, Any]]:
    product_path = path or MOCK_PRODUCTS_PATH
    data = json.loads(product_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a list of products in {product_path}")
    return data


def build_batch_fact_sheets(products: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    for product in products:
        fact_sheet = build_product_fact_sheet(product)
        opportunity = score_product_opportunity(fact_sheet)
        market = str(product.get("market") or fact_sheet.get("market") or "de")
        dimension_scores = build_dimension_scores(product, fact_sheet, opportunity, market=market)
        items.append(
            {
                "product": product,
                "fact_sheet": fact_sheet,
                "opportunity": opportunity,
                "dimension_scores": dimension_scores,
            }
        )
    return {"items": items}


def build_mock_batch_fact_sheets(path: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    return build_batch_fact_sheets(load_mock_products(path))


def main() -> None:
    print(json.dumps(build_mock_batch_fact_sheets(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
