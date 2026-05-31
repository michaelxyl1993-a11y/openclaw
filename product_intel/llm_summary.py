"""LLM prompt and rule-based summary layer for Product Intel."""

from __future__ import annotations

import copy
import json
from typing import Any


def safe_products(manager_payload: dict[str, Any]) -> list[dict[str, Any]]:
    products = manager_payload.get("products", [])
    return products if isinstance(products, list) else []


def safe_summary(manager_payload: dict[str, Any]) -> dict[str, Any]:
    summary = manager_payload.get("summary", {})
    return summary if isinstance(summary, dict) else {}


def safe_meta(manager_payload: dict[str, Any]) -> dict[str, Any]:
    meta = manager_payload.get("meta", {})
    return meta if isinstance(meta, dict) else {}


def product_line(product: dict[str, Any]) -> str:
    formats = product.get("recommended_formats", [])
    if isinstance(formats, list):
        format_text = ",".join(str(item) for item in formats)
    else:
        format_text = str(formats)
    hooks = product.get("recommended_hooks", [])
    if isinstance(hooks, list):
        hook_text = ", ".join(str(item) for item in hooks[:5])
    else:
        hook_text = str(hooks)
    return (
        f"{product.get('rank', '-')}. {product.get('opportunity_score', 0)} / "
        f"{product.get('decision', '')} / {product.get('product_name', '')} / "
        f"形式:{format_text or '-'} / hooks:{hook_text or '-'}"
    )


def build_llm_summary_prompt(manager_payload: dict[str, Any], market: str = "de") -> str:
    products = safe_products(manager_payload)
    compact_payload = {
        "meta": safe_meta(manager_payload),
        "summary": safe_summary(manager_payload),
        "products": [
            {
                "rank": product.get("rank"),
                "product_id": product.get("product_id"),
                "product_name": product.get("product_name"),
                "category": product.get("category"),
                "opportunity_score": product.get("opportunity_score"),
                "decision": product.get("decision"),
                "recommended_formats": product.get("recommended_formats"),
                "recommended_hooks": product.get("recommended_hooks"),
                "content_angle_summary": product.get("content_angle_summary"),
                "risk_flags": product.get("risk_flags"),
                "dimension_scores": product.get("dimension_scores"),
                "missing_evidence_count": product.get("missing_evidence_count"),
                "next_action": product.get("next_action"),
            }
            for product in products
        ],
    }
    payload_text = json.dumps(compact_payload, ensure_ascii=False, indent=2)
    return f"""你是 OpenClaw 商品运营分析助手。请基于下面 Product Intel v1.2 的结构化结果，输出适合运营团队直接阅读的中文选品建议。

硬性规则：
- 只做解释和归纳，不允许修改已有 score、decision、dimension_scores。
- 不允许虚构外部数据，不允许假装已经查过 Google Trends、TikTok、Instagram、YouTube Shorts 或 Reels。
- 如果缺数据，必须写“缺失证据”，不能编造。
- 输出必须中文。
- 输出必须适合发给运营团队，清晰、短句、可执行。
- 市场：{market}

请输出以下 9 个部分：
1）本批次整体结论
2）今天优先主推商品
3）建议小测商品
4）暂缓 / 放弃商品
5）每个 main_push 商品的核心理由
6）每个商品适合图文还是视频
7）适合的内容角度 / hook 方向
8）主要缺失证据
9）48小时后复盘指标

Product Intel 结构化结果：
{payload_text}
"""


def build_rule_based_summary(manager_payload: dict[str, Any], market: str = "de") -> str:
    meta = safe_meta(manager_payload)
    summary = safe_summary(manager_payload)
    products = safe_products(manager_payload)
    if not products:
        return (
            "运营摘要：本批次没有可分析商品。\n"
            f"市场：{market}\n"
            "请检查输入表是否包含商品名称、类目、价格、销量等基础字段。"
        )

    counts = {
        "main_push": int(meta.get("main_push_count", 0) or 0),
        "small_test": int(meta.get("small_test_count", 0) or 0),
        "hold": int(meta.get("hold_count", 0) or 0),
        "reject": int(meta.get("reject_count", 0) or 0),
    }
    main_push_products = [product for product in products if product.get("decision") == "main_push"]
    small_test_products = [product for product in products if product.get("decision") == "small_test"]
    hold_or_reject = [product for product in products if product.get("decision") in {"hold", "reject"}]
    missing = summary.get("common_missing_evidence", [])
    missing_lines = []
    if isinstance(missing, list):
        for item in missing[:5]:
            if isinstance(item, dict):
                missing_lines.append(f"- {item.get('evidence', '')}（{item.get('count', 0)}）")
            else:
                missing_lines.append(f"- {item}")
    if not missing_lines:
        missing_lines.append("- 暂无集中缺失证据。")

    reason_lines = []
    reasons = summary.get("main_push_reasons_summary", [])
    if isinstance(reasons, list):
        reason_lines.extend(f"- {reason}" for reason in reasons[:5])
    if not reason_lines:
        reason_lines.append("- 主推理由不足，请优先补充增长、佣金、评论与竞品证据。")

    lines = [
        "运营摘要：",
        f"市场：{market}",
        f"本批次输入商品数：{meta.get('total_products', len(products))}",
        f"决策分布：main_push {counts['main_push']} / small_test {counts['small_test']} / hold {counts['hold']} / reject {counts['reject']}",
        "",
        "Top 5 商品：",
    ]
    for product in products[:5]:
        lines.append(f"- {product_line(product)}")

    lines.extend(["", "今天优先主推商品："])
    if main_push_products:
        for product in main_push_products[:5]:
            lines.append(f"- {product.get('product_name', '')}：{product.get('next_action', '')}")
    else:
        lines.append("- 暂无明确主推商品，建议先从 small_test 商品做小样本验证。")

    lines.extend(["", "建议小测商品："])
    if small_test_products:
        for product in small_test_products[:5]:
            lines.append(f"- {product.get('product_name', '')}：先发1-2条，观察CTR/CVR/评论阻力。")
    else:
        lines.append("- 暂无 small_test 商品。")

    lines.extend(["", "暂缓 / 放弃商品："])
    if hold_or_reject:
        for product in hold_or_reject[:5]:
            lines.append(f"- {product.get('product_name', '')}：{product.get('decision', '')}，补证据或不进今日生产池。")
    else:
        lines.append("- 暂无暂缓或放弃商品。")

    lines.extend(["", "主推理由摘要：", *reason_lines])
    lines.extend(["", "主要缺失证据：", *missing_lines])
    lines.extend(
        [
            "",
            "下一步动作：",
            "- main_push 商品进入今日账号分发表，优先生成图文素材。",
            "- small_test 商品先做1-2条，48小时后看 CTR、CVR、加购率、评论异议和质量投诉。",
            "- hold/reject 商品不要占用今日主推产能，先补齐缺失证据。",
        ]
    )
    return "\n".join(lines)


def attach_summary_to_payload(
    manager_payload: dict[str, Any],
    market: str = "de",
    use_llm: bool = False,
) -> dict[str, Any]:
    payload = copy.deepcopy(manager_payload)
    prompt = build_llm_summary_prompt(payload, market=market)
    summary_text = build_rule_based_summary(payload, market=market)
    payload["llm_summary"] = {
        "mode": "rule_based" if not use_llm else "prompt_only",
        "summary_text": summary_text,
        "llm_prompt": prompt,
    }
    return payload
