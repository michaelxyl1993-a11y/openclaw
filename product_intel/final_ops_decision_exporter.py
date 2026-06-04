"""Export final operations decisions from merged real LLM Judge review CSV."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


OUTPUT_FIELDS = [
    "product_id",
    "product_name",
    "source_platform",
    "source_detected",
    "rule_decision",
    "opportunity_score",
    "next_action",
    "llm_review_result",
    "llm_confidence",
    "final_human_review_priority",
    "final_ops_action",
    "final_ops_priority",
    "final_ops_reason",
    "llm_challenge_reason",
    "llm_missing_evidence",
]


def load_review_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("merged real LLM review CSV contains no products.")
    required = {
        "product_id",
        "product_name",
        "source_platform",
        "source_detected",
        "rule_decision",
        "opportunity_score",
        "next_action",
        "llm_review_result",
        "llm_confidence",
        "final_human_review_priority",
        "llm_challenge_reason",
        "llm_missing_evidence",
    }
    missing = sorted(required - set(rows[0]))
    if missing:
        raise ValueError(f"merged real LLM review CSV missing columns: {', '.join(missing)}")
    return rows


def final_ops_decision(row: dict[str, str]) -> tuple[str, str, str]:
    review = row["llm_review_result"]
    rule_decision = row["rule_decision"]
    if review == "challenge":
        return (
            "human_review_first",
            "P0_review",
            "LLM Judge challenge，人工复核后再执行规则建议",
        )
    if review == "insufficient_evidence":
        return "evidence_required", "P2_evidence", "LLM Judge 判断证据不足，补证后再执行"
    if review == "not_reviewed":
        return "not_ready", "P3_not_reviewed", "尚未完成 LLM Judge 复核，不进入运营执行"
    if review != "agree":
        raise ValueError(f"{row['product_id']}: unsupported llm_review_result: {review}")
    mapping = {
        "main_push": ("main_push", "P0_main_push", "规则建议主推且 LLM Judge 同意"),
        "small_test": ("small_test", "P1_small_test", "规则建议小样本测试且 LLM Judge 同意"),
        "hold": ("hold_for_evidence", "P2_hold", "规则建议暂缓，保留观察并补充证据"),
        "reject": ("hold_for_evidence", "P2_hold", "规则建议拒绝，暂不进入运营执行"),
    }
    if rule_decision not in mapping:
        raise ValueError(f"{row['product_id']}: unsupported rule_decision: {rule_decision}")
    return mapping[rule_decision]


def build_final_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    final_rows: list[dict[str, str]] = []
    for row in rows:
        action, priority, reason = final_ops_decision(row)
        final_rows.append(
            {
                **{field: row.get(field, "") for field in OUTPUT_FIELDS},
                "final_ops_action": action,
                "final_ops_priority": priority,
                "final_ops_reason": reason,
            }
        )
    return final_rows


def product_ref(row: dict[str, str]) -> dict[str, str]:
    return {
        "product_id": row["product_id"],
        "product_name": row["product_name"],
        "rule_decision": row["rule_decision"],
        "final_ops_action": row["final_ops_action"],
        "final_ops_priority": row["final_ops_priority"],
        "reason": row["final_ops_reason"],
    }


def build_recommended_today_plan(rows: list[dict[str, str]]) -> dict[str, Any]:
    executable = [
        product_ref(row)
        for row in rows
        if row["final_ops_action"] in {"main_push", "small_test"}
    ]
    human_review = [
        product_ref(row) for row in rows if row["final_ops_action"] == "human_review_first"
    ]
    hold = [
        product_ref(row)
        for row in rows
        if row["final_ops_action"] in {"hold_for_evidence", "evidence_required", "not_ready"}
    ]
    challenge_notes = [
        {
            "product_id": row["product_id"],
            "product_name": row["product_name"],
            "note": (
                f"{row['product_id']}｜{row['product_name']}："
                "规则建议 "
                f"{row['rule_decision']}，但 LLM Judge challenge，需人工复核后再执行。"
            ),
        }
        for row in rows
        if row["llm_review_result"] == "challenge"
    ]
    return {
        "today_executable_products": executable,
        "human_review_first_products": human_review,
        "hold_for_evidence_products": hold,
        "challenge_notes": challenge_notes,
    }


def build_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    action_counts = Counter(row["final_ops_action"] for row in rows)
    priority_counts = Counter(row["final_ops_priority"] for row in rows)
    challenge_products = [
        {
            **product_ref(row),
            "llm_challenge_reason": row["llm_challenge_reason"],
        }
        for row in rows
        if row["llm_review_result"] == "challenge"
    ]
    return {
        "total_products": len(rows),
        "final_ops_action_counts": dict(sorted(action_counts.items())),
        "final_ops_priority_counts": dict(sorted(priority_counts.items())),
        "main_push_count": action_counts.get("main_push", 0),
        "small_test_count": action_counts.get("small_test", 0),
        "hold_count": action_counts.get("hold_for_evidence", 0),
        "human_review_first_count": action_counts.get("human_review_first", 0),
        "challenge_products": challenge_products,
        "recommended_today_plan": build_recommended_today_plan(rows),
    }


def _summary_product_ids(summary: dict[str, Any]) -> set[str]:
    product_ids: set[str] = set()
    plan = summary.get("recommended_today_plan", {})
    if isinstance(plan, dict):
        for field in (
            "today_executable_products",
            "human_review_first_products",
            "hold_for_evidence_products",
            "challenge_notes",
        ):
            values = plan.get(field, [])
            if isinstance(values, list):
                for item in values:
                    if isinstance(item, dict) and item.get("product_id"):
                        product_ids.add(str(item["product_id"]))
    challenges = summary.get("challenge_products", [])
    if isinstance(challenges, list):
        for item in challenges:
            if isinstance(item, dict) and item.get("product_id"):
                product_ids.add(str(item["product_id"]))
    return product_ids


def validate_summary_is_current(
    rows: list[dict[str, str]], summary: dict[str, Any]
) -> None:
    current_product_ids = {str(row["product_id"]) for row in rows}
    unknown = sorted(_summary_product_ids(summary) - current_product_ids)
    if unknown:
        raise ValueError(
            "final ops summary contains stale product ids: " + ", ".join(unknown)
        )
    summary_text = json.dumps(summary, ensure_ascii=False)
    stale_note_key = "manual" + "_3_note"
    if stale_note_key in summary_text:
        raise ValueError("final ops summary contains stale hardcoded challenge note.")


def table_markdown(rows: list[dict[str, str]]) -> str:
    lines = [
        "# Product Intel Final Ops Decision Table",
        "",
        "| 商品 ID | 商品名 | 来源 | 规则决策 | 分数 | LLM 复核 | 置信度 | 最终动作 | 优先级 | 原因 |",
        "| --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['product_id']} | {row['product_name']} | {row['source_platform']} | "
            f"{row['rule_decision']} | {row['opportunity_score']} | {row['llm_review_result']} | "
            f"{row['llm_confidence']} | {row['final_ops_action']} | {row['final_ops_priority']} | "
            f"{row['final_ops_reason']} |"
        )
    return "\n".join(lines) + "\n"


def summary_markdown(summary: dict[str, Any]) -> str:
    plan = summary["recommended_today_plan"]
    lines = [
        "# Product Intel Final Ops Action Summary",
        "",
        "## 核心统计",
        "",
        f"- 商品总数：{summary['total_products']}",
        f"- 最终动作分布：{json.dumps(summary['final_ops_action_counts'], ensure_ascii=False)}",
        f"- 优先级分布：{json.dumps(summary['final_ops_priority_counts'], ensure_ascii=False)}",
        "",
        "## 今日可执行",
        "",
    ]
    for product in plan["today_executable_products"]:
        lines.append(
            f"- {product['product_id']}｜{product['product_name']}："
            f"{product['final_ops_action']}（{product['final_ops_priority']}）"
        )
    if not plan["today_executable_products"]:
        lines.append("- 无")
    lines.extend(["", "## 先人工复核", ""])
    for product in plan["human_review_first_products"]:
        lines.append(
            f"- {product['product_id']}｜{product['product_name']}：{product['reason']}"
        )
    if not plan["human_review_first_products"]:
        lines.append("- 无")
    lines.extend(["", "## 暂缓补证", ""])
    for product in plan["hold_for_evidence_products"]:
        lines.append(
            f"- {product['product_id']}｜{product['product_name']}：{product['reason']}"
        )
    if not plan["hold_for_evidence_products"]:
        lines.append("- 无")
    lines.extend(["", "## 特殊说明", ""])
    challenge_notes = plan.get("challenge_notes", [])
    if challenge_notes:
        for item in challenge_notes:
            lines.append(f"- {item['note']}")
    else:
        lines.append("- 无")
    lines.append("")
    return "\n".join(lines)


def write_outputs(
    rows: list[dict[str, str]],
    output_dir: str | Path,
) -> tuple[dict[str, Path], dict[str, Any]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    summary = build_summary(rows)
    validate_summary_is_current(rows, summary)
    paths = {
        "final_table_csv": output / "final_ops_decision_table.csv",
        "final_table_md": output / "final_ops_decision_table.md",
        "action_summary_json": output / "final_ops_action_summary.json",
        "action_summary_md": output / "final_ops_action_summary.md",
    }
    with paths["final_table_csv"].open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    paths["final_table_md"].write_text(table_markdown(rows), encoding="utf-8")
    paths["action_summary_json"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["action_summary_md"].write_text(summary_markdown(summary), encoding="utf-8")
    return paths, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Merged real LLM review CSV path")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = build_final_rows(load_review_rows(args.input))
    paths, summary = write_outputs(rows, args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for label, path in paths.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()
