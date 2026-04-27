
import json
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
RAW_DIR = BASE_DIR / "raw"
REPORT_DIR = BASE_DIR / "reports"
MEDIA_DIR = BASE_DIR / "media"
INPUT_PATH = BASE_DIR / "input_test.json"

MEDIA_DIR.mkdir(exist_ok=True)

VIDEO_URL_KEYS = {
    "videoDownloadNoWatermarkUrl",
    "videoDownloadUrl",
    "downloadAddr",
    "downloadUrl",
    "playAddr",
    "playUrl",
    "videoUrl",
    "webVideoUrl",
    "mediaUrl",
    "mediaUrls",
    "url",
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def cache_key(url: str) -> str:
    import hashlib
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def iter_values(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from iter_values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from iter_values(v)


def looks_like_video_url(value: str) -> bool:
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v.startswith("http"):
        return False

    lower = v.lower()

    if "tiktokcdn" in lower or "muscdn" in lower or "byteoversea" in lower:
        return True

    if any(x in lower for x in [".mp4", "mime_type=video", "video_mp4", "video/tos"]):
        return True

    return False



def collect_candidate_urls(current_key: str):
    candidates = []

    # 只允许当前素材 key 对应的 raw 文件，避免误用历史素材图片/封面
    raw_files = sorted(
        list(RAW_DIR.glob(f"{current_key}*.json")),
        key=lambda x: x.stat().st_mtime,
        reverse=True
    )

    preferred_fields = {
        "videoDownloadNoWatermarkUrl": -5,
        "videoDownloadUrl": -4,
        "videoPlayUrl": -3,
        "videoUrl": -2,
    }

    for f in raw_files:
        try:
            data = read_json(f)
        except Exception:
            continue

        for k, v in iter_values(data):
            key = str(k)

            # 排除字幕、封面、头像、音乐、图片、通用 downloadLink
            low_key = key.lower()
            if any(x in low_key for x in [
                "subtitle", "transcription", "cover", "avatar", "music",
                "image", "photo", "downloadlink"
            ]):
                continue

            # 只收视频字段，不再收泛化 url/downloadLink
            if key not in preferred_fields:
                continue

            values = v if isinstance(v, list) else [v]
            for item in values:
                if isinstance(item, str) and looks_like_video_url(item):
                    candidates.append((preferred_fields[key], str(f), key, item.strip()))

    seen = set()
    out = []
    for priority, source, key, url in sorted(candidates, key=lambda x: x[0]):
        if url in seen:
            continue
        seen.add(url)
        out.append((source, key, url))

    return out

def curl_download(url: str, output_path: Path) -> bool:
    cmd = [
        "curl",
        "-L",
        "--fail",
        "--retry", "3",
        "--retry-delay", "2",
        "--connect-timeout", "8",
        "--max-time", "20",
        "-A", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        "-H", "Referer: https://www.tiktok.com/",
        "-o", str(output_path),
        url,
    ]

    completed = subprocess.run(cmd, text=True, capture_output=True)

    if completed.returncode == 0 and is_valid_video_file(output_path):
        return True

    if completed.stderr:
        print(completed.stderr[-2000:])

    return False


def ytdlp_download(material_url: str, output_path: Path) -> bool:
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-check-certificates",
        "-o",
        str(output_path),
        material_url,
    ]

    completed = subprocess.run(cmd, text=True, capture_output=True)

    if completed.returncode == 0 and is_valid_video_file(output_path):
        return True

    if completed.stdout:
        print(completed.stdout[-2000:])
    if completed.stderr:
        print(completed.stderr[-3000:])

    return False



def is_valid_video_file(path: Path) -> bool:
    if not path.exists() or not path.is_file() or path.stat().st_size < 100000:
        return False

    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name:format=duration,size",
        "-of", "json",
        str(path),
    ]
    probe = subprocess.run(cmd, text=True, capture_output=True)

    if probe.returncode != 0:
        print("ffprobe failed:", probe.stderr[-1000:])
        return False

    try:
        info = json.loads(probe.stdout or "{}")
        duration = float(info.get("format", {}).get("duration") or 0)
        streams = info.get("streams") or []
        codec = streams[0].get("codec_name", "") if streams else ""

        # mjpeg 通常是图片/封面，不是正常 TikTok 视频
        if codec in {"mjpeg", "png", "webp"}:
            print(f"Invalid video codec detected: {codec}")
            return False

        if duration < 1:
            print(f"Invalid video duration: {duration}")
            return False

        return True
    except Exception as e:
        print("ffprobe parse failed:", repr(e))
        return False

def main():
    input_payload = read_json(INPUT_PATH)
    material_url = input_payload.get("material_url", "").strip()
    if not material_url:
        raise RuntimeError("input_test.json missing material_url")

    key = cache_key(material_url)
    output_path = MEDIA_DIR / f"{key}.mp4"

    print("Trying direct video URLs from raw Apify data...")

    candidates = collect_candidate_urls(key)
    print(f"Found candidate video urls: {len(candidates)}")

    # 避免 100+ 个历史 raw 候选逐个尝试导致长时间卡住
    candidates = candidates[:12]

    for source, field, url in candidates:
        print(f"Trying direct url from {source} field={field}")
        if curl_download(url, output_path):
            print(json.dumps({
                "status": "success",
                "method": "curl_direct_url",
                "media_path": str(output_path),
                "source": source,
                "field": field,
                "file_size_bytes": output_path.stat().st_size,
                "canonical_url": material_url,
            }, ensure_ascii=False, indent=2))
            return

    print("Direct URL download failed. Falling back to python -m yt_dlp...")

    if ytdlp_download(material_url, output_path):
        print(json.dumps({
            "status": "success",
            "method": "python_module_yt_dlp",
            "media_path": str(output_path),
            "file_size_bytes": output_path.stat().st_size,
            "canonical_url": material_url,
        }, ensure_ascii=False, indent=2))
        return

    raise RuntimeError("Video download failed: all direct URLs and yt-dlp fallback failed")


if __name__ == "__main__":
    main()
