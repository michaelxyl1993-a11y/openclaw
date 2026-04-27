import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent

STEPS = [
    {
        "name": "抓取评论",
        "script": "test_comments.py",
        "required": True
    },
    {
        "name": "抓取 metadata",
        "script": "test_metadata.py",
        "required": True
    },
    {
        "name": "生成 data packet",
        "script": "build_data_packet.py",
        "required": True
    },
    {
        "name": "下载字幕",
        "script": "download_subtitles.py",
        "required": False
    },
    {
        "name": "合并字幕到 data packet",
        "script": "attach_subtitles_to_packet.py",
        "required": False
    },
    {
        "name": "抓取视频下载信息",
        "script": "test_downloader.py",
        "required": False
    },
    {
        "name": "下载视频文件",
        "script": "download_media.py",
        "required": False
    },
    {
        "name": "抽取视频关键帧",
        "script": "extract_frames.py",
        "required": False
    },
    {
        "name": "生成 contact sheet",
        "script": "make_visual_packet.py",
        "required": False
    },
    {
        "name": "生成分析 prompt",
        "script": "make_analysis_prompt.py",
        "required": True
    },
    {
        "name": "生成 QWEN 报告",
        "script": "generate_report_qwen.py",
        "required": True
    },
]

def run_step(step):
    script_path = BASE_DIR / step["script"]

    if not script_path.exists():
        message = f"Missing script: {script_path}"
        if step["required"]:
            raise FileNotFoundError(message)
        print(f"⚠️  跳过可选步骤：{step['name']}，原因：{message}")
        return {
            "name": step["name"],
            "script": step["script"],
            "status": "skipped",
            "reason": message
        }

    print("\n" + "=" * 80)
    print(f"▶️  {step['name']}：{step['script']}")
    print("=" * 80)

    completed = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(BASE_DIR),
        text=True,
        capture_output=True
    )

    print(completed.stdout)

    if completed.returncode != 0:
        print(completed.stderr)

        if step["required"]:
            raise RuntimeError(f"Step failed: {step['name']} ({step['script']})")

        print(f"⚠️  可选步骤失败，继续后续流程：{step['name']}")
        return {
            "name": step["name"],
            "script": step["script"],
            "status": "failed_optional",
            "stderr": completed.stderr[-2000:]
        }

    return {
        "name": step["name"],
        "script": step["script"],
        "status": "success"
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="input_test.json", help="Input JSON file path")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip comments/metadata/downloader fetching, reuse existing raw files")
    parser.add_argument("--no-report", action="store_true", help="Build packet/prompt only, do not generate QWEN report")
    args = parser.parse_args()

    input_src = Path(args.input).expanduser()
    if not input_src.is_absolute():
        input_src = BASE_DIR / input_src

    if not input_src.exists():
        raise FileNotFoundError(f"Input file not found: {input_src}")

    input_dst = BASE_DIR / "input_test.json"

    if input_src.resolve() != input_dst.resolve():
        shutil.copyfile(input_src, input_dst)
        print(f"Copied input file to {input_dst}")

    if not os.environ.get("APIFY_TOKEN") and not args.skip_fetch:
        raise RuntimeError("Missing APIFY_TOKEN. Please export APIFY_TOKEN before running full fetch.")

    if not os.environ.get("QWEN_API_KEY") and not args.no_report:
        raise RuntimeError("Missing QWEN_API_KEY. Please export QWEN_API_KEY before generating report.")

    if not os.environ.get("QWEN_BASE_URL") and not args.no_report:
        raise RuntimeError("Missing QWEN_BASE_URL. Please export QWEN_BASE_URL before generating report.")

    selected_steps = STEPS

    if args.skip_fetch:
        skip_scripts = {
            "test_comments.py",
            "test_metadata.py",
            "download_subtitles.py",
            "test_downloader.py",
        }
        selected_steps = [
            step for step in selected_steps
            if step["script"] not in skip_scripts
        ]

    if args.no_report:
        selected_steps = [
            step for step in selected_steps
            if step["script"] != "generate_report_qwen.py"
        ]

    results = []

    for step in selected_steps:
        result = run_step(step)
        results.append(result)

    summary = {
        "status": "success",
        "input": str(input_dst),
        "steps": results
    }

    summary_path = BASE_DIR / "reports" / "last_run_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("\n" + "=" * 80)
    print("✅ TikTok insight pipeline finished")
    print(f"Summary: {summary_path}")
    print("=" * 80)

if __name__ == "__main__":
    main()
