#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TikTok Insight V1.2 - Comment Evidence Packet Builder

Purpose:
- Read Apify TikTok comments JSON from raw/*_comments.json
- Sort comments by diggCount
- Extract high-liked comments and all liked comments
- Generate a markdown evidence packet for GPT V1.2 comment-driven insight mode

Usage:
  python3 comment_evidence_packet.py ./raw/xxx_comments.json

Output:
  reports/comment_evidence_<stem>.md
  reports/comment_evidence_<stem>.json
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List


BASE_DIR = Path(__file__).resolve().parent
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


COMMENT_TYPE_RULES = [
    ("购买意向/购买方式", ["buy", "where", "link", "shop", "order", "purchase", "price", "多少钱", "哪里买", "链接"]),
    ("效果质疑", ["work", "really", "does it", "proof", "before", "after", "真的", "有效", "有用", "对比"]),
    ("适用场景提问", ["use", "for", "with", "on", "carpet", "sofa", "dog", "cat", "kids", "pet", "适合", "能不能", "可以用"]),
    ("价格/性价比质疑", ["expensive", "cheap", "worth", "cost", "price", "太贵", "值不值"]),
    ("参数/规格问题", ["size", "battery", "long", "charge", "watt", "capacity", "尺寸", "电池", "续航", "容量"]),
    ("负面反馈/不信任", ["fake", "scam", "ad", "lie", "垃圾", "骗人", "广告", "假的"]),
    ("人群共鸣/场景共鸣", ["need this", "i need", "my dog", "my kid", "my home", "我需要", "我家", "孩子", "宠物"]),
]


def load_comments(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(data, list):
        comments = data
    elif isinstance(data, dict):
        comments = None
        for key in ["comments", "data", "items", "results"]:
            if isinstance(data.get(key), list):
                comments = data[key]
                break
        if comments is None:
            raise ValueError(f"Cannot find comment list in dict keys: {list(data.keys())}")
    else:
        raise ValueError(f"Unsupported JSON root type: {type(data)}")

    return [c for c in comments if isinstance(c, dict)]


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def get_text(c: Dict[str, Any]) -> str:
    return str(c.get("text") or c.get("comment") or c.get("commentText") or "").strip()


def classify_comment(text: str) -> str:
    low = text.lower()
    matched = []

    for label, keywords in COMMENT_TYPE_RULES:
        if any(k.lower() in low for k in keywords):
            matched.append(label)

    if matched:
        return " / ".join(matched[:2])

    if "?" in text or "？" in text:
        return "问题/疑问"

    if len(text.strip()) <= 6:
        return "短互动/弱信息"

    return "普通反馈/待人工判断"


def infer_exposed_need(text: str, comment_type: str) -> str:
    low = text.lower()

    if "购买意向" in comment_type:
        return "用户在寻找购买入口、价格或下单方式"
    if "效果质疑" in comment_type:
        return "用户需要看到更真实的效果证明和前后对比"
    if "适用场景" in comment_type:
        return "用户在确认产品能否适配自己的具体使用场景"
    if "价格" in comment_type:
        return "用户对价格和性价比存在犹豫，需要解释为什么值得买"
    if "参数" in comment_type:
        return "用户需要明确规格、续航、尺寸、容量等商品信息"
    if "负面" in comment_type:
        return "用户对素材真实性或产品可信度有疑虑"
    if "人群共鸣" in comment_type:
        return "评论暴露出具体人群或家庭场景，可转化为下一条内容角度"

    if "whirlpool" in low:
        return "用户在探索产品是否能支持更高功率/特殊设备场景"
    if "dog" in low or "cat" in low or "pet" in low:
        return "宠物家庭场景可能是强需求点"
    if "kid" in low or "baby" in low or "children" in low:
        return "小孩家庭场景可能是强需求点"

    return "需要结合上下文进一步判断"


def replication_value(text: str, like_count: int, comment_type: str) -> str:
    if like_count >= 50:
        return "高：高赞评论，值得优先转成素材角度"
    if like_count >= 10:
        return "中高：有明显共鸣，可作为辅助角度"
    if like_count > 0 and any(k in comment_type for k in ["购买", "效果", "适用场景", "价格", "参数", "人群"]):
        return "中：有具体需求，可进入候选素材角度"
    if like_count > 0:
        return "低到中：有互动，但需人工判断是否有转化价值"
    return "低：无点赞，不作为 V1.2 重点证据"


def normalize_comment(c: Dict[str, Any]) -> Dict[str, Any]:
    text = get_text(c)
    like_count = safe_int(c.get("diggCount") or c.get("likeCount") or c.get("like_count"))
    reply_count = safe_int(c.get("replyCommentTotal") or c.get("replyCount") or c.get("reply_count"))
    comment_type = classify_comment(text)

    return {
        "cid": c.get("cid") or "",
        "unique_id": c.get("uniqueId") or "",
        "text": text,
        "digg_count": like_count,
        "reply_count": reply_count,
        "create_time_iso": c.get("createTimeISO") or "",
        "video_url": c.get("videoWebUrl") or c.get("submittedVideoUrl") or c.get("input") or "",
        "liked_by_author": bool(c.get("likedByAuthor", False)),
        "pinned_by_author": bool(c.get("pinnedByAuthor", False)),
        "comment_type": comment_type,
        "exposed_need": infer_exposed_need(text, comment_type),
        "replication_value": replication_value(text, like_count, comment_type),
    }


def build_packet(comments: List[Dict[str, Any]], source_file: Path) -> Dict[str, Any]:
    normalized = [normalize_comment(c) for c in comments if get_text(c)]
    normalized.sort(key=lambda x: (x["digg_count"], x["reply_count"]), reverse=True)

    liked_comments = [c for c in normalized if c["digg_count"] > 0]
    top_liked_comments = liked_comments[:30]

    type_counts: Dict[str, int] = {}
    for c in liked_comments:
        key = c["comment_type"]
        type_counts[key] = type_counts.get(key, 0) + 1

    max_like = max([c["digg_count"] for c in normalized], default=0)

    effective_for_insight = len(liked_comments) >= 5 or max_like >= 10

    return {
        "packet_version": "TikTok Insight V1.2 comment_evidence_packet_v0.1",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source_file": str(source_file),
        "comment_summary": {
            "total_comments": len(normalized),
            "liked_comments": len(liked_comments),
            "top_comment_like_count": max_like,
            "effective_for_insight": effective_for_insight,
            "note": "If effective_for_insight is false, use V1.1 material replication analysis instead of deep comment demand insight.",
        },
        "type_counts": type_counts,
        "top_liked_comments": top_liked_comments,
        "all_liked_comments": liked_comments,
    }


def md_escape(text: str) -> str:
    return str(text).replace("\n", " ").replace("|", "｜").strip()


def render_markdown(packet: Dict[str, Any]) -> str:
    summary = packet["comment_summary"]
    top = packet["top_liked_comments"]
    all_liked = packet["all_liked_comments"]

    lines = []
    lines.append("# TikTok Insight V1.2 评论证据包")
    lines.append("")
    lines.append("## 1. 评论数据概览")
    lines.append("")
    lines.append(f"- 来源文件：`{packet['source_file']}`")
    lines.append(f"- 评论总数：{summary['total_comments']}")
    lines.append(f"- 有点赞评论数：{summary['liked_comments']}")
    lines.append(f"- 最高点赞数：{summary['top_comment_like_count']}")
    lines.append(f"- 是否适合评论区需求洞察：{'是' if summary['effective_for_insight'] else '否'}")
    lines.append("")
    lines.append("## 2. 评论类型统计")
    lines.append("")
    if packet["type_counts"]:
        for k, v in sorted(packet["type_counts"].items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- {k}：{v}")
    else:
        lines.append("- 暂无有点赞评论可统计")
    lines.append("")
    lines.append("## 3. 高赞评论证据表 Top 30")
    lines.append("")
    lines.append("| 排名 | 点赞数 | 回复数 | 用户 | 原评论 | 评论类型 | 暴露需求/疑虑 | 复刻价值 |")
    lines.append("|---|---:|---:|---|---|---|---|---|")

    for i, c in enumerate(top, 1):
        lines.append(
            f"| {i} | {c['digg_count']} | {c['reply_count']} | "
            f"{md_escape(c['unique_id'])} | {md_escape(c['text'])} | "
            f"{md_escape(c['comment_type'])} | {md_escape(c['exposed_need'])} | {md_escape(c['replication_value'])} |"
        )

    lines.append("")
    lines.append("## 4. 所有有点赞评论汇总")
    lines.append("")
    lines.append("> 注：这里保留所有 diggCount > 0 的评论，用于避免 AI 只看摘要造成关键信息遗漏。")
    lines.append("")
    lines.append("| 排名 | 点赞数 | 回复数 | 原评论 | 评论类型 | 暴露需求/疑虑 |")
    lines.append("|---|---:|---:|---|---|---|")

    for i, c in enumerate(all_liked, 1):
        lines.append(
            f"| {i} | {c['digg_count']} | {c['reply_count']} | "
            f"{md_escape(c['text'])} | {md_escape(c['comment_type'])} | {md_escape(c['exposed_need'])} |"
        )

    lines.append("")
    lines.append("## 5. 给 GPT V1.2 的使用说明")
    lines.append("")
    lines.append("后续 AI 需求洞察必须基于上面的评论证据，不允许脱离评论事实凭空总结。")
    lines.append("如果评论证据不足，应明确说明评论数据不足，不建议做深度需求判断。")
    lines.append("")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 comment_evidence_packet.py ./raw/xxx_comments.json")
        sys.exit(1)

    source_file = Path(sys.argv[1]).expanduser().resolve()
    if not source_file.exists():
        print(f"ERROR: file not found: {source_file}")
        sys.exit(1)

    comments = load_comments(source_file)
    packet = build_packet(comments, source_file)

    stem = source_file.stem.replace("_comments", "")
    out_json = REPORTS_DIR / f"comment_evidence_{stem}.json"
    out_md = REPORTS_DIR / f"comment_evidence_{stem}.md"

    out_json.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    out_md.write_text(render_markdown(packet), encoding="utf-8")

    summary = packet["comment_summary"]
    print("✅ comment evidence packet generated")
    print(f"source: {source_file}")
    print(f"comments: {summary['total_comments']}")
    print(f"liked_comments: {summary['liked_comments']}")
    print(f"top_like_count: {summary['top_comment_like_count']}")
    print(f"effective_for_insight: {summary['effective_for_insight']}")
    print(f"json: {out_json}")
    print(f"md: {out_md}")


if __name__ == "__main__":
    main()
