"""Run multi-file evidence through LLM Judge review and final ops export."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from .final_ops_decision_exporter import (
    build_final_rows,
    load_review_rows,
    write_outputs as write_final_ops_outputs,
)
from .llm_judge_merger import extract_items, load_json
from .real_llm_judge_runner import (
    RESULTS_FILENAME,
    load_existing_results,
    run_batch,
    write_runner_outputs,
)


MODE = "feishu_multi_file_llm_ops_runner_v1.23"
SUMMARY_JSON = "feishu_multi_file_llm_ops_summary.json"
SUMMARY_MD = "feishu_multi_file_llm_ops_summary.md"
CHALLENGE_CSV = "final_challenge_products.csv"
REVIEW_NOTE_MD = "final_review_note.md"


class FeishuMultiFileLLMOpsRunnerError(ValueError):
    """Raised when evidence cannot enter the LLM ops workflow."""


def load_evidence_payload(path: str | Path) -> dict[str, Any]:
    evidence_path = Path(path)
    if not evidence_path.exists():
        raise FeishuMultiFileLLMOpsRunnerError(
            f"Evidence file does not exist: {evidence_path}"
        )
    payload = load_json(evidence_path)
    products = extract_items(payload, "evidence payload")
    if not products:
        raise FeishuMultiFileLLMOpsRunnerError("Evidence payload contains no products.")
    return payload


def _decision_counts(products: Sequence[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(
        str(product.get("decision") or product.get("rule_decision") or "")
        for product in products
    )
    return {
        "main_push": counts.get("main_push", 0),
        "small_test": counts.get("small_test", 0),
        "hold": counts.get("hold", 0),
        "reject": counts.get("reject", 0),
    }


def _write_challenge_outputs(
    final_rows: list[dict[str, str]],
    output_dir: str | Path,
) -> dict[str, Path]:
    output = Path(output_dir)
    challenge_rows = [
        row for row in final_rows if row.get("llm_review_result") == "challenge"
    ]
    csv_path = output / CHALLENGE_CSV
    note_path = output / REVIEW_NOTE_MD
    fields = [
        "product_id",
        "product_name",
        "source_platform",
        "rule_decision",
        "opportunity_score",
        "llm_confidence",
        "llm_challenge_reason",
        "final_ops_action",
        "final_ops_priority",
        "final_ops_reason",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in challenge_rows:
            writer.writerow({field: row.get(field, "") for field in fields})

    lines = [
        "# Product Intel Final Review Note",
        "",
        f"- challenge_count：{len(challenge_rows)}",
        "",
        "## Challenge Products",
        "",
    ]
    if challenge_rows:
        for row in challenge_rows:
            lines.append(
                f"- {row.get('product_id', '')}｜{row.get('product_name', '')}："
                f"{row.get('final_ops_reason', '')}"
            )
    else:
        lines.append("- 无")
    lines.append("")
    note_path.write_text("\n".join(lines), encoding="utf-8")
    return {"challenge_csv": csv_path, "review_note_md": note_path}


def _summary_markdown(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Product Intel v1.23 Feishu Multi-file LLM Ops Summary",
            "",
            f"- 商品总数：{summary['total_products']}",
            f"- evidence：{summary['evidence_path']}",
            f"- real_llm_requested：{str(summary['real_llm_requested']).lower()}",
            f"- real_llm_enabled：{str(summary['real_llm_enabled']).lower()}",
            f"- real_llm_called_count：{summary['real_llm_called_count']}",
            f"- success_count：{summary['success_count']}",
            f"- error_count：{summary['error_count']}",
            f"- LLM review 分布：{json.dumps(summary['llm_review_result_counts'], ensure_ascii=False)}",
            f"- confidence 分布：{json.dumps(summary['confidence_counts'], ensure_ascii=False)}",
            f"- 规则决策分布：{json.dumps(summary['decision_counts'], ensure_ascii=False)}",
            f"- final priority 分布：{json.dumps(summary['final_priority_counts'], ensure_ascii=False)}",
            f"- challenge_count：{summary['challenge_count']}",
            f"- ready_for_feishu_message：{str(summary['ready_for_feishu_message']).lower()}",
            "",
            "## 输出文件",
            "",
            *[
                f"- {label}: {path}"
                for label, path in summary.get("output_files", {}).items()
            ],
            "",
            "## 下一步",
            "",
            f"`{summary['next_command']}`" if summary.get("next_command") else "- 无",
            "",
        ]
    )


def _next_command(output_dir: str | Path) -> str:
    output = Path(output_dir)
    if (output / "final_ops_decision_table.csv").exists():
        return (
            "python3 -m product_intel.feishu_clean_message_pack "
            f"--handoff-message product_intel/output_next_round/feishu_ops_handoff_message.md "
            f"--final-summary {output / 'final_ops_action_summary.json'} "
            f"--final-table {output / 'final_ops_decision_table.csv'} "
            f"--output-dir {output}"
        )
    return ""


def run_feishu_multi_file_llm_ops(
    *,
    evidence: str | Path,
    output_dir: str | Path,
    model: str | None = None,
    limit: int | None = None,
    start_index: int = 0,
    real_llm: bool = False,
    resume: bool = False,
    force_overwrite_success: bool = False,
    environ: Mapping[str, str] | None = None,
    client: Any | None = None,
) -> dict[str, Any]:
    evidence_path = Path(evidence)
    output = Path(output_dir)
    evidence_payload = load_evidence_payload(evidence_path)
    products = extract_items(evidence_payload, "evidence payload")
    existing_results_payload = (
        load_existing_results(output / RESULTS_FILENAME) if resume else None
    )

    results_payload, samples_payload, run_summary = run_batch(
        evidence_payload,
        real_llm_requested=real_llm,
        limit=limit,
        start_index=start_index,
        model=model,
        resume=resume,
        existing_results_payload=existing_results_payload,
        force_overwrite_success=force_overwrite_success,
        environ=environ,
        client=client,
    )
    runner_paths = write_runner_outputs(
        results_payload,
        samples_payload,
        run_summary,
        output,
        merge=True,
        evidence_payload=evidence_payload,
    )

    merged_csv = output / "all_evidence_with_real_llm_review.csv"
    final_rows = build_final_rows(load_review_rows(merged_csv))
    final_paths, final_summary = write_final_ops_outputs(final_rows, output)
    extra_paths = _write_challenge_outputs(final_rows, output)

    final_priority_counts = final_summary.get("final_ops_priority_counts", {})
    llm_review_counts = run_summary.get("review_result_counts", {})
    confidence_counts = run_summary.get("confidence_counts", {})
    challenge_count = int(final_summary.get("human_review_first_count", 0) or 0)
    output_files = {
        **{key: str(path) for key, path in runner_paths.items()},
        **{key: str(path) for key, path in final_paths.items()},
        **{key: str(path) for key, path in extra_paths.items()},
    }
    summary = {
        "mode": MODE,
        "total_products": len(products),
        "evidence_path": str(evidence_path),
        "real_llm_requested": real_llm,
        "real_llm_enabled": bool(run_summary.get("real_llm_enabled", False)),
        "real_llm_called_count": run_summary.get("real_llm_called_count", 0),
        "success_count": run_summary.get("success_count", 0),
        "error_count": run_summary.get("error_count", 0),
        "llm_review_result_counts": llm_review_counts,
        "confidence_counts": confidence_counts,
        "decision_counts": _decision_counts(products),
        "final_priority_counts": final_priority_counts,
        "challenge_count": challenge_count,
        "ready_for_feishu_message": bool(final_rows),
        "output_files": output_files,
        "next_command": _next_command(output),
    }
    output.mkdir(parents=True, exist_ok=True)
    summary_json = output / SUMMARY_JSON
    summary_md = output / SUMMARY_MD
    summary["output_files"]["summary_json"] = str(summary_json)
    summary["output_files"]["summary_md"] = str(summary_md)
    summary_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary_md.write_text(_summary_markdown(summary), encoding="utf-8")
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--real-llm", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--force-overwrite-success", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_feishu_multi_file_llm_ops(
        evidence=args.evidence,
        output_dir=args.output_dir,
        model=args.model,
        limit=args.limit,
        start_index=args.start_index,
        real_llm=args.real_llm,
        resume=args.resume,
        force_overwrite_success=args.force_overwrite_success,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
