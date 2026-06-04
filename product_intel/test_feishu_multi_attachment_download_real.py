"""Tests for Product Intel v1.21 opt-in Feishu multi-attachment download."""

from __future__ import annotations

import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from .feishu_multi_attachment_download_real import (
    FeishuDownloadHTTPError,
    build_downloaded_inputs,
    build_summary,
    load_download_plan,
    load_runtime_token_context,
    main,
    run_multi_download,
    write_outputs,
)


PACKAGE_DIR = Path(__file__).resolve().parent
PLAN = (
    PACKAGE_DIR
    / "output_feishu_multi_attachment_dry_run"
    / "feishu_multi_attachment_download_plan.json"
)
TOKEN_SOURCE = PACKAGE_DIR / "mock_feishu_multi_attachment_event.json"
PROTECTED_FILES = [
    PACKAGE_DIR / "run_product_intel.py",
    PACKAGE_DIR / "multi_file_batch_runner.py",
    PACKAGE_DIR / "feishu_product_intel_bot.py",
    PACKAGE_DIR / "job_queue.py",
]


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


class FailIfCalledClient:
    def download_file(self, **kwargs) -> None:
        raise AssertionError("Real Feishu API must not be called.")


class FakeDownloadClient:
    def __init__(self, failing_filename: str = "") -> None:
        self.calls: list[dict] = []
        self.failing_filename = failing_filename

    def download_file(self, **kwargs) -> None:
        self.calls.append(kwargs)
        target = Path(kwargs["target_path"])
        if target.name == self.failing_filename:
            raise RuntimeError(
                f"download failed for {kwargs['file_token']} with fake-app-secret"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"downloaded:{target.name}".encode("utf-8"))


class FakeHTTP400Client:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def download_file(self, **kwargs) -> None:
        self.calls.append(kwargs)
        raise FeishuDownloadHTTPError(
            response_status_code=400,
            response_body=json.dumps(
                {
                    "code": 99991663,
                    "msg": (
                        "bad request token="
                        f"{kwargs['file_token']} message={kwargs['message_id']} "
                        "secret=fake-app-secret tenant=tenant_access_token_fake"
                    ),
                }
            ),
            response_content_type="application/json",
            sensitive_values=["tenant_access_token_fake"],
        )


class FakeInvalidOpenMessageClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def download_file(self, **kwargs) -> None:
        self.calls.append(kwargs)
        raise FeishuDownloadHTTPError(
            response_status_code=400,
            response_body=json.dumps(
                {
                    "code": 99992354,
                    "msg": "The request you send is not a valid {open_message_id} or not exists",
                    "field_violations": [
                        {
                            "field": "message_id",
                            "description": "id not exist",
                        }
                    ],
                    "debug_token": kwargs["file_token"],
                    "debug_secret": "fake-app-secret",
                }
            ),
            response_content_type="application/json",
        )


class FeishuMultiAttachmentDownloadRealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protected_digests = {
            path: _digest(path) for path in PROTECTED_FILES if path.exists()
        }
        cls.plan = load_download_plan(PLAN)
        cls.token_context = load_runtime_token_context(TOKEN_SOURCE)

    @classmethod
    def tearDownClass(cls) -> None:
        for path, expected in cls.protected_digests.items():
            if _digest(path) != expected:
                raise AssertionError(f"Protected source was modified: {path}")

    def _plan_for_temp(self, temp_dir: str) -> dict:
        plan = json.loads(json.dumps(self.plan))
        for task in plan["download_tasks"]:
            task["target_path"] = str(Path(temp_dir) / task["filename"])
        return plan

    def _enabled_env(self) -> dict[str, str]:
        return {
            "PRODUCT_INTEL_REAL_FEISHU_MULTI_DOWNLOAD_ENABLED": "true",
            "FEISHU_APP_ID": "fake-app-id",
            "FEISHU_APP_SECRET": "fake-app-secret",
        }

    def test_default_disabled_never_calls_real_api(self) -> None:
        receipt = run_multi_download(self.plan, environ={}, client=FailIfCalledClient())
        self.assertFalse(receipt["real_feishu_api_called"])
        self.assertFalse(receipt["real_download_performed"])
        self.assertEqual(receipt["download_status"], "disabled")
        self.assertEqual(receipt["disabled_count"], 4)
        self.assertTrue(
            all(item["download_status"] == "disabled" for item in receipt["download_results"])
        )

    def test_enabled_env_must_equal_true(self) -> None:
        receipt = run_multi_download(
            self.plan,
            environ={"PRODUCT_INTEL_REAL_FEISHU_MULTI_DOWNLOAD_ENABLED": "false"},
            client=FailIfCalledClient(),
        )
        self.assertFalse(receipt["real_feishu_api_called"])
        self.assertEqual(receipt["disabled_count"], 4)

    def test_missing_credentials_are_blocked_without_api_call(self) -> None:
        receipt = run_multi_download(
            self.plan,
            environ={"PRODUCT_INTEL_REAL_FEISHU_MULTI_DOWNLOAD_ENABLED": "true"},
            token_context=self.token_context,
            client=FailIfCalledClient(),
        )
        self.assertFalse(receipt["real_feishu_api_called"])
        self.assertFalse(receipt["real_download_performed"])
        self.assertEqual(receipt["error_count"], 4)
        self.assertIn("credentials", receipt["error"])

    def test_missing_runtime_token_source_is_blocked(self) -> None:
        receipt = run_multi_download(
            self.plan,
            environ=self._enabled_env(),
            client=FailIfCalledClient(),
        )
        self.assertFalse(receipt["real_feishu_api_called"])
        self.assertIn("runtime token source", receipt["error"])

    def test_runtime_token_source_can_be_hash_mapping(self) -> None:
        event = json.loads(TOKEN_SOURCE.read_text(encoding="utf-8"))
        mapping = {
            sha256(item["file_token"].encode("utf-8")).hexdigest(): item["file_token"]
            for item in event["attachments"]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "runtime-token-source.json"
            source.write_text(
                json.dumps(
                    {
                        "message_id": event["message_id"],
                        "file_tokens": mapping,
                    }
                ),
                encoding="utf-8",
            )
            context = load_runtime_token_context(source)
        self.assertEqual(context["message_id"], event["message_id"])
        self.assertEqual(context["tokens_by_hash"], mapping)

    def test_runtime_token_source_requires_open_message_id(self) -> None:
        event = json.loads(TOKEN_SOURCE.read_text(encoding="utf-8"))
        mapping = {
            sha256(item["file_token"].encode("utf-8")).hexdigest(): item["file_token"]
            for item in event["attachments"]
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "runtime-token-source.json"
            source.write_text(
                json.dumps(
                    {
                        "message_id": "4958c28729f13569",
                        "file_tokens": mapping,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "open_message_id starting with om_"):
                load_runtime_token_context(source)

    def test_direct_short_message_id_context_is_blocked_with_diagnostic(self) -> None:
        context = json.loads(json.dumps(self.token_context))
        context["message_id"] = "4958c28729f13569"
        receipt = run_multi_download(
            self.plan,
            environ=self._enabled_env(),
            token_context=context,
            client=FailIfCalledClient(),
        )
        self.assertFalse(receipt["real_feishu_api_called"])
        self.assertFalse(receipt["real_download_performed"])
        self.assertEqual(receipt["probable_root_cause"], "invalid_open_message_id")
        self.assertIn("open_message_id starting with om_", receipt["error"])

    def test_fake_client_downloads_multiple_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan = self._plan_for_temp(temp_dir)
            client = FakeDownloadClient()
            receipt = run_multi_download(
                plan,
                environ=self._enabled_env(),
                token_context=self.token_context,
                client=client,
            )
            self.assertEqual(len(client.calls), 4)
            self.assertEqual(receipt["success_count"], 4)
            self.assertEqual(receipt["error_count"], 0)
            self.assertTrue(receipt["real_feishu_api_called"])
            self.assertTrue(receipt["real_download_performed"])
            self.assertTrue(all(Path(path).stat().st_size > 0 for path in receipt["downloaded_input_files"]))
            self.assertTrue(build_downloaded_inputs(receipt)["ready_for_multi_file_batch_runner"])

    def test_token_hash_mismatch_marks_file_error_without_stopping_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan = self._plan_for_temp(temp_dir)
            context = json.loads(json.dumps(self.token_context))
            missing_hash = plan["download_tasks"][0]["file_token_hash"]
            context["tokens_by_hash"].pop(missing_hash)
            receipt = run_multi_download(
                plan,
                environ=self._enabled_env(),
                token_context=context,
                client=FakeDownloadClient(),
            )
            self.assertEqual(receipt["success_count"], 3)
            self.assertEqual(receipt["error_count"], 1)
            self.assertEqual(len(receipt["downloaded_input_files"]), 3)
            self.assertIn("unavailable", receipt["download_results"][0]["error"])

    def test_single_failure_does_not_stop_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan = self._plan_for_temp(temp_dir)
            client = FakeDownloadClient("mock_fastmoss_products.xlsx")
            receipt = run_multi_download(
                plan,
                environ=self._enabled_env(),
                token_context=self.token_context,
                client=client,
            )
            self.assertEqual(len(client.calls), 4)
            self.assertEqual(receipt["success_count"], 3)
            self.assertEqual(receipt["error_count"], 1)
            self.assertEqual(len(receipt["downloaded_input_files"]), 3)
            self.assertNotIn("mock_fastmoss_products.xlsx", receipt["downloaded_input_files"])
            rendered = json.dumps(receipt)
            self.assertNotIn("mock_file_token_fastmoss", rendered)
            self.assertNotIn("fake-app-secret", rendered)

    def test_fake_400_response_writes_sanitized_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan = self._plan_for_temp(temp_dir)
            client = FakeHTTP400Client()
            receipt = run_multi_download(
                plan,
                environ=self._enabled_env(),
                token_context=self.token_context,
                client=client,
            )
        self.assertEqual(len(client.calls), 4)
        self.assertTrue(receipt["real_feishu_api_called"])
        self.assertFalse(receipt["real_download_performed"])
        self.assertEqual(receipt["success_count"], 0)
        self.assertEqual(receipt["error_count"], 4)
        first = receipt["download_results"][0]
        self.assertEqual(first["response_status_code"], 400)
        self.assertEqual(first["response_content_type"], "application/json")
        self.assertEqual(first["request_method"], "GET")
        self.assertEqual(
            first["request_endpoint_template"],
            "/open-apis/im/v1/messages/{message_id}/resources/{file_token}",
        )
        self.assertEqual(first["resource_type"], "file")
        self.assertTrue(first["message_id_redacted"].startswith("REDACTED_MESSAGE_ID:"))
        self.assertIn("99991663", first["response_body_sanitized"])
        self.assertIn("bad request", first["response_body_sanitized"])
        rendered = json.dumps(receipt)
        for forbidden in [
            "mock_file_token_echotik",
            "mock_file_token_fastmoss",
            "mock_file_token_kalodata",
            "mock_file_token_manual",
            "fake-app-secret",
            "tenant_access_token_fake",
            self.token_context["message_id"],
        ]:
            self.assertNotIn(forbidden, rendered)

    def test_invalid_open_message_id_response_sets_root_cause(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan = self._plan_for_temp(temp_dir)
            context = json.loads(json.dumps(self.token_context))
            context["message_id_source_path"] = "event.message.message_id"
            client = FakeInvalidOpenMessageClient()
            receipt = run_multi_download(
                plan,
                environ=self._enabled_env(),
                token_context=context,
                client=client,
            )
        self.assertEqual(len(client.calls), 4)
        self.assertTrue(receipt["real_feishu_api_called"])
        self.assertFalse(receipt["real_download_performed"])
        self.assertEqual(receipt["probable_root_cause"], "invalid_open_message_id")
        self.assertIn("event.message.message_id", receipt["next_debug_hint"])
        first = receipt["download_results"][0]
        self.assertEqual(first["response_status_code"], 400)
        self.assertEqual(first["message_id_source_path"], "event.message.message_id")
        self.assertEqual(first["message_id_len"], len(context["message_id"]))
        self.assertTrue(first["message_id_hash_prefix"])
        self.assertIn("99992354", first["response_body_sanitized"])
        rendered = json.dumps(receipt)
        self.assertNotIn(context["message_id"], rendered)
        self.assertNotIn("fake-app-secret", rendered)
        for token in context["tokens_by_hash"].values():
            self.assertNotIn(token, rendered)

    def test_success_outputs_do_not_leak_runtime_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan = self._plan_for_temp(str(Path(temp_dir) / "downloads"))
            receipt = run_multi_download(
                plan,
                environ=self._enabled_env(),
                token_context=self.token_context,
                client=FakeDownloadClient(),
            )
            output_dir = Path(temp_dir) / "outputs"
            paths = write_outputs(receipt, output_dir)
            rendered = "\n".join(
                path.read_text(encoding="utf-8-sig") for path in paths.values()
            )
        fixture = json.loads(TOKEN_SOURCE.read_text(encoding="utf-8"))
        for item in fixture["attachments"]:
            self.assertNotIn(item["file_token"], rendered)
        for forbidden in [
            "FEISHU_APP_ID",
            "FEISHU_APP_SECRET",
            "chat_id",
            "oc_",
            "file_v3_",
            "mock_file_token",
        ]:
            self.assertNotIn(forbidden, rendered)

    def test_missing_plan_is_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not exist"):
            load_download_plan("/private/tmp/missing-product-intel-v1-21-plan.json")

    def test_no_supported_tasks_returns_blocked_receipt(self) -> None:
        receipt = run_multi_download(
            {"download_tasks": [{"supported": False}]},
            environ={},
            client=FailIfCalledClient(),
        )
        self.assertEqual(receipt["download_task_count"], 0)
        self.assertIn("no supported", receipt["error"])
        self.assertFalse(receipt["real_feishu_api_called"])

    def test_outputs_are_redacted_and_all_files_are_generated(self) -> None:
        receipt = run_multi_download(self.plan, environ={})
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_outputs(receipt, temp_dir)
            self.assertEqual(
                set(paths),
                {
                    "receipt_json",
                    "summary_json",
                    "summary_md",
                    "downloaded_files_csv",
                    "downloaded_inputs_json",
                },
            )
            rendered = "\n".join(
                path.read_text(encoding="utf-8-sig") for path in paths.values()
            )
            self.assertTrue(all(path.exists() and path.stat().st_size > 0 for path in paths.values()))
        fixture = json.loads(TOKEN_SOURCE.read_text(encoding="utf-8"))
        for item in fixture["attachments"]:
            self.assertNotIn(item["file_token"], rendered)
        for forbidden in [
            "FEISHU_APP_ID",
            "FEISHU_APP_SECRET",
            "chat_id",
            "oc_",
            "file_v3_",
            "mock_file_token",
        ]:
            self.assertNotIn(forbidden, rendered)

    def test_downloaded_inputs_include_only_successes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            plan = self._plan_for_temp(temp_dir)
            receipt = run_multi_download(
                plan,
                environ=self._enabled_env(),
                token_context=self.token_context,
                client=FakeDownloadClient("mock_manual_products.xlsx"),
            )
            inputs = build_downloaded_inputs(receipt)
            summary = build_summary(receipt)
            self.assertEqual(len(inputs["downloaded_input_files"]), 3)
            self.assertTrue(inputs["ready_for_multi_file_batch_runner"])
            self.assertEqual(summary["success_count"], 3)

    def test_module_isolated_from_analysis_and_message_send(self) -> None:
        source = (PACKAGE_DIR / "feishu_multi_attachment_download_real.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("run_pipeline", source)
        self.assertNotIn("from .multi_file_batch_runner import", source)
        self.assertNotIn("run_multi_file_batch(", source)
        self.assertNotIn("requests.get(", source.split("class FeishuMultiAttachmentDownloadClient")[0])
        self.assertNotIn("requests.post(", source.split("class FeishuMultiAttachmentDownloadClient")[0])

    def test_disabled_cli_does_not_require_runtime_token_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            exit_code = main(
                [
                    "--download-plan",
                    str(PLAN),
                    "--output-dir",
                    temp_dir,
                ]
            )
            receipt = json.loads(
                (Path(temp_dir) / "feishu_multi_attachment_download_real_receipt.json").read_text(
                    encoding="utf-8"
                )
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(receipt["download_status"], "disabled")
        self.assertFalse(receipt["real_feishu_api_called"])

    def test_protected_sources_are_not_modified(self) -> None:
        for path, expected in self.protected_digests.items():
            self.assertEqual(_digest(path), expected)


if __name__ == "__main__":
    unittest.main()
