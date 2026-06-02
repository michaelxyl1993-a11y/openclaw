"""Export Product Intel decision tables."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


DECISION_CSV_FIELDS = [
    "rank",
    "product_id",
    "product_name",
    "category",
    "source_platform",
    "price",
    "commission_rate",
    "sold_count",
    "gmv",
    "opportunity_score",
    "decision",
    "suggested_format",
    "suggested_daily_posts",
    "recommended_hooks",
    "content_angle_summary",
    "reasons",
    "risk_flags",
    "ops_risk_note",
    "dimension_summary",
    "strongest_dimensions",
    "weakest_dimensions",
    "missing_evidence_count",
    "main_push_reason",
    "next_action",
]


def save_decision_csv(rows: list[dict[str, Any]], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=DECISION_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in DECISION_CSV_FIELDS})
    return output_path


def markdown_escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def save_decision_markdown(rows: list[dict[str, Any]], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "rank",
        "商品",
        "类目",
        "分数",
        "决策",
        "建议形式",
        "日投放",
        "hooks",
        "8维度摘要",
        "强维度",
        "弱维度",
        "主推/判断依据",
        "风险",
        "运营风险说明",
        "下一步动作",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        values = [
            row.get("rank", ""),
            row.get("product_name", ""),
            row.get("category", ""),
            row.get("opportunity_score", ""),
            row.get("decision", ""),
            row.get("suggested_format", ""),
            row.get("suggested_daily_posts", ""),
            row.get("recommended_hooks", ""),
            row.get("dimension_summary", ""),
            row.get("strongest_dimensions", ""),
            row.get("weakest_dimensions", ""),
            row.get("main_push_reason", ""),
            row.get("risk_flags", ""),
            row.get("ops_risk_note", ""),
            row.get("next_action", ""),
        ]
        lines.append("| " + " | ".join(markdown_escape(value) for value in values) + " |")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path
