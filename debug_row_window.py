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

    try:
        return json.loads(text)
    except Exception:
        pass

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
        if set(value.keys()) == {"text"}:
            return value["text"]
        if set(value.keys()) == {"name"}:
            return value["name"]
        if set(value.keys()) == {"value"}:
            return value["value"]
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

    record = data.get("record")
    if isinstance(record, dict):
        if isinstance(record.get("fields"), dict):
            return record["fields"]
        return record

    if isinstance(data, dict) and isinstance(data.get("fields"), dict):
        return data["fields"]

    if isinstance(record_payload.get("fields"), dict):
        return record_payload["fields"]

    raise KeyError(f"record-get 返回结构异常，无法提取 fields。原始 keys: {list(record_payload.keys())}")


def safe_get(d: Any, key: str) -> Any:
    if isinstance(d, dict):
        return d.get(key)
    return None


def main():
    if len(sys.argv) < 4:
        print(json.dumps({
            "ok": False,
            "reason": "usage: python3 debug_row_window.py <start_row> <end_row> <target_group_id>"
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    start_row = int(sys.argv[1])
    end_row = int(sys.argv[2])
    target_group_id = sys.argv[3].strip()

    try:
        payload = get_record_list(limit=500)
        rows = extract_rows(payload)
        record_ids = extract_record_ids(payload)

        if len(rows) != len(record_ids):
            raise ValueError("rows 数量与 record_id_list 数量不一致")

        total_rows = len(rows)
        if start_row < 1 or end_row > total_rows or start_row > end_row:
            raise ValueError(f"非法区间: start={start_row}, end={end_row}, total_rows={total_rows}")

        out = []

        for row_no in range(start_row, end_row + 1):
            idx = row_no - 1
            row = normalize_value(rows[idx])
            record_id = record_ids[idx]

            row_text = json.dumps(row, ensure_ascii=False)
            row_group_id = safe_get(row, "商品组ID")
            row_task_type = safe_get(row, "任务类型")
            row_status = safe_get(row, "任务状态")
            row_variant_no = safe_get(row, "变体序号")

            record_payload = get_record(record_id)
            raw_fields = normalize_value(extract_fields(record_payload))

            raw_group_id = raw_fields.get("商品组ID")
            raw_task_type = raw_fields.get("任务类型")
            raw_status = raw_fields.get("任务状态")
            raw_variant_no = raw_fields.get("变体序号")
            raw_note = raw_fields.get("备注")
            raw_source_seed = raw_fields.get("source_seed_record_id") or raw_fields.get("来源seed_record_id")

            out.append({
                "row_no": row_no,
                "record_id": record_id,
                "row_view": {
                    "商品组ID": row_group_id,
                    "任务类型": row_task_type,
                    "任务状态": row_status,
                    "变体序号": row_variant_no,
                    "row_contains_target_group_text": target_group_id in row_text,
                    "row_text_preview": row_text[:300]
                },
                "record_get_raw": {
                    "商品组ID": raw_group_id,
                    "任务类型": raw_task_type,
                    "任务状态": raw_status,
                    "变体序号": raw_variant_no,
                    "备注": raw_note,
                    "source_seed_record_id": raw_source_seed,
                    "raw_group_match_target": raw_group_id == target_group_id
                }
            })

        print(json.dumps({
            "ok": True,
            "target_group_id": target_group_id,
            "total_rows": total_rows,
            "window_start": start_row,
            "window_end": end_row,
            "rows": out
        }, ensure_ascii=False, indent=2))

    except Exception as e:
        print(json.dumps({
            "ok": False,
            "reason": str(e)
        }, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()