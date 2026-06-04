"""Opt-in real Feishu file-message sender for uploaded final ops attachments."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from .feishu_message_send_adapter_real import (
    APP_ID_ENV,
    APP_SECRET_ENV,
    redact_identifier,
    sanitize_error,
)
from .feishu_runtime_token_source_builder import PRIVATE_RUNTIME_DIR


MODE = "feishu_final_attachment_file_send_real_v1.26"
REAL_FILE_SEND_ENABLED_ENV = "PRODUCT_INTEL_REAL_FEISHU_FILE_SEND_ENABLED"
CHAT_ID_ENV = "PRODUCT_INTEL_FEISHU_TEST_CHAT_ID"
DEFAULT_SECURE_RECEIPT = PRIVATE_RUNTIME_DIR / "feishu_final_attachment_upload_secure_receipt.json"
RECEIPT_FILENAME = "feishu_final_attachment_file_send_receipt.json"
SUMMARY_FILENAME = "feishu_final_attachment_file_send_summary.json"


class FeishuFinalAttachmentFileSendError(ValueError):
    """Raised when uploaded files cannot be sent as file messages."""


def is_real_file_send_enabled(environ: Mapping[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    return env.get(REAL_FILE_SEND_ENABLED_ENV, "").strip().lower() == "true"


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_upload_receipt(path: str | Path) -> dict[str, Any]:
    receipt_path = Path(path)
    if not receipt_path.exists():
        raise FeishuFinalAttachmentFileSendError(
            f"file send blocked: upload receipt does not exist: {receipt_path}"
        )
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("uploaded_files"), list):
        raise FeishuFinalAttachmentFileSendError(
            "file send blocked: upload receipt must contain uploaded_files."
        )
    return payload


def load_secure_upload_receipt(path: str | Path) -> dict[str, Any]:
    secure_path = Path(path)
    if not secure_path.exists():
        return {"uploaded_files": []}
    payload = json.loads(secure_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("uploaded_files"), list):
        raise FeishuFinalAttachmentFileSendError(
            "file send blocked: secure upload receipt must contain uploaded_files."
        )
    return payload


def _secure_token_index(secure_receipt: dict[str, Any]) -> dict[str, str]:
    indexed: dict[str, str] = {}
    for item in secure_receipt.get("uploaded_files", []):
        if not isinstance(item, dict):
            continue
        token = str(item.get("file_token", "")).strip()
        token_hash = str(item.get("file_token_hash", "")).strip()
        if token and not token_hash:
            token_hash = _hash_text(token)
        if token and token_hash:
            indexed[token_hash] = token
    return indexed


def uploaded_file_items(
    public_receipt: dict[str, Any],
    secure_receipt: dict[str, Any],
) -> tuple[list[dict[str, Any]], bool]:
    token_index = _secure_token_index(secure_receipt)
    items: list[dict[str, Any]] = []
    missing_raw_token = False
    for item in public_receipt.get("uploaded_files", []):
        if not isinstance(item, dict) or item.get("upload_status") != "uploaded":
            continue
        token_hash = str(item.get("file_token_hash", "")).strip()
        token = str(item.get("file_token", "") or "").strip()
        if not token and token_hash:
            token = token_index.get(token_hash, "")
        if not token:
            missing_raw_token = True
        items.append(
            {
                "filename": str(item.get("filename", "")),
                "size_bytes": int(item.get("size_bytes", 0) or 0),
                "file_token": token,
                "file_token_hash": token_hash or (_hash_text(token) if token else ""),
            }
        )
    return items, missing_raw_token


class FeishuFileMessageClient:
    """Minimal client for sending existing Feishu file keys as file messages."""

    def send_file(
        self,
        *,
        app_id: str,
        app_secret: str,
        chat_id: str,
        file_token: str,
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
        tenant_token = str(token_data.get("tenant_access_token") or "")
        if not tenant_token:
            raise RuntimeError("failed to get Feishu tenant access token: empty token.")

        response = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            headers={
                "Authorization": f"Bearer {tenant_token}",
                "Content-Type": "application/json",
            },
            params={"receive_id_type": "chat_id"},
            json={
                "receive_id": chat_id,
                "msg_type": "file",
                "content": json.dumps({"file_key": file_token}, ensure_ascii=False),
            },
            timeout=(5, 20),
        )
        payload = response.json()
        if not (200 <= response.status_code < 300) or payload.get("code", 0) != 0:
            raise RuntimeError("Feishu file-message send failed.")
        message_id = str((payload.get("data") or {}).get("message_id") or "")
        if not message_id:
            raise RuntimeError("Feishu file-message send failed: empty message id.")
        return message_id


def _base_sent_file(item: dict[str, Any], status: str) -> dict[str, Any]:
    return {
        "filename": str(item.get("filename", "")),
        "file_token_hash": str(item.get("file_token_hash", "")),
        "send_status": status,
        "message_id_redacted": None,
        "error": None,
    }


def run_file_message_send(
    public_receipt: dict[str, Any],
    secure_receipt: dict[str, Any],
    *,
    chat_id: str | None = None,
    environ: Mapping[str, str] | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    env = environ if environ is not None else os.environ
    enabled = is_real_file_send_enabled(env)
    resolved_chat_id = str(chat_id or env.get(CHAT_ID_ENV, "")).strip()
    files, missing_raw_token = uploaded_file_items(public_receipt, secure_receipt)
    receipt = {
        "mode": MODE,
        "real_file_send_enabled": enabled,
        "real_feishu_api_called": False,
        "file_message_send_supported": not missing_raw_token and bool(files),
        "attempted_file_send_count": 0,
        "success_count": 0,
        "error_count": 0,
        "sent_files": [_base_sent_file(item, "disabled") for item in files],
        "all_files_sent": False,
        "ready_for_final_delivery": False,
        "required_next_action": "",
        "error": None,
    }
    if not files:
        receipt.update(
            {
                "file_message_send_supported": False,
                "error": "No uploaded files are available for file-message send.",
                "required_next_action": "upload_final_attachments_first",
            }
        )
        return receipt
    if missing_raw_token:
        receipt.update(
            {
                "file_message_send_supported": False,
                "error": "Raw file_token is unavailable; rerun final attachment upload to generate private secure receipt.",
                "required_next_action": "rerun_v1_25_upload_to_create_private_secure_receipt",
            }
        )
        return receipt
    if not enabled:
        return receipt
    if not resolved_chat_id:
        receipt.update(
            {
                "error": "A test chat_id is required for real file send.",
                "sent_files": [_base_sent_file(item, "error") for item in files],
                "error_count": len(files),
            }
        )
        return receipt
    app_id = env.get(APP_ID_ENV, "").strip()
    app_secret = env.get(APP_SECRET_ENV, "").strip()
    if not app_id or not app_secret:
        receipt.update(
            {
                "error": f"{APP_ID_ENV} and {APP_SECRET_ENV} are required for real file send.",
                "sent_files": [_base_sent_file(item, "error") for item in files],
                "error_count": len(files),
            }
        )
        return receipt

    sender = client or FeishuFileMessageClient()
    results: list[dict[str, Any]] = []
    for item in files:
        result = _base_sent_file(item, "error")
        receipt["attempted_file_send_count"] += 1
        try:
            receipt["real_feishu_api_called"] = True
            message_id = sender.send_file(
                app_id=app_id,
                app_secret=app_secret,
                chat_id=resolved_chat_id,
                file_token=item["file_token"],
            )
            result.update(
                {
                    "send_status": "sent",
                    "message_id_redacted": redact_identifier(message_id),
                    "error": None,
                }
            )
        except Exception as exc:
            result["error"] = sanitize_error(
                exc, [app_id, app_secret, resolved_chat_id, item["file_token"]]
            )
        results.append(result)

    receipt["sent_files"] = results
    counts = Counter(item["send_status"] for item in results)
    receipt["success_count"] = counts.get("sent", 0)
    receipt["error_count"] = counts.get("error", 0)
    receipt["all_files_sent"] = receipt["success_count"] == len(results)
    receipt["ready_for_final_delivery"] = receipt["all_files_sent"]
    return receipt


def build_summary(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": MODE,
        "real_file_send_enabled": receipt["real_file_send_enabled"],
        "real_feishu_api_called": receipt["real_feishu_api_called"],
        "file_message_send_supported": receipt["file_message_send_supported"],
        "attempted_file_send_count": receipt["attempted_file_send_count"],
        "success_count": receipt["success_count"],
        "error_count": receipt["error_count"],
        "all_files_sent": receipt["all_files_sent"],
        "ready_for_final_delivery": receipt["ready_for_final_delivery"],
        "required_next_action": receipt["required_next_action"],
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
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["summary_json"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upload-receipt", required=True)
    parser.add_argument("--secure-upload-receipt", default=str(DEFAULT_SECURE_RECEIPT))
    parser.add_argument("--chat-id")
    parser.add_argument("--output-dir", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    receipt = run_file_message_send(
        load_upload_receipt(args.upload_receipt),
        load_secure_upload_receipt(args.secure_upload_receipt),
        chat_id=args.chat_id,
    )
    paths = write_outputs(receipt, args.output_dir)
    print(json.dumps(build_summary(receipt), ensure_ascii=False, indent=2))
    for label, path in paths.items():
        print(f"{label}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
