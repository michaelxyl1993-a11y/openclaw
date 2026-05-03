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


def handle_localekit_text(text: str) -> str:
    payload = parse_localekit_message(text)

    ok, error = validate_localekit_payload(payload)
    if not ok:
        return f"""❌ LocaleKit 请求格式不完整

{error}

推荐模板：

【LocaleKit】
任务类型：
目标市场：
目标语言：
目标模型：
商品：
原始内容：

保留不变：
需要改写：
风险要求：
输出要求：
""".strip()

    result = call_localekit(payload)
    return build_localekit_reply(result)