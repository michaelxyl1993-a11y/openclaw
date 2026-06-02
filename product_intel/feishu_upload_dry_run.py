"""Validate Feishu handoff files and generate a local-only upload plan."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


MESSAGE_MARKERS = [
    "Product Intel 选品虾｜最终运营交付",
    "manual-3",
    "规则建议 main_push，但 LLM Judge challenge",
]
CSV_FIELDS = [
    "path",
    "filename",
    "file_type",
    "size_bytes",
    "exists",
    "non_empty",
    "upload_required",
    "upload_status",
]


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("handoff manifest must be an object.")
    for field in ["source_files", "output_files"]:
        if not isinstance(manifest.get(field), list):
            raise ValueError(f"handoff manifest {field} must be a list.")
    return manifest


def unique_attachment_paths(manifest: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for value in [*manifest["source_files"], *manifest["output_files"]]:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            paths.append(text)
    return paths


def inspect_attachment(path: str | Path) -> dict[str, Any]:
    attachment = Path(path)
    exists = attachment.exists() and attachment.is_file()
    size = attachment.stat().st_size if exists else 0
    return {
        "path": str(attachment),
        "filename": attachment.name,
        "file_type": attachment.suffix.lstrip(".").lower() or "unknown",
        "size_bytes": size,
        "exists": exists,
        "non_empty": exists and size > 0,
        "upload_required": True,
        "upload_status": "dry_run_only",
    }


def inspect_message(path: str | Path) -> dict[str, Any]:
    message_path = Path(path)
    exists = message_path.exists() and message_path.is_file()
    text = message_path.read_text(encoding="utf-8") if exists else ""
    marker_checks = {marker: marker in text for marker in MESSAGE_MARKERS}
    return {
        "path": str(message_path),
        "exists": exists,
        "non_empty": bool(text.strip()),
        "marker_checks": marker_checks,
        "ready": exists and bool(text.strip()) and all(marker_checks.values()),
    }


def build_dry_run_plan(
    manifest: dict[str, Any],
    message_path: str | Path,
) -> dict[str, Any]:
    attachments = [
        inspect_attachment(path) for path in unique_attachment_paths(manifest)
    ]
    valid_count = sum(item["exists"] and item["non_empty"] for item in attachments)
    invalid_count = len(attachments) - valid_count
    message = inspect_message(message_path)
    return {
        "ready_for_upload": invalid_count == 0 and message["ready"],
        "total_attachments": len(attachments),
        "valid_attachment_count": valid_count,
        "invalid_attachment_count": invalid_count,
        "message_ready": message["ready"],
        "message_check": message,
        "will_call_feishu_api": False,
        "will_send_message": False,
        "attachment_items": attachments,
    }


def report_markdown(plan: dict[str, Any]) -> str:
    valid = [
        item for item in plan["attachment_items"] if item["exists"] and item["non_empty"]
    ]
    invalid = [
        item for item in plan["attachment_items"] if not item["exists"] or not item["non_empty"]
    ]
    lines = [
        "# Product Intel Feishu Upload Dry Run Report",
        "",
        "## 结论",
        "",
        f"- ready_for_upload：{str(plan['ready_for_upload']).lower()}",
        f"- 附件总数：{plan['total_attachments']}",
        f"- 有效附件：{plan['valid_attachment_count']}",
        f"- 异常附件：{plan['invalid_attachment_count']}",
        f"- handoff message 可用：{str(plan['message_ready']).lower()}",
        "- 本次不会调用飞书 API。",
        "- 本次不会发送消息。",
        "",
        "## 可上传附件列表",
        "",
    ]
    for item in valid:
        lines.append(f"- {item['path']}（{item['size_bytes']} bytes）")
    if not valid:
        lines.append("- 无")
    lines.extend(["", "## 缺失或异常附件", ""])
    for item in invalid:
        lines.append(
            f"- {item['path']}：exists={str(item['exists']).lower()}，"
            f"non_empty={str(item['non_empty']).lower()}"
        )
    if not invalid:
        lines.append("- 无")
    lines.extend(
        [
            "",
            "## 真实上传前确认事项",
            "",
            "- [ ] 人工确认附件清单与目标飞书会话。",
            "- [ ] 人工确认 manual-3 已完成复核。",
            "- [ ] 人工确认 handoff message 文案。",
            "- [ ] 仅在明确授权后使用独立真实上传流程。",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(plan: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "plan_json": output / "feishu_upload_dry_run_plan.json",
        "report_md": output / "feishu_upload_dry_run_report.md",
        "attachment_csv": output / "feishu_upload_attachment_manifest.csv",
    }
    paths["plan_json"].write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["report_md"].write_text(report_markdown(plan), encoding="utf-8")
    with paths["attachment_csv"].open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(
            {field: item[field] for field in CSV_FIELDS}
            for item in plan["attachment_items"]
        )
    return paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plan = build_dry_run_plan(load_manifest(args.manifest), args.message)
    paths = write_outputs(plan, args.output_dir)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    for label, path in paths.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()

