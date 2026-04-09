#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
LARK_CLI = "/Users/michaelchui/.npm-global/bin/lark-cli"

import argparse
import json
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

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
    env = dict(**os.environ)
    env["LARK_CLI_NO_PROXY"] = "1"

    result = subprocess.run(args, capture_output=True, text=True, env=env)
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
        return " ".join([p for p in parts if p]).strip()
    if isinstance(value, dict):
        for key in ["text", "name", "title", "value", "label", "display_value"]:
            if key in value:
                return flatten_text(value[key])
        parts = [flatten_text(v) for v in value.values()]
        return " ".join([p for p in parts if p]).strip()
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
            if re.fullmatch(r"rec[\w-]+", x.strip()):
                found.append(x.strip())

    walk(payload)

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
    for key in ["record_id", "recordId", "id"]:
        val = extract_field(payload, key)
        if val.startswith("rec"):
            return val
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


def summarize(rows: List[Dict[str, str]]) -> Dict[str, int]:
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


def acquire_lock(group_id: str) -> str:
    lock_path = f"/tmp/openclaw_group_scheduler_{group_id}.lock"
    try:
        with open(lock_path, "x", encoding="utf-8") as f:
            f.write(str(time.time()))
    except FileExistsError:
        raise RuntimeError(f"检测到锁文件已存在：{lock_path}，请确认是否已有实例在运行。")
    return lock_path


def release_lock(lock_path: str) -> None:
    try:
        subprocess.run(["/bin/rm", "-f", lock_path], check=False)
    except Exception:
        pass


def send_to_manager(group_id: str) -> None:
    chat_id = "oc_9284d20b41bb119e731304a814c3d2bb"
    text = f"/start_variant {group_id}"

    args = [
        LARK_CLI,
        "im",
        "+messages-send",
        "--chat-id",
        chat_id,
        "--text",
        text,
    ]

    env = dict(**os.environ)
    env["LARK_CLI_NO_PROXY"] = "1"

    result = subprocess.run(args, capture_output=True, text=True, env=env)
    output = (result.stdout or "") + (("\n" + result.stderr) if result.stderr else "")

    if result.returncode != 0:
        raise RuntimeError(f"发送消息失败:\n{output.strip()}")

    try:
        resp = json.loads((result.stdout or "").strip())
    except Exception:
        raise RuntimeError(f"发送消息返回非 JSON，无法确认是否成功:\n{output.strip()}")

    if not resp.get("ok"):
        raise RuntimeError(f"发送消息返回失败:\n{json.dumps(resp, ensure_ascii=False, indent=2)}")

    print(f'[SEND] 已自动发送给飞书 manager: "{text}"')


def main():
    parser = argparse.ArgumentParser(description="OpenClaw v1 自动调度器（自动触发下一轮）")
    parser.add_argument("group_id", help="商品组ID，例如 20260404-006")
    parser.add_argument("--poll-seconds", type=int, default=20, help="轮询间隔，默认20秒")
    parser.add_argument("--max-rounds", type=int, default=12, help="最大触发轮数，默认12")
    parser.add_argument("--round-timeout-minutes", type=int, default=8, help="单轮最长等待时间，默认8分钟")
    args = parser.parse_args()

    group_id = args.group_id
    poll_seconds = max(5, args.poll_seconds)
    max_rounds = max(1, args.max_rounds)
    round_timeout_seconds = max(60, args.round_timeout_minutes * 60)

    lock_path = acquire_lock(group_id)
    rounds = 0
    last_signature = None

    print(f"\n启动 v1 自动调度器，商品组ID = {group_id}")
    print(f"轮询间隔 = {poll_seconds}s")
    print(f"最大触发轮数 = {max_rounds}")
    print(f"单轮等待上限 = {args.round_timeout_minutes} 分钟\n")

    try:
        while True:
            rows = get_group_variant_rows(group_id)
            sig = json.dumps(rows, ensure_ascii=False, sort_keys=True)

            if sig != last_signature:
                print_snapshot(rows)
                last_signature = sig

            # 1. 遇到异常终态，保守停机
            bad_row = first_row_with_status(rows, STOP_STATUSES)
            if bad_row:
                print("[STOP] 发现异常终态，停止调度。")
                print(f"[STOP] {format_row(bad_row)}")
                sys.exit(10)

            # 2. 全部完成
            if rows and all(r["任务状态"] == STATUS_DONE for r in rows):
                print(f"[DONE] 商品组 {group_id} 的所有 variant 已完成。")
                sys.exit(0)

            # 3. 如果有执行中，继续等
            inflight_row = first_row_with_status(rows, INFLIGHT_STATUSES)
            if inflight_row:
                print(f'[WAIT] 当前有执行中: 变体 {inflight_row["变体序号"]}，继续等待。')
                time.sleep(poll_seconds)
                continue

            # 4. 如果没有执行中，但有待执行，则自动发下一轮
            runnable_row = first_row_with_status(rows, RUNNABLE_STATUSES)
            if runnable_row:
                if rounds >= max_rounds:
                    print("[STOP] 达到最大触发轮数，停止。")
                    sys.exit(11)

                vn = runnable_row["变体序号"]
                print(f"[TRIGGER] 当前无执行中，准备自动触发下一轮：变体 {vn}")
                send_to_manager(group_id)
                rounds += 1

                started_at = time.time()
                saw_inflight = False

                while True:
                    rows2 = get_group_variant_rows(group_id)
                    sig2 = json.dumps(rows2, ensure_ascii=False, sort_keys=True)
                    if sig2 != last_signature:
                        print_snapshot(rows2)
                        last_signature = sig2

                    bad_row2 = first_row_with_status(rows2, STOP_STATUSES)
                    if bad_row2:
                        print("[STOP] 本轮执行中出现异常终态，停止调度。")
                        print(f"[STOP] {format_row(bad_row2)}")
                        sys.exit(12)

                    if rows2 and all(r["任务状态"] == STATUS_DONE for r in rows2):
                        print(f"[DONE] 商品组 {group_id} 的所有 variant 已完成。")
                        sys.exit(0)

                    inflight_row2 = first_row_with_status(rows2, INFLIGHT_STATUSES)
                    if inflight_row2:
                        saw_inflight = True
                        print(f'[WAIT] 本轮已进入执行中: 变体 {inflight_row2["变体序号"]}')
                        time.sleep(poll_seconds)
                        continue

                    # 本轮收口：看见过执行中，现在执行中消失了
                    if saw_inflight and not inflight_row2:
                        print("[ROUND DONE] 本轮已收口，返回主循环判断下一轮。")
                        break

                    if time.time() - started_at > round_timeout_seconds:
                        print("[STOP] 单轮等待超时，停止调度，请人工检查。")
                        sys.exit(13)

                    time.sleep(poll_seconds)

                continue

            # 5. 没有执行中，也没有待执行
            print("[STOP] 当前组没有执行中，也没有待执行。")
            print("[STOP] 若你预期应继续推进，请人工检查表格状态。")
            sys.exit(14)

    finally:
        release_lock(lock_path)


if __name__ == "__main__":
    main()