"""Regression tests for shared candidate-sheet field aliases."""

from __future__ import annotations

from .csv_profile import profile_csv_rows
from .field_aliases import FIELD_ALIASES


EXPECTED_FIELDS = {
    "product_id",
    "product_name",
    "category",
    "price",
    "sold_count",
    "gmv",
    "commission_rate",
    "product_url",
    "shop_name",
    "source_platform",
    "growth_7d",
    "growth_30d",
    "related_video_count",
    "related_influencer_count",
    "rating",
    "review_count",
}


def main() -> None:
    if set(FIELD_ALIASES) != EXPECTED_FIELDS:
        raise AssertionError(f"field alias coverage mismatch: {set(FIELD_ALIASES)}")
    rows = [{
        "商品ID": "cn-1",
        "产品名称": "中文商品",
        "叶子类目": "家居",
        "当前售价": 9.9,
        "30日销量": 100,
        "近7日GMV": 990,
        "commission %": "12%",
        "TikTok商品链接": "https://example.com/cn-1",
        "商家名称": "中文店铺",
        "商品评分": 4.8,
        "评论数": 88,
    }]
    mapped = profile_csv_rows(rows)["mapped_fields"]
    for field in ["product_name", "category", "price", "sold_count", "gmv", "commission_rate", "product_url", "shop_name", "rating", "review_count"]:
        if not mapped.get(field):
            raise AssertionError(f"alias mapping missing for {field}: {mapped}")
    print("Field alias tests passed.")


if __name__ == "__main__":
    main()
