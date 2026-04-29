#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TikTok Insight V1.2 - Comment Evidence Driven Insight Report Generator

Purpose:
- Read AI enriched comment evidence packet
- Generate a full TikTok Insight V1.2 comment evidence driven report
- The report must be based on real comment evidence, not generic assumptions

Usage:
  source .env.local
  python3 generate_comment_insight_report.py ./reports/comment_evidence_enriched_xxx.json

Optional:
  python3 generate_comment_insight_report.py ./reports/comment_evidence_enriched_xxx.json --product "ALLPOWERS R600 Portable Power Station" --market "DE"

Output:
  reports/comment_insight_report_<stem>.md
"""

import json
import os
import sys
import re
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: openai package not installed. Try: pip3 install openai")
    sys.exit(1)


BASE_DIR = Path(__file__).resolve().parent
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


SYSTEM_PROMPT = """你是 TikTok Shop 评论区需求洞察与内容复刻顾问。

你的任务是基于“评论证据包”生成 TikTok Insight V1.2 评论证据洞察报告。

核心原则：
1. 必须先尊重评论事实，再做 AI 洞察。
2. 所有用户需求、人群、场景、购买阻力判断，都必须能对应到评论证据。
3. 不允许脱离评论事实泛泛总结。
4. 如果评论数量少，要明确说明样本有限，不能过度推断。
5. 如果评论里没有出现某个需求，不要凭空补。
6. 涉及价格、功率、容量、材质、尺寸、续航、功效、质保、库存、物流等未确认信息，必须标注“需商品团队确认”。
7. 输出要给图文团队和视频团队直接执行，不要写空泛理论。

报告必须用中文。
"""


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_arg(args: List[str], key: str, default: str = "") -> str:
    if key in args:
        i = args.index(key)
        if i + 1 < len(args):
            return args[i + 1]
    return default


def md_escape(text: Any) -> str:
    return str(text or "").replace("\n", " ").replace("|", "｜").strip()


def build_evidence_text(packet: Dict[str, Any]) -> str:
    summary = packet.get("comment_summary", {})
    top = packet.get("top_liked_comments", [])
    all_liked = packet.get("all_liked_comments", [])
    ai_counts = packet.get("ai_type_counts", {})

    lines = []
    lines.append("# 评论证据包摘要")
    lines.append("")
    lines.append("## 评论数据概览")
    lines.append(f"- 评论总数：{summary.get('total_comments', 0)}")
    lines.append(f"- 有点赞评论数：{summary.get('liked_comments', 0)}")
    lines.append(f"- 最高点赞数：{summary.get('top_comment_like_count', 0)}")
    lines.append(f"- 可用于下一条素材的评论数：{summary.get('useful_comment_count', packet.get('useful_comment_count', 0))}")
    lines.append(f"- 是否适合评论区需求洞察：{summary.get('effective_for_insight', False)}")
    lines.append("")

    lines.append("## AI 评论类型统计")
    if ai_counts:
        for k, v in sorted(ai_counts.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- {k}：{v}")
    else:
        lines.append("- 暂无")
    lines.append("")

    lines.append("## 高赞评论证据 Top 30")
    lines.append("| 排名 | 点赞数 | 回复数 | 原评论 | 中文翻译 | AI评论类型 | 暴露需求/疑虑 | 复刻价值 | 下一条素材打法 |")
    lines.append("|---|---:|---:|---|---|---|---|---|---|")

    for i, c in enumerate(top, 1):
        lines.append(
            f"| {i} | {c.get('digg_count', 0)} | {c.get('reply_count', 0)} | "
            f"{md_escape(c.get('text'))} | {md_escape(c.get('translated_zh'))} | "
            f"{md_escape(c.get('ai_comment_type'))} | "
            f"{md_escape(c.get('ai_exposed_need_or_objection'))} | "
            f"{md_escape(c.get('ai_replication_value'))} | "
            f"{md_escape(c.get('recommended_content_angle'))} |"
        )

    lines.append("")
    lines.append("## 所有有点赞评论")
    lines.append("| 排名 | 点赞数 | 原评论 | 中文翻译 | AI评论类型 | 暴露需求/疑虑 | 是否值得用于下一条素材 |")
    lines.append("|---|---:|---|---|---|---|---|")

    for i, c in enumerate(all_liked, 1):
        worth = "是" if c.get("worth_using_for_next_content") else "否"
        lines.append(
            f"| {i} | {c.get('digg_count', 0)} | {md_escape(c.get('text'))} | "
            f"{md_escape(c.get('translated_zh'))} | "
            f"{md_escape(c.get('ai_comment_type'))} | "
            f"{md_escape(c.get('ai_exposed_need_or_objection'))} | {worth} |"
        )

    return "\n".join(lines)


def build_user_prompt(packet: Dict[str, Any], market: str, product: str) -> str:
    evidence_text = build_evidence_text(packet)
    summary = packet.get("comment_summary", {})

    return f"""请基于下面的 TikTok 评论证据包，生成一份完整的《TikTok Insight V1.2 评论证据洞察报告》。

市场：{market or "未提供"}
商品：{product or "未提供"}
评论样本情况：
- 评论总数：{summary.get('total_comments', 0)}
- 有点赞评论数：{summary.get('liked_comments', 0)}
- 最高点赞数：{summary.get('top_comment_like_count', 0)}

重要要求：
- 你必须基于评论证据包输出，不允许凭空总结。
- 每个“真实用户需求”后面必须写对应的评论证据。
- 每个“购买阻力”后面必须写对应的评论证据。
- 如果评论样本较少，必须明确说明“样本有限，适合作为方向信号，不适合直接代表全部用户”。
- 结论必须能指导图文团队和视频团队下一条怎么做。
- 不要复述太多原评论表格，但要引用关键评论证据。
- 涉及商品参数、功率、容量、续航、瓦数、是否能带动某设备等信息，必须标注“需商品团队确认”。

报告格式必须严格按下面结构输出：

# TikTok Insight V1.2 评论证据洞察报告

## 1. 一句话结论
用 2-4 句话说明：评论区暴露出的最大机会是什么，是否值得继续做，适合图文还是视频。

## 2. 评论数据概览
用 bullet 输出评论总数、有点赞评论数、最高点赞数、评论样本是否充足、主要评论类型。

## 3. 高赞评论核心发现
列出 3-5 个发现。每个发现必须包含：
- 发现
- 评论证据
- 对内容生产的意义

## 4. 真实用户需求 Top 5
用表格输出：
| 排名 | 真实需求 | 评论证据 | 内容机会 |
如果不足 5 个，就只输出真实存在的数量，不要硬凑。

## 5. 购买阻力与质疑点
用表格输出：
| 阻力/质疑 | 评论证据 | 下一条内容怎么化解 | 需商品团队确认 |
必须具体到内容怎么拍/怎么表达。

## 6. 人群与使用场景
只输出评论证据里出现或强相关的人群/场景。
不要凭空扩展没有证据的人群。

## 7. 素材接受度判断
判断这条素材评论区属于以下哪一种：
- 高意向购买型
- 真实种草型
- 参数咨询型
- 争议讨论型
- 纯热闹互动型
- 低转化围观型
并说明判断依据。

## 8. 下一条图文复刻方向
给 2 套图文结构。
每套 3 图，每图包含：
- 画面
- 图上文字
- 作用
- 需确认信息

## 9. 下一条视频复刻方向
给 2 套视频结构。
每套按：
- 0-3秒
- 3-8秒
- 8-15秒
- 15秒后
- CTA
输出。

## 10. 评论回复/评论区运营建议
给 5 条可直接复制的评论回复话术。
必须围绕评论区真实疑虑。

## 11. 商品团队需确认信息
列出这条素材继续放大前，商品团队必须确认的参数、价格、库存、物流、质保、适用边界等。

下面是评论证据包：

{evidence_text}
"""


def call_openai_report(packet: Dict[str, Any], market: str, product: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL", "gpt-5.5")
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip()

    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY. Run: source .env.local")

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = OpenAI(**client_kwargs)

    user_prompt = build_user_prompt(packet, market, product)

    print(f"Using model: {model}")
    print(f"Base URL: {base_url or 'OpenAI default'}")

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_completion_tokens=24000,
    )

    content = resp.choices[0].message.content or ""
    return content.strip()


def main():
    if len(sys.argv) < 2:
        print("Usage: source .env.local && python3 generate_comment_insight_report.py ./reports/comment_evidence_enriched_xxx.json [--product PRODUCT] [--market MARKET]")
        sys.exit(1)

    args = sys.argv[1:]
    source_file = Path(args[0]).expanduser().resolve()
    product = extract_arg(args, "--product", "")
    market = extract_arg(args, "--market", "")

    if not source_file.exists():
        print(f"ERROR: file not found: {source_file}")
        sys.exit(1)

    packet = load_json(source_file)

    report = call_openai_report(packet, market=market, product=product)

    stem = source_file.stem.replace("comment_evidence_enriched_", "")
    out_md = REPORTS_DIR / f"comment_insight_report_{stem}.md"

    header = f"""<!--
Generated by TikTok Insight V1.2 comment evidence driven report generator
Generated at: {datetime.utcnow().isoformat()}Z
Source packet: {source_file}
Market: {market}
Product: {product}
-->

"""

    out_md.write_text(header + report + "\n", encoding="utf-8")

    print("✅ V1.2 comment insight report generated")
    print(f"source: {source_file}")
    print(f"report: {out_md}")


if __name__ == "__main__":
    main()
