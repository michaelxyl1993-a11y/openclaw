"""Candidate sheet profiling and field mapping diagnosis."""

from __future__ import annotations

from typing import Any

from .field_aliases import (
    FIELD_ALIASES,
    OPTIONAL_FIELDS,
    REQUIRED_FIELDS,
    base_column_name,
    detect_source_from_features,
    duplicate_columns,
    normalize_header,
    source_from_value,
)


VALID_SOURCES = {"auto", "mock", "echotik", "fastmoss", "kalodata", "manual", "manual_or_unknown"}

WARNING_MESSAGES = {
    "product_url": "缺少 product_url：不影响初筛，但后续无法直接跳转商品链接",
    "shop_name": "缺少 shop_name：无法判断商家维度，merchant_quality 会降权",
    "commission_rate": "缺少 commission_rate：利润窗口判断可信度下降",
    "rating_review_count": "缺少 rating/review_count：商家质量和用户反馈证据不足",
    "trend_content_heat": "缺少 growth_30d / related_video_count / related_influencer_count：趋势/内容热度证据不足",
}

CORE_MAPPING_FIELDS = ["product_id", "product_name", "category", "price", "sold_count", "gmv", "commission_rate"]
INFERABLE_SOURCES = {"echotik", "fastmoss", "kalodata", "manual"}


def non_empty_count(rows: list[dict[str, Any]], column: str) -> int:
    return sum(1 for row in rows if str(row.get(column, "")).strip())


def find_mapped_column(columns: list[str], aliases: list[str], rows: list[dict[str, Any]] | None = None) -> str:
    candidates: list[str] = []
    for alias in aliases:
        for column in columns:
            if alias == column or normalize_header(alias) == normalize_header(base_column_name(column)):
                if column not in candidates:
                    candidates.append(column)
    if not candidates:
        return ""
    if rows:
        return max(candidates, key=lambda column: non_empty_count(rows, column))
    return candidates[0]


def detect_source(columns: list[str], rows: list[dict[str, Any]], mapped_fields: dict[str, str], requested_source: str) -> str:
    requested = requested_source.strip().lower()
    if requested != "auto":
        return requested if requested in VALID_SOURCES else "manual_or_unknown"
    source_column = mapped_fields.get("source_platform", "")
    if source_column:
        for row in rows:
            detected = source_from_value(row.get(source_column, ""))
            if detected:
                return detected
    return detect_source_from_features(columns)


def source_platform_diagnosis(rows: list[dict[str, Any]], mapped_fields: dict[str, str], source_detected: str) -> tuple[str, str]:
    source_column = mapped_fields.get("source_platform", "")
    if source_column:
        for row in rows:
            value = source_from_value(row.get(source_column, ""))
            if value:
                return value, "explicit"
    if source_detected in INFERABLE_SOURCES:
        return source_detected, "inferred"
    return "", "missing"


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


def build_warnings(rows: list[dict[str, Any]], missing_required: list[str], missing_optional: list[str], duplicates: list[str]) -> list[str]:
    warnings: list[str] = []
    if not rows:
        warnings.append("文件中没有可读取的数据行")
    warnings.extend(f"缺少必填字段 {field}：请补充该字段后再进行完整判断" for field in missing_required)
    for field in missing_optional:
        if field in WARNING_MESSAGES:
            warnings.append(WARNING_MESSAGES[field])
    if "rating" in missing_optional or "review_count" in missing_optional:
        warnings.append(WARNING_MESSAGES["rating_review_count"])
    if any(field in missing_optional for field in ["growth_30d", "related_video_count", "related_influencer_count"]):
        warnings.append(WARNING_MESSAGES["trend_content_heat"])
    if duplicates:
        warnings.append("存在重复列名：" + ", ".join(duplicates) + "；已优先选择非空数据更多的列")
    return warnings


def calculate_quality_score(mapped_fields: dict[str, str], duplicates: list[str]) -> int:
    required_score = sum(bool(mapped_fields.get(field)) for field in REQUIRED_FIELDS) / len(REQUIRED_FIELDS) * 55
    optional_score = sum(bool(mapped_fields.get(field)) for field in OPTIONAL_FIELDS) / len(OPTIONAL_FIELDS) * 45
    return max(0, min(100, round(required_score + optional_score - min(len(duplicates) * 3, 12))))


def mapping_confidence(mapped_fields: dict[str, str]) -> str:
    missing_core = [field for field in CORE_MAPPING_FIELDS if not mapped_fields.get(field)]
    if not missing_core:
        return "high"
    if len(missing_core) <= 2:
        return "medium"
    return "low"


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
    source_detected = detect_source(input_columns, rows, mapped_fields, source)
    source_platform_value, source_platform_source = source_platform_diagnosis(rows, mapped_fields, source_detected)
    missing_required = [field for field in REQUIRED_FIELDS if not mapped_fields.get(field)]
    missing_optional = [
        field for field in OPTIONAL_FIELDS
        if not mapped_fields.get(field) and not (field == "source_platform" and source_platform_source == "inferred")
    ]
    duplicates = duplicate_columns(input_columns)
    mapped_columns = {column for column in mapped_fields.values() if column}
    unmapped = [column for column in input_columns if column not in mapped_columns]
    score = calculate_quality_score(mapped_fields, duplicates)
    return {
        "detected_file_type": detected_file_type,
        "detected_sheet_name": detected_sheet_name,
        "source_detected": source_detected,
        "source_platform_value": source_platform_value,
        "source_platform_source": source_platform_source,
        "row_count": len(rows),
        "mapped_fields": mapped_fields,
        "missing_required_fields": missing_required,
        "missing_optional_fields": missing_optional,
        "unmapped_columns": unmapped,
        "duplicate_columns": duplicates,
        "warnings": build_warnings(rows, missing_required, missing_optional, duplicates),
        "field_quality_score": score,
        "mapping_confidence": mapping_confidence(mapped_fields),
        "input_columns": input_columns,
        "missing_fields": missing_required + missing_optional,
        "sample_values": sample_values(rows, mapped_fields),
    }
