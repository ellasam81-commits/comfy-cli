#!/usr/bin/env python3
"""Generate S1E03 as twelve one-shot five-second Seedance Mini clips.

The paid work is deliberately split into a one-clip continuity gate and an
eleven-clip remainder stage.  Every selected clip is submitted exactly once;
the process stops immediately on the first failure and never retries a paid
request.
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
SOURCE_DIR = ROOT / "references" / "s1e03"
PLAN_PATH = SOURCE_DIR / "five_second_v1_plan.json"

OUTPUT_ROOT = ROOT / "output" / "s1e03"
RUNTIME_DIR = OUTPUT_ROOT / "runtime_refs"
RAW_DIR = OUTPUT_ROOT / "raw"
AUDIT_DIR = OUTPUT_ROOT / "audit"
PROOF_DIR = OUTPUT_ROOT / "proof"
LAST_FRAME_DIR = OUTPUT_ROOT / "last_frames"

BOARD_SIZE = (1672, 941)
CHART_SIZE = (1024, 1536)
STAGE_CLIPS = {
    "gate": ["01"],
    "remainder": [f"{index:02d}" for index in range(2, 13)],
}

CHARACTER_PROFILES = {
    "jian_ci": (
        "Jian Ci / 检刺: Chinese man around thirty, tall and slim, very pale "
        "angular narrow face, sharp cheekbones, layered side-part black hair, "
        "narrow dark eyes, white knee-length forensic coat over a black high-neck "
        "shirt, black gloves, no glasses. Only Jian Ci may show restrained deep-"
        "burgundy irises, and only when the shot explicitly requests it."
    ),
    "lin_qian": (
        "Lin Qian / 林浅: living adult Chinese woman, chin-length straight black "
        "bob, controlled alert expression, fitted dark-navy police field uniform, "
        "black trousers and utility belt; never a victim."
    ),
    "zhou_qiao": (
        "Zhou Qiao / 周峤: young Chinese male technical officer, messy black hair, "
        "silver-rim glasses, small hearing device and dark technical field jacket. "
        "His name is 周峤, never 周屿."
    ),
    "xu_wei": (
        "Xu Wei / 许未: adult Chinese woman, long brown hair in a high ponytail, "
        "olive forensic coverall, black examination gloves, quick precise movement."
    ),
    "han_che": (
        "Han Che / 韩彻: mature Chinese man, broad square weathered face, short "
        "dark-gray hair, dark command jacket and restrained stern expression."
    ),
    "su_wang": (
        "Su Wang / 苏望: 22-year-old Chinese man, visibly younger and different "
        "from Jian Ci, warmer skin, softer rounder face, wider eyes, blunt black "
        "fringe, charcoal civilian shirt with rolled sleeves and bare hands. No "
        "badge, white coat, gloves or red eyes."
    ),
    "cheng_ye": (
        "Cheng Ye / 程野: late-twenties Chinese male rally co-driver, cropped dark "
        "hair, longer face and black-red rally clothing, clearly different from "
        "Su Wang and Jian Ci. He appears only in photographs, scans or a restrained "
        "unconscious rescue memory; never as a moving corpse."
    ),
    "shen_heng": (
        "Shen Heng / 沈衡: lean 45-year-old Chinese male team doctor, receding "
        "hairline, silver half-rim glasses, deep-green scrubs under a gray "
        "waterproof medical coat and blue medical gloves. He never resembles "
        "square-faced Han Che or Jian Ci."
    ),
    "chen_mo": (
        "Chen Mo / 陈沫: living Chinese woman around thirty, shoulder-length "
        "rain-wet black hair, deep-brown long coat over an ivory blouse, black "
        "trousers and dark shoes. Blood stains only her blouse collar; her neck "
        "skin remains completely intact with no cut or scar. She stays upright, "
        "conscious and distinct from Lin Qian and Xu Wei."
    ),
}

CHART_COLUMN_BOXES = {
    "jian_ci": (8, 245, 205, 661),
    "lin_qian": (208, 245, 408, 661),
    "zhou_qiao": (411, 245, 613, 661),
    "xu_wei": (616, 245, 819, 661),
    "han_che": (821, 245, 1019, 661),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=tuple(STAGE_CLIPS), required=True)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--initial-continuity-frame", type=Path)
    parser.add_argument("--expected-initial-sha256")
    return parser.parse_args()


def configure_paths(stage: str) -> None:
    global OUTPUT_ROOT, RUNTIME_DIR, RAW_DIR, AUDIT_DIR, PROOF_DIR, LAST_FRAME_DIR
    default = f"output/s1e03-{stage}"
    configured = Path(os.environ.get("GENERATION_OUTPUT_DIR", default))
    OUTPUT_ROOT = configured if configured.is_absolute() else ROOT / configured
    RUNTIME_DIR = OUTPUT_ROOT / "runtime_refs"
    RAW_DIR = OUTPUT_ROOT / "raw"
    AUDIT_DIR = OUTPUT_ROOT / "audit"
    PROOF_DIR = OUTPUT_ROOT / "proof"
    LAST_FRAME_DIR = OUTPUT_ROOT / "last_frames"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def safe_source_path(relative: str) -> Path:
    candidate = (SOURCE_DIR / relative).resolve()
    root = SOURCE_DIR.resolve()
    if candidate != root and root not in candidate.parents:
        raise RuntimeError(f"Reference escapes source directory: {relative}")
    if not candidate.is_file():
        raise RuntimeError(f"Reference is missing: {relative}")
    return candidate


def load_and_validate_plan() -> dict[str, Any]:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    required = {
        "schema_version": 2,
        "episode": "S1E03",
        "model": "seedance-2.0-mini",
        "duration_seconds_per_clip": 5,
        "clip_count": 12,
        "shots_per_clip": 3,
        "resolution": "480p",
        "aspect_ratio": "16:9",
        "generate_audio": True,
        "bitrate_mode": "high",
        "automatic_retries": 0,
    }
    for key, expected in required.items():
        if plan.get(key) != expected:
            raise RuntimeError(f"Invalid plan value {key}: {plan.get(key)!r}")

    clips = plan.get("clips")
    expected_ids = [f"{index:02d}" for index in range(1, 13)]
    if not isinstance(clips, list) or [clip.get("id") for clip in clips] != expected_ids:
        raise RuntimeError("The plan must contain clips 01 through 12 in order")

    stage_ids = plan.get("stages", {})
    if stage_ids.get("gate", {}).get("clip_ids") != STAGE_CLIPS["gate"]:
        raise RuntimeError("Gate stage is not locked to clip 01")
    if stage_ids.get("remainder", {}).get("clip_ids") != STAGE_CLIPS["remainder"]:
        raise RuntimeError("Remainder stage is not locked to clips 02-12")

    for relative, expected_digest in plan["source_sha256"].items():
        path = safe_source_path(relative)
        if sha256(path) != expected_digest:
            raise RuntimeError(f"Locked source hash changed: {relative}")

    for board_index in range(1, 5):
        board = safe_source_path(f"board_{board_index:02d}.png")
        with Image.open(board) as image:
            if image.size != BOARD_SIZE:
                raise RuntimeError(f"Locked board size changed: {board} {image.size}")
            image.verify()
    with Image.open(safe_source_path("source_refs/character_chart_highres.jpeg")) as chart:
        if chart.size != CHART_SIZE:
            raise RuntimeError(f"Character chart size changed: {chart.size}")
        chart.verify()

    for clip in clips:
        row = int(clip["row"])
        if row not in (1, 2, 3):
            raise RuntimeError(f"Invalid row for clip {clip['id']}")
        expected_panels = [(row - 1) * 3 + offset for offset in range(1, 4)]
        if clip["panels"] != expected_panels or len(clip["shots"]) != 3:
            raise RuntimeError(f"Invalid three-shot mapping for clip {clip['id']}")
        timestamp = float(clip.get("continuity_frame_second", 4.60))
        if not 0.25 <= timestamp <= 4.85:
            raise RuntimeError(f"Invalid continuity frame time for clip {clip['id']}")
        dialogue = clip.get("dialogue")
        if not isinstance(dialogue, list) or not dialogue:
            raise RuntimeError(f"Clip {clip['id']} must contain Mandarin dialogue")
        for line in dialogue:
            if not (0 <= float(line["start"]) < float(line["end"]) <= 5):
                raise RuntimeError(f"Invalid dialogue timing for clip {clip['id']}")
        for item in clip.get("extra_reference_images", []):
            safe_source_path(item["file"])
        for item in clip.get("reference_videos", []):
            safe_source_path(item["file"])
    return plan


def panel_box(image: Image.Image, row: int, column: int) -> tuple[int, int, int, int]:
    x0 = round((column - 1) * image.width / 3) + 4
    x1 = round(column * image.width / 3) - 4
    y0 = round((row - 1) * image.height / 3) + 4
    y1 = round(row * image.height / 3) - 4
    return x0, y0, x1, y1


def clean_panel(image: Image.Image, row: int, column: int) -> Image.Image:
    panel = image.crop(panel_box(image, row, column)).convert("RGB")
    panel = panel.filter(ImageFilter.UnsharpMask(radius=1.0, percent=120, threshold=2))
    panel = ImageEnhance.Contrast(panel).enhance(1.06)
    return ImageOps.fit(
        panel,
        (640, 360),
        Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )


def save_identity_canvas(images: list[Image.Image], target: Path) -> None:
    canvas = Image.new("RGB", (960, 720), (3, 7, 12))
    if len(images) == 1:
        canvas.paste(ImageOps.pad(images[0], (960, 720), Image.Resampling.LANCZOS), (0, 0))
    else:
        for index, source in enumerate(images[:2]):
            fitted = ImageOps.fit(source.convert("RGB"), (480, 720), Image.Resampling.LANCZOS)
            canvas.paste(fitted, (index * 480, 0))
    canvas.save(target, quality=97)


def prepare_references(
    plan: dict[str, Any], selected_clips: list[dict[str, Any]]
) -> dict[str, Path]:
    for directory in (RUNTIME_DIR, RAW_DIR, AUDIT_DIR, PROOF_DIR, LAST_FRAME_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    identity_paths: dict[str, Path] = {}
    chart_path = safe_source_path("source_refs/character_chart_highres.jpeg")
    chart = Image.open(chart_path).convert("RGB")
    for character, box in CHART_COLUMN_BOXES.items():
        crop = chart.crop(box)
        crop = ImageEnhance.Contrast(crop).enhance(1.10)
        crop = crop.filter(ImageFilter.UnsharpMask(radius=1.0, percent=130, threshold=2))
        target = RUNTIME_DIR / f"identity_{character}.jpg"
        save_identity_canvas([crop], target)
        identity_paths[character] = target

    external_identities = {
        "jian_ci": safe_source_path("source_refs/jian_ci_identity.jpg"),
        "su_wang": safe_source_path("continuity/su_wang_identity_accepted.jpg"),
    }
    for character, source in external_identities.items():
        with Image.open(source) as image:
            target = RUNTIME_DIR / f"identity_{character}.jpg"
            save_identity_canvas([image.convert("RGB")], target)
            identity_paths[character] = target

    board_01 = Image.open(safe_source_path("board_01.png")).convert("RGB")
    board_03 = Image.open(safe_source_path("board_03.png")).convert("RGB")
    board_04 = Image.open(safe_source_path("board_04.png")).convert("RGB")
    derived = {
        "cheng_ye": [clean_panel(board_01, 3, 3), clean_panel(board_01, 2, 1)],
        "shen_heng": [clean_panel(board_01, 2, 3), clean_panel(board_03, 2, 2)],
        "chen_mo": [clean_panel(board_04, 2, 2), clean_panel(board_04, 2, 3)],
    }
    for character, images in derived.items():
        target = RUNTIME_DIR / f"identity_{character}.jpg"
        save_identity_canvas(images, target)
        identity_paths[character] = target

    for clip in selected_clips:
        board = Image.open(safe_source_path(clip["board"])).convert("RGB")
        row = int(clip["row"])
        for shot_index in range(1, 4):
            panel = clean_panel(board, row, shot_index)
            target = RUNTIME_DIR / f"clip_{clip['id']}_shot_{shot_index}.jpg"
            panel.save(target, quality=97)

    write_json(
        AUDIT_DIR / "prepared_references.json",
        {
            "created_at": utc_now(),
            "plan_sha256": sha256(PLAN_PATH),
            "selected_clip_ids": [clip["id"] for clip in selected_clips],
            "identity_files": {key: str(value) for key, value in identity_paths.items()},
            "note": "Reference crops only; no paid request made during preparation.",
        },
    )
    return identity_paths


def validate_reference_image(path: Path) -> None:
    with Image.open(path) as image:
        width, height = image.size
        image.verify()
    if not (300 <= width <= 6000 and 300 <= height <= 6000):
        raise RuntimeError(f"Reference image dimensions invalid: {path} {width}x{height}")
    ratio = width / height
    if not 0.4 <= ratio <= 2.5:
        raise RuntimeError(f"Reference image ratio invalid: {path} {ratio:.3f}")
    if path.stat().st_size >= 30 * 1024 * 1024:
        raise RuntimeError(f"Reference image exceeds 30MB: {path}")


def validate_reference_video(path: Path, spec: dict[str, Any]) -> dict[str, Any]:
    result = run(
        [
            "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)
        ]
    )
    probe = json.loads(result.stdout)
    streams = probe.get("streams", [])
    video = [stream for stream in streams if stream.get("codec_type") == "video"]
    if not video:
        raise RuntimeError(f"Video reference has no video stream: {path}")
    duration = float(probe.get("format", {}).get("duration") or 0)
    if not float(spec["duration_min"]) <= duration <= float(spec["duration_max"]):
        raise RuntimeError(f"Video reference duration invalid: {path} {duration}")
    return {"path": str(path), "duration": duration, "sha256": sha256(path)}


def build_reference_list(
    clip: dict[str, Any],
    identity_paths: dict[str, Path],
    previous_continuity_frame: Path | None,
) -> list[tuple[str, Path]]:
    specs: list[tuple[str, Path]] = [
        (
            f"storyboard shot {shot_index}, exact composition and order authority",
            RUNTIME_DIR / f"clip_{clip['id']}_shot_{shot_index}.jpg",
        )
        for shot_index in range(1, 4)
    ]
    for character in clip["characters"]:
        specs.append((f"identity authority for {character}", identity_paths[character]))
    for item in clip.get("extra_reference_images", []):
        specs.append((item["label"], safe_source_path(item["file"])))
    if previous_continuity_frame is not None:
        specs.append(
            (
                "previous accepted clip continuity frame, low-priority position and lighting support only",
                previous_continuity_frame,
            )
        )
    if clip["use_previous_last_frame"] and previous_continuity_frame is None:
        raise RuntimeError(f"Clip {clip['id']} requires a continuity frame")
    if len(specs) > 9:
        raise RuntimeError(f"Too many image references for clip {clip['id']}: {len(specs)}")
    for _, path in specs:
        validate_reference_image(path)
    if clip["use_previous_last_frame"] and not any(
        "previous accepted" in label for label, _ in specs
    ):
        raise RuntimeError(f"Continuity frame was not retained for clip {clip['id']}")
    return specs


def build_video_reference_list(clip: dict[str, Any]) -> list[tuple[str, Path]]:
    specs: list[tuple[str, Path]] = []
    for item in clip.get("reference_videos", []):
        path = safe_source_path(item["file"])
        validate_reference_video(path, item)
        specs.append((item["label"], path))
    if clip["id"] != "01" and specs:
        raise RuntimeError("Only clip 01 may use a video reference")
    return specs


def build_prompt(
    plan: dict[str, Any],
    clip: dict[str, Any],
    image_specs: list[tuple[str, Path]],
    video_specs: list[tuple[str, Path]],
) -> str:
    image_map = "\n".join(
        f"- Reference image {index}: {label}."
        for index, (label, _) in enumerate(image_specs, start=1)
    )
    video_map = "\n".join(
        f"- Reference video {index}: {label}."
        for index, (label, _) in enumerate(video_specs, start=1)
    ) or "- No video reference for this clip."
    shots = "\n".join(
        f"{index}. {description}"
        for index, description in enumerate(clip["shots"], start=1)
    )
    profiles = "\n".join(CHARACTER_PROFILES[key] for key in clip["characters"])
    audio = "\n".join(
        (
            f"{float(line['start']):.2f}-{float(line['end']):.2f} "
            f"{line['speaker_zh']} ({line['speaker_en']}): {line['zh']}"
        )
        for line in clip["dialogue"]
    )
    continuity_rule = (
        "A previous continuity image is supplied. It controls only starting position, "
        "room lighting and screen direction; it may not override this clip's faces, "
        "wardrobe, props or storyboard."
        if any("previous accepted" in label for label, _ in image_specs)
        else "No previous continuity image is supplied; establish this clip directly from its storyboard and scene references."
    )
    text_rule = (
        "Do not create readable in-world text or labels. The exact Container-07 "
        "first shot is replaced deterministically in post, so the generated label "
        "surface must stay blank."
        if clip["id"] == "07"
        else "Do not create any readable in-world text or labels."
    )
    return f"""
ORIGINAL SERIES PRODUCTION LOCK. Animate one clean five-second 16:9 clip for
{plan['series_title_zh']} {plan['episode']}《{plan['episode_title_zh']}》, clip
{clip['id']} of 12. This is an original dark forensic manga-noir production
based only on the user's own storyboard and character references. Do not imitate
any named artist, studio, franchise or copyrighted character.

ABSOLUTE STORYBOARD RULE. Render exactly three distinct full-screen cinematic
shots in the exact reference order and timing below, using ordinary hard cuts.
Every shot fills the 16:9 frame. Never display the three panels together, a
storyboard page, grid, split screen, border, panel number, prompt, UI, title,
subtitle, logo or watermark. Do not repeat, skip, swap or merge shots. Do not
{text_rule}

REFERENCE IMAGE MAP:
{image_map}

REFERENCE VIDEO MAP:
{video_map}
Reference video is low-priority motion, architecture and screen-direction
support only. Never copy its old dialogue, text, subtitle, title, wrong shot
order or transient expression.
{continuity_rule}

EXACT THREE SHOTS:
{shots}

CHARACTER IDENTITY LOCK:
{profiles}
Preserve face, apparent age, hair, body proportions, wardrobe and handed props
through every shot. No face swap, twin, duplicate, morph, wardrobe exchange,
extra person or identity drift. Jian Ci and Su Wang must never resemble one
another. Han Che and Shen Heng must never resemble one another. Only Jian Ci
may ever have burgundy irises.

SCENE AND PROP LOCK. Location: {clip['scene']}. Match the storyboard's cold
blue-black low-saturation suspense lighting, rain-dark surfaces, fine ink
linework, controlled contrast and restrained high-detail 2D motion. Keep
architecture, furniture, sealed evidence, tools, clothing and prop placement
coherent. Camera language is cinematic crime direction: motivated wide/medium/
macro progression, stable screen direction, subtle parallax and at most one
restrained push. No frantic camera, glossy 3D, photoreal live action, chibi or
bright fantasy glow.

STORY AND FORENSIC LOCK. {plan['global_story_lock']}
Use gloves, seals and chain-of-custody discipline. DNA identifies biological
source but is not guilt by itself. Entomology narrows an interval but never
produces an exact minute. Tool marks require independent blood, access and
record corroboration. {clip['special_negative']}

AUDIO LOCK. Generate synchronized native Mandarin audio with clear natural
adult Chinese voices and restrained location ambience. No music; one continuous
suspense score is added later in post. Speak only the exact Chinese lines below,
at a brisk but intelligible pace without overlap. Do not speak English and do
not invent words:
{audio}
Make every specified line audible, centered and louder than ambience. Do not
generate visible subtitles; deterministic Chinese/English subtitles and the
persistent top header are added in post.

STRICT NEGATIVE: {plan['global_negative']}.
""".strip()


def upload_reference(client: Any, path: Path) -> str:
    response = client.files.upload(path)
    urls = response.get("file_urls") if isinstance(response, dict) else None
    if not urls or not isinstance(urls[0], str):
        raise RuntimeError(f"No Segmind file URL returned for {path}: {response}")
    return urls[0]


def collect_urls(value: Any, found: list[str]) -> None:
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        found.append(value)
    elif isinstance(value, list):
        for child in value:
            collect_urls(child, found)
    elif isinstance(value, dict):
        for child in value.values():
            collect_urls(child, found)


def looks_like_video(data: bytes, content_type: str, url: str) -> bool:
    suffix = Path(urlparse(url).path).suffix.lower()
    return (
        "video/" in content_type.lower()
        or data[4:8] == b"ftyp"
        or data[:4] == bytes.fromhex("1a45dfa3")
        or suffix in {".mp4", ".webm", ".mov"}
    )


def download_video(result: Any, target: Path) -> str:
    import requests

    urls: list[str] = []
    output = result.get("output", result) if isinstance(result, dict) else result
    collect_urls(output, urls)
    urls = list(dict.fromkeys(urls))
    if not urls:
        raise RuntimeError("Segmind completed without a downloadable output URL")
    for url in urls:
        response = requests.get(url, timeout=300)
        response.raise_for_status()
        if looks_like_video(response.content, response.headers.get("content-type", ""), url):
            target.write_bytes(response.content)
            return url
    raise RuntimeError(f"Segmind output contained no video URL: {urls}")


def probe_and_verify(
    video_path: Path,
    clip_id: str,
    speech_model: Any,
    expected_dialogue: list[dict[str, Any]],
) -> dict[str, Any]:
    if video_path.stat().st_size < 200_000:
        raise RuntimeError(f"Clip {clip_id} is unexpectedly small")
    probe_result = run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video_path)]
    )
    probe = json.loads(probe_result.stdout)
    streams = probe.get("streams", [])
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if not video_streams or not audio_streams:
        raise RuntimeError(f"Clip {clip_id} must contain video and audio")
    duration = float(probe.get("format", {}).get("duration") or 0)
    if not 4.3 <= duration <= 5.8:
        raise RuntimeError(f"Clip {clip_id} duration invalid: {duration}")
    audio_duration = float(audio_streams[0].get("duration") or duration)
    if audio_duration < 4.0:
        raise RuntimeError(f"Clip {clip_id} audio is too short: {audio_duration}")

    loudness = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(video_path), "-vn",
            "-af", "volumedetect", "-f", "null", "-",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    match = re.search(r"max_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB", loudness.stderr)
    if not match or match.group(1) == "-inf" or float(match.group(1)) < -55:
        raise RuntimeError(f"Clip {clip_id} audio is silent or too quiet")

    segment_iterator, speech_info = speech_model.transcribe(
        str(video_path),
        language="zh",
        task="transcribe",
        beam_size=1,
        temperature=0,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 250},
        condition_on_previous_text=False,
    )
    segments = [
        {"start": float(segment.start), "end": float(segment.end), "text": segment.text.strip()}
        for segment in segment_iterator
        if segment.text.strip()
    ]
    transcript = "".join(segment["text"] for segment in segments)
    speech_seconds = sum(max(0.0, item["end"] - item["start"]) for item in segments)
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", transcript))
    speech_audit = {
        "clip_id": clip_id,
        "language_forced": "zh",
        "reported_language": getattr(speech_info, "language", None),
        "language_probability": getattr(speech_info, "language_probability", None),
        "transcript": transcript,
        "cjk_character_count": cjk_count,
        "detected_speech_seconds": speech_seconds,
        "segments": segments,
        "expected_dialogue": [line["zh"] for line in expected_dialogue],
        "purpose": "Fail-fast Mandarin-presence check; final words are audited separately.",
    }
    write_json(AUDIT_DIR / f"clip_{clip_id}_speech_check.json", speech_audit)
    if speech_seconds < 0.40 or cjk_count < 2:
        raise RuntimeError(f"Clip {clip_id} has no verifiable Mandarin speech")

    write_json(AUDIT_DIR / f"clip_{clip_id}_ffprobe.json", probe)
    (AUDIT_DIR / f"clip_{clip_id}_loudness.txt").write_text(loudness.stderr, encoding="utf-8")
    return {
        "duration": duration,
        "size_bytes": video_path.stat().st_size,
        "video_codec": video_streams[0].get("codec_name"),
        "width": video_streams[0].get("width"),
        "height": video_streams[0].get("height"),
        "audio_codec": audio_streams[0].get("codec_name"),
        "audio_channels": audio_streams[0].get("channels"),
        "audio_duration": audio_duration,
        "max_volume_db": float(match.group(1)),
        "detected_speech_seconds": speech_seconds,
        "asr_transcript": transcript,
    }


def make_proof(video_path: Path, clip: dict[str, Any]) -> Path:
    clip_id = clip["id"]
    continuity = LAST_FRAME_DIR / f"clip_{clip_id}_continuity.jpg"
    run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss",
            f"{float(clip['continuity_frame_second']):.3f}", "-i", str(video_path),
            "-frames:v", "1", "-q:v", "2", str(continuity),
        ]
    )
    contact = PROOF_DIR / f"clip_{clip_id}_contact.jpg"
    run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video_path),
            "-vf", "fps=0.6,scale=427:240:force_original_aspect_ratio=decrease,"
            "pad=427:240:(ow-iw)/2:(oh-ih)/2:black,tile=3x1:padding=4:margin=4",
            "-frames:v", "1", "-q:v", "2", str(contact),
        ]
    )
    return continuity


def extract_cost(result: Any) -> float | None:
    if not isinstance(result, dict):
        return None
    metrics = result.get("metrics")
    if isinstance(metrics, dict):
        for key in ("cost", "cost_usd", "price"):
            value = metrics.get(key)
            if isinstance(value, (int, float)):
                return float(value)
    for key in ("cost", "cost_usd"):
        value = result.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def validate_stage_args(args: argparse.Namespace) -> Path | None:
    if args.stage == "gate":
        if args.initial_continuity_frame or args.expected_initial_sha256:
            raise RuntimeError("Gate stage rejects external continuity input")
        return None
    if not args.initial_continuity_frame or not args.expected_initial_sha256:
        raise RuntimeError("Remainder stage requires the accepted gate continuity frame and SHA-256")
    frame = args.initial_continuity_frame.resolve()
    if not frame.is_file():
        raise RuntimeError(f"Initial continuity frame is missing: {frame}")
    validate_reference_image(frame)
    actual = sha256(frame)
    if actual != args.expected_initial_sha256:
        raise RuntimeError(f"Initial continuity SHA mismatch: {actual}")
    return frame


def prepare_only(
    plan: dict[str, Any],
    selected_clips: list[dict[str, Any]],
    identity_paths: dict[str, Path],
    initial_frame: Path | None,
) -> None:
    placeholder = initial_frame
    records: list[dict[str, Any]] = []
    for clip in selected_clips:
        continuity = placeholder if clip["use_previous_last_frame"] else None
        if clip["use_previous_last_frame"] and continuity is None:
            # Static validation for later same-stage links uses a known valid
            # identity image; the real generated frame is used during paid work.
            continuity = identity_paths[clip["characters"][0]]
        image_specs = build_reference_list(clip, identity_paths, continuity)
        video_specs = build_video_reference_list(clip)
        prompt = build_prompt(plan, clip, image_specs, video_specs)
        (AUDIT_DIR / f"clip_{clip['id']}_prompt.txt").write_text(prompt, encoding="utf-8")
        records.append(
            {
                "clip_id": clip["id"],
                "image_reference_count": len(image_specs),
                "video_reference_count": len(video_specs),
                "image_references": [str(path) for _, path in image_specs],
                "video_references": [str(path) for _, path in video_specs],
            }
        )
        placeholder = identity_paths[clip["characters"][0]]
    write_json(
        AUDIT_DIR / "prepare_only_manifest.json",
        {
            "status": "prepared_without_paid_request",
            "stage": selected_clips[0]["id"] == "01" and "gate" or "remainder",
            "created_at": utc_now(),
            "records": records,
        },
    )
    print("All locked references and prompts validated; no paid request made.")


def main() -> None:
    args = parse_args()
    configure_paths(args.stage)
    plan = load_and_validate_plan()
    selected_ids = STAGE_CLIPS[args.stage]
    selected_clips = [clip for clip in plan["clips"] if clip["id"] in selected_ids]
    initial_frame = validate_stage_args(args)
    identity_paths = prepare_references(plan, selected_clips)

    if args.prepare_only:
        prepare_only(plan, selected_clips, identity_paths, initial_frame)
        return
    if not os.environ.get("SEGMIND_API_KEY"):
        raise RuntimeError("SEGMIND_API_KEY is missing; no paid request made")

    from faster_whisper import WhisperModel
    from segmind import SegmindClient

    speech_model = WhisperModel(
        "tiny",
        device="cpu",
        compute_type="int8",
        download_root=os.environ.get("WHISPER_CACHE_DIR", "whisper_cache"),
    )
    client = SegmindClient()
    completed: list[dict[str, Any]] = []
    previous_frame = initial_frame
    estimated_total = round(len(selected_clips) * float(plan["estimated_usd_per_clip"]), 3)
    manifest_path = AUDIT_DIR / "generation_manifest.json"
    manifest: dict[str, Any] = {
        "episode": plan["episode"],
        "stage": args.stage,
        "started_at": utc_now(),
        "planned_clip_ids": selected_ids,
        "planned_clips": len(selected_clips),
        "completed_clips": 0,
        "request_count": 0,
        "automatic_retries": 0,
        "estimated_usd_per_clip": plan["estimated_usd_per_clip"],
        "estimated_usd_total": estimated_total,
        "actual_provider_cost_usd": None,
        "initial_continuity_frame": str(initial_frame) if initial_frame else None,
        "initial_continuity_sha256": sha256(initial_frame) if initial_frame else None,
        "status": "running",
        "clips": completed,
    }
    write_json(manifest_path, manifest)

    try:
        for clip in selected_clips:
            clip_id = clip["id"]
            continuity = previous_frame if clip["use_previous_last_frame"] else None
            image_specs = build_reference_list(clip, identity_paths, continuity)
            video_specs = build_video_reference_list(clip)
            prompt = build_prompt(plan, clip, image_specs, video_specs)
            (AUDIT_DIR / f"clip_{clip_id}_prompt.txt").write_text(prompt, encoding="utf-8")

            request_audit: dict[str, Any] = {
                "clip_id": clip_id,
                "stage": args.stage,
                "model": plan["model"],
                "duration": 5,
                "resolution": "480p",
                "aspect_ratio": "16:9",
                "generate_audio": True,
                "bitrate_mode": "high",
                "seed": clip["seed"],
                "image_reference_files": [str(path) for _, path in image_specs],
                "image_reference_labels": [label for label, _ in image_specs],
                "video_reference_files": [str(path) for _, path in video_specs],
                "video_reference_labels": [label for label, _ in video_specs],
                "request_count": 0,
                "automatic_retries": 0,
                "estimated_usd": plan["estimated_usd_per_clip"],
                "actual_provider_cost_usd": None,
                "status": "uploading_references",
                "started_at": utc_now(),
            }
            request_path = AUDIT_DIR / f"clip_{clip_id}_request.json"
            write_json(request_path, request_audit)

            image_urls = [upload_reference(client, path) for _, path in image_specs]
            video_urls = [upload_reference(client, path) for _, path in video_specs]
            request_audit["status"] = "submitting_once"
            request_audit["request_count"] = 1
            write_json(request_path, request_audit)
            manifest["request_count"] += 1
            write_json(manifest_path, manifest)

            payload: dict[str, Any] = {
                "prompt": prompt,
                "reference_images": image_urls,
                "duration": 5,
                "resolution": "480p",
                "aspect_ratio": "16:9",
                "generate_audio": True,
                "bitrate_mode": "high",
                "return_last_frame": True,
                "seed": clip["seed"],
            }
            if video_urls:
                payload["reference_videos"] = video_urls

            # This is the sole paid submission statement. The loop reaches it
            # exactly once per selected clip and stops after any failure.
            job = client.submit_async("seedance-2.0-mini", **payload)
            request_audit["request_id"] = job.request_id
            request_audit["status"] = "processing"
            write_json(request_path, request_audit)
            print(f"Clip {clip_id}: Segmind request {job.request_id}", flush=True)

            result = job.wait(timeout=1800, interval=5)
            write_json(AUDIT_DIR / f"clip_{clip_id}_result.json", result)
            request_audit["actual_provider_cost_usd"] = extract_cost(result)
            video_path = RAW_DIR / f"S1E03_clip_{clip_id}_raw.mp4"
            request_audit["output_url"] = download_video(result, video_path)
            request_audit["technical_qc"] = probe_and_verify(
                video_path, clip_id, speech_model, clip["dialogue"]
            )
            previous_frame = make_proof(video_path, clip)

            request_audit["status"] = "completed"
            request_audit["completed_at"] = utc_now()
            request_audit["video_sha256"] = sha256(video_path)
            request_audit["continuity_frame_sha256"] = sha256(previous_frame)
            write_json(request_path, request_audit)
            completed.append(request_audit)
            manifest["completed_clips"] = len(completed)
            known_costs = [
                item["actual_provider_cost_usd"]
                for item in completed
                if item["actual_provider_cost_usd"] is not None
            ]
            manifest["actual_provider_cost_usd"] = round(sum(known_costs), 8) if known_costs else None
            write_json(manifest_path, manifest)

        manifest["status"] = "completed"
        manifest["completed_at"] = utc_now()
        write_json(manifest_path, manifest)
        print(f"S1E03 {args.stage} completed with {len(completed)} one-shot request(s).")
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["failed_at"] = utc_now()
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        write_json(manifest_path, manifest)
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
