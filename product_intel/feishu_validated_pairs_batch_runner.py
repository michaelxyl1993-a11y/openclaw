"""Run multi-file Product Intel from Feishu validated download pairs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .multi_file_batch_runner import run_multi_file_batch


MODE = "feishu_validated_pairs_batch_runner_v1.22"
SUMMARY_JSON = "feishu_validated_pairs_batch_runner_summary.json"
SUMMARY_MD = "feishu_validated_pairs_batch_runner_summary.md"


class FeishuValidatedPairsBatchRunnerError(ValueError):
    """Raised when validated pairs cannot be converted to local inputs."""


def load_validated_pairs(path: str | Path) -> list[dict[str, Any]]:
    input_path = Path(path)
    if not input_path.exists():
        raise FeishuValidatedPairsBatchRunnerError(
            f"Validated pairs JSON does not exist: {input_path}"
        )
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FeishuValidatedPairsBatchRunnerError(
            "Validated pairs JSON must be an object."
        )
    pairs = payload.get("validated_pairs")
    if not isinstance(pairs, list):
        raise FeishuValidatedPairsBatchRunnerError(
            "Validated pairs JSON must contain validated_pairs."
        )
    return [pair for pair in pairs if isinstance(pair, dict)]


def _first_path(pair: dict[str, Any]) -> str:
    for field in ("probe_download_path", "download_path", "target_path"):
        value = str(pair.get(field, "")).strip()
        if value:
            return value
    return ""


def resolve_input_files(pairs: Sequence[dict[str, Any]]) -> tuple[list[str], int]:
    input_files: list[str] = []
    missing_count = 0
    seen: set[str] = set()
    for pair in pairs:
        candidate = _first_path(pair)
        if not candidate:
            missing_count += 1
            continue
        path = Path(candidate)
        if not path.exists() or not path.is_file() or path.stat().st_size <= 0:
            missing_count += 1
            continue
        text = str(path)
        if text in seen:
            continue
        seen.add(text)
        input_files.append(text)
    return input_files, missing_count


def _next_command(output_dir: str | Path) -> str:
    evidence_path = Path(output_dir) / "multi_file_all_evidence.json"
    if evidence_path.exists():
        return (
            "run_real_llm_judge_or_final_ops_exporter_after_confirming "
            f"evidence output path: {evidence_path}"
        )
    return "run_real_llm_judge_or_final_ops_exporter_after_confirming evidence output path"


def build_summary_markdown(summary: dict[str, Any]) -> str:
    counts = summary.get("decision_counts", {})
    source_counts = summary.get("source_detected_counts", {})
    lines = [
        "# Product Intel v1.22 Feishu Validated Pairs Batch Runner",
        "",
        "## 结论",
        "",
        f"- validated_pair_count：{summary['validated_pair_count']}",
        f"- input_file_count：{summary['input_file_count']}",
        f"- missing_input_count：{summary['missing_input_count']}",
        f"- total_products：{summary['total_products']}",
        f"- error_count：{summary['error_count']}",
        f"- ready_for_llm_judge：{str(summary['ready_for_llm_judge']).lower()}",
        "",
        "## 来源识别",
        "",
    ]
    if source_counts:
        lines.extend(f"- {source}：{count}" for source, count in source_counts.items())
    else:
        lines.append("- 无")
    lines.extend(
        [
            "",
            "## 决策分布",
            "",
            f"- main_push：{counts.get('main_push', 0)}",
            f"- small_test：{counts.get('small_test', 0)}",
            f"- hold：{counts.get('hold', 0)}",
            f"- reject：{counts.get('reject', 0)}",
            "",
            "## 输入文件",
            "",
        ]
    )
    lines.extend(f"- {path}" for path in summary["input_files"])
    if not summary["input_files"]:
        lines.append("- 无")
    lines.extend(["", "## 下一步", "", f"`{summary['next_command']}`", ""])
    return "\n".join(lines)


def write_summary_outputs(summary: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary_json": output / SUMMARY_JSON,
        "summary_md": output / SUMMARY_MD,
    }
    paths["summary_json"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths["summary_md"].write_text(build_summary_markdown(summary), encoding="utf-8")
    return paths


def run_validated_pairs_batch(
    *,
    validated_pairs: str | Path,
    source: str = "auto",
    market: str = "all",
    output_dir: str | Path = "product_intel/output_multi_file_from_feishu",
) -> dict[str, Any]:
    pairs = load_validated_pairs(validated_pairs)
    input_files, missing_count = resolve_input_files(pairs)
    output = Path(output_dir)

    multi_summary: dict[str, Any] = {
        "total_products": 0,
        "source_detected_counts": {},
        "decision_counts": {"main_push": 0, "small_test": 0, "hold": 0, "reject": 0},
        "error_count": missing_count,
    }
    multi_summary_path = ""
    if input_files:
        result = run_multi_file_batch(
            inputs=input_files,
            source=source,
            market=market,
            output_dir=output,
        )
        multi_summary = result["summary"]
        multi_summary_path = str(output / "multi_file_batch_summary.json")

    ready = bool(input_files) and int(multi_summary.get("error_count", 0) or 0) == 0
    summary = {
        "mode": MODE,
        "validated_pair_count": len(pairs),
        "input_file_count": len(input_files),
        "missing_input_count": missing_count,
        "input_files": input_files,
        "source": source,
        "market": market,
        "output_dir": str(output),
        "multi_file_batch_summary_path": multi_summary_path,
        "total_products": multi_summary.get("total_products", 0),
        "source_detected_counts": multi_summary.get("source_detected_counts", {}),
        "decision_counts": multi_summary.get("decision_counts", {}),
        "error_count": multi_summary.get("error_count", missing_count),
        "ready_for_llm_judge": ready,
        "next_command": _next_command(output) if ready else "",
    }
    paths = write_summary_outputs(summary, output)
    summary["output_files"] = {key: str(path) for key, path in paths.items()}
    paths["summary_json"].write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validated-pairs", required=True)
    parser.add_argument("--source", default="auto")
    parser.add_argument("--market", default="all")
    parser.add_argument("--output-dir", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_validated_pairs_batch(
        validated_pairs=args.validated_pairs,
        source=args.source,
        market=args.market,
        output_dir=args.output_dir,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
