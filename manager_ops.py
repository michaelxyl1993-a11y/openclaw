#!/usr/bin/env python3
import json
import subprocess
import sys
from typing import Any, Dict, List

PYTHON = "/usr/bin/python3"
TOOLS_DIR = "/Users/michaelchui/Desktop/openclaw_tools"

GET_GROUP_RECORDS = f"{TOOLS_DIR}/get_group_records.py"
GET_RECORD = f"{TOOLS_DIR}/get_record.py"
CHECK_GROUP_STATE = f"{TOOLS_DIR}/check_group_state.py"
VERIFY_RECORD = f"{TOOLS_DIR}/verify_record.py"
UPDATE_RECORD = f"{TOOLS_DIR}/update_record.py"

# 这里如果你的飞书列名不完全一致，只改右边的列名即可
FIELD_MAP = {
    "image1_text": "图1文字",
    "image2_text": "图2文字",
    "image3_text": "图3文字",
    "image1_prompt": "图1 prompt",
    "image2_prompt": "图2 prompt",
    "image3_prompt": "图3 prompt",
    "title": "产出标题",
    "caption": "产出配文",
    "hashtags": "hashtags",
    "status": "任务状态",
    "note": "备注",
    "timestamp": "时间戳",
}

REQUIRED_OUTPUT_KEYS = [
    "image1_text",
    "image2_text",
    "image3_text",
    "image1_prompt",
    "image2_prompt",
    "image3_prompt",
    "title",
    "caption",
    "hashtags",
]


def run_json(args: List[str]) -> Dict[str, Any]:
    result = subprocess.run(args, capture_output=True, text=True)
    output = (result.stdout or "") + (("\n" + result.stderr) if result.stderr else "")
    if result.returncode != 0:
        raise RuntimeError(output.strip() or f"Command failed: {' '.join(args)}")

    output = output.strip()
    try:
        return json.loads(output)
    except Exception:
        start = output.find("{")
        end = output.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(output[start:end + 1])
        raise ValueError("无法解析 JSON 输出")


def ok_or_raise(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not payload.get("ok"):
        raise RuntimeError(json.dumps(payload, ensure_ascii=False))
    return payload


def load_json_file(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError("payload json 必须是对象")
    return payload


def cmd_check_group_state(group_id: str) -> Dict[str, Any]:
    payload = run_json([PYTHON, CHECK_GROUP_STATE, group_id])
    payload = ok_or_raise(payload)
    return payload


def cmd_verify_record(record_id: str) -> Dict[str, Any]:
    payload = run_json([PYTHON, VERIFY_RECORD, record_id])
    payload = ok_or_raise(payload)
    return payload


def cmd_get_group_records(group_id: str) -> Dict[str, Any]:
    payload = run_json([PYTHON, GET_GROUP_RECORDS, group_id])
    payload = ok_or_raise(payload)
    return payload


def cmd_get_record(record_id: str) -> Dict[str, Any]:
    payload = run_json([PYTHON, GET_RECORD, record_id])
    payload = ok_or_raise(payload)
    return payload


def cmd_set_note(record_id: str, note: str) -> Dict[str, Any]:
    payload = run_json([PYTHON, UPDATE_RECORD, record_id, "备注", note])
    payload = ok_or_raise(payload)
    return payload


def cmd_set_status(record_id: str, status: str) -> Dict[str, Any]:
    payload = run_json([PYTHON, UPDATE_RECORD, record_id, "任务状态", status])
    payload = ok_or_raise(payload)
    return payload


def cmd_set_timestamp(record_id: str) -> Dict[str, Any]:
    payload = run_json([PYTHON, UPDATE_RECORD, record_id, "时间戳", "NOW"])
    payload = ok_or_raise(payload)
    return payload


def cmd_set_status_with_timestamp(record_id: str, status: str, note: str = "") -> Dict[str, Any]:
    status_resp = cmd_set_status(record_id, status)
    ts_resp = cmd_set_timestamp(record_id)

    note_resp = None
    if note != "":
        note_resp = cmd_set_note(record_id, note)

    verify_resp = cmd_verify_record(record_id)

    return {
        "ok": True,
        "record_id": record_id,
        "status_update": status_resp.get("updated"),
        "timestamp_update": ts_resp.get("updated"),
        "note_update": None if note_resp is None else note_resp.get("updated"),
        "verify": verify_resp.get("summary"),
    }


def cmd_update_field(record_id: str, field_name: str, value: Any) -> Dict[str, Any]:
    if value is None:
        raise ValueError(f"{field_name} 的值不能为空")

    write_value = "NOW" if field_name == "时间戳" and str(value).upper() == "NOW" else str(value)

    payload = run_json([PYTHON, UPDATE_RECORD, record_id, field_name, write_value])
    payload = ok_or_raise(payload)
    return payload


def cmd_write_variant_outputs(record_id: str, payload_json_path: str) -> Dict[str, Any]:
    payload = load_json_file(payload_json_path)

    missing = [k for k in REQUIRED_OUTPUT_KEYS if k not in payload]
    if missing:
        raise ValueError(f"payload 缺少必填 key: {', '.join(missing)}")

    update_order = [
        "image1_text",
        "image2_text",
        "image3_text",
        "image1_prompt",
        "image2_prompt",
        "image3_prompt",
        "title",
        "caption",
        "hashtags",
        "status",
        "note",
        "timestamp",
    ]

    updates = []
    for key in update_order:
        if key not in payload:
            continue

        if key not in FIELD_MAP:
            raise ValueError(f"不支持的 payload key: {key}")

        field_name = FIELD_MAP[key]
        value = payload[key]

        # timestamp 允许写 NOW
        if key == "timestamp":
            if value in (True, "NOW", "now"):
                value = "NOW"
            elif value in ("", None, False):
                continue

        # note 允许空字符串，表示清空备注
        if key == "note":
            value = "" if value is None else str(value)

        resp = cmd_update_field(record_id, field_name, value)
        updates.append({
            "payload_key": key,
            "field_name": field_name,
            "updated": resp.get("updated"),
        })

    verify_resp = cmd_verify_record(record_id)

    return {
        "ok": True,
        "record_id": record_id,
        "updated_count": len(updates),
        "updates": updates,
        "verify": verify_resp.get("summary"),
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "ok": False,
            "reason": "usage: python3 manager_ops.py <command> [args...]"
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    command = sys.argv[1].strip()

    try:
        if command == "check_group_state":
            if len(sys.argv) != 3:
                raise ValueError("usage: python3 manager_ops.py check_group_state <group_id>")
            result = cmd_check_group_state(sys.argv[2].strip())

        elif command == "verify_record":
            if len(sys.argv) != 3:
                raise ValueError("usage: python3 manager_ops.py verify_record <record_id>")
            result = cmd_verify_record(sys.argv[2].strip())

        elif command == "get_group_records":
            if len(sys.argv) != 3:
                raise ValueError("usage: python3 manager_ops.py get_group_records <group_id>")
            result = cmd_get_group_records(sys.argv[2].strip())

        elif command == "get_record":
            if len(sys.argv) != 3:
                raise ValueError("usage: python3 manager_ops.py get_record <record_id>")
            result = cmd_get_record(sys.argv[2].strip())

        elif command == "set_note":
            if len(sys.argv) != 4:
                raise ValueError("usage: python3 manager_ops.py set_note <record_id> <note>")
            result = cmd_set_note(sys.argv[2].strip(), sys.argv[3])

        elif command == "set_status":
            if len(sys.argv) != 4:
                raise ValueError("usage: python3 manager_ops.py set_status <record_id> <status>")
            result = cmd_set_status(sys.argv[2].strip(), sys.argv[3])

        elif command == "set_timestamp":
            if len(sys.argv) != 3:
                raise ValueError("usage: python3 manager_ops.py set_timestamp <record_id>")
            result = cmd_set_timestamp(sys.argv[2].strip())

        elif command == "set_status_with_timestamp":
            if len(sys.argv) not in (4, 5):
                raise ValueError("usage: python3 manager_ops.py set_status_with_timestamp <record_id> <status> [note]")
            record_id = sys.argv[2].strip()
            status = sys.argv[3]
            note = sys.argv[4] if len(sys.argv) == 5 else ""
            result = cmd_set_status_with_timestamp(record_id, status, note)

        elif command == "write_variant_outputs":
            if len(sys.argv) != 4:
                raise ValueError("usage: python3 manager_ops.py write_variant_outputs <record_id> <payload_json_path>")
            record_id = sys.argv[2].strip()
            payload_json_path = sys.argv[3]
            result = cmd_write_variant_outputs(record_id, payload_json_path)

        else:
            raise ValueError(
                "unknown command. supported: "
                "check_group_state, verify_record, get_group_records, get_record, "
                "set_note, set_status, set_timestamp, set_status_with_timestamp, write_variant_outputs"
            )

        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as e:
        print(json.dumps({
            "ok": False,
            "command": command,
            "reason": str(e)
        }, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()