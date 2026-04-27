import os
import json
import hashlib
from pathlib import Path
from apify_client import ApifyClient

BASE_DIR = Path(__file__).parent
RAW_DIR = BASE_DIR / "raw"
RAW_DIR.mkdir(exist_ok=True)

APIFY_TOKEN = os.environ.get("APIFY_TOKEN")

if not APIFY_TOKEN:
    raise RuntimeError("Missing APIFY_TOKEN. Please run: export APIFY_TOKEN='your_token'")

def cache_key(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def main():
    input_path = BASE_DIR / "input_test.json"
    payload = json.loads(input_path.read_text(encoding="utf-8"))

    material_url = payload["material_url"].strip()

    if not material_url.startswith("http"):
        raise ValueError(f"Invalid material_url: {material_url}")

    client = ApifyClient(APIFY_TOKEN)

    actor_id = "clockworks/tiktok-scraper"

    run_input = {
        "postURLs": [material_url],
        "resultsPerPage": 1,
        "shouldDownloadVideos": False,
        "shouldDownloadCovers": False,
        "shouldDownloadSubtitles": False
    }

    print("Running Apify actor:", actor_id)
    print("Target URL:", material_url)

    run = client.actor(actor_id).call(run_input=run_input)

    run_status = run.get("status")
    dataset_id = run.get("defaultDatasetId")

    if run_status != "SUCCEEDED":
        print(json.dumps(run, ensure_ascii=False, indent=2))
        raise RuntimeError(f"Apify actor failed. status={run_status}")

    items = client.dataset(dataset_id).list_items().items

    if items and isinstance(items[0], dict):
        if items[0].get("errorCode") or items[0].get("error"):
            print(json.dumps(items[0], ensure_ascii=False, indent=2))
            raise RuntimeError("Apify returned an error item. Please check the TikTok URL or actor input schema.")

    key = cache_key(material_url)
    output_path = RAW_DIR / f"{key}_metadata.json"

    output_path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    field_names = sorted(list(items[0].keys())) if items and isinstance(items[0], dict) else []

    result = {
        "status": "success",
        "actor_id": actor_id,
        "run_status": run_status,
        "dataset_id": dataset_id,
        "items_count": len(items),
        "field_names": field_names,
        "output_path": str(output_path),
        "sample": items[:1]
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
