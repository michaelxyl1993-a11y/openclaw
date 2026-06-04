"""Validate Feishu attachment file_token/message_id pairs with a real download probe."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from .feishu_callback_capture_verifier import verify_capture_event
from .feishu_multi_attachment_download_real import (
    APP_ID_ENV,
    APP_SECRET_ENV,
    FeishuDownloadHTTPError,
    FeishuMultiAttachmentDownloadClient,
    REAL_DOWNLOAD_ENABLED_ENV,
    apply_http_diagnostics,
    is_real_download_enabled,
    response_indicates_invalid_open_message_id,
    sanitize_error,
)
from .feishu_runtime_token_source_builder import (
    PRIVATE_RUNTIME_DIR,
    extract_attachments,
    extract_message_id,
)


MODE = "feishu_validated_download_pairs_v1.21.12"
DEFAULT_EVENTS_DIR = PRIVATE_RUNTIME_DIR / "feishu_events"
DEFAULT_OUTPUT = PRIVATE_RUNTIME_DIR / "feishu_validated_download_pairs.json"
DEFAULT_PROBE_DIR = PRIVATE_RUNTIME_DIR / "probe_downloads"
INVALID_OPEN_MESSAGE_ID_ROOT_CAUSE = "invalid_open_message_id"


class FeishuAttachmentDownloadProbeError(ValueError):
    """Raised when a probe cannot be prepared safely."""


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


def _ensure_private_runtime_path(path: str | Path) -> Path:
    output = Path(path)
    if not output.is_absolute():
        output = Path.cwd() / output
    output = output.resolve()
    private_root = PRIVATE_RUNTIME_DIR.resolve()
    if not str(output).startswith(str(private_root) + os.sep):
        raise FeishuAttachmentDownloadProbeError(
            f"probe output must be written under {PRIVATE_RUNTIME_DIR}"
        )
    return output


def _event_paths(events_dir: str | Path, lookback_seconds: int) -> list[Path]:
    root = Path(events_dir)
    if not root.exists():
        raise FeishuAttachmentDownloadProbeError(
            f"events directory does not exist: {root}"
        )
    import time

    now = time.time()
    paths = sorted(root.glob("*.json"), key=lambda path: path.stat().st_mtime)
    if lookback_seconds <= 0:
        return paths
    return [
        path
        for path in paths
        if now - path.stat().st_mtime <= lookback_seconds
    ]


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FeishuAttachmentDownloadProbeError(f"event must be an object: {path}")
    return payload


def collect_candidate_pairs(
    events_dir: str | Path,
    *,
    lookback_seconds: int = 300,
) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for path in _event_paths(events_dir, lookback_seconds):
        if "compact_event" in path.name:
            continue
        try:
            payload = _load_json(path)
            verification = verify_capture_event(payload)
        except Exception:
            continue
        if not verification.get("capture_valid_for_download"):
            continue
        try:
            message_id, source_path = extract_message_id(payload)
            attachments = extract_attachments(payload)
        except Exception:
            continue
        for attachment in attachments:
            token = str(
                _first_non_empty(attachment, ("file_token", "token", "file_key"))
            ).strip()
            filename = str(
                _first_non_empty(
                    attachment, ("file_name", "filename", "name", "fileName")
                )
            ).strip()
            if not token or not filename:
                continue
            pairs.append(
                {
                    "filename": Path(filename).name,
                    "file_token": token,
                    "file_token_hash": _hash_text(token),
                    "message_id": message_id,
                    "message_id_hash_prefix": _hash_prefix(message_id),
                    "message_id_len": len(message_id),
                    "message_id_source_path": source_path,
                    "source_event_path": str(path),
                    "source_event_mtime": path.stat().st_mtime,
                }
            )
    return pairs


def _probe_target_path(pair: dict[str, Any], probe_dir: Path) -> Path:
    filename = Path(str(pair.get("filename", "attachment"))).name
    token_hash = str(pair.get("file_token_hash", ""))[:12]
    return probe_dir / f"{token_hash}_{filename}"


def _dedupe_validated_pairs(pairs: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    by_token: dict[str, dict[str, Any]] = {}
    by_filename: dict[str, dict[str, Any]] = {}
    for pair in pairs:
        token_hash = str(pair.get("file_token_hash", ""))
        filename = str(pair.get("filename", ""))
        previous = by_token.get(token_hash)
        if previous and float(previous.get("source_event_mtime", 0)) >= float(
            pair.get("source_event_mtime", 0)
        ):
            continue
        by_token[token_hash] = pair
        existing_filename = by_filename.get(filename)
        if not existing_filename or float(pair.get("source_event_mtime", 0)) >= float(
            existing_filename.get("source_event_mtime", 0)
        ):
            by_filename[filename] = pair
    selected_hashes = {pair["file_token_hash"] for pair in by_filename.values()}
    return [
        pair
        for pair in by_token.values()
        if pair.get("file_token_hash") in selected_hashes
    ]


def run_probe(
    events_dir: str | Path,
    *,
    lookback_seconds: int = 300,
    output: str | Path = DEFAULT_OUTPUT,
    probe_dir: str | Path = DEFAULT_PROBE_DIR,
    environ: Mapping[str, str] | None = None,
    client: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    env = environ if environ is not None else os.environ
    output_path = _ensure_private_runtime_path(output)
    probe_root = _ensure_private_runtime_path(probe_dir)
    candidate_pairs = collect_candidate_pairs(
        events_dir, lookback_seconds=lookback_seconds
    )
    enabled = is_real_download_enabled(env)
    app_id = env.get(APP_ID_ENV, "").strip()
    app_secret = env.get(APP_SECRET_ENV, "").strip()
    validated: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    downloader = client or FeishuMultiAttachmentDownloadClient()

    if enabled and app_id and app_secret:
        probe_root.mkdir(parents=True, exist_ok=True)
        for pair in candidate_pairs:
            target = _probe_target_path(pair, probe_root)
            secrets = [
                app_id,
                app_secret,
                str(pair.get("file_token", "")),
                str(pair.get("message_id", "")),
            ]
            try:
                downloader.download_file(
                    app_id=app_id,
                    app_secret=app_secret,
                    message_id=str(pair["message_id"]),
                    file_token=str(pair["file_token"]),
                    target_path=str(target),
                )
                if not target.exists() or target.stat().st_size <= 0:
                    raise RuntimeError("Probe download did not produce a non-empty file.")
                validated_pair = dict(pair)
                validated_pair["validated"] = True
                validated_pair["probe_download_path"] = str(target)
                validated.append(validated_pair)
            except FeishuDownloadHTTPError as exc:
                failed_pair = dict(pair)
                failed_pair["validated"] = False
                failed_pair["error"] = sanitize_error(exc, secrets)
                apply_http_diagnostics(
                    failed_pair,
                    exc,
                    secrets=secrets,
                    message_id=str(pair.get("message_id", "")),
                    message_id_source_path=str(pair.get("message_id_source_path", "")),
                )
                failed_pair["probable_root_cause"] = (
                    INVALID_OPEN_MESSAGE_ID_ROOT_CAUSE
                    if response_indicates_invalid_open_message_id(exc.response_body)
                    else ""
                )
                failed.append(failed_pair)
            except Exception as exc:
                failed_pair = dict(pair)
                failed_pair["validated"] = False
                failed_pair["error"] = sanitize_error(exc, secrets)
                failed.append(failed_pair)
    else:
        for pair in candidate_pairs:
            failed_pair = dict(pair)
            failed_pair["validated"] = False
            failed_pair["error"] = (
                "probe disabled: real download env and Feishu app credentials are required."
            )
            failed.append(failed_pair)

    validated = _dedupe_validated_pairs(validated)
    payload = {
        "mode": MODE,
        "candidate_pair_count": len(candidate_pairs),
        "validated_pair_count": len(validated),
        "failed_pair_count": len(failed),
        "validated_pairs": validated,
        "failed_pairs": failed,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.chmod(output_path, 0o600)
    summary = {
        "mode": MODE,
        "candidate_pair_count": len(candidate_pairs),
        "validated_pair_count": len(validated),
        "failed_pair_count": len(failed),
        "filenames_validated": [pair["filename"] for pair in validated],
        "filenames_failed": [pair["filename"] for pair in failed],
        "ready_for_validated_batch": len(validated) >= 1,
        "output_path": str(output_path),
        "required_next_action": ""
        if validated
        else "run_probe_with_real_download_enabled_or_send_files_again",
    }
    return payload, summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events-dir", default=str(DEFAULT_EVENTS_DIR))
    parser.add_argument("--lookback-seconds", type=int, default=300)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _, summary = run_probe(
        args.events_dir,
        lookback_seconds=args.lookback_seconds,
        output=args.output,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
