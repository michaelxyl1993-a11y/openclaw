"""Opt-in single-file real Feishu upload adapter. This module never sends messages."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .feishu_product_intel_bot import infer_feishu_file_type


MODE = "feishu_upload_adapter_real_v1.15"
REAL_UPLOAD_ENABLED_ENV = "PRODUCT_INTEL_REAL_FEISHU_UPLOAD_ENABLED"
APP_ID_ENV = "FEISHU_APP_ID"
APP_SECRET_ENV = "FEISHU_APP_SECRET"
RECEIPT_FILENAME = "feishu_real_upload_single_receipt.json"


def is_real_upload_enabled(environ: Mapping[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    return env.get(REAL_UPLOAD_ENABLED_ENV, "").strip().lower() == "true"


def load_dry_run_plan(path: str | Path) -> dict[str, Any]:
    plan_path = Path(path)
    if not plan_path.exists():
        raise ValueError(f"Feishu real upload blocked: dry-run plan does not exist: {plan_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise ValueError("Feishu real upload blocked: dry-run plan must be an object.")
    if plan.get("ready_for_upload") is not True:
        raise ValueError("Feishu real upload blocked: dry-run plan is not ready_for_upload.")
    if not isinstance(plan.get("attachment_items"), list):
        raise ValueError("Feishu real upload blocked: attachment_items must be a list.")
    return plan


def select_attachment(plan: dict[str, Any], attachment_index: int) -> dict[str, Any]:
    items = plan["attachment_items"]
    if attachment_index < 0 or attachment_index >= len(items):
        raise ValueError(
            f"Feishu real upload blocked: attachment-index {attachment_index} is out of range."
        )
    item = items[attachment_index]
    if not isinstance(item, dict):
        raise ValueError("Feishu real upload blocked: attachment item must be an object.")
    path = Path(str(item.get("path", "")))
    if not path.exists() or not path.is_file():
        raise ValueError(f"Feishu real upload blocked: attachment does not exist: {path}")
    if path.stat().st_size <= 0:
        raise ValueError(f"Feishu real upload blocked: attachment is empty: {path}")
    return {**item, "path": str(path), "size_bytes": path.stat().st_size}


def sanitize_error(error: Exception | str, secrets: list[str]) -> str:
    text = str(error)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def base_receipt(
    attachment: dict[str, Any],
    attachment_index: int,
    *,
    real_upload_enabled: bool,
) -> dict[str, Any]:
    return {
        "mode": MODE,
        "real_upload_enabled": real_upload_enabled,
        "real_feishu_api_called": False,
        "real_message_sent": False,
        "attachment_index": attachment_index,
        "filename": str(attachment.get("filename") or Path(attachment["path"]).name),
        "path": str(attachment["path"]),
        "size_bytes": int(attachment["size_bytes"]),
        "upload_status": "disabled",
        "file_token": None,
        "error": None,
    }


class FeishuSingleFileUploadClient:
    """Minimal Feishu client for token retrieval and one file upload only."""

    def upload_file(
        self,
        *,
        app_id: str,
        app_secret: str,
        path: str,
        filename: str,
        file_type: str,
    ) -> str:
        import requests

        token_response = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=(5, 20),
        )
        token_data = token_response.json()
        if not (200 <= token_response.status_code < 300) or token_data.get("code", 0) != 0:
            raise RuntimeError("failed to get Feishu tenant access token.")
        token = str(token_data.get("tenant_access_token") or "")
        if not token:
            raise RuntimeError("failed to get Feishu tenant access token: empty token.")

        with Path(path).open("rb") as file_obj:
            upload_response = requests.post(
                "https://open.feishu.cn/open-apis/im/v1/files",
                headers={"Authorization": f"Bearer {token}"},
                data={"file_type": file_type, "file_name": filename},
                files={"file": (filename, file_obj)},
                timeout=(5, 60),
            )
        upload_data = upload_response.json()
        if not (200 <= upload_response.status_code < 300) or upload_data.get("code", 0) != 0:
            raise RuntimeError("Feishu single-file upload failed.")
        file_token = str((upload_data.get("data") or {}).get("file_key") or "")
        if not file_token:
            raise RuntimeError("Feishu single-file upload failed: empty file token.")
        return file_token


def run_single_upload(
    plan: dict[str, Any],
    attachment_index: int,
    *,
    environ: Mapping[str, str] | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    env = environ if environ is not None else os.environ
    attachment = select_attachment(plan, attachment_index)
    enabled = is_real_upload_enabled(env)
    receipt = base_receipt(attachment, attachment_index, real_upload_enabled=enabled)
    if not enabled:
        return receipt

    app_id = env.get(APP_ID_ENV, "").strip()
    app_secret = env.get(APP_SECRET_ENV, "").strip()
    if not app_id or not app_secret:
        receipt.update(
            {
                "upload_status": "error",
                "error": f"{APP_ID_ENV} and {APP_SECRET_ENV} are required for real upload.",
            }
        )
        return receipt

    uploader = client or FeishuSingleFileUploadClient()
    try:
        receipt["real_feishu_api_called"] = True
        receipt["file_token"] = uploader.upload_file(
            app_id=app_id,
            app_secret=app_secret,
            path=receipt["path"],
            filename=receipt["filename"],
            file_type=infer_feishu_file_type(receipt["path"]),
        )
        receipt["upload_status"] = "uploaded"
    except Exception as exc:
        receipt["upload_status"] = "error"
        receipt["error"] = sanitize_error(exc, [app_id, app_secret])
    return receipt


def write_receipt(receipt: dict[str, Any], output_dir: str | Path) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / RECEIPT_FILENAME
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run-plan", required=True)
    parser.add_argument("--attachment-index", required=True, type=int)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    receipt = run_single_upload(load_dry_run_plan(args.dry_run_plan), args.attachment_index)
    path = write_receipt(receipt, args.output_dir)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    print(f"receipt_json: {path}")


if __name__ == "__main__":
    main()

