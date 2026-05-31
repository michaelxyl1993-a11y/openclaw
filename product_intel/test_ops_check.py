"""Smoke tests for Product Intel ops checks."""

from __future__ import annotations

import requests

from . import ops_check


class FakeResponse:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text

    def json(self) -> dict[str, object]:
        if self.text.startswith("{"):
            return {"ok": True}
        raise ValueError("not json")


def main() -> None:
    original_get = ops_check.requests.get
    calls: list[str] = []
    try:
        def fake_get_ok(url: str, timeout: tuple[int, int]) -> FakeResponse:
            calls.append(url)
            return FakeResponse(200, '{"ok": true, "service": "product_intel_feishu_bot"}')

        ops_check.requests.get = fake_get_ok  # type: ignore[assignment]
        result = ops_check.run_ops_check(local_url="http://local/health", public_url="https://public/health")
        if result["local_health"]["status"] != "ok":
            raise AssertionError(f"local should be ok: {result}")
        if result["public_health"]["status"] != "ok":
            raise AssertionError(f"public should be ok: {result}")
        if calls != ["http://local/health", "https://public/health"]:
            raise AssertionError(f"unexpected calls: {calls}")

        def fake_get_404(url: str, timeout: tuple[int, int]) -> FakeResponse:
            return FakeResponse(404, "not found")

        ops_check.requests.get = fake_get_404  # type: ignore[assignment]
        fail_404 = ops_check.check_health("https://public/health")
        if fail_404["status"] != "fail" or fail_404["status_code"] != 404:
            raise AssertionError(f"404 should fail: {fail_404}")

        def fake_get_timeout(url: str, timeout: tuple[int, int]) -> FakeResponse:
            raise requests.exceptions.Timeout("timed out")

        ops_check.requests.get = fake_get_timeout  # type: ignore[assignment]
        fail_timeout = ops_check.check_health("https://public/health")
        if fail_timeout["status"] != "fail" or "Timeout" not in fail_timeout["error"]:
            raise AssertionError(f"timeout should fail safely: {fail_timeout}")

        def fake_get_conn(url: str, timeout: tuple[int, int]) -> FakeResponse:
            raise requests.exceptions.ConnectionError("connection refused")

        ops_check.requests.get = fake_get_conn  # type: ignore[assignment]
        fail_connection = ops_check.check_health("http://local/health")
        if fail_connection["status"] != "fail" or "ConnectionError" not in fail_connection["error"]:
            raise AssertionError(f"connection error should fail safely: {fail_connection}")
    finally:
        ops_check.requests.get = original_get  # type: ignore[assignment]

    print("Product Intel ops check smoke test passed.")


if __name__ == "__main__":
    main()
