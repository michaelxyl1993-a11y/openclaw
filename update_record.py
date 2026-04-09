#!/usr/bin/env python3
import json
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, List

LARK_CLI = "/Users/michaelchui/.npm-global/bin/lark-cli"
BASE_TOKEN = "YPYkb6elYafQZUs0NaqchZD0nif"
TABLE_ID = "tblZhp8737rlnCXO"

ALLOWED_FIELDS = {
    "任务状态",
    "备注",
    "时间戳",
    "图1文字",
    "图2文字",
    "图3文字",
    "图1 prompt",
    "图2 prompt",
    "图3 prompt",
    "产出标题",
    "产出配文",
    "hashtags",
}


def run_command(args: List[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True)
    output = (result.stdout or "") + (("\n" + result.stderr) if result.stderr else "")
    if result.returncode != 0:
        raise RuntimeError(output.strip() or f"Command failed: {' '.join(args)}")
    return output.strip()


def extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start:end + 1])

    raise ValueError("无法从命令输出中提取 JSON")


def normalize_value(field_name: str, value: str) -> str:
    if field_name == "时间戳" and value == "NOW":
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return value


def update_record(record_id: str, field_name: str, field_value: str) -> Dict[str, Any]:
    if field_name not in ALLOWED_FIELDS:
        raise ValueError(f"只允许更新这些字段: {sorted(ALLOWED_FIELDS)}")

    final_value = normalize_value(field_name, field_value)
    payload = {field_name: final_value}

    args = [
        LARK_CLI,
        "base",
        "+record-upsert",
        "--as", "user",
        "--base-token", BASE_TOKEN,
        "--table-id", TABLE_ID,
        "--record-id", record_id,
        "--json", json.dumps(payload, ensure_ascii=False),
    ]

    raw = run_command(args)
    resp = extract_json(raw)

    if not resp.get("ok"):
        raise RuntimeError(json.dumps(resp, ensure_ascii=False))

    return {
        "ok": True,
        "record_id": record_id,
        "updated": payload,
        "response": resp
    }


def main():
    if len(sys.argv) != 4:
        print(json.dumps({
            "ok": False,
            "reason": "usage: python3 update_record.py <record_id> <field_name> <field_value>"
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    record_id = sys.argv[1].strip()
    field_name = sys.argv[2].strip()
    field_value = sys.argv[3]

    try:
        result = update_record(record_id, field_name, field_value)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({
            "ok": False,
            "record_id": record_id,
            "reason": str(e)
        }, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()