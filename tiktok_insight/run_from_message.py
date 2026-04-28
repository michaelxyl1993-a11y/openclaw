import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
INPUTS_DIR = BASE_DIR / "inputs"
REPORT_DIR = BASE_DIR / "reports"

INPUTS_DIR.mkdir(exist_ok=True)
REPORT_DIR.mkdir(exist_ok=True)


FIELD_ALIASES = {
    "market": ["市场", "国家", "market"],
    "product": ["商品", "商品名称", "product"],
    "product_core_selling_points": ["商品核心卖点", "核心卖点", "selling points", "core selling points"],
    "format": ["体裁", "形式", "format"],
    "material_url": ["视频链接", "图文链接", "素材链接", "链接", "url", "material_url"],
    "analysis_goal": ["分析目标", "目标", "analysis_goal"],
    "known_performance_notes": ["补充信息", "已知表现", "表现数据", "补充数据", "notes"]
}


def normalize_url(url: str) -> str:
    url = url.strip()
    if url.startswith("tiktok.com/"):
        url = "https://www." + url
    elif url.startswith("www.tiktok.com/"):
        url = "https://" + url
    return url


def normalize_format(fmt: str) -> str:
    f = fmt.strip().lower()

    if f in ["图文", "photo", "photos", "slideshow", "image", "images"]:
        return "photo"

    if f in ["视频", "video", "short video"]:
        return "video"

    return fmt.strip()


def force_type_from_format(fmt: str) -> str:
    f = normalize_format(fmt).lower()

    if f == "photo":
        return "slideshow"

    if f == "video":
        return "video"

    return "auto"


def parse_message(text: str) -> dict:
    lines = text.splitlines()
    result = {}

    current_key = None
    buffer = []

    label_to_key = {}
    for key, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            label_to_key[alias.lower()] = key

    def flush():
        nonlocal current_key, buffer
        if current_key:
            value = "\n".join(buffer).strip()
            if value:
                result[current_key] = value
        current_key = None
        buffer = []

    for raw_line in lines:
        line = raw_line.rstrip()
        if not line.strip():
            continue

        matched = False

        for label_lower, key in label_to_key.items():
            # 支持：
            # 市场：DE
            # 市场: DE
            # market: DE
            pattern = rf"^\s*{re.escape(label_lower)}\s*[:：]\s*(.*)$"
            m = re.match(pattern, line, flags=re.IGNORECASE)
            if m:
                flush()
                current_key = key
                first_value = m.group(1).strip()
                buffer = [first_value] if first_value else []
                matched = True
                break

        if not matched:
            if current_key:
                buffer.append(line.strip())

    flush()

    return result



def extract_first_tiktok_url(text: str) -> str:
    """
    从整条消息里兜底提取 TikTok URL。
    支持裸链接、Markdown 链接、飞书链接卡片残留。
    """
    if not text:
        return ""

    # Markdown link: [TikTok](https://...)
    m = re.search(r"\[[^\]]*\]\((https?://[^)\s]*tiktok\.com/[^)\s]+)\)", text, flags=re.I)
    if m:
        return m.group(1).strip().rstrip("。,.，)）")

    # Bare URL
    m = re.search(r"https?://[^\s<>\)\"']*tiktok\.com/[^\s<>\)\"']+", text, flags=re.I)
    if m:
        return m.group(0).strip().rstrip("。,.，)）")

    return ""


def build_input(parsed: dict) -> dict:
    # Fallback: 如果字段解析没拿到 material_url，就从原始全文里提取第一个 TikTok 链接
    if not parsed.get("material_url"):
        raw_text = parsed.get("_raw_text") or ""
        fallback_url = extract_first_tiktok_url(raw_text)
        if fallback_url:
            parsed["material_url"] = fallback_url

    required = ["market", "product", "format", "material_url", "analysis_goal"]
    missing = [x for x in required if not parsed.get(x)]

    if missing:
        raise RuntimeError(f"Missing required fields: {missing}")

    material_url = normalize_url(parsed["material_url"])
    fmt = normalize_format(parsed["format"])

    product_core_selling_points = parsed.get("product_core_selling_points", "").strip()

    payload = {
        "market": parsed["market"].strip(),
        "product": parsed["product"].strip(),
        "product_core_selling_points": product_core_selling_points,
        "format": fmt,
        "material_url": material_url,
        "analysis_goal": parsed["analysis_goal"].strip(),
        "comment_limit": 100,
        "mode": "standard_v3",
        "known_performance": {
            "source": "team_or_competitor",
            "notes": parsed.get("known_performance_notes", "").strip()
        }
    }

    return payload


def save_input(payload: dict) -> Path:
    key = hashlib.md5(payload["material_url"].encode("utf-8")).hexdigest()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = INPUTS_DIR / f"{ts}_{key}_input.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def cache_key(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--message-file", required=True, help="Path to staff message text file")
    parser.add_argument("--skip-fetch", action="store_true", help="Reuse existing raw files")
    args = parser.parse_args()

    message_path = Path(args.message_file).expanduser()
    if not message_path.is_absolute():
        message_path = BASE_DIR / message_path

    if not message_path.exists():
        raise FileNotFoundError(f"Message file not found: {message_path}")

    text = message_path.read_text(encoding="utf-8")
    parsed = parse_message(text)
    parsed["_raw_text"] = text
    payload = build_input(parsed)

    input_path = save_input(payload)
    force_type = force_type_from_format(payload["format"])

    cmd = [
        sys.executable,
        str(BASE_DIR / "run_insight_v2.py"),
        "--input",
        str(input_path),
    ]

    if force_type != "auto":
        cmd += ["--force-type", force_type]

    if args.skip_fetch:
        cmd += ["--skip-fetch"]

    print("=" * 88)
    print("Parsed input:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("=" * 88)
    print("Running:")
    print(" ".join(cmd))
    print("=" * 88)

    completed = subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        text=True
    )

    if completed.returncode != 0:
        raise RuntimeError("run_insight_v2.py failed")

    key = cache_key(payload["material_url"])
    report_path = REPORT_DIR / f"{key}_report_qwen.md"

    if not report_path.exists():
        raise FileNotFoundError(f"Report not found: {report_path}")

    print("\n" + "=" * 88)
    print("✅ Insight report generated")
    print(f"Input JSON: {input_path}")
    print(f"Report: {report_path}")
    print("=" * 88)

    report_text = report_path.read_text(encoding="utf-8")

    print("\n\n===== REPORT START =====\n")
    print(report_text)
    print("\n===== REPORT END =====\n")


if __name__ == "__main__":
    main()
