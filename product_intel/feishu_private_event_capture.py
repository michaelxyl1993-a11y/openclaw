"""Capture Feishu attachment callback events into gitignored private runtime files."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


SOURCE = "product_intel_feishu_callback"
PACKAGE_DIR = Path(__file__).resolve().parent
PRIVATE_RUNTIME_DIR = PACKAGE_DIR / "private_runtime"
LATEST_EVENT_PATH = PRIVATE_RUNTIME_DIR / "feishu_latest_attachment_event.json"
ARCHIVE_DIR = PRIVATE_RUNTIME_DIR / "feishu_events"
REDACTED_TOKEN = "REDACTED_FILE_TOKEN"


def _first_non_empty(item: dict[str, Any], fields: Sequence[str]) -> Any:
    for field in fields:
        value = item.get(field)
        if value not in (None, ""):
            return value
    return ""


def _parse_json_maybe(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""


def _event_message(payload: dict[str, Any]) -> dict[str, Any]:
    event = payload.get("event")
    if isinstance(event, dict) and isinstance(event.get("message"), dict):
        return event["message"]
    message = payload.get("message")
    return message if isinstance(message, dict) else {}


def extract_message_id(payload: dict[str, Any]) -> str:
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    message = _event_message(payload)
    return str(
        _first_non_empty(
            payload,
            ("message_id", "messageId"),
        )
        or _first_non_empty(event, ("message_id", "messageId"))
        or _first_non_empty(message, ("message_id", "messageId"))
    ).strip()


def extract_chat_id(payload: dict[str, Any]) -> str:
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    message = _event_message(payload)
    content = _parse_json_maybe(message.get("content"))
    return str(
        _first_non_empty(payload, ("chat_id",))
        or _first_non_empty(event, ("chat_id",))
        or _first_non_empty(message, ("chat_id",))
        or _first_non_empty(content, ("chat_id",))
    ).strip()


def _candidate_attachment_lists(payload: dict[str, Any]) -> list[Any]:
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    message = _event_message(payload)
    content = _parse_json_maybe(message.get("content"))
    candidates: list[Any] = [
        payload.get("attachments"),
        payload.get("files"),
        event.get("attachments") if isinstance(event, dict) else None,
        event.get("files") if isinstance(event, dict) else None,
        message.get("attachments"),
        message.get("files"),
        content.get("attachments"),
        content.get("files"),
    ]
    message_file = message.get("file")
    if isinstance(message_file, dict):
        candidates.append([message_file])
    file_fields = {
        "file_token": _first_non_empty(message, ("file_token", "file_key", "file_id"))
        or _first_non_empty(content, ("file_token", "file_key", "file_id", "key")),
        "filename": _first_non_empty(
            message,
            ("file_name", "filename", "name"),
        )
        or _first_non_empty(content, ("file_name", "filename", "name", "fileName")),
        "size_bytes": _first_non_empty(message, ("size_bytes", "size", "file_size"))
        or _first_non_empty(content, ("size_bytes", "size", "file_size")),
        "mime_type": _first_non_empty(message, ("mime_type", "mimetype"))
        or _first_non_empty(content, ("mime_type", "mimetype")),
    }
    if file_fields["file_token"] or file_fields["filename"]:
        candidates.append([file_fields])
    return candidates


def extract_attachment_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for candidate in _candidate_attachment_lists(payload):
        if not isinstance(candidate, list):
            continue
        for item in candidate:
            if isinstance(item, dict):
                items.append(item)
    return items


def normalize_attachment(item: dict[str, Any]) -> dict[str, Any]:
    token = str(_first_non_empty(item, ("file_token", "token", "file_key", "file_id", "key"))).strip()
    filename = str(
        _first_non_empty(
            item,
            ("filename", "file_name", "name", "fileName"),
        )
    ).strip()
    size_raw = _first_non_empty(item, ("size_bytes", "size", "file_size"))
    try:
        size_bytes = int(size_raw) if str(size_raw).strip() else 0
    except (TypeError, ValueError):
        size_bytes = 0
    mime_type = str(_first_non_empty(item, ("mime_type", "mimetype"))).strip()
    file_type = str(_first_non_empty(item, ("file_type", "type"))).strip()
    return {
        "filename": Path(filename).name if filename else "",
        "file_type": file_type or Path(filename).suffix.lower().lstrip("."),
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "file_token": token,
        "file_token_hash": _hash_text(token),
    }


def redacted_chat_id(chat_id: str) -> str:
    if not chat_id:
        return ""
    return "REDACTED_CHAT_ID"


def build_private_attachment_event(payload: dict[str, Any]) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat()
    message_id = extract_message_id(payload)
    chat_id = extract_chat_id(payload)
    raw_attachments = extract_attachment_items(payload)
    if not raw_attachments:
        return {
            "mode": "feishu_private_attachment_event_v1.21.3",
            "status": "no_attachments",
            "created_at": created_at,
            "source": SOURCE,
            "message_id": message_id,
            "chat_id_redacted": redacted_chat_id(chat_id),
            "chat_id_hash": _hash_text(chat_id),
            "attachments": [],
            "errors": ["no attachments found"],
        }

    attachments = [normalize_attachment(item) for item in raw_attachments]
    errors: list[str] = []
    if not message_id:
        errors.append("message_id missing")
    if any(not item["file_token"] for item in attachments):
        errors.append("file_token missing")
    if any(item["file_token"] == REDACTED_TOKEN for item in attachments):
        errors.append("file_token is redacted")

    status = "captured" if not errors else "blocked"
    return {
        "mode": "feishu_private_attachment_event_v1.21.3",
        "status": status,
        "created_at": created_at,
        "source": SOURCE,
        "message_id": message_id,
        "chat_id_redacted": redacted_chat_id(chat_id),
        "chat_id_hash": _hash_text(chat_id),
        "attachments": attachments,
        "attachment_count": len(attachments),
        "errors": errors,
    }


def _safe_archive_name(event: dict[str, Any]) -> str:
    created = str(event.get("created_at", "")).replace(":", "").replace("+", "Z")
    created = created.replace("-", "").replace(".", "_")
    message_hash = _hash_text(str(event.get("message_id", "")))[:12] or "missing"
    return f"{created}_{message_hash}_event.json"


def write_private_attachment_event(
    event: dict[str, Any],
    *,
    latest_path: Path = LATEST_EVENT_PATH,
    archive_dir: Path = ARCHIVE_DIR,
) -> dict[str, Any]:
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(event, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(text, encoding="utf-8")
    archive_path = archive_dir / _safe_archive_name(event)
    archive_path.write_text(text, encoding="utf-8")
    return {
        "status": event.get("status", ""),
        "attachment_count": event.get("attachment_count", 0),
        "message_id_hash": _hash_text(str(event.get("message_id", ""))),
        "file_token_hashes": [item.get("file_token_hash", "") for item in event.get("attachments", [])],
        "latest_path": str(latest_path),
        "archive_path": str(archive_path),
        "errors": event.get("errors", []),
    }


def capture_private_attachment_event(payload: dict[str, Any]) -> dict[str, Any]:
    event = build_private_attachment_event(payload)
    return write_private_attachment_event(event)
