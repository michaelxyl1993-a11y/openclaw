# Local dev SSL workaround for macOS/proxy self-signed certificate chain.
# Only for local Feishu bot testing.
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import argparse
import json
import re
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import hashlib
from openai import OpenAI


def clean_feishu_message_text(text: str) -> str:
    """Clean Feishu mention placeholders and invisible chars."""
    import re
    if not text:
        return ""
    # Feishu text content uses placeholders like @_user_1 for bot mentions
    text = re.sub(r"@\s*_user_\d+\s*", "", text)
    text = re.sub(r"@\S*user_\d+\s*", "", text)
    text = re.sub(r"@\s*Content\s+Analyzer\s*", "", text, flags=re.I)
    text = text.replace("\u200b", "").replace("\ufeff", "")
    return text.strip()


BASE_DIR = Path(__file__).parent
FEISHU_LOG_DIR = BASE_DIR / "feishu_logs"
PROCESSED_EVENTS_PATH = BASE_DIR / "feishu_processed_events.json"
DEDUP_LOCK = threading.Lock()
FEISHU_LOG_DIR.mkdir(exist_ok=True)

INSIGHT_SERVER = os.getenv("INSIGHT_SERVER", "http://127.0.0.1:8765").rstrip("/")
FEISHU_OPEN_BASE = os.getenv("FEISHU_OPEN_BASE", "https://open.feishu.cn")

APP_ID = os.getenv("FEISHU_APP_ID", "").strip()
APP_SECRET = os.getenv("FEISHU_APP_SECRET", "").strip()
VERIFY_TOKEN = os.getenv("FEISHU_VERIFICATION_TOKEN", "").strip()

DEFAULT_SKIP_FETCH = os.getenv("INSIGHT_SKIP_FETCH_DEFAULT", "false").lower() in ["1", "true", "yes"]

TOKEN_CACHE = {
    "token": "",
    "expire_at": 0
}


def now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def write_json_log(prefix: str, data: dict):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = FEISHU_LOG_DIR / f"{ts}_{prefix}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def http_json(method: str, url: str, data: dict | None = None, headers: dict | None = None, timeout: int = 30) -> dict:
    body = None
    final_headers = {
        "Content-Type": "application/json; charset=utf-8"
    }
    if headers:
        final_headers.update(headers)

    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=final_headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {e.code} {url}: {raw}") from e


def get_tenant_access_token() -> str:
    if not APP_ID or not APP_SECRET:
        raise RuntimeError("Missing FEISHU_APP_ID or FEISHU_APP_SECRET")

    now = int(time.time())
    if TOKEN_CACHE["token"] and TOKEN_CACHE["expire_at"] > now + 120:
        return TOKEN_CACHE["token"]

    url = f"{FEISHU_OPEN_BASE}/open-apis/auth/v3/tenant_access_token/internal"
    resp = http_json("POST", url, {
        "app_id": APP_ID,
        "app_secret": APP_SECRET
    })

    token = resp.get("tenant_access_token")
    expire = int(resp.get("expire", 7200))

    if not token:
        raise RuntimeError(f"Failed to get tenant_access_token: {resp}")

    TOKEN_CACHE["token"] = token
    TOKEN_CACHE["expire_at"] = now + expire
    return token


def split_text(text: str, max_chars: int = 3500) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    chunks = []
    current = ""

    for para in text.split("\n"):
        if len(current) + len(para) + 1 <= max_chars:
            current += para + "\n"
        else:
            if current.strip():
                chunks.append(current.strip())
            current = para + "\n"

    if current.strip():
        chunks.append(current.strip())

    return chunks



def make_feishu_short_reply(full_text: str) -> str:
    """
    飞书默认回复短版：
    - 保留完整报告在本地 md
    - 飞书只发运营决策版，避免刷屏
    """
    if not full_text:
        return ""

    text = full_text.strip()

    # 尽量从完整报告里抽取关键章节
    wanted_heads = [
        "## 1. 一句话结论",
        "## 2. 核心情绪",
        "## 3. 口播卖点拆解",
        "## 4. 画面证明方式",
        "## 5. 可套用视频模板",
        "## 6. 可套用图文模板",
        "## 7. 下一条直接怎么做",
        "## 8. 风险与评论区拦截",
    ]

    short_head_map = {
        "## 1. 一句话结论": "## 1. 一句话结论",
        "## 2. 核心情绪": "## 2. 核心情绪",
        "## 3. 口播卖点拆解": "## 3. 口播卖点拆解",
        "## 4. 画面证明方式": "## 4. 画面证明方式",
        "## 5. 可套用视频模板": "## 5. 可套用视频模板",
        "## 6. 可套用图文模板": "## 6. 可套用图文模板",
        "## 7. 下一条直接怎么做": "## 7. 下一条直接怎么做",
        "## 8. 风险与评论区拦截": "## 8. 风险与评论区拦截",
    }

    lines = text.splitlines()
    picked = []
    current_head = None
    keep = False
    kept_lines_for_head = 0

    for line in lines:
        if line.startswith("## "):
            current_head = line.strip()
            keep = current_head in wanted_heads
            kept_lines_for_head = 0
            if keep:
                picked.append(short_head_map.get(current_head, line))
            continue

        if keep:
            # 每个章节最多保留 5 行，避免太长
            if kept_lines_for_head < 5:
                picked.append(line)
                kept_lines_for_head += 1

    short = "\n".join(picked).strip()

    # 如果抽取失败，就直接取前面一段
    if len(short) < 200:
        short = text[:1800]

    # 清理过长内容
    max_len = 2200
    if len(short) > max_len:
        short = short[:max_len].rstrip() + "\n\n……"

    short = format_feishu_reply_for_readability(short)
    return "✅ TikTok Insight V1 复刻执行报告\n\n" + short + "\n\n📄 完整深度报告已保存到本地 reports 目录。"


def format_feishu_reply_for_readability(text: str) -> str:
    """
    飞书阅读优化：
    - ## 1. 结论先行 -> 【1. 结论先行】
    - 章节前后增加空行
    - 列表之间适度留白
    """
    if not text:
        return ""

    lines = text.splitlines()
    out = []

    for raw in lines:
        line = raw.rstrip()

        # Markdown 二级标题转成飞书更醒目的中文括号标题
        if line.startswith("## "):
            title = line.replace("## ", "", 1).strip()
            if out and out[-1] != "":
                out.append("")
            out.append(f"【{title}】")
            out.append("")
            continue

        # 去掉多余的 Markdown 加粗符号，飞书纯文本里更干净
        line = line.replace("**", "")

        # 一级标题如果保留，改成普通醒目行
        if line.startswith("# "):
            title = line.replace("# ", "", 1).strip()
            if out and out[-1] != "":
                out.append("")
            out.append(f"【{title}】")
            out.append("")
            continue

        out.append(line)

    # 压缩连续空行，最多保留一个空行
    cleaned = []
    blank = False
    for line in out:
        if line.strip() == "":
            if not blank:
                cleaned.append("")
            blank = True
        else:
            cleaned.append(line)
            blank = False

    return "\n".join(cleaned).strip()


def reply_message(message_id: str, text: str):
    token = get_tenant_access_token()
    url = f"{FEISHU_OPEN_BASE}/open-apis/im/v1/messages/{message_id}/reply"

    parts = split_text(text)

    for idx, part in enumerate(parts):
        prefix = ""
        if len(parts) > 1:
            prefix = f"（{idx + 1}/{len(parts)}）\n"

        body = {
            "msg_type": "text",
            "content": json.dumps({
                "text": prefix + part
            }, ensure_ascii=False)
        }

        resp = http_json(
            "POST",
            url,
            body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )

        if resp.get("code", 0) != 0:
            raise RuntimeError(f"Reply message failed: {resp}")

        time.sleep(0.3)


def normalize_markdown_links(text: str) -> str:
    """
    飞书会把链接文本变成 [TikTok](https://...)。
    下游只接受裸 TikTok URL，所以这里统一还原。
    """
    if not text:
        return text

    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\2", text)
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return text

def extract_text_message(event_payload: dict) -> tuple[str, str]:
    """
    返回 message_id, text
    支持飞书 v2 事件结构。
    """
    event = event_payload.get("event", {})
    message = event.get("message", {})

    message_id = message.get("message_id", "")
    message_type = message.get("message_type", "")
    raw_content = message.get("content", "")

    if message_type != "text":
        return message_id, ""

    try:
        content_obj = json.loads(raw_content)
        text = content_obj.get("text", "")
    except Exception:
        text = raw_content

    text = clean_feishu_message_text(text)
    text = normalize_markdown_links(text)
    return message_id, text.strip()



def load_processed_events() -> dict:
    if not PROCESSED_EVENTS_PATH.exists():
        return {}
    try:
        return json.loads(PROCESSED_EVENTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_processed_events(data: dict):
    # 只保留最近 1000 条，避免文件无限增长
    items = list(data.items())[-1000:]
    compact = dict(items)
    PROCESSED_EVENTS_PATH.write_text(
        json.dumps(compact, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def is_duplicate_event(payload: dict, message_id: str) -> bool:
    """
    飞书可能同一条消息用不同 event_id 重试投递。
    所以不能只看 event_id；event_id 和 message_id 任意一个命中过，都视为重复。
    """
    header = payload.get("header", {}) or {}
    event_id = header.get("event_id", "") or payload.get("uuid", "")

    keys = []
    if event_id:
        keys.append(f"event:{event_id}")
    if message_id:
        keys.append(f"message:{message_id}")

    if not keys:
        return False

    data = load_processed_events()

    # 任意 key 已存在，都认为重复
    for key in keys:
        if key in data:
            return True

    record = {
        "message_id": message_id,
        "event_id": event_id,
        "time": now_ts()
    }

    # event_id 和 message_id 都写入，后续任意一种重复都能拦住
    for key in keys:
        data[key] = record

    save_processed_events(data)
    return False


def get_event_chat_id(payload: dict) -> str:
    try:
        return (
            payload.get("event", {})
            .get("message", {})
            .get("chat_id", "")
        ) or ""
    except Exception:
        return ""


def normalize_text_for_dedupe(text: str) -> str:
    if not text:
        return ""
    try:
        text = clean_feishu_message_text(text)
    except Exception:
        pass
    try:
        text = normalize_markdown_links(text)
    except Exception:
        pass
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    return text.strip()


def is_duplicate_content(payload: dict, message_id: str, text: str, ttl_seconds: int = 600) -> bool:
    """
    强去重：
    同一个 chat_id + 同一段清洗正文，ttl_seconds 内只允许提交一次。
    加 DEDUP_LOCK，避免飞书并发重试时两个请求同时穿透。
    """
    with DEDUP_LOCK:
        chat_id = get_event_chat_id(payload)
        normalized = normalize_text_for_dedupe(text)

        if not normalized:
            return False

        key_raw = f"{chat_id}|{normalized}"
        content_hash = hashlib.sha256(key_raw.encode("utf-8")).hexdigest()
        key = f"content:{content_hash}"

        data = load_processed_events()
        now = datetime.now().timestamp()

        cleaned = {}
        for k, v in data.items():
            if not k.startswith("content:"):
                cleaned[k] = v
                continue
            try:
                ts = float(v.get("ts", 0))
            except Exception:
                ts = 0
            if now - ts <= ttl_seconds:
                cleaned[k] = v

        data = cleaned

        if key in data:
            write_json_log("duplicate_content", {
                "message_id": message_id,
                "chat_id": chat_id,
                "hash": content_hash,
                "text_preview": normalized[:300],
            })
            return True

        data[key] = {
            "message_id": message_id,
            "chat_id": chat_id,
            "text_preview": normalized[:300],
            "time": now_ts(),
            "ts": now,
        }
        save_processed_events(data)
        return False



LAST_CONTEXT_PATH = BASE_DIR / "feishu_last_report_context.json"

def make_report_id() -> str:
    """生成短 Report ID，例如 R0428-1923-5F3A。"""
    suffix = hashlib.md5(f"{time.time()}-{os.getpid()}".encode("utf-8")).hexdigest()[:4].upper()
    return datetime.now().strftime("R%m%d-%H%M-") + suffix


def extract_report_id(text: str) -> str:
    """从追问文本里识别 Report ID。"""
    if not text:
        return ""
    m = re.search(r"\bR\d{4}-\d{4}-[A-Z0-9]{4}\b", text)
    if m:
        return m.group(0)
    return ""


def save_last_report_context(chat_id: str, message_id: str, report_path: str, reply_text: str, report_id: str = ""):
    """
    保存同一个群最近一次成功分析报告，并保存最近 20 条历史报告。
    """
    if not chat_id or not report_path:
        return

    if not report_id:
        report_id = make_report_id()

    data = {}
    if LAST_CONTEXT_PATH.exists():
        try:
            data = json.loads(LAST_CONTEXT_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}

    chat_ctx = data.get(chat_id) or {}
    history = chat_ctx.get("history") or []

    item = {
        "report_id": report_id,
        "message_id": message_id,
        "report_path": report_path,
        "reply_preview": (reply_text or "")[:3000],
        "time": now_ts(),
    }

    # 去重：同 report_id 或同 report_path 的旧记录先移除
    history = [
        x for x in history
        if x.get("report_id") != report_id and x.get("report_path") != report_path
    ]

    history.insert(0, item)
    history = history[:20]

    chat_ctx["latest_report_id"] = report_id
    chat_ctx["message_id"] = message_id
    chat_ctx["report_id"] = report_id
    chat_ctx["report_path"] = report_path
    chat_ctx["reply_preview"] = (reply_text or "")[:3000]
    chat_ctx["time"] = now_ts()
    chat_ctx["history"] = history

    data[chat_id] = chat_ctx

    LAST_CONTEXT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def load_last_report_context(chat_id: str, report_id: str = "") -> dict:
    """
    读取报告上下文。
    - 如果提供 report_id，优先在该群历史报告里找指定报告
    - 如果不提供，则读取最近一次成功报告
    """
    if not chat_id or not LAST_CONTEXT_PATH.exists():
        return {}

    try:
        data = json.loads(LAST_CONTEXT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

    chat_ctx = data.get(chat_id) or {}
    if not chat_ctx:
        return {}

    if report_id:
        for item in chat_ctx.get("history", []):
            if item.get("report_id") == report_id:
                report_path = item.get("report_path")
                if report_path and Path(report_path).exists():
                    return item
                return {}
        return {}

    report_path = chat_ctx.get("report_path")
    if not report_path or not Path(report_path).exists():
        return {}

    return chat_ctx


def list_recent_report_ids(chat_id: str) -> str:
    """返回本群最近报告 ID 列表，用于找不到指定 ID 时提示。"""
    if not chat_id or not LAST_CONTEXT_PATH.exists():
        return ""

    try:
        data = json.loads(LAST_CONTEXT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return ""

    chat_ctx = data.get(chat_id) or {}
    history = chat_ctx.get("history") or []
    if not history:
        return ""

    lines = []
    for item in history[:8]:
        rid = item.get("report_id", "")
        t = item.get("time", "")
        if rid:
            lines.append(f"- {rid}（{t}）")
    return "\n".join(lines)

def is_followup_message(text: str) -> bool:
    """
    判断是否像追问。
    完整模板消息仍然走正式分析；非完整模板但包含追问关键词时，走追问模式。
    """
    if not text:
        return False

    if should_process_message(text):
        return False

    lowered = text.lower()
    keywords = [
        "继续", "追问", "上面", "刚才", "这条", "这个", "这份报告",
        "适合", "图文", "视频", "复刻", "模板", "脚本", "口播",
        "评论", "回复", "标题", "文案", "怎么做", "怎么拍", "怎么改",
        "情绪", "卖点", "表达方式", "套用",
        "give", "script", "template", "caption", "hook", "video", "carousel"
    ]

    return any(k in lowered or k in text for k in keywords)


VIDEO_EXECUTION_PACK_RULES = """
## Video Execution Pack Mode｜视频执行包模式

当用户基于上一份 TikTok Insight 报告追问，并且追问内容包含以下任意意图时，进入“视频执行包模式”：
- 视频执行包
- 视频脚本
- 视频分镜
- 分镜脚本
- Sora 提示词
- Seedance 提示词
- Kling 提示词
- Veo 提示词
- HappyHorse 提示词
- 即梦提示词
- 生成视频 prompt
- 生视频提示词
- 视频模型提示词
- 根据报告生成脚本
- 继续出视频脚本
- 给我 3 套视频脚本
- 给我 Sora/Seedance 版本

视频执行包模式的任务不是重新分析素材，而是把最近一次成功分析报告转成可执行生产方案。

必须基于报告内容提取：
- 市场与目标语言
- 商品与核心卖点
- 推荐复刻方向
- 画面证明方式
- 评论区风险与购买质疑
- 禁止夸大的未确认卖点
- 适合图文还是视频优先

不得凭空新增报告中没有确认的卖点。
涉及容量、防水、防晒、承重、材质、锁具、尺寸、功效、续航、保修、价格、物流、库存等未确认信息时，必须标注“需商品团队确认”。

## FINAL OUTPUT CONTRACT｜最终输出硬契约

进入视频执行包模式后，只允许按下面模板输出。不要改变模块顺序，不要省略字段。

开头必须写：
✅ 基于最近一次报告生成视频执行包

然后输出 3 套方案。

每套方案标题格式必须为：
## 方案 X：标题
Hook Family：痛点/前后对比型 / 功能证明/装载清单型 / 场景代入型 / 价值信任/细节证明型 / 时效反差型

三套方案的 Hook Family 不能重复。

每套方案必须按以下顺序输出：

### 1）15秒结构

0–3秒：
- 画面：
- 口播：

3–8秒：
- 画面：
- 口播：

8–12秒：
- 画面：
- 口播：

12–15秒：
- 画面：
- 口播：

禁止出现“15秒后”“15s+”“结尾后”“额外镜头”。
CTA 必须放在 12–15秒内完成。

### 2）默认安全字幕
- 
- 
- 
- 

默认安全字幕不能包含未确认参数或功能。
容量、防水、承重、锁孔、液压杆、UV、可坐人、尺寸、价格、质保、库存、物流等，只能放入【确认后可选字幕】。

### 3）确认后可选字幕
需商品团队确认后才可使用：
- 
- 
- 

### 4）人类拍摄版注意事项
- 
- 
- 

必须包含：
- 场景要求
- 人物/手部出镜要求
- 镜头风格要求
- 避免 AI 感要求
- 避免误导和夸大要求

### 5）Sora Prompt / English

必须是一段完整英文 Prompt。
必须包含：
- 15-second vertical TikTok-style video
- 9:16
- realistic handheld smartphone footage
- scene
- product
- time-coded shots
- voiceover in target-market language
- no text, no subtitles, no captions, no on-screen text, no watermark, no logos
- keep the product shape, color, material, and proportions consistent
- realistic hand-object interaction, no clipping
- no unverified claims

Sora Prompt 不允许要求模型生成任何文字、字幕、caption、overlay 或贴纸。
Sora Prompt 只负责画面、人物动作、商品交互、镜头、场景和真实感。

### 6）Seedance Prompt / 中文完整提示词

必须是完整中文 Prompt，不能只列分镜。
必须包含：
- 生成15秒9:16竖屏视频
- TikTok手机随拍感
- 目标市场真实场景
- 主体商品外观保持一致
- 0–3秒 / 3–8秒 / 8–12秒 / 12–15秒
- 口播，口播必须使用目标市场语言
- 限制项

Seedance Prompt 的限制项必须包含：
不要生成文字、字幕、水印、logo；不要出现 Gallonen / Inch；不要夸大防水、防晒、承重、锁孔、液压杆、容量等未确认卖点；人手和商品交互真实，不穿模；商品外观、颜色、比例、材质保持一致。

## 输出硬规则

- 禁止输出 Markdown 代码块符号。
- 字幕不要使用反引号包裹。
- 不要写“同上”。
- Prompt 直接放在标题下方，方便复制。
- 如果内容过长，自动分段输出，并在每段开头标注（1/3）（2/3）（3/3）。
- 不要把同一个 Prompt 截断在中间。
"""


def answer_followup_with_gpt(chat_id: str, question: str) -> str:
    requested_report_id = extract_report_id(question)
    ctx = load_last_report_context(chat_id, requested_report_id)

    if requested_report_id and not ctx:
        recent = list_recent_report_ids(chat_id)
        extra = f"\n\n本群最近可用报告 ID：\n{recent}" if recent else ""
        return (
            f"我没有找到报告 ID：{requested_report_id}，暂时无法基于这份报告追问。"
            f"{extra}\n\n"
            "请检查 Report ID 是否复制完整，格式类似：R0428-1923-5F3A。"
        )

    if not ctx:
        return (
            "我还没有找到本群最近一次成功分析报告，暂时无法追问。\n\n"
            "请先按完整模板提交一条 TikTok 素材，等 Bot 输出 V1 报告后，再在同一个群里追问。"
        )

    report_id = ctx.get("report_id") or requested_report_id or "最近一次报告"
    report_path = Path(ctx["report_path"])
    report_text = report_path.read_text(encoding="utf-8")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return "追问失败：当前服务缺少 OPENAI_API_KEY。"

    model = os.environ.get("OPENAI_FOLLOWUP_MODEL") or os.environ.get("OPENAI_MODEL", "gpt-5.5")
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip()

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = OpenAI(**client_kwargs)

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
    "你是 TikTok Shop 内容复刻执行顾问。"
    "用户正在基于上一份 TikTok Insight 报告做追问。"
    "请只回答用户追问，不要重新输出完整报告。"
    "回答必须基于报告内容，不要凭空扩展。"
    "默认输出执行清单，而不是长篇解释。"
    "如果用户要图文结构，每套控制在3-5页，每页只写：画面、图上文字、作用。"
    "如果用户要口播，直接给可复制口播句式。"
    "如果用户要评论回复，直接给可复制回复话术。"
    "每次优先给2套方案，除非用户明确要求更多。"
    "不要写过多背景分析，不要重复上一份报告内容。"
    "涉及尺码、价格、材质、功效、带载时长、质保、库存等未确认信息时，必须标注需商品团队确认。"
    "中文回复，结构清晰，避免空泛。"
    "\n\n"
    + VIDEO_EXECUTION_PACK_RULES
                )
            },
            {
                "role": "user",
                "content": (
                    f"当前使用的报告 ID：{report_id}\n\n"
                    "以下是用于追问的完整报告：\n\n"
                    f"{report_text[:20000]}\n\n"
                    "用户追问：\n"
                    f"{question}\n\n"
                    "请基于上一份报告回答追问。"
                )
            }
        ],
        max_completion_tokens=5000
    )

    return completion.choices[0].message.content or "追问失败：模型没有返回内容。"


def run_followup_and_reply(message_id: str, chat_id: str, text: str):
    try:
        requested_report_id = extract_report_id(text)
        if requested_report_id:
            reply_message(message_id, f"收到，这是基于报告 {requested_report_id} 的追问，我来补充回答。")
        else:
            reply_message(message_id, "收到，这是基于最近一次成功报告的追问，我来补充回答。")
        answer = answer_followup_with_gpt(chat_id, text)
        reply_message(message_id, answer)
    except Exception as e:
        write_json_log("followup_error", {
            "message_id": message_id,
            "chat_id": chat_id,
            "error": repr(e),
            "text_preview": text[:1000],
        })
        try:
            reply_message(
                message_id,
                "❌ 追问处理失败。\n\n"
                f"错误：{repr(e)}"
            )
        except Exception:
            pass


def should_process_message(text: str) -> bool:
    required_markers = ["市场", "商品", "体裁"]
    has_required = all(x in text for x in required_markers)
    has_url = "tiktok.com/" in text
    return has_required and has_url


def detect_skip_fetch(text: str) -> bool:
    lowered = text.lower()
    if "skip_fetch:true" in lowered or "skip-fetch:true" in lowered or "跳过抓取：是" in text:
        return True
    if "skip_fetch:false" in lowered or "skip-fetch:false" in lowered or "跳过抓取：否" in text:
        return False
    return DEFAULT_SKIP_FETCH


def submit_insight_job(message_text: str, skip_fetch: bool, chat_id: str = "") -> str:
    url = f"{INSIGHT_SERVER}/analyze"
    resp = http_json("POST", url, {
        "message": message_text,
        "skip_fetch": skip_fetch
    }, timeout=30)

    if resp.get("status") != "accepted":
        # HTTP server busy，不当作红色失败；交给上层友好提示
        if resp.get("status") == "busy" or "当前已有分析任务" in str(resp):
            raise RuntimeError("BUSY: 当前已有分析任务在运行，请等待完成后再提交。")
        raise RuntimeError(f"Insight server rejected job: {resp}")

    return resp["job_id"]


def get_insight_job(job_id: str) -> dict:
    url = f"{INSIGHT_SERVER}/jobs/{job_id}"
    return http_json("GET", url, timeout=30)


def run_analysis_and_reply(message_id: str, text: str, chat_id: str = ""):
    try:
        skip_fetch = detect_skip_fetch(text)

        reply_message(
            message_id,
            "收到，开始分析这条 TikTok 素材。\n\n预计需要 1–5 分钟。分析完成后我会直接在本话题回复。"
        )

        job_id = submit_insight_job(text, skip_fetch=skip_fetch, chat_id=chat_id)

        deadline = time.time() + 1800
        last_status = ""

        while time.time() < deadline:
            job = get_insight_job(job_id)
            status = job.get("status")

            if status != last_status:
                last_status = status

            if status == "success":
                reply_text = job.get("reply_text", "").strip()
                if not reply_text:
                    reply_text = f"✅ 分析完成，但没有取到 reply_text。\nReport: {job.get('report_path')}"

                # 为每份成功报告统一生成 Report ID，V1.1 / V1.2 都进入历史上下文，支持后续指定报告追问。
                report_id = make_report_id()

                if job.get("report_version") == "v1.2_comment":
                    # V1.2 已经由 make_v12_feishu_short_reply.py 生成飞书短版，
                    # 不再套 V1/V1.1 的 make_feishu_short_reply()，避免标题和结构被改回 V1。
                    reply_text = reply_text.replace("REPORT_ID_PLACEHOLDER", report_id)

                    # 兜底：如果短版里没有 Report ID 行，就补一行。
                    if "本次报告 ID：" not in reply_text:
                        reply_text = reply_text.replace(
                            "✅ TikTok Insight V1.2 评论证据洞察报告",
                            f"✅ TikTok Insight V1.2 评论证据洞察报告\n本次报告 ID：{report_id}",
                            1
                        )
                else:
                    reply_text = make_feishu_short_reply(reply_text)

                    # V1.1: 为每份报告生成 Report ID，方便后续指定历史报告追问。
                    reply_text = reply_text.replace(
                        "✅ TikTok Insight V1 复刻执行报告",
                        f"✅ TikTok Insight V1.1 复刻执行报告\n\n本次报告 ID：{report_id}",
                        1
                    )

                reply_message(message_id, reply_text)

                # 保存最近一次成功报告和历史报告，供同群追问使用
                try:
                    save_last_report_context(
                        chat_id=chat_id,
                        message_id=message_id,
                        report_path=job.get("report_path", ""),
                        reply_text=reply_text,
                        report_id=report_id,
                    )
                except Exception as ctx_e:
                    write_json_log("save_context_error", {
                        "message_id": message_id,
                        "chat_id": chat_id,
                        "report_id": report_id,
                        "error": repr(ctx_e),
                    })

                return

            if status == "failed":
                error = job.get("error") or job.get("reply_text") or "Unknown error"
                reply_message(
                    message_id,
                    "❌ TikTok Insight 分析失败。\n\n"
                    f"Job ID: {job_id}\n"
                    f"错误：{error[:1500]}"
                )
                return

            time.sleep(8)

        reply_message(
            message_id,
            f"❌ TikTok Insight 分析超时。\n\nJob ID: {job_id}\n请稍后重试，或让负责人检查本地服务日志。"
        )

    except Exception as e:
        write_json_log("thread_error", {
            "message_id": message_id,
            "error": repr(e),
            "text_preview": text[:1000],
        })
        try:
            err = repr(e)
            if "BUSY:" in err or "当前已有分析任务" in err:
                reply_message(
                    message_id,
                    "⏳ 当前已有 TikTok Insight 分析任务在运行。\n\n请等上一条完成后再提交，避免重复消耗。"
                )
            else:
                reply_message(
                    message_id,
                    "❌ TikTok Insight Bot 处理失败。\n\n"
                    f"错误：{repr(e)}"
                )
        except Exception as reply_e:
            write_json_log("reply_error", {
                "message_id": message_id,
                "error": repr(reply_e),
            })


class FeishuHandler(BaseHTTPRequestHandler):
    def send_json(self, status_code: int, data: dict):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def read_payload(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw.strip() else {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self.send_json(200, {
                "status": "ok",
                "service": "feishu_tiktok_insight_bot",
                "time": now_ts(),
                "insight_server": INSIGHT_SERVER
            })
            return

        self.send_json(404, {"status": "not_found"})

    def do_POST(self):
        path = urlparse(self.path).path

        if path != "/feishu/events":
            self.send_json(404, {"status": "not_found"})
            return

        try:
            payload = self.read_payload()
            write_json_log("event", payload)

            # 飞书 URL verification
            if "challenge" in payload:
                self.send_json(200, {
                    "challenge": payload["challenge"]
                })
                return

            # v2 event token check
            if VERIFY_TOKEN:
                header_token = payload.get("header", {}).get("token", "")
                old_token = payload.get("token", "")
                incoming_token = header_token or old_token

                if incoming_token and incoming_token != VERIFY_TOKEN:
                    self.send_json(403, {
                        "status": "forbidden",
                        "error": "Invalid verification token"
                    })
                    return

            header = payload.get("header", {})
            event_type = header.get("event_type", "")

            if event_type != "im.message.receive_v1":
                self.send_json(200, {
                    "status": "ignored",
                    "event_type": event_type
                })
                return

            message_id, text = extract_text_message(payload)
            message = payload.get("event", {}).get("message", {})
            chat_id = message.get("chat_id", "")

            if not message_id:
                self.send_json(200, {
                    "status": "ignored",
                    "reason": "missing message_id"
                })
                return

            if is_duplicate_event(payload, message_id):
                self.send_json(200, {
                    "status": "ignored",
                    "reason": "duplicate_event",
                    "message_id": message_id
                })
                return

            if not text:
                reply_message(
                    message_id,
                    "目前只支持文本格式。请按模板发送：市场 / 商品 / 体裁 / 链接 / 分析目标。"
                )
                self.send_json(200, {"status": "ignored", "reason": "non-text"})
                return

            if is_duplicate_content(payload, message_id, text):
                self.send_json(200, {
                    "status": "ignored",
                    "reason": "duplicate_content",
                    "message_id": message_id
                })
                return

            if not should_process_message(text):
                if is_followup_message(text):
                    write_json_log("followup_received", {
                        "message_id": message_id,
                        "chat_id": chat_id,
                        "text_preview": text[:500],
                    })
                    self.send_json(200, {"status": "accepted", "mode": "followup"})
                    t = threading.Thread(
                        target=run_followup_and_reply,
                        args=(message_id, chat_id, text),
                        daemon=True,
                    )
                    t.start()
                    return

                reply_message(
                    message_id,
                    "请按这个格式提交一条素材：\n\n"
                    "市场：DE\n\n"
                    "商品：\n\n"
                    "商品核心卖点：（可选，但建议填）\n\n"
                    "体裁：图文/视频\n\n"
                    "视频/图文链接：\n\n"
                    "分析目标：\n\n"
                    "补充信息：（可选）"
                )
                self.send_json(200, {"status": "ignored", "reason": "template_not_matched"})
                return

            t = threading.Thread(
                target=run_analysis_and_reply,
                args=(message_id, text, chat_id),
                daemon=True
            )
            t.start()

            self.send_json(200, {
                "status": "accepted"
            })

        except Exception as e:
            write_json_log("error", {"error": repr(e)})
            self.send_json(500, {
                "status": "failed",
                "error": repr(e)
            })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), FeishuHandler)

    print("✅ Feishu TikTok Insight Bot server started")
    print(f"Health: http://{args.host}:{args.port}/health")
    print(f"Events: http://{args.host}:{args.port}/feishu/events")
    print(f"Insight server: {INSIGHT_SERVER}")

    server.serve_forever()


if __name__ == "__main__":
    main()
