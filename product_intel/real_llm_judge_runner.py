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
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    env = dict(environ if environ is not None else os.environ)
    if start_index < 0:
        raise ValueError("start_index must be >= 0.")
    if limit is not None and limit < 0:
        raise ValueError("limit must be >= 0.")
    if sleep_seconds < 0:
        raise ValueError("sleep_seconds must be >= 0.")

    products = extract_items(evidence_payload, "evidence payload")
    selected = products[start_index:]
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

    results_payload = {
        "mode": "real_llm_judge_runner_v1.10",
        "real_llm_requested": real_llm_requested,
        "real_llm_enabled": is_real_llm_enabled(env),
        "model": selected_model,
        "product_count": len(products),
        "real_llm_called_count": sum(
            bool(result["real_llm_called"]) for result in results
        ),
        "results": results,
    }
    samples_payload = {
        "mode": "real_llm_judge_runner_prompt_samples_v1.10",
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
) -> dict[str, Any]:
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
        "output_files": {},
    }


def summary_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Product Intel v1.10 Real LLM Judge Run Summary",
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    evidence_payload = load_json(args.evidence)
    results_payload, samples_payload, summary = run_batch(
        evidence_payload,
        real_llm_requested=args.real_llm,
        limit=args.limit,
        start_index=args.start_index,
        model=args.model,
        sleep_seconds=args.sleep_seconds,
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

