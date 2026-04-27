import json
import re
import hashlib
from pathlib import Path

BASE_DIR = Path(__file__).parent
REPORT_DIR = BASE_DIR / "reports"

def cache_key(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path: Path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def infer_language_from_filename(path: Path) -> str:
    m = re.search(r"_subtitle_\d+_(.+)\.txt$", path.name)
    return m.group(1) if m else "unknown"

def choose_best_transcript(transcripts: list[dict], market: str) -> dict | None:
    if not transcripts:
        return None

    market = (market or "").upper()

    preferred = {
        "DE": ["deu-DE", "de-DE", "de", "ger", "deu"],
        "FR": ["fra-FR", "fr-FR", "fr", "fre", "fra"],
        "US": ["eng-US", "en-US", "en", "eng"],
        "UK": ["eng-GB", "en-GB", "eng-US", "en-US", "en", "eng"],
    }.get(market, [])

    for lang in preferred:
        for t in transcripts:
            if lang.lower() in t["language"].lower():
                return t

    # 如果没有匹配市场语言，优先选最长的，因为通常信息更完整
    return sorted(transcripts, key=lambda x: x.get("text_length", 0), reverse=True)[0]

def main():
    input_path = BASE_DIR / "input_test.json"
    payload = read_json(input_path)

    material_url = payload["material_url"].strip()
    market = payload.get("market", "")

    key = cache_key(material_url)
    data_packet_path = REPORT_DIR / f"{key}_data_packet.json"

    if not data_packet_path.exists():
        raise FileNotFoundError(f"Missing data packet: {data_packet_path}")

    data_packet = read_json(data_packet_path)

    subtitle_files = sorted(REPORT_DIR.glob(f"{key}_subtitle_*.txt"))

    transcripts = []

    for path in subtitle_files:
        text = path.read_text(encoding="utf-8").strip()
        language = infer_language_from_filename(path)

        transcripts.append({
            "language": language,
            "text_path": str(path),
            "text_length": len(text),
            "text": text
        })

    best = choose_best_transcript(transcripts, market)

    data_packet["data_availability"]["transcript_available"] = bool(best)
    data_packet["transcripts"] = {
        "count": len(transcripts),
        "available_languages": [t["language"] for t in transcripts],
        "best_transcript_language": best["language"] if best else None,
        "best_transcript_text": best["text"] if best else None,
        "all_transcripts": transcripts,
    }

    write_json(data_packet_path, data_packet)

    print(json.dumps({
        "status": "success",
        "data_packet_path": str(data_packet_path),
        "transcript_count": len(transcripts),
        "available_languages": [t["language"] for t in transcripts],
        "best_transcript_language": best["language"] if best else None,
        "best_transcript_preview": best["text"][:500] if best else None,
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
