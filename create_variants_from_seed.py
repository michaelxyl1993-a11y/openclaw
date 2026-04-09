#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


PYTHON = "/usr/bin/python3"
TOOLS_DIR = "/Users/michaelchui/Desktop/openclaw_tools"
MANAGER_OPS = f"{TOOLS_DIR}/manager_ops.py"


def run_json(args: List[str]) -> Dict[str, Any]:
    result = subprocess.run(args, capture_output=True, text=True)
    output = (result.stdout or "") + (("\n" + result.stderr) if result.stderr else "")
    output = output.strip()

    if result.returncode != 0:
        raise RuntimeError(output or f"command failed: {' '.join(args)}")

    if not output:
        raise RuntimeError(f"empty stdout from command: {' '.join(args)}")

    try:
        return json.loads(output)
    except Exception:
        start = output.find("{")
        end = output.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(output[start:end + 1])
        raise ValueError(f"无法解析 JSON 输出: {output[:500]}")


def load_json_file(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"payload file not found: {path}")

    with p.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, dict):
        raise ValueError("payload json 必须是对象")
    return payload


def normalize_record_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    兼容 manager_ops.py get_record 的不同返回形状。
    当前你本地真实返回是：
    {
      "ok": true,
      "record_id": "...",
      "fields": {...}
    }
    所以要优先取 fields。
    """
    for key in ("fields", "summary", "record", "data"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def pick_first(data: Dict[str, Any], keys: List[str]) -> Any:
    for key in keys:
        if key in data:
            return data[key]
    return None


def validate_seed_split_payload(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    variants = payload.get("variants")
    if not isinstance(variants, list):
        raise ValueError("payload 必须包含 variants 数组")
    if len(variants) != 10:
        raise ValueError("variants 必须正好 10 条")

    allowed_indexes = {f"{i:02d}" for i in range(1, 11)}
    seen = set()
    cleaned: List[Dict[str, str]] = []

    for item in variants:
        if not isinstance(item, dict):
            raise ValueError("variants 中每一项都必须是对象")

        idx = item.get("index")
        angle = item.get("angle")

        if idx not in allowed_indexes:
            raise ValueError(f"非法 index: {idx}")
        if idx in seen:
            raise ValueError(f"重复 index: {idx}")
        if not isinstance(angle, str) or not angle.strip():
            raise ValueError(f"index {idx} 的 angle 不能为空")

        seen.add(idx)
        cleaned.append({
            "index": idx,
            "angle": angle.strip(),
        })

    cleaned.sort(key=lambda x: x["index"])
    return cleaned


def main():
    if len(sys.argv) != 3:
        print(json.dumps({
            "ok": False,
            "reason": "usage: python3 create_variants_from_seed.py <seed_record_id> <payload_json_path>"
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    seed_record_id = sys.argv[1].strip()
    payload_json_path = sys.argv[2].strip()

    try:
        payload = load_json_file(payload_json_path)
        variants = validate_seed_split_payload(payload)

        seed_resp = run_json([PYTHON, MANAGER_OPS, "get_record", seed_record_id])
        if not seed_resp.get("ok"):
            raise RuntimeError(f"get_record failed: {json.dumps(seed_resp, ensure_ascii=False)}")

        seed_data = normalize_record_payload(seed_resp)

        task_type = pick_first(seed_data, ["任务类型", "task_type"])
        group_id = pick_first(seed_data, ["商品组ID", "group_id"])
        status = pick_first(seed_data, ["任务状态", "status"])
        note = pick_first(seed_data, ["备注", "note"])

        if task_type != "seed":
            raise ValueError(f"record_id={seed_record_id} 不是 seed，当前任务类型={task_type}")

        if not isinstance(group_id, str) or not group_id.strip():
            raise ValueError("无法从 seed 记录中解析 商品组ID")

        group_resp = run_json([PYTHON, MANAGER_OPS, "check_group_state", group_id])
        if not group_resp.get("ok"):
            raise RuntimeError(f"check_group_state failed: {json.dumps(group_resp, ensure_ascii=False)}")

        current_variant_count = int(group_resp.get("variant_count", 0))
        current_seed_count = int(group_resp.get("seed_count", 0))
        result_label = group_resp.get("result")

        # 第 1 版先保守：只要当前组里已经有任何 variant，就不允许继续
        can_proceed = current_variant_count == 0

        output = {
            "ok": True,
            "mode": "dry_run",
            "seed_record_id": seed_record_id,
            "group_id": group_id,
            "seed_status": status,
            "seed_note": note,
            "seed_count": current_seed_count,
            "current_variant_count": current_variant_count,
            "group_result": result_label,
            "can_proceed": can_proceed,
            "block_reason": None if can_proceed else "当前商品组已存在 variant；第1版 dry-run 先保守阻断",
            "planned_variant_count": len(variants),
            "planned_variants": variants,
        }

        print(json.dumps(output, ensure_ascii=False, indent=2))

    except Exception as e:
        print(json.dumps({
            "ok": False,
            "mode": "dry_run",
            "seed_record_id": seed_record_id,
            "reason": str(e),
        }, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()