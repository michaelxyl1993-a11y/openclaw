"""Build a private runtime token source for Feishu multi-attachment download."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Sequence


MODE = "feishu_runtime_token_source_v1.21.10"
PACKAGE_DIR = Path(__file__).resolve().parent
PRIVATE_RUNTIME_DIR = PACKAGE_DIR / "private_runtime"
DEFAULT_OUTPUT = PRIVATE_RUNTIME_DIR / "feishu_runtime_token_source.json"
REDACTED_TOKEN = "REDACTED_FILE_TOKEN"
FILE_TOKEN_FIELDS = ("file_key", "file_token", "token")
FILENAME_FIELDS = ("file_name", "filename", "name", "fileName")
SIZE_FIELDS = ("size_bytes", "size", "file_size")
MIME_FIELDS = ("mime_type", "mimetype")


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


def _file_candidate_from_dict(item: dict[str, Any]) -> dict[str, Any]:
    token = _first_non_empty(item, FILE_TOKEN_FIELDS)
    filename = _first_non_empty(item, FILENAME_FIELDS)
    if not token or not filename:
        return {}
    return {
        "file_token": token,
        "file_name": filename,
        "size_bytes": _first_non_empty(item, SIZE_FIELDS),
        "mime_type": _first_non_empty(item, MIME_FIELDS),
        "file_type": _first_non_empty(item, ("file_type", "type")),
    }


def _recursive_file_candidates(value: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if isinstance(value, dict):
        file_candidate = _file_candidate_from_dict(value)
        if file_candidate:
            candidates.append(file_candidate)
        for child in value.values():
            candidates.extend(_recursive_file_candidates(child))
    elif isinstance(value, list):
        for child in value:
            candidates.extend(_recursive_file_candidates(child))
    return candidates


def _dedupe_attachments(items: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        token = str(_first_non_empty(item, FILE_TOKEN_FIELDS)).strip()
        filename = str(_first_non_empty(item, FILENAME_FIELDS)).strip()
        key = (
            f"token:{hashlib.sha256(token.encode('utf-8')).hexdigest()}"
            if token
            else f"filename:{filename}"
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _value_at_path(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _event_message(payload: dict[str, Any]) -> dict[str, Any]:
    event = payload.get("event")
    if isinstance(event, dict) and isinstance(event.get("message"), dict):
        return event["message"]
    message = payload.get("message")
    return message if isinstance(message, dict) else {}


def _priority_message_paths() -> list[str]:
    return [
        "event.message.message_id",
        "event.message.open_message_id",
        "event.message.event_message_id",
        "message.message_id",
        "message.open_message_id",
        "open_message_id",
        "message_id",
    ]


def _candidate_message_ids(payload: dict[str, Any]) -> list[tuple[str, Any]]:
    candidates: list[tuple[str, Any]] = [
        (path, _value_at_path(payload, path)) for path in _priority_message_paths()
    ]
    return candidates


def _recursive_message_id_candidates(value: Any, path: str = "") -> list[tuple[str, Any]]:
    candidates: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if key in {"message_id", "open_message_id", "open_id"}:
                candidates.append((child_path, child))
            candidates.extend(_recursive_message_id_candidates(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            candidates.extend(_recursive_message_id_candidates(child, child_path))
    return candidates


def collect_message_id_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    candidates: list[dict[str, Any]] = []
    for source_path, value in [
        *_candidate_message_ids(payload),
        *_recursive_message_id_candidates(payload),
    ]:
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text:
            continue
        key = (source_path, text)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "path": source_path,
                "value": text,
                "startswith_om": text.startswith("om_"),
                "len": len(text),
                "hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        )
    return candidates


def sanitize_message_id_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": candidate["path"],
        "len": candidate["len"],
        "startswith_om": candidate["startswith_om"],
        "hash_prefix": str(candidate["hash"])[:16],
    }


def choose_message_id_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    om_candidates = [candidate for candidate in candidates if candidate["startswith_om"]]
    if not om_candidates:
        return None
    top_level_message = [
        candidate for candidate in om_candidates if candidate["path"] == "message_id"
    ]
    if len(om_candidates) == 1 and top_level_message:
        return top_level_message[0]
    for path in _priority_message_paths():
        if path == "message_id":
            continue
        for candidate in om_candidates:
            if candidate["path"] == path:
                return candidate
    for candidate in om_candidates:
        if candidate["path"] != "message_id":
            return candidate
    return top_level_message[0] if top_level_message else om_candidates[0]


def inspect_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = collect_message_id_candidates(payload)
    selected = choose_message_id_candidate(candidates)
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    event_message = event.get("message") if isinstance(event.get("message"), dict) else {}
    try:
        attachments = extract_attachments(payload)
        attachment_count = len(attachments)
    except RuntimeTokenSourceBuilderError:
        attachments = []
        attachment_count = 0
    return {
        "mode": MODE,
        "attachment_count": attachment_count,
        "raw_capture_source": str(payload.get("raw_capture_source", "")),
        "raw_event_detected": bool(payload.get("raw_event_detected"))
        or (isinstance(event_message, dict) and bool(event_message)),
        "has_header": isinstance(payload.get("header"), dict),
        "has_schema": bool(payload.get("schema")),
        "has_event": isinstance(event, dict) and bool(event),
        "has_event_message": isinstance(event_message, dict) and bool(event_message),
        "has_event_message_message_id": bool(
            str(event_message.get("message_id", "")).strip()
        )
        if isinstance(event_message, dict)
        else False,
        "has_event_message_open_message_id": bool(
            str(event_message.get("open_message_id", "")).strip()
        )
        if isinstance(event_message, dict)
        else False,
        "normalized_attachment_count": len(
            attachments
        ),
        "event_message_keys_count": len(event_message) if isinstance(event_message, dict) else 0,
        "event_message_keys_sample": sorted(list(event_message.keys()))[:20]
        if isinstance(event_message, dict)
        else [],
        "top_level_keys_sample": sorted(list(payload.keys()))[:20],
        "message_id_candidates_count": len(candidates),
        "message_id_candidate_sources": [
            sanitize_message_id_candidate(candidate) for candidate in candidates
        ],
        "recommended_message_id_source_path": selected["path"] if selected else "",
        "selected_message_id_source_path": selected["path"] if selected else "",
        "selected_message_id_len": selected["len"] if selected else 0,
        "selected_message_id_startswith_om": bool(selected and selected["startswith_om"]),
        "message_id_length_warning": bool(selected and selected["len"] < 20),
    }


def inspect_event_file(path: str | Path) -> dict[str, Any]:
    return inspect_event_payload(load_event(path))


def extract_message_id(payload: dict[str, Any]) -> tuple[str, str]:
    selected = choose_message_id_candidate(collect_message_id_candidates(payload))
    if selected:
        return str(selected["value"]), str(selected["path"])
    raise RuntimeTokenSourceBuilderError(
        "Feishu runtime token source blocked: open_message_id starting with om_ is required."
    )


def extract_attachments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Any] = [
        payload.get("attachments"),
        payload.get("files"),
        payload.get("normalized_attachments"),
    ]
    message = payload.get("message")
    if isinstance(message, dict):
        candidates.extend([message.get("attachments"), message.get("files")])
        content = _parse_json_maybe(message.get("content"))
        candidates.extend([content.get("attachments"), content.get("files")])
        content_files = _recursive_file_candidates(content)
        if content_files:
            candidates.append(content_files)
    event = payload.get("event")
    if isinstance(event, dict):
        candidates.extend([event.get("attachments"), event.get("files")])
        event_message = event.get("message")
        if isinstance(event_message, dict):
            candidates.extend(
                [event_message.get("attachments"), event_message.get("files")]
            )
            content = _parse_json_maybe(event_message.get("content"))
            candidates.extend([content.get("attachments"), content.get("files")])
            content_files = _recursive_file_candidates(content)
            if content_files:
                candidates.append(content_files)
    items: list[dict[str, Any]] = []
    for value in candidates:
        if isinstance(value, list) and value:
            if not all(isinstance(item, dict) for item in value):
                raise RuntimeTokenSourceBuilderError("attachments/files items must be objects.")
            items.extend(value)
    items.extend(_recursive_file_candidates(payload))
    deduped = _dedupe_attachments(items)
    if deduped:
        return deduped
    raise RuntimeTokenSourceBuilderError("event JSON must contain attachments or files.")


def _is_batch_payload(payload: dict[str, Any]) -> bool:
    mode = str(payload.get("mode", ""))
    return mode.startswith("feishu_attachment_event_batch_")


def _build_batch_runtime_token_source(payload: dict[str, Any]) -> dict[str, Any]:
    attachments = payload.get("attachments")
    if not isinstance(attachments, list) or not attachments:
        raise RuntimeTokenSourceBuilderError("batch JSON must contain attachments.")

    tokens_by_hash: dict[str, str] = {}
    download_context_by_file_hash: dict[str, dict[str, str]] = {}
    missing_count = 0
    redacted_count = 0
    invalid_message_count = 0
    first_message_id = ""
    first_message_source_path = ""

    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        token = str(_first_non_empty(attachment, ("file_token", "token", "file_key"))).strip()
        message_id = str(attachment.get("message_id", "")).strip()
        message_id_source_path = str(
            attachment.get("message_id_source_path", "")
        ).strip()
        if not token:
            missing_count += 1
            continue
        if token == REDACTED_TOKEN:
            redacted_count += 1
            continue
        if not message_id.startswith("om_"):
            invalid_message_count += 1
            continue
        token_hash = str(attachment.get("file_token_hash", "")).strip()
        if not token_hash:
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        tokens_by_hash[token_hash] = token
        download_context_by_file_hash[token_hash] = {
            "file_token": token,
            "message_id": message_id,
            "message_id_source_path": message_id_source_path,
            "source_event_path": str(attachment.get("source_event_path", "")).strip(),
        }
        if not first_message_id:
            first_message_id = message_id
            first_message_source_path = message_id_source_path

    if redacted_count:
        raise RuntimeTokenSourceBuilderError(
            "batch contains REDACTED_FILE_TOKEN; real file_token values are required."
        )
    if missing_count:
        raise RuntimeTokenSourceBuilderError(
            "batch contains attachments without file_token/token/file_key."
        )
    if invalid_message_count:
        raise RuntimeTokenSourceBuilderError(
            "batch contains attachments without open_message_id starting with om_."
        )
    if not tokens_by_hash:
        raise RuntimeTokenSourceBuilderError("batch contains no real attachment tokens.")

    return {
        "mode": MODE,
        "source_mode": str(payload.get("mode", "")),
        "message_id": first_message_id,
        "message_id_source_path": first_message_source_path,
        "message_id_candidates_count": 0,
        "message_id_candidate_sources": [],
        "message_id_length_warning": bool(first_message_id and len(first_message_id) < 20),
        "tokens_by_hash": tokens_by_hash,
        "download_context_by_file_hash": download_context_by_file_hash,
        "attachment_count": len(tokens_by_hash),
        "per_file_message_context_count": len(download_context_by_file_hash),
    }


def build_runtime_token_source(payload: dict[str, Any]) -> dict[str, Any]:
    if _is_batch_payload(payload):
        return _build_batch_runtime_token_source(payload)

    message_id, message_id_source_path = extract_message_id(payload)
    inspection = inspect_event_payload(payload)
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
        "message_id_source_path": message_id_source_path,
        "message_id_candidates_count": inspection["message_id_candidates_count"],
        "message_id_candidate_sources": inspection["message_id_candidate_sources"],
        "message_id_length_warning": len(message_id) < 20,
        "tokens_by_hash": tokens_by_hash,
        "attachment_count": len(tokens_by_hash),
        "per_file_message_context_count": 0,
        "download_context_by_file_hash": {},
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
    payload = load_event(event_json)
    source = build_runtime_token_source(payload)
    output_path = write_runtime_token_source(source, output)
    inspection = inspect_event_payload(payload) if not _is_batch_payload(payload) else {}
    contexts = source.get("download_context_by_file_hash")
    context_values = list(contexts.values()) if isinstance(contexts, dict) else []
    message_id_lens = sorted(
        {
            len(str(context.get("message_id", "")))
            for context in context_values
            if isinstance(context, dict)
        }
    )
    message_source_paths = sorted(
        {
            str(context.get("message_id_source_path", ""))
            for context in context_values
            if isinstance(context, dict) and context.get("message_id_source_path")
        }
    )
    return {
        "mode": MODE,
        "output_path": str(output_path),
        "attachment_count": source["attachment_count"],
        "token_source_count": len(source["tokens_by_hash"]),
        "per_file_message_context_count": source.get(
            "per_file_message_context_count", 0
        ),
        "message_id_present": bool(source["message_id"]),
        "message_id_looks_open": str(source["message_id"]).startswith("om_"),
        "message_id_len": len(str(source["message_id"])),
        "message_id_source_path": source["message_id_source_path"],
        "message_id_lens": message_id_lens or [len(str(source["message_id"]))],
        "message_id_source_paths": message_source_paths
        or ([source["message_id_source_path"]] if source["message_id_source_path"] else []),
        "message_id_candidates_count": source["message_id_candidates_count"],
        "message_id_candidate_sources": source["message_id_candidate_sources"],
        "message_id_length_warning": source["message_id_length_warning"],
        "raw_event_detected": inspection.get("raw_event_detected", False),
        "has_event_message": inspection.get("has_event_message", False),
        "has_event_message_message_id": inspection.get(
            "has_event_message_message_id", False
        ),
        "has_event_message_open_message_id": inspection.get(
            "has_event_message_open_message_id", False
        ),
        "normalized_attachment_count": inspection.get(
            "normalized_attachment_count", source["attachment_count"]
        ),
        "token_hashes": sorted(source["tokens_by_hash"]),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-json")
    parser.add_argument("--inspect-event")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.inspect_event:
        print(json.dumps(inspect_event_file(args.inspect_event), ensure_ascii=False, indent=2))
        return 0
    if not args.event_json:
        raise RuntimeTokenSourceBuilderError("--event-json is required unless --inspect-event is used.")
    summary = build_from_event_file(args.event_json, args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
