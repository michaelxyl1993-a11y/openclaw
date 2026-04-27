import os
import json
import base64
import hashlib
from pathlib import Path

from openai import OpenAI

BASE_DIR = Path(__file__).parent
REPORT_DIR = BASE_DIR / "reports"

def cache_key(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def encode_image_as_data_url(image_path: Path) -> str:
    suffix = image_path.suffix.lower()
    if suffix in [".jpg", ".jpeg"]:
        mime = "image/jpeg"
    elif suffix == ".png":
        mime = "image/png"
    elif suffix == ".webp":
        mime = "image/webp"
    else:
        raise ValueError(f"Unsupported image type: {suffix}")

    data = image_path.read_bytes()
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def main():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY. Please run: export OPENAI_API_KEY='your_key'")

    model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

    input_path = BASE_DIR / "input_test.json"
    payload = read_json(input_path)

    material_url = payload["material_url"].strip()
    key = cache_key(material_url)

    prompt_path = REPORT_DIR / f"{key}_analysis_prompt.md"
    data_packet_path = REPORT_DIR / f"{key}_data_packet.json"

    if not prompt_path.exists():
        raise FileNotFoundError(f"Missing analysis prompt: {prompt_path}")

    if not data_packet_path.exists():
        raise FileNotFoundError(f"Missing data packet: {data_packet_path}")

    data_packet = read_json(data_packet_path)
    contact_sheet_path = Path(
        data_packet
        .get("visual_packet", {})
        .get("contact_sheet_path", "")
    )

    if not contact_sheet_path.exists():
        raise FileNotFoundError(f"Missing contact sheet: {contact_sheet_path}")

    prompt_text = prompt_path.read_text(encoding="utf-8")
    image_data_url = encode_image_as_data_url(contact_sheet_path)

    client = OpenAI(api_key=api_key)

    print(f"Using model: {model}")
    print(f"Prompt: {prompt_path}")
    print(f"Image: {contact_sheet_path}")

    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": prompt_text
                    },
                    {
                        "type": "input_image",
                        "image_url": image_data_url,
                        "detail": "high"
                    }
                ]
            }
        ],
    )

    report_text = response.output_text

    output_path = REPORT_DIR / f"{key}_report.md"
    output_path.write_text(report_text, encoding="utf-8")

    print(json.dumps({
        "status": "success",
        "model": model,
        "report_path": str(output_path),
        "report_chars": len(report_text),
        "preview": report_text[:1000]
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
