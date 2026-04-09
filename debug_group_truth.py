#!/usr/bin/env python3
import argparse
import importlib.util
import inspect
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_MANAGER_OPS = "/Users/michaelchui/Desktop/openclaw_tools/manager_ops.py"
DEFAULT_BASE_URL = "https://open.feishu.cn"


APP_TOKEN_KEYS = [
    "BITABLE_APP_TOKEN",
    "FEISHU_BITABLE_APP_TOKEN",
    "FEISHU_APP_TOKEN",
    "APP_TOKEN",
]

TABLE_ID_KEYS = [
    "BITABLE_TABLE_ID",
    "FEISHU_BITABLE_TABLE_ID",
    "FEISHU_TABLE_ID",
    "TABLE_ID",
]

APP_ID_KEYS = [
    "FEISHU_APP_ID",
    "APP_ID",
    "LARK_APP_ID",
]

APP_SECRET_KEYS = [
    "FEISHU_APP_SECRET",
    "APP_SECRET",
    "LARK_APP_SECRET",
]

TENANT_TOKEN_KEYS = [
    "FEISHU_TENANT_ACCESS_TOKEN",
    "TENANT_ACCESS_TOKEN",
    "LARK_TENANT_ACCESS_TOKEN",
]


GROUP_ID_KEYS = ["商品组ID", "group_id"]
TASK_TYPE_KEYS = ["任务类型", "task_type"]
VARIANT_NO_KEYS = ["变体序号", "variant_no"]
STATUS_KEYS = ["任务状态", "status"]
NOTE_KEYS = ["备注", "note"]
SOURCE_SEED_KEYS = [
    "source_seed_record_id",
    "来源seed_record_id",
    "来源Seed记录ID",
    "源seed_record_id",
    "seed_record_id",
]


def http_json(method: str, url: str, headers: Optional[Dict[str, str]] = None, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    headers = headers or {}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            **headers,
            "Content-Type": "application/json; charset=utf-8",
        }

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} {url}\n{err_raw[:2000]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"network error for {url}: {e}")

    try:
        return json.loads(raw)
    except Exception:
        raise RuntimeError(f"non-json response from {url}: {raw[:1000]}")


def load_module(module_path: str):
    p = Path(module_path)
    if not p.exists():
        raise FileNotFoundError(f"manager_ops.py not found: {module_path}")

    spec = importlib.util.spec_from_file_location("manager_ops_debug_import", str(p))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module spec: {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def module_globals_map(module) -> Dict[str, Any]:
    out = {}
    for name in dir(module):
        if name.startswith("__"):
            continue
        try:
            out[name] = getattr(module, name)
        except Exception:
            pass
    return out


def pick_from_dict(d: Dict[str, Any], keys: List[str]) -> Optional[str]:
    for key in keys:
        value = d.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def guess_from_module_strings(module_map: Dict[str, Any], pattern: str) -> Optional[str]:
    regex = re.compile(pattern)
    for _, value in module_map.items():
        if isinstance(value, str) and regex.fullmatch(value.strip()):
            return value.strip()
    return None


def pick_field(fields: Dict[str, Any], keys: List[str]) -> Any:
    for key in keys:
        if key in fields:
            return fields[key]
    return None


def normalize_scalar(value: Any) -> Any:
    if isinstance(value, list):
        if len(value) == 1:
            return normalize_scalar(value[0])
        return value
    if isinstance(value, dict):
        if "text" in value and len(value) == 1:
            return value["text"]
        if "name" in value and len(value) == 1:
            return value["name"]
        if "id" in value and len(value) == 1:
            return value["id"]
    return value


def stringify(value: Any) -> str:
    value = normalize_scalar(value)
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(value)


def flatten_text(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(value)


def contains_text(value: Any, needle: str) -> bool:
    if not needle:
        return False
    text = flatten_text(value)
    return needle in text


def get_tenant_access_token(base_url: str, env_map: Dict[str, str], module_map: Dict[str, Any]) -> str:
    direct = pick_from_dict(env_map, TENANT_TOKEN_KEYS)
    if direct:
        return direct

    module_direct = pick_from_dict(module_map, TENANT_TOKEN_KEYS)
    if module_direct:
        return module_direct

    for fn_name in [
        "get_tenant_access_token",
        "_get_tenant_access_token",
        "fetch_tenant_access_token",
        "ensure_tenant_access_token",
    ]:
        fn = module_map.get(fn_name)
        if callable(fn):
            try:
                sig = inspect.signature(fn)
                if len(sig.parameters) == 0:
                    resp = fn()
                    if isinstance(resp, str) and resp.strip():
                        return resp.strip()
                    if isinstance(resp, dict):
                        token = resp.get("tenant_access_token") or resp.get("token")
                        if isinstance(token, str) and token.strip():
                            return token.strip()
            except Exception:
                pass

    app_id = pick_from_dict(env_map, APP_ID_KEYS) or pick_from_dict(module_map, APP_ID_KEYS)
    app_secret = pick_from_dict(env_map, APP_SECRET_KEYS) or pick_from_dict(module_map, APP_SECRET_KEYS)

    if not app_id or not app_secret:
        raise RuntimeError(
            "无法获取 tenant_access_token：没找到现成 token，也没找到 app_id/app_secret。"
        )

    url = f"{base_url}/open-apis/auth/v3/tenant_access_token/internal"
    resp = http_json("POST", url, body={
        "app_id": app_id,
        "app_secret": app_secret,
    })

    token = resp.get("tenant_access_token") or (resp.get("data") or {}).get("tenant_access_token")
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError(f"tenant_access_token 获取失败: {json.dumps(resp, ensure_ascii=False)[:1000]}")

    return token.strip()


def guess_bitable_ids(env_map: Dict[str, str], module_map: Dict[str, Any]) -> Tuple[str, str]:
    app_token = pick_from_dict(env_map, APP_TOKEN_KEYS) or pick_from_dict(module_map, APP_TOKEN_KEYS)
    table_id = pick_from_dict(env_map, TABLE_ID_KEYS) or pick_from_dict(module_map, TABLE_ID_KEYS)

    if not app_token:
        app_token = guess_from_module_strings(module_map, r"app[a-zA-Z0-9]{6,}") or guess_from_module_strings(env_map, r"app[a-zA-Z0-9]{6,}")
    if not table_id:
        table_id = guess_from_module_strings(module_map, r"tbl[a-zA-Z0-9]{6,}") or guess_from_module_strings(env_map, r"tbl[a-zA-Z0-9]{6,}")

    if not app_token or not table_id:
        raise RuntimeError(
            f"无法定位 app_token/table_id。当前探测结果 app_token={app_token!r}, table_id={table_id!r}"
        )

    return app_token, table_id


def list_all_records(base_url: str, tenant_access_token: str, app_token: str, table_id: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    page_token = None

    while True:
        query = {"page_size": 500}
        if page_token:
            query["page_token"] = page_token

        url = (
            f"{base_url}/open-apis/bitable/v1/apps/{urllib.parse.quote(app_token)}/"
            f"tables/{urllib.parse.quote(table_id)}/records?{urllib.parse.urlencode(query)}"
        )

        resp = http_json("GET", url, headers={
            "Authorization": f"Bearer {tenant_access_token}",
        })

        code = resp.get("code", 0)
        if code not in (0, None):
            raise RuntimeError(f"list records failed: {json.dumps(resp, ensure_ascii=False)[:2000]}")

        data = resp.get("data") or {}
        items = data.get("items") or []
        if not isinstance(items, list):
            raise RuntimeError(f"unexpected list response: {json.dumps(resp, ensure_ascii=False)[:2000]}")

        records.extend(items)

        has_more = bool(data.get("has_more"))
        page_token = data.get("page_token")
        if not has_more:
            break

    return records


def build_candidate(record: Dict[str, Any], target_group_id: str, seed_record_id: Optional[str], extra_needles: List[str]) -> Tuple[bool, Dict[str, Any]]:
    record_id = record.get("record_id")
    fields = record.get("fields") or {}
    row_text = flatten_text(fields)

    group_id_raw = pick_field(fields, GROUP_ID_KEYS)
    task_type_raw = pick_field(fields, TASK_TYPE_KEYS)
    variant_no_raw = pick_field(fields, VARIANT_NO_KEYS)
    status_raw = pick_field(fields, STATUS_KEYS)
    note_raw = pick_field(fields, NOTE_KEYS)
    source_seed_raw = pick_field(fields, SOURCE_SEED_KEYS)

    group_id = stringify(group_id_raw).strip()
    task_type = stringify(task_type_raw).strip()
    variant_no = stringify(variant_no_raw).strip()
    status = stringify(status_raw).strip()
    note = stringify(note_raw).strip()
    source_seed = stringify(source_seed_raw).strip()

    matched_by: List[str] = []

    if group_id == target_group_id:
        matched_by.append("exact_group_id")

    if target_group_id and target_group_id in row_text:
        matched_by.append("rough_group_text")

    if seed_record_id:
        if source_seed == seed_record_id:
            matched_by.append("exact_source_seed_record_id")
        if seed_record_id in row_text:
            matched_by.append("rough_seed_text")

    for needle in extra_needles:
        if needle and needle in row_text:
            matched_by.append(f"needle:{needle}")

    matched_by = sorted(set(matched_by))
    is_candidate = len(matched_by) > 0

    candidate = {
        "record_id": record_id,
        "group_id": group_id,
        "task_type": task_type,
        "variant_no": variant_no,
        "status": status,
        "note": note,
        "source_seed_record_id": source_seed,
        "matched_by": matched_by,
        "row_text_preview": row_text[:400],
        "fields": fields,
    }

    return is_candidate, candidate


def build_minimal_row(record: Dict[str, Any]) -> Dict[str, Any]:
    fields = record.get("fields") or {}
    return {
        "record_id": record.get("record_id"),
        "group_id": stringify(pick_field(fields, GROUP_ID_KEYS)).strip(),
        "task_type": stringify(pick_field(fields, TASK_TYPE_KEYS)).strip(),
        "variant_no": stringify(pick_field(fields, VARIANT_NO_KEYS)).strip(),
        "status": stringify(pick_field(fields, STATUS_KEYS)).strip(),
        "note": stringify(pick_field(fields, NOTE_KEYS)).strip(),
        "source_seed_record_id": stringify(pick_field(fields, SOURCE_SEED_KEYS)).strip(),
        "row_text_preview": flatten_text(fields)[:300],
    }


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Raw truth debug helper for bitable group scan.")
    parser.add_argument("group_id", help="target group id, e.g. 20260404-009")
    parser.add_argument("--seed-record-id", dest="seed_record_id", default="", help="optional seed record id")
    parser.add_argument("--needle", action="append", default=[], help="extra text needle; can pass multiple times")
    parser.add_argument("--manager-ops", default=DEFAULT_MANAGER_OPS, help="path to manager_ops.py")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Feishu/Lark base url")
    parser.add_argument("--out", default="", help="output report json path")
    return parser.parse_args()


def main():
    args = parse_args()
    target_group_id = args.group_id.strip()
    seed_record_id = args.seed_record_id.strip() or None
    extra_needles = [x.strip() for x in args.needle if isinstance(x, str) and x.strip()]

    try:
        env_map = dict(os.environ)
        module = load_module(args.manager_ops)
        module_map = module_globals_map(module)

        app_token, table_id = guess_bitable_ids(env_map, module_map)
        tenant_access_token = get_tenant_access_token(args.base_url, env_map, module_map)

        records = list_all_records(
            base_url=args.base_url,
            tenant_access_token=tenant_access_token,
            app_token=app_token,
            table_id=table_id,
        )

        candidates: List[Dict[str, Any]] = []
        exact_group_matches = 0
        seed_matches = 0
        rough_group_matches = 0

        minimal_rows: List[Dict[str, Any]] = []

        for record in records:
            minimal_rows.append(build_minimal_row(record))
            is_candidate, candidate = build_candidate(
                record=record,
                target_group_id=target_group_id,
                seed_record_id=seed_record_id,
                extra_needles=extra_needles,
            )
            if is_candidate:
                candidates.append(candidate)
                if "exact_group_id" in candidate["matched_by"]:
                    exact_group_matches += 1
                if "exact_source_seed_record_id" in candidate["matched_by"] or "rough_seed_text" in candidate["matched_by"]:
                    seed_matches += 1
                if "rough_group_text" in candidate["matched_by"]:
                    rough_group_matches += 1

        candidates.sort(
            key=lambda x: (
                0 if "exact_group_id" in x["matched_by"] else 1,
                0 if "exact_source_seed_record_id" in x["matched_by"] else 1,
                0 if x.get("task_type") == "variant" else 1,
                x.get("variant_no") or "",
                x.get("record_id") or "",
            )
        )

        out_path = Path(args.out) if args.out else Path(f"./debug_truth_{target_group_id}.json")
        jsonl_path = out_path.with_suffix(".jsonl")

        report = {
            "ok": True,
            "group_id": target_group_id,
            "seed_record_id": seed_record_id,
            "scan_summary": {
                "total_records_scanned": len(records),
                "candidate_count": len(candidates),
                "exact_group_match_count": exact_group_matches,
                "seed_related_match_count": seed_matches,
                "rough_group_text_match_count": rough_group_matches,
            },
            "runtime_context": {
                "manager_ops": str(Path(args.manager_ops)),
                "base_url": args.base_url,
                "app_token_tail": app_token[-6:] if len(app_token) >= 6 else app_token,
                "table_id": table_id,
                "extra_needles": extra_needles,
            },
            "candidates": candidates,
            "output_files": {
                "report_json": str(out_path.resolve()),
                "all_rows_jsonl": str(jsonl_path.resolve()),
            },
        }

        write_json(out_path, report)
        write_jsonl(jsonl_path, minimal_rows)

        print(json.dumps({
            "ok": True,
            "group_id": target_group_id,
            "seed_record_id": seed_record_id,
            "total_records_scanned": len(records),
            "candidate_count": len(candidates),
            "exact_group_match_count": exact_group_matches,
            "seed_related_match_count": seed_matches,
            "rough_group_text_match_count": rough_group_matches,
            "report_json": str(out_path.resolve()),
            "all_rows_jsonl": str(jsonl_path.resolve()),
        }, ensure_ascii=False, indent=2))

    except Exception as e:
        print(json.dumps({
            "ok": False,
            "group_id": args.group_id,
            "seed_record_id": args.seed_record_id,
            "reason": str(e),
        }, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()