#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from typing import Any, Dict, List, Tuple

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


def get_record_list(limit: int = 200, offset: int = 0) -> Dict[str, Any]:
    args = [
        LARK_CLI,
        "base",
        "+record-list",
        "--as", "user",
        "--base-token", BASE_TOKEN,
        "--table-id", TABLE_ID,
        "--limit", str(limit),
        "--offset", str(offset),
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


def fetch_all_rows(page_limit: int = 200, max_pages: int = 100) -> Tuple[List[Any], List[str], List[Dict[str, Any]]]:
    all_rows: List[Any] = []
    all_record_ids: List[str] = []
    page_stats: List[Dict[str, Any]] = []

    offset = 0
    page_no = 1
    seen_page_signatures = set()

    while True:
        if page_no > max_pages:
            raise RuntimeError(f"分页超过安全上限 max_pages={max_pages}，疑似死循环，请检查")

        payload = get_record_list(limit=page_limit, offset=offset)
        rows = extract_rows(payload)
        record_ids = extract_record_ids(payload)

        if len(rows) != len(record_ids):
            raise ValueError(f"第 {page_no} 页 rows 数量与 record_id_list 数量不一致")

        page_size = len(rows)
        signature = None
        if page_size > 0:
            signature = (record_ids[0], record_ids[-1], page_size)
            if signature in seen_page_signatures:
                raise RuntimeError(f"检测到重复页，疑似 offset 分页异常：page_no={page_no}, signature={signature}")
            seen_page_signatures.add(signature)

        page_stats.append({
            "page_no": page_no,
            "offset": offset,
            "page_size": page_size,
            "first_record_id": record_ids[0] if page_size > 0 else None,
            "last_record_id": record_ids[-1] if page_size > 0 else None,
        })

        if page_size == 0:
            break

        all_rows.extend(rows)
        all_record_ids.extend(record_ids)

        offset += page_size
        page_no += 1

    return all_rows, all_record_ids, page_stats


def get_group_records(group_id: str, page_limit: int = 200, max_pages: int = 100, debug: bool = False) -> Dict[str, Any]:
    rows, record_ids, page_stats = fetch_all_rows(page_limit=page_limit, max_pages=max_pages)

    if len(rows) != len(record_ids):
        raise ValueError("全量 rows 数量与 record_id_list 数量不一致")

    candidate_record_ids: List[str] = []

    # 第一步：全量分页后再做粗筛
    for idx, row in enumerate(rows):
        row_text = json.dumps(row, ensure_ascii=False)
        if group_id in row_text:
            candidate_record_ids.append(record_ids[idx])

    # 去重，保留顺序
    dedup_candidate_record_ids = list(dict.fromkeys(candidate_record_ids))

    seed_record_ids: List[str] = []
    variant_record_ids: List[str] = []
    inspected_records: List[Dict[str, Any]] = []

    # 第二步：对候选逐条 record-get 精确判断
    for record_id in dedup_candidate_record_ids:
        record_payload = get_record(record_id)
        fields = normalize_value(extract_fields(record_payload))

        current_group_id = fields.get("商品组ID")
        task_type = fields.get("任务类型")
        variant_no = fields.get("变体序号")
        status = fields.get("任务状态")

        if current_group_id != group_id:
            if debug:
                inspected_records.append({
                    "record_id": record_id,
                    "group_id": current_group_id,
                    "task_type": task_type,
                    "variant_no": variant_no,
                    "status": status,
                    "matched": False,
                })
            continue

        matched = False
        if task_type == "seed" and (variant_no is None or variant_no == ""):
            seed_record_ids.append(record_id)
            matched = True
        elif task_type == "variant":
            variant_record_ids.append(record_id)
            matched = True

        if debug:
            inspected_records.append({
                "record_id": record_id,
                "group_id": current_group_id,
                "task_type": task_type,
                "variant_no": variant_no,
                "status": status,
                "matched": matched,
            })

    result = {
        "ok": True,
        "group_id": group_id,
        "seed_record_ids": seed_record_ids,
        "variant_record_ids": variant_record_ids,
        "seed_count": len(seed_record_ids),
        "variant_count": len(variant_record_ids),
        "total_rows_scanned": len(rows),
        "total_pages_scanned": len([p for p in page_stats if p["page_size"] > 0]),
        "candidate_record_count": len(dedup_candidate_record_ids),
        "page_limit": page_limit,
    }

    if debug:
        result["page_stats"] = page_stats
        result["candidate_record_ids"] = dedup_candidate_record_ids
        result["inspected_records"] = inspected_records

    return result


def main():
    parser = argparse.ArgumentParser(description="Paged version of get_group_records using lark-cli offset pagination.")
    parser.add_argument("group_id", help="商品组ID，例如 20260404-009")
    parser.add_argument("--page-limit", type=int, default=200, help="每页拉取数量，默认 200")
    parser.add_argument("--max-pages", type=int, default=100, help="最大翻页数，默认 100")
    parser.add_argument("--debug", action="store_true", help="输出调试信息")
    args = parser.parse_args()

    group_id = args.group_id.strip()

    try:
        result = get_group_records(
            group_id=group_id,
            page_limit=args.page_limit,
            max_pages=args.max_pages,
            debug=args.debug,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({
            "ok": False,
            "group_id": group_id,
            "reason": str(e),
        }, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()