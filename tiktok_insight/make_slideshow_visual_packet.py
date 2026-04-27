import json
import hashlib
from pathlib import Path
from PIL import Image, ImageDraw

BASE_DIR = Path(__file__).parent
REPORT_DIR = BASE_DIR / "reports"

def cache_key(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def make_contact_sheet(image_paths, output_path: Path, cols=4, thumb_w=270, thumb_h=480):
    cards = []

    for idx, path in enumerate(image_paths, start=1):
        img = Image.open(path).convert("RGB")
        img.thumbnail((thumb_w, thumb_h))

        canvas = Image.new("RGB", (thumb_w, thumb_h + 38), "white")
        x = (thumb_w - img.width) // 2
        y = (thumb_h - img.height) // 2
        canvas.paste(img, (x, y))

        draw = ImageDraw.Draw(canvas)
        draw.text((10, thumb_h + 10), f"Slide {idx:02d}", fill=(0, 0, 0))

        cards.append(canvas)

    rows = (len(cards) + cols - 1) // cols
    sheet_w = cols * thumb_w
    sheet_h = rows * (thumb_h + 38)

    sheet = Image.new("RGB", (sheet_w, sheet_h), "white")

    for i, card in enumerate(cards):
        row = i // cols
        col = i % cols
        sheet.paste(card, (col * thumb_w, row * (thumb_h + 38)))

    sheet.save(output_path, quality=92)

def main():
    input_path = BASE_DIR / "input_test.json"
    payload = read_json(input_path)

    material_url = payload["material_url"].strip()
    key = cache_key(material_url)

    data_packet_path = REPORT_DIR / f"{key}_data_packet.json"
    data_packet = read_json(data_packet_path)

    image_paths = data_packet.get("slideshow_images", {}).get("image_paths", [])
    image_paths = [Path(p) for p in image_paths if Path(p).exists()]

    if not image_paths:
        raise RuntimeError("No slideshow image paths found. Run download_slideshow_images.py first.")

    output_path = REPORT_DIR / f"{key}_slideshow_contact_sheet.jpg"

    make_contact_sheet(image_paths, output_path)

    data_packet.setdefault("data_availability", {})
    data_packet["data_availability"]["slideshow_visual_packet_available"] = True

    data_packet["visual_packet"] = {
        "type": "slideshow",
        "contact_sheet_path": str(output_path),
        "image_count": len(image_paths),
        "source": "slideshow_images"
    }

    write_json(data_packet_path, data_packet)

    print(json.dumps({
        "status": "success",
        "contact_sheet_path": str(output_path),
        "image_count": len(image_paths)
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
