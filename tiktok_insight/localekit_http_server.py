# localekit_http_server.py
# Standalone LocaleKit HTTP server

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict

from localekit_service import run_localekit


def json_response(handler: BaseHTTPRequestHandler, status_code: int, data: Dict[str, Any]) -> None:
    body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class LocaleKitHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            json_response(
                self,
                200,
                {
                    "status": "ok",
                    "tool": "localekit",
                    "version": "v1_standalone_http",
                },
            )
            return

        json_response(
            self,
            404,
            {
                "status": "error",
                "error": "not_found",
                "path": self.path,
            },
        )

    def do_POST(self) -> None:
        if self.path != "/localekit/run":
            json_response(
                self,
                404,
                {
                    "status": "error",
                    "error": "not_found",
                    "path": self.path,
                },
            )
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(raw_body) if raw_body.strip() else {}

            result = run_localekit(payload)
            json_response(self, 200, result)

        except Exception as e:
            json_response(
                self,
                500,
                {
                    "status": "error",
                    "tool": "localekit",
                    "error": str(e),
                },
            )


def main() -> None:
    port = int(os.getenv("LOCALEKIT_PORT", "8781"))
    server = HTTPServer(("127.0.0.1", port), LocaleKitHandler)
    print(f"LocaleKit HTTP server running at http://127.0.0.1:{port}")
    print("Health check: GET /health")
    print("Run: POST /localekit/run")
    server.serve_forever()


if __name__ == "__main__":
    main()
