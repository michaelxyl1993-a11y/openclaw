"""Build a local-only Feishu message send preview with disabled real send."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


MODE = "feishu_message_send_adapter_mock_v1.16"
REDACTED_FILE_TOKENS = {"", "REDACTED_FILE_TOKEN", "null", "None"}


def load_handoff_message(path: str | Path) -> str:
    message = Path(path).read_text(encoding="utf-8")
    if not message.strip():
        raise ValueError("Feishu message mock blocked: handoff message is empty.")
    return message


def load_upload_receipt(path: str | Path) -> dict[str, Any]:
    receipt = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(receipt, dict):
        raise ValueError("Feishu message mock blocked: upload receipt must be an object.")
    return receipt


def load_mock_tokens(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("Feishu message mock blocked: mock token CSV contains no tokens.")
    required = {"filename", "path", "mock_file_token"}
    missing = sorted(required - set(rows[0]))
    if missing:
        raise ValueError(f"Feishu message mock blocked: mock token CSV missing columns: {', '.join(missing)}")
    return rows


def is_real_file_token_available(receipt: dict[str, Any]) -> bool:
    token = str(receipt.get("file_token") or "")
    return receipt.get("upload_status") == "uploaded" and token not in REDACTED_FILE_TOKENS


def resolve_attachment_tokens(
    upload_receipt: dict[str, Any],
    mock_tokens: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], bool, bool]:
    if is_real_file_token_available(upload_receipt):
        return (
            [
                {
                    "filename": str(upload_receipt.get("filename", "")),
                    "path": str(upload_receipt.get("path", "")),
                    "file_token": str(upload_receipt["file_token"]),
                    "token_source": "real_upload_receipt",
                }
            ],
            True,
            False,
        )
    return (
        [
            {
                "filename": row["filename"],
                "path": row["path"],
                "file_token": row["mock_file_token"],
                "token_source": "mock_token_fallback",
            }
            for row in mock_tokens
        ],
        False,
        True,
    )


def build_send_plan(
    message: str,
    upload_receipt: dict[str, Any],
    mock_tokens: list[dict[str, str]],
) -> dict[str, Any]:
    attachment_tokens, real_available, using_mock = resolve_attachment_tokens(
        upload_receipt, mock_tokens
    )
    return {
        "mode": MODE,
        "message_ready": bool(message.strip()),
        "attachment_ready": bool(attachment_tokens),
        "real_file_token_available": real_available,
        "using_mock_tokens_for_preview": using_mock,
        "real_message_send_enabled": False,
        "real_feishu_message_api_called": False,
        "real_message_sent": False,
        "send_status": "mock_only",
        "target_type": "unset",
        "target_id": None,
        "attachment_tokens": attachment_tokens,
    }


def build_preview(message: str, plan: dict[str, Any]) -> str:
    lines = [
        message.rstrip(),
        "",
        "## Feishu Message Send Mock Preview",
        "",
        "- 本次为 mock，不会发送真实飞书消息。",
        "- 不会调用真实飞书消息 API。",
        f"- real_file_token_available：{str(plan['real_file_token_available']).lower()}",
        f"- using_mock_tokens_for_preview：{str(plan['using_mock_tokens_for_preview']).lower()}",
        "",
        "### 附件 Tokens",
        "",
    ]
    lines.extend(
        f"- {item['filename']}：{item['file_token']}（{item['token_source']}）"
        for item in plan["attachment_tokens"]
    )
    return "\n".join(lines) + "\n"


def build_mock_receipt(plan: dict[str, Any], preview_path: str | Path) -> dict[str, Any]:
    return {
        **plan,
        "message_preview_path": str(preview_path),
        "error": None,
    }


def write_outputs(
    plan: dict[str, Any],
    preview: str,
    output_dir: str | Path,
) -> tuple[dict[str, Path], dict[str, Any]]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "send_plan_json": output / "feishu_message_send_mock_plan.json",
        "message_preview_md": output / "feishu_message_send_mock_preview.md",
        "send_receipt_json": output / "feishu_message_send_mock_receipt.json",
    }
    paths["send_plan_json"].write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["message_preview_md"].write_text(preview, encoding="utf-8")
    receipt = build_mock_receipt(plan, paths["message_preview_md"])
    paths["send_receipt_json"].write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return paths, receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff-message", required=True)
    parser.add_argument("--upload-receipt", required=True)
    parser.add_argument("--mock-token-csv", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    message = load_handoff_message(args.handoff_message)
    plan = build_send_plan(
        message,
        load_upload_receipt(args.upload_receipt),
        load_mock_tokens(args.mock_token_csv),
    )
    preview = build_preview(message, plan)
    paths, receipt = write_outputs(plan, preview, args.output_dir)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    for label, path in paths.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()

