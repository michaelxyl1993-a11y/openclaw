"""Opt-in real upload for final Product Intel operations attachments."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .feishu_product_intel_bot import infer_feishu_file_type
from .feishu_upload_adapter_real import (
    APP_ID_ENV,
    APP_SECRET_ENV,
    FeishuSingleFileUploadClient,
    REAL_UPLOAD_ENABLED_ENV,
    is_real_upload_enabled,
    sanitize_error,
)


MODE = "feishu_final_attachment_upload_real_v1.25"
RECEIPT_FILENAME = "feishu_final_attachment_upload_receipt.json"
SUMMARY_FILENAME = "feishu_final_attachment_upload_summary.json"


class FeishuFinalAttachmentUploadError(ValueError):
    """Raised when final attachment upload plan is invalid."""


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def load_upload_plan(path: str | Path) -> dict[str, Any]:
    plan_path = Path(path)
    if not plan_path.exists():
        raise FeishuFinalAttachmentUploadError(
            f"final attachment upload blocked: upload plan does not exist: {plan_path}"
        )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise FeishuFinalAttachmentUploadError(
            "final attachment upload blocked: upload plan must be an object."
        )
    if not isinstance(plan.get("attachment_items"), list):
        raise FeishuFinalAttachmentUploadError(
            "final attachment upload blocked: attachment_items must be a list."
        )
    return plan


def _valid_attachment(item: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(item.get("path", "")))
    if not path.exists() or not path.is_file():
        raise FeishuFinalAttachmentUploadError(f"attachment does not exist: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise FeishuFinalAttachmentUploadError(f"attachment is empty: {path}")
    return {
        "filename": str(item.get("filename") or path.name),
        "path": str(path),
        "size_bytes": size,
        "file_type": str(item.get("file_type") or infer_feishu_file_type(str(path))),
    }


def _base_file_result(item: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "filename": str(item.get("filename", "")),
        "path": str(item.get("path", "")),
        "size_bytes": int(item.get("size_bytes", 0) or 0),
        "upload_status": status,
        "file_token_redacted": "REDACTED_FILE_TOKEN",
        "file_token_hash": "",
        "error": None,
    }


def run_final_attachment_upload(
    plan: dict[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    import os

    env = environ if environ is not None else os.environ
    enabled = is_real_upload_enabled(env)
    raw_items = [item for item in plan.get("attachment_items", []) if isinstance(item, dict)]
    attachments = [_valid_attachment(item) for item in raw_items]
    receipt = {
        "mode": MODE,
        "real_upload_enabled": enabled,
        "real_feishu_api_called": False,
        "upload_status": "disabled" if not enabled else "pending",
        "attachment_count": len(attachments),
        "attempted_upload_count": 0,
        "success_count": 0,
        "error_count": 0,
        "uploaded_files": [_base_file_result(item, "disabled") for item in attachments],
        "ready_for_attachment_message": False,
        "next_command": "",
        "error": None,
    }
    if not attachments:
        receipt.update({"upload_status": "error", "error_count": 0, "error": "no attachments"})
        return receipt
    if not enabled:
        return receipt

    app_id = env.get(APP_ID_ENV, "").strip()
    app_secret = env.get(APP_SECRET_ENV, "").strip()
    if not app_id or not app_secret:
        receipt.update(
            {
                "upload_status": "error",
                "error_count": len(attachments),
                "uploaded_files": [_base_file_result(item, "error") for item in attachments],
                "error": f"{APP_ID_ENV} and {APP_SECRET_ENV} are required for real upload.",
            }
        )
        return receipt

    uploader = client or FeishuSingleFileUploadClient()
    results: list[dict[str, Any]] = []
    for item in attachments:
        result = _base_file_result(item, "error")
        receipt["attempted_upload_count"] += 1
        try:
            receipt["real_feishu_api_called"] = True
            token = uploader.upload_file(
                app_id=app_id,
                app_secret=app_secret,
                path=item["path"],
                filename=item["filename"],
                file_type=item["file_type"],
            )
            result.update(
                {
                    "upload_status": "uploaded",
                    "file_token_redacted": "REDACTED_FILE_TOKEN",
                    "file_token_hash": _hash_token(str(token)),
                    "error": None,
                }
            )
        except Exception as exc:
            result["error"] = sanitize_error(exc, [app_id, app_secret])
        results.append(result)

    receipt["uploaded_files"] = results
    receipt["success_count"] = sum(item["upload_status"] == "uploaded" for item in results)
    receipt["error_count"] = sum(item["upload_status"] == "error" for item in results)
    if receipt["success_count"] == len(results):
        receipt["upload_status"] = "uploaded"
    elif receipt["success_count"] > 0:
        receipt["upload_status"] = "partial"
    else:
        receipt["upload_status"] = "error"
    receipt["ready_for_attachment_message"] = receipt["success_count"] == len(results)
    if receipt["ready_for_attachment_message"]:
        receipt["next_command"] = (
            "python3 -m product_intel.feishu_message_send_adapter_real "
            "--message-preview product_intel/output_feishu_llm_ops/feishu_final_attachment_message_preview.md "
            "--mock-plan product_intel/output_feishu_llm_ops/feishu_final_attachment_upload_plan.json "
            "--chat-id \"$PRODUCT_INTEL_FEISHU_TEST_CHAT_ID\" "
            "--output-dir product_intel/output_feishu_llm_ops"
        )
    return receipt


def build_summary(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": MODE,
        "real_upload_enabled": receipt["real_upload_enabled"],
        "real_feishu_api_called": receipt["real_feishu_api_called"],
        "upload_status": receipt["upload_status"],
        "attachment_count": receipt["attachment_count"],
        "attempted_upload_count": receipt["attempted_upload_count"],
        "success_count": receipt["success_count"],
        "error_count": receipt["error_count"],
        "ready_for_attachment_message": receipt["ready_for_attachment_message"],
        "next_command": receipt["next_command"],
        "error": receipt["error"],
    }


def write_outputs(receipt: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    summary = build_summary(receipt)
    paths = {
        "receipt_json": output / RECEIPT_FILENAME,
        "summary_json": output / SUMMARY_FILENAME,
    }
    paths["receipt_json"].write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    paths["summary_json"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upload-plan", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    receipt = run_final_attachment_upload(load_upload_plan(args.upload_plan))
    paths = write_outputs(receipt, args.output_dir)
    print(json.dumps(build_summary(receipt), ensure_ascii=False, indent=2))
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
