#!/usr/bin/env python3
import json
import subprocess
import sys
from typing import Any, Dict, List, Optional

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

    # 先直接尝试
    try:
        return json.loads(text)
    except Exception:
        pass

    # 如果输出里混了别的文字，尝试截取第一段 JSON
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            pass

    raise ValueError("无法从命令输出中提取 JSON")


def run_json_command(args: List[str]) -> Dict[str, Any]:
    raw = run_command(args)
    return extract_json(raw)


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
        # 常见简单对象，直接取值
        if set(value.keys()) == {"text"}:
            return value["text"]
        if set(value.keys()) == {"name"}:
            return value["name"]
        if set(value.keys()) == {"value"}:
            return value["value"]

        # 否则递归保留结构
        return {k: normalize_value(v) for k, v in value.items()}

    return value


def get_record_list(limit: int = 500) -> Dict[str, Any]:
    args = [
        LARK_CLI,
        "base",
        "+record-list",
        "--as", "user",
        "--base-token", BASE_TOKEN,
        "--table-id", TABLE_ID,
        "--limit", str(limit),
    ]
    return run_json_command(args)


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
    return run_json_command(args)


def extract_rows(payload: Dict[str, Any]) -> List[Any]:
    data = payload.get("data", payload)

    # 适配常见结构
    if isinstance(data.get("data"), list):
        return data["data"]
    if isinstance(data.get("items"), list):
        return data["items"]
    if isinstance(data.get("rows"), list):
        return data["rows"]

    raise KeyError("record-list 返回里未找到 rows/data/items 数组")


def extract_record_ids(payload: Dict[str, Any]) -> List[str]:
    data = payload.get("data", payload)

    if isinstance(data.get("record_id_list"), list):
        return data["record_id_list"]
    if isinstance(data.get("recordIds"), list):
        return data["recordIds"]
    if isinstance(data.get("record_ids"), list):
        return data["record_ids"]

    raise KeyError("record-list 返回里未找到 record_id_list")


def extract_fields(record_payload: Dict[str, Any]) -> Dict[str, Any]:
    data = record_payload.get("data", {})

    # 结构 A: {"data": {"record": {...字段直接在这里...}}}
    record = data.get("record")
    if isinstance(record, dict):
        # 如果 record 下面还有 fields，就取 fields
        if isinstance(record.get("fields"), dict):
            return record["fields"]
        # 否则 record 本身就是字段对象
        return record

    # 结构 B: {"data": {"fields": {...}}}
    if isinstance(data, dict) and isinstance(data.get("fields"), dict):
        return data["fields"]

    # 结构 C: {"fields": {...}}
    if isinstance(record_payload.get("fields"), dict):
        return record_payload["fields"]

    raise KeyError(f"record-get 返回结构异常，无法提取 fields。原始 keys: {list(record_payload.keys())}")


def get_group_records(group_id: str) -> Dict[str, Any]:
    record_list_payload = get_record_list(limit=500)
    rows = extract_rows(record_list_payload)
    record_ids = extract_record_ids(record_list_payload)

    if len(rows) != len(record_ids):
        raise ValueError("record-list rows 数量与 record_id_list 数量不一致")

    candidate_record_ids: List[str] = []

    # 第一步：粗筛候选
    for idx, row in enumerate(rows):
        row_text = json.dumps(row, ensure_ascii=False)
        if group_id in row_text:
            candidate_record_ids.append(record_ids[idx])

    # 第二步：逐条 record-get，做精确判断
    seed_record_ids: List[str] = []
    variant_record_ids: List[str] = []

    for record_id in candidate_record_ids:
        record_payload = get_record(record_id)
        fields = normalize_value(extract_fields(record_payload))

        current_group_id = fields.get("商品组ID")
        task_type = fields.get("任务类型")
        variant_no = fields.get("变体序号")

        if current_group_id != group_id:
            continue

        if task_type == "seed" and (variant_no is None or variant_no == ""):
            seed_record_ids.append(record_id)
        elif task_type == "variant":
            variant_record_ids.append(record_id)

    return {
        "ok": True,
        "group_id": group_id,
        "seed_record_ids": seed_record_ids,
        "variant_record_ids": variant_record_ids,
        "seed_count": len(seed_record_ids),
        "variant_count": len(variant_record_ids),
    }


def main():
    if len(sys.argv) != 2:
        print(json.dumps({
            "ok": False,
            "reason": "usage: python3 get_group_records.py <group_id>"
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    group_id = sys.argv[1].strip()

    try:
        result = get_group_records(group_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({
            "ok": False,
            "group_id": group_id,
            "reason": str(e)
        }, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()