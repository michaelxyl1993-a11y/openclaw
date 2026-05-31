"""Operational health checks for Product Intel Feishu Bot."""

from __future__ import annotations

import json
from typing import Any

import requests


SERVICE_NAME = "product_intel_feishu_bot"
LOCAL_HEALTH_URL = "http://127.0.0.1:8788/health"
PUBLIC_HEALTH_URL = "https://product.packytech.com/health"


def check_health(url: str, timeout: tuple[int, int] = (3, 10)) -> dict[str, Any]:
    try:
        resp = requests.get(url, timeout=timeout)
        response_text = resp.text[:500]
        ok = resp.status_code == 200
        try:
            data = resp.json()
            if isinstance(data, dict) and data.get("ok") is False:
                ok = False
        except ValueError:
            pass
        return {
            "status": "ok" if ok else "fail",
            "url": url,
            "service_name": SERVICE_NAME,
            "status_code": resp.status_code,
            "response_text": response_text,
            "error": "",
        }
    except requests.RequestException as exc:
        return {
            "status": "fail",
            "url": url,
            "service_name": SERVICE_NAME,
            "status_code": None,
            "response_text": "",
            "error": f"{exc.__class__.__name__}: {exc}",
        }


def run_ops_check(
    local_url: str = LOCAL_HEALTH_URL,
    public_url: str = PUBLIC_HEALTH_URL,
) -> dict[str, Any]:
    return {
        "service_name": SERVICE_NAME,
        "local_health": check_health(local_url),
        "public_health": check_health(public_url),
    }


def print_ops_result(result: dict[str, Any]) -> None:
    print(f"service_name: {result.get('service_name', SERVICE_NAME)}")
    for label in ["local_health", "public_health"]:
        item = result.get(label, {}) if isinstance(result.get(label, {}), dict) else {}
        print(f"{label}: {item.get('status', 'fail')}")
        print(f"  url: {item.get('url', '')}")
        print(f"  service_name: {item.get('service_name', SERVICE_NAME)}")
        print(f"  status_code: {item.get('status_code')}")
        if item.get("response_text"):
            print(f"  response_text: {item.get('response_text')}")
        if item.get("error"):
            print(f"  error: {item.get('error')}")


def main() -> int:
    result = run_ops_check()
    print_ops_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
