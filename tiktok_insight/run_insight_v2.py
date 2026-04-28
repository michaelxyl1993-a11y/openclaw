import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
REPORT_DIR = BASE_DIR / "reports"

REPORT_DIR.mkdir(exist_ok=True)

FETCH_STEPS = [
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
]

COMMON_STEPS = [
    {
        "name": "生成 data packet",
        "script": "build_data_packet.py",
        "required": True
    },
]

VIDEO_STEPS = [
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
        "required": True
    },
    {
        "name": "抽取视频关键帧",
        "script": "extract_frames.py",
        "required": True
    },
    {
        "name": "生成视频 contact sheet",
        "script": "make_visual_packet.py",
        "required": True
    },
    {
        "name": "生成视频分析 prompt",
        "script": "make_analysis_prompt.py",
        "required": True
    },
]

SLIDESHOW_STEPS = [
    {
        "name": "下载图文图片",
        "script": "download_slideshow_images.py",
        "required": True
    },
    {
        "name": "生成图文 contact sheet",
        "script": "make_slideshow_visual_packet.py",
        "required": True
    },
    {
        "name": "生成图文分析 prompt",
        "script": "make_analysis_prompt_slideshow.py",
        "required": True
    },
]

REPORT_STEP = {
    "name": "生成 QWEN 报告",
    "script": "generate_report_qwen.py",
    "required": True
}



def assert_valid_video_file(path_value):
    from pathlib import Path
    p = Path(str(path_value or "")).expanduser()
    if str(path_value).strip() in ("", "."):
        raise RuntimeError(f"Video download failed: invalid media_path={path_value!r}")
    if not p.exists():
        raise RuntimeError(f"Video download failed: media file does not exist: {p}")
    if not p.is_file():
        raise RuntimeError(f"Video download failed: media path is not a file: {p}")
    if p.stat().st_size < 1024:
        raise RuntimeError(f"Video download failed: media file too small: {p} size={p.stat().st_size}")
    return str(p)

def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def cache_key(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


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

    print("\n" + "=" * 88)
    print(f"▶️  {step['name']}：{step['script']}")
    print("=" * 88)

    completed = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(BASE_DIR),
        text=True,
        capture_output=True
    )

    if completed.stdout:
        print(completed.stdout)

    if completed.returncode != 0:
        if completed.stderr:
            print(completed.stderr)

        if step["required"]:
            raise RuntimeError(f"Step failed: {step['name']} ({step['script']})")

        print(f"⚠️  可选步骤失败，继续后续流程：{step['name']}")
        return {
            "name": step["name"],
            "script": step["script"],
            "status": "failed_optional",
            "stderr": completed.stderr[-3000:] if completed.stderr else ""
        }

    return {
        "name": step["name"],
        "script": step["script"],
        "status": "success"
    }


def detect_material_type(input_payload: dict, data_packet: dict):
    input_format = (input_payload.get("format") or "").strip().lower()
    metadata = data_packet.get("metadata", {})

    is_slideshow = metadata.get("is_slideshow")

    if is_slideshow is True:
        return "slideshow"

    if input_format in {"photo", "slideshow", "image", "images", "图文"}:
        return "slideshow"

    return "video"


def get_output_paths(input_payload: dict):
    material_url = input_payload["material_url"].strip()
    key = cache_key(material_url)

    return {
        "key": key,
        "data_packet_path": str(REPORT_DIR / f"{key}_data_packet.json"),
        "analysis_prompt_path": str(REPORT_DIR / f"{key}_analysis_prompt.md"),
        "report_qwen_path": str(REPORT_DIR / f"{key}_report_qwen.md"),
        "video_contact_sheet_path": str(REPORT_DIR / f"{key}_contact_sheet.jpg"),
        "slideshow_contact_sheet_path": str(REPORT_DIR / f"{key}_slideshow_contact_sheet.jpg"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="input_test.json", help="Input JSON file path")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip Apify comments/metadata fetching and reuse existing raw files")
    parser.add_argument("--no-report", action="store_true", help="Build packet and prompt only, do not generate QWEN report")
    parser.add_argument("--force-type", choices=["auto", "video", "slideshow"], default="auto", help="Force material type if auto detection is wrong")
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

    input_payload = read_json(input_dst)

    if not input_payload.get("material_url"):
        raise RuntimeError("input JSON missing material_url")

    if not args.skip_fetch and not os.environ.get("APIFY_TOKEN"):
        raise RuntimeError("Missing APIFY_TOKEN. Please export APIFY_TOKEN before full fetch.")

    if not args.no_report:
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("Missing OPENAI_API_KEY. Please export OPENAI_API_KEY before generating report.")

    results = []

    if not args.skip_fetch:
        for step in FETCH_STEPS:
            results.append(run_step(step))
    else:
        print("⏩ skip-fetch enabled: 跳过 Apify 评论和 metadata 抓取，复用已有 raw 文件。")

    for step in COMMON_STEPS:
        results.append(run_step(step))

    paths = get_output_paths(input_payload)
    data_packet_path = Path(paths["data_packet_path"])

    if not data_packet_path.exists():
        raise FileNotFoundError(f"Missing data packet after build step: {data_packet_path}")

    data_packet = read_json(data_packet_path)

    if args.force_type == "auto":
        material_type = detect_material_type(input_payload, data_packet)
    else:
        material_type = args.force_type

    print("\n" + "=" * 88)
    print(f"🧭 Detected material type: {material_type}")
    print("=" * 88)

    if material_type == "slideshow":
        branch_steps = SLIDESHOW_STEPS
    else:
        branch_steps = VIDEO_STEPS

    for step in branch_steps:
        # 视频下载失败时，不允许继续进入 extract_frames.py；
        # 否则 extract_frames 可能拿到 "." 作为输入，导致 ffmpeg 报 "Is a directory"。
        if material_type == "video" and step["script"] == "extract_frames.py":
            media_dir = BASE_DIR / "media"
            key = paths["key"]

            candidates = [
                media_dir / f"{key}.mp4",
                media_dir / f"{key}.mov",
                media_dir / f"{key}.webm",
            ]
            candidates += sorted(media_dir.glob(f"{key}*.mp4"))
            candidates += sorted(media_dir.glob(f"{key}*.mov"))
            candidates += sorted(media_dir.glob(f"{key}*.webm"))

            # 去重
            seen = set()
            unique_candidates = []
            for c in candidates:
                if c not in seen:
                    unique_candidates.append(c)
                    seen.add(c)

            valid_candidates = []
            for c in unique_candidates:
                try:
                    if c.exists() and c.is_file() and c.stat().st_size >= 1024:
                        valid_candidates.append(c)
                except Exception:
                    pass

            if not valid_candidates:
                checked = "\n".join(str(x) for x in unique_candidates[:20])
                raise RuntimeError(
                    "Video download failed: no valid downloaded video file found before extract_frames.py.\n"
                    f"Expected key: {key}\n"
                    f"Checked candidates:\n{checked}\n"
                    "请优先检查 download_media.py 输出、TikTok CDN 下载是否失败，或改用本地视频文件兜底。"
                )

            print(f"✅ Valid video file found before extract_frames: {valid_candidates[0]}")

        results.append(run_step(step))

    if not args.no_report:
        results.append(run_step(REPORT_STEP))

    summary = {
        "status": "success",
        "input": str(input_dst),
        "material_type": material_type,
        "skip_fetch": args.skip_fetch,
        "no_report": args.no_report,
        "outputs": paths,
        "steps": results
    }

    summary_path = REPORT_DIR / "last_run_summary.json"
    write_json(summary_path, summary)

    print("\n" + "=" * 88)
    print("✅ TikTok Insight pipeline v2 finished")
    print(f"Material type: {material_type}")
    print(f"Summary: {summary_path}")
    print(f"Data packet: {paths['data_packet_path']}")
    print(f"Prompt: {paths['analysis_prompt_path']}")
    if not args.no_report:
        print(f"Report: {paths['report_qwen_path']}")
    print("=" * 88)


if __name__ == "__main__":
    main()
