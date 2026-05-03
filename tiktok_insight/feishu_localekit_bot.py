# feishu_localekit_bot.py
# Standalone Feishu bot for LocaleKit

import argparse
import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from localekit_client import handle_localekit_text, is_localekit_help_request


# Local dev SSL workaround for macOS/proxy self-signed certificate chain.
# Only for local Feishu bot testing.
ssl._create_default_https_context = ssl._create_unverified_context


BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "localekit_feishu_logs"
PROCESSED_EVENTS_PATH = BASE_DIR / "localekit_feishu_processed_events.json"
LOG_DIR.mkdir(exist_ok=True)

FEISHU_OPEN_BASE = os.getenv("FEISHU_OPEN_BASE", "https://open.feishu.cn")

APP_ID = os.getenv("LOCALEKIT_FEISHU_APP_ID", "").strip()
APP_SECRET = os.getenv("LOCALEKIT_FEISHU_APP_SECRET", "").strip()
VERIFY_TOKEN = os.getenv("LOCALEKIT_FEISHU_VERIFICATION_TOKEN", "").strip()

# Optional. If you later get bot open_id, set this for stricter @ filtering.
BOT_OPEN_ID = os.getenv("LOCALEKIT_BOT_OPEN_ID", "").strip()

TOKEN_CACHE = {
    "token": "",
    "expire_at": 0,
}


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def write_json_log(prefix: str, data: dict):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"{ts}_{prefix}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def http_json(method: str, url: str, data: dict | None = None, headers: dict | None = None, timeout: int = 30) -> dict:
    body = None
    final_headers = {
        "Content-Type": "application/json; charset=utf-8"
    }
    if headers:
        final_headers.update(headers)

    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=final_headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {e.code} {url}: {raw}") from e


def get_tenant_access_token() -> str:
    if not APP_ID or not APP_SECRET:
        raise RuntimeError("Missing LOCALEKIT_FEISHU_APP_ID or LOCALEKIT_FEISHU_APP_SECRET")

    now = int(time.time())
    if TOKEN_CACHE["token"] and TOKEN_CACHE["expire_at"] > now + 120:
        return TOKEN_CACHE["token"]

    url = f"{FEISHU_OPEN_BASE}/open-apis/auth/v3/tenant_access_token/internal"
    resp = http_json("POST", url, {
        "app_id": APP_ID,
        "app_secret": APP_SECRET,
    })

    token = resp.get("tenant_access_token")
    expire = int(resp.get("expire", 7200))

    if not token:
        raise RuntimeError(f"Failed to get tenant_access_token: {resp}")

    TOKEN_CACHE["token"] = token
    TOKEN_CACHE["expire_at"] = now + expire
    return token


def split_text(text: str, max_chars: int = 3500) -> list[str]:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return [text]

    chunks = []
    current = ""

    for para in text.split("\n"):
        if len(current) + len(para) + 1 <= max_chars:
            current += para + "\n"
        else:
            if current.strip():
                chunks.append(current.strip())
            current = para + "\n"

    if current.strip():
        chunks.append(current.strip())

    return chunks


def reply_message(message_id: str, text: str):
    token = get_tenant_access_token()
    url = f"{FEISHU_OPEN_BASE}/open-apis/im/v1/messages/{message_id}/reply"

    parts = split_text(text)

    for idx, part in enumerate(parts):
        prefix = ""
        if len(parts) > 1:
            prefix = f"（{idx + 1}/{len(parts)}）\n"

        body = {
            "msg_type": "text",
            "content": json.dumps({
                "text": prefix + part
            }, ensure_ascii=False)
        }

        resp = http_json(
            "POST",
            url,
            body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )

        if resp.get("code", 0) != 0:
            raise RuntimeError(f"Reply message failed: {resp}")

        time.sleep(0.3)


def load_processed_events() -> dict:
    if not PROCESSED_EVENTS_PATH.exists():
        return {}
    try:
        return json.loads(PROCESSED_EVENTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_processed_events(data: dict):
    items = list(data.items())[-1000:]
    compact = dict(items)
    PROCESSED_EVENTS_PATH.write_text(
        json.dumps(compact, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def is_duplicate_event(payload: dict, message_id: str) -> bool:
    header = payload.get("header", {}) or {}
    event_id = header.get("event_id", "") or payload.get("uuid", "")

    keys = []
    if event_id:
        keys.append(f"event:{event_id}")
    if message_id:
        keys.append(f"message:{message_id}")

    if not keys:
        return False

    data = load_processed_events()

    for key in keys:
        if key in data:
            return True

    record = {
        "message_id": message_id,
        "event_id": event_id,
        "time": now_ts(),
    }

    for key in keys:
        data[key] = record

    save_processed_events(data)
    return False


def clean_feishu_message_text(text: str) -> str:
    if not text:
        return ""

    text = re.sub(r"@\s*_user_\d+\s*", "", text)
    text = re.sub(r"@\S*user_\d+\s*", "", text)
    text = re.sub(r"@\s*本地化器\s*LocaleKit\s*", "", text, flags=re.I)
    text = re.sub(r"@\s*LocaleKit\s*", "", text, flags=re.I)
    text = re.sub(r"@\s*LocalKit\s*", "", text, flags=re.I)
    text = text.replace("\u200b", "").replace("\ufeff", "")
    return text.strip()


def extract_text_message(event_payload: dict) -> tuple[str, str, str, dict]:
    event = event_payload.get("event", {})
    message = event.get("message", {})

    message_id = message.get("message_id", "")
    message_type = message.get("message_type", "")
    raw_content = message.get("content", "")

    if message_type != "text":
        return message_id, "", raw_content, message

    try:
        content_obj = json.loads(raw_content)
        text = content_obj.get("text", "")
    except Exception:
        text = raw_content

    clean_text = clean_feishu_message_text(text)
    return message_id, clean_text, raw_content, message


def is_private_chat(message: dict) -> bool:
    chat_type = str(message.get("chat_type", "")).lower()
    return chat_type in ["p2p", "private"]


def _looks_like_localekit_mention(value: str) -> bool:
    if not value:
        return False
    lower = value.lower()
    return (
        "localekit" in lower
        or "localkit" in lower
        or "本地人虾" in value
        or "本地化器" in value
    )


def is_bot_mentioned(message: dict, raw_content: str) -> bool:
    """
    Group messages must @ this bot.

    Rules:
    - Private chat: allow.
    - Group chat: only allow if the actual mention looks like LocaleKit.
    - Do NOT accept just because there is any mention, otherwise @分析虾 will also trigger LocaleKit.
    """
    if is_private_chat(message):
        return True

    mentions = message.get("mentions") or []

    if BOT_OPEN_ID and mentions:
        for m in mentions:
            mid = m.get("id") or {}
            if mid.get("open_id") == BOT_OPEN_ID:
                return True

    for m in mentions:
        candidates = [
            str(m.get("name", "")),
            str(m.get("key", "")),
            json.dumps(m, ensure_ascii=False),
        ]
        if any(_looks_like_localekit_mention(x) for x in candidates):
            return True

    # fallback: some Feishu payloads may include display text in raw content
    if _looks_like_localekit_mention(raw_content):
        return True

    return False

def should_ack_before_processing(text: str) -> bool:
    if not text:
        return False
    if is_localekit_help_request(text):
        return False
    return "任务类型" in text and "目标语言" in text and "原始内容" in text


def run_localekit_and_reply(message_id: str, text: str):
    try:
        if should_ack_before_processing(text):
            reply_message(message_id, "收到，正在用本地化器 LocaleKit 处理请求。")

        answer = handle_localekit_text(text)
        reply_message(message_id, answer)

    except Exception as e:
        write_json_log("localekit_error", {
            "message_id": message_id,
            "error": repr(e),
            "text_preview": text[:1000],
        })
        try:
            reply_message(
                message_id,
                "❌ 本地化器 LocaleKit 处理失败。\n\n"
                f"错误：{repr(e)}"
            )
        except Exception:
            pass


class LocaleKitFeishuHandler(BaseHTTPRequestHandler):
    def send_json(self, status_code: int, data: dict):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def read_payload(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw.strip() else {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self.send_json(200, {
                "status": "ok",
                "service": "feishu_localekit_bot",
                "time": now_ts(),
            })
            return

        self.send_json(404, {"status": "not_found"})

    def do_POST(self):
        path = urlparse(self.path).path

        if path != "/feishu/localekit/events":
            self.send_json(404, {"status": "not_found"})
            return

        try:
            payload = self.read_payload()
            write_json_log("event", payload)

            if "challenge" in payload:
                self.send_json(200, {
                    "challenge": payload["challenge"]
                })
                return

            if VERIFY_TOKEN:
                header_token = payload.get("header", {}).get("token", "")
                old_token = payload.get("token", "")
                incoming_token = header_token or old_token

                if incoming_token and incoming_token != VERIFY_TOKEN:
                    self.send_json(403, {
                        "status": "forbidden",
                        "error": "Invalid verification token",
                    })
                    return

            header = payload.get("header", {})
            event_type = header.get("event_type", "")

            if event_type != "im.message.receive_v1":
                self.send_json(200, {
                    "status": "ignored",
                    "event_type": event_type,
                })
                return

            message_id, text, raw_content, message = extract_text_message(payload)

            if not message_id:
                self.send_json(200, {
                    "status": "ignored",
                    "reason": "missing message_id",
                })
                return

            if is_duplicate_event(payload, message_id):
                self.send_json(200, {
                    "status": "ignored",
                    "reason": "duplicate_event",
                    "message_id": message_id,
                })
                return

            if not text:
                self.send_json(200, {
                    "status": "ignored",
                    "reason": "empty_text",
                })
                return

            if not is_bot_mentioned(message, raw_content):
                self.send_json(200, {
                    "status": "ignored",
                    "reason": "bot_not_mentioned",
                    "message_id": message_id,
                })
                return

            self.send_json(200, {
                "status": "accepted",
                "mode": "localekit",
            })

            t = threading.Thread(
                target=run_localekit_and_reply,
                args=(message_id, text),
                daemon=True,
            )
            t.start()

        except Exception as e:
            write_json_log("error", {"error": repr(e)})
            self.send_json(500, {
                "status": "failed",
                "error": repr(e),
            })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8782)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), LocaleKitFeishuHandler)

    print("✅ Feishu LocaleKit Bot server started")
    print(f"Health: http://{args.host}:{args.port}/health")
    print(f"Events: http://{args.host}:{args.port}/feishu/localekit/events")

    server.serve_forever()


if __name__ == "__main__":
    main()