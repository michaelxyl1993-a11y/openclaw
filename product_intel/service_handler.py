"""Service-level wrapper for Product Intel jobs.

This module is intentionally framework-neutral so Feishu bots, HTTP apps, and
OpenClaw manager jobs can call Product Intel without shelling out to the CLI.
"""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

from .run_product_intel import ProductIntelRunError, run_pipeline


def empty_decision_summary(row_count: int = 0) -> dict[str, Any]:
    return {
        "total_products": row_count,
        "main_push_count": 0,
        "small_test_count": 0,
        "hold_count": 0,
        "reject_count": 0,
        "top_products": [],
    }


def compact_output_files(output_files: dict[str, str], profile_only: bool) -> dict[str, str]:
    compact = {
        "csv_profile_json": output_files.get("csv_profile_json", ""),
        "csv_profile_md": output_files.get("csv_profile_md", ""),
    }
    if not profile_only:
        compact.update(
            {
                "decision_table_csv": output_files.get("decision_csv", ""),
                "decision_table_md": output_files.get("decision_md", ""),
                "manager_payload_json": output_files.get("manager_json", ""),
            }
        )
    return compact


def build_decision_summary(payload: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("meta", {}) if isinstance(payload.get("meta", {}), dict) else {}
    products = payload.get("products", []) if isinstance(payload.get("products", []), list) else []
    top_products = []
    for product in products[:5]:
        top_products.append(
            {
                "rank": product.get("rank", 0),
                "product_id": product.get("product_id", ""),
                "product_name": product.get("product_name", ""),
                "opportunity_score": product.get("opportunity_score", 0),
                "decision": product.get("decision", ""),
                "recommended_formats": product.get("recommended_formats", []),
                "recommended_hooks": product.get("recommended_hooks", []),
            }
        )
    return {
        "total_products": meta.get("total_products", profile.get("row_count", 0)),
        "main_push_count": meta.get("main_push_count", 0),
        "small_test_count": meta.get("small_test_count", 0),
        "hold_count": meta.get("hold_count", 0),
        "reject_count": meta.get("reject_count", 0),
        "top_products": top_products,
    }


def build_summary_text(
    profile: dict[str, Any],
    decision_summary: dict[str, Any],
    output_files: dict[str, str],
    profile_only: bool,
) -> str:
    mapped_fields = profile.get("mapped_fields", {}) if isinstance(profile.get("mapped_fields", {}), dict) else {}
    mapped_count = sum(1 for value in mapped_fields.values() if value)
    warnings = profile.get("warnings", []) if isinstance(profile.get("warnings", []), list) else []
    lines = [
        "Product Intel 运行完成",
        f"任务类型：{'CSV 诊断' if profile_only else '完整选品分析'}",
        f"识别来源：{profile.get('source_detected', '')}",
        f"输入行数：{profile.get('row_count', 0)}",
        f"已映射字段数：{mapped_count}",
        f"warnings 数量：{len(warnings)}",
    ]
    if not profile_only:
        lines.extend(
            [
                f"商品总数：{decision_summary.get('total_products', 0)}",
                f"main_push：{decision_summary.get('main_push_count', 0)}",
                f"small_test：{decision_summary.get('small_test_count', 0)}",
                f"hold：{decision_summary.get('hold_count', 0)}",
                f"reject：{decision_summary.get('reject_count', 0)}",
                "Top 5 商品：",
            ]
        )
        top_products = decision_summary.get("top_products", [])
        if top_products:
            for product in top_products:
                lines.append(
                    f"{product.get('rank', '-')}. {product.get('opportunity_score', 0)} / "
                    f"{product.get('decision', '')} / {product.get('product_name', '')}"
                )
        else:
            lines.append("暂无 Top 商品。")
    lines.append("输出文件：")
    for label, path in output_files.items():
        if path:
            lines.append(f"- {label}: {path}")
    return "\n".join(lines)


def error_response(
    error: Exception,
    input_path: str,
    profile_only: bool,
    request_meta: dict[str, Any] | None,
) -> dict[str, Any]:
    message = str(error) or error.__class__.__name__
    return {
        "ok": False,
        "job_type": "profile_only" if profile_only else "full_run",
        "summary_text": f"Product Intel 运行失败：{message}\n输入文件：{input_path}",
        "profile": {},
        "decision_summary": empty_decision_summary(),
        "output_files": {},
        "warnings": [],
        "errors": [message],
        "request_meta": request_meta or {},
    }


def run_product_intel_job(
    input_path: str,
    source: str = "auto",
    market: str = "de",
    output_dir: str = "product_intel/output",
    limit: int | None = None,
    profile_only: bool = False,
    request_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run Product Intel and return a bot/HTTP friendly structured result."""
    try:
        result = run_pipeline(
            input_path=input_path,
            source=source,
            market=market,
            output_dir=output_dir,
            limit=limit,
            output_format="all",
            profile_only=profile_only,
        )
        profile = result.get("profile", {})
        output_files = compact_output_files(result.get("output_files", {}), profile_only)
        decision_summary = (
            empty_decision_summary(profile.get("row_count", 0))
            if profile_only
            else build_decision_summary(result.get("payload", {}), profile)
        )
        warnings = profile.get("warnings", []) if isinstance(profile.get("warnings", []), list) else []
        return {
            "ok": True,
            "job_type": "profile_only" if profile_only else "full_run",
            "summary_text": build_summary_text(profile, decision_summary, output_files, profile_only),
            "profile": profile,
            "decision_summary": decision_summary,
            "manager_payload": result.get("payload", {}),
            "output_files": output_files,
            "warnings": warnings,
            "errors": [],
            "request_meta": request_meta or {},
        }
    except ProductIntelRunError as exc:
        return error_response(exc, input_path, profile_only, request_meta)
    except Exception as exc:  # pragma: no cover - defensive wrapper for service callers.
        traceback.print_exc()
        return error_response(exc, input_path, profile_only, request_meta)


if __name__ == "__main__":
    demo = run_product_intel_job(
        input_path=str(Path(__file__).resolve().parent / "mock_products.csv"),
        source="auto",
        market="de",
        output_dir=str(Path(__file__).resolve().parent / "output"),
    )
    print(demo["summary_text"])
