"""Opt-in single text-message Feishu send adapter. Disabled by default."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping


MODE = "feishu_message_send_adapter_real_v1.17"
REAL_SEND_ENABLED_ENV = "PRODUCT_INTEL_REAL_FEISHU_MESSAGE_SEND_ENABLED"
CHAT_ID_ENV = "PRODUCT_INTEL_FEISHU_TEST_CHAT_ID"
APP_ID_ENV = "FEISHU_APP_ID"
APP_SECRET_ENV = "FEISHU_APP_SECRET"
RECEIPT_FILENAME = "feishu_message_send_real_receipt.json"


def is_real_send_enabled(environ: Mapping[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    return env.get(REAL_SEND_ENABLED_ENV, "").strip().lower() == "true"


def redact_identifier(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) <= 8:
        return f"{text[:2]}...{text[-2:]}"
    return f"{text[:5]}...{text[-3:]}"


def load_message_preview(path: str | Path) -> str:
    preview_path = Path(path)
    if not preview_path.exists():
        raise ValueError(f"Feishu real message send blocked: preview does not exist: {preview_path}")
    message = preview_path.read_text(encoding="utf-8")
    if not message.strip():
        raise ValueError("Feishu real message send blocked: preview is empty.")
    return message


def load_mock_plan(path: str | Path) -> dict[str, Any]:
    plan_path = Path(path)
    if not plan_path.exists():
        raise ValueError(f"Feishu real message send blocked: mock plan does not exist: {plan_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise ValueError("Feishu real message send blocked: mock plan must be an object.")
    if plan.get("real_feishu_message_api_called") is not False:
        raise ValueError("Feishu real message send blocked: mock plan API-called flag must be false.")
    if plan.get("real_message_sent") is not False:
        raise ValueError("Feishu real message send blocked: mock plan sent flag must be false.")
    return plan


def sanitize_error(error: Exception | str, sensitive_values: list[str]) -> str:
    text = str(error)
    for value in sensitive_values:
        if value:
            text = text.replace(value, "[REDACTED]")
    return text


def base_receipt(
    *,
    enabled: bool,
    chat_id: str,
    preview_path: str | Path,
    message: str,
) -> dict[str, Any]:
    return {
        "mode": MODE,
        "real_send_enabled": enabled,
        "real_feishu_message_api_called": False,
        "real_message_sent": False,
        "send_status": "disabled",
        "target_type": "chat_id",
        "chat_id_provided": bool(chat_id),
        "chat_id_redacted": redact_identifier(chat_id),
        "message_preview_path": str(preview_path),
        "message_length": len(message),
        "attachment_send_enabled": False,
        "attachments_sent": 0,
        "message_id": None,
        "error": None,
    }


class FeishuSingleTextMessageClient:
    """Minimal client for one text message. It never sends attachments."""

    def send_text(
        self,
        *,
        app_id: str,
        app_secret: str,
        chat_id: str,
        text: str,
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

        send_response = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            params={"receive_id_type": "chat_id"},
            json={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            timeout=(5, 20),
        )
        send_data = send_response.json()
        if not (200 <= send_response.status_code < 300) or send_data.get("code", 0) != 0:
            raise RuntimeError("Feishu single text-message send failed.")
        message_id = str((send_data.get("data") or {}).get("message_id") or "")
        if not message_id:
            raise RuntimeError("Feishu single text-message send failed: empty message id.")
        return message_id


def run_single_text_send(
    message: str,
    mock_plan: dict[str, Any],
    *,
    preview_path: str | Path,
    chat_id: str | None = None,
    environ: Mapping[str, str] | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    if mock_plan.get("real_feishu_message_api_called") is not False:
        raise ValueError("Feishu real message send blocked: mock plan API-called flag must be false.")
    if mock_plan.get("real_message_sent") is not False:
        raise ValueError("Feishu real message send blocked: mock plan sent flag must be false.")
    if not message.strip():
        raise ValueError("Feishu real message send blocked: preview is empty.")

    env = environ if environ is not None else os.environ
    resolved_chat_id = str(chat_id or env.get(CHAT_ID_ENV, "")).strip()
    enabled = is_real_send_enabled(env)
    receipt = base_receipt(
        enabled=enabled,
        chat_id=resolved_chat_id,
        preview_path=preview_path,
        message=message,
    )
    if not enabled:
        return receipt
    if not resolved_chat_id:
        receipt.update({"send_status": "error", "error": "A test chat_id is required for real send."})
        return receipt

    app_id = env.get(APP_ID_ENV, "").strip()
    app_secret = env.get(APP_SECRET_ENV, "").strip()
    if not app_id or not app_secret:
        receipt.update(
            {
                "send_status": "error",
                "error": f"{APP_ID_ENV} and {APP_SECRET_ENV} are required for real send.",
            }
        )
        return receipt

    sender = client or FeishuSingleTextMessageClient()
    try:
        receipt["real_feishu_message_api_called"] = True
        message_id = sender.send_text(
            app_id=app_id,
            app_secret=app_secret,
            chat_id=resolved_chat_id,
            text=message,
        )
        if not message_id:
            raise RuntimeError("Feishu single text-message send failed: empty message id.")
        receipt.update(
            {
                "real_message_sent": True,
                "send_status": "sent",
                "message_id": "REDACTED_MESSAGE_ID",
            }
        )
    except Exception as exc:
        receipt.update(
            {
                "send_status": "error",
                "error": sanitize_error(exc, [app_id, app_secret, resolved_chat_id]),
            }
        )
    return receipt


def write_receipt(receipt: dict[str, Any], output_dir: str | Path) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / RECEIPT_FILENAME
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--message-preview", required=True)
    parser.add_argument("--mock-plan", required=True)
    parser.add_argument("--chat-id")
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    message = load_message_preview(args.message_preview)
    receipt = run_single_text_send(
        message,
        load_mock_plan(args.mock_plan),
        preview_path=args.message_preview,
        chat_id=args.chat_id,
    )
    path = write_receipt(receipt, args.output_dir)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    print(f"receipt_json: {path}")


if __name__ == "__main__":
    main()

