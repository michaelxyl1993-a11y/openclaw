import json
import hashlib
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).parent
RAW_DIR = BASE_DIR / "raw"
REPORT_DIR = BASE_DIR / "reports"
REPORT_DIR.mkdir(exist_ok=True)

def cache_key(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))

def pick_first(items: list[dict]) -> dict:
    if not items:
        return {}
    return items[0] if isinstance(items[0], dict) else {}

def simplify_comment(c: dict) -> dict:
    return {
        "text": c.get("text"),
        "like_count": c.get("diggCount"),
        "reply_count": c.get("replyCommentTotal"),
        "liked_by_author": c.get("likedByAuthor"),
        "pinned_by_author": c.get("pinnedByAuthor"),
        "created_at": c.get("createTimeISO"),
        "user_unique_id": c.get("uniqueId"),
    }

def simplify_metadata(m: dict) -> dict:
    author = m.get("authorMeta") or {}
    music = m.get("musicMeta") or {}
    video = m.get("videoMeta") or {}
    hashtags = m.get("hashtags") or []

    return {
        "post_id": m.get("id"),
        "submitted_url": m.get("submittedVideoUrl"),
        "canonical_url": m.get("webVideoUrl"),
        "caption": m.get("text"),
        "text_language": m.get("textLanguage"),
        "created_at": m.get("createTimeISO"),
        "is_slideshow": m.get("isSlideshow"),
        "is_ad": m.get("isAd"),
        "is_pinned": m.get("isPinned"),
        "is_sponsored": m.get("isSponsored"),
        "author": {
            "id": author.get("id"),
            "name": author.get("name"),
            "nickname": author.get("nickName"),
            "profile_url": author.get("profileUrl"),
            "verified": author.get("verified"),
            "followers": author.get("fans"),
            "following": author.get("following"),
            "heart_count": author.get("heart"),
            "video_count": author.get("video"),
        },
        "stats": {
            "play_count": m.get("playCount"),
            "like_count": m.get("diggCount"),
            "comment_count": m.get("commentCount"),
            "share_count": m.get("shareCount"),
            "collect_count": m.get("collectCount"),
            "repost_count": m.get("repostCount"),
        },
        "hashtags": [
            {
                "name": h.get("name"),
                "title": h.get("title"),
                "cover": h.get("cover"),
            }
            for h in hashtags
        ],
        "music": {
            "id": music.get("musicId"),
            "name": music.get("musicName"),
            "author": music.get("musicAuthor"),
            "original": music.get("musicOriginal"),
            "cover_url": music.get("coverMediumUrl"),
            "play_url": music.get("playUrl"),
        },
        "video": {
            "duration": video.get("duration"),
            "width": video.get("width"),
            "height": video.get("height"),
            "format": video.get("format"),
            "definition": video.get("definition"),
            "cover_url": video.get("coverUrl"),
            "original_cover_url": video.get("originalCoverUrl"),
            "download_addr": video.get("downloadAddr"),
            "play_addr": video.get("playAddr"),
            "subtitle_links": video.get("subtitleLinks"),
        },
        "raw_available_fields": sorted(list(m.keys())),
    }

def main():
    input_path = BASE_DIR / "input_test.json"
    payload = read_json(input_path)

    material_url = payload["material_url"].strip()
    key = cache_key(material_url)

    comments_path = RAW_DIR / f"{key}_comments.json"
    metadata_path = RAW_DIR / f"{key}_metadata.json"

    comments = read_json(comments_path)
    metadata_items = read_json(metadata_path)
    metadata = pick_first(metadata_items)

    simplified_comments = [simplify_comment(c) for c in comments if isinstance(c, dict)]
    top_comments = sorted(
        simplified_comments,
        key=lambda x: x.get("like_count") or 0,
        reverse=True
    )[:30]

    data_packet = {
        "input": payload,
        "data_availability": {
            "comments_available": len(simplified_comments) > 0,
            "comments_count_scraped": len(simplified_comments),
            "metadata_available": bool(metadata),
            "media_file_available": False,
            "transcript_available": False,
            "slideshow_images_available": False,
        },
        "metadata": simplify_metadata(metadata),
        "comments": {
            "count": len(simplified_comments),
            "top_comments_by_likes": top_comments,
            "all_comments": simplified_comments,
        },
    }

    output_path = REPORT_DIR / f"{key}_data_packet.json"
    output_path.write_text(
        json.dumps(data_packet, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(json.dumps({
        "status": "success",
        "output_path": str(output_path),
        "comments_count": len(simplified_comments),
        "is_slideshow": data_packet["metadata"].get("is_slideshow"),
        "caption": data_packet["metadata"].get("caption"),
        "canonical_url": data_packet["metadata"].get("canonical_url"),
        "stats": data_packet["metadata"].get("stats"),
        "has_video_download_addr": bool(data_packet["metadata"]["video"].get("download_addr")),
        "has_video_play_addr": bool(data_packet["metadata"]["video"].get("play_addr")),
        "subtitle_links_count": len(data_packet["metadata"]["video"].get("subtitle_links") or []),
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
