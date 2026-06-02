"""Regression tests for the local-only Product Intel v1.7 evidence layer."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from .batch_fact_sheet import build_batch_fact_sheets
from .decision_table import build_decision_rows
from .evidence_pack import DIMENSIONS
from .input_adapter import load_products_from_file
from .manager_payload import build_manager_payload
from .run_product_intel import run_pipeline


PACKAGE_DIR = Path(__file__).resolve().parent
REALISTIC_SOURCES = ["echotik", "fastmoss", "kalodata", "manual"]


def validate_evidence_pack(product: dict, expected_source: str) -> None:
    pack = product.get("evidence_pack")
    if not isinstance(pack, dict):
        raise AssertionError(f"missing evidence_pack: {product}")
    evidence = pack.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != set(DIMENSIONS):
        raise AssertionError(f"evidence_pack must expose 8 dimensions: {pack}")
    for dimension, item in evidence.items():
        if not isinstance(item, dict):
            raise AssertionError(f"{dimension}: evidence item must be a dict: {item}")
        if item.get("coverage") not in {"strong", "medium", "weak", "missing"}:
            raise AssertionError(f"{dimension}: invalid coverage: {item}")
        if not isinstance(item.get("missing"), list):
            raise AssertionError(f"{dimension}: missing must be a list: {item}")
    if pack.get("source_detected") != expected_source:
        raise AssertionError(f"source_detected missing from evidence pack: expected {expected_source}, got {pack}")
    if not isinstance(product.get("evidence_coverage_summary"), dict):
        raise AssertionError(f"missing evidence_coverage_summary: {product}")


def main() -> None:
    products, _ = load_products_from_file(PACKAGE_DIR / "mock_products.xlsx", source="mock")
    batch = build_batch_fact_sheets(products)
    rows = build_decision_rows(batch["items"])
    before = {row["product_id"]: row["decision"] for row in rows}
    payload = build_manager_payload(batch["items"], meta={"source": "mock", "source_detected": "mock", "market": "de"})
    after = {product["product_id"]: product["decision"] for product in payload["products"]}
    if before != after:
        raise AssertionError(f"evidence pack changed mock decisions: before={before}, after={after}")
    expected_mock_counts = {"main_push": 3, "small_test": 4, "hold": 1}
    if dict(Counter(after.values())) != expected_mock_counts:
        raise AssertionError(f"mock decision distribution changed: {Counter(after.values())}")
    for product in payload["products"]:
        validate_evidence_pack(product, "mock")

    realistic_counts: Counter[str] = Counter()
    for source in REALISTIC_SOURCES:
        with TemporaryDirectory() as output_dir:
            result = run_pipeline(
                PACKAGE_DIR / f"mock_{source}_products.xlsx",
                source="auto",
                market="de",
                output_dir=output_dir,
            )
        for product in result["payload"]["products"]:
            validate_evidence_pack(product, source)
            realistic_counts[product["decision"]] += 1
    expected_realistic_counts = {"main_push": 1, "small_test": 8, "hold": 3}
    if dict(realistic_counts) != expected_realistic_counts:
        raise AssertionError(f"realistic output decision distribution changed: {dict(realistic_counts)}")
    print("Evidence pack tests passed.")


if __name__ == "__main__":
    main()
