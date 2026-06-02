"""Regression tests for the evidence-bounded Product Intel v1.8 Judge prompt."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from .llm_judge_contract import build_llm_judge_input
from .llm_judge_prompt import build_llm_judge_prompt
from .run_product_intel import run_pipeline


PACKAGE_DIR = Path(__file__).resolve().parent


def main() -> None:
    with TemporaryDirectory() as output_dir:
        result = run_pipeline(
            PACKAGE_DIR / "mock_echotik_products.xlsx",
            source="auto",
            market="de",
            output_dir=output_dir,
        )
    product = result["payload"]["products"][0]
    prompt = build_llm_judge_prompt(build_llm_judge_input(product))
    for text in [
        "只能基于 evidence_pack",
        "不允许脑补",
        "不允许使用外部实时信息",
        "严格 JSON",
        "不允许直接修改或覆盖 rule_decision",
    ]:
        if text not in prompt:
            raise AssertionError(f"judge prompt missing guardrail: {text}")
    if product["decision"] not in prompt or product["product_id"] not in prompt:
        raise AssertionError("judge prompt missing product rule context")
    print("LLM Judge prompt tests passed.")


if __name__ == "__main__":
    main()
