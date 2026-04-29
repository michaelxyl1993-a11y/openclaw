#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent
REPORTS_DIR = BASE_DIR / "reports"
RAW_DIR = BASE_DIR / "raw"


def run_cmd(cmd):
    print("RUN:", " ".join(str(x) for x in cmd))
    p = subprocess.run(
        [str(x) for x in cmd],
        cwd=str(BASE_DIR),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(p.stdout)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(str(x) for x in cmd)}")
    return p.stdout


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", required=True)
    parser.add_argument("--market", default="")
    parser.add_argument("--product", default="")
    parser.add_argument("--report-id", default="")
    args = parser.parse_args()

    key = args.key
    report_id = args.report_id or datetime.now().strftime("R%m%d-%H%M-%S")

    comments_path = RAW_DIR / f"{key}_comments.json"
    if not comments_path.exists():
        raise FileNotFoundError(f"comments file not found: {comments_path}")

    evidence_json = REPORTS_DIR / f"comment_evidence_{key}.json"
    enriched_json = REPORTS_DIR / f"comment_evidence_enriched_{key}.json"
    report_md = REPORTS_DIR / f"comment_insight_report_{key}.md"
    short_txt = REPORTS_DIR / f"feishu_short_v12_{key}.txt"

    run_cmd([sys.executable, "comment_evidence_packet.py", str(comments_path)])
    run_cmd([sys.executable, "comment_evidence_ai_enrich.py", str(evidence_json)])
    run_cmd([
        sys.executable,
        "generate_comment_insight_report.py",
        str(enriched_json),
        "--market",
        args.market,
        "--product",
        args.product,
    ])
    run_cmd([sys.executable, "make_v12_feishu_short_reply.py", str(report_md), report_id])

    result = {
        "status": "success",
        "report_version": "v1.2_comment",
        "key": key,
        "report_id": report_id,
        "comments_path": str(comments_path),
        "evidence_json": str(evidence_json),
        "enriched_json": str(enriched_json),
        "report_path": str(report_md),
        "short_reply_path": str(short_txt),
        "reply_text": read_text(short_txt) if short_txt.exists() else "",
    }

    out = REPORTS_DIR / f"v12_comment_chain_result_{key}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("✅ V1.2 comment chain finished")
    print(f"result: {out}")
    print(f"report: {report_md}")
    print(f"short: {short_txt}")


if __name__ == "__main__":
    main()
