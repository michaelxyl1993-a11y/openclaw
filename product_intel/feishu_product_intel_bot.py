"""Feishu file trigger bot for Product Intel.

This bot is intentionally separate from PublishKit and Video Director. It only
handles the closed loop: receive a CSV/Excel file message, download the file,
run Product Intel, upload result files, and reply with a structured summary.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from flask import Flask, jsonify, request

from .feishu_private_event_capture import capture_private_attachment_event
from .job_queue import enqueue_job, start_worker
from .service_handler import run_product_intel_job


SERVICE_NAME = "product_intel_feishu_bot"
DEFAULT_PORT = 8788
TOKEN_CACHE: dict[str, Any] = {"token": "", "expires_at": 0.0}
PROCESSED_MESSAGE_IDS: set[str] = set()
PROCESSED_MESSAGE_ORDER: list[str] = []
IN_FLIGHT_DEDUPE_KEYS: set[str] = set()
ACTIVE_FILE_KEYS: dict[str, str] = {}
JOB_STATUSES: dict[str, dict[str, Any]] = {}
DEDUPE_LOCK = threading.Lock()
MAX_PROCESSED_MESSAGE_IDS = 1000

app = Flask(__name__)


class ProductIntelJobError(RuntimeError):
    """User-facing background job failure."""

    def __init__(self, reason: str, suggestion: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.suggestion = suggestion


def generate_job_id() -> str:
    return f"pi_{datetime.now().strftime('%Y%m%d')}_{secrets.token_hex(3)}"


def structured_log(event: str, job_id: str = "", info: dict[str, str] | None = None, **fields: Any) -> None:
    context = info or {}
    values = {
        "job_id": job_id,
        "message_id": context.get("message_id", ""),
        "event_id": context.get("event_id", ""),
        "chat_id": context.get("chat_id", ""),
        "file_name": context.get("file_name", ""),
        "file_type": Path(context.get("file_name", "")).suffix.lower().lstrip("."),
        **fields,
    }
    details = " ".join(f"{key}={str(value)[:500]!r}" for key, value in values.items() if value not in ("", None))
    print(f"[product-intel-feishu] {event} {details}".rstrip())


def safe_filename(name: str) -> str:
    base = Path(str(name or "uploaded.csv")).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return cleaned or "uploaded.csv"


def is_csv_file(file_name: str) -> bool:
    return str(file_name or "").strip().lower().endswith(".csv")


def is_supported_product_file(file_name: str) -> bool:
    return str(file_name or "").strip().lower().endswith((".csv", ".xlsx", ".xls"))


def parse_json_maybe(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def first_non_empty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def extract_event_info(payload: dict[str, Any]) -> dict[str, str]:
    event = payload.get("event", {}) if isinstance(payload.get("event", {}), dict) else {}
    header = payload.get("header", {}) if isinstance(payload.get("header", {}), dict) else {}
    message = event.get("message", {}) if isinstance(event.get("message", {}), dict) else {}
    content = parse_json_maybe(message.get("content"))
    file_info = parse_json_maybe(message.get("file"))

    message_type = first_non_empty(
        message.get("message_type"),
        message.get("msg_type"),
        content.get("message_type"),
        content.get("msg_type"),
    )
    file_key = first_non_empty(
        message.get("file_key"),
        message.get("file_token"),
        message.get("file_id"),
        file_info.get("file_key"),
        file_info.get("file_token"),
        file_info.get("file_id"),
        content.get("file_key"),
        content.get("file_token"),
        content.get("file_id"),
        content.get("key"),
    )
    file_name = first_non_empty(
        message.get("file_name"),
        message.get("name"),
        file_info.get("file_name"),
        file_info.get("name"),
        content.get("file_name"),
        content.get("name"),
        content.get("fileName"),
    )

    return {
        "event_type": first_non_empty(header.get("event_type"), payload.get("event_type"), payload.get("type")),
        "event_id": first_non_empty(header.get("event_id"), payload.get("uuid"), payload.get("event_id")),
        "chat_id": first_non_empty(message.get("chat_id"), event.get("chat_id"), content.get("chat_id")),
        "chat_type": first_non_empty(message.get("chat_type"), event.get("chat_type"), content.get("chat_type")),
        "message_id": first_non_empty(message.get("message_id"), message.get("messageId"), event.get("message_id")),
        "message_type": message_type,
        "file_key": file_key,
        "file_name": file_name,
        "text": first_non_empty(content.get("text"), message.get("text"), payload.get("text")),
    }


def dedupe_key_for(info: dict[str, str]) -> str:
    return first_non_empty(info.get("message_id"), info.get("event_id"))


def dedupe_result_for(key: str) -> str:
    if not key:
        return "missing_key"
    with DEDUPE_LOCK:
        return "duplicate" if key in PROCESSED_MESSAGE_IDS or key in IN_FLIGHT_DEDUPE_KEYS else "new"


def claim_dedupe_key(key: str) -> None:
    if not key:
        return
    with DEDUPE_LOCK:
        IN_FLIGHT_DEDUPE_KEYS.add(key)


def release_dedupe_key(key: str) -> None:
    if not key:
        return
    with DEDUPE_LOCK:
        IN_FLIGHT_DEDUPE_KEYS.discard(key)


def active_file_job(file_key: str) -> str:
    if not file_key:
        return ""
    with DEDUPE_LOCK:
        return ACTIVE_FILE_KEYS.get(file_key, "")


def set_job_status(job_id: str, status: str, info: dict[str, str], error: str = "") -> None:
    if not job_id:
        return
    with DEDUPE_LOCK:
        JOB_STATUSES[job_id] = {
            "status": status,
            "message_id": info.get("message_id", ""),
            "event_id": info.get("event_id", ""),
            "chat_id": info.get("chat_id", ""),
            "file_key": info.get("file_key", ""),
            "file_name": info.get("file_name", ""),
            "error": error,
            "updated_at": time.time(),
        }


def reserve_file_key(file_key: str, job_id: str) -> None:
    if not file_key or not job_id:
        return
    with DEDUPE_LOCK:
        ACTIVE_FILE_KEYS[file_key] = job_id


def release_file_key(file_key: str, job_id: str) -> None:
    if not file_key:
        return
    with DEDUPE_LOCK:
        if ACTIVE_FILE_KEYS.get(file_key) == job_id:
            ACTIVE_FILE_KEYS.pop(file_key, None)


def response_body_preview(result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return ""
    if result.get("error"):
        return str(result.get("error"))[:300]
    data = result.get("data")
    if data:
        return json.dumps(data, ensure_ascii=False)[:300]
    return ""


def log_private_attachment_capture(summary: dict[str, Any]) -> None:
    if not summary:
        return
    print(
        "[product-intel-feishu] private_attachment_event_capture "
        f"status={summary.get('status', '')} "
        f"attachment_count={summary.get('attachment_count', 0)} "
        f"message_id_hash={str(summary.get('message_id_hash', ''))[:16]} "
        f"file_token_hashes={','.join(str(value)[:16] for value in summary.get('file_token_hashes', []))} "
        f"errors={';'.join(str(value) for value in summary.get('errors', []))}"
    )


def log_event_decision(
    info: dict[str, str],
    dedupe_key: str,
    dedupe_result: str,
    action: str,
    reply_result: dict[str, Any] | None = None,
    exc: BaseException | None = None,
) -> None:
    status_code = ""
    response_body = ""
    if reply_result:
        status_code = str(reply_result.get("status_code", ""))
        response_body = response_body_preview(reply_result)
    print(
        "[product-intel-feishu] "
        f"event_type={info.get('event_type', '')} "
        f"event_id={info.get('event_id', '')} "
        f"message_id={info.get('message_id', '')} "
        f"chat_id={info.get('chat_id', '')} "
        f"message_type={info.get('message_type', '')} "
        f"file_name={info.get('file_name', '')} "
        f"text_preview={info.get('text', '')[:80]!r} "
        f"dedupe_key={dedupe_key} "
        f"dedupe_result={dedupe_result} "
        f"action={action} "
        f"reply_status_code={status_code} "
        f"reply_response_body={response_body[:300]!r}"
    )
    if exc is not None:
        print("[product-intel-feishu] exception traceback:")
        traceback.print_exception(type(exc), exc, exc.__traceback__)


def mark_processed(message_id: str) -> None:
    if not message_id:
        return
    with DEDUPE_LOCK:
        IN_FLIGHT_DEDUPE_KEYS.discard(message_id)
        PROCESSED_MESSAGE_IDS.add(message_id)
        PROCESSED_MESSAGE_ORDER.append(message_id)
        while len(PROCESSED_MESSAGE_ORDER) > MAX_PROCESSED_MESSAGE_IDS:
            old_id = PROCESSED_MESSAGE_ORDER.pop(0)
            PROCESSED_MESSAGE_IDS.discard(old_id)


def get_tenant_access_token() -> str:
    now = time.time()
    cached = str(TOKEN_CACHE.get("token") or "")
    if cached and float(TOKEN_CACHE.get("expires_at") or 0) > now + 60:
        return cached

    app_id = os.getenv("FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise RuntimeError("FEISHU_APP_ID or FEISHU_APP_SECRET is not configured")

    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": app_id, "app_secret": app_secret}, timeout=(5, 20))
    text = resp.text[:500]
    if resp.status_code >= 400:
        raise RuntimeError(f"failed to get tenant_access_token: status={resp.status_code} body={text}")
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"failed to get tenant_access_token: body={text}")
    token = str(data.get("tenant_access_token") or "")
    if not token:
        raise RuntimeError("failed to get tenant_access_token: empty token")
    expire = int(data.get("expire") or 7200)
    TOKEN_CACHE["token"] = token
    TOKEN_CACHE["expires_at"] = now + max(60, expire - 120)
    return token


def download_feishu_file(
    message_id: str,
    file_key: str,
    save_dir: str = "/tmp/product_intel_uploads",
    file_name: str | None = None,
) -> str:
    if not message_id or not file_key:
        raise ValueError("message_id and file_key are required to download Feishu file")
    token = get_tenant_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_key}"
    resp = requests.get(url, headers=headers, params={"type": "file"}, timeout=(5, 60))
    if resp.status_code >= 400:
        raise RuntimeError(f"failed to download Feishu file: status={resp.status_code} body={resp.text[:500]}")

    directory = Path(save_dir)
    directory.mkdir(parents=True, exist_ok=True)
    chosen_name = safe_filename(file_name or file_key)
    if not is_supported_product_file(chosen_name):
        chosen_name = f"{chosen_name}.csv"
    path = directory / f"{int(time.time())}_{chosen_name}"
    path.write_bytes(resp.content)
    return str(path)


def reply_feishu_text(chat_id: str, text: str) -> dict[str, Any]:
    if not chat_id:
        print("reply_feishu_text skipped: empty chat_id")
        return {"ok": False, "error": "empty chat_id"}
    try:
        token = get_tenant_access_token()
        url = "https://open.feishu.cn/open-apis/im/v1/messages"
        body = {
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        resp = requests.post(url, headers=headers, params={"receive_id_type": "chat_id"}, json=body, timeout=(5, 20))
        print(f"reply_feishu_text status={resp.status_code} body={resp.text[:500]}")
        data: dict[str, Any] = {}
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text[:500]}
        ok = 200 <= resp.status_code < 300 and data.get("code", 0) == 0
        if not ok:
            print(f"reply_feishu_text failed status={resp.status_code} body={resp.text[:500]}")
        return {"ok": ok, "status_code": resp.status_code, "data": data}
    except requests.RequestException as exc:
        print(f"reply_feishu_text request error: {exc}")
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        print(f"reply_feishu_text error: {exc}")
        return {"ok": False, "error": str(exc)}


def infer_feishu_file_type(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".xls", ".xlsx"}:
        return "xls"
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".doc", ".docx"}:
        return "doc"
    if suffix in {".ppt", ".pptx"}:
        return "ppt"
    if suffix in {".mp4", ".mov"}:
        return "mp4"
    return "stream"


def upload_file_to_feishu(chat_id: str, file_path: str, display_name: str | None = None) -> dict[str, Any]:
    """Upload a local file to Feishu and send it as a file message to chat_id."""
    path = Path(file_path)
    if not chat_id:
        return {"ok": False, "error": "empty chat_id"}
    if not path.exists() or not path.is_file():
        return {"ok": False, "error": f"file does not exist: {path}"}

    try:
        token = get_tenant_access_token()
        headers = {"Authorization": f"Bearer {token}"}
        upload_url = "https://open.feishu.cn/open-apis/im/v1/files"
        file_name = safe_filename(display_name or path.name)
        with path.open("rb") as file_obj:
            resp = requests.post(
                upload_url,
                headers=headers,
                data={"file_type": infer_feishu_file_type(path), "file_name": file_name},
                files={"file": (file_name, file_obj)},
                timeout=(5, 60),
            )
        print(f"upload_file_to_feishu upload status={resp.status_code} body={resp.text[:500]}")
        try:
            data = resp.json()
        except ValueError:
            data = {"raw": resp.text[:500]}
        if not (200 <= resp.status_code < 300) or data.get("code", 0) != 0:
            return {"ok": False, "status_code": resp.status_code, "data": data, "error": resp.text[:500]}

        file_key = str((data.get("data") or {}).get("file_key") or "")
        if not file_key:
            return {"ok": False, "status_code": resp.status_code, "data": data, "error": "empty file_key"}

        send_url = "https://open.feishu.cn/open-apis/im/v1/messages"
        body = {
            "receive_id": chat_id,
            "msg_type": "file",
            "content": json.dumps({"file_key": file_key}, ensure_ascii=False),
        }
        send_headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        send_resp = requests.post(
            send_url,
            headers=send_headers,
            params={"receive_id_type": "chat_id"},
            json=body,
            timeout=(5, 20),
        )
        print(f"upload_file_to_feishu send status={send_resp.status_code} body={send_resp.text[:500]}")
        try:
            send_data = send_resp.json()
        except ValueError:
            send_data = {"raw": send_resp.text[:500]}
        ok = 200 <= send_resp.status_code < 300 and send_data.get("code", 0) == 0
        return {
            "ok": ok,
            "file_key": file_key,
            "upload_status_code": resp.status_code,
            "send_status_code": send_resp.status_code,
            "data": send_data,
            "error": "" if ok else send_resp.text[:500],
        }
    except requests.RequestException as exc:
        print(f"upload_file_to_feishu request error: {exc}")
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        print(f"upload_file_to_feishu error: {exc}")
        return {"ok": False, "error": str(exc)}


def result_file_targets(output_files: dict[str, str]) -> dict[str, str]:
    return {
        "decision_table_csv": output_files.get("decision_table_csv", ""),
        "decision_table_md": output_files.get("decision_table_md", ""),
        "manager_payload_json": output_files.get("manager_payload_json", ""),
        "input_profile_md": output_files.get("csv_profile_md", ""),
    }


def upload_result_files(chat_id: str, output_files: dict[str, str]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for label, path in result_file_targets(output_files).items():
        if not path:
            results[label] = {"ok": False, "error": "missing output path"}
            continue
        print(f"uploading result file label={label} path={path}")
        results[label] = upload_file_to_feishu(chat_id, path, display_name=Path(path).name)
    return results


def upload_status_text(upload_results: dict[str, dict[str, Any]]) -> list[str]:
    lines = ["已尝试上传结果附件："]
    for label in ["decision_table_csv", "decision_table_md", "manager_payload_json", "input_profile_md"]:
        item = upload_results.get(label, {})
        if item.get("ok"):
            lines.append(f"- {label}：成功")
        else:
            error = str(item.get("error") or "失败")
            lines.append(f"- {label}：失败（{error[:120]}）")
    return lines


def short_ops_summary(summary_text: str, limit: int = 800) -> str:
    text = str(summary_text or "").strip()
    if text.startswith("运营摘要："):
        text = text[len("运营摘要：") :].lstrip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n完整分析请查看附件 manager_payload_json。"


def format_product_intel_reply(
    result: dict[str, Any],
    upload_results: dict[str, dict[str, Any]] | None = None,
    job_id: str = "",
) -> str:
    if result.get("ok"):
        profile = result.get("profile", {}) if isinstance(result.get("profile", {}), dict) else {}
        decision_summary = (
            result.get("decision_summary", {}) if isinstance(result.get("decision_summary", {}), dict) else {}
        )
        mapped_fields = profile.get("mapped_fields", {}) if isinstance(profile.get("mapped_fields", {}), dict) else {}
        mapped_count = sum(1 for value in mapped_fields.values() if value)
        warnings = profile.get("warnings", []) if isinstance(profile.get("warnings", []), list) else []
        file_type = str(profile.get("detected_file_type") or "").upper() or "UNKNOWN"
        sheet_name = str(profile.get("detected_sheet_name") or "-")
        lines = [
            "【Product Intel 商品分析完成】",
            f"job_id：{job_id}" if job_id else "",
            "",
            "任务类型：完整选品分析",
            f"文件类型：{file_type}",
            f"Sheet：{sheet_name}",
            f"输入行数：{profile.get('row_count', 0)}",
            f"已映射字段数：{mapped_count}",
            f"warnings 数量：{len(warnings)}",
            "",
            "决策分布：",
            f"main_push：{decision_summary.get('main_push_count', 0)}",
            f"small_test：{decision_summary.get('small_test_count', 0)}",
            f"hold：{decision_summary.get('hold_count', 0)}",
            f"reject：{decision_summary.get('reject_count', 0)}",
            "",
            "Top 5 商品：",
        ]
        top_products = decision_summary.get("top_products", [])
        if top_products:
            for product in top_products[:5]:
                lines.append(
                    f"{product.get('rank', '-')}. {product.get('opportunity_score', 0)} / "
                    f"{product.get('decision', '')} / {product.get('product_name', '')}"
                )
        else:
            lines.append("暂无 Top 商品。")

        manager_payload = (
            result.get("manager_payload", {}) if isinstance(result.get("manager_payload", {}), dict) else {}
        )
        llm_summary = (
            manager_payload.get("llm_summary", {}) if isinstance(manager_payload.get("llm_summary", {}), dict) else {}
        )
        manager_summary = (
            manager_payload.get("summary", {}) if isinstance(manager_payload.get("summary", {}), dict) else {}
        )
        risk_heavy_products = (
            manager_summary.get("risk_heavy_products", [])
            if isinstance(manager_summary.get("risk_heavy_products", []), list)
            else []
        )
        lines.extend(["", f"主要风险商品数：{len(risk_heavy_products)}"])
        summary_text = str(llm_summary.get("summary_text") or "").strip()
        if summary_text:
            lines.extend(["", "运营摘要：", short_ops_summary(summary_text)])

        lines.append("")
        lines.extend(upload_status_text(upload_results or {}))

        output_files = result.get("output_files", {}) if isinstance(result.get("output_files", {}), dict) else {}
        lines.extend(["", "本地输出路径（管理员排查用）："])
        for key in ["decision_table_csv", "decision_table_md", "manager_payload_json", "csv_profile_md"]:
            value = output_files.get(key)
            if value:
                lines.append(f"- {key}: {value}")
        return "\n".join(lines)

    errors = result.get("errors", [])
    error_text = "; ".join(str(item) for item in errors) if errors else "unknown error"
    job_line = f"\njob_id：{job_id}" if job_id else ""
    return f"【Product Intel 商品分析失败】{job_line}\n\n{result.get('summary_text', '')}\n\n错误：{error_text}"


def failure_reply_text(job_id: str, reason: str, suggestion: str = "") -> str:
    lines = ["【Product Intel 分析失败】", f"job_id：{job_id}", f"原因：{reason}"]
    if suggestion:
        lines.append(f"建议：{suggestion}")
    return "\n".join(lines)


def classify_job_error(exc: BaseException) -> tuple[str, str]:
    text = str(exc)
    lowered = text.lower()
    if isinstance(exc, ProductIntelJobError):
        return exc.reason, exc.suggestion
    if "download" in lowered or "下载" in text:
        return f"文件下载失败：{text}", "请重新上传文件；如果持续失败，请检查飞书文件下载权限。"
    if "sheet" in lowered:
        return "Excel 文件没有识别到有效商品 sheet", "请检查表头是否在第一行，或确认第一个非空 sheet 是否为商品表。"
    if "empty" in lowered or "no products" in lowered or "有效商品" in text:
        return "文件没有识别到有效商品行", "请检查表头是否在第一行，并确认至少有一行商品数据。"
    if "unsupported" in lowered or "不支持" in text:
        return f"文件格式不支持：{text}", "请上传 .csv、.xlsx 或 .xls 文件。"
    return f"Product Intel 分析异常：{text}", "请检查输入文件格式，或联系管理员查看任务日志。"


def process_file_event(info: dict[str, str], job_id: str = "") -> None:
    message_id = info.get("message_id", "")
    chat_id = info.get("chat_id", "")
    file_name = info.get("file_name", "")
    file_key = info.get("file_key", "")

    if not file_key:
        raise ProductIntelJobError("文件消息缺少 file_key", "请重新上传 CSV 或 Excel 文件。")
    if not is_supported_product_file(file_name):
        raise ProductIntelJobError("文件格式不支持", "请上传 .csv、.xlsx 或 .xls 文件。")

    structured_log("file_download_started", job_id, info, status="running", file_key=file_key)
    local_csv_path = download_feishu_file(message_id, file_key, file_name=file_name)
    structured_log("file_download_finished", job_id, info, status="success", local_path=local_csv_path)

    structured_log("analysis_started", job_id, info, status="running")
    result = run_product_intel_job(
        input_path=local_csv_path,
        source="auto",
        market="de",
        output_dir="product_intel/output",
        profile_only=False,
        request_meta={
            "source": "feishu",
            "chat_id": chat_id,
            "message_id": message_id,
            "file_name": file_name,
            "job_id": job_id,
        },
    )
    if not result.get("ok"):
        errors = result.get("errors", [])
        reason = "; ".join(str(item) for item in errors) if errors else "unknown analysis error"
        raise ProductIntelJobError(f"Product Intel 分析异常：{reason}", "请检查输入文件表头和有效商品行。")
    structured_log("analysis_finished", job_id, info, status="success")

    upload_results: dict[str, dict[str, Any]] = {}
    output_files = result.get("output_files", {}) if isinstance(result.get("output_files", {}), dict) else {}
    structured_log("upload_started", job_id, info, status="running")
    upload_results = upload_result_files(chat_id, output_files)
    failed_uploads = [label for label, item in upload_results.items() if not item.get("ok")]
    structured_log(
        "upload_finished",
        job_id,
        info,
        status="partial_failed" if failed_uploads else "success",
        failed_uploads=",".join(failed_uploads),
    )
    if failed_uploads:
        print(f"Product Intel upload warnings job_id={job_id} message_id={message_id} failed={failed_uploads}")

    reply_result = reply_feishu_text(chat_id, format_product_intel_reply(result, upload_results, job_id=job_id))
    structured_log(
        "reply_sent",
        job_id,
        info,
        status="success" if reply_result.get("ok") else "failed",
        reply_status_code=reply_result.get("status_code", ""),
        reply_response_body=response_body_preview(reply_result),
    )
    if not reply_result.get("ok"):
        raise ProductIntelJobError("飞书回复失败", response_body_preview(reply_result) or "请联系管理员查看任务日志。")


def process_background_job(job: dict[str, Any]) -> None:
    info = job.get("info", {}) if isinstance(job.get("info", {}), dict) else {}
    dedupe_key = str(job.get("dedupe_key") or "")
    dedupe_result = str(job.get("dedupe_result") or "new")
    action = str(job.get("action") or "ignored")
    job_id = str(job.get("job_id") or "")
    set_job_status(job_id, "running", info)
    structured_log("job_started", job_id, info, status="running", action=action, dedupe_key=dedupe_key or "missing_key")
    try:
        if action == "text_fallback":
            reply_result: dict[str, Any] = {}
            if info.get("chat_id"):
                reply_result = reply_feishu_text(info["chat_id"], "请上传 CSV 或 Excel 文件进行商品分析。")
            if reply_result.get("ok"):
                mark_processed(dedupe_key)
            else:
                release_dedupe_key(dedupe_key)
            print(f"text fallback replied message_id={info.get('message_id')} text_preview={info.get('text', '')[:120]}")
            log_event_decision(info, dedupe_key, dedupe_result, action, reply_result)
        elif action == "file_analysis":
            status_result = reply_feishu_text(
                info.get("chat_id", ""),
                f"已收到文件，正在分析，预计 10-30 秒返回结果。\njob_id：{job_id}",
            )
            structured_log(
                "reply_sent",
                job_id,
                info,
                status="received_notice_sent" if status_result.get("ok") else "received_notice_failed",
                reply_status_code=status_result.get("status_code", ""),
                reply_response_body=response_body_preview(status_result),
            )
            process_file_event(info, job_id=job_id)
            mark_processed(dedupe_key)
            log_event_decision(info, dedupe_key, dedupe_result, action)
        else:
            release_dedupe_key(dedupe_key)
            log_event_decision(info, dedupe_key, dedupe_result, "ignored")
        set_job_status(job_id, "success", info)
        release_file_key(info.get("file_key", ""), job_id)
        structured_log("job_finished", job_id, info, status="success", action=action)
    except Exception as exc:
        reason, suggestion = classify_job_error(exc)
        mark_processed(dedupe_key)
        release_file_key(info.get("file_key", ""), job_id)
        set_job_status(job_id, "failed", info, error=reason)
        structured_log("job_failed", job_id, info, status="failed", action=action, error=reason)
        traceback.print_exc()
        reply_result = {}
        if info.get("chat_id"):
            reply_result = reply_feishu_text(info["chat_id"], failure_reply_text(job_id, reason, suggestion))
        structured_log(
            "reply_sent",
            job_id,
            info,
            status="failure_notice_sent" if reply_result.get("ok") else "failure_notice_failed",
            reply_status_code=reply_result.get("status_code", ""),
            reply_response_body=response_body_preview(reply_result),
        )
        log_event_decision(info, dedupe_key, dedupe_result, action, reply_result, exc)


def enqueue_event_job(info: dict[str, str], dedupe_key: str, dedupe_result: str, action: str) -> str:
    job_id = generate_job_id() if action == "file_analysis" else ""
    claim_dedupe_key(dedupe_key)
    reserve_file_key(info.get("file_key", ""), job_id)
    set_job_status(job_id, "queued", info)
    try:
        enqueue_job(
            {
                "info": info,
                "event_id": info.get("event_id", ""),
                "message_id": info.get("message_id", ""),
                "dedupe_key": dedupe_key,
                "dedupe_result": dedupe_result,
                "action": action,
                "job_id": job_id,
            },
            process_background_job,
        )
        structured_log("job_enqueued", job_id, info, status="queued", action=action, dedupe_key=dedupe_key or "missing_key")
        return job_id
    except Exception:
        release_dedupe_key(dedupe_key)
        release_file_key(info.get("file_key", ""), job_id)
        set_job_status(job_id, "failed", info, error="enqueue failed")
        raise


@app.get("/health")
def health() -> Any:
    return jsonify({"ok": True, "service": SERVICE_NAME})


@app.post("/feishu/events")
def feishu_events() -> Any:
    payload = request.get_json(silent=True) or {}
    if payload.get("type") == "url_verification" and payload.get("challenge"):
        return jsonify({"challenge": payload.get("challenge")})
    if payload.get("challenge"):
        return jsonify({"challenge": payload.get("challenge")})

    info = extract_event_info(payload)
    try:
        capture_summary = capture_private_attachment_event(payload)
        if capture_summary.get("status") != "no_attachments":
            log_private_attachment_capture(capture_summary)
    except Exception as exc:
        print(f"[product-intel-feishu] private_attachment_event_capture_failed error={str(exc)[:200]!r}")
    dedupe_key = dedupe_key_for(info)
    dedupe_result = dedupe_result_for(dedupe_key)
    print(
        "[product-intel-feishu] "
        f"event_received event_type={info.get('event_type', '')} event_id={info.get('event_id', '')} "
        f"message_id={info.get('message_id', '')} chat_id={info.get('chat_id', '')} "
        f"message_type={info.get('message_type', '')} file_name={info.get('file_name', '')} "
        f"text_preview={info.get('text', '')[:80]!r} dedupe_key={dedupe_key or 'missing_key'} "
        f"dedupe_result={dedupe_result}"
    )
    if dedupe_result == "missing_key":
        print("[product-intel-feishu] warning: missing message_id and event_id; event will be processed without dedupe")

    event_type = info.get("event_type", "")
    if event_type and event_type not in {"im.message.receive_v1", "message"}:
        log_event_decision(info, dedupe_key, dedupe_result, "ignored")
        print(f"[product-intel-feishu] event_ack dedupe_key={dedupe_key or 'missing_key'} action=ignored")
        return jsonify({"ok": True, "ignored": True})

    if dedupe_result == "duplicate":
        print(f"[product-intel-feishu] duplicate_skipped dedupe_key={dedupe_key}")
        log_event_decision(info, dedupe_key, dedupe_result, "ignored")
        print(f"[product-intel-feishu] event_ack dedupe_key={dedupe_key} action=ignored")
        return jsonify({"ok": True, "duplicate": True})

    message_type = info.get("message_type", "").lower()
    if message_type == "text":
        enqueue_event_job(info, dedupe_key, dedupe_result, "text_fallback")
        print(f"[product-intel-feishu] event_ack dedupe_key={dedupe_key or 'missing_key'} action=text_fallback")
        return jsonify({"ok": True, "fallback": "text"})

    if message_type and message_type not in {"file", "post"} and not info.get("file_key"):
        enqueue_event_job(info, dedupe_key, dedupe_result, "text_fallback")
        print(f"[product-intel-feishu] event_ack dedupe_key={dedupe_key or 'missing_key'} action=text_fallback")
        return jsonify({"ok": True, "ignored": True})

    try:
        active_job_id = active_file_job(info.get("file_key", ""))
        if active_job_id:
            structured_log(
                "duplicate_skipped",
                active_job_id,
                info,
                status="in_flight_file_key",
                dedupe_key=dedupe_key or "missing_key",
            )
            print(f"[product-intel-feishu] event_ack dedupe_key={dedupe_key or 'missing_key'} action=ignored")
            return jsonify({"ok": True, "duplicate": True})
        job_id = enqueue_event_job(info, dedupe_key, dedupe_result, "file_analysis")
        print(
            f"[product-intel-feishu] event_ack job_id={job_id} "
            f"dedupe_key={dedupe_key or 'missing_key'} action=file_analysis"
        )
    except Exception as exc:
        print(f"failed to enqueue Product Intel file event: {exc}")
        traceback.print_exc()
        log_event_decision(info, dedupe_key, dedupe_result, "file_analysis", exc=exc)
        print(f"[product-intel-feishu] event_ack dedupe_key={dedupe_key or 'missing_key'} action=file_analysis_failed")
    return jsonify({"ok": True})


def main() -> None:
    start_worker()
    port = int(os.getenv("PRODUCT_INTEL_BOT_PORT", str(DEFAULT_PORT)))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
