import json
import hashlib
from pathlib import Path

BASE_DIR = Path(__file__).parent
REPORT_DIR = BASE_DIR / "reports"

def cache_key(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    input_path = BASE_DIR / "input_test.json"
    payload = read_json(input_path)

    material_url = payload["material_url"].strip()
    key = cache_key(material_url)

    data_packet_path = REPORT_DIR / f"{key}_data_packet.json"

    if not data_packet_path.exists():
        raise FileNotFoundError(f"Missing data packet: {data_packet_path}")

    data_packet = read_json(data_packet_path)

    old_input = data_packet.get("input", {})
    data_packet["input"] = payload

    write_json(data_packet_path, data_packet)

    print(json.dumps({
        "status": "success",
        "data_packet_path": str(data_packet_path),
        "old_product": old_input.get("product"),
        "new_product": payload.get("product"),
        "new_core_selling_points": payload.get("product_core_selling_points"),
        "material_url": material_url
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
