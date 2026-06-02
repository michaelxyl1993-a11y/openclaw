"""Batch runner for opt-in real OpenAI LLM Judge reviews."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping

from .evidence_pack import DIMENSIONS
from .llm_judge_merger import (
    extract_items,
    load_json,
    merge_llm_judge_results,
    write_outputs as write_merger_outputs,
)
from .llm_judge_prompt import build_llm_judge_prompt
from .openai_llm_judge import (
    DEFAULT_MODEL,
    OPENAI_API_KEY_ENV,
    OPENAI_MODEL_ENV,
    REAL_LLM_ENABLED_ENV,
    build_openai_judge_input,
    is_real_llm_enabled,
    run_openai_llm_judge,
)


RESULTS_FILENAME = "all_evidence_real_llm_judge_results.json"
PROMPT_SAMPLES_FILENAME = "all_evidence_real_llm_judge_prompt_samples.json"
SUMMARY_JSON_FILENAME = "real_llm_judge_run_summary.json"
SUMMARY_MD_FILENAME = "real_llm_judge_run_summary.md"
REAL_MERGE_FILENAMES = {
    "merged_json": "all_evidence_with_real_llm_review.json",
    "merged_csv": "all_evidence_with_real_llm_review.csv",
    "summary_json": "real_llm_review_ops_summary.json",
    "summary_md": "real_llm_review_ops_summary.md",
}


def evaluate_real_llm_gate(
    real_llm_requested: bool,
    environ: Mapping[str, str] | None = None,
) -> tuple[bool, str]:
    env = environ if environ is not None else os.environ
    if not real_llm_requested:
        return False, "dry-run：未传入 --real-llm，未调用真实 OpenAI API。"
    if not is_real_llm_enabled(env):
        return False, f"disabled：{REAL_LLM_ENABLED_ENV} 未设置为 true，未调用真实 OpenAI API。"
    if not env.get(OPENAI_API_KEY_ENV, "").strip():
        return False, f"disabled：缺少 {OPENAI_API_KEY_ENV}，未调用真实 OpenAI API。"
    return True, ""


def build_disabled_result(evidence_item: dict[str, Any], message: str) -> dict[str, Any]:
    judge_input = build_openai_judge_input(evidence_item)
    evidence = judge_input["evidence_pack"]["evidence"]
    dimension_reviews = {
        dimension: {
            "evidence_sufficiency": evidence[dimension]["coverage"],
            "reason": message,
            "missing_evidence": list(evidence[dimension]["missing"]),
        }
        for dimension in DIMENSIONS
    }
    return {
        "product_id": judge_input["product_id"],
        "product_name": judge_input["product_name"],
        "rule_decision": judge_input["rule_decision"],
        "review_result": "insufficient_evidence",
        "confidence": "low",
        "challenge_reason": "",
        "missing_evidence": sorted(
            {
                missing
                for review in dimension_reviews.values()
                for missing in review["missing_evidence"]
            }
        ),
        "dimension_reviews": dimension_reviews,
        "recommended_human_action": message,
        "real_llm_called": False,
    }


def sanitize_error(error: Exception | str, api_key: str = "") -> str:
    text = str(error)
    if api_key:
        text = text.replace(api_key, "[REDACTED]")
    return text


def prompt_sample(evidence_item: dict[str, Any], model: str) -> dict[str, str]:
    judge_input = build_openai_judge_input(evidence_item)
    prompt = build_llm_judge_prompt(judge_input)
    return {
        "product_id": judge_input["product_id"],
        "product_name": judge_input["product_name"],
        "model": model,
        "prompt_preview": prompt[:800],
    }


def error_result(evidence_item: dict[str, Any], error_message: str) -> dict[str, Any]:
    result = build_disabled_result(
        evidence_item,
        "真实 LLM Judge 调用失败，需人工复核或稍后重试。",
    )
    result["recommended_human_action"] = (
        "真实 LLM Judge 调用失败，需人工复核或稍后重试。"
    )
    result["runner_error"] = error_message
    return result


def validate_existing_results_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("existing results must be an object containing a results list.")
    seen: set[str] = set()
    for item in payload["results"]:
        if not isinstance(item, dict):
            raise ValueError("existing result items must be objects.")
        product_id = str(item.get("product_id", "")).strip()
        if not product_id:
            raise ValueError("existing result item missing product_id.")
        if product_id in seen:
            raise ValueError(f"duplicate existing result product_id: {product_id}")
        if item.get("runner_status") not in {"disabled", "success", "error"}:
            raise ValueError(f"{product_id}: invalid existing runner_status.")
        if not isinstance(item.get("real_llm_called"), bool):
            raise ValueError(f"{product_id}: existing real_llm_called must be a boolean.")
        seen.add(product_id)
    return payload


def load_existing_results(path: str | Path) -> dict[str, Any]:
    existing_path = Path(path)
    if not existing_path.exists():
        return {"results": []}
    return validate_existing_results_payload(load_json(existing_path))


def is_real_success(result: dict[str, Any] | None) -> bool:
    return bool(
        result
        and result.get("runner_status") == "success"
        and result.get("real_llm_called") is True
    )


def upsert_results(
    existing_results: list[dict[str, Any]],
    new_results: list[dict[str, Any]],
    *,
    force_overwrite_success: bool = False,
) -> tuple[list[dict[str, Any]], int, int, int, list[str]]:
    cumulative = {str(item["product_id"]): item for item in existing_results}
    appended = 0
    updated = 0
    protected = 0
    newly_successful: list[str] = []
    for item in new_results:
        product_id = str(item["product_id"])
        existing = cumulative.get(product_id)
        if (
            is_real_success(existing)
            and not is_real_success(item)
            and not force_overwrite_success
        ):
            protected += 1
            continue
        if existing is not None:
            updated += 1
        else:
            appended += 1
        if is_real_success(item) and not is_real_success(existing):
            newly_successful.append(product_id)
        cumulative[product_id] = item
    return list(cumulative.values()), appended, updated, protected, newly_successful


def run_batch(
    evidence_payload: Any,
    *,
    real_llm_requested: bool = False,
    limit: int | None = None,
    start_index: int = 0,
    model: str | None = None,
    sleep_seconds: float = 0,
    client: Any | None = None,
    environ: Mapping[str, str] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    append: bool = False,
    resume: bool = False,
    existing_results_payload: Any | None = None,
    force_overwrite_success: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    env = dict(environ if environ is not None else os.environ)
    if start_index < 0:
        raise ValueError("start_index must be >= 0.")
    if limit is not None and limit < 0:
        raise ValueError("limit must be >= 0.")
    if sleep_seconds < 0:
        raise ValueError("sleep_seconds must be >= 0.")

    if append and resume:
        raise ValueError("append and resume are mutually exclusive.")
    existing_payload = (
        validate_existing_results_payload(existing_results_payload)
        if existing_results_payload is not None
        else {"results": []}
    )
    existing_results = existing_payload["results"] if append or resume else []
    existing_by_id = {
        str(item["product_id"]): item for item in existing_results
    }

    products = extract_items(evidence_payload, "evidence payload")
    candidates = products[start_index:]
    resumed_skipped_product_ids: list[str] = []
    if resume:
        selected = []
        for product in candidates:
            product_id = str(product.get("product_id", ""))
            if (
                is_real_success(existing_by_id.get(product_id))
                and not force_overwrite_success
            ):
                resumed_skipped_product_ids.append(product_id)
                continue
            selected.append(product)
    else:
        selected = candidates
    if limit is not None:
        selected = selected[:limit]
    selected_model = model or env.get(OPENAI_MODEL_ENV) or DEFAULT_MODEL
    env[OPENAI_MODEL_ENV] = selected_model
    allow_real_call, disabled_message = evaluate_real_llm_gate(
        real_llm_requested, env
    )
    api_key = env.get(OPENAI_API_KEY_ENV, "").strip()

    results: list[dict[str, Any]] = []
    samples: list[dict[str, str]] = []
    for index, product in enumerate(selected):
        samples.append(prompt_sample(product, selected_model))
        if not allow_real_call:
            result = build_disabled_result(product, disabled_message)
            result.update({"runner_status": "disabled", "runner_error": ""})
            results.append(result)
            continue
        try:
            result = run_openai_llm_judge(product, client=client, environ=env)
            result.update({"runner_status": "success", "runner_error": ""})
        except Exception as exc:
            result = error_result(product, sanitize_error(exc, api_key))
            result["runner_status"] = "error"
        results.append(result)
        if sleep_seconds and index < len(selected) - 1:
            sleep_fn(sleep_seconds)

    (
        cumulative_results,
        appended_count,
        updated_count,
        protected_count,
        newly_successful_product_ids,
    ) = upsert_results(
        existing_results,
        results,
        force_overwrite_success=force_overwrite_success,
    )
    output_results = cumulative_results if append or resume else results
    results_payload = {
        "mode": "real_llm_judge_runner_v1.10.1",
        "real_llm_requested": real_llm_requested,
        "real_llm_enabled": is_real_llm_enabled(env),
        "model": selected_model,
        "product_count": len(products),
        "real_llm_called_count": sum(
            bool(result["real_llm_called"]) for result in output_results
        ),
        "results": output_results,
    }
    samples_payload = {
        "mode": "real_llm_judge_runner_prompt_samples_v1.10.1",
        "model": selected_model,
        "product_count": len(samples),
        "samples": samples,
    }
    summary = build_run_summary(
        total_products=len(products),
        results=results,
        real_llm_requested=real_llm_requested,
        real_llm_enabled=is_real_llm_enabled(env),
        model=selected_model,
        limit=limit,
        start_index=start_index,
        existing_results=existing_results,
        cumulative_results=output_results,
        appended_result_count=appended_count,
        updated_result_count=updated_count,
        protected_success_count=protected_count,
        force_overwrite_success=force_overwrite_success,
        newly_successful_product_ids=newly_successful_product_ids,
        resumed_skipped_product_ids=resumed_skipped_product_ids,
        evidence_products=products,
    )
    return results_payload, samples_payload, summary


def build_run_summary(
    *,
    total_products: int,
    results: list[dict[str, Any]],
    real_llm_requested: bool,
    real_llm_enabled: bool,
    model: str,
    limit: int | None,
    start_index: int,
    existing_results: list[dict[str, Any]] | None = None,
    cumulative_results: list[dict[str, Any]] | None = None,
    appended_result_count: int = 0,
    updated_result_count: int = 0,
    protected_success_count: int = 0,
    force_overwrite_success: bool = False,
    newly_successful_product_ids: list[str] | None = None,
    resumed_skipped_product_ids: list[str] | None = None,
    evidence_products: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    existing_results = existing_results or []
    cumulative_results = cumulative_results if cumulative_results is not None else results
    evidence_products = evidence_products or []
    newly_successful_product_ids = newly_successful_product_ids or []
    resumed_skipped_product_ids = resumed_skipped_product_ids or []
    cumulative_by_id = {
        str(result["product_id"]): result for result in cumulative_results
    }
    status_counts = Counter(result["runner_status"] for result in results)
    review_counts = Counter(result["review_result"] for result in results)
    confidence_counts = Counter(result["confidence"] for result in results)
    return {
        "total_products": total_products,
        "attempted_products": len(results),
        "real_llm_requested": real_llm_requested,
        "real_llm_enabled": real_llm_enabled,
        "model": model,
        "limit": limit,
        "start_index": start_index,
        "real_llm_called_count": sum(
            bool(result["real_llm_called"]) for result in results
        ),
        "skipped_count": max(total_products - len(results), 0),
        "success_count": status_counts.get("success", 0),
        "disabled_count": status_counts.get("disabled", 0),
        "error_count": status_counts.get("error", 0),
        "review_result_counts": dict(sorted(review_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "error_products": [
            {
                "product_id": result["product_id"],
                "product_name": result["product_name"],
                "runner_error": result["runner_error"],
            }
            for result in results
            if result["runner_status"] == "error"
        ],
        "existing_result_count": len(existing_results),
        "appended_result_count": appended_result_count,
        "updated_result_count": updated_result_count,
        "protected_success_count": protected_success_count,
        "force_overwrite_success": force_overwrite_success,
        "newly_successful_product_ids": newly_successful_product_ids,
        "attempted_product_ids": [
            str(result["product_id"]) for result in results
        ],
        "resumed_skipped_count": len(resumed_skipped_product_ids),
        "resumed_skipped_product_ids": resumed_skipped_product_ids,
        "cumulative_result_count": len(cumulative_results),
        "cumulative_real_success_count": sum(
            is_real_success(result) for result in cumulative_results
        ),
        "successful_product_ids": [
            str(result["product_id"])
            for result in cumulative_results
            if is_real_success(result)
        ],
        "not_reviewed_product_ids": [
            str(product.get("product_id", ""))
            for product in evidence_products
            if not is_real_success(cumulative_by_id.get(str(product.get("product_id", ""))))
        ],
        "output_files": {},
    }


def summary_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Product Intel v1.10.2 Real LLM Judge Run Summary",
            "",
            f"- 商品总数：{summary['total_products']}",
            f"- 本次处理商品数：{summary['attempted_products']}",
            f"- real LLM requested：{str(summary['real_llm_requested']).lower()}",
            f"- real LLM enabled：{str(summary['real_llm_enabled']).lower()}",
            f"- 模型：{summary['model']}",
            f"- limit：{summary['limit']}",
            f"- start index：{summary['start_index']}",
            f"- 真实 API 调用成功数：{summary['real_llm_called_count']}",
            f"- 跳过商品数：{summary['skipped_count']}",
            f"- success：{summary['success_count']}",
            f"- disabled：{summary['disabled_count']}",
            f"- error：{summary['error_count']}",
            f"- 已有结果数：{summary['existing_result_count']}",
            f"- 本次新增结果数：{summary['appended_result_count']}",
            f"- 本次更新结果数：{summary['updated_result_count']}",
            f"- 受保护真实成功结果数：{summary['protected_success_count']}",
            f"- 强制覆盖真实成功：{str(summary['force_overwrite_success']).lower()}",
            f"- 本次新增真实成功商品：{json.dumps(summary['newly_successful_product_ids'], ensure_ascii=False)}",
            f"- 本次尝试商品：{json.dumps(summary['attempted_product_ids'], ensure_ascii=False)}",
            f"- resume 跳过成功商品数：{summary['resumed_skipped_count']}",
            f"- resume 跳过成功商品：{json.dumps(summary['resumed_skipped_product_ids'], ensure_ascii=False)}",
            f"- 累计结果数：{summary['cumulative_result_count']}",
            f"- 累计真实成功商品数：{summary['cumulative_real_success_count']}",
            f"- 已真实成功商品：{json.dumps(summary['successful_product_ids'], ensure_ascii=False)}",
            f"- 尚未真实成功商品：{json.dumps(summary['not_reviewed_product_ids'], ensure_ascii=False)}",
            f"- review 分布：{json.dumps(summary['review_result_counts'], ensure_ascii=False)}",
            f"- confidence 分布：{json.dumps(summary['confidence_counts'], ensure_ascii=False)}",
            "",
            "## 输出文件",
            "",
            *[
                f"- {label}: {path}"
                for label, path in summary.get("output_files", {}).items()
            ],
            "",
        ]
    )


def write_runner_outputs(
    results_payload: dict[str, Any],
    samples_payload: dict[str, Any],
    summary: dict[str, Any],
    output_dir: str | Path,
    *,
    judge_results_output: str = RESULTS_FILENAME,
    merge: bool = False,
    evidence_payload: Any | None = None,
) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "judge_results": output / judge_results_output,
        "prompt_samples": output / PROMPT_SAMPLES_FILENAME,
        "run_summary_json": output / SUMMARY_JSON_FILENAME,
        "run_summary_md": output / SUMMARY_MD_FILENAME,
    }
    paths["judge_results"].write_text(
        json.dumps(results_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["prompt_samples"].write_text(
        json.dumps(samples_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if merge:
        if evidence_payload is None:
            raise ValueError("evidence_payload is required when merge=True.")
        merged = merge_llm_judge_results(evidence_payload, results_payload)
        paths.update(
            {
                f"merge_{label}": path
                for label, path in write_merger_outputs(
                    merged,
                    output,
                    filenames=REAL_MERGE_FILENAMES,
                ).items()
            }
        )
    summary["output_files"] = {
        label: str(path) for label, path in paths.items()
    }
    paths["run_summary_json"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["run_summary_md"].write_text(summary_markdown(summary), encoding="utf-8")
    return paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, help="all_evidence.json path")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--real-llm", action="store_true", help="Explicitly request real API calls")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--model")
    parser.add_argument("--sleep-seconds", type=float, default=0)
    parser.add_argument("--merge", action="store_true")
    parser.add_argument("--judge-results-output", default=RESULTS_FILENAME)
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--existing-results")
    parser.add_argument("--force-overwrite-success", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    evidence_payload = load_json(args.evidence)
    existing_path = args.existing_results or str(
        Path(args.output_dir) / args.judge_results_output
    )
    existing_results_payload = (
        load_existing_results(existing_path) if args.append or args.resume else None
    )
    results_payload, samples_payload, summary = run_batch(
        evidence_payload,
        real_llm_requested=args.real_llm,
        limit=args.limit,
        start_index=args.start_index,
        model=args.model,
        sleep_seconds=args.sleep_seconds,
        append=args.append,
        resume=args.resume,
        existing_results_payload=existing_results_payload,
        force_overwrite_success=args.force_overwrite_success,
    )
    paths = write_runner_outputs(
        results_payload,
        samples_payload,
        summary,
        args.output_dir,
        judge_results_output=args.judge_results_output,
        merge=args.merge,
        evidence_payload=evidence_payload,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for label, path in paths.items():
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()
