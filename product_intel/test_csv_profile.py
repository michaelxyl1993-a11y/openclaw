"""Smoke tests for CSV profile diagnosis."""

from __future__ import annotations

import json
from pathlib import Path

from .csv_loader import load_raw_csv_rows
from .csv_profile import profile_csv_rows
from .export_csv_profile import save_csv_profile_json, save_csv_profile_markdown


PACKAGE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PACKAGE_DIR / "output"


def main() -> None:
    mock_rows = load_raw_csv_rows(PACKAGE_DIR / "mock_products.csv")
    mock_profile = profile_csv_rows(mock_rows, source="auto")
    if mock_profile["source_detected"] not in {"mock", "echotik", "fastmoss", "manual"}:
        raise AssertionError(f"mock profile source not detected: {mock_profile}")
    if not mock_profile["mapped_fields"].get("product_name"):
        raise AssertionError("mock profile did not map product_name")

    cn_rows = [
        {"商品ID": "p1", "产品名称": "中文商品", "分类": "家居", "商品价格": "¥9.9", "近7天销量": "100"},
        {"商品ID": "p2", "产品名称": "第二个商品", "分类": "美妆", "商品价格": "¥19.9", "近7天销量": "50"},
    ]
    cn_profile = profile_csv_rows(cn_rows, source="auto")
    for field in ["product_name", "category", "price", "sold_count"]:
        if not cn_profile["mapped_fields"].get(field):
            raise AssertionError(f"Chinese profile did not map {field}: {cn_profile}")

    missing_name_profile = profile_csv_rows([{"商品ID": "p3", "类目": "家居"}], source="manual")
    if "product_name" not in missing_name_profile["missing_required_fields"]:
        raise AssertionError(f"missing product_name not reported: {missing_name_profile}")

    json_path = save_csv_profile_json(mock_profile, OUTPUT_DIR / "test_csv_profile.json")
    md_path = save_csv_profile_markdown(mock_profile, OUTPUT_DIR / "test_csv_profile.md")
    if not json_path.exists() or not md_path.exists():
        raise AssertionError("profile exports were not created")
    reloaded = json.loads(json_path.read_text(encoding="utf-8"))
    if not reloaded.get("source_detected"):
        raise AssertionError("reloaded profile missing source_detected")

    print("CSV profile smoke test passed.")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")


if __name__ == "__main__":
    main()
