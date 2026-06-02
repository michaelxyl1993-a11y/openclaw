"""Generate local mock Feishu upload tokens and a sandbox receipt."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


MODE = "feishu_upload_adapter_mock_v1.14"
TOKEN_CSV_FIELDS = [
    "filename",
    "path",
    "size_bytes",
    "file_type",
    "mock_file_token",
    "upload_status",
    "real_upload_called",
]


def load_dry_run_plan(path: str | Path) -> dict[str, Any]:
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise ValueError("Feishu upload dry-run plan must be an object.")
    if plan.get("ready_for_upload") is not True:
        raise ValueError("Feishu mock upload blocked: dry-run plan is not ready_for_upload.")
    if not isinstance(plan.get("attachment_items"), list):
        raise ValueError("Feishu upload dry-run plan attachment_items must be a list.")
    return plan


def stable_mock_file_token(item: dict[str, Any]) -> str:
    seed = "|".join(
        [
            str(item.get("path", "")),
            str(item.get("filename", "")),
            str(item.get("size_bytes", "")),
            str(item.get("file_type", "")),
        ]
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:20]
    return f"mock_file_token_{digest}"


def build_mock_attachment_tokens(plan: dict[str, Any]) -> list[dict[str, Any]]:
    tokens: list[dict[str, Any]] = []
    for item in plan["attachment_items"]:
        if not isinstance(item, dict):
            raise ValueError("Feishu mock upload blocked: attachment item must be an object.")
        if not item.get("exists") or not item.get("non_empty"):
            raise ValueError(
                f"Feishu mock upload blocked: invalid attachment {item.get('path', '')}."
            )
        tokens.append(
            {
                "filename": str(item.get("filename", "")),
                "path": str(item.get("path", "")),
                "size_bytes": int(item.get("size_bytes", 0)),
                "file_type": str(item.get("file_type", "")),
                "mock_file_token": stable_mock_file_token(item),
                "upload_status": "mock_uploaded",
                "real_upload_called": False,
            }
        )
    return tokens


def build_message_preview(message_path: str | Path, tokens: list[dict[str, Any]]) -> str:
    message = Path(message_path).read_text(encoding="utf-8")
    if not message.strip():
        raise ValueError("Feishu mock upload blocked: handoff message is empty.")
    lines = [
        message.rstrip(),
        "",
        "## Mock / Sandbox 附件 Tokens",
        "",
        "- 本次为 mock/sandbox，不会发送飞书消息。",
        "- 本次不会调用真实飞书 API，也不会上传真实附件。",
        "",
    ]
    lines.extend(
        f"- {item['filename']}：{item['mock_file_token']}" for item in tokens
    )
    return "\n".join(lines) + "\n"


def build_receipt(
    tokens: list[dict[str, Any]],
    message_preview_path: str | Path,
) -> dict[str, Any]:
    return {
        "mode": MODE,
        "ready_for_mock_send": True,
        "real_feishu_api_called": False,
        "real_message_sent": False,
        "total_attachments": len(tokens),
        "mock_uploaded_count": len(tokens),
        "attachment_tokens": tokens,
        "message_preview_path": str(message_preview_path),
    }


def write_outputs(
    plan: dict[str, Any],
    message_path: str | Path,
    output_dir: str | Path,
) -> tuple[dict[str, Path], dict[str, Any]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "receipt_json": output / "feishu_upload_mock_receipt.json",
        "message_preview_md": output / "feishu_upload_mock_message_preview.md",
        "attachment_tokens_csv": output / "feishu_upload_mock_attachment_tokens.csv",
    }
    tokens = build_mock_attachment_tokens(plan)
    paths["message_preview_md"].write_text(
        build_message_preview(message_path, tokens),
        encoding="utf-8",
    )
    receipt = build_receipt(tokens, paths["message_preview_md"])
    paths["receipt_json"].write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with paths["attachment_tokens_csv"].open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=TOKEN_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(tokens)
    return paths, receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run-plan", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    plan = load_dry_run_plan(args.dry_run_plan)
    paths, receipt = write_outputs(plan, args.message, args.output_dir)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    for label, path in paths.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()

