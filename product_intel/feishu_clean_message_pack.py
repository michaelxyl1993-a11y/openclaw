"""Generate a clean operations message for opt-in real Feishu text send."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


MODE = "feishu_clean_message_pack_v1.18"
FORBIDDEN_TERMS = [
    "mock",
    "sandbox",
    "mock_file_token",
    "mock_token",
    "using_mock_tokens_for_preview",
    "不会发送真实飞书消息",
    "Feishu Message Send Mock Preview",
]
ATTACHMENT_NAMES = [
    "final_ops_decision_table.csv",
    "final_ops_action_summary.md",
    "final_challenge_products.csv",
    "final_review_note.md",
]


def load_final_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("clean message pack blocked: final table contains no products.")
    required = {"product_id", "product_name", "llm_review_result", "final_ops_action"}
    missing = sorted(required - set(rows[0]))
    if missing:
        raise ValueError(f"clean message pack blocked: final table missing columns: {', '.join(missing)}")
    return rows


def load_summary(path: str | Path) -> dict[str, Any]:
    summary = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(summary, dict) or "total_products" not in summary:
        raise ValueError("clean message pack blocked: final summary is invalid.")
    return summary


def contains_forbidden_terms(text: str) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in FORBIDDEN_TERMS)


def attachment_paths(output_dir: str | Path) -> list[str]:
    output = Path(output_dir)
    return [str(output / name) for name in ATTACHMENT_NAMES]


def format_product(row: dict[str, str]) -> str:
    return f"- {row['product_id']} {row['product_name']}"


def build_clean_message(rows: list[dict[str, str]], output_dir: str | Path) -> str:
    reviews = Counter(row["llm_review_result"] for row in rows)
    executable = [row for row in rows if row["final_ops_action"] in {"main_push", "small_test"}]
    manual_review = [row for row in rows if row["final_ops_action"] == "human_review_first"]
    hold = [
        row
        for row in rows
        if row["final_ops_action"] in {"hold_for_evidence", "evidence_required", "not_ready"}
    ]
    lines = [
        "# Product Intel 选品虾｜最终运营交付",
        "",
        "## 1. 本轮总览",
        "",
        f"- 商品总数：{len(rows)}",
        f"- 今日可执行：{len(executable)}",
        f"- 必须人工复核：{len(manual_review)}",
        f"- 暂缓补证：{len(hold)}",
        f"- LLM agree：{reviews.get('agree', 0)}",
        f"- LLM challenge：{reviews.get('challenge', 0)}",
        "",
        "## 2. 今日可执行",
        "",
    ]
    lines.extend(format_product(row) for row in executable)
    if not executable:
        lines.append("- 无")
    lines.extend(["", "## 3. 必须人工复核", ""])
    lines.extend(format_product(row) for row in manual_review)
    if manual_review:
        lines.append("- 规则建议 main_push，但 LLM Judge challenge，需人工复核后再放大。")
    else:
        lines.append("- 无")
    lines.extend(["", "## 4. 暂缓补证", ""])
    lines.extend(format_product(row) for row in hold)
    if not hold:
        lines.append("- 无")
    lines.extend(["", "## 5. 附件说明", ""])
    lines.extend(f"- {path}" for path in attachment_paths(output_dir))
    message = "\n".join(lines) + "\n"
    if contains_forbidden_terms(message):
        raise ValueError("clean message pack blocked: generated message contains forbidden test terms.")
    return message


def build_plan(
    message: str,
    handoff_message: str | Path,
    final_summary: str | Path,
    final_table: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    output = Path(output_dir)
    forbidden = contains_forbidden_terms(message)
    return {
        "mode": MODE,
        "message_ready": bool(message.strip()) and not forbidden,
        "message_length": len(message),
        "contains_mock_terms": forbidden,
        "attachment_send_enabled": False,
        "attachments_sent": 0,
        "ready_for_real_text_send": bool(message.strip()) and not forbidden,
        "source_files": [
            str(Path(handoff_message)),
            str(Path(final_summary)),
            str(Path(final_table)),
        ],
        "output_files": [
            str(output / "feishu_clean_message_preview.md"),
            str(output / "feishu_clean_message_plan.json"),
            str(output / "feishu_clean_message_checklist.md"),
        ],
    }


def checklist_markdown() -> str:
    return """# Product Intel Clean Message Checklist

- [ ] clean message 不包含 mock/sandbox/token 测试文案
- [ ] manual-3 已标记人工复核
- [ ] 今日可执行商品数量为 8
- [ ] 暂缓补证商品数量为 3
- [ ] 本次只发送文本，不发送附件
- [ ] 真实发送前确认 chat_id 是测试群
- [ ] 真实发送前确认 PRODUCT_INTEL_REAL_FEISHU_MESSAGE_SEND_ENABLED=true
"""


def write_outputs(
    message: str,
    plan: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "message_preview": output / "feishu_clean_message_preview.md",
        "message_plan": output / "feishu_clean_message_plan.json",
        "checklist": output / "feishu_clean_message_checklist.md",
    }
    paths["message_preview"].write_text(message, encoding="utf-8")
    paths["message_plan"].write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["checklist"].write_text(checklist_markdown(), encoding="utf-8")
    return paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff-message", required=True)
    parser.add_argument("--final-summary", required=True)
    parser.add_argument("--final-table", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    Path(args.handoff_message).read_text(encoding="utf-8")
    load_summary(args.final_summary)
    rows = load_final_rows(args.final_table)
    message = build_clean_message(rows, args.output_dir)
    plan = build_plan(
        message,
        args.handoff_message,
        args.final_summary,
        args.final_table,
        args.output_dir,
    )
    paths = write_outputs(message, plan, args.output_dir)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    for label, path in paths.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()

