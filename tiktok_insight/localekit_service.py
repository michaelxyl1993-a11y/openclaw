# localekit_service.py
# LocaleKit v1 service layer

import json
import os
import time
import random
import urllib.request
import urllib.error
from typing import Any, Dict

from localekit_prompt_rules import build_localekit_system_prompt, SUPPORTED_TASK_TYPES


def make_localekit_report_id() -> str:
    now = time.strftime("%m%d-%H%M")
    suffix = random.randint(1000, 9999)
    return f"LK{now}-{suffix}"


def normalize_payload(payload: Dict[str, Any]) -> Dict[str, str]:
    return {
        "task_type": str(payload.get("task_type") or payload.get("任务类型") or "").strip(),
        "target_market": str(payload.get("target_market") or payload.get("目标市场") or "").strip(),
        "target_language": str(payload.get("target_language") or payload.get("目标语言") or "").strip(),
        "target_model": str(payload.get("target_model") or payload.get("目标模型") or "").strip(),
        "product": str(payload.get("product") or payload.get("商品") or "").strip(),
        "source_content": str(payload.get("source_content") or payload.get("原始内容") or "").strip(),
        "keep_unchanged": str(payload.get("keep_unchanged") or payload.get("保留不变") or "").strip(),
        "rewrite_scope": str(payload.get("rewrite_scope") or payload.get("需要改写") or "").strip(),
        "risk_requirements": str(payload.get("risk_requirements") or payload.get("风险要求") or "").strip(),
        "output_requirements": str(payload.get("output_requirements") or payload.get("输出要求") or "").strip(),
    }


def validate_request(data: Dict[str, str]) -> None:
    if not data["task_type"]:
        raise ValueError("missing task_type / 任务类型")

    if data["task_type"] not in SUPPORTED_TASK_TYPES:
        raise ValueError(
            "unsupported task_type / 任务类型. Supported: "
            + " / ".join(SUPPORTED_TASK_TYPES)
        )

    if not data["target_market"]:
        raise ValueError("missing target_market / 目标市场")

    if not data["target_language"]:
        raise ValueError("missing target_language / 目标语言")

    if not data["source_content"]:
        raise ValueError("missing source_content / 原始内容")


def build_user_prompt(data: Dict[str, str]) -> str:
    return f"""
请根据以下 LocaleKit 请求执行。

任务类型：{data["task_type"]}
目标市场：{data["target_market"]}
目标语言：{data["target_language"]}
目标模型：{data["target_model"] or "未指定"}
商品：{data["product"] or "未指定"}

原始内容：
{data["source_content"]}

保留不变：
{data["keep_unchanged"] or "未指定"}

需要改写：
{data["rewrite_scope"] or "未指定"}

风险要求：
{data["risk_requirements"] or "未指定"}

输出要求：
{data["output_requirements"] or "给我完整可复制版本"}

请直接输出最终结果。
""".strip()


def call_openai_compatible(messages: list[dict[str, str]]) -> str:
    api_key = (
        os.getenv("LOCALEKIT_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("QWEN_API_KEY")
    )
    base_url = (
        os.getenv("LOCALEKIT_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("QWEN_BASE_URL")
        or "https://api.openai.com/v1"
    )
    model = (
        os.getenv("LOCALEKIT_MODEL")
        or os.getenv("OPENAI_MODEL")
        or os.getenv("QWEN_MODEL")
        or "gpt-5.4-mini"
    )

    if not api_key:
        raise RuntimeError(
            "missing API key. Please set LOCALEKIT_API_KEY or OPENAI_API_KEY or QWEN_API_KEY"
        )

    url = base_url.rstrip("/") + "/chat/completions"

    body = {
        "model": model,
        "messages": messages,
        "stream": False,
    }

    request = urllib.request.Request(
        url=url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM HTTPError {e.code}: {error_body}") from e
    except Exception as e:
        raise RuntimeError(f"LLM request failed: {e}") from e

    try:
        return parsed["choices"][0]["message"]["content"].strip()
    except Exception as e:
        raise RuntimeError(f"Unexpected LLM response: {json.dumps(parsed, ensure_ascii=False)[:2000]}") from e


def run_localekit(payload: Dict[str, Any]) -> Dict[str, Any]:
    report_id = make_localekit_report_id()
    data = normalize_payload(payload)
    validate_request(data)

    system_prompt = build_localekit_system_prompt()
    user_prompt = build_user_prompt(data)

    reply_text = call_openai_compatible(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )

    return {
        "status": "success",
        "tool": "localekit",
        "report_id": report_id,
        "task_type": data["task_type"],
        "target_market": data["target_market"],
        "target_language": data["target_language"],
        "target_model": data["target_model"],
        "reply_text": reply_text,
    }
