#!/usr/bin/env python3
"""Repair only S01E08 clip 05's duplicate-Lin-Qian identity error, once."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from base64 import b64decode
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image, ImageOps

ROOT = Path.cwd()
SOURCE = ROOT / "references/s1e06"
OUTPUT = ROOT / "output/s1e08-clip05-identity-repair"
RUNTIME = OUTPUT / "runtime_refs"
RAW = OUTPUT / "raw"
AUDIT = OUTPUT / "audit"
PROOF = OUTPUT / "proof"
CHART = ROOT / "references/s1e03/source_refs/character_chart_highres.jpeg"
VIDEO_REFERENCE = SOURCE / "repair/clip05_correct_prefix_reference.mp4"
PANEL_FILES = [SOURCE / f"panels/clip_05_shot_{index}.jpg.b64" for index in range(1, 5)]
IDENTITY_CROPS = {"lin_qian": (208, 245, 408, 661), "xu_wei": (616, 245, 819, 661)}

def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()

def dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)

def check_image(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < 5_000:
        raise RuntimeError(f"Invalid image reference: {path}")
    with Image.open(path) as image:
        width, height = image.size
        image.verify()
    if width < 200 or height < 200:
        raise RuntimeError(f"Image reference too small: {path}")

def prepare_images() -> list[Path]:
    refs: list[Path] = []
    for index, encoded in enumerate(PANEL_FILES, start=1):
        if not encoded.is_file():
            raise RuntimeError(f"Missing storyboard panel: {encoded}")
        target = RUNTIME / f"clip05_shot_{index}.jpg"
        target.write_bytes(b64decode(encoded.read_text(encoding="ascii"), validate=True))
        check_image(target)
        refs.append(target)
    check_image(CHART)
    with Image.open(CHART) as chart:
        rgb = chart.convert("RGB")
        for name in ("xu_wei", "lin_qian"):
            target = RUNTIME / f"identity_{name}.jpg"
            ImageOps.fit(rgb.crop(IDENTITY_CROPS[name]), (320, 480), Image.Resampling.LANCZOS).save(target, quality=95)
            check_image(target)
            refs.append(target)
    return refs

def check_video_reference() -> None:
    if not VIDEO_REFERENCE.is_file() or VIDEO_REFERENCE.stat().st_size < 300_000:
        raise RuntimeError("Correct-prefix video reference is missing or invalid")
    probe = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(VIDEO_REFERENCE)]).stdout)
    duration = float(probe.get("format", {}).get("duration") or 0)
    if not 3.4 <= duration <= 3.9:
        raise RuntimeError(f"Unexpected prefix reference duration: {duration}")

def upload(client: Any, path: Path) -> str:
    result = client.files.upload(path)
    urls = result.get("file_urls") if isinstance(result, dict) else None
    if not urls or not isinstance(urls[0], str):
        raise RuntimeError(f"Reference upload failed: {path}")
    return urls[0]

def collect_urls(value: Any, output: list[str]) -> None:
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        output.append(value)
    elif isinstance(value, dict):
        for child in value.values():
            collect_urls(child, output)
    elif isinstance(value, list):
        for child in value:
            collect_urls(child, output)

def fetch_video(result: Any, target: Path) -> str:
    import requests
    urls: list[str] = []
    collect_urls(result.get("output", result) if isinstance(result, dict) else result, urls)
    for url in dict.fromkeys(urls):
        response = requests.get(url, timeout=300)
        response.raise_for_status()
        data = response.content
        if data[4:8] == b"ftyp" or "video/" in response.headers.get("content-type", "").lower() or Path(urlparse(url).path).suffix.lower() in {".mp4", ".mov", ".webm"}:
            target.write_bytes(data)
            return url
    raise RuntimeError("Provider returned no repair video")

def prompt() -> str:
    return """ORIGINAL SERIES VIDEO-CORRECTION LOCK. Repair one five-second 16:9 2D manga-cinema clip from 《吸血法医·剑刺》. This is S01E08 clip 05, the cold trace-evidence laboratory. Preserve the accepted cold blue-black lighting, camera axis, microscope, sealed glass preparations, fine ink linework, restrained cel shading and realistic forensic handling.

The supplied video is the accepted correct first 3.65 seconds and controls motion, lighting, lens and geography. Storyboard images 1-4 control the exact four-shot chronology. Image 5 is the absolute Xu Wei identity. Image 6 is the absolute Lin Qian identity.

EXACT TIMING:
0.00-1.20: Xu Wei, and only Xu Wei, places two separately sealed glass preparations on the trace bench.
1.20-2.25: objective macro of the two distinct samples.
2.25-3.85: Xu Wei compares them at the microscope, brown high ponytail and olive forensic coverall unchanged.
3.85-5.00: match the fourth storyboard panel exactly: Xu Wei remains on the right foreground beside the microscope and evidence, brown high ponytail and olive coverall; exactly one Lin Qian stands on the left background observing, chin-length black bob and navy police uniform.

ABSOLUTE IDENTITY FIX: Never transform Xu Wei into Lin Qian. Never place two Lin Qians in the frame. Never create twins, duplicates, reflections resembling a second person, face swaps or wardrobe swaps. There are exactly two women in the final shot: one Xu Wei foreground/right and one Lin Qian background/left. Xu Wei is the only speaking character and makes one restrained natural mouth movement for the Mandarin line “袖口玻璃，与现场碎片相符。” Lin Qian does not speak.

No generated audio is required; original accepted audio will be retained in post. Do not render a header, subtitle, caption, logo, watermark, readable report, UI, comic grid, split screen or border. No live action, photoreal, 3D, chibi, camera shake, extra people, distorted hands, bare-hand evidence, gore or supernatural effect."""

def main() -> None:
    for directory in (RUNTIME, RAW, AUDIT, PROOF):
        directory.mkdir(parents=True, exist_ok=True)
    if not os.environ.get("SEGMIND_API_KEY"):
        raise RuntimeError("SEGMIND_API_KEY is missing; no paid request made")
    check_video_reference()
    image_refs = prepare_images()
    from segmind import SegmindClient
    client = SegmindClient()
    request = {
        "episode": "S01E08", "clip": "05",
        "repair": "duplicate Lin Qian -> Xu Wei foreground/right + one Lin Qian background/left",
        "request_count": 1, "automatic_retries": 0, "status": "uploading_references",
        "started_at": stamp(), "image_references": [str(path) for path in image_refs],
        "video_reference": str(VIDEO_REFERENCE),
    }
    dump(AUDIT / "request.json", request)
    text = prompt()
    (AUDIT / "prompt.txt").write_text(text, encoding="utf-8")
    image_urls = [upload(client, path) for path in image_refs]
    video_url = upload(client, VIDEO_REFERENCE)
    job = client.submit_async("seedance-2.0-mini", prompt=text, reference_images=image_urls,
        reference_videos=[video_url], duration=5, resolution="480p", aspect_ratio="16:9",
        generate_audio=False, bitrate_mode="high", return_last_frame=True, seed=202608805)
    request.update({"request_id": job.request_id, "status": "processing"})
    dump(AUDIT / "request.json", request)
    result = job.wait(timeout=1800, interval=5)
    dump(AUDIT / "result.json", result)
    video = RAW / "S1E08_clip_05_identity_repair_raw.mp4"
    request["output_url"] = fetch_video(result, video)
    probe = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)]).stdout)
    streams = probe.get("streams", [])
    visual = [item for item in streams if item.get("codec_type") == "video"]
    duration = float(probe.get("format", {}).get("duration") or 0)
    if video.stat().st_size < 200_000 or not visual or not 4.3 <= duration <= 5.8:
        raise RuntimeError("Repair video failed technical QC")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-vf", "fps=0.8,scale=432:248,tile=4x1", "-frames:v", "1", str(PROOF / "clip05_repair_contact.jpg")])
    request.update({"status": "completed", "completed_at": stamp(), "duration": duration,
        "width": visual[0].get("width"), "height": visual[0].get("height"), "video_sha256": sha(video)})
    dump(AUDIT / "request.json", request)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
