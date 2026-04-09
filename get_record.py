#!/usr/bin/env python3
import json
import subprocess
import sys
from typing import Any, Dict, List

LARK_CLI = "/Users/michaelchui/.npm-global/bin/lark-cli"
BASE_TOKEN = "YPYkb6elYafQZUs0NaqchZD0nif"
TABLE_ID = "tblZhp8737rlnCXO"


def run_command(args: List[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True)
    output = (result.stdout or "") + (("\n" + result.stderr) if result.stderr else "")
    if result.returncode != 0:
        raise RuntimeError(output.strip() or f"Command failed: {' '.join(args)}")
    return output.strip()


def extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()

    # 直接尝试
    try:
        return json.loads(text)
    except Exception:
        pass

    # 兼容前面混有 warning 的情况
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        return json.loads(candidate)

    raise ValueError("无法从命令输出中提取 JSON")


def normalize_value(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, list):
        normalized = [normalize_value(v) for v in value]
        if len(normalized) == 0:
            return None
        if len(normalized) == 1:
            return normalized[0]
        return normalized

    if isinstance(value, dict):
        # 简单对象直接取值
        if set(value.keys()) == {"text"}:
            return value["text"]
        if set(value.keys()) == {"name"}:
            return value["name"]
        if set(value.keys()) == {"value"}:
            return value["value"]

        return {k: normalize_value(v) for k, v in value.items()}

    return value


def extract_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = payload.get("data", {})
    record = data.get("record")

    # 你截图里就是这种结构：data.record 直接是字段对象
    if isinstance(record, dict):
        # 如果 record 下还有 fields，就取 fields
        if isinstance(record.get("fields"), dict):
            return record["fields"]
        # 否则 record 本身就是字段对象
        return record

    # 兼容其他可能结构
    if isinstance(data.get("fields"), dict):
        return data["fields"]

    if isinstance(payload.get("fields"), dict):
        return payload["fields"]

    raise KeyError("record-get 返回结构异常，未找到字段对象")


def get_record(record_id: str) -> Dict[str, Any]:
    args = [
        LARK_CLI,
        "base",
        "+record-get",
        "--as", "user",
        "--base-token", BASE_TOKEN,
        "--table-id", TABLE_ID,
        "--record-id", record_id,
    ]

    raw = run_command(args)
    payload = extract_json(raw)
    fields = extract_fields(payload)
    normalized_fields = normalize_value(fields)

    return {
        "ok": True,
        "record_id": record_id,
        "fields": normalized_fields
    }


def main():
    if len(sys.argv) != 2:
        print(json.dumps({
            "ok": False,
            "reason": "usage: python3 get_record.py <record_id>"
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    record_id = sys.argv[1].strip()

    try:
        result = get_record(record_id)
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