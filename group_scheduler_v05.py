#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

PYTHON = "/usr/bin/python3"
MANAGER_OPS = "/Users/michaelchui/Desktop/openclaw_tools/manager_ops.py"

STATUS_DONE = "已完成"
STATUS_RUNNABLE = "待执行"
STATUS_INFLIGHT = "执行中"
STATUS_REVISE = "待返工"
STATUS_PAUSED = "已暂停"

STOP_STATUSES = {STATUS_REVISE, STATUS_PAUSED}
INFLIGHT_STATUSES = {STATUS_INFLIGHT}
RUNNABLE_STATUSES = {STATUS_RUNNABLE}
DONE_STATUSES = {STATUS_DONE}


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
        raise ValueError(f"无法解析 JSON 输出: {output[:500]}")


def call_manager_ops(command: str, *args: str) -> Dict[str, Any]:
    return run_json([PYTHON, MANAGER_OPS, command, *args])


def flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts = [flatten_text(v) for v in value]
        parts = [p for p in parts if p]
        return " ".join(parts).strip()
    if isinstance(value, dict):
        # 常见结构兼容
        for key in ["text", "name", "title", "value", "label", "display_value"]:
            if key in value:
                return flatten_text(value[key])
        parts = [flatten_text(v) for v in value.values()]
        parts = [p for p in parts if p]
        return " ".join(parts).strip()
    return str(value).strip()


def find_all_record_ids(payload: Any) -> List[str]:
    found: List[str] = []

    def walk(x: Any):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            # 兼容 recxxxxxxxx 形式
            if re.fullmatch(r"rec[\w-]+", x.strip()):
                found.append(x.strip())

    walk(payload)
    # 去重保序
    seen = set()
    result = []
    for rid in found:
        if rid not in seen:
            seen.add(rid)
            result.append(rid)
    return result


def get_candidate_field_maps(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []

    def walk(x: Any):
        if isinstance(x, dict):
            if "fields" in x and isinstance(x["fields"], dict):
                candidates.append(x["fields"])
            candidates.append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(payload)
    return candidates


def extract_field(payload: Dict[str, Any], field_name: str) -> str:
    for d in get_candidate_field_maps(payload):
        if field_name in d:
            return flatten_text(d[field_name])
    return ""


def extract_record_id(payload: Dict[str, Any]) -> str:
    # 优先常见键
    for key in ["record_id", "recordId", "id"]:
        val = extract_field(payload, key)
        if val.startswith("rec"):
            return val
    # 兜底：全量找 rec...
    ids = find_all_record_ids(payload)
    return ids[0] if ids else ""


def safe_int_variant_no(value: str) -> int:
    value = flatten_text(value)
    m = re.search(r"\d+", value)
    return int(m.group()) if m else 9999


def get_group_variant_rows(group_id: str) -> List[Dict[str, str]]:
    group_payload = call_manager_ops("get_group_records", group_id)
    record_ids = find_all_record_ids(group_payload)

    if not record_ids:
        raise RuntimeError(f"商品组 {group_id} 未找到 record_id")

    rows: List[Dict[str, str]] = []

    for rid in record_ids:
        rec = call_manager_ops("get_record", rid)

        row = {
            "record_id": extract_record_id(rec) or rid,
            "商品组ID": extract_field(rec, "商品组ID"),
            "任务类型": extract_field(rec, "任务类型"),
            "任务状态": extract_field(rec, "任务状态"),
            "变体序号": extract_field(rec, "变体序号"),
            "营销切角": extract_field(rec, "营销切角"),
            "备注": extract_field(rec, "备注"),
            "时间戳": extract_field(rec, "时间戳"),
        }

        if row["任务类型"] == "variant":
            rows.append(row)

    rows.sort(key=lambda x: safe_int_variant_no(x["变体序号"]))
    return rows


def summarize(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    statuses = [r["任务状态"] for r in rows]
    return {
        "total": len(rows),
        "done": sum(1 for s in statuses if s == STATUS_DONE),
        "runnable": sum(1 for s in statuses if s == STATUS_RUNNABLE),
        "inflight": sum(1 for s in statuses if s == STATUS_INFLIGHT),
        "revise": sum(1 for s in statuses if s == STATUS_REVISE),
        "paused": sum(1 for s in statuses if s == STATUS_PAUSED),
    }


def first_row_with_status(rows: List[Dict[str, str]], target_statuses: set) -> Optional[Dict[str, str]]:
    for r in rows:
        if r["任务状态"] in target_statuses:
            return r
    return None


def format_row(r: Dict[str, str]) -> str:
    return (
        f'变体 {r["变体序号"]} | 状态={r["任务状态"]} | '
        f'切角={r["营销切角"] or "-"} | 备注={r["备注"] or "-"}'
    )


def print_snapshot(rows: List[Dict[str, str]]) -> None:
    print("\n=== 当前组内状态 ===")
    for r in rows:
        print(format_row(r))
    s = summarize(rows)
    print(
        f'\n汇总: 总数={s["total"]}, 已完成={s["done"]}, 待执行={s["runnable"]}, '
        f'执行中={s["inflight"]}, 待返工={s["revise"]}, 已暂停={s["paused"]}'
    )
    print("===================\n")


def main():
    parser = argparse.ArgumentParser(description="OpenClaw v0.5 手动调度辅助器（只查表+提示触发）")
    parser.add_argument("group_id", help="商品组ID，例如 20260404-004")
    parser.add_argument("--poll-seconds", type=int, default=20, help="轮询间隔，默认20秒")
    parser.add_argument("--max-wait-minutes", type=int, default=180, help="最长监控时间，默认180分钟")
    parser.add_argument("--once", action="store_true", help="只检查一次，不循环")
    args = parser.parse_args()

    group_id = args.group_id
    poll_seconds = max(5, args.poll_seconds)
    deadline = time.time() + args.max_wait_minutes * 60

    last_signature = None
    last_action_prompted_for_variant = None

    print(f"\n启动 v0.5 手动调度辅助器，商品组ID = {group_id}")
    print(f"轮询间隔 = {poll_seconds}s")
    print("本脚本不会自动发消息给飞书 manager，只会提示你何时触发下一轮。\n")

    while True:
        try:
            rows = get_group_variant_rows(group_id)
        except Exception as e:
            print(f"[ERROR] 读取组状态失败: {e}")
            if args.once:
                sys.exit(2)
            time.sleep(poll_seconds)
            continue

        sig = json.dumps(rows, ensure_ascii=False, sort_keys=True)
        changed = sig != last_signature

        if changed:
            print_snapshot(rows)
            last_signature = sig

        # 1) 异常终态：当前阶段保守起见，直接停机
        bad_row = first_row_with_status(rows, STOP_STATUSES)
        if bad_row:
            print("[STOP] 发现异常终态，当前组停止自动推进。")
            print(f"[STOP] {format_row(bad_row)}")
            sys.exit(10)

        # 2) 全部已完成
        if rows and all(r["任务状态"] == STATUS_DONE for r in rows):
            print(f"[DONE] 商品组 {group_id} 的所有 variant 已完成。")
            sys.exit(0)

        # 3) 有执行中：继续等
        inflight_row = first_row_with_status(rows, INFLIGHT_STATUSES)
        if inflight_row:
            print(f'[WAIT] 当前有执行中: 变体 {inflight_row["变体序号"]}，继续等待。')
            last_action_prompted_for_variant = None
            if args.once:
                sys.exit(0)
            if time.time() > deadline:
                print("[STOP] 达到最长监控时间，停止。")
                sys.exit(11)
            time.sleep(poll_seconds)
            continue

        # 4) 没有执行中，但有待执行：提示手动触发
        runnable_row = first_row_with_status(rows, RUNNABLE_STATUSES)
        if runnable_row:
            vn = runnable_row["变体序号"]
            if last_action_prompted_for_variant != vn or changed:
                print("[ACTION NEEDED] 当前无执行中，且存在待执行 variant。")
                print(f"[NEXT] 下一条应触发: 变体 {vn}")
                print(f"[NEXT] 请在飞书 manager 发送：/start_variant {group_id}")
                print("[NEXT] 发出后，本脚本会继续轮询，检测该轮是否进入执行中 / 已完成。\n")
                last_action_prompted_for_variant = vn

            if args.once:
                sys.exit(0)
            if time.time() > deadline:
                print("[STOP] 达到最长监控时间，停止。")
                sys.exit(11)
            time.sleep(poll_seconds)
            continue

        # 5) 没有执行中，也没有待执行：说明当前没有可推进项
        print("[STOP] 当前组没有执行中，也没有待执行。")
        print("[STOP] 若你预期应继续推进，请人工检查表格状态。")
        sys.exit(12)


if __name__ == "__main__":
    main()