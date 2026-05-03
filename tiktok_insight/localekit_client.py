# localekit_client.py
# Feishu-side client for calling standalone LocaleKit HTTP service

import json
import os
import re
import urllib.request
import urllib.error
from typing import Dict, Any


LOCALEKIT_RUN_URL = os.getenv(
    "LOCALEKIT_RUN_URL",
    "http://127.0.0.1:8781/localekit/run",
)


LOCALEKIT_TASK_TYPES = [
    "Prompt只改口播",
    "Prompt只改图上文字",
    "发布文案本地化",
    "整套素材本地化",
    "模型格式适配",
    "合规风险清洗",
]


def is_localekit_message(text: str) -> bool:
    if not text:
        return False

    normalized = text.strip()

    if normalized.startswith("【LocaleKit】"):
        return True

    if normalized.startswith("【本地化器】"):
        return True

    if "任务类型：" in normalized and any(t in normalized for t in LOCALEKIT_TASK_TYPES):
        return True

    if "任务类型:" in normalized and any(t in normalized for t in LOCALEKIT_TASK_TYPES):
        return True

    return False


def _extract_field(text: str, field_names: list[str]) -> str:
    """
    Extract a field block from Chinese template text.

    Supports:
    任务类型：
    任务类型:
    target_market:
    """
    all_fields = [
        "任务类型", "目标市场", "目标语言", "目标模型", "商品",
        "原始内容", "保留不变", "需要改写", "风险要求", "输出要求",
        "task_type", "target_market", "target_language", "target_model", "product",
        "source_content", "keep_unchanged", "rewrite_scope", "risk_requirements", "output_requirements",
    ]

    for field in field_names:
        pattern = rf"(?:^|\n){re.escape(field)}\s*[:：]\s*"
        match = re.search(pattern, text)
        if not match:
            continue

        start = match.end()

        next_positions = []
        for next_field in all_fields:
            next_pattern = rf"\n{re.escape(next_field)}\s*[:：]\s*"
            next_match = re.search(next_pattern, text[start:])
            if next_match:
                next_positions.append(start + next_match.start())

        end = min(next_positions) if next_positions else len(text)
        return text[start:end].strip()

    return ""


def parse_localekit_message(text: str) -> Dict[str, str]:
    clean_text = text.strip()
    clean_text = clean_text.replace("【LocaleKit】", "", 1).strip()
    clean_text = clean_text.replace("【本地化器】", "", 1).strip()

    payload = {
        "task_type": _extract_field(clean_text, ["任务类型", "task_type"]),
        "target_market": _extract_field(clean_text, ["目标市场", "target_market"]),
        "target_language": _extract_field(clean_text, ["目标语言", "target_language"]),
        "target_model": _extract_field(clean_text, ["目标模型", "target_model"]),
        "product": _extract_field(clean_text, ["商品", "product"]),
        "source_content": _extract_field(clean_text, ["原始内容", "source_content"]),
        "keep_unchanged": _extract_field(clean_text, ["保留不变", "keep_unchanged"]),
        "rewrite_scope": _extract_field(clean_text, ["需要改写", "rewrite_scope"]),
        "risk_requirements": _extract_field(clean_text, ["风险要求", "risk_requirements"]),
        "output_requirements": _extract_field(clean_text, ["输出要求", "output_requirements"]),
    }

    return payload


def validate_localekit_payload(payload: Dict[str, str]) -> tuple[bool, str]:
    if not payload.get("task_type"):
        return False, "缺少任务类型。请填写：任务类型：发布文案本地化 / Prompt只改口播 / Prompt只改图上文字 / 整套素材本地化 / 模型格式适配 / 合规风险清洗"

    if payload["task_type"] not in LOCALEKIT_TASK_TYPES:
        return False, "任务类型不支持。当前支持：\n" + "\n".join([f"- {x}" for x in LOCALEKIT_TASK_TYPES])

    if not payload.get("target_market"):
        return False, "缺少目标市场。请填写：目标市场：DE / FR / US / UK"

    if not payload.get("target_language"):
        return False, "缺少目标语言。请填写：目标语言：德语 / 法语 / 美式英语 / 英式英语"

    if not payload.get("source_content"):
        return False, "缺少原始内容。请填写：原始内容：..."

    return True, ""


def call_localekit(payload: Dict[str, Any]) -> Dict[str, Any]:
    request = urllib.request.Request(
        LOCALEKIT_RUN_URL,
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
        raise RuntimeError(f"LocaleKit HTTPError {e.code}: {body}") from e
    except Exception as e:
        raise RuntimeError(f"LocaleKit request failed: {e}") from e


def build_localekit_reply(result: Dict[str, Any]) -> str:
    if result.get("status") != "success":
        return (
            "❌ LocaleKit 执行失败\n\n"
            f"错误：{result.get('error') or result}"
        )

    report_id = result.get("report_id", "")
    task_type = result.get("task_type", "")
    target_market = result.get("target_market", "")
    target_language = result.get("target_language", "")
    reply_text = result.get("reply_text", "")

    return f"""✅ LocaleKit 本地化结果

Report ID：{report_id}
任务类型：{task_type}
目标市场：{target_market}
目标语言：{target_language}

{reply_text}
""".strip()



def is_localekit_help_request(text: str) -> bool:
    if not text:
        return False

    normalized = text.strip()
    clean = normalized.replace("【LocaleKit】", "").replace("【本地化器】", "").strip()

    # 只发【LocaleKit】或【本地化器】时，返回帮助
    if clean == "":
        return True

    lower = clean.lower()

    help_keywords = [
        "帮助", "help",
        "模板", "用法", "怎么用", "如何使用",
        "支持哪些", "示例", "example"
    ]

    # 注意：不要把“任务类型”本身当成帮助关键词。
    # 因为正常请求里都会有“任务类型：xxx”。
    has_help_keyword = any(k in clean for k in help_keywords) or any(k in lower for k in help_keywords)

    if has_help_keyword:
        return True

    return False

def build_localekit_help_reply() -> str:
    return """✅ LocaleKit 本地化器使用说明

LocaleKit 不是素材分析工具，不需要 TikTok 链接。
它用于：发布文案本地化、Prompt 本地化、视频/图片模型 Prompt 格式适配、合规风险清洗。

【支持的任务类型】
1. Prompt只改口播
2. Prompt只改图上文字
3. 发布文案本地化
4. 整套素材本地化
5. 模型格式适配
6. 合规风险清洗

【标准模板】

【LocaleKit】
任务类型：发布文案本地化
目标市场：DE
目标语言：德语
目标模型：
商品：
原始内容：

保留不变：
需要改写：
风险要求：
输出要求：

【示例】

【LocaleKit】
任务类型：发布文案本地化
目标市场：DE
目标语言：德语
目标模型：
商品：厨房收纳盒
原始内容：
标题：厨房终于不乱了
Caption：这个收纳盒可以让厨房看起来更整齐，适合小户型家庭。

保留不变：厨房收纳、视觉变整齐、小户型适用
需要改写：改成德国 TikTok 达人口语
风险要求：不要英德混用，不要新增未确认卖点
输出要求：给我3套标题、caption、5个hashtags，并附中文解释

【注意】
- 如果要分析 TikTok 链接，请用分析虾素材分析模板，不要用 LocaleKit。
- 如果只是本地化文案、口播、图上文字或 Prompt，请用 LocaleKit。
- DE 必须德语，FR 必须法语，避免英德/英法混用。
""".strip()


def build_localekit_error_reply(error: str, payload: Dict[str, str]) -> str:
    task_type = payload.get("task_type", "")
    target_market = payload.get("target_market", "")
    target_language = payload.get("target_language", "")
    source_content = payload.get("source_content", "")

    filled = []
    if task_type:
        filled.append(f"任务类型：{task_type}")
    if target_market:
        filled.append(f"目标市场：{target_market}")
    if target_language:
        filled.append(f"目标语言：{target_language}")
    if source_content:
        filled.append("原始内容：已填写")

    filled_text = "\n".join(filled) if filled else "暂未识别到有效字段"

    return f"""❌ LocaleKit 请求格式不完整

问题：
{error}

我当前识别到：
{filled_text}

请按下面模板重新发送：

【LocaleKit】
任务类型：发布文案本地化
目标市场：DE
目标语言：德语
目标模型：
商品：
原始内容：

保留不变：
需要改写：
风险要求：
输出要求：

支持的任务类型：
- Prompt只改口播
- Prompt只改图上文字
- 发布文案本地化
- 整套素材本地化
- 模型格式适配
- 合规风险清洗

如果不知道怎么写，可以直接发送：
【LocaleKit】帮助
""".strip()


def handle_localekit_text(text: str) -> str:
    if is_localekit_help_request(text):
        return build_localekit_help_reply()

    payload = parse_localekit_message(text)

    ok, error = validate_localekit_payload(payload)
    if not ok:
        return build_localekit_error_reply(error, payload)

    result = call_localekit(payload)
    return build_localekit_reply(result)

