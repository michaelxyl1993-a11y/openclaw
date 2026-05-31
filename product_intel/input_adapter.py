"""Input adapters for EchoTik / FastMoss / manual product candidate rows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .csv_profile import FIELD_ALIASES as PROFILE_FIELD_ALIASES, profile_csv_rows


FIELD_ALIASES = {
    "product_id": ["product_id", "item_id", "goods_id", "商品ID", "商品id"],
    "product_name": ["product_name", "title", "商品名称", "商品标题", "name"],
    "category": ["category", "leaf_category", "category_name", "类目", "商品类目"],
    "price": ["price", "sale_price", "min_price", "价格", "售价"],
    "commission_rate": ["commission_rate", "commission", "佣金率", "达人佣金率"],
    "sold_count": ["sold_count", "sales", "sold", "销量", "已售", "近7天销量"],
    "gmv": ["gmv", "GMV", "sales_amount", "销售额", "成交金额"],
    "source_platform": ["source_platform", "candidate_source", "来源", "数据来源"],
    "growth_7d": ["growth_7d", "7d_growth", "growth7d", "近7天增长", "7日增长"],
    "growth_30d": ["growth_30d", "30d_growth", "growth30d", "近30天增长", "30日增长"],
    "related_video_count": ["related_video_count", "video_count", "关联视频数", "相关视频数"],
    "related_influencer_count": ["related_influencer_count", "influencer_count", "达人数量", "关联达人数"],
    "rating": ["rating", "评分", "商品评分"],
    "review_count": ["review_count", "reviews", "评价数", "评论数"],
}


def first_present(row: dict[str, Any], aliases: list[str]) -> Any:
    for alias in aliases:
        if alias in row and row[alias] not in (None, ""):
            return row[alias]
    lower_map = {str(key).lower(): value for key, value in row.items()}
    for alias in aliases:
        value = lower_map.get(alias.lower())
        if value not in (None, ""):
            return value
    return ""


def value_from_mapping(row: dict[str, Any], field: str, mapped_fields: dict[str, str] | None = None) -> Any:
    if mapped_fields and mapped_fields.get(field):
        mapped_value = row.get(mapped_fields[field], "")
        if mapped_value not in ("", None):
            return mapped_value
    aliases = FIELD_ALIASES.get(field) or PROFILE_FIELD_ALIASES.get(field, [])
    return first_present(row, aliases)


def normalize_product_row(
    row: dict[str, Any],
    mapped_fields: dict[str, str] | None = None,
    raw_source: str = "unknown",
    raw_row_index: int | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    product_name = str(value_from_mapping(row, "product_name", mapped_fields)).strip()
    category = str(value_from_mapping(row, "category", mapped_fields)).strip()
    if not product_name:
        warnings.append("missing product_name; row marked invalid")
    if not category:
        warnings.append("missing category; using unknown")
        category = "unknown"
    for optional_field in ["price", "sold_count", "gmv"]:
        if value_from_mapping(row, optional_field, mapped_fields) in ("", None):
            warnings.append(f"missing optional field: {optional_field}")

    product = {
        "product_id": str(value_from_mapping(row, "product_id", mapped_fields)).strip(),
        "product_name": product_name,
        "category": category,
        "price": value_from_mapping(row, "price", mapped_fields),
        "commission_rate": value_from_mapping(row, "commission_rate", mapped_fields),
        "sold_count": value_from_mapping(row, "sold_count", mapped_fields),
        "gmv": value_from_mapping(row, "gmv", mapped_fields),
        "product_url": value_from_mapping(row, "product_url", mapped_fields),
        "shop_name": value_from_mapping(row, "shop_name", mapped_fields),
        "source_platform": str(value_from_mapping(row, "source_platform", mapped_fields)).strip(),
        "growth_7d": value_from_mapping(row, "growth_7d", mapped_fields),
        "growth_30d": value_from_mapping(row, "growth_30d", mapped_fields),
        "related_video_count": value_from_mapping(row, "related_video_count", mapped_fields),
        "related_influencer_count": value_from_mapping(row, "related_influencer_count", mapped_fields),
        "rating": value_from_mapping(row, "rating", mapped_fields),
        "review_count": value_from_mapping(row, "review_count", mapped_fields),
        "raw": dict(row),
        "raw_source": raw_source,
        "raw_row_index": raw_row_index,
        "normalize_warnings": warnings,
        "invalid": not bool(product_name),
    }

    if not product["product_id"]:
        fallback_name = product["product_name"] or "unknown_product"
        product["product_id"] = "manual_" + "_".join(fallback_name.lower().split())[:80]
    if not product["source_platform"]:
        product["source_platform"] = "unknown"

    return product


def normalize_product_rows(rows: list[dict[str, Any]], source: str = "auto") -> list[dict[str, Any]]:
    profile = profile_csv_rows(rows, source=source)
    mapped_fields = profile.get("mapped_fields", {})
    raw_source = profile.get("source_detected", source)
    return [
        normalize_product_row(row, mapped_fields=mapped_fields, raw_source=raw_source, raw_row_index=index)
        for index, row in enumerate(rows, start=1)
    ]


SUPPORTED_INPUT_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def detect_file_type(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".xlsx":
        return "xlsx"
    if suffix == ".xls":
        return "xls"
    raise ValueError(f"unsupported input file format: {suffix or 'none'}. Supported formats: .csv, .xlsx, .xls")


def load_raw_product_rows(path: str | Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    file_type = detect_file_type(path)
    if file_type == "csv":
        from .csv_loader import load_raw_csv_rows

        return load_raw_csv_rows(path), {"detected_file_type": "csv", "detected_sheet_name": ""}
    from .excel_loader import load_raw_excel_rows

    rows, sheet_name = load_raw_excel_rows(path)
    return rows, {"detected_file_type": file_type, "detected_sheet_name": sheet_name}


def load_products_from_file(path: str | Path, source: str = "auto") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows, metadata = load_raw_product_rows(path)
    return normalize_product_rows(rows, source=source), metadata
