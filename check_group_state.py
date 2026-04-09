#!/usr/bin/env python3
import json
import subprocess
import sys
from typing import Any, Dict, List

PYTHON = "/usr/bin/python3"
TOOLS_DIR = "/Users/michaelchui/Desktop/openclaw_tools"
GET_GROUP_RECORDS = f"{TOOLS_DIR}/get_group_records.py"
GET_RECORD = f"{TOOLS_DIR}/get_record.py"


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


def get_group_records(group_id: str) -> Dict[str, Any]:
    return run_json([PYTHON, GET_GROUP_RECORDS, group_id])


def get_record(record_id: str) -> Dict[str, Any]:
    return run_json([PYTHON, GET_RECORD, record_id])


def normalize_status(value: Any) -> str:
    if value is None:
        return "UNKNOWN"
    return str(value)


def main():
    if len(sys.argv) != 2:
        print(json.dumps({
            "ok": False,
            "reason": "usage: python3 check_group_state.py <group_id>"
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    group_id = sys.argv[1].strip()

    try:
        group_info = get_group_records(group_id)
        if not group_info.get("ok"):
            print(json.dumps(group_info, ensure_ascii=False, indent=2))
            sys.exit(1)

        seed_ids = group_info.get("seed_record_ids", [])
        variant_ids = group_info.get("variant_record_ids", [])

        seed_status = None
        if seed_ids:
            seed_record = get_record(seed_ids[0])
            if not seed_record.get("ok"):
                raise RuntimeError(f"无法读取 seed record: {seed_ids[0]}")
            seed_status = seed_record["fields"].get("任务状态")

        summary = {
            "待拆分": 0,
            "待执行": 0,
            "执行中": 0,
            "待返工": 0,
            "已完成": 0,
            "已暂停": 0,
            "UNKNOWN": 0
        }

        for rid in variant_ids:
            record = get_record(rid)
            if not record.get("ok"):
                summary["UNKNOWN"] += 1
                continue

            status = normalize_status(record["fields"].get("任务状态"))
            if status not in summary:
                summary["UNKNOWN"] += 1
            else:
                summary[status] += 1

        if len(seed_ids) == 1 and len(variant_ids) == 0:
            result = "SEED_ONLY"
        elif len(seed_ids) == 1 and len(variant_ids) > 0:
            result = "HAS_VARIANTS"
        else:
            result = "CHECK_FAIL"

        output = {
            "ok": True,
            "group_id": group_id,
            "seed_count": len(seed_ids),
            "variant_count": len(variant_ids),
            "seed_status": seed_status,
            "variant_status_summary": summary,
            "result": result
        }

        print(json.dumps(output, ensure_ascii=False, indent=2))

    except Exception as e:
        print(json.dumps({
            "ok": False,
            "group_id": group_id,
            "reason": str(e)
        }, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()