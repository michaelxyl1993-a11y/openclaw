"""Build a cross-source operations distribution table from Product Intel outputs."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


PACKAGE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PACKAGE_DIR / "output_ops_summary"
SOURCES = ["echotik", "fastmoss", "kalodata", "manual"]
DECISIONS = ["main_push", "small_test", "hold", "reject"]
DECISION_LABELS = {
    "main_push": "今天可主推",
    "small_test": "小样本测试",
    "hold": "暂缓",
    "reject": "淘汰",
}
EXPECTED_NEXT_ACTION = {
    "main_push": "今天可主推",
    "small_test": "小样本测试",
    "hold": "暂缓",
    "reject": "淘汰",
}
CSV_FIELDS = [
    "source_platform",
    "source_rank",
    "product_id",
    "product_name",
    "category",
    "price",
    "commission_rate",
    "sold_count",
    "gmv",
    "opportunity_score",
    "decision",
    "decision_label",
    "distribution_priority",
    "risk_level",
    "risk_flags",
    "strongest_dimensions",
    "weakest_dimensions",
    "missing_evidence_count",
    "core_decision_basis",
    "recommended_formats",
    "recommended_hooks",
    "suggested_daily_posts",
    "account_type",
    "next_action",
    "next_action_consistent",
    "manager_instruction",
]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def risk_level(product: dict[str, Any]) -> str:
    flags = product.get("risk_flags", [])
    joined = " ".join(str(flag) for flag in flags)
    if "Human review is required" in joined or "需人工复核" in joined or "表达需谨慎" in joined:
        return "high_review"
    if flags:
        return "attention"
    return "low"


def distribution_priority(decision: str) -> str:
    return {
        "main_push": "P0_今日主推",
        "small_test": "P1_小样本测试",
        "hold": "P2_暂缓补证",
        "reject": "P3_淘汰",
    }.get(decision, "P9_待确认")


def join_values(values: Any) -> str:
    if isinstance(values, list):
        return "；".join(str(value) for value in values)
    return str(values or "")


def validate_next_action(decision: str, next_action: str) -> bool:
    expected = EXPECTED_NEXT_ACTION.get(decision)
    return bool(expected and expected in next_action)


def load_source(source: str) -> tuple[dict[str, Any], list[dict[str, str]], list[dict[str, Any]]]:
    source_dir = PACKAGE_DIR / f"output_{source}"
    payload = read_json(source_dir / "product_intel_manager_payload.json")
    decision_rows = read_csv(source_dir / "product_intel_decision_table.csv")
    products = payload.get("products", [])
    product_by_id = {str(product.get("product_id", "")): product for product in products}
    csv_by_id = {str(row.get("product_id", "")): row for row in decision_rows}
    if set(product_by_id) != set(csv_by_id):
        raise ValueError(f"{source}: manager payload and decision CSV product IDs differ")

    operating_rows: list[dict[str, Any]] = []
    for csv_row in decision_rows:
        product = product_by_id[csv_row["product_id"]]
        decision = str(product.get("decision", ""))
        next_action = str(product.get("next_action", ""))
        if csv_row.get("decision") != decision or csv_row.get("next_action") != next_action:
            raise ValueError(f"{source}/{csv_row['product_id']}: payload and decision CSV differ")
        routing = product.get("routing", {}) if isinstance(product.get("routing"), dict) else {}
        operating_rows.append({
            "source_platform": source,
            "source_rank": product.get("rank", ""),
            "product_id": product.get("product_id", ""),
            "product_name": product.get("product_name", ""),
            "category": product.get("category", ""),
            "price": product.get("price", ""),
            "commission_rate": product.get("commission_rate", ""),
            "sold_count": product.get("sold_count", ""),
            "gmv": product.get("gmv", ""),
            "opportunity_score": product.get("opportunity_score", ""),
            "decision": decision,
            "decision_label": DECISION_LABELS.get(decision, product.get("decision_label", "")),
            "distribution_priority": distribution_priority(decision),
            "risk_level": risk_level(product),
            "risk_flags": join_values(product.get("risk_flags", [])),
            "strongest_dimensions": product.get("strongest_dimensions", ""),
            "weakest_dimensions": product.get("weakest_dimensions", ""),
            "missing_evidence_count": product.get("missing_evidence_count", 0),
            "core_decision_basis": product.get("main_push_reason", ""),
            "recommended_formats": join_values(product.get("recommended_formats", [])),
            "recommended_hooks": join_values(product.get("recommended_hooks", [])),
            "suggested_daily_posts": product.get("suggested_daily_posts", ""),
            "account_type": routing.get("account_type", ""),
            "next_action": next_action,
            "next_action_consistent": "yes" if validate_next_action(decision, next_action) else "no",
            "manager_instruction": product.get("manager_instruction", ""),
        })
    return payload, decision_rows, operating_rows


def markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "/") for value in row) + " |")
    return lines


def build_markdown(source_payloads: dict[str, dict[str, Any]], operating_rows: list[dict[str, Any]]) -> str:
    counts = Counter(row["decision"] for row in operating_rows)
    inconsistent = [row for row in operating_rows if row["next_action_consistent"] != "yes"]
    lines = [
        "# Product Intel v1.6 运营分发表",
        "",
        "## 总览",
        "",
        f"- 商品总数：{len(operating_rows)}",
        f"- 决策分布：main_push {counts['main_push']} / small_test {counts['small_test']} / hold {counts['hold']} / reject {counts['reject']}",
        f"- next_action 一致性：{'全部通过' if not inconsistent else f'存在 {len(inconsistent)} 条冲突'}",
        "",
        "## 来源汇总",
        "",
    ]
    source_rows = []
    for source in SOURCES:
        meta = source_payloads[source].get("meta", {})
        source_rows.append([
            source,
            meta.get("total_products", 0),
            meta.get("main_push_count", 0),
            meta.get("small_test_count", 0),
            meta.get("hold_count", 0),
            meta.get("reject_count", 0),
        ])
    lines.extend(markdown_table(["来源", "商品总数", "main_push", "small_test", "hold", "reject"], source_rows))

    lines.extend(["", "## 各来源 Top 5", ""])
    for source in SOURCES:
        lines.extend([f"### {source}", ""])
        source_rows = [row for row in operating_rows if row["source_platform"] == source][:5]
        lines.extend(markdown_table(
            ["排名", "商品", "分数", "决策", "核心依据", "next_action"],
            [[row["source_rank"], row["product_name"], row["opportunity_score"], row["decision"],
              row["core_decision_basis"], row["next_action"]] for row in source_rows],
        ))
        lines.append("")

    lines.extend(["## 风险商品", ""])
    risk_rows = [row for row in operating_rows if row["risk_level"] != "low"]
    lines.extend(markdown_table(
        ["来源", "商品", "决策", "风险等级", "风险标记", "强维度", "弱维度"],
        [[row["source_platform"], row["product_name"], row["decision"], row["risk_level"],
          row["risk_flags"], row["strongest_dimensions"], row["weakest_dimensions"]] for row in risk_rows],
    ))

    lines.extend(["", "## 运营分发表", ""])
    lines.extend(markdown_table(
        ["优先级", "来源", "商品", "类目", "分数", "决策", "风险", "建议日更", "账号类型", "核心依据", "next_action"],
        [[row["distribution_priority"], row["source_platform"], row["product_name"], row["category"],
          row["opportunity_score"], row["decision"], row["risk_level"], row["suggested_daily_posts"],
          row["account_type"], row["core_decision_basis"], row["next_action"]] for row in operating_rows],
    ))
    return "\n".join(lines) + "\n"


def main() -> None:
    source_payloads: dict[str, dict[str, Any]] = {}
    operating_rows: list[dict[str, Any]] = []
    for source in SOURCES:
        payload, _decision_rows, rows = load_source(source)
        source_payloads[source] = payload
        operating_rows.extend(rows)
    operating_rows.sort(key=lambda row: (row["distribution_priority"], -int(row["opportunity_score"]), row["source_platform"]))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / "product_intel_v1_6_ops_distribution.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(operating_rows)
    md_path = OUTPUT_DIR / "product_intel_v1_6_ops_summary.md"
    md_path.write_text(build_markdown(source_payloads, operating_rows), encoding="utf-8")

    inconsistent = [row for row in operating_rows if row["next_action_consistent"] != "yes"]
    counts = Counter(row["decision"] for row in operating_rows)
    print(f"products={len(operating_rows)}")
    print("distribution=" + " ".join(f"{decision}:{counts[decision]}" for decision in DECISIONS))
    print(f"next_action_conflicts={len(inconsistent)}")
    print(f"markdown={md_path}")
    print(f"csv={csv_path}")


if __name__ == "__main__":
    main()
