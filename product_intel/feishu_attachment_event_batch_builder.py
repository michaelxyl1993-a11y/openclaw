"""Build a private batch from multiple valid Feishu raw attachment events."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .feishu_callback_capture_verifier import verify_capture_event
from .feishu_runtime_token_source_builder import (
    PRIVATE_RUNTIME_DIR,
    extract_attachments,
    extract_message_id,
)


MODE = "feishu_attachment_event_batch_v1.21.12"
DEFAULT_EVENTS_DIR = PRIVATE_RUNTIME_DIR / "feishu_events"
DEFAULT_OUTPUT = PRIVATE_RUNTIME_DIR / "feishu_latest_attachment_batch.json"


class FeishuAttachmentEventBatchBuilderError(ValueError):
    """Raised when raw Feishu events cannot produce a download-ready batch."""


def _hash_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _hash_prefix(value: str) -> str:
    return _hash_text(value)[:16] if value else ""


def _first_non_empty(item: dict[str, Any], fields: Sequence[str]) -> Any:
    for field in fields:
        value = item.get(field)
        if value not in (None, ""):
            return value
    return ""


def _event_message(payload: dict[str, Any]) -> dict[str, Any]:
    event = payload.get("event")
    if isinstance(event, dict) and isinstance(event.get("message"), dict):
        return event["message"]
    message = payload.get("message")
    return message if isinstance(message, dict) else {}


def _sender_id(payload: dict[str, Any]) -> str:
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    sender = event.get("sender") if isinstance(event.get("sender"), dict) else {}
    sender_id = sender.get("sender_id") if isinstance(sender.get("sender_id"), dict) else {}
    return str(
        _first_non_empty(sender_id, ("open_id", "user_id", "union_id"))
        or _first_non_empty(sender, ("open_id", "user_id", "union_id"))
    ).strip()


def _chat_id(payload: dict[str, Any]) -> str:
    message = _event_message(payload)
    return str(message.get("chat_id", "")).strip()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FeishuAttachmentEventBatchBuilderError(f"event must be an object: {path}")
    return payload


def _recent_event_paths(events_dir: str | Path, lookback_seconds: int) -> list[Path]:
    root = Path(events_dir)
    if not root.exists():
        raise FeishuAttachmentEventBatchBuilderError(
            f"events directory does not exist: {root}"
        )
    now = datetime.now(timezone.utc).timestamp()
    paths = sorted(root.glob("*.json"), key=lambda path: path.stat().st_mtime)
    if lookback_seconds <= 0:
        return paths
    return [
        path
        for path in paths
        if now - path.stat().st_mtime <= lookback_seconds
    ]


def _ensure_private_runtime_output(path: str | Path) -> Path:
    output = Path(path)
    if not output.is_absolute():
        output = Path.cwd() / output
    output = output.resolve()
    private_root = PRIVATE_RUNTIME_DIR.resolve()
    if not str(output).startswith(str(private_root) + os.sep):
        raise FeishuAttachmentEventBatchBuilderError(
            f"attachment batch must be written under {PRIVATE_RUNTIME_DIR}"
        )
    return output


def _attachment_record(
    attachment: dict[str, Any],
    *,
    attachment_index: int,
    message_id: str,
    message_id_source_path: str,
    source_event_path: str,
) -> dict[str, Any]:
    token = str(
        _first_non_empty(attachment, ("file_token", "token", "file_key"))
    ).strip()
    filename = str(
        _first_non_empty(attachment, ("file_name", "filename", "name", "fileName"))
    ).strip()
    size_raw = _first_non_empty(attachment, ("size_bytes", "size", "file_size"))
    try:
        size_bytes = int(size_raw) if size_raw not in (None, "") else 0
    except (TypeError, ValueError):
        size_bytes = 0
    token_hash = _hash_text(token) if token else ""
    return {
        "attachment_index": attachment_index,
        "filename": Path(filename).name if filename else f"attachment_{attachment_index + 1}",
        "file_token": token,
        "file_token_hash": token_hash,
        "message_id": message_id,
        "message_id_source_path": message_id_source_path,
        "message_id_hash_prefix": _hash_prefix(message_id),
        "message_id_len": len(message_id),
        "source_event_path": source_event_path,
        "size_bytes": size_bytes,
        "mime_type": str(
            _first_non_empty(attachment, ("mime_type", "mimetype"))
        ).strip(),
        "file_type": str(_first_non_empty(attachment, ("file_type", "type"))).strip(),
    }


def _dedupe_records(records: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for record in records:
        token_hash = str(record.get("file_token_hash", ""))
        filename = str(record.get("filename", ""))
        message_hash = str(record.get("message_id_hash_prefix", ""))
        key = f"token:{token_hash}" if token_hash else f"filename:{filename}:{message_hash}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    for index, record in enumerate(deduped):
        record["attachment_index"] = index
    return deduped


def _load_validated_pairs(path: str | Path) -> list[dict[str, Any]]:
    payload = _load_json(Path(path))
    pairs = payload.get("validated_pairs")
    if not isinstance(pairs, list):
        raise FeishuAttachmentEventBatchBuilderError(
            "validated pairs JSON must contain validated_pairs."
        )
    return [pair for pair in pairs if isinstance(pair, dict)]


def _records_from_validated_pairs(pairs: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    by_token: dict[str, dict[str, Any]] = {}
    by_filename: dict[str, dict[str, Any]] = {}
    for pair in pairs:
        token = str(pair.get("file_token", "")).strip()
        message_id = str(pair.get("message_id", "")).strip()
        filename = str(pair.get("filename", "")).strip()
        if not token or not message_id.startswith("om_") or not filename:
            continue
        token_hash = str(pair.get("file_token_hash", "")).strip()
        if not token_hash:
            token_hash = _hash_text(token)
        normalized = {
            "attachment_index": 0,
            "filename": Path(filename).name,
            "file_token": token,
            "file_token_hash": token_hash,
            "message_id": message_id,
            "message_id_source_path": str(
                pair.get("message_id_source_path", "")
            ).strip(),
            "message_id_hash_prefix": str(
                pair.get("message_id_hash_prefix", "")
            ).strip()
            or _hash_prefix(message_id),
            "message_id_len": int(pair.get("message_id_len", 0) or len(message_id)),
            "source_event_path": str(pair.get("source_event_path", "")).strip(),
            "size_bytes": int(pair.get("size_bytes", 0) or 0),
            "probe_download_path": str(pair.get("probe_download_path", "")).strip(),
        }
        previous = by_token.get(token_hash)
        if previous and str(previous.get("source_event_path", "")) >= str(
            normalized.get("source_event_path", "")
        ):
            continue
        by_token[token_hash] = normalized
        current_filename = by_filename.get(normalized["filename"])
        if not current_filename or str(normalized.get("source_event_path", "")) >= str(
            current_filename.get("source_event_path", "")
        ):
            by_filename[normalized["filename"]] = normalized
    selected_hashes = {
        str(record.get("file_token_hash", "")) for record in by_filename.values()
    }
    records = [
        record
        for record in by_token.values()
        if str(record.get("file_token_hash", "")) in selected_hashes
    ]
    records = sorted(records, key=lambda item: (item.get("filename", ""), item.get("source_event_path", "")))
    for index, record in enumerate(records):
        record["attachment_index"] = index
    return records


def _batch_from_records(
    records: Sequence[dict[str, Any]],
    *,
    strategy: str,
    selected_key: tuple[str, str] = ("", ""),
    source_event_paths: Sequence[str] | None = None,
    stats: dict[str, int] | None = None,
    ready_for_real_download: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_paths = list(source_event_paths or [])
    message_hashes = [str(record.get("message_id_hash_prefix", "")) for record in records]
    unique_message_hashes = {value for value in message_hashes if value}
    repeated_message_id_count = len(message_hashes) - len(unique_message_hashes)
    repeated_message_id_warning = repeated_message_id_count > 0
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    batch_hash = _hash_prefix("|".join(str(record.get("file_token_hash", "")) for record in records))
    stats = stats or {}
    batch = {
        "mode": MODE,
        "batch_id": f"{now}_{batch_hash}",
        "event_count": len(source_paths),
        "attachment_count": len(records),
        "source_event_paths": source_paths,
        "batch_selection_strategy": strategy,
        "single_attachment_event_count": stats.get("single_attachment_event_count", 0),
        "multi_attachment_event_count": stats.get("multi_attachment_event_count", 0),
        "ignored_multi_attachment_event_count": stats.get(
            "ignored_multi_attachment_event_count", 0
        ),
        "ignored_compact_event_count": stats.get("ignored_compact_event_count", 0),
        "selected_source_event_paths": source_paths,
        "per_attachment_message_id_unique_count": len(unique_message_hashes),
        "repeated_message_id_count": repeated_message_id_count,
        "repeated_message_id_warning": repeated_message_id_warning,
        "ready_for_real_download": bool(records) and ready_for_real_download,
        "chat_id_hash_prefix": selected_key[0],
        "sender_id_hash_prefix": selected_key[1],
        "attachments": list(records),
    }
    summary = {
        "mode": MODE,
        "batch_created": bool(records),
        "event_count": len(source_paths),
        "attachment_count": len(records),
        "valid_event_count": stats.get("valid_event_count", 0),
        "ignored_event_count": stats.get("ignored_event_count", 0),
        "batch_selection_strategy": strategy,
        "single_attachment_event_count": stats.get("single_attachment_event_count", 0),
        "multi_attachment_event_count": stats.get("multi_attachment_event_count", 0),
        "ignored_multi_attachment_event_count": batch["ignored_multi_attachment_event_count"],
        "ignored_compact_event_count": batch["ignored_compact_event_count"],
        "selected_source_event_paths": source_paths,
        "per_attachment_message_id_unique_count": len(unique_message_hashes),
        "repeated_message_id_count": repeated_message_id_count,
        "repeated_message_id_warning": repeated_message_id_warning,
        "output_path": "",
        "filenames": [str(record.get("filename", "")) for record in records],
        "message_id_lens": [record.get("message_id_len", 0) for record in records],
        "message_id_hash_prefixes": message_hashes,
        "token_hashes": [str(record.get("file_token_hash", "")) for record in records],
        "ready_for_real_download": bool(records) and ready_for_real_download,
        "required_next_action": ""
        if records and ready_for_real_download
        else "send_files_to_product_bot_again_or_check_callback_capture",
    }
    return batch, summary


def build_batch_from_validated_pairs(validated_pairs: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    pairs = _load_validated_pairs(validated_pairs)
    records = _records_from_validated_pairs(pairs)
    source_paths = sorted({str(record.get("source_event_path", "")) for record in records if record.get("source_event_path")})
    return _batch_from_records(
        records,
        strategy="validated_download_pairs",
        source_event_paths=source_paths,
        stats={"valid_event_count": len(source_paths)},
        ready_for_real_download=True,
    )


def collect_valid_event_groups(
    events_dir: str | Path,
    *,
    lookback_seconds: int = 300,
    allow_compact: bool = False,
) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], dict[str, int]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    stats = {
        "valid_event_count": 0,
        "ignored_event_count": 0,
        "ignored_compact_event_count": 0,
        "single_attachment_event_count": 0,
        "multi_attachment_event_count": 0,
    }
    for path in _recent_event_paths(events_dir, lookback_seconds):
        is_compact = "compact_event" in path.name
        is_raw = "_raw_event" in path.name or "http_raw_event" in path.name
        try:
            payload = _load_json(path)
            verification = verify_capture_event(payload)
        except Exception:
            stats["ignored_event_count"] += 1
            continue
        if not verification.get("capture_valid_for_download"):
            stats["ignored_event_count"] += 1
            if is_compact:
                stats["ignored_compact_event_count"] += 1
            continue
        if is_compact and not allow_compact:
            stats["ignored_event_count"] += 1
            stats["ignored_compact_event_count"] += 1
            continue
        try:
            message_id, source_path = extract_message_id(payload)
            attachments = extract_attachments(payload)
        except Exception:
            stats["ignored_event_count"] += 1
            continue
        attachment_count = len(attachments)
        stats["valid_event_count"] += 1
        if attachment_count == 1 and is_raw:
            stats["single_attachment_event_count"] += 1
        elif attachment_count > 1:
            stats["multi_attachment_event_count"] += 1
        chat_hash = _hash_prefix(_chat_id(payload))
        sender_hash = _hash_prefix(_sender_id(payload))
        event_record = {
            "path": str(path),
            "mtime": path.stat().st_mtime,
            "message_id": message_id,
            "message_id_source_path": source_path,
            "attachments": attachments,
            "attachment_count": attachment_count,
            "is_raw_event": is_raw,
            "is_compact_event": is_compact,
        }
        groups.setdefault((chat_hash, sender_hash), []).append(event_record)
    return groups, stats


def build_attachment_event_batch(
    events_dir: str | Path,
    *,
    lookback_seconds: int = 300,
    allow_multi_attachment_events: bool = False,
    allow_shared_message_id_for_multi_attachment: bool = False,
    allow_compact: bool = False,
    validated_pairs: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if validated_pairs:
        return build_batch_from_validated_pairs(validated_pairs)

    groups, stats = collect_valid_event_groups(
        events_dir, lookback_seconds=lookback_seconds, allow_compact=allow_compact
    )
    if not groups:
        summary = {
            "mode": MODE,
            "batch_created": False,
            "event_count": 0,
            "attachment_count": 0,
            "valid_event_count": stats["valid_event_count"],
            "ignored_event_count": stats["ignored_event_count"],
            "batch_selection_strategy": "strict_single_attachment_raw_events",
            "single_attachment_event_count": stats["single_attachment_event_count"],
            "multi_attachment_event_count": stats["multi_attachment_event_count"],
            "ignored_multi_attachment_event_count": stats["multi_attachment_event_count"],
            "ignored_compact_event_count": stats["ignored_compact_event_count"],
            "selected_source_event_paths": [],
            "per_attachment_message_id_unique_count": 0,
            "repeated_message_id_count": 0,
            "repeated_message_id_warning": False,
            "output_path": "",
            "filenames": [],
            "message_id_lens": [],
            "message_id_hash_prefixes": [],
            "token_hashes": [],
            "ready_for_real_download": False,
            "required_next_action": "send_files_to_product_bot_again_or_check_callback_capture",
        }
        return {}, summary

    selected_key, candidate_events = max(
        groups.items(),
        key=lambda item: (max(event["mtime"] for event in item[1]), len(item[1])),
    )
    candidate_events = sorted(candidate_events, key=lambda item: item["mtime"])
    single_events = [
        event
        for event in candidate_events
        if event["attachment_count"] == 1 and event["is_raw_event"]
    ]
    multi_events = [
        event for event in candidate_events if event["attachment_count"] > 1
    ]
    if single_events:
        selected_events = single_events
        strategy = "strict_single_attachment_raw_events"
    elif allow_multi_attachment_events and multi_events:
        selected_events = multi_events
        strategy = "explicit_multi_attachment_events"
    else:
        selected_events = []
        strategy = "strict_single_attachment_raw_events"
    records: list[dict[str, Any]] = []
    for event in selected_events:
        for attachment in event["attachments"]:
            records.append(
                _attachment_record(
                    attachment,
                    attachment_index=len(records),
                    message_id=event["message_id"],
                    message_id_source_path=event["message_id_source_path"],
                    source_event_path=event["path"],
                )
            )
    records = _dedupe_records(records)
    message_hashes = [record["message_id_hash_prefix"] for record in records]
    unique_message_hashes = set(message_hashes)
    repeated_message_id_count = len(message_hashes) - len(unique_message_hashes)
    repeated_message_id_warning = repeated_message_id_count > 0
    selected_has_multi_event = any(event["attachment_count"] > 1 for event in selected_events)
    ready_for_real_download = bool(records)
    if selected_has_multi_event and repeated_message_id_warning:
        ready_for_real_download = allow_shared_message_id_for_multi_attachment
    stats_for_batch = {
        **stats,
        "ignored_multi_attachment_event_count": (
            stats["multi_attachment_event_count"]
            if strategy == "strict_single_attachment_raw_events"
            else 0
        ),
    }
    return _batch_from_records(
        records,
        strategy=strategy,
        selected_key=selected_key,
        source_event_paths=[event["path"] for event in selected_events],
        stats=stats_for_batch,
        ready_for_real_download=ready_for_real_download,
    )


def write_attachment_event_batch(batch: dict[str, Any], output: str | Path) -> Path:
    output_path = _ensure_private_runtime_output(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(batch, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(output_path, 0o600)
    return output_path


def build_and_write_batch(
    events_dir: str | Path,
    *,
    lookback_seconds: int,
    output: str | Path,
    allow_multi_attachment_events: bool = False,
    allow_shared_message_id_for_multi_attachment: bool = False,
    allow_compact: bool = False,
    validated_pairs: str | Path | None = None,
) -> dict[str, Any]:
    batch, summary = build_attachment_event_batch(
        events_dir,
        lookback_seconds=lookback_seconds,
        allow_multi_attachment_events=allow_multi_attachment_events,
        allow_shared_message_id_for_multi_attachment=allow_shared_message_id_for_multi_attachment,
        allow_compact=allow_compact,
        validated_pairs=validated_pairs,
    )
    if batch:
        output_path = write_attachment_event_batch(batch, output)
        summary["output_path"] = str(output_path)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events-dir", default=str(DEFAULT_EVENTS_DIR))
    parser.add_argument("--lookback-seconds", type=int, default=300)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--validated-pairs")
    parser.add_argument("--allow-multi-attachment-events", action="store_true")
    parser.add_argument(
        "--allow-shared-message-id-for-multi-attachment", action="store_true"
    )
    parser.add_argument("--allow-compact", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = build_and_write_batch(
        args.events_dir,
        lookback_seconds=args.lookback_seconds,
        output=args.output,
        allow_multi_attachment_events=args.allow_multi_attachment_events,
        allow_shared_message_id_for_multi_attachment=args.allow_shared_message_id_for_multi_attachment,
        allow_compact=args.allow_compact,
        validated_pairs=args.validated_pairs,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
