"""Build a private runtime token source for Feishu multi-attachment download."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Sequence


MODE = "feishu_runtime_token_source_v1.21.2"
PACKAGE_DIR = Path(__file__).resolve().parent
PRIVATE_RUNTIME_DIR = PACKAGE_DIR / "private_runtime"
DEFAULT_OUTPUT = PRIVATE_RUNTIME_DIR / "feishu_runtime_token_source.json"
REDACTED_TOKEN = "REDACTED_FILE_TOKEN"


class RuntimeTokenSourceBuilderError(ValueError):
    """Raised when a callback event cannot produce a usable runtime source."""


def _first_non_empty(item: dict[str, Any], fields: Sequence[str]) -> Any:
    for field in fields:
        value = item.get(field)
        if value not in (None, ""):
            return value
    return ""


def load_event(path: str | Path) -> dict[str, Any]:
    event_path = Path(path)
    if not event_path.exists():
        raise RuntimeTokenSourceBuilderError(f"event JSON does not exist: {event_path}")
    payload = json.loads(event_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeTokenSourceBuilderError("event JSON must be an object.")
    return payload


def extract_message_id(payload: dict[str, Any]) -> str:
    candidates = [
        payload.get("message_id"),
        (payload.get("message") or {}).get("message_id")
        if isinstance(payload.get("message"), dict)
        else "",
        (payload.get("event") or {}).get("message_id")
        if isinstance(payload.get("event"), dict)
        else "",
    ]
    event = payload.get("event")
    if isinstance(event, dict) and isinstance(event.get("message"), dict):
        candidates.append(event["message"].get("message_id"))
    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text
    raise RuntimeTokenSourceBuilderError(
        "runtime token source requires message_id in message_id, event.message_id, or event.message.message_id."
    )


def extract_attachments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Any] = [payload.get("attachments"), payload.get("files")]
    message = payload.get("message")
    if isinstance(message, dict):
        candidates.extend([message.get("attachments"), message.get("files")])
    event = payload.get("event")
    if isinstance(event, dict):
        candidates.extend([event.get("attachments"), event.get("files")])
        event_message = event.get("message")
        if isinstance(event_message, dict):
            candidates.extend(
                [event_message.get("attachments"), event_message.get("files")]
            )
    for value in candidates:
        if isinstance(value, list) and value:
            if not all(isinstance(item, dict) for item in value):
                raise RuntimeTokenSourceBuilderError("attachments/files items must be objects.")
            return value
    raise RuntimeTokenSourceBuilderError("event JSON must contain attachments or files.")


def build_runtime_token_source(payload: dict[str, Any]) -> dict[str, Any]:
    message_id = extract_message_id(payload)
    attachments = extract_attachments(payload)
    tokens_by_hash: dict[str, str] = {}
    redacted_count = 0
    missing_count = 0
    for attachment in attachments:
        token = str(_first_non_empty(attachment, ("file_token", "token", "file_key"))).strip()
        if not token:
            missing_count += 1
            continue
        if token == REDACTED_TOKEN:
            redacted_count += 1
            continue
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        tokens_by_hash[token_hash] = token

    if redacted_count:
        raise RuntimeTokenSourceBuilderError(
            "event contains REDACTED_FILE_TOKEN; a real file_token is required."
        )
    if missing_count:
        raise RuntimeTokenSourceBuilderError(
            "event contains attachments without file_token/token/file_key."
        )
    if not tokens_by_hash:
        raise RuntimeTokenSourceBuilderError("event contains no real attachment tokens.")

    return {
        "mode": MODE,
        "message_id": message_id,
        "tokens_by_hash": tokens_by_hash,
        "attachment_count": len(tokens_by_hash),
    }


def _ensure_private_runtime_path(path: str | Path) -> Path:
    output = Path(path)
    if not output.is_absolute():
        output = Path.cwd() / output
    output = output.resolve()
    private_root = PRIVATE_RUNTIME_DIR.resolve()
    if not str(output).startswith(str(private_root) + os.sep):
        raise RuntimeTokenSourceBuilderError(
            f"runtime token source must be written under {PRIVATE_RUNTIME_DIR}"
        )
    return output


def write_runtime_token_source(source: dict[str, Any], output: str | Path) -> Path:
    output_path = _ensure_private_runtime_path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(source, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(output_path, 0o600)
    return output_path


def build_from_event_file(event_json: str | Path, output: str | Path) -> dict[str, Any]:
    source = build_runtime_token_source(load_event(event_json))
    output_path = write_runtime_token_source(source, output)
    return {
        "mode": MODE,
        "output_path": str(output_path),
        "attachment_count": source["attachment_count"],
        "token_hashes": sorted(source["tokens_by_hash"]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-json", required=True)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = build_from_event_file(args.event_json, args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
