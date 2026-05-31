"""Small in-process background queue for Product Intel bot jobs."""

from __future__ import annotations

import queue
import threading
import traceback
from collections.abc import Callable
from typing import Any


Job = dict[str, Any]
JobHandler = Callable[[Job], None]

JOB_QUEUE: queue.Queue[tuple[Job, JobHandler]] = queue.Queue()
_WORKER_LOCK = threading.Lock()
_WORKER_STARTED = False


def _job_label(job: Job) -> str:
    return str(job.get("dedupe_key") or job.get("message_id") or job.get("event_id") or "missing_key")


def _worker_loop() -> None:
    while True:
        job, handler = JOB_QUEUE.get()
        label = _job_label(job)
        action = str(job.get("action") or "unknown")
        job_id = str(job.get("job_id") or "")
        print(f"[product-intel-queue] job_started job_id={job_id} dedupe_key={label} action={action}")
        try:
            handler(job)
            print(f"[product-intel-queue] job_finished job_id={job_id} dedupe_key={label} action={action}")
        except Exception as exc:  # pragma: no cover - defensive worker boundary.
            print(f"[product-intel-queue] job_failed job_id={job_id} dedupe_key={label} action={action} error={exc}")
            traceback.print_exc()
        finally:
            JOB_QUEUE.task_done()


def start_worker() -> None:
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        thread = threading.Thread(target=_worker_loop, name="product-intel-worker", daemon=True)
        thread.start()
        _WORKER_STARTED = True
        print("[product-intel-queue] worker_started")


def enqueue_job(job: Job, handler: JobHandler) -> None:
    start_worker()
    JOB_QUEUE.put((job, handler))
    print(
        "[product-intel-queue] "
        f"job_enqueued job_id={job.get('job_id', '')} dedupe_key={_job_label(job)} action={job.get('action', 'unknown')} "
        f"queue_size={JOB_QUEUE.qsize()}"
    )
