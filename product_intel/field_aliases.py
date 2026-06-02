"""Shared field aliases and source detection rules for candidate product sheets."""

from __future__ import annotations

from collections import Counter
from typing import Any


FIELD_ALIASES = {
    "product_id": ["product_id", "item_id", "goods_id", "product id", "EchoTik商品ID", "FastMoss商品ID", "KaLoData Product ID", "商品ID", "商品id", "商品编号", "id"],
    "product_name": ["product_name", "title", "name", "商品名称", "商品名", "商品标题", "产品名称", "product_title"],
    "category": ["category", "leaf_category", "category_name", "商品类目", "类目", "叶子类目", "分类"],
    "price": ["price", "当前售价", "售价", "价格", "sale_price", "商品价格", "final_price", "min_price"],
    "sold_count": ["sales", "sold", "sold_count", "销量", "已售", "近7日销量", "近7天销量", "30日销量", "近30日销量"],
    "gmv": ["gmv", "GMV", "销售额", "成交额", "成交金额", "近7日GMV", "近7天GMV", "30日GMV", "近30日GMV", "sales_amount"],
    "commission_rate": ["commission", "commission_rate", "佣金", "佣金率", "commission %", "commission%", "达人佣金率"],
    "product_url": ["product_url", "url", "商品链接", "TikTok商品链接", "item_url", "链接"],
    "shop_name": ["shop_name", "seller_name", "merchant_name", "店铺名", "店铺", "店铺名称", "商家名称", "卖家名称"],
    "source_platform": ["source_platform", "candidate_source", "数据来源", "来源"],
    "growth_7d": ["growth_7d", "7d_growth", "growth7d", "近7天增长", "近7日增长", "7日增长"],
    "growth_30d": ["growth_30d", "30d_growth", "growth30d", "近30天增长", "近30日增长", "30日增长"],
    "related_video_count": ["related_video_count", "video_count", "关联视频数", "相关视频数", "带货视频数"],
    "related_influencer_count": ["related_influencer_count", "influencer_count", "达人数量", "关联达人数", "相关达人数", "带货达人数"],
    "rating": ["rating", "score", "商品评分", "评分"],
    "review_count": ["reviews", "review_count", "评论数", "评价数"],
}

REQUIRED_FIELDS = ["product_id", "product_name", "category"]
OPTIONAL_FIELDS = [
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
]

SOURCE_ALIASES = {
    "echotik": {"echotik", "echo tik"},
    "fastmoss": {"fastmoss", "fast moss"},
    "kalodata": {"kalodata", "kalo data"},
    "manual": {"manual", "手工", "手动"},
    "manual_or_unknown": {"unknown", "manual_or_unknown"},
}

# Use combinations instead of a single generic column so merged manual sheets are
# not misclassified merely because they contain common commerce metrics.
SOURCE_FEATURES = {
    "echotik": {"echotik商品id", "达人佣金率", "近7天销量", "近7天增长"},
    "fastmoss": {"fastmoss商品id", "tiktok商品链接", "近7日gmv", "关联视频数"},
    "kalodata": {"kalodata product id", "product_title", "30日gmv", "相关达人数"},
}

DUPLICATE_SUFFIX = "__duplicate_"


def normalize_header(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def base_column_name(column: str) -> str:
    return column.split(DUPLICATE_SUFFIX, 1)[0]


def duplicate_columns(columns: list[str]) -> list[str]:
    counts = Counter(base_column_name(column) for column in columns)
    return [column for column, count in counts.items() if count > 1]


def source_from_value(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    for source, aliases in SOURCE_ALIASES.items():
        if normalized in aliases:
            return source
    return normalized or ""


def detect_source_from_features(columns: list[str]) -> str:
    normalized_columns = {normalize_header(base_column_name(column)) for column in columns}
    scores = {
        source: sum(normalize_header(feature) in normalized_columns for feature in features)
        for source, features in SOURCE_FEATURES.items()
    }
    best_source = max(scores, key=scores.get)
    return best_source if scores[best_source] >= 2 else "manual_or_unknown"
