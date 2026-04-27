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
    payload = json.loads((BASE_DIR / "input_test.json").read_text(encoding="utf-8"))
    material_url = payload["material_url"].strip()
    key = cache_key(material_url)

    client = ApifyClient(APIFY_TOKEN)

    actor_id = "happy_b/tiktok-video-scraper"

    candidate_inputs = [
        {"urls": [material_url]},
        {"videoUrls": [material_url]},
        {"postURLs": [material_url]},
        {"startUrls": [{"url": material_url}]}
    ]

    last_error = None

    for idx, run_input in enumerate(candidate_inputs, start=1):
        print(f"\nTrying input schema #{idx}:")
        print(json.dumps(run_input, ensure_ascii=False, indent=2))

        try:
            run = client.actor(actor_id).call(run_input=run_input)
            run_status = run.get("status")
            dataset_id = run.get("defaultDatasetId")

            if run_status != "SUCCEEDED":
                print("Run status:", run_status)
                print(json.dumps(run, ensure_ascii=False, indent=2))
                continue

            items = client.dataset(dataset_id).list_items().items

            if not items:
                print("No items returned.")
                continue

            output_path = RAW_DIR / f"{key}_downloader_happy_b.json"
            output_path.write_text(
                json.dumps(items, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

            field_names = sorted(list(items[0].keys())) if isinstance(items[0], dict) else []

            print(json.dumps({
                "status": "success",
                "actor_id": actor_id,
                "schema_index": idx,
                "dataset_id": dataset_id,
                "items_count": len(items),
                "field_names": field_names,
                "output_path": str(output_path),
                "sample": items[:1]
            }, ensure_ascii=False, indent=2))

            return

        except Exception as e:
            last_error = e
            print("Failed with error:", str(e))

    raise RuntimeError(f"All candidate input schemas failed. Last error: {last_error}")

if __name__ == "__main__":
    main()
