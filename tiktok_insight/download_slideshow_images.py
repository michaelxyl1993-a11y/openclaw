import json
import hashlib
import subprocess
from pathlib import Path

import certifi
import requests
from PIL import Image

BASE_DIR = Path(__file__).parent
RAW_DIR = BASE_DIR / "raw"
MEDIA_DIR = BASE_DIR / "media"
REPORT_DIR = BASE_DIR / "reports"

MEDIA_DIR.mkdir(exist_ok=True)
REPORT_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    "Referer": "https://www.tiktok.com/",
}

MIN_VALID_IMAGE_BYTES = 5_000


def cache_key(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_valid_image(path: Path) -> bool:
    if not path.exists():
        return False

    if path.stat().st_size < MIN_VALID_IMAGE_BYTES:
        return False

    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


def pick_image_entries(item: dict):
    entries = []

    slideshow_links = item.get("slideshowImageLinks") or []

    if isinstance(slideshow_links, list):
        for idx, entry in enumerate(slideshow_links, start=1):
            if not isinstance(entry, dict):
                continue

            urls = []

            download_link = entry.get("downloadLink")
            tiktok_link = entry.get("tiktokLink")

            if download_link:
                urls.append(download_link)

            if tiktok_link and tiktok_link not in urls:
                urls.append(tiktok_link)

            if urls:
                entries.append({
                    "index": idx,
                    "source_field": "slideshowImageLinks",
                    "urls": urls
                })

    return entries


def download_with_requests(url: str, output_path: Path):
    with requests.get(
        url,
        headers=HEADERS,
        timeout=(15, 180),
        stream=True,
        allow_redirects=True,
        verify=certifi.where(),
    ) as resp:
        content_type = resp.headers.get("Content-Type", "")
        resp.raise_for_status()

        with output_path.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 512):
                if chunk:
                    f.write(chunk)

    return {
        "method": "requests",
        "content_type": content_type,
        "file_size_bytes": output_path.stat().st_size,
    }


def download_with_curl(url: str, output_path: Path):
    cmd = [
        "curl",
        "-L",
        "--fail",
        "--compressed",
        "--http1.1",
        "-k",
        "--retry", "3",
        "--retry-delay", "2",
        "--connect-timeout", "20",
        "--max-time", "240",
        "-A", HEADERS["User-Agent"],
        "-H", "Referer: https://www.tiktok.com/",
        "-H", "Accept: image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "-o", str(output_path),
        url,
    ]

    subprocess.run(cmd, check=True)

    return {
        "method": "curl",
        "content_type": "unknown",
        "file_size_bytes": output_path.stat().st_size,
    }


def try_download(entry: dict, output_path: Path):
    errors = []

    # 关键：已有有效图片就直接复用，不删除
    if is_valid_image(output_path):
        return {
            "method": "existing_file",
            "content_type": "existing",
            "file_size_bytes": output_path.stat().st_size,
            "source_url": None,
        }

    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")

    for url in entry["urls"]:
        if tmp_path.exists():
            tmp_path.unlink()

        try:
            result = download_with_requests(url, tmp_path)

            if is_valid_image(tmp_path):
                tmp_path.replace(output_path)
                result["file_size_bytes"] = output_path.stat().st_size
                result["source_url"] = url
                return result

            size = tmp_path.stat().st_size if tmp_path.exists() else 0
            errors.append(f"requests invalid image, size={size}, url={url[:160]}")

        except Exception as e:
            errors.append(f"requests failed: {repr(e)}, url={url[:160]}")

        if tmp_path.exists():
            tmp_path.unlink()

        try:
            result = download_with_curl(url, tmp_path)

            if is_valid_image(tmp_path):
                tmp_path.replace(output_path)
                result["file_size_bytes"] = output_path.stat().st_size
                result["source_url"] = url
                return result

            size = tmp_path.stat().st_size if tmp_path.exists() else 0
            errors.append(f"curl invalid image, size={size}, url={url[:160]}")

        except Exception as e:
            errors.append(f"curl failed: {repr(e)}, url={url[:160]}")

        if tmp_path.exists():
            tmp_path.unlink()

    # 再兜底一次：如果旧文件还在，就复用
    if is_valid_image(output_path):
        return {
            "method": "existing_file_after_failed_download",
            "content_type": "existing",
            "file_size_bytes": output_path.stat().st_size,
            "source_url": None,
        }

    raise RuntimeError("; ".join(errors))


def main():
    input_path = BASE_DIR / "input_test.json"
    payload = read_json(input_path)

    material_url = payload["material_url"].strip()
    key = cache_key(material_url)

    metadata_path = RAW_DIR / f"{key}_metadata.json"
    data_packet_path = REPORT_DIR / f"{key}_data_packet.json"

    if not metadata_path.exists():
        raise FileNotFoundError(f"Missing metadata file: {metadata_path}")

    if not data_packet_path.exists():
        raise FileNotFoundError(f"Missing data packet: {data_packet_path}")

    items = read_json(metadata_path)
    item = items[0] if isinstance(items, list) and items else items

    image_entries = pick_image_entries(item)

    if not image_entries:
        raise RuntimeError("No slideshow image links found in metadata.")

    images_dir = MEDIA_DIR / f"{key}_slideshow"
    images_dir.mkdir(exist_ok=True)

    downloaded = []
    failed = []

    for entry in image_entries:
        idx = entry["index"]
        output_path = images_dir / f"slide_{idx:02d}.jpg"

        try:
            result = try_download(entry, output_path)

            downloaded.append({
                "index": idx,
                "local_path": str(output_path),
                "source_field": entry["source_field"],
                "method": result.get("method"),
                "content_type": result.get("content_type"),
                "file_size_bytes": result.get("file_size_bytes"),
                "source_url": result.get("source_url"),
            })

        except Exception as e:
            failed.append({
                "index": idx,
                "error": repr(e),
                "urls": [u[:300] for u in entry.get("urls", [])]
            })

    debug_path = images_dir / f"{key}_slideshow_download_debug.json"
    debug_path.write_text(json.dumps({
        "expected_count": len(image_entries),
        "downloaded_count": len(downloaded),
        "failed_count": len(failed),
        "failed": failed
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    # 关键：如果没拿齐，直接失败，不要继续生成错误的一图报告
    if len(downloaded) < len(image_entries):
        print(json.dumps({
            "status": "failed",
            "reason": "Not all slideshow images were downloaded.",
            "expected_count": len(image_entries),
            "downloaded_count": len(downloaded),
            "failed_count": len(failed),
            "debug_path": str(debug_path),
            "downloaded": [x["local_path"] for x in downloaded],
            "failed_sample": failed[:3]
        }, ensure_ascii=False, indent=2))

        raise RuntimeError(
            f"Slideshow image download incomplete: {len(downloaded)}/{len(image_entries)}"
        )

    data_packet = read_json(data_packet_path)

    data_packet.setdefault("data_availability", {})
    data_packet["data_availability"]["slideshow_images_available"] = True

    data_packet["slideshow_images"] = {
        "images_dir": str(images_dir),
        "image_count": len(downloaded),
        "source_field": "slideshowImageLinks",
        "image_paths": [x["local_path"] for x in downloaded],
        "images": downloaded
    }

    write_json(data_packet_path, data_packet)

    print(json.dumps({
        "status": "success",
        "images_dir": str(images_dir),
        "image_count": len(downloaded),
        "sample_images": [x["local_path"] for x in downloaded[:6]],
        "failed_count": len(failed),
        "debug_path": str(debug_path)
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
