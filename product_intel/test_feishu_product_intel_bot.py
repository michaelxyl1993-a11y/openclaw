"""Smoke tests for the Product Intel Feishu CSV bot."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from . import feishu_product_intel_bot as bot
from .feishu_product_intel_bot import (
    app,
    extract_event_info,
    format_product_intel_reply,
    infer_feishu_file_type,
    is_csv_file,
    is_supported_product_file,
    safe_filename,
    upload_file_to_feishu,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self) -> dict[str, object]:
        return self._payload


def main() -> None:
    if not is_csv_file("abc.csv"):
        raise AssertionError("abc.csv should be detected as CSV")
    if not is_csv_file("ABC.CSV"):
        raise AssertionError("ABC.CSV should be detected as CSV")
    if is_csv_file("abc.xlsx"):
        raise AssertionError("abc.xlsx should not be detected as CSV")
    if not is_supported_product_file("abc.xlsx"):
        raise AssertionError("abc.xlsx should be supported")
    if not is_supported_product_file("abc.xls"):
        raise AssertionError("abc.xls should be supported")
    if is_supported_product_file("abc.pdf"):
        raise AssertionError("abc.pdf should not be supported")

    cleaned = safe_filename("../a.csv")
    if ".." in cleaned or "/" in cleaned or "\\" in cleaned:
        raise AssertionError(f"unsafe filename was not cleaned: {cleaned}")
    if not cleaned.endswith(".csv"):
        raise AssertionError(f"safe filename should preserve extension: {cleaned}")
    if infer_feishu_file_type("result.xlsx") != "xls":
        raise AssertionError("xlsx should map to Feishu xls file_type")
    if infer_feishu_file_type("result.csv") != "stream":
        raise AssertionError("csv should map to Feishu stream file_type")

    mock_event = {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1", "event_id": "evt_test"},
        "event": {
            "message": {
                "message_id": "om_test",
                "chat_id": "oc_test",
                "message_type": "file",
                "content": json.dumps({"file_key": "file_v2_test", "file_name": "products.xlsx"}),
            }
        },
    }
    info = extract_event_info(mock_event)
    expected = {
        "chat_id": "oc_test",
        "message_id": "om_test",
        "message_type": "file",
        "file_key": "file_v2_test",
        "file_name": "products.xlsx",
    }
    for key, value in expected.items():
        if info.get(key) != value:
            raise AssertionError(f"extract_event_info {key}={info.get(key)!r}, expected {value!r}")

    with app.test_client() as client:
        resp = client.get("/health")
        if resp.status_code != 200:
            raise AssertionError(f"health status={resp.status_code}")
        data = resp.get_json()
        if data != {"ok": True, "service": "product_intel_feishu_bot"}:
            raise AssertionError(f"unexpected health response: {data}")

        challenge_resp = client.post(
            "/feishu/events",
            json={"type": "url_verification", "challenge": "challenge_test"},
        )
        if challenge_resp.status_code != 200 or challenge_resp.get_json() != {"challenge": "challenge_test"}:
            raise AssertionError(f"unexpected challenge response: {challenge_resp.get_json()}")

        bot.PROCESSED_MESSAGE_IDS.clear()
        bot.PROCESSED_MESSAGE_ORDER.clear()
        bot.IN_FLIGHT_DEDUPE_KEYS.clear()
        bot.ACTIVE_FILE_KEYS.clear()
        bot.JOB_STATUSES.clear()
        sent_texts: list[tuple[str, str]] = []
        original_reply = bot.reply_feishu_text
        original_enqueue = bot.enqueue_job
        queued_jobs: list[tuple[dict[str, object], object]] = []
        try:
            bot.reply_feishu_text = (  # type: ignore[assignment]
                lambda chat_id, text: sent_texts.append((chat_id, text))
                or {"ok": True, "status_code": 200, "data": {"code": 0}}
            )
            bot.enqueue_job = lambda job, handler: queued_jobs.append((job, handler))  # type: ignore[assignment]

            def post_text(message_id: str, event_id: str, text: str):
                return client.post(
                    "/feishu/events",
                    json={
                        "schema": "2.0",
                        "header": {"event_type": "im.message.receive_v1", "event_id": event_id},
                        "event": {
                            "message": {
                                "message_id": message_id,
                                "chat_id": "oc_text_test",
                                "message_type": "text",
                                "content": json.dumps({"text": text}),
                            }
                        },
                    },
                )

            text_resp = post_text("om_text_test_1", "evt_text_test_1", "hi")
            job, handler = queued_jobs.pop(0)
            handler(job)  # type: ignore[operator]
            text_resp_2 = post_text("om_text_test_2", "evt_text_test_2", "hi")
            job, handler = queued_jobs.pop(0)
            handler(job)  # type: ignore[operator]
            text_resp_3 = post_text("om_text_test_3", "evt_text_test_3", "hii")
            job, handler = queued_jobs.pop(0)
            handler(job)  # type: ignore[operator]
            duplicate_resp = post_text("om_text_test_3", "evt_text_test_3_retry", "hiii")
        finally:
            bot.reply_feishu_text = original_reply  # type: ignore[assignment]
            bot.enqueue_job = original_enqueue  # type: ignore[assignment]
        if text_resp.status_code != 200 or text_resp_2.status_code != 200 or text_resp_3.status_code != 200:
            raise AssertionError("text fallback responses should return 200")
        if duplicate_resp.status_code != 200:
            raise AssertionError(f"duplicate text fallback status={duplicate_resp.status_code}")
        if len(sent_texts) != 3:
            raise AssertionError(f"three unique text messages should send three replies, got {sent_texts}")
        if sent_texts[0][0] != "oc_text_test":
            raise AssertionError(f"text fallback replied to wrong chat: {sent_texts}")
        for _chat_id, text in sent_texts:
            if "请上传 CSV 或 Excel 文件进行商品分析。" not in text:
                raise AssertionError(f"text fallback reply text is wrong: {text}")

        file_events: list[dict[str, str]] = []
        original_process_file = bot.process_file_event
        original_enqueue = bot.enqueue_job
        original_reply = bot.reply_feishu_text
        queued_jobs = []
        try:
            bot.PROCESSED_MESSAGE_IDS.clear()
            bot.PROCESSED_MESSAGE_ORDER.clear()
            bot.IN_FLIGHT_DEDUPE_KEYS.clear()
            bot.ACTIVE_FILE_KEYS.clear()
            bot.JOB_STATUSES.clear()

            def fake_process_file_event(info: dict[str, str], job_id: str = "") -> None:
                file_events.append(info)

            bot.process_file_event = fake_process_file_event  # type: ignore[assignment]
            bot.enqueue_job = lambda job, handler: queued_jobs.append((job, handler))  # type: ignore[assignment]
            bot.reply_feishu_text = lambda chat_id, text: {"ok": True, "status_code": 200, "data": {"code": 0}}  # type: ignore[assignment]
            started_at = time.monotonic()
            file_resp = client.post(
                "/feishu/events",
                json={
                    "schema": "2.0",
                    "header": {"event_type": "im.message.receive_v1", "event_id": "evt_file_test"},
                    "event": {
                        "message": {
                            "message_id": "om_file_test",
                            "chat_id": "oc_file_test",
                            "message_type": "file",
                            "content": json.dumps({"file_key": "file_key_test", "file_name": "products.xlsx"}),
                        }
                    },
                },
            )
            elapsed = time.monotonic() - started_at
            duplicate_file_resp = client.post(
                "/feishu/events",
                json={
                    "schema": "2.0",
                    "header": {"event_type": "im.message.receive_v1", "event_id": "evt_file_test_retry"},
                    "event": {
                        "message": {
                            "message_id": "om_file_test",
                            "chat_id": "oc_file_test",
                            "message_type": "file",
                            "content": json.dumps({"file_key": "file_key_test", "file_name": "products.xlsx"}),
                        }
                    },
                },
            )
            if file_events:
                raise AssertionError("file analysis should not run in HTTP request thread")
            if len(queued_jobs) != 1:
                raise AssertionError(f"duplicate file event should enqueue once, got {queued_jobs}")
            job, handler = queued_jobs.pop(0)
            handler(job)  # type: ignore[operator]
        finally:
            bot.process_file_event = original_process_file  # type: ignore[assignment]
            bot.enqueue_job = original_enqueue  # type: ignore[assignment]
            bot.reply_feishu_text = original_reply  # type: ignore[assignment]
        if file_resp.status_code != 200:
            raise AssertionError(f"file event status={file_resp.status_code}")
        if duplicate_file_resp.status_code != 200:
            raise AssertionError(f"duplicate file event status={duplicate_file_resp.status_code}")
        if elapsed >= 1:
            raise AssertionError(f"file ACK should return in under 1 second, took {elapsed:.3f}s")
        if len(file_events) != 1:
            raise AssertionError(f"file message should go to file analysis once, got {file_events}")
        if file_events[0].get("file_name") != "products.xlsx":
            raise AssertionError(f"file event did not preserve file_name: {file_events}")

    background_replies: list[str] = []
    background_uploads: list[tuple[str, dict[str, str]]] = []
    original_reply = bot.reply_feishu_text
    original_download = bot.download_feishu_file
    original_run_job = bot.run_product_intel_job
    original_upload_results = bot.upload_result_files
    try:
        bot.PROCESSED_MESSAGE_IDS.clear()
        bot.PROCESSED_MESSAGE_ORDER.clear()
        bot.IN_FLIGHT_DEDUPE_KEYS.clear()
        bot.ACTIVE_FILE_KEYS.clear()
        bot.JOB_STATUSES.clear()
        bot.reply_feishu_text = (  # type: ignore[assignment]
            lambda chat_id, text: background_replies.append(text)
            or {"ok": True, "status_code": 200, "data": {"code": 0}}
        )
        bot.download_feishu_file = lambda *args, **kwargs: "/tmp/products.xlsx"  # type: ignore[assignment]
        bot.run_product_intel_job = lambda **kwargs: {  # type: ignore[assignment]
            "ok": True,
            "profile": {"mapped_fields": {}, "warnings": []},
            "decision_summary": {"top_products": []},
            "manager_payload": {},
            "output_files": {
                "decision_table_csv": "/tmp/decision.csv",
                "decision_table_md": "/tmp/decision.md",
                "manager_payload_json": "/tmp/manager.json",
                "csv_profile_md": "/tmp/profile.md",
            },
        }
        bot.upload_result_files = (  # type: ignore[assignment]
            lambda chat_id, output_files: background_uploads.append((chat_id, output_files))
            or {
                "decision_table_csv": {"ok": True},
                "decision_table_md": {"ok": True},
                "manager_payload_json": {"ok": True},
                "input_profile_md": {"ok": True},
            }
        )
        success_info = {
            "event_id": "evt_background_success",
            "message_id": "om_background_success",
            "chat_id": "oc_background_success",
            "message_type": "file",
            "file_key": "file_background_success",
            "file_name": "products.xlsx",
            "text": "",
        }
        bot.claim_dedupe_key("om_background_success")
        bot.reserve_file_key("file_background_success", "pi_test_success")
        bot.process_background_job(
            {
                "job_id": "pi_test_success",
                "dedupe_key": "om_background_success",
                "dedupe_result": "new",
                "action": "file_analysis",
                "info": success_info,
            }
        )
        if len(background_replies) != 2:
            raise AssertionError(f"successful background job should send status and result replies: {background_replies}")
        if "已收到文件，正在分析" not in background_replies[0] or "job_id：pi_test_success" not in background_replies[0]:
            raise AssertionError(f"missing received notice: {background_replies}")
        if "【Product Intel 商品分析完成】" not in background_replies[1]:
            raise AssertionError(f"missing successful result reply: {background_replies}")
        if len(background_uploads) != 1:
            raise AssertionError(f"successful background job should upload result files: {background_uploads}")
        if bot.JOB_STATUSES.get("pi_test_success", {}).get("status") != "success":
            raise AssertionError(f"success job status not recorded: {bot.JOB_STATUSES}")

        failure_replies: list[str] = []
        bot.reply_feishu_text = (  # type: ignore[assignment]
            lambda chat_id, text: failure_replies.append(text)
            or {"ok": True, "status_code": 200, "data": {"code": 0}}
        )
        bot.download_feishu_file = (  # type: ignore[assignment]
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("failed to download Feishu file"))
        )
        failure_info = {
            "event_id": "evt_background_failure",
            "message_id": "om_background_failure",
            "chat_id": "oc_background_failure",
            "message_type": "file",
            "file_key": "file_background_failure",
            "file_name": "products.xlsx",
            "text": "",
        }
        bot.claim_dedupe_key("om_background_failure")
        bot.reserve_file_key("file_background_failure", "pi_test_failure")
        bot.process_background_job(
            {
                "job_id": "pi_test_failure",
                "dedupe_key": "om_background_failure",
                "dedupe_result": "new",
                "action": "file_analysis",
                "info": failure_info,
            }
        )
        if len(failure_replies) != 2:
            raise AssertionError(f"failed background job should send status and failure replies: {failure_replies}")
        if "【Product Intel 分析失败】" not in failure_replies[1] or "job_id：pi_test_failure" not in failure_replies[1]:
            raise AssertionError(f"missing failed result reply: {failure_replies}")
        if bot.JOB_STATUSES.get("pi_test_failure", {}).get("status") != "failed":
            raise AssertionError(f"failure job status not recorded: {bot.JOB_STATUSES}")
    finally:
        bot.reply_feishu_text = original_reply  # type: ignore[assignment]
        bot.download_feishu_file = original_download  # type: ignore[assignment]
        bot.run_product_intel_job = original_run_job  # type: ignore[assignment]
        bot.upload_result_files = original_upload_results  # type: ignore[assignment]

    calls: list[dict[str, object]] = []
    original_get_token = bot.get_tenant_access_token
    original_post = bot.requests.post
    try:
        bot.get_tenant_access_token = lambda: "tenant_token_test"  # type: ignore[assignment]

        def fake_post(url: str, **kwargs: object) -> FakeResponse:
            calls.append({"url": url, "kwargs": kwargs})
            if url.endswith("/im/v1/files"):
                return FakeResponse(200, {"code": 0, "data": {"file_key": "file_key_test"}})
            if url.endswith("/im/v1/messages"):
                body = kwargs.get("json", {})
                if not isinstance(body, dict) or body.get("msg_type") != "file":
                    raise AssertionError(f"expected file message body, got {body}")
                return FakeResponse(200, {"code": 0, "data": {"message_id": "om_file_msg"}})
            raise AssertionError(f"unexpected URL: {url}")

        bot.requests.post = fake_post  # type: ignore[assignment]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "result.csv"
            path.write_text("a,b\n1,2\n", encoding="utf-8")
            upload_result = upload_file_to_feishu("oc_test", str(path))
        if not upload_result.get("ok"):
            raise AssertionError(f"mock upload should succeed: {upload_result}")
        if len(calls) != 2:
            raise AssertionError(f"expected upload and send calls, got {len(calls)}")
    finally:
        bot.get_tenant_access_token = original_get_token  # type: ignore[assignment]
        bot.requests.post = original_post  # type: ignore[assignment]

    reply = format_product_intel_reply(
        {
            "ok": True,
            "manager_payload": {
                "llm_summary": {
                    "summary_text": "运营摘要：\n" + ("这是很长的分析内容。" * 140),
                }
            },
            "profile": {
                "detected_file_type": "xlsx",
                "detected_sheet_name": "Sheet1",
                "row_count": 7,
                "mapped_fields": {"product_name": "商品名称", "price": "价格"},
                "warnings": ["demo warning"],
            },
            "decision_summary": {
                "main_push_count": 1,
                "small_test_count": 2,
                "hold_count": 3,
                "reject_count": 1,
                "top_products": [
                    {"rank": 1, "opportunity_score": 88, "decision": "main_push", "product_name": "Demo Product"}
                ],
            },
            "output_files": {
                "decision_table_csv": "product_intel/output/product_intel_decision_table.csv",
                "decision_table_md": "product_intel/output/product_intel_decision_table.md",
                "manager_payload_json": "product_intel/output/product_intel_manager_payload.json",
                "csv_profile_md": "product_intel/output/product_intel_csv_profile.md",
            },
        },
        {
            "decision_table_csv": {"ok": True},
            "decision_table_md": {"ok": True},
            "manager_payload_json": {"ok": False, "error": "mock failure"},
            "input_profile_md": {"ok": True},
        },
    )
    for expected_text in [
        "文件类型：XLSX",
        "Sheet：Sheet1",
        "已尝试上传结果附件：",
        "decision_table_csv：成功",
        "manager_payload_json：失败",
    ]:
        if expected_text not in reply:
            raise AssertionError(f"reply missing {expected_text!r}: {reply}")
    if reply.count("运营摘要：") != 1:
        raise AssertionError(f"reply should contain one ops summary title: {reply}")
    if "完整分析请查看附件 manager_payload_json。" not in reply:
        raise AssertionError(f"long ops summary should include attachment hint: {reply}")

    print("Product Intel Feishu bot smoke test passed.")


if __name__ == "__main__":
    main()
