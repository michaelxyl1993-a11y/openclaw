# localekit_test.py
# Local test runner for LocaleKit v1

import argparse
import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path


LOCALEKIT_URL = os.getenv("LOCALEKIT_URL", "http://127.0.0.1:8781/localekit/run")


TEST_CASES = {
    "copy": {
        "task_type": "发布文案本地化",
        "target_market": "DE",
        "target_language": "德语",
        "target_model": "",
        "product": "厨房收纳盒",
        "source_content": "标题：厨房终于不乱了\nCaption：这个收纳盒可以让厨房看起来更整齐，适合小户型家庭。",
        "keep_unchanged": "保留厨房收纳、视觉变整齐、小户型适用这个方向",
        "rewrite_scope": "改成德国TikTok达人带货口语",
        "risk_requirements": "不要英德混用，不要新增未确认卖点",
        "output_requirements": "给我3套标题、caption、5个hashtags，并附中文解释",
    },
    "overlay": {
        "task_type": "Prompt只改图上文字",
        "target_market": "FR",
        "target_language": "法语",
        "target_model": "Nano Banana Pro",
        "product": "女士内衣",
        "source_content": (
            "9:16 TikTok product image, realistic French bedroom scene, soft natural light, "
            "a woman holding the product naturally, clean composition. "
            "Overlay text: Looks expensive, but it is not. "
            "Keep product accurate, no extra claims."
        ),
        "keep_unchanged": "商品、人物、场景、构图、画面风格保持不变",
        "rewrite_scope": "只改图上文字，改成法国本地化表达",
        "risk_requirements": "语气精致自然，不要低俗，不要英法混用，不要新增未确认卖点",
        "output_requirements": "先单独列出本地化后的图上文字，再输出完整可复制Prompt",
    },
    "sora": {
        "task_type": "模型格式适配",
        "target_market": "US",
        "target_language": "美式英语",
        "target_model": "Sora",
        "product": "户外收纳箱",
        "source_content": (
            "一个真实美国家庭后院，露台杂物很乱，女生用收纳箱把坐垫、园艺工具和小物件收起来，"
            "15秒视频，真实手机拍摄感，有口播。"
        ),
        "keep_unchanged": "后院收纳、前后对比、真实手机拍摄感",
        "rewrite_scope": "转成Sora英文prompt，口播用美式英语",
        "risk_requirements": "不要写具体容量、防水、承重、锁孔、液压杆，除非确认",
        "output_requirements": "给我完整Sora Prompt，不要代码块",
    },
    "seedance": {
        "task_type": "模型格式适配",
        "target_market": "DE",
        "target_language": "德语",
        "target_model": "Seedance",
        "product": "厨房收纳盒",
        "source_content": (
            "德国小户型厨房，台面很乱，一位女生把调料、小工具和零散物品放进收纳盒，"
            "15秒竖屏视频，TikTok手机随拍感。"
        ),
        "keep_unchanged": "德国厨房、小户型、收纳前后对比",
        "rewrite_scope": "转成Seedance中文完整提示词，口播用德语",
        "risk_requirements": "不要英德混用，不要新增容量、材质、承重等未确认卖点",
        "output_requirements": "给我完整Seedance中文Prompt，包含0-3秒/3-8秒/8-12秒/12-15秒",
    },
    "risk": {
        "task_type": "合规风险清洗",
        "target_market": "DE",
        "target_language": "德语",
        "target_model": "",
        "product": "牙齿美白贴",
        "source_content": (
            "标题：7天牙齿变白，省下牙医钱！\n"
            "Caption：这款牙贴可以彻底去除黄牙，100%有效，敏感牙也完全没问题。"
        ),
        "keep_unchanged": "保留牙齿看起来更清爽、更有自信这个方向",
        "rewrite_scope": "删除强功效和医疗化表达，改成德国TikTok可用版本",
        "risk_requirements": "不要医疗承诺，不要100%有效，不要7天强承诺",
        "output_requirements": "列出风险点，再给安全标题、caption、5个hashtags",
    },
}


def call_localekit(payload: dict) -> dict:
    request = urllib.request.Request(
        LOCALEKIT_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTPError {e.code}: {body}") from e
    except Exception as e:
        raise RuntimeError(f"LocaleKit request failed: {e}") from e


def save_markdown(result: dict, case_name: str) -> Path:
    output_dir = Path("localekit_outputs")
    output_dir.mkdir(exist_ok=True)

    report_id = result.get("report_id") or time.strftime("LK%Y%m%d-%H%M%S")
    filename = output_dir / f"{report_id}_{case_name}.md"

    content = []
    content.append(f"# LocaleKit Output - {report_id}")
    content.append("")
    content.append(f"- Case: {case_name}")
    content.append(f"- Task Type: {result.get('task_type', '')}")
    content.append(f"- Target Market: {result.get('target_market', '')}")
    content.append(f"- Target Language: {result.get('target_language', '')}")
    content.append(f"- Target Model: {result.get('target_model', '')}")
    content.append("")
    content.append("---")
    content.append("")
    content.append(result.get("reply_text", ""))

    filename.write_text("\n".join(content), encoding="utf-8")
    return filename


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LocaleKit local test cases.")
    parser.add_argument(
        "--case",
        choices=sorted(TEST_CASES.keys()),
        default="copy",
        help="Test case to run.",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save reply_text to localekit_outputs/*.md",
    )
    args = parser.parse_args()

    payload = TEST_CASES[args.case]

    print(f"Running LocaleKit test case: {args.case}")
    print(f"Endpoint: {LOCALEKIT_URL}")
    print("-" * 60)

    result = call_localekit(payload)

    print(f"Status: {result.get('status')}")
    print(f"Report ID: {result.get('report_id')}")
    print(f"Task Type: {result.get('task_type')}")
    print(f"Target Market: {result.get('target_market')}")
    print(f"Target Language: {result.get('target_language')}")
    print("=" * 60)
    print(result.get("reply_text", ""))

    if args.save:
        saved_path = save_markdown(result, args.case)
        print("=" * 60)
        print(f"Saved to: {saved_path}")


if __name__ == "__main__":
    main()