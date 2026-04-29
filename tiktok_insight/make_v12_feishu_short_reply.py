#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TikTok Insight V1.2 - Feishu Short Reply Formatter

Purpose:
- Read full V1.2 comment insight report markdown
- Produce a concise Feishu-ready short reply

Usage:
  python3 make_v12_feishu_short_reply.py ./reports/comment_insight_report_xxx.md R0429-1542-0001

Output:
  reports/feishu_short_v12_xxx.txt
"""

import re
import sys
from pathlib import Path
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


def section(text: str, title: str) -> str:
    pattern = rf"##\s+{re.escape(title)}\s*\n(.*?)(?=\n##\s+|\Z)"
    m = re.search(pattern, text, flags=re.S)
    return m.group(1).strip() if m else ""


def strip_md(s: str) -> str:
    s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"\*\*(.*?)\*\*", r"\1", s)
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"^\s*---+\s*$", "", s, flags=re.M)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def take_lines(s: str, max_lines: int = 8) -> str:
    lines = [x.rstrip() for x in strip_md(s).splitlines() if x.strip()]
    return "\n".join(lines[:max_lines]).strip()


def extract_table_rows(s: str, max_rows: int = 5) -> list:
    rows = []
    for line in s.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        if "---" in line:
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 2:
            continue
        if any(h in cols[0] for h in ["排名", "阻力/质疑"]):
            continue
        rows.append(cols)
    return rows[:max_rows]


def format_top_needs(s: str) -> str:
    rows = extract_table_rows(s, 5)
    if not rows:
        return take_lines(s, 10)

    out = []
    for r in rows:
        # expected: 排名 | 真实需求 | 评论证据 | 内容机会
        if len(r) >= 4:
            out.append(f"{r[0]}. {r[1]}\n证据：{r[2]}\n机会：{r[3]}")
    return "\n\n".join(out)


def format_objections(s: str) -> str:
    rows = extract_table_rows(s, 5)
    if not rows:
        return take_lines(s, 10)

    out = []
    for i, r in enumerate(rows, 1):
        # expected: 阻力/质疑 | 评论证据 | 下一条内容怎么化解 | 需商品团队确认
        if len(r) >= 4:
            out.append(f"{i}. {r[0]}\n证据：{r[1]}\n化解：{r[2]}")
    return "\n\n".join(out)

def format_next_actions(graphic_s: str, video_s: str) -> str:
    out = []

    # Keep short: extract headings and first useful text
    graphic_titles = re.findall(r"###\s+(图文方向\s*\d+[:：]?.*)", graphic_s)
    video_titles = re.findall(r"###\s+(视频方向\s*\d+[:：]?.*)", video_s)

    if graphic_titles:
        out.append("图文：")
        for t in graphic_titles[:2]:
            out.append(f"- {strip_md(t)}")

    if video_titles:
        out.append("视频：")
        for t in video_titles[:2]:
            out.append(f"- {strip_md(t)}")

    if not out:
        combined = (graphic_s + "\n" + video_s).strip()
        return take_lines(combined, 12)

    return "\n".join(out)

def extract_high_comment_findings(s: str, max_items: int = 3) -> str:
    clean = strip_md(s)

    # 兼容多种格式：
    # ### 发现 1：xxx
    # 发现 1：xxx
    # **发现 1：xxx**
    pattern = r"(?:^|\n)(?:#{1,4}\s*)?(发现\s*\d+[：:].*?)(?=\n(?:#{1,4}\s*)?发现\s*\d+[：:]|\n##\s+|\Z)"
    matches = re.findall(pattern, clean, flags=re.S)

    items = []
    for m in matches:
        lines = [x.strip("- ").strip() for x in m.splitlines() if x.strip()]
        if not lines:
            continue

        # 每个发现最多保留 4 行，避免飞书短版太长
        items.append("\n".join(lines[:4]))

    if items:
        return "\n\n".join(items[:max_items])

    # fallback：如果没匹配到“发现 x”，就取前几行
    return take_lines(clean, 12)

def make_short_reply(report_text: str, report_id: str) -> str:
    one = section(report_text, "1. 一句话结论")
    data = section(report_text, "2. 评论数据概览")
    findings = section(report_text, "3. 高赞评论核心发现")
    needs = section(report_text, "4. 真实用户需求 Top 5")
    objections = section(report_text, "5. 购买阻力与质疑点")
    graphic = section(report_text, "8. 下一条图文复刻方向")
    video = section(report_text, "9. 下一条视频复刻方向")

    parts = []
    parts.append("✅ TikTok Insight V1.2 评论证据洞察报告")
    parts.append(f"本次报告 ID：{report_id}")
    parts.append("")
    parts.append("【1. 一句话结论】")
    parts.append(take_lines(one, 6) or "未提取到结论")
    parts.append("")
    parts.append("【2. 评论数据概览】")
    parts.append(take_lines(data, 8) or "未提取到数据概览")
    parts.append("")
    parts.append("【3. 高赞评论核心发现】")
    parts.append(extract_high_comment_findings(findings, 3) or "未提取到高赞评论发现")
    parts.append("")
    parts.append("【4. 真实需求 Top 5】")
    parts.append(format_top_needs(needs) or "未提取到真实需求")
    parts.append("")
    parts.append("【5. 购买阻力 Top 5】")
    parts.append(format_objections(objections) or "未提取到购买阻力")
    parts.append("")
    parts.append("【6. 下一条怎么做】")
    parts.append(format_next_actions(graphic, video) or "未提取到下一条执行方向")
    parts.append("")
    parts.append("📄 完整评论证据表和深度报告已保存到本地 reports 目录。")
    parts.append("提醒：涉及功率、容量、瓦数、续航、价格、库存、物流、质保等信息，仍需商品团队确认。")

    return "\n".join(parts).strip() + "\n"


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 make_v12_feishu_short_reply.py ./reports/comment_insight_report_xxx.md [REPORT_ID]")
        sys.exit(1)

    report_path = Path(sys.argv[1]).expanduser().resolve()
    if not report_path.exists():
        print(f"ERROR: file not found: {report_path}")
        sys.exit(1)

    report_id = sys.argv[2] if len(sys.argv) >= 3 else datetime.now().strftime("R%m%d-%H%M-%S")

    text = report_path.read_text(encoding="utf-8")
    short = make_short_reply(text, report_id)

    stem = report_path.stem.replace("comment_insight_report_", "")
    out_path = REPORTS_DIR / f"feishu_short_v12_{stem}.txt"
    out_path.write_text(short, encoding="utf-8")

    print("✅ V1.2 Feishu short reply generated")
    print(f"report_id: {report_id}")
    print(f"source: {report_path}")
    print(f"short_reply: {out_path}")
    print("")
    print(short)


if __name__ == "__main__":
    main()
