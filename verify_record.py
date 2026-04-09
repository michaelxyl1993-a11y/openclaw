#!/usr/bin/env python3
import json
import subprocess
import sys
from typing import Any, Dict, List

PYTHON = "/usr/bin/python3"
TOOLS_DIR = "/Users/michaelchui/Desktop/openclaw_tools"
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


def get_record(record_id: str) -> Dict[str, Any]:
    return run_json([PYTHON, GET_RECORD, record_id])


def main():
    if len(sys.argv) != 2:
        print(json.dumps({
            "ok": False,
            "reason": "usage: python3 verify_record.py <record_id>"
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    record_id = sys.argv[1].strip()

    try:
        record = get_record(record_id)
        if not record.get("ok"):
            print(json.dumps(record, ensure_ascii=False, indent=2))
            sys.exit(1)

        fields = record.get("fields", {})

        output = {
            "ok": True,
            "record_id": record_id,
            "summary": {
                "商品组ID": fields.get("商品组ID"),
                "任务类型": fields.get("任务类型"),
                "任务状态": fields.get("任务状态"),
                "变体序号": fields.get("变体序号"),
                "营销切角": fields.get("营销切角"),
                "备注": fields.get("备注"),
                "时间戳": fields.get("时间戳"),
                "产出标题": fields.get("产出标题"),
                "产出配文": fields.get("产出配文"),
                "hashtags": fields.get("hashtags"),
                "图1文字": fields.get("图1文字"),
                "图2文字": fields.get("图2文字"),
                "图3文字": fields.get("图3文字"),
                "图1 prompt": fields.get("图1 prompt"),
                "图2 prompt": fields.get("图2 prompt"),
                "图3 prompt": fields.get("图3 prompt"),
            }
        }

        print(json.dumps(output, ensure_ascii=False, indent=2))

    except Exception as e:
        print(json.dumps({
            "ok": False,
            "record_id": record_id,
            "reason": str(e)
        }, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()