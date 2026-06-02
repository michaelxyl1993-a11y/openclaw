"""Export CSV profile diagnosis reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def save_csv_profile_json(profile: dict[str, Any], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def save_csv_profile_markdown(profile: dict[str, Any], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mapped = profile.get("mapped_fields", {})
    samples = profile.get("sample_values", {})
    lines = [
        "# Product Intel CSV Profile",
        "",
        "## Source Detection",
        "",
        f"- source_detected: {profile.get('source_detected', '')}",
        f"- source_platform_value: {profile.get('source_platform_value', '') or '(missing)'}",
        f"- source_platform_source: {profile.get('source_platform_source', 'missing')}",
        f"- detected_file_type: {profile.get('detected_file_type', '')}",
        f"- detected_sheet_name: {profile.get('detected_sheet_name', '') or '(none)'}",
        f"- row_count: {profile.get('row_count', 0)}",
        f"- field_quality_score: {profile.get('field_quality_score', 0)}",
        f"- mapping_confidence: {profile.get('mapping_confidence', '')}",
        "",
        "## Input Columns",
        "",
        ", ".join(profile.get("input_columns", [])) or "(none)",
        "",
        "## Field Mapping",
        "",
        "| internal field | input column |",
        "| --- | --- |",
    ]
    for field, column in mapped.items():
        if field == "source_platform" and not column and profile.get("source_platform_source") == "inferred":
            column = f"(inferred from source_detected: {profile.get('source_platform_value', '')})"
        lines.append(f"| {field} | {column or '(missing)'} |")
    lines.extend(["", "## Missing Fields", ""])
    lines.append("- missing_fields: " + (", ".join(profile.get("missing_fields", [])) or "(none)"))
    lines.append("- required: " + (", ".join(profile.get("missing_required_fields", [])) or "(none)"))
    lines.append("- optional: " + (", ".join(profile.get("missing_optional_fields", [])) or "(none)"))
    lines.append("- unmapped_columns: " + (", ".join(profile.get("unmapped_columns", [])) or "(none)"))
    lines.append("- duplicate_columns: " + (", ".join(profile.get("duplicate_columns", [])) or "(none)"))
    lines.extend(["", "## Sample Values", ""])
    for field, values in samples.items():
        lines.append(f"- {field}: {', '.join(values) if values else '(none)'}")
    lines.extend(["", "## Warnings", ""])
    warnings = profile.get("warnings", [])
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("(none)")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path
