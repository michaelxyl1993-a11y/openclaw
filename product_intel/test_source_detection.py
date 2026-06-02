"""Regression tests for direct and feature-based source detection."""

from __future__ import annotations

from pathlib import Path

from .csv_profile import profile_csv_rows
from .input_adapter import load_raw_product_rows


PACKAGE_DIR = Path(__file__).resolve().parent


def assert_source(rows: list[dict], expected: str) -> None:
    actual = profile_csv_rows(rows, source="auto")["source_detected"]
    if actual != expected:
        raise AssertionError(f"expected source={expected}, got {actual}: {rows}")


def main() -> None:
    assert_source([{"candidate_source": "FastMoss", "title": "Direct Source"}], "fastmoss")
    assert_source([{"EchoTik商品ID": "e1", "商品名称": "Echo", "近7天销量": 10, "达人佣金率": "8%"}], "echotik")
    assert_source([{"FastMoss商品ID": "f1", "title": "Fast", "TikTok商品链接": "https://example.com", "近7日GMV": 10}], "fastmoss")
    assert_source([{"KaLoData Product ID": "k1", "product_title": "Kalo", "30日GMV": 10, "相关达人数": 3}], "kalodata")
    assert_source([{"商品编号": "m1", "商品名": "Manual", "销量": 10}], "manual_or_unknown")
    for filename, expected in {
        "mock_echotik_products.xlsx": "echotik",
        "mock_fastmoss_products.xlsx": "fastmoss",
        "mock_kalodata_products.xlsx": "kalodata",
        "mock_manual_products.xlsx": "manual",
    }.items():
        rows, metadata = load_raw_product_rows(PACKAGE_DIR / filename)
        actual = profile_csv_rows(rows, source="auto", **metadata)["source_detected"]
        if actual != expected:
            raise AssertionError(f"{filename}: expected source={expected}, got {actual}")
    print("Source detection tests passed.")


if __name__ == "__main__":
    main()
