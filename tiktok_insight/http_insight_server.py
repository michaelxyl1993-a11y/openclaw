import argparse
import json
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).parent
INCOMING_DIR = BASE_DIR / "incoming_messages"
JOB_DIR = BASE_DIR / "http_jobs"

INCOMING_DIR.mkdir(exist_ok=True)
JOB_DIR.mkdir(exist_ok=True)

MAX_ACTIVE_JOBS = 1


def now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def write_json(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def job_path(job_id: str) -> Path:
    return JOB_DIR / f"{job_id}.json"


def count_running_jobs() -> int:
    count = 0
    for p in JOB_DIR.glob("*.json"):
        try:
            data = read_json(p)
            if data.get("status") == "running":
                count += 1
        except Exception:
            pass
    return count


def update_job(job_id: str, patch: dict):
    p = job_path(job_id)
    data = read_json(p) if p.exists() else {}
    data.update(patch)
    data["updated_at"] = now_ts()
    write_json(p, data)


def run_job(job_id: str, message_file: Path, skip_fetch: bool):
    update_job(job_id, {
        "status": "running",
        "started_at": now_ts(),
        "message_file": str(message_file),
        "skip_fetch": skip_fetch,
    })

    cmd = [
        sys.executable,
        str(BASE_DIR / "insight_service.py"),
        "--message-file",
        str(message_file),
    ]

    if skip_fetch:
        cmd.append("--skip-fetch")

    try:
        completed = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            text=True,
            capture_output=True,
            timeout=1200
        )

        if completed.returncode != 0:
            update_job(job_id, {
                "status": "failed",
                "finished_at": now_ts(),
                "error": completed.stderr[-5000:] if completed.stderr else "Unknown error",
                "stdout_tail": completed.stdout[-5000:] if completed.stdout else "",
            })
            return

        # insight_service.py 正常情况下只输出一个 JSON
        try:
            result = json.loads(completed.stdout)
        except Exception:
            result = {
                "status": "failed",
                "error": "Failed to parse insight_service.py JSON output",
                "stdout_tail": completed.stdout[-8000:],
                "stderr_tail": completed.stderr[-3000:] if completed.stderr else "",
            }

        if result.get("status") == "success":
            update_job(job_id, {
                "status": "success",
                "finished_at": now_ts(),
                "report_path": result.get("report_path"),
                "reply_text": result.get("reply_text"),
                "reply_chars": result.get("reply_chars"),
                "service_result_path": result.get("result_path"),
            })
        else:
            update_job(job_id, {
                "status": "failed",
                "finished_at": now_ts(),
                "error": result.get("error", "Insight service failed"),
                "reply_text": result.get("reply_text", ""),
                "service_result": result,
            })

    except subprocess.TimeoutExpired:
        update_job(job_id, {
            "status": "failed",
            "finished_at": now_ts(),
            "error": "Job timeout after 1200 seconds",
        })
    except Exception as e:
        update_job(job_id, {
            "status": "failed",
            "finished_at": now_ts(),
            "error": repr(e),
        })


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status_code: int, data: dict):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw.strip() else {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            self.send_json(200, {
                "status": "ok",
                "service": "tiktok_insight_http",
                "time": now_ts(),
                "running_jobs": count_running_jobs()
            })
            return

        if path.startswith("/jobs/"):
            job_id = path.replace("/jobs/", "").strip()
            p = job_path(job_id)

            if not p.exists():
                self.send_json(404, {
                    "status": "not_found",
                    "job_id": job_id
                })
                return

            self.send_json(200, read_json(p))
            return

        self.send_json(404, {
            "status": "not_found",
            "path": path
        })

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path != "/analyze":
            self.send_json(404, {
                "status": "not_found",
                "path": path
            })
            return

        if count_running_jobs() >= MAX_ACTIVE_JOBS:
            self.send_json(429, {
                "status": "busy",
                "message": "当前已有分析任务在运行，请稍后再提交。"
            })
            return

        try:
            payload = self.read_body_json()
            message = payload.get("message", "").strip()
            skip_fetch = bool(payload.get("skip_fetch", False))

            if not message:
                self.send_json(400, {
                    "status": "failed",
                    "error": "Missing field: message"
                })
                return

            job_id = uuid.uuid4().hex[:12]
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            message_file = INCOMING_DIR / f"{ts}_{job_id}.txt"
            message_file.write_text(message, encoding="utf-8")

            write_json(job_path(job_id), {
                "job_id": job_id,
                "status": "queued",
                "created_at": now_ts(),
                "message_file": str(message_file),
                "skip_fetch": skip_fetch
            })

            t = threading.Thread(
                target=run_job,
                args=(job_id, message_file, skip_fetch),
                daemon=True
            )
            t.start()

            self.send_json(202, {
                "status": "accepted",
                "job_id": job_id,
                "check_url": f"/jobs/{job_id}",
                "message": "任务已提交，正在后台分析。"
            })

        except Exception as e:
            self.send_json(500, {
                "status": "failed",
                "error": repr(e)
            })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)

    print(f"✅ TikTok Insight HTTP server started")
    print(f"Health: http://{args.host}:{args.port}/health")
    print(f"Analyze: POST http://{args.host}:{args.port}/analyze")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
