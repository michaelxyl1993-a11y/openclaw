"""Regression tests for the local-only Product Intel v1.8 LLM Judge contract."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from .llm_judge_contract import build_llm_judge_input, validate_llm_judge_input, validate_llm_judge_output
from .mock_llm_judge import mock_llm_judge
from .run_product_intel import run_pipeline


PACKAGE_DIR = Path(__file__).resolve().parent
SOURCES = ["echotik", "fastmoss", "kalodata", "manual"]


def main() -> None:
    counts: Counter[str] = Counter()
    for source in SOURCES:
        with TemporaryDirectory() as output_dir:
            result = run_pipeline(
                PACKAGE_DIR / f"mock_{source}_products.xlsx",
                source="auto",
                market="de",
                output_dir=output_dir,
            )
        for product in result["payload"]["products"]:
            before = {
                "decision": product["decision"],
                "next_action": product["next_action"],
                "opportunity_score": product["opportunity_score"],
            }
            judge_input = build_llm_judge_input(product)
            validate_llm_judge_input(judge_input)
            if not judge_input.get("evidence_pack"):
                raise AssertionError(f"{source}: judge input missing evidence_pack: {judge_input}")
            judge_output = mock_llm_judge(judge_input)
            validate_llm_judge_output(judge_output)
            after = {
                "decision": product["decision"],
                "next_action": product["next_action"],
                "opportunity_score": product["opportunity_score"],
            }
            if before != after:
                raise AssertionError(f"{source}: LLM Judge contract changed rule result: before={before}, after={after}")
            if product.get("llm_judge_ready") is not True:
                raise AssertionError(f"{source}: product should be LLM Judge ready: {product}")
            ref = product.get("llm_judge_input_ref", {})
            if ref.get("product_id") != product["product_id"] or ref.get("evidence_pack_field") != "evidence_pack":
                raise AssertionError(f"{source}: invalid llm_judge_input_ref: {product}")
            counts[product["decision"]] += 1
    expected = {"main_push": 1, "small_test": 8, "hold": 3}
    if dict(counts) != expected:
        raise AssertionError(f"realistic output decision distribution changed: expected {expected}, got {dict(counts)}")
    print("LLM Judge contract tests passed.")


if __name__ == "__main__":
    main()
