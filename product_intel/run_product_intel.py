"""CLI runner for Product Intel."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .batch_fact_sheet import build_batch_fact_sheets
from .input_adapter import load_products_from_file, load_raw_product_rows
from .csv_profile import profile_csv_rows
from .decision_table import build_decision_rows
from .export_csv_profile import save_csv_profile_json, save_csv_profile_markdown
from .export_decision_table import save_decision_csv, save_decision_markdown
from .export_manager_payload import save_manager_payload_json
from .manager_payload import build_manager_payload


VALID_SOURCES = {"auto", "mock", "echotik", "fastmoss", "manual"}
VALID_MARKETS = {"all", "de", "fr", "uk", "us"}
VALID_FORMATS = {"all", "decision_csv", "decision_md", "manager_json"}


class ProductIntelRunError(ValueError):
    """Raised for user-facing runner validation errors."""


def validate_choice(name: str, value: str, valid_values: set[str]) -> str:
    normalized = value.strip().lower()
    if normalized not in valid_values:
        allowed = ", ".join(sorted(valid_values))
        raise ProductIntelRunError(f"invalid {name}: {value}. Allowed values: {allowed}")
    return normalized


def output_paths(output_dir: str | Path) -> dict[str, Path]:
    directory = Path(output_dir)
    return {
        "decision_csv": directory / "product_intel_decision_table.csv",
        "decision_md": directory / "product_intel_decision_table.md",
        "manager_json": directory / "product_intel_manager_payload.json",
        "csv_profile_json": directory / "product_intel_csv_profile.json",
        "csv_profile_md": directory / "product_intel_csv_profile.md",
    }


def run_pipeline(
    input_path: str | Path,
    source: str = "auto",
    market: str = "all",
    output_dir: str | Path = "product_intel/output",
    limit: int | None = None,
    output_format: str = "all",
    profile_only: bool = False,
) -> dict[str, Any]:
    source = validate_choice("source", source, VALID_SOURCES)
    market = validate_choice("market", market, VALID_MARKETS)
    output_format = validate_choice("format", output_format, VALID_FORMATS)
    path = Path(input_path)
    if not path.exists():
        raise ProductIntelRunError(f"input file does not exist: {path}")

    try:
        raw_rows, input_metadata = load_raw_product_rows(path)
    except ValueError as exc:
        raise ProductIntelRunError(str(exc)) from exc
    profile = profile_csv_rows(raw_rows, source=source, **input_metadata)
    paths = output_paths(output_dir)
    written: dict[str, str] = {
        "csv_profile_json": str(save_csv_profile_json(profile, paths["csv_profile_json"])),
        "csv_profile_md": str(save_csv_profile_markdown(profile, paths["csv_profile_md"])),
    }
    if profile_only:
        return {
            "input_path": str(path),
            "source": source,
            "market": market,
            "total_products": len(raw_rows),
            "profile": profile,
            "rows": [],
            "payload": {"meta": {"main_push_count": 0, "small_test_count": 0, "hold_count": 0, "reject_count": 0}, "products": []},
            "output_files": written,
        }

    try:
        products, _input_metadata = load_products_from_file(path, source=source)
    except ValueError as exc:
        raise ProductIntelRunError(str(exc)) from exc
    if limit is not None:
        products = products[: max(0, int(limit))]
    if not products:
        raise ProductIntelRunError(f"CSV is empty or no products were loaded: {path}")

    batch = build_batch_fact_sheets(products)
    results = batch["items"]
    rows = build_decision_rows(results)
    payload_market = "" if market == "all" else market
    payload = build_manager_payload(
        results,
        meta={
            "source": source,
            "market": payload_market,
            "input_path": str(path),
        },
    )

    if output_format in {"all", "decision_csv"}:
        written["decision_csv"] = str(save_decision_csv(rows, paths["decision_csv"]))
    if output_format in {"all", "decision_md"}:
        written["decision_md"] = str(save_decision_markdown(rows, paths["decision_md"]))
    if output_format in {"all", "manager_json"}:
        written["manager_json"] = str(save_manager_payload_json(payload, paths["manager_json"]))

    return {
        "input_path": str(path),
        "source": source,
        "market": market,
        "total_products": len(products),
        "profile": profile,
        "rows": rows,
        "payload": payload,
        "output_files": written,
    }


def run_product_intel(
    input_path: str | Path,
    source: str = "auto",
    market: str = "all",
    output_dir: str | Path = "product_intel/output",
    limit: int | None = None,
    output_format: str = "all",
    profile_only: bool = False,
) -> dict[str, Any]:
    """Backward-compatible wrapper for the v0.7 runner name."""
    return run_pipeline(
        input_path=input_path,
        source=source,
        market=market,
        output_dir=output_dir,
        limit=limit,
        output_format=output_format,
        profile_only=profile_only,
    )


def print_summary(result: dict[str, Any]) -> None:
    meta = result["payload"]["meta"]
    profile = result.get("profile", {})
    print(f"input path: {result['input_path']}")
    print(f"source: {result['source']}")
    print(f"market: {result['market']}")
    print(f"source_detected: {profile.get('source_detected', '')}")
    print(f"row_count: {profile.get('row_count', 0)}")
    print(f"missing_required_fields: {profile.get('missing_required_fields', [])}")
    print(f"missing_optional_fields: {profile.get('missing_optional_fields', [])}")
    print(f"warnings count: {len(profile.get('warnings', []))}")
    print(f"mapped fields: {profile.get('mapped_fields', {})}")
    print(f"total products: {result['total_products']}")
    print(f"main_push_count: {meta['main_push_count']}")
    print(f"small_test_count: {meta['small_test_count']}")
    print(f"hold_count: {meta['hold_count']}")
    print(f"reject_count: {meta['reject_count']}")
    print("top 5:")
    for product in result["payload"]["products"][:5]:
        print(
            f"- {product['product_name']} | "
            f"score={product['opportunity_score']} | "
            f"decision={product['decision']}"
        )
    print("output files:")
    for label, path in result["output_files"].items():
        print(f"- {label}: {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Product Intel over a CSV candidate file.")
    parser.add_argument("--input", required=True, help="Input CSV file path.")
    parser.add_argument("--source", default="auto", help="Source: auto, mock, echotik, fastmoss, manual.")
    parser.add_argument("--market", default="all", help="Market: all, de, fr, uk, us.")
    parser.add_argument("--output-dir", default="product_intel/output", help="Output directory.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of products for testing.")
    parser.add_argument("--format", default="all", help="Output format: all, decision_csv, decision_md, manager_json.")
    parser.add_argument("--profile-only", action="store_true", help="Only write CSV profile reports.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_pipeline(
            input_path=args.input,
            source=args.source,
            market=args.market,
            output_dir=args.output_dir,
            limit=args.limit,
            output_format=args.format,
            profile_only=args.profile_only,
        )
    except ProductIntelRunError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
