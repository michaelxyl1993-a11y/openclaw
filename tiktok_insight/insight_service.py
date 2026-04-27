import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
REPORT_DIR = BASE_DIR / "reports"
OUTPUT_DIR = BASE_DIR / "service_outputs"

OUTPUT_DIR.mkdir(exist_ok=True)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_staff_reply(report_text: str, max_chars: int = 12000) -> str:
    """
    飞书单条消息不适合无限长。这里先做一个保守截断。
    后面接飞书时，如果报告太长，可以改成分段发送。
    """
    report_text = report_text.strip()

    header = "✅ TikTok Insight V3 分析完成\n\n"
    body = report_text

    if len(header + body) <= max_chars:
        return header + body

    clipped = body[:max_chars - len(header) - 300].rstrip()

    return (
        header
        + clipped
        + "\n\n……\n\n⚠️ 报告内容较长，已截断。完整报告请查看本地 report 文件。"
    )


def extract_report_path(stdout: str) -> str:
    """
    从 run_from_message.py 输出里提取 Report: xxx
    """
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("Report: "):
            return line.replace("Report: ", "").strip()
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--message-file", required=True, help="员工输入文本文件")
    parser.add_argument("--skip-fetch", action="store_true", help="复用已有 raw 文件")
    args = parser.parse_args()

    message_path = Path(args.message_file).expanduser()
    if not message_path.is_absolute():
        message_path = BASE_DIR / message_path

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = OUTPUT_DIR / f"{ts}_result.json"

    cmd = [
        sys.executable,
        str(BASE_DIR / "run_from_message.py"),
        "--message-file",
        str(message_path),
    ]

    if args.skip_fetch:
        cmd.append("--skip-fetch")

    try:
        completed = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            text=True,
            capture_output=True,
            timeout=900
        )

        if completed.returncode != 0:
            result = {
                "status": "failed",
                "stage": "run_from_message",
                "message_file": str(message_path),
                "error": completed.stderr[-5000:] if completed.stderr else "Unknown error",
                "stdout_tail": completed.stdout[-5000:] if completed.stdout else "",
                "reply_text": (
                    "❌ TikTok Insight 分析失败。\n\n"
                    "请检查：链接是否有效、体裁是否填写为图文/视频、Apify/QWEN Key 是否可用、网络是否正常。\n\n"
                    "技术错误已写入 service_outputs。"
                )
            }
            write_json(result_path, result)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(1)

        report_path_str = extract_report_path(completed.stdout)

        if not report_path_str:
            raise RuntimeError("未能从 run_from_message.py 输出中提取 report_path")

        report_path = Path(report_path_str)

        if not report_path.exists():
            raise FileNotFoundError(f"报告文件不存在：{report_path}")

        report_text = read_text(report_path)
        reply_text = build_staff_reply(report_text)

        result = {
            "status": "success",
            "message_file": str(message_path),
            "report_path": str(report_path),
            "reply_text": reply_text,
            "reply_chars": len(reply_text),
            "result_path": str(result_path)
        }

        write_json(result_path, result)

        print(json.dumps(result, ensure_ascii=False, indent=2))

    except Exception as e:
        result = {
            "status": "failed",
            "stage": "insight_service",
            "message_file": str(message_path),
            "error": repr(e),
            "reply_text": (
                "❌ TikTok Insight 分析失败。\n\n"
                f"错误原因：{repr(e)}"
            )
        }
        write_json(result_path, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
