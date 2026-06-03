"""Build a local-only Feishu multi-attachment download dry-run plan."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shlex
from collections import Counter
from pathlib import Path
from typing import Any, Sequence


MODE = "feishu_multi_attachment_dry_run_v1.20"
PLAN_MODE = "feishu_multi_attachment_download_plan_v1.20"
SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".xls"}
DEFAULT_MAX_ATTACHMENTS = 20
DEFAULT_MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024
CSV_FIELDS = [
    "attachment_index",
    "filename",
    "suffix",
    "supported",
    "size_bytes",
    "file_token_hash",
    "planned_download_path",
    "planned_batch_input",
    "error_count",
]


class MultiAttachmentDryRunError(ValueError):
    """Raised when attachment metadata cannot produce a dry-run plan."""


def _first_non_empty(item: dict[str, Any], fields: Sequence[str]) -> Any:
    for field in fields:
        value = item.get(field)
        if value not in (None, ""):
            return value
    return ""


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest() if token else ""


def load_attachment_items(path: str | Path) -> list[dict[str, Any]]:
    """Load attachment metadata from attachments, files, or a direct JSON list."""
    input_path = Path(path)
    if not input_path.exists():
        raise MultiAttachmentDryRunError(
            f"Attachment JSON does not exist: {input_path}"
        )
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MultiAttachmentDryRunError(
            f"Attachment JSON is invalid: {input_path}: {exc}"
        ) from exc

    if isinstance(payload, list):
        attachments = payload
    elif isinstance(payload, dict):
        attachments = payload.get("attachments")
        if attachments is None:
            attachments = payload.get("files")
    else:
        attachments = None
    if not isinstance(attachments, list) or not attachments:
        raise MultiAttachmentDryRunError(
            "Attachment JSON must contain a non-empty attachments/files list."
        )
    if not all(isinstance(item, dict) for item in attachments):
        raise MultiAttachmentDryRunError("Each attachment must be a JSON object.")
    return attachments


def _deduplicated_filename(filename: str, occurrence: int) -> str:
    if occurrence <= 1:
        return filename
    path = Path(filename)
    return f"{path.stem}_{occurrence}{path.suffix}"


def _parse_size(raw_size: Any) -> tuple[int, str | None]:
    try:
        size = int(raw_size)
    except (TypeError, ValueError):
        return 0, "附件大小缺失或不是整数"
    if size <= 0:
        return size, "附件大小必须大于 0"
    return size, None


def build_dry_run_manifest(
    raw_attachments: Sequence[dict[str, Any]],
    *,
    download_dir: str | Path = "product_intel/feishu_downloads",
    max_attachments: int = DEFAULT_MAX_ATTACHMENTS,
    max_file_size_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES,
) -> dict[str, Any]:
    """Normalize metadata and decide whether a future real download is safe."""
    if not raw_attachments:
        raise MultiAttachmentDryRunError("At least one attachment is required.")
    if max_attachments <= 0:
        raise MultiAttachmentDryRunError("max_attachments must be greater than zero.")
    if max_file_size_bytes <= 0:
        raise MultiAttachmentDryRunError(
            "max_file_size_bytes must be greater than zero."
        )

    download_root = Path(download_dir)
    filename_seen: Counter[str] = Counter()
    token_seen: Counter[str] = Counter()
    normalized: list[dict[str, Any]] = []
    serious_errors: list[str] = []

    if len(raw_attachments) > max_attachments:
        serious_errors.append(
            f"附件数量 {len(raw_attachments)} 超过上限 {max_attachments}"
        )

    for index, raw in enumerate(raw_attachments):
        raw_filename = str(
            _first_non_empty(raw, ("file_name", "filename", "name"))
        ).strip()
        filename = Path(raw_filename).name if raw_filename else f"attachment_{index + 1}"
        suffix = Path(filename).suffix.lower()
        supported = suffix in SUPPORTED_SUFFIXES
        token = str(_first_non_empty(raw, ("file_token", "token"))).strip()
        size, size_error = _parse_size(
            _first_non_empty(raw, ("size_bytes", "size", "file_size"))
        )

        filename_seen[filename] += 1
        if token:
            token_seen[token] += 1
        planned_filename = _deduplicated_filename(filename, filename_seen[filename])
        planned_path = str(download_root / planned_filename)

        errors: list[str] = []
        if not raw_filename:
            errors.append("附件文件名缺失")
        if not supported:
            errors.append("不支持的文件类型，仅允许 .csv / .xlsx / .xls")
        if not token:
            errors.append("附件 token 缺失")
        if size_error:
            errors.append(size_error)
        if size > max_file_size_bytes:
            errors.append(f"附件大小超过上限 {max_file_size_bytes} bytes")

        blocking_errors = [
            error
            for error in errors
            if error != "不支持的文件类型，仅允许 .csv / .xlsx / .xls"
        ]
        if supported and blocking_errors:
            serious_errors.extend(f"{filename}: {error}" for error in blocking_errors)

        normalized.append(
            {
                "attachment_index": index,
                "filename": filename,
                "suffix": suffix,
                "supported": supported,
                "size_bytes": size,
                "mime_type": str(
                    _first_non_empty(raw, ("mime_type", "mimetype"))
                ).strip(),
                "file_token_redacted": "REDACTED_FILE_TOKEN" if token else "",
                "file_token_hash": _token_hash(token),
                "planned_download_path": planned_path,
                "planned_batch_input": supported and not blocking_errors,
                "errors": errors,
            }
        )

    supported_items = [item for item in normalized if item["supported"]]
    unsupported_items = [item for item in normalized if not item["supported"]]
    planned_inputs = [
        item["planned_download_path"]
        for item in normalized
        if item["planned_batch_input"]
    ]
    planned_paths = [item["planned_download_path"] for item in normalized]
    paths_unique = len(planned_paths) == len(set(planned_paths))
    if not paths_unique:
        serious_errors.append("规划下载路径不唯一")
    if not supported_items:
        serious_errors.append("没有可下载并进入批处理的 CSV / XLSX / XLS 附件")

    duplicate_filename_count = sum(
        count - 1 for count in filename_seen.values() if count > 1
    )
    duplicate_file_token_count = sum(
        count - 1 for count in token_seen.values() if count > 1
    )
    ready_for_real_download = bool(supported_items) and not serious_errors
    ready_for_multi_file_batch_runner = (
        bool(supported_items)
        and bool(planned_inputs)
        and len(planned_inputs) == len(supported_items)
        and all(item["suffix"] in SUPPORTED_SUFFIXES for item in supported_items)
    )
    return {
        "mode": MODE,
        "real_feishu_api_called": False,
        "real_download_performed": False,
        "attachment_count": len(normalized),
        "supported_attachment_count": len(supported_items),
        "unsupported_attachment_count": len(unsupported_items),
        "ready_for_real_download": ready_for_real_download,
        "ready_for_multi_file_batch_runner": ready_for_multi_file_batch_runner,
        "max_attachments": max_attachments,
        "max_file_size_bytes": max_file_size_bytes,
        "attachments": normalized,
        "unsupported_attachments": unsupported_items,
        "duplicate_filename_count": duplicate_filename_count,
        "duplicate_file_token_count": duplicate_file_token_count,
        "errors": serious_errors,
    }


def build_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    supported = [item for item in manifest["attachments"] if item["supported"]]
    suffix_counts = Counter(item["suffix"] for item in supported)
    planned_inputs = [
        item["planned_download_path"]
        for item in manifest["attachments"]
        if item["planned_batch_input"]
    ]
    quoted_inputs = " ".join(shlex.quote(path) for path in planned_inputs)
    return {
        "mode": MODE,
        "attachment_count": manifest["attachment_count"],
        "supported_attachment_count": manifest["supported_attachment_count"],
        "unsupported_attachment_count": manifest["unsupported_attachment_count"],
        "csv_count": suffix_counts[".csv"],
        "xlsx_count": suffix_counts[".xlsx"],
        "xls_count": suffix_counts[".xls"],
        "total_supported_size_bytes": sum(item["size_bytes"] for item in supported),
        "duplicate_filename_count": manifest["duplicate_filename_count"],
        "duplicate_file_token_count": manifest["duplicate_file_token_count"],
        "ready_for_real_download": manifest["ready_for_real_download"],
        "ready_for_multi_file_batch_runner": manifest[
            "ready_for_multi_file_batch_runner"
        ],
        "planned_input_files": planned_inputs,
        "next_command_after_real_download": (
            "python3 -m product_intel.multi_file_batch_runner "
            f"--inputs {quoted_inputs} --source auto --market de "
            "--output-dir product_intel/output_multi_file_from_feishu"
        ),
    }


def build_download_plan(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": PLAN_MODE,
        "real_download_enabled": False,
        "real_feishu_api_called": False,
        "download_tasks": [
            {
                "attachment_index": item["attachment_index"],
                "filename": item["filename"],
                "file_token_redacted": item["file_token_redacted"],
                "file_token_hash": item["file_token_hash"],
                "target_path": item["planned_download_path"],
                "supported": item["supported"],
                "size_bytes_expected": item["size_bytes"],
            }
            for item in manifest["attachments"]
            if item["supported"]
        ],
    }


def summary_markdown(summary: dict[str, Any], manifest: dict[str, Any]) -> str:
    lines = [
        "# Product Intel v1.20 Feishu Multi-attachment Download Dry Run",
        "",
        "## 结论",
        "",
        "- 本次未调用真实飞书 API。",
        "- 本次未下载真实附件。",
        f"- ready_for_real_download：{str(summary['ready_for_real_download']).lower()}",
        (
            "- ready_for_multi_file_batch_runner："
            f"{str(summary['ready_for_multi_file_batch_runner']).lower()}"
        ),
        f"- 附件总数：{summary['attachment_count']}",
        f"- 支持附件：{summary['supported_attachment_count']}",
        f"- 不支持附件：{summary['unsupported_attachment_count']}",
        "",
        "## 可进入批处理的文件",
        "",
    ]
    lines.extend(f"- {path}" for path in summary["planned_input_files"])
    if not summary["planned_input_files"]:
        lines.append("- 无")
    lines.extend(["", "## 不支持或异常附件", ""])
    exceptional = [item for item in manifest["attachments"] if item["errors"]]
    for item in exceptional:
        lines.append(f"- {item['filename']}：{'；'.join(item['errors'])}")
    if not exceptional:
        lines.append("- 无")
    lines.extend(
        [
            "",
            "## 下一步",
            "",
            f"`{summary['next_command_after_real_download']}`",
            "",
        ]
    )
    return "\n".join(lines)


def checklist_markdown() -> str:
    return """# Product Intel v1.20 Feishu Multi-attachment Dry Run Checklist

- [ ] 本次未调用真实飞书 API
- [ ] 本次未下载真实附件
- [ ] 所有真实 file_token 已脱敏
- [ ] 支持文件类型仅限 .csv / .xlsx / .xls
- [ ] 已识别可进入批处理的文件
- [ ] ready_for_real_download=true
- [ ] ready_for_multi_file_batch_runner=true
- [ ] 下一步 v1.21 才允许真实下载
"""


def write_outputs(
    manifest: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    summary = build_summary(manifest)
    plan = build_download_plan(manifest)
    paths = {
        "manifest_json": output / "feishu_multi_attachment_dry_run_manifest.json",
        "summary_json": output / "feishu_multi_attachment_dry_run_summary.json",
        "summary_md": output / "feishu_multi_attachment_dry_run_summary.md",
        "download_plan_json": output / "feishu_multi_attachment_download_plan.json",
        "file_list_csv": output / "feishu_multi_attachment_file_list.csv",
        "checklist_md": output / "feishu_multi_attachment_checklist.md",
    }
    paths["manifest_json"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    paths["summary_json"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    paths["summary_md"].write_text(
        summary_markdown(summary, manifest), encoding="utf-8"
    )
    paths["download_plan_json"].write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with paths["file_list_csv"].open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for item in manifest["attachments"]:
            writer.writerow(
                {
                    "attachment_index": item["attachment_index"],
                    "filename": item["filename"],
                    "suffix": item["suffix"],
                    "supported": item["supported"],
                    "size_bytes": item["size_bytes"],
                    "file_token_hash": item["file_token_hash"],
                    "planned_download_path": item["planned_download_path"],
                    "planned_batch_input": item["planned_batch_input"],
                    "error_count": len(item["errors"]),
                }
            )
    paths["checklist_md"].write_text(checklist_markdown(), encoding="utf-8")
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attachments-json", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--download-dir", default="product_intel/feishu_downloads"
    )
    parser.add_argument("--max-attachments", type=int, default=DEFAULT_MAX_ATTACHMENTS)
    parser.add_argument(
        "--max-file-size-bytes", type=int, default=DEFAULT_MAX_FILE_SIZE_BYTES
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = build_dry_run_manifest(
        load_attachment_items(args.attachments_json),
        download_dir=args.download_dir,
        max_attachments=args.max_attachments,
        max_file_size_bytes=args.max_file_size_bytes,
    )
    write_outputs(manifest, args.output_dir)
    print(json.dumps(build_summary(manifest), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
