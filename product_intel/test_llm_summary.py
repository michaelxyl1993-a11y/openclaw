"""Smoke tests for Product Intel v1.3 LLM summary layer."""

from __future__ import annotations

import copy

from .llm_summary import attach_summary_to_payload, build_llm_summary_prompt, build_rule_based_summary


def mock_payload() -> dict:
    return {
        "version": "product_intel_v0.6",
        "meta": {
            "market": "de",
            "total_products": 3,
            "main_push_count": 1,
            "small_test_count": 1,
            "hold_count": 0,
            "reject_count": 1,
        },
        "summary": {
            "main_push_reasons_summary": ["7-day growth is above 20%.", "Commission rate is at least 8%."],
            "common_missing_evidence": [
                {"evidence": "external_trend: Google Trends signal", "count": 3},
                {"evidence": "competition: same SKU count", "count": 2},
            ],
        },
        "products": [
            {
                "rank": 1,
                "product_id": "p1",
                "product_name": "Raised Double Cat Bowl",
                "opportunity_score": 95,
                "decision": "main_push",
                "recommended_formats": ["photo", "video"],
                "recommended_hooks": ["pet_behavior", "problem_solution"],
                "next_action": "今天可主推，进入账号分发表",
                "dimension_scores": {"final_test_decision": {"decision": "main_push", "score": 92}},
            },
            {
                "rank": 2,
                "product_id": "p2",
                "product_name": "Portable Mini Handheld Fan",
                "opportunity_score": 70,
                "decision": "small_test",
                "recommended_formats": ["photo", "video"],
                "recommended_hooks": ["pain_point_hot_weather"],
                "next_action": "小样本测试",
                "dimension_scores": {"final_test_decision": {"decision": "small_test", "score": 70}},
            },
            {
                "rank": 3,
                "product_id": "p3",
                "product_name": "Foldable Home Walking Treadmill",
                "opportunity_score": 25,
                "decision": "reject",
                "recommended_formats": ["video"],
                "recommended_hooks": [],
                "next_action": "不建议当前阶段做",
                "dimension_scores": {"final_test_decision": {"decision": "reject", "score": 25}},
            },
        ],
    }


def main() -> None:
    payload = mock_payload()
    original = copy.deepcopy(payload)

    prompt = build_llm_summary_prompt(payload, market="de")
    if not prompt:
        raise AssertionError("llm prompt should not be empty")
    for text in ["不允许修改已有 score", "不允许虚构外部数据", "输出必须中文", "48小时后复盘指标"]:
        if text not in prompt:
            raise AssertionError(f"prompt missing guardrail: {text}")

    summary = build_rule_based_summary(payload, market="de")
    if not summary:
        raise AssertionError("rule based summary should not be empty")
    for text in ["main_push", "small_test", "reject", "Top 5 商品", "主要缺失证据"]:
        if text not in summary:
            raise AssertionError(f"summary missing {text}: {summary}")

    attached = attach_summary_to_payload(payload, market="de", use_llm=False)
    llm_summary = attached.get("llm_summary", {})
    if llm_summary.get("mode") != "rule_based":
        raise AssertionError(f"unexpected summary mode: {llm_summary}")
    if not llm_summary.get("summary_text") or not llm_summary.get("llm_prompt"):
        raise AssertionError(f"attached summary incomplete: {llm_summary}")

    if payload != original:
        raise AssertionError("attach_summary_to_payload must not mutate input payload")
    for index, product in enumerate(attached["products"]):
        if product["opportunity_score"] != original["products"][index]["opportunity_score"]:
            raise AssertionError("summary layer changed opportunity_score")
        if product["decision"] != original["products"][index]["decision"]:
            raise AssertionError("summary layer changed decision")

    fallback = attach_summary_to_payload({}, market="de")
    fallback_text = fallback.get("llm_summary", {}).get("summary_text", "")
    if "没有可分析商品" not in fallback_text:
        raise AssertionError(f"empty payload fallback should be readable: {fallback_text}")

    print("Product Intel LLM summary smoke test passed.")


if __name__ == "__main__":
    main()
