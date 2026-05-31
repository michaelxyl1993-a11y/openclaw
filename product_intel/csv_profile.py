"""CSV schema profiling and field mapping diagnosis."""

from __future__ import annotations

from typing import Any


FIELD_ALIASES = {
    "product_id": ["product_id", "item_id", "goods_id", "商品ID", "商品id", "id"],
    "product_name": ["product_name", "title", "商品名称", "商品标题", "产品名称", "name"],
    "category": ["category", "类目", "分类", "category_name", "leaf_category", "商品类目"],
    "price": ["price", "商品价格", "售价", "final_price", "sale_price", "min_price", "价格"],
    "sold_count": ["sold_count", "sales", "sold", "销量", "已售", "近7天销量"],
    "gmv": ["gmv", "GMV", "销售额", "成交金额", "sales_amount"],
    "commission_rate": ["commission", "commission_rate", "佣金", "佣金率", "达人佣金率"],
    "product_url": ["product_url", "url", "商品链接", "链接"],
    "shop_name": ["shop_name", "seller_name", "店铺", "店铺名称", "卖家名称"],
    "source_platform": ["source_platform", "candidate_source", "来源", "数据来源"],
    "growth_7d": ["growth_7d", "7d_growth", "growth7d", "近7天增长", "7日增长"],
    "growth_30d": ["growth_30d", "30d_growth", "growth30d", "近30天增长", "30日增长"],
    "related_video_count": ["related_video_count", "video_count", "关联视频数", "相关视频数"],
    "related_influencer_count": ["related_influencer_count", "influencer_count", "达人数量", "关联达人数"],
    "rating": ["rating", "评分", "商品评分"],
    "review_count": ["review_count", "reviews", "评价数", "评论数"],
}

REQUIRED_FIELDS = ["product_id", "product_name", "category"]
OPTIONAL_FIELDS = ["price", "sold_count", "gmv", "commission_rate", "product_url", "shop_name", "growth_7d", "growth_30d", "related_video_count", "related_influencer_count", "rating", "review_count"]
VALID_SOURCES = {"auto", "mock", "echotik", "fastmoss", "manual"}


def normalize_header(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def non_empty_count(rows: list[dict[str, Any]], column: str) -> int:
    return sum(1 for row in rows if str(row.get(column, "")).strip())


def find_mapped_column(columns: list[str], aliases: list[str], rows: list[dict[str, Any]] | None = None) -> str:
    candidates: list[str] = []
    exact = {str(column): str(column) for column in columns}
    for alias in aliases:
        if alias in exact and exact[alias] not in candidates:
            candidates.append(exact[alias])

    normalized_columns = {normalize_header(column): str(column) for column in columns}
    for alias in aliases:
        match = normalized_columns.get(normalize_header(alias))
        if match and match not in candidates:
            candidates.append(match)
    if not candidates:
        return ""
    if rows:
        return max(candidates, key=lambda column: non_empty_count(rows, column))
    return candidates[0]


def detect_source(columns: list[str], requested_source: str) -> str:
    requested = requested_source.strip().lower()
    if requested != "auto":
        return requested if requested in VALID_SOURCES else "unknown"
    joined = " ".join(columns).lower()
    if "source_platform" in joined or "mock" in joined:
        return "mock"
    if "candidate_source" in joined or "fastmoss" in joined:
        return "fastmoss"
    if "商品id" in joined or "达人佣金" in joined or "echotik" in joined:
        return "echotik"
    if any(term in joined for term in ["商品名称", "类目", "来源"]):
        return "manual"
    return "unknown"


def sample_values(rows: list[dict[str, Any]], mapped_fields: dict[str, str]) -> dict[str, list[str]]:
    samples: dict[str, list[str]] = {}
    for field in ["product_name", "price", "sold_count"]:
        column = mapped_fields.get(field, "")
        values: list[str] = []
        if column:
            for row in rows:
                value = str(row.get(column, "")).strip()
                if value and value not in values:
                    values.append(value)
                if len(values) >= 3:
                    break
        samples[field] = values
    return samples


def profile_csv_rows(
    rows: list[dict[str, Any]],
    source: str = "auto",
    detected_file_type: str = "csv",
    detected_sheet_name: str = "",
) -> dict[str, Any]:
    if source.strip().lower() not in VALID_SOURCES:
        source = "auto"
    input_columns = list(rows[0].keys()) if rows else []
    mapped_fields = {
        field: find_mapped_column(input_columns, aliases, rows)
        for field, aliases in FIELD_ALIASES.items()
    }
    missing_required = [field for field in REQUIRED_FIELDS if not mapped_fields.get(field)]
    missing_optional = [field for field in OPTIONAL_FIELDS if not mapped_fields.get(field)]
    warnings: list[str] = []
    if not rows:
        warnings.append("CSV has no data rows.")
    for field in missing_required:
        warnings.append(f"Missing required field mapping: {field}")
    for field in missing_optional:
        warnings.append(f"Missing optional field mapping: {field}")

    return {
        "source_detected": detect_source(input_columns, source),
        "detected_file_type": detected_file_type,
        "detected_sheet_name": detected_sheet_name,
        "input_columns": input_columns,
        "mapped_fields": mapped_fields,
        "missing_required_fields": missing_required,
        "missing_optional_fields": missing_optional,
        "missing_fields": missing_required + missing_optional,
        "row_count": len(rows),
        "sample_values": sample_values(rows, mapped_fields),
        "warnings": warnings,
    }
