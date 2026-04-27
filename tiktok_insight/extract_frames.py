import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
INPUT_PATH = BASE_DIR / "input_test.json"
MEDIA_DIR = BASE_DIR / "media"
REPORT_DIR = BASE_DIR / "reports"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def cache_key(url: str) -> str:
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def main():
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Missing input_test.json: {INPUT_PATH}")

    input_payload = read_json(INPUT_PATH)
    material_url = input_payload.get("material_url", "").strip()
    if not material_url:
        raise RuntimeError("input_test.json missing material_url")

    key = cache_key(material_url)
    media_path = MEDIA_DIR / f"{key}.mp4"
    frames_dir = MEDIA_DIR / f"{key}_frames"

    if not media_path.exists():
        raise FileNotFoundError(f"Missing media file: {media_path}")

    if not media_path.is_file():
        raise RuntimeError(f"Media path is not a file: {media_path}")

    if media_path.stat().st_size < 100000:
        raise RuntimeError(f"Media file too small: {media_path} size={media_path.stat().st_size}")

    # 先用 ffprobe 验证视频有效，避免假 mp4 进入 ffmpeg
    probe_cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration,size",
        "-of", "json",
        str(media_path),
    ]
    probe = subprocess.run(probe_cmd, text=True, capture_output=True)
    if probe.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {media_path}: {probe.stderr[-2000:]}")

    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    output_pattern = frames_dir / "frame_%03d.jpg"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(media_path),
        "-vf", "fps=1/5",
        "-q:v", "3",
        str(output_pattern),
    ]

    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)

    frames = sorted(frames_dir.glob("frame_*.jpg"))

    if not frames:
        raise RuntimeError(f"No frames extracted: {frames_dir}")

    # 写回 data_packet，供 make_visual_packet.py 生成 contact sheet 使用
    data_packet_path = REPORT_DIR / f"{key}_data_packet.json"
    if data_packet_path.exists():
        data_packet = read_json(data_packet_path)

        frame_paths = [str(x) for x in frames]

        data_packet["media_path"] = str(media_path)
        data_packet["frames_dir"] = str(frames_dir)
        data_packet["frame_paths"] = frame_paths
        data_packet["video_frame_paths"] = frame_paths
        data_packet["frames"] = frame_paths
        data_packet["video"] = data_packet.get("video") or {}
        data_packet["video"]["media_path"] = str(media_path)
        data_packet["video"]["frames_dir"] = str(frames_dir)
        data_packet["video"]["frame_paths"] = frame_paths

        data_packet_path.write_text(
            json.dumps(data_packet, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        print(f"✅ Wrote frame paths to data packet: {data_packet_path}")
    else:
        print(f"⚠️ data_packet not found, skip writeback: {data_packet_path}")

    print(json.dumps({
        "status": "success",
        "media_path": str(media_path),
        "frames_dir": str(frames_dir),
        "frame_count": len(frames),
        "sampling_rule": "fps=1/5",
        "sample_frames": [str(x) for x in frames[:5]],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
