"""Merge rule results with optional LLM Judge reviews for operations."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from .llm_judge_contract import validate_llm_judge_output


REVIEW_RESULTS = {"agree", "challenge", "insufficient_evidence", "not_reviewed"}
CONFIDENCE_VALUES = {"high", "medium", "low", "missing"}
CSV_FIELDS = [
    "product_id",
    "product_name",
    "source_platform",
    "source_detected",
    "rule_decision",
    "opportunity_score",
    "next_action",
    "overall_evidence_coverage",
    "missing_evidence_total",
    "llm_review_result",
    "llm_confidence",
    "final_human_review_priority",
    "final_human_review_reason",
    "llm_challenge_reason",
    "llm_missing_evidence",
    "llm_real_called",
]


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def extract_items(payload: Any, label: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and isinstance(payload.get("products"), list):
        items = payload["products"]
    elif isinstance(payload, dict) and isinstance(payload.get("results"), list):
        items = payload["results"]
    else:
        raise ValueError(f"{label} must be a list or contain a products/results list.")
    if not all(isinstance(item, dict) for item in items):
        raise ValueError(f"{label} items must be objects.")
    return items


def index_judge_results(judge_results: Any) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in extract_items(judge_results, "judge results"):
        product_id = str(item.get("product_id", "")).strip()
        if not product_id:
            raise ValueError("judge result missing product_id.")
        if product_id in indexed:
            raise ValueError(f"duplicate judge result product_id: {product_id}")
        indexed[product_id] = item
    return indexed


def normalize_judge_result(item: dict[str, Any] | None) -> dict[str, Any]:
    if item is None:
        return {
            "llm_review_result": "not_reviewed",
            "llm_confidence": "missing",
            "llm_challenge_reason": "",
            "llm_missing_evidence": [],
            "llm_dimension_reviews": {},
            "llm_recommended_human_action": "尚未执行 LLM Judge 复核，建议按运营优先级安排人工检查。",
            "llm_real_called": False,
        }

    raw = item.get("mock_llm_judge_output", item)
    if not isinstance(raw, dict):
        raise ValueError("judge output must be an object.")

    if "llm_decision_review" in raw:
        validate_llm_judge_output(raw)
        review_result = raw["llm_decision_review"]
        confidence = raw["llm_confidence"]
        challenge_reason = raw["challenge_reason"]
        missing_evidence = raw["suggested_next_evidence"]
        dimension_reviews = raw["dimension_reviews"]
        human_action = raw["llm_ops_note"]
        real_called = bool(item.get("real_llm_called", False))
    elif "review_result" in raw:
        review_result = raw.get("review_result")
        confidence = raw.get("confidence")
        challenge_reason = raw.get("challenge_reason", "")
        missing_evidence = raw.get("missing_evidence", [])
        dimension_reviews = raw.get("dimension_reviews", {})
        human_action = raw.get("recommended_human_action", "")
        real_called = raw.get("real_llm_called", False)
    else:
        raise ValueError("unsupported judge result format.")

    if review_result not in REVIEW_RESULTS - {"not_reviewed"}:
        raise ValueError(f"invalid llm review result: {review_result}")
    if confidence not in CONFIDENCE_VALUES - {"missing"}:
        raise ValueError(f"invalid llm confidence: {confidence}")
    if not isinstance(missing_evidence, list):
        raise ValueError("llm missing evidence must be a list.")
    if not isinstance(dimension_reviews, dict):
        raise ValueError("llm dimension reviews must be an object.")
    if not isinstance(real_called, bool):
        raise ValueError("llm real called must be a boolean.")

    return {
        "llm_review_result": review_result,
        "llm_confidence": confidence,
        "llm_challenge_reason": str(challenge_reason),
        "llm_missing_evidence": [str(value) for value in missing_evidence],
        "llm_dimension_reviews": dimension_reviews,
        "llm_recommended_human_action": str(human_action),
        "llm_real_called": real_called,
    }


def human_review_priority(
    rule_decision: str,
    llm_review_result: str,
    llm_confidence: str,
    overall_evidence_coverage: str,
) -> tuple[str, str]:
    if llm_review_result == "challenge":
        if rule_decision == "main_push":
            return "high", "规则建议主推，但 LLM Judge 提出挑战，需人工复核"
        return "high", "LLM Judge 对规则结果提出挑战，需人工复核"
    if llm_review_result == "insufficient_evidence":
        if overall_evidence_coverage in {"weak", "missing"}:
            return "high", "LLM Judge 判断证据不足，且整体证据覆盖较弱，需优先补证"
        return "medium", "LLM Judge 判断证据不足，建议补证后人工复核"
    if llm_review_result == "agree":
        if llm_confidence == "high":
            return "low", "LLM Judge 高置信同意规则结果"
        return "medium", "LLM Judge 同意规则结果，但置信度有限，建议常规人工抽查"
    return "medium", "尚未执行 LLM Judge 复核，建议安排常规人工检查"


def merge_product(
    evidence_item: dict[str, Any],
    judge_result: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = deepcopy(evidence_item)
    evidence_pack = evidence_item.get("evidence_pack", {})
    if not isinstance(evidence_pack, dict):
        evidence_pack = {}
    summary = evidence_item.get("evidence_coverage_summary", {})
    if not isinstance(summary, dict):
        summary = {}

    rule_decision = str(evidence_item.get("decision") or evidence_item.get("rule_decision") or "")
    coverage = str(
        evidence_item.get("overall_evidence_coverage")
        or evidence_pack.get("overall_evidence_coverage")
        or summary.get("overall_evidence_coverage")
        or "missing"
    )
    missing_total = int(
        evidence_item.get("missing_evidence_total")
        or evidence_pack.get("missing_evidence_total")
        or summary.get("missing_evidence_total")
        or 0
    )
    llm_fields = normalize_judge_result(judge_result)
    priority, reason = human_review_priority(
        rule_decision,
        llm_fields["llm_review_result"],
        llm_fields["llm_confidence"],
        coverage,
    )

    merged.update(
        {
            "source_detected": str(
                evidence_item.get("source_detected")
                or evidence_pack.get("source_detected")
                or ""
            ),
            "rule_decision": rule_decision,
            "overall_evidence_coverage": coverage,
            "missing_evidence_total": missing_total,
            **llm_fields,
            "final_human_review_priority": priority,
            "final_human_review_reason": reason,
        }
    )
    return merged


def merge_llm_judge_results(
    evidence_payload: Any,
    judge_results_payload: Any,
) -> dict[str, Any]:
    evidence_items = extract_items(evidence_payload, "evidence payload")
    judge_index = index_judge_results(judge_results_payload)
    products = [
        merge_product(item, judge_index.get(str(item.get("product_id", ""))))
        for item in evidence_items
    ]
    return {
        "mode": "product_intel_llm_judge_merged_v1.9",
        "product_count": len(products),
        "products": products,
    }


def build_ops_summary(products: list[dict[str, Any]]) -> dict[str, Any]:
    rule_counts = Counter(product["rule_decision"] for product in products)
    review_counts = Counter(product["llm_review_result"] for product in products)
    confidence_counts = Counter(product["llm_confidence"] for product in products)
    priority_counts = Counter(product["final_human_review_priority"] for product in products)
    high_priority_products = [
        {
            "product_id": product["product_id"],
            "product_name": product["product_name"],
            "rule_decision": product["rule_decision"],
            "llm_review_result": product["llm_review_result"],
            "reason": product["final_human_review_reason"],
        }
        for product in products
        if product["final_human_review_priority"] == "high"
    ]
    main_push_challenged = [
        {
            "product_id": product["product_id"],
            "product_name": product["product_name"],
            "reason": product["final_human_review_reason"],
        }
        for product in products
        if product["rule_decision"] == "main_push"
        and product["llm_review_result"] == "challenge"
    ]
    return {
        "total_products": len(products),
        "rule_decision_counts": dict(sorted(rule_counts.items())),
        "llm_review_result_counts": dict(sorted(review_counts.items())),
        "llm_confidence_counts": dict(sorted(confidence_counts.items())),
        "final_human_review_priority_counts": dict(sorted(priority_counts.items())),
        "challenge_count": review_counts.get("challenge", 0),
        "insufficient_evidence_count": review_counts.get("insufficient_evidence", 0),
        "high_priority_count": priority_counts.get("high", 0),
        "high_priority_products": high_priority_products,
        "main_push_challenged_products": main_push_challenged,
        "missing_judge_result_count": review_counts.get("not_reviewed", 0),
    }


def summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Product Intel v1.9 LLM Review Ops Summary",
        "",
        "## 核心统计",
        "",
        f"- 商品总数：{summary['total_products']}",
        f"- 规则决策分布：{json.dumps(summary['rule_decision_counts'], ensure_ascii=False)}",
        f"- LLM 复核分布：{json.dumps(summary['llm_review_result_counts'], ensure_ascii=False)}",
        f"- 人工复核优先级：{json.dumps(summary['final_human_review_priority_counts'], ensure_ascii=False)}",
        f"- LLM challenge 数量：{summary['challenge_count']}",
        f"- 证据不足数量：{summary['insufficient_evidence_count']}",
        f"- 未复核数量：{summary['missing_judge_result_count']}",
        "",
        "## 高优先级人工复核商品",
        "",
        "| 商品 ID | 商品名 | 规则决策 | LLM 复核 | 原因 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for product in summary["high_priority_products"]:
        lines.append(
            f"| {product['product_id']} | {product['product_name']} | "
            f"{product['rule_decision']} | {product['llm_review_result']} | {product['reason']} |"
        )
    if not summary["high_priority_products"]:
        lines.append("| - | - | - | - | 无 |")
    lines.extend(
        [
            "",
            "## 主推商品 LLM Challenge",
            "",
            "| 商品 ID | 商品名 | 原因 |",
            "| --- | --- | --- |",
        ]
    )
    for product in summary["main_push_challenged_products"]:
        lines.append(f"| {product['product_id']} | {product['product_name']} | {product['reason']} |")
    if not summary["main_push_challenged_products"]:
        lines.append("| - | - | 无 |")
    return "\n".join(lines) + "\n"


def write_outputs(
    merged_payload: dict[str, Any],
    output_dir: str | Path,
    filenames: dict[str, str] | None = None,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    products = merged_payload["products"]
    summary = build_ops_summary(products)
    names = {
        "merged_json": "all_evidence_with_llm_review.json",
        "merged_csv": "all_evidence_with_llm_review.csv",
        "summary_json": "llm_review_ops_summary.json",
        "summary_md": "llm_review_ops_summary.md",
        **(filenames or {}),
    }
    paths = {
        key: output / filename for key, filename in names.items()
    }
    paths["merged_json"].write_text(
        json.dumps(merged_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with paths["merged_csv"].open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for product in products:
            row = {field: product.get(field, "") for field in CSV_FIELDS}
            row["llm_missing_evidence"] = json.dumps(
                row["llm_missing_evidence"], ensure_ascii=False
            )
            writer.writerow(row)
    paths["summary_json"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["summary_md"].write_text(summary_markdown(summary), encoding="utf-8")
    return paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, help="all_evidence.json path")
    parser.add_argument("--judge-results", required=True, help="Judge results JSON path")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    merged = merge_llm_judge_results(load_json(args.evidence), load_json(args.judge_results))
    paths = write_outputs(merged, args.output_dir)
    summary = build_ops_summary(merged["products"])
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for label, path in paths.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()
