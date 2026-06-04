"""Build final operations attachment upload plan and message preview."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .feishu_product_intel_bot import infer_feishu_file_type


MODE = "feishu_final_attachment_pack_v1.25"
PLAN_FILENAME = "feishu_final_attachment_upload_plan.json"
PREVIEW_FILENAME = "feishu_final_attachment_message_preview.md"
SUMMARY_JSON_FILENAME = "feishu_final_attachment_pack_summary.json"
SUMMARY_MD_FILENAME = "feishu_final_attachment_pack_summary.md"


class FeishuFinalAttachmentPackError(ValueError):
    """Raised when final ops attachments cannot be packed."""


def attachment_item(path: str | Path, index: int) -> dict[str, Any]:
    attachment_path = Path(path)
    exists = attachment_path.exists() and attachment_path.is_file()
    size = attachment_path.stat().st_size if exists else 0
    non_empty = size > 0
    return {
        "attachment_index": index,
        "path": str(attachment_path),
        "filename": attachment_path.name,
        "file_type": infer_feishu_file_type(str(attachment_path)),
        "size_bytes": size,
        "exists": exists,
        "non_empty": non_empty,
        "upload_required": exists and non_empty,
        "upload_status": "pending" if exists and non_empty else "missing",
    }


def build_upload_plan(attachments: Sequence[str | Path]) -> dict[str, Any]:
    if not attachments:
        raise FeishuFinalAttachmentPackError("At least one attachment is required.")
    items = [attachment_item(path, index) for index, path in enumerate(attachments)]
    ready = all(item["upload_required"] for item in items)
    return {
        "mode": MODE,
        "ready_for_upload": ready,
        "real_feishu_api_called": False,
        "real_message_sent": False,
        "attachment_count": len(items),
        "existing_attachment_count": sum(item["exists"] and item["non_empty"] for item in items),
        "missing_attachment_count": sum(not item["upload_required"] for item in items),
        "total_size_bytes": sum(item["size_bytes"] for item in items),
        "attachment_items": items,
    }


def build_message_preview(plan: dict[str, Any]) -> str:
    lines = [
        "# Product Intel 选品虾｜附件已生成",
        "",
        "以下最终运营交付附件已上传：",
    ]
    for item in plan["attachment_items"]:
        lines.append(f"- {item['filename']}")
    lines.extend(
        [
            "",
            "说明：",
            "- final_ops_decision_table.csv：完整商品运营决策表",
            "- final_ops_action_summary.md：运营动作摘要",
            "- final_challenge_products.csv：需人工复核商品",
            "- final_review_note.md：本轮最终复核说明",
            "",
            "当前发送方式：文本说明消息；如需发送文件消息，请使用后续附件文件消息 adapter。",
        ]
    )
    return "\n".join(lines) + "\n"


def build_summary(plan: dict[str, Any], output_dir: str | Path) -> dict[str, Any]:
    output = Path(output_dir)
    return {
        "mode": MODE,
        "attachment_count": plan["attachment_count"],
        "existing_attachment_count": plan["existing_attachment_count"],
        "missing_attachment_count": plan["missing_attachment_count"],
        "total_size_bytes": plan["total_size_bytes"],
        "filenames": [item["filename"] for item in plan["attachment_items"]],
        "ready_for_upload": plan["ready_for_upload"],
        "output_files": {
            "upload_plan": str(output / PLAN_FILENAME),
            "message_preview": str(output / PREVIEW_FILENAME),
            "summary_json": str(output / SUMMARY_JSON_FILENAME),
            "summary_md": str(output / SUMMARY_MD_FILENAME),
        },
        "next_command": (
            "python3 -m product_intel.feishu_final_attachment_upload_real "
            f"--upload-plan {output / PLAN_FILENAME} --output-dir {output}"
            if plan["ready_for_upload"]
            else ""
        ),
    }


def summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Product Intel v1.25 Final Attachment Pack Summary",
        "",
        f"- attachment_count：{summary['attachment_count']}",
        f"- existing_attachment_count：{summary['existing_attachment_count']}",
        f"- missing_attachment_count：{summary['missing_attachment_count']}",
        f"- total_size_bytes：{summary['total_size_bytes']}",
        f"- ready_for_upload：{str(summary['ready_for_upload']).lower()}",
        "",
        "## Attachments",
        "",
    ]
    lines.extend(f"- {filename}" for filename in summary["filenames"])
    if summary["next_command"]:
        lines.extend(["", "## Next", "", f"`{summary['next_command']}`"])
    lines.append("")
    return "\n".join(lines)


def write_outputs(
    plan: dict[str, Any],
    message_preview: str,
    output_dir: str | Path,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    summary = build_summary(plan, output)
    paths = {
        "upload_plan": output / PLAN_FILENAME,
        "message_preview": output / PREVIEW_FILENAME,
        "summary_json": output / SUMMARY_JSON_FILENAME,
        "summary_md": output / SUMMARY_MD_FILENAME,
    }
    paths["upload_plan"].write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    paths["message_preview"].write_text(message_preview, encoding="utf-8")
    paths["summary_json"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    paths["summary_md"].write_text(summary_markdown(summary), encoding="utf-8")
    return paths


def build_pack(attachments: Sequence[str | Path], output_dir: str | Path) -> dict[str, Any]:
    plan = build_upload_plan(attachments)
    message_preview = build_message_preview(plan)
    paths = write_outputs(plan, message_preview, output_dir)
    summary = build_summary(plan, output_dir)
    summary["output_files"] = {key: str(path) for key, path in paths.items()}
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--attachment", action="append", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = build_pack(args.attachment, args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
