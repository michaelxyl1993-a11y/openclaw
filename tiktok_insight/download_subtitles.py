import json
import re
import ssl
import hashlib
from pathlib import Path
from urllib.request import Request, urlopen

import certifi

BASE_DIR = Path(__file__).parent
REPORT_DIR = BASE_DIR / "reports"
RAW_DIR = BASE_DIR / "raw"
RAW_DIR.mkdir(exist_ok=True)
REPORT_DIR.mkdir(exist_ok=True)

def cache_key(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def strip_vtt(vtt_text: str) -> str:
    lines = []

    for line in vtt_text.splitlines():
        line = line.strip()

        if not line:
            continue
        if line.upper().startswith("WEBVTT"):
            continue
        if "-->" in line:
            continue
        if re.match(r"^\d+$", line):
            continue
        if line.startswith("NOTE"):
            continue

        # 去掉 VTT 里的简单标签
        line = re.sub(r"<[^>]+>", "", line)
        lines.append(line)

    text = " ".join(lines)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def fetch_text(url: str) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*"
        }
    )

    # 使用 certifi 提供的证书包，解决 macOS Python SSL 证书问题
    ssl_context = ssl.create_default_context(cafile=certifi.where())

    with urlopen(req, timeout=60, context=ssl_context) as resp:
        return resp.read().decode("utf-8", errors="replace")

def main():
    input_path = BASE_DIR / "input_test.json"
    payload = read_json(input_path)

    material_url = payload["material_url"].strip()
    key = cache_key(material_url)

    data_packet_path = REPORT_DIR / f"{key}_data_packet.json"
    data_packet = read_json(data_packet_path)

    subtitle_links = (
        data_packet
        .get("metadata", {})
        .get("video", {})
        .get("subtitle_links")
        or []
    )

    if not subtitle_links:
        print(json.dumps({
            "status": "no_subtitles",
            "message": "No subtitle links found in data packet."
        }, ensure_ascii=False, indent=2))
        return

    results = []

    for idx, item in enumerate(subtitle_links, start=1):
        language = item.get("language") or "unknown"
        source = item.get("source")
        url = item.get("downloadLink") or item.get("url")

        if not url:
            results.append({
                "language": language,
                "source": source,
                "error": "Missing subtitle download URL"
            })
            continue

        try:
            raw_vtt = fetch_text(url)
            clean_text = strip_vtt(raw_vtt)

            safe_language = re.sub(r"[^a-zA-Z0-9_-]+", "_", language)

            raw_path = RAW_DIR / f"{key}_subtitle_{idx}_{safe_language}.vtt"
            txt_path = REPORT_DIR / f"{key}_subtitle_{idx}_{safe_language}.txt"

            raw_path.write_text(raw_vtt, encoding="utf-8")
            txt_path.write_text(clean_text, encoding="utf-8")

            results.append({
                "language": language,
                "source": source,
                "raw_path": str(raw_path),
                "text_path": str(txt_path),
                "text_preview": clean_text[:500],
                "text_length": len(clean_text)
            })

        except Exception as e:
            results.append({
                "language": language,
                "source": source,
                "error": str(e)
            })

    ok_count = sum(1 for r in results if "text_path" in r)

    output = {
        "status": "success" if ok_count > 0 else "failed",
        "subtitle_count": len(results),
        "downloaded_count": ok_count,
        "results": results
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
