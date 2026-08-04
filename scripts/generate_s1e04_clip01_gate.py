#!/usr/bin/env python3
"""One-shot S1E04 clip-01 generation gate.

The paid API submission occurs in exactly one statement.  Preparation may be
run freely, while generation stops on the first failed request and never
retries.  Generated text is prohibited; the header and bilingual subtitles are
applied only after all twelve clips have passed visual and Mandarin-audio QC.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


ROOT = Path.cwd()
SOURCE = ROOT / "references" / "s1e04"
PLAN_PATH = SOURCE / "clip01_gate_plan.json"
OUTPUT = Path(os.environ.get("GENERATION_OUTPUT_DIR", "output/s1e04-clip01-gate"))
if not OUTPUT.is_absolute():
    OUTPUT = ROOT / OUTPUT
RUNTIME = OUTPUT / "runtime_refs"
RAW = OUTPUT / "raw"
AUDIT = OUTPUT / "audit"
PROOF = OUTPUT / "proof"
LAST = OUTPUT / "last_frames"
BOARD_SIZE = (1672, 941)

CHARACTERS = {
    "jian_ci": "检刺 / Jian Ci: tall slim pale Chinese male forensic doctor, sharp angular narrow face, layered short side-part black hair, white forensic coat over a black high-neck shirt, black gloves, no glasses.",
    "lin_qian": "林浅 / Lin Qian: adult Chinese female police investigator, chin-length straight black bob, calm alert expression, fitted dark-navy field uniform, black gloves and utility belt.",
    "chen_mo": "陈沫 / Chen Mo: living Chinese woman around thirty, shoulder-length rain-wet black hair, deep-brown long coat over ivory blouse, black trousers and dark shoes. Her neck is completely intact and uninjured; blood exists only on the outer blouse collar.",
}


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-only", action="store_true")
    return parser.parse_args()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(path: Path) -> str:
    data = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            data.update(chunk)
    return data.hexdigest()


def write_json(path: Path, content: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def source(relative: str) -> Path:
    path = (SOURCE / relative).resolve()
    if SOURCE.resolve() not in path.parents or not path.is_file():
        raise RuntimeError(f"Missing locked source: {relative}")
    return path


def load() -> tuple[dict[str, Any], dict[str, Any]]:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    expected = {
        "episode": "S1E04", "model": "seedance-2.0-mini",
        "duration_seconds_per_clip": 5, "clip_count": 1, "shots_per_clip": 4,
        "resolution": "480p", "aspect_ratio": "16:9", "generate_audio": True,
        "bitrate_mode": "high", "automatic_retries": 0,
    }
    for key, value in expected.items():
        if plan.get(key) != value:
            raise RuntimeError(f"Plan is not locked: {key}")
    clip = plan.get("clip")
    if not isinstance(clip, dict) or clip.get("id") != "01":
        raise RuntimeError("Gate plan must contain only clip 01")
    if len(clip.get("shots", [])) != 4 or not clip.get("previous_frame"):
        raise RuntimeError("Clip 01 must be a four-shot continuity gate")
    for line in clip.get("dialogue", []):
        if not 0 <= float(line["start"]) < float(line["end"]) <= 5:
            raise RuntimeError("Invalid dialogue timing")
    required = [
        "gate/clip01_shot1.jpg", "gate/clip01_shot2.jpg",
        "gate/clip01_shot3.jpg", "gate/clip01_shot4.jpg",
        "gate/s1e03_last_frame.jpg",
    ]
    for relative in required:
        source(relative)
    return plan, clip


def panel(image: Image.Image, position: int) -> Image.Image:
    row, column = divmod(position - 1, 2)
    x0 = round(column * image.width / 2) + 4
    x1 = round((column + 1) * image.width / 2) - 4
    y0 = round(row * image.height / 2) + 4
    y1 = round((row + 1) * image.height / 2) - 4
    crop = image.crop((x0, y0, x1, y1)).convert("RGB")
    crop = crop.filter(ImageFilter.UnsharpMask(radius=1.0, percent=130, threshold=2))
    crop = ImageEnhance.Contrast(crop).enhance(1.08)
    return ImageOps.fit(crop, (640, 360), Image.Resampling.LANCZOS)


def make_identity(images: list[Image.Image], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", (960, 720), (3, 7, 12))
    for index, image in enumerate(images[:2]):
        fitted = ImageOps.fit(image.convert("RGB"), (480, 720), Image.Resampling.LANCZOS)
        canvas.paste(fitted, (index * 480, 0))
    canvas.save(target, quality=97)


def prepare(plan: dict[str, Any], clip: dict[str, Any]) -> dict[str, Path]:
    for directory in (RUNTIME, RAW, AUDIT, PROOF, LAST):
        directory.mkdir(parents=True, exist_ok=True)
    panels = [source(f"gate/clip01_shot{index}.jpg") for index in range(1, 5)]
    for index, item in enumerate(panels, start=1):
        with Image.open(item) as image:
            if image.size != (640, 360):
                raise RuntimeError(f"Invalid gate storyboard crop: {item}")
            image.verify()
    identities: dict[str, Path] = {}
    jian = ROOT / "references" / "s1e03" / "source_refs" / "jian_ci_identity.jpg"
    if not jian.is_file():
        raise RuntimeError("Locked Jian Ci identity reference is missing")
    identities["jian_ci"] = jian
    chart_path = ROOT / "references" / "s1e03" / "source_refs" / "character_chart_highres.jpeg"
    if not chart_path.is_file():
        raise RuntimeError("Locked character chart is missing")
    chart = Image.open(chart_path).convert("RGB")
    # The second column of the locked character chart is Lin Qian.
    lin_crop = chart.crop((208, 245, 408, 661))
    lin = RUNTIME / "identity_lin_qian.jpg"
    make_identity([lin_crop], lin)
    identities["lin_qian"] = lin
    chen = RUNTIME / "identity_chen_mo.jpg"
    make_identity([Image.open(panels[1]).convert("RGB"), Image.open(panels[2]).convert("RGB")], chen)
    identities["chen_mo"] = chen
    previous = source("gate/s1e03_last_frame.jpg")
    for file in [*panels, *identities.values(), previous]:
        with Image.open(file) as image:
            width, height = image.size
            image.verify()
        if width < 300 or height < 300 or file.stat().st_size > 30 * 1024 * 1024:
            raise RuntimeError(f"Invalid reference: {file}")
    write_json(AUDIT / "preflight.json", {
        "created_at": now(), "paid_requests": 0, "plan_sha256": digest(PLAN_PATH),
        "sources": {str(path.relative_to(ROOT)): digest(path) for path in [*panels, previous, jian, chart_path]},
        "reference_count": 8, "rule": "Four storyboard panels + 3 identities + accepted S1E03 final frame."
    })
    return {**identities, "previous": previous}


def prompt(plan: dict[str, Any], clip: dict[str, Any], refs: dict[str, Path]) -> str:
    dialogue = "\n".join(f"{line['start']:.2f}-{line['end']:.2f} {line['speaker']}: {line['zh']}" for line in clip["dialogue"])
    shots = "\n".join(f"{i + 1}. {value}" for i, value in enumerate(clip["shots"]))
    profiles = "\n".join(CHARACTERS[name] for name in clip["characters"])
    return f"""
ORIGINAL SERIES PRODUCTION LOCK. Render one clean five-second 16:9 animated
clip for {plan['series_title_zh']} S1E04《{plan['episode_title_zh']}》, clip 01
of 12. It is an original dark forensic manga-noir series based only on the
user's own storyboard and character references. Do not imitate a named artist,
studio, franchise, or copyrighted character.

ABSOLUTE STORYBOARD RULE. Render exactly four full-screen cinematic shots in
the exact reference order and timing below with ordinary hard cuts. References
1-4 are the four storyboard panels, reference 5 is Jian Ci identity, reference
6 is Lin Qian identity, reference 7 is Chen Mo identity, and reference 8 is
the accepted S1E03 final-frame continuity reference. Reference 8 controls only
opening lighting and screen direction. Every shot fills the frame. Never show a
grid, page, panel, split screen, collage, border, UI, title, subtitle, logo,
watermark, readable sign, or generated text.

EXACT FOUR SHOTS:
{shots}

IDENTITY LOCK:
{profiles}
Preserve faces, hair, clothing, scale and props. Chen Mo must be upright,
conscious, full-body visible in shot 2, with a completely uninjured neck. Blood
is only on the outside of her ivory blouse collar. No face swaps, duplicates,
extra people or wardrobe changes.

LOOK AND DIRECTION. {clip['scene']}. The storyboard controls only the four
shot actions, framing and props; it must NOT control paint texture or turn the
video into a concept-art poster. Match the accepted earlier episodes: clean
mature Japanese 2D cinematic animation, crisp thin ink linework, restrained
cel shading with realistic cinematic light falloff, natural depth and subtle
live camera movement. Keep cold blue-grey low saturation and rain-dark
surfaces, but use clean animated line edges and coherent moving space. Never
use oil paint, thick painterly brush texture, key-visual poster rendering,
static illustration, graphic-novel hatching, frozen character pose, a separate
monitor illustration, or an exaggerated black vignette. Cinematic crime
direction: stable camera axis, motivated medium / full body / macro / monitor
progression, restrained parallax, natural blink/breath movement, no shake or
spin.
Gloved evidence handling and sealed chain of custody only. No gore.

MANDARIN AUDIO LOCK. Generate synchronized native Mandarin audio. Speak only
this exact line, clear and audible above restrained rain-room ambience. No
English, no other dialogue, no music, no silence:
{dialogue}
Do not generate visible subtitles; clear Chinese and English subtitles plus the
persistent episode header are added deterministically in post after QC.

STRICT NEGATIVE: {plan['global_negative']}
""".strip()


def upload(client: Any, path: Path) -> str:
    response = client.files.upload(path)
    urls = response.get("file_urls") if isinstance(response, dict) else None
    if not urls or not isinstance(urls[0], str):
        raise RuntimeError(f"Reference upload failed: {path}")
    return urls[0]


def urls(value: Any, result: list[str]) -> None:
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        result.append(value)
    elif isinstance(value, dict):
        for child in value.values():
            urls(child, result)
    elif isinstance(value, list):
        for child in value:
            urls(child, result)


def download(result: Any, target: Path) -> str:
    import requests
    candidates: list[str] = []
    urls(result.get("output", result) if isinstance(result, dict) else result, candidates)
    for url in dict.fromkeys(candidates):
        response = requests.get(url, timeout=300)
        response.raise_for_status()
        video = response.content
        suffix = Path(urlparse(url).path).suffix.lower()
        if video[4:8] == b"ftyp" or "video/" in response.headers.get("content-type", "").lower() or suffix in {".mp4", ".mov", ".webm"}:
            target.write_bytes(video)
            return url
    raise RuntimeError("Provider returned no downloadable video")


def qc(video: Path, expected: list[dict[str, Any]]) -> dict[str, Any]:
    if video.stat().st_size < 200_000:
        raise RuntimeError("Generated clip is unexpectedly small")
    probe = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)]).stdout)
    streams = probe.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    duration = float(probe.get("format", {}).get("duration") or 0)
    if not videos or not audios or not 4.3 <= duration <= 5.8:
        raise RuntimeError("Video/audio stream or duration QC failed")
    loudness = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vn", "-af", "volumedetect", "-f", "null", "-"], check=False, capture_output=True, text=True)
    volume = re.search(r"max_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB", loudness.stderr)
    if not volume or volume.group(1) == "-inf" or float(volume.group(1)) < -55:
        raise RuntimeError("Audio is silent or too quiet")
    from faster_whisper import WhisperModel
    model = WhisperModel("tiny", device="cpu", compute_type="int8", download_root=os.environ.get("WHISPER_CACHE_DIR", "whisper_cache"))
    iterator, info = model.transcribe(str(video), language="zh", task="transcribe", beam_size=1, vad_filter=True, condition_on_previous_text=False)
    segments = [{"start": float(s.start), "end": float(s.end), "text": s.text.strip()} for s in iterator if s.text.strip()]
    transcript = "".join(item["text"] for item in segments)
    seconds = sum(item["end"] - item["start"] for item in segments)
    if seconds < 0.4 or len(re.findall(r"[\u3400-\u9fff]", transcript)) < 2:
        raise RuntimeError("Mandarin ASR QC failed")
    write_json(AUDIT / "clip01_speech.json", {"reported_language": getattr(info, "language", None), "transcript": transcript, "speech_seconds": seconds, "expected": [x["zh"] for x in expected]})
    write_json(AUDIT / "clip01_ffprobe.json", probe)
    (AUDIT / "clip01_loudness.txt").write_text(loudness.stderr, encoding="utf-8")
    return {"duration": duration, "width": videos[0].get("width"), "height": videos[0].get("height"), "audio_codec": audios[0].get("codec_name"), "max_volume_db": float(volume.group(1)), "asr": transcript}


def proof(video: Path) -> Path:
    continuity = LAST / "clip01_continuity.jpg"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "4.70", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(continuity)])
    contact = PROOF / "clip01_four_shot_contact.jpg"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-vf", "fps=0.8,scale=427:240:force_original_aspect_ratio=decrease,pad=427:240:(ow-iw)/2:(oh-ih)/2:black,tile=4x1:padding=4:margin=4", "-frames:v", "1", "-q:v", "2", str(contact)])
    return continuity


def main() -> None:
    options = args()
    plan, clip = load()
    refs = prepare(plan, clip)
    ordered = [*(source(f"gate/clip01_shot{i}.jpg") for i in range(1, 5)), refs["jian_ci"], refs["lin_qian"], refs["chen_mo"], refs["previous"]]
    text = prompt(plan, clip, refs)
    (AUDIT / "clip01_prompt.txt").write_text(text, encoding="utf-8")
    if options.prepare_only:
        print("S1E04 clip 01 preflight passed; no paid request made.")
        return
    if not os.environ.get("SEGMIND_API_KEY"):
        raise RuntimeError("SEGMIND_API_KEY is missing; no paid request made")
    from segmind import SegmindClient
    client = SegmindClient()
    request = {"episode": "S1E04", "clip": "01", "request_count": 0, "automatic_retries": 0, "status": "uploading", "started_at": now(), "references": [str(p) for p in ordered]}
    request_path = AUDIT / "clip01_request.json"
    write_json(request_path, request)
    image_urls = [upload(client, path) for path in ordered]
    request["request_count"] = 1
    request["status"] = "submitting_once"
    write_json(request_path, request)
    # Sole paid provider submission: there is no retry branch.
    job = client.submit_async("seedance-2.0-mini", prompt=text, reference_images=image_urls, duration=5, resolution="480p", aspect_ratio="16:9", generate_audio=True, bitrate_mode="high", return_last_frame=True, seed=20260804)
    request["request_id"] = job.request_id
    request["status"] = "processing"
    write_json(request_path, request)
    result = job.wait(timeout=1800, interval=5)
    write_json(AUDIT / "clip01_result.json", result)
    video = RAW / "S1E04_clip_01_raw.mp4"
    request["output_url"] = download(result, video)
    request["technical_qc"] = qc(video, clip["dialogue"])
    last = proof(video)
    request.update({"status": "completed", "completed_at": now(), "video_sha256": digest(video), "continuity_sha256": digest(last)})
    write_json(request_path, request)
    print("S1E04 clip 01 generated once and passed technical audio QC.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        raise
