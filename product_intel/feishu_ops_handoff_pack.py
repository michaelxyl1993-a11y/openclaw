"""Generate local-only Feishu operations handoff pack files."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


VERSION = "product_intel_feishu_ops_handoff_v1.12"
ATTACHMENT_NAMES = [
    "final_ops_decision_table.csv",
    "final_ops_decision_table.md",
    "final_ops_action_summary.json",
    "final_ops_action_summary.md",
    "final_challenge_products.csv",
    "final_review_note.md",
]
OUTPUT_NAMES = [
    "feishu_ops_handoff_message.md",
    "feishu_ops_handoff_manifest.json",
    "feishu_ops_handoff_brief.json",
    "feishu_ops_handoff_checklist.md",
]


def load_final_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("final operations table contains no products.")
    required = {
        "product_id",
        "product_name",
        "source_platform",
        "rule_decision",
        "llm_review_result",
        "final_human_review_priority",
        "final_ops_action",
        "final_ops_priority",
        "final_ops_reason",
    }
    missing = sorted(required - set(rows[0]))
    if missing:
        raise ValueError(f"final operations table missing columns: {', '.join(missing)}")
    return rows


def load_summary(path: str | Path) -> dict[str, Any]:
    summary = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(summary, dict) or "total_products" not in summary:
        raise ValueError("final operations summary must be an object with total_products.")
    return summary


def product_ref(row: dict[str, str]) -> dict[str, str]:
    return {
        "product_id": row["product_id"],
        "product_name": row["product_name"],
        "source_platform": row["source_platform"],
        "rule_decision": row["rule_decision"],
        "llm_review_result": row["llm_review_result"],
        "final_ops_action": row["final_ops_action"],
        "final_ops_priority": row["final_ops_priority"],
        "final_ops_reason": row["final_ops_reason"],
    }


def attachment_paths(output_dir: str | Path) -> list[str]:
    output = Path(output_dir)
    return [str(output / name) for name in ATTACHMENT_NAMES]


def build_brief(rows: list[dict[str, str]], output_dir: str | Path) -> dict[str, Any]:
    actions = Counter(row["final_ops_action"] for row in rows)
    main_push = [product_ref(row) for row in rows if row["final_ops_action"] == "main_push"]
    small_test = [product_ref(row) for row in rows if row["final_ops_action"] == "small_test"]
    human_review = [
        product_ref(row) for row in rows if row["final_ops_action"] == "human_review_first"
    ]
    hold = [
        product_ref(row)
        for row in rows
        if row["final_ops_action"] in {"hold_for_evidence", "evidence_required", "not_ready"}
    ]
    return {
        "total_products": len(rows),
        "today_executable_count": len(main_push) + len(small_test),
        "human_review_first_count": len(human_review),
        "hold_count": len(hold),
        "challenge_count": sum(row["llm_review_result"] == "challenge" for row in rows),
        "main_push_products": main_push,
        "small_test_products": small_test,
        "human_review_products": human_review,
        "hold_products": hold,
        "attachment_paths": attachment_paths(output_dir),
    }


def format_product_line(product: dict[str, str]) -> str:
    return (
        f"- {product['product_id']}｜{product['product_name']}｜"
        f"{product['final_ops_action']}｜{product['final_ops_priority']}"
    )


def build_handoff_message(
    rows: list[dict[str, str]],
    brief: dict[str, Any],
) -> str:
    actions = Counter(row["final_ops_action"] for row in rows)
    llm_reviews = Counter(row["llm_review_result"] for row in rows)
    high_priority_review = sum(
        row["final_human_review_priority"] == "high" for row in rows
    )
    lines = [
        "# Product Intel 选品虾｜最终运营交付",
        "",
        "## 1. 本轮总览",
        "",
        f"- 商品总数：{brief['total_products']}",
        f"- main_push：{actions.get('main_push', 0)}",
        f"- small_test：{actions.get('small_test', 0)}",
        f"- hold：{actions.get('hold_for_evidence', 0) + actions.get('evidence_required', 0)}",
        f"- human_review_first：{actions.get('human_review_first', 0)}",
        f"- LLM agree：{llm_reviews.get('agree', 0)}",
        f"- LLM challenge：{llm_reviews.get('challenge', 0)}",
        f"- high priority review：{high_priority_review}",
        "",
        "## 2. 今日可执行",
        "",
    ]
    for product in [*brief["main_push_products"], *brief["small_test_products"]]:
        lines.append(format_product_line(product))
    if not brief["main_push_products"] and not brief["small_test_products"]:
        lines.append("- 无")
    lines.extend(["", "## 3. 必须人工复核", ""])
    for product in brief["human_review_products"]:
        lines.append(format_product_line(product))
        if product["product_id"] == "manual-3":
            lines.append("- manual-3：规则建议 main_push，但 LLM Judge challenge，需人工复核后再放大")
    if not brief["human_review_products"]:
        lines.append("- 无")
    lines.extend(["", "## 4. 暂缓补证", ""])
    for product in brief["hold_products"]:
        lines.append(format_product_line(product))
    if not brief["hold_products"]:
        lines.append("- 无")
    lines.extend(["", "## 5. 附件清单", ""])
    lines.extend(f"- {path}" for path in brief["attachment_paths"])
    return "\n".join(lines) + "\n"


def build_manifest(
    rows: list[dict[str, str]],
    final_table: str | Path,
    summary: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    manual_review_products = [
        product_ref(row) for row in rows if row["final_ops_action"] == "human_review_first"
    ]
    output = Path(output_dir)
    return {
        "version": VERSION,
        "source_files": [str(Path(final_table)), str(Path(summary))],
        "output_files": [str(output / name) for name in OUTPUT_NAMES],
        "total_products": len(rows),
        "ready_for_feishu_upload": True,
        "requires_manual_review": bool(manual_review_products),
        "manual_review_products": manual_review_products,
    }


def checklist_markdown() -> str:
    return """# Product Intel Handoff Checklist

- [ ] 确认 final_ops_decision_table.csv 可打开
- [ ] 确认 manual-3 已人工复核
- [ ] 确认主推商品未被 LLM challenge
- [ ] 确认小样本商品已分配账号
- [ ] 确认 hold 商品不进入今日生产
- [ ] 确认附件已上传飞书
- [ ] 确认运营负责人已收到 handoff message
"""


def write_handoff_pack(
    rows: list[dict[str, str]],
    summary: dict[str, Any],
    final_table: str | Path,
    summary_path: str | Path,
    output_dir: str | Path,
) -> tuple[dict[str, Path], dict[str, Any], dict[str, Any]]:
    if int(summary["total_products"]) != len(rows):
        raise ValueError("final table and summary total_products do not match.")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    brief = build_brief(rows, output)
    manifest = build_manifest(rows, final_table, summary_path, output)
    paths = {
        "handoff_message": output / OUTPUT_NAMES[0],
        "manifest": output / OUTPUT_NAMES[1],
        "brief": output / OUTPUT_NAMES[2],
        "checklist": output / OUTPUT_NAMES[3],
    }
    paths["handoff_message"].write_text(
        build_handoff_message(rows, brief),
        encoding="utf-8",
    )
    paths["manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["brief"].write_text(
        json.dumps(brief, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["checklist"].write_text(checklist_markdown(), encoding="utf-8")
    return paths, manifest, brief


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final-table", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_final_rows(args.final_table)
    summary = load_summary(args.summary)
    paths, manifest, brief = write_handoff_pack(
        rows,
        summary,
        args.final_table,
        args.summary,
        args.output_dir,
    )
    print(json.dumps({"manifest": manifest, "brief": brief}, ensure_ascii=False, indent=2))
    for label, path in paths.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()

