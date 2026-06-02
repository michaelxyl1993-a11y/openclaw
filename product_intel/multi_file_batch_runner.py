"""Run Product Intel against multiple source files and merge local outputs."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Sequence

from .decision_table import next_action
from .export_decision_table import DECISION_CSV_FIELDS, markdown_escape
from .run_product_intel import run_pipeline


MODE = "product_intel_multi_file_batch_v1.19"
SUPPORTED_SUFFIXES = {".csv", ".xlsx", ".xls"}
DECISION_NAMES = ("main_push", "small_test", "hold", "reject")
BATCH_FIELDS = (
    "batch_product_key",
    "batch_input_filename",
    "batch_input_path",
    "batch_source_detected",
    "batch_file_index",
    "batch_product_index",
)
COMBINED_DECISION_CSV_FIELDS = (*BATCH_FIELDS, *DECISION_CSV_FIELDS)


class MultiFileBatchError(ValueError):
    """Raised when a multi-file batch cannot be prepared safely."""


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _supported_file(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_SUFFIXES


def resolve_input_paths(
    inputs: Sequence[str | Path] | None = None,
    input_dir: str | Path | None = None,
    pattern: str = "*.xlsx",
) -> list[Path]:
    """Resolve explicit files or an input directory glob into validated files."""
    if bool(inputs) == bool(input_dir):
        raise MultiFileBatchError("Specify exactly one of --inputs or --input-dir.")

    if inputs:
        paths = [Path(item) for item in inputs]
    else:
        directory = Path(input_dir or "")
        if not directory.exists():
            raise MultiFileBatchError(f"Input directory does not exist: {directory}")
        if not directory.is_dir():
            raise MultiFileBatchError(f"Input directory is not a directory: {directory}")
        paths = sorted(path for path in directory.glob(pattern) if path.is_file())

    if not paths:
        raise MultiFileBatchError("No input files matched the requested batch.")

    validated: list[Path] = []
    for path in paths:
        if not path.exists():
            raise MultiFileBatchError(f"Input file does not exist: {path}")
        if not path.is_file():
            raise MultiFileBatchError(f"Input path is not a file: {path}")
        if not _supported_file(path):
            raise MultiFileBatchError(
                f"Unsupported input file type for {path}: expected CSV, XLSX, or XLS."
            )
        validated.append(path)
    return validated


def _decision_counts(products: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(product.get("decision", "")) for product in products)
    return {name: counts.get(name, 0) for name in DECISION_NAMES}


def _next_action_conflicts(products: Iterable[dict[str, Any]]) -> int:
    conflicts = 0
    for product in products:
        decision = str(product.get("decision", ""))
        if decision not in DECISION_NAMES:
            conflicts += 1
            continue
        if next_action(decision) not in str(product.get("next_action", "")):
            conflicts += 1
    return conflicts


def _duplicate_product_id_count(products: Iterable[dict[str, Any]]) -> int:
    counts = Counter(str(product.get("product_id", "")) for product in products)
    return sum(count - 1 for count in counts.values() if count > 1)


def _output_stem(path: Path, file_index: int, used_stems: set[str]) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("._") or "input"
    candidate = stem
    if candidate in used_stems:
        candidate = f"{stem}_{file_index:02d}"
    used_stems.add(candidate)
    return candidate


def _batch_product_key(file_index: int, product_index: int, product_id: Any) -> str:
    return f"file-{file_index:03d}:product-{product_index:03d}:{product_id or 'missing-id'}"


def _enrich_product(
    product: dict[str, Any],
    input_path: Path,
    source_detected: str,
    file_index: int,
    product_index: int,
) -> dict[str, Any]:
    enriched = deepcopy(product)
    enriched.update(
        {
            "batch_input_filename": input_path.name,
            "batch_input_path": str(input_path),
            "batch_source_detected": source_detected,
            "batch_file_index": file_index,
            "batch_product_index": product_index,
            "batch_product_key": _batch_product_key(
                file_index, product_index, product.get("product_id")
            ),
        }
    )
    return enriched


def _enrich_decision_row(
    row: dict[str, Any], product: dict[str, Any]
) -> dict[str, Any]:
    enriched = {field: product.get(field, "") for field in BATCH_FIELDS}
    enriched.update(deepcopy(row))
    return enriched


def _write_combined_decision_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COMBINED_DECISION_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in COMBINED_DECISION_CSV_FIELDS})


def _write_combined_decision_markdown(
    path: Path, rows: list[dict[str, Any]]
) -> None:
    lines = [
        "# Product Intel 多文件合并决策表",
        "",
        "| batch_product_key | 输入文件 | 来源 | 商品 ID | 商品名 | 分数 | 决策 | 下一步动作 |",
        "| --- | --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| {key} | {filename} | {source} | {product_id} | {product_name} | "
            "{score} | {decision} | {action} |".format(
                key=markdown_escape(row.get("batch_product_key", "")),
                filename=markdown_escape(row.get("batch_input_filename", "")),
                source=markdown_escape(row.get("batch_source_detected", "")),
                product_id=markdown_escape(row.get("product_id", "")),
                product_name=markdown_escape(row.get("product_name", "")),
                score=markdown_escape(row.get("opportunity_score", "")),
                decision=markdown_escape(row.get("decision", "")),
                action=markdown_escape(row.get("next_action", "")),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_summary_markdown(
    path: Path, manifest: dict[str, Any], summary: dict[str, Any]
) -> None:
    lines = [
        "# Product Intel v1.19 多文件批处理汇总",
        "",
        "## 输入文件",
        "",
        "| 文件 | 识别来源 | 映射置信度 | 字段质量分 | 商品数 | main_push | small_test | hold | reject |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in manifest["inputs"]:
        counts = item["decision_counts"]
        lines.append(
            "| {filename} | {source} | {confidence} | {quality} | {products} | "
            "{main_push} | {small_test} | {hold} | {reject} |".format(
                filename=markdown_escape(item["input_filename"]),
                source=markdown_escape(item["source_detected"]),
                confidence=markdown_escape(item["mapping_confidence"]),
                quality=item["field_quality_score"],
                products=item["product_count"],
                **counts,
            )
        )

    counts = summary["decision_counts"]
    lines.extend(
        [
            "",
            "## 合计",
            "",
            f"- 输入文件数：{summary['total_input_files']}",
            f"- 商品总数：{summary['total_products']}",
            (
                "- 决策分布："
                f"main_push {counts['main_push']} / "
                f"small_test {counts['small_test']} / "
                f"hold {counts['hold']} / reject {counts['reject']}"
            ),
            f"- 重复 product_id 数量：{summary['duplicate_product_id_count']}",
            f"- next_action 冲突数量：{summary['next_action_conflicts']}",
            f"- 错误数量：{summary['error_count']}",
            "",
            "## 下游建议",
            "",
            "- 合并后的 `multi_file_all_evidence.json` 可进入 LLM Judge 复核层。",
            "- 合并后的决策表可进入 final ops exporter。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_multi_file_batch(
    *,
    inputs: Sequence[str | Path] | None = None,
    input_dir: str | Path | None = None,
    pattern: str = "*.xlsx",
    source: str = "auto",
    market: str = "all",
    output_dir: str | Path = "product_intel/output_multi_file",
) -> dict[str, Any]:
    """Run each input independently and generate merged local-only outputs."""
    input_paths = resolve_input_paths(inputs=inputs, input_dir=input_dir, pattern=pattern)
    output_root = Path(output_dir)
    per_file_root = output_root / "per_file"
    output_root.mkdir(parents=True, exist_ok=True)

    manifest_inputs: list[dict[str, Any]] = []
    combined_products: list[dict[str, Any]] = []
    combined_rows: list[dict[str, Any]] = []
    used_stems: set[str] = set()

    for file_index, input_path in enumerate(input_paths):
        per_file_dir = per_file_root / _output_stem(input_path, file_index, used_stems)
        result = run_pipeline(
            input_path=input_path,
            source=source,
            market=market,
            output_dir=per_file_dir,
        )
        profile = result["profile"]
        source_detected = str(profile.get("source_detected", "unknown"))
        per_file_products = result["payload"]["products"]
        per_file_rows = result["rows"]
        if len(per_file_products) != len(per_file_rows):
            raise MultiFileBatchError(
                f"Manager payload and decision table size mismatch for {input_path}."
            )

        enriched_products: list[dict[str, Any]] = []
        for product_index, (product, row) in enumerate(zip(per_file_products, per_file_rows)):
            enriched = _enrich_product(
                product=product,
                input_path=input_path,
                source_detected=source_detected,
                file_index=file_index,
                product_index=product_index,
            )
            enriched_products.append(enriched)
            combined_products.append(enriched)
            combined_rows.append(_enrich_decision_row(row, enriched))

        manifest_inputs.append(
            {
                "input_path": str(input_path),
                "input_filename": input_path.name,
                "output_dir": str(per_file_dir),
                "source_requested": source,
                "source_detected": source_detected,
                "mapping_confidence": profile.get("mapping_confidence", "missing"),
                "field_quality_score": profile.get("field_quality_score", 0),
                "product_count": len(enriched_products),
                "decision_counts": _decision_counts(enriched_products),
            }
        )

    source_counts = Counter(item["source_detected"] for item in manifest_inputs)
    summary = {
        "total_input_files": len(input_paths),
        "total_products": len(combined_products),
        "source_detected_counts": dict(sorted(source_counts.items())),
        "decision_counts": _decision_counts(combined_products),
        "next_action_conflicts": _next_action_conflicts(combined_products),
        "duplicate_product_id_count": _duplicate_product_id_count(combined_products),
        "error_count": 0,
    }
    combined_manager_payload = {
        "version": "product_intel_multi_file_manager_payload_v1.19",
        "mode": MODE,
        "meta": {
            "source": "multi_file",
            "source_requested": source,
            "market": market,
            "total_input_files": len(input_paths),
        },
        "summary": summary,
        "products": combined_products,
    }
    all_evidence = {
        "mode": "product_intel_multi_file_all_evidence_v1.19",
        "product_count": len(combined_products),
        "products": combined_products,
    }
    output_paths = {
        "manifest_json": output_root / "multi_file_batch_manifest.json",
        "summary_json": output_root / "multi_file_batch_summary.json",
        "summary_md": output_root / "multi_file_batch_summary.md",
        "combined_manager_payload_json": output_root
        / "multi_file_combined_manager_payload.json",
        "combined_decision_table_csv": output_root
        / "multi_file_combined_decision_table.csv",
        "combined_decision_table_md": output_root
        / "multi_file_combined_decision_table.md",
        "all_evidence_json": output_root / "multi_file_all_evidence.json",
    }
    manifest = {
        "mode": MODE,
        "input_count": len(input_paths),
        "inputs": manifest_inputs,
        "combined_outputs": {key: str(path) for key, path in output_paths.items()},
    }

    _json_dump(output_paths["manifest_json"], manifest)
    _json_dump(output_paths["summary_json"], summary)
    _write_summary_markdown(output_paths["summary_md"], manifest, summary)
    _json_dump(output_paths["combined_manager_payload_json"], combined_manager_payload)
    _write_combined_decision_csv(output_paths["combined_decision_table_csv"], combined_rows)
    _write_combined_decision_markdown(output_paths["combined_decision_table_md"], combined_rows)
    _json_dump(output_paths["all_evidence_json"], all_evidence)

    return {
        "manifest": manifest,
        "summary": summary,
        "combined_manager_payload": combined_manager_payload,
        "combined_decision_rows": combined_rows,
        "all_evidence": all_evidence,
        "output_files": {key: str(path) for key, path in output_paths.items()},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Product Intel against multiple local CSV or Excel inputs."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--inputs", nargs="+", help="Explicit CSV/XLSX/XLS input files.")
    group.add_argument("--input-dir", help="Directory containing batch input files.")
    parser.add_argument("--pattern", default="*.xlsx", help="Glob for --input-dir mode.")
    parser.add_argument("--source", default="auto", help="Source override or auto.")
    parser.add_argument("--market", default="all", help="Market label passed to the pipeline.")
    parser.add_argument(
        "--output-dir",
        default="product_intel/output_multi_file",
        help="Directory for per-file and merged outputs.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_multi_file_batch(
        inputs=args.inputs,
        input_dir=args.input_dir,
        pattern=args.pattern,
        source=args.source,
        market=args.market,
        output_dir=args.output_dir,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
