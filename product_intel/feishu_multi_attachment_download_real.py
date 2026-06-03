"""Opt-in real Feishu multi-attachment downloader. This module never analyzes files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shlex
from pathlib import Path
from typing import Any, Mapping, Sequence


MODE = "feishu_multi_attachment_download_real_v1.21"
INPUTS_MODE = "feishu_multi_attachment_downloaded_inputs_v1.21"
REAL_DOWNLOAD_ENABLED_ENV = "PRODUCT_INTEL_REAL_FEISHU_MULTI_DOWNLOAD_ENABLED"
APP_ID_ENV = "FEISHU_APP_ID"
APP_SECRET_ENV = "FEISHU_APP_SECRET"
SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".xls"}
CSV_FIELDS = [
    "attachment_index",
    "filename",
    "target_path",
    "supported",
    "download_status",
    "file_token_hash",
    "size_bytes_expected",
    "size_bytes_downloaded",
    "exists",
    "error",
]


def is_real_download_enabled(environ: Mapping[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    return env.get(REAL_DOWNLOAD_ENABLED_ENV, "").strip().lower() == "true"


def load_download_plan(path: str | Path) -> dict[str, Any]:
    plan_path = Path(path)
    if not plan_path.exists():
        raise ValueError(
            f"Feishu multi-download blocked: download plan does not exist: {plan_path}"
        )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if not isinstance(plan, dict):
        raise ValueError("Feishu multi-download blocked: download plan must be an object.")
    if not isinstance(plan.get("download_tasks"), list):
        raise ValueError(
            "Feishu multi-download blocked: download_tasks must be a list."
        )
    return plan


def _first_non_empty(item: dict[str, Any], fields: Sequence[str]) -> Any:
    for field in fields:
        value = item.get(field)
        if value not in (None, ""):
            return value
    return ""


def _attachment_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        attachments = payload
    elif isinstance(payload, dict):
        attachments = payload.get("attachments")
        if attachments is None:
            attachments = payload.get("files")
    else:
        attachments = None
    if not isinstance(attachments, list):
        raise ValueError(
            "Feishu multi-download blocked: token source must contain attachments/files."
        )
    if not all(isinstance(item, dict) for item in attachments):
        raise ValueError(
            "Feishu multi-download blocked: token source attachments must be objects."
        )
    return attachments


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _token_context_from_mapping(payload: dict[str, Any]) -> dict[str, str]:
    tokens_by_hash: dict[str, str] = {}
    for field in ("tokens_by_hash", "file_tokens"):
        mapping = payload.get(field)
        if isinstance(mapping, dict):
            for token_hash, token in mapping.items():
                token_text = str(token).strip()
                if token_hash and token_text:
                    tokens_by_hash[str(token_hash)] = token_text

    token_items = payload.get("tokens")
    if isinstance(token_items, list):
        for item in token_items:
            if not isinstance(item, dict):
                continue
            token = str(_first_non_empty(item, ("file_token", "token"))).strip()
            token_hash = str(item.get("file_token_hash", "")).strip()
            if token and not token_hash:
                token_hash = _hash_token(token)
            if token and token_hash:
                tokens_by_hash[token_hash] = token
    return tokens_by_hash


def load_runtime_token_context(path: str | Path) -> dict[str, Any]:
    """Load sensitive tokens into memory only; callers must never serialize this."""
    source_path = Path(path)
    if not source_path.exists():
        raise ValueError(
            f"Feishu multi-download blocked: token source does not exist: {source_path}"
        )
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    message_id = str(payload.get("message_id", "")).strip() if isinstance(payload, dict) else ""
    if not message_id:
        raise ValueError(
            "Feishu multi-download blocked: token source message_id is required."
        )
    tokens_by_hash = _token_context_from_mapping(payload) if isinstance(payload, dict) else {}
    if not tokens_by_hash:
        for attachment in _attachment_list(payload):
            token = str(_first_non_empty(attachment, ("file_token", "token"))).strip()
            if token:
                tokens_by_hash[_hash_token(token)] = token
    if not tokens_by_hash:
        raise ValueError(
            "Feishu multi-download blocked: token source has no attachment tokens."
        )
    return {"message_id": message_id, "tokens_by_hash": tokens_by_hash}


def sanitize_error(error: Exception | str, secrets: Sequence[str]) -> str:
    text = str(error)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def _supported_tasks(plan: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for task in plan["download_tasks"]:
        if not isinstance(task, dict):
            raise ValueError(
                "Feishu multi-download blocked: each download task must be an object."
            )
        if task.get("supported") is True:
            tasks.append(task)
    return tasks


def _base_result(task: dict[str, Any], status: str = "disabled") -> dict[str, Any]:
    target_path = str(task.get("target_path", ""))
    return {
        "attachment_index": task.get("attachment_index"),
        "filename": str(task.get("filename", "")),
        "target_path": target_path,
        "supported": task.get("supported") is True,
        "download_status": status,
        "file_token_redacted": "REDACTED_FILE_TOKEN",
        "file_token_hash": str(task.get("file_token_hash", "")),
        "size_bytes_expected": int(task.get("size_bytes_expected", 0) or 0),
        "size_bytes_downloaded": 0,
        "exists": False,
        "error": None,
    }


def _base_receipt(tasks: list[dict[str, Any]], enabled: bool) -> dict[str, Any]:
    return {
        "mode": MODE,
        "real_download_enabled": enabled,
        "real_feishu_api_called": False,
        "real_download_performed": False,
        "download_status": "pending" if enabled else "disabled",
        "download_task_count": len(tasks),
        "attempted_download_count": 0,
        "success_count": 0,
        "disabled_count": len(tasks) if not enabled else 0,
        "error_count": 0,
        "downloaded_input_files": [],
        "download_results": [_base_result(task) for task in tasks],
        "error": None,
    }


class FeishuMultiAttachmentDownloadClient:
    """Minimal isolated Feishu client for downloading message resources only."""

    def __init__(self) -> None:
        self._tenant_access_token = ""

    def _access_token(self, app_id: str, app_secret: str) -> str:
        if self._tenant_access_token:
            return self._tenant_access_token
        import requests

        response = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": app_id, "app_secret": app_secret},
            timeout=(5, 20),
        )
        payload = response.json()
        if not (200 <= response.status_code < 300) or payload.get("code", 0) != 0:
            raise RuntimeError("failed to get Feishu tenant access token.")
        token = str(payload.get("tenant_access_token") or "")
        if not token:
            raise RuntimeError("failed to get Feishu tenant access token: empty token.")
        self._tenant_access_token = token
        return token

    def download_file(
        self,
        *,
        app_id: str,
        app_secret: str,
        message_id: str,
        file_token: str,
        target_path: str,
    ) -> None:
        import requests

        access_token = self._access_token(app_id, app_secret)
        response = requests.get(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_token}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"type": "file"},
            timeout=(5, 60),
        )
        if not (200 <= response.status_code < 300):
            raise RuntimeError(
                f"Feishu attachment download failed: status={response.status_code}."
            )
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f"{target.name}.part")
        temporary.write_bytes(response.content)
        temporary.replace(target)


def _blocked_receipt(
    receipt: dict[str, Any], error: str, *, disabled: bool = False
) -> dict[str, Any]:
    status = "disabled" if disabled else "error"
    receipt["download_status"] = status
    receipt["error"] = error
    receipt["disabled_count"] = receipt["download_task_count"] if disabled else 0
    receipt["error_count"] = 0 if disabled else receipt["download_task_count"]
    for result in receipt["download_results"]:
        result["download_status"] = status
        result["error"] = None if disabled else error
    return receipt


def run_multi_download(
    plan: dict[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
    token_context: dict[str, Any] | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    """Download supported tasks only. Failures are isolated per attachment."""
    env = environ if environ is not None else os.environ
    enabled = is_real_download_enabled(env)
    tasks = _supported_tasks(plan)
    receipt = _base_receipt(tasks, enabled)
    if not tasks:
        return _blocked_receipt(
            receipt, "Feishu multi-download blocked: no supported download tasks."
        )
    if not enabled:
        return receipt

    app_id = env.get(APP_ID_ENV, "").strip()
    app_secret = env.get(APP_SECRET_ENV, "").strip()
    if not app_id or not app_secret:
        return _blocked_receipt(
            receipt,
            "Feishu multi-download blocked: Feishu app credentials are required.",
        )
    if not token_context:
        return _blocked_receipt(
            receipt,
            "Feishu multi-download blocked: runtime token source is required for real download.",
        )
    message_id = str(token_context.get("message_id", "")).strip()
    tokens_by_hash = token_context.get("tokens_by_hash")
    if not message_id or not isinstance(tokens_by_hash, dict):
        return _blocked_receipt(
            receipt,
            "Feishu multi-download blocked: runtime token source is invalid.",
        )

    downloader = client or FeishuMultiAttachmentDownloadClient()
    results: list[dict[str, Any]] = []
    for task in tasks:
        result = _base_result(task, status="error")
        token_hash = str(task.get("file_token_hash", ""))
        file_token = str(tokens_by_hash.get(token_hash, ""))
        secrets = [app_id, app_secret, message_id, file_token]
        if not file_token:
            result["error"] = "Feishu attachment token is unavailable for this task."
            results.append(result)
            continue

        receipt["attempted_download_count"] += 1
        receipt["real_feishu_api_called"] = True
        try:
            downloader.download_file(
                app_id=app_id,
                app_secret=app_secret,
                message_id=message_id,
                file_token=file_token,
                target_path=result["target_path"],
            )
            path = Path(result["target_path"])
            exists = path.exists() and path.is_file()
            size = path.stat().st_size if exists else 0
            suffix = path.suffix.lower()
            if not exists:
                raise RuntimeError("Downloaded attachment does not exist.")
            if size <= 0:
                raise RuntimeError("Downloaded attachment is empty.")
            if suffix not in SUPPORTED_SUFFIXES:
                raise RuntimeError("Downloaded attachment suffix is unsupported.")
            result.update(
                {
                    "download_status": "downloaded",
                    "size_bytes_downloaded": size,
                    "exists": True,
                    "error": None,
                }
            )
            receipt["downloaded_input_files"].append(str(path))
        except Exception as exc:
            result["error"] = sanitize_error(exc, secrets)
        results.append(result)

    receipt["download_results"] = results
    receipt["success_count"] = sum(
        result["download_status"] == "downloaded" for result in results
    )
    receipt["error_count"] = sum(
        result["download_status"] == "error" for result in results
    )
    receipt["disabled_count"] = 0
    receipt["real_download_performed"] = receipt["success_count"] > 0
    if receipt["success_count"] == len(tasks):
        receipt["download_status"] = "downloaded"
    elif receipt["success_count"] > 0:
        receipt["download_status"] = "partial"
    else:
        receipt["download_status"] = "error"
    return receipt


def build_downloaded_inputs(receipt: dict[str, Any]) -> dict[str, Any]:
    files = list(receipt["downloaded_input_files"])
    quoted_inputs = " ".join(shlex.quote(path) for path in files)
    ready = bool(files) and all(
        Path(path).exists()
        and Path(path).is_file()
        and Path(path).stat().st_size > 0
        and Path(path).suffix.lower() in SUPPORTED_SUFFIXES
        for path in files
    )
    return {
        "mode": INPUTS_MODE,
        "ready_for_multi_file_batch_runner": ready,
        "downloaded_input_files": files,
        "next_command": (
            "python3 -m product_intel.multi_file_batch_runner "
            f"--inputs {quoted_inputs} --source auto --market de "
            "--output-dir product_intel/output_multi_file_from_feishu"
            if files
            else ""
        ),
    }


def build_summary(receipt: dict[str, Any]) -> dict[str, Any]:
    inputs = build_downloaded_inputs(receipt)
    return {
        "mode": MODE,
        "real_download_enabled": receipt["real_download_enabled"],
        "real_feishu_api_called": receipt["real_feishu_api_called"],
        "real_download_performed": receipt["real_download_performed"],
        "download_status": receipt["download_status"],
        "download_task_count": receipt["download_task_count"],
        "attempted_download_count": receipt["attempted_download_count"],
        "success_count": receipt["success_count"],
        "disabled_count": receipt["disabled_count"],
        "error_count": receipt["error_count"],
        "ready_for_multi_file_batch_runner": inputs[
            "ready_for_multi_file_batch_runner"
        ],
        "downloaded_input_files": inputs["downloaded_input_files"],
        "next_command": inputs["next_command"],
        "error": receipt["error"],
    }


def summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Product Intel v1.21 Real Feishu Multi-attachment Download Summary",
        "",
        f"- real_download_enabled：{str(summary['real_download_enabled']).lower()}",
        f"- real_feishu_api_called：{str(summary['real_feishu_api_called']).lower()}",
        f"- real_download_performed：{str(summary['real_download_performed']).lower()}",
        f"- download_status：{summary['download_status']}",
        f"- download_task_count：{summary['download_task_count']}",
        f"- attempted_download_count：{summary['attempted_download_count']}",
        f"- success_count：{summary['success_count']}",
        f"- disabled_count：{summary['disabled_count']}",
        f"- error_count：{summary['error_count']}",
        (
            "- ready_for_multi_file_batch_runner："
            f"{str(summary['ready_for_multi_file_batch_runner']).lower()}"
        ),
        "",
        "## 已下载输入文件",
        "",
    ]
    lines.extend(f"- {path}" for path in summary["downloaded_input_files"])
    if not summary["downloaded_input_files"]:
        lines.append("- 无")
    if summary["next_command"]:
        lines.extend(["", "## 下一步", "", f"`{summary['next_command']}`"])
    if summary["error"]:
        lines.extend(["", "## 阻断原因", "", f"- {summary['error']}"])
    lines.append("")
    return "\n".join(lines)


def write_outputs(
    receipt: dict[str, Any], output_dir: str | Path
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    summary = build_summary(receipt)
    inputs = build_downloaded_inputs(receipt)
    paths = {
        "receipt_json": output / "feishu_multi_attachment_download_real_receipt.json",
        "summary_json": output / "feishu_multi_attachment_download_real_summary.json",
        "summary_md": output / "feishu_multi_attachment_download_real_summary.md",
        "downloaded_files_csv": output / "feishu_multi_attachment_downloaded_files.csv",
        "downloaded_inputs_json": output / "feishu_multi_attachment_downloaded_inputs.json",
    }
    paths["receipt_json"].write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    paths["summary_json"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    paths["summary_md"].write_text(summary_markdown(summary), encoding="utf-8")
    with paths["downloaded_files_csv"].open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for result in receipt["download_results"]:
            writer.writerow({field: result.get(field, "") for field in CSV_FIELDS})
    paths["downloaded_inputs_json"].write_text(
        json.dumps(inputs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-plan", required=True)
    parser.add_argument(
        "--runtime-token-source",
        help="Sensitive runtime token source JSON. Required only when real download is enabled.",
    )
    parser.add_argument(
        "--attachments-json",
        help="Raw Feishu attachment event JSON used as runtime token source.",
    )
    parser.add_argument(
        "--token-source-json",
        help="Deprecated alias for --runtime-token-source.",
    )
    parser.add_argument("--output-dir", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    env = os.environ
    token_context = None
    if is_real_download_enabled(env):
        source_path = (
            args.runtime_token_source
            or args.attachments_json
            or args.token_source_json
        )
        if source_path:
            token_context = load_runtime_token_context(source_path)
    receipt = run_multi_download(
        load_download_plan(args.download_plan),
        environ=env,
        token_context=token_context,
    )
    write_outputs(receipt, args.output_dir)
    print(json.dumps(build_summary(receipt), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
