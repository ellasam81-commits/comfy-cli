#!/usr/bin/env python3
"""Generate S1E02 as twelve sequential five-second Seedance Mini review clips.

The script intentionally performs exactly one paid model submission per clip,
stops on the first failure, and never retries a paid request.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from faster_whisper import WhisperModel
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps
from segmind import SegmindClient


ROOT = Path.cwd()
SOURCE_DIR = ROOT / "references" / "s1e02"
PLAN_PATH = SOURCE_DIR / "five_second_v1_plan.json"
RUNTIME_DIR = ROOT / "runtime_refs"
RAW_DIR = ROOT / "raw"
AUDIT_DIR = ROOT / "audit"
PROOF_DIR = ROOT / "proof"
LAST_FRAME_DIR = ROOT / "last_frames"

EXPECTED_DIMENSIONS = {
    "board_01.jpeg": (512, 341),
    "board_02.jpeg": (512, 341),
    "board_03.jpeg": (512, 341),
    "board_04.jpeg": (512, 341),
    "character_chart.jpeg": (384, 576),
}

PANEL_X = [(4, 128), (128, 252), (252, 376), (376, 508)]
VISUAL_Y = {
    "board_01.jpeg": [(47, 104), (146, 203), (245, 302)],
    "board_02.jpeg": [(47, 104), (146, 203), (245, 302)],
    "board_03.jpeg": [(58, 108), (146, 196), (231, 281)],
    "board_04.jpeg": [(58, 108), (146, 196), (231, 281)],
}

CHARACTER_PROFILES = {
    "jian_ci": (
        "Jian Ci / 检刺: Chinese man, early thirties, tall and slim, very pale "
        "angular narrow face, sharp cheekbones, layered side-part black hair, "
        "narrow dark eyes, white knee-length forensic coat over a black high-neck "
        "shirt, black gloves, no glasses. Only Jian Ci may show restrained deep-"
        "burgundy vampire irises, and only where the shot description requests it."
    ),
    "lin_qian": (
        "Lin Qian / 林浅: adult Chinese woman, chin-length straight black bob, "
        "controlled alert expression, fitted dark-navy police field uniform and "
        "utility belt; she is alive and is never a victim."
    ),
    "zhou_qiao": (
        "Zhou Qiao / 周峤: young Chinese male technical officer, messy black hair, "
        "silver-rim glasses, small hearing device, dark technical field jacket. "
        "His name is 周峤, never 周屿."
    ),
    "xu_wei": (
        "Xu Wei / 许未: adult Chinese woman, long brown hair in a high ponytail, "
        "olive forensic coverall, black examination gloves, quick precise movement."
    ),
    "han_che": (
        "Han Che / 韩彻: mature Chinese man, square weathered face, short dark hair, "
        "dark command jacket, restrained stern expression."
    ),
    "su_wang": (
        "Su Wang / 苏望: 22-year-old Chinese man, visibly younger and different from "
        "Jian Ci, warmer skin, softer rounder face, wider eyes, blunt forward black "
        "fringe, dark charcoal civilian shirt with rolled sleeves and bare hands. "
        "No badge, no white coat, no gloves, no red eyes."
    ),
}

CHART_COLUMN_BOXES = {
    "jian_ci": (3, 92, 77, 248),
    "lin_qian": (78, 92, 153, 248),
    "zhou_qiao": (154, 92, 230, 248),
    "xu_wei": (231, 92, 307, 248),
    "han_che": (308, 92, 382, 248),
}


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
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )


def load_and_validate_plan() -> dict[str, Any]:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    required = {
        "episode": "S1E02",
        "model": "seedance-2.0-mini",
        "duration_seconds_per_clip": 5,
        "clip_count": 12,
        "resolution": "480p",
        "aspect_ratio": "16:9",
        "generate_audio": True,
        "automatic_retries": 0,
    }
    for key, expected in required.items():
        if plan.get(key) != expected:
            raise RuntimeError(f"Invalid plan value {key}: {plan.get(key)!r}")

    clips = plan.get("clips")
    if not isinstance(clips, list) or [clip.get("id") for clip in clips] != [
        f"{index:02d}" for index in range(1, 13)
    ]:
        raise RuntimeError("The plan must contain clips 01 through 12 in order")

    for filename, expected_digest in plan["source_sha256"].items():
        source_path = SOURCE_DIR / filename
        if sha256(source_path) != expected_digest:
            raise RuntimeError(f"Locked source hash changed: {filename}")
        with Image.open(source_path) as image:
            if image.size != EXPECTED_DIMENSIONS[filename]:
                raise RuntimeError(f"Locked source dimensions changed: {filename}")

    for clip in clips:
        if clip["row"] not in (1, 2, 3) or clip["panels"] != [
            (clip["row"] - 1) * 4 + offset for offset in range(1, 5)
        ]:
            raise RuntimeError(f"Invalid storyboard mapping for clip {clip['id']}")
        for line in clip["dialogue"]:
            if not (0 <= float(line["start"]) < float(line["end"]) <= 5):
                raise RuntimeError(f"Invalid dialogue timing for clip {clip['id']}")

    return plan


def clean_panel(image: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    panel = image.crop(box).convert("RGB")
    draw = ImageDraw.Draw(panel)
    sample = panel.crop((20, 0, min(38, panel.width), min(16, panel.height)))
    sample = sample.resize((1, 1), Image.Resampling.BOX)
    fill = sample.getpixel((0, 0))
    draw.rectangle((0, 0, min(18, panel.width), min(14, panel.height)), fill=fill)
    panel = panel.filter(ImageFilter.UnsharpMask(radius=1.2, percent=125, threshold=2))
    panel = ImageEnhance.Contrast(panel).enhance(1.12)
    panel = ImageEnhance.Color(panel).enhance(0.94)
    return ImageOps.pad(
        panel,
        (640, 360),
        Image.Resampling.LANCZOS,
        color=(3, 7, 12),
        centering=(0.5, 0.5),
    )


def prepare_references(plan: dict[str, Any]) -> dict[str, Path]:
    for directory in (RUNTIME_DIR, RAW_DIR, AUDIT_DIR, PROOF_DIR, LAST_FRAME_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    identity_paths: dict[str, Path] = {}
    chart = Image.open(SOURCE_DIR / "character_chart.jpeg").convert("RGB")
    for character, box in CHART_COLUMN_BOXES.items():
        crop = chart.crop(box)
        crop = ImageEnhance.Contrast(crop).enhance(1.12)
        crop = crop.filter(ImageFilter.UnsharpMask(radius=1.2, percent=135, threshold=2))
        target = RUNTIME_DIR / f"identity_{character}.jpg"
        ImageOps.pad(
            crop,
            (480, 720),
            Image.Resampling.LANCZOS,
            color=(3, 7, 12),
        ).save(target, quality=97)
        identity_paths[character] = target

    # Su Wang is absent from the core chart. Lock him with the two accepted
    # storyboard portraits: first reveal (board 2 panel 4) and close-up (board 4 panel 10).
    su_sources: list[Image.Image] = []
    for board_name, row_index, column_index in (
        ("board_02.jpeg", 0, 3),
        ("board_04.jpeg", 2, 1),
    ):
        board = Image.open(SOURCE_DIR / board_name).convert("RGB")
        x0, x1 = PANEL_X[column_index]
        y0, y1 = VISUAL_Y[board_name][row_index]
        su_sources.append(clean_panel(board, (x0, y0, x1, y1)).resize((480, 270)))
    su_canvas = Image.new("RGB", (480, 720), (3, 7, 12))
    su_canvas.paste(su_sources[0], (0, 60))
    su_canvas.paste(su_sources[1], (0, 390))
    su_target = RUNTIME_DIR / "identity_su_wang.jpg"
    su_canvas.save(su_target, quality=97)
    identity_paths["su_wang"] = su_target

    for clip in plan["clips"]:
        board_name = clip["board"]
        board = Image.open(SOURCE_DIR / board_name).convert("RGB")
        y0, y1 = VISUAL_Y[board_name][clip["row"] - 1]
        panel_images: list[Image.Image] = []
        for shot_index, (x0, x1) in enumerate(PANEL_X, start=1):
            panel = clean_panel(board, (x0, y0, x1, y1))
            target = RUNTIME_DIR / f"clip_{clip['id']}_shot_{shot_index}.jpg"
            panel.save(target, quality=97)
            panel_images.append(panel)

        row_canvas = Image.new("RGB", (1280, 180), (3, 7, 12))
        for shot_index, panel in enumerate(panel_images):
            row_canvas.paste(panel.resize((320, 180), Image.Resampling.LANCZOS), (shot_index * 320, 0))
        row_target = RUNTIME_DIR / f"clip_{clip['id']}_ordered_row.jpg"
        row_canvas.save(row_target, quality=97)

    write_json(
        AUDIT_DIR / "prepared_references.json",
        {
            "created_at": utc_now(),
            "plan_sha256": sha256(PLAN_PATH),
            "identity_files": {key: str(value) for key, value in identity_paths.items()},
            "note": "Reference crops only; no paid request made during preparation.",
        },
    )
    return identity_paths


def build_reference_list(
    clip: dict[str, Any],
    identity_paths: dict[str, Path],
    previous_last_frame: Path | None,
) -> list[tuple[str, Path]]:
    specs: list[tuple[str, Path]] = [
        (
            f"storyboard shot {shot_index}, exact composition authority",
            RUNTIME_DIR / f"clip_{clip['id']}_shot_{shot_index}.jpg",
        )
        for shot_index in range(1, 5)
    ]
    specs.append(
        (
            "ordered four-shot storyboard strip, left-to-right timing authority",
            RUNTIME_DIR / f"clip_{clip['id']}_ordered_row.jpg",
        )
    )
    for character in clip["characters"]:
        specs.append((f"identity authority for {character}", identity_paths[character]))
    if previous_last_frame is not None:
        specs.append(
            (
                "previous accepted clip last frame, low-priority continuity reference only",
                previous_last_frame,
            )
        )
    if len(specs) > 9:
        specs = [spec for spec in specs if not spec[0].startswith("ordered four-shot")]
    if len(specs) > 9:
        specs = [spec for spec in specs if "previous accepted" not in spec[0]]
    if len(specs) > 9:
        raise RuntimeError(f"Too many references for clip {clip['id']}: {len(specs)}")
    return specs


def build_prompt(clip: dict[str, Any], reference_specs: list[tuple[str, Path]]) -> str:
    reference_map = "\n".join(
        f"- Reference image {index}: {label}."
        for index, (label, _) in enumerate(reference_specs, start=1)
    )
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
    previous_rule = (
        "The final reference is continuity support only. Never copy its text, shot "
        "composition, wrong character, or transient facial expression into a new shot."
        if any("previous accepted" in label for label, _ in reference_specs)
        else "No previous-frame reference is supplied; establish the location directly from the four storyboard shots."
    )
    text_rule = (
        "The only permitted readable in-world text is the simple room plaque 302 in shot 1; do not create any other text."
        if clip["id"] == "07"
        else "Do not create any readable in-world text."
    )
    return f"""
ORIGINAL SERIES PRODUCTION LOCK. Animate one clean five-second 16:9 clip for
《吸血法医·剑刺》 S1E02《会说话的骨头》, clip {clip['id']} of 12. This is an
original dark forensic manga-noir production based only on the user's own
storyboards and character chart. Do not imitate any named artist, studio,
franchise or copyrighted character.

ABSOLUTE STORYBOARD RULE. Render four distinct full-screen shots in the exact
left-to-right reference order. Use hard cuts near 1.25, 2.50 and 3.75 seconds.
Every shot must fill the 16:9 frame. Never show a four-panel grid, storyboard
page, split screen, panel border, storyboard panel number, prompt, UI,
watermark, logo, title or subtitle. {text_rule} Do not repeat, skip, swap or
merge shots.

REFERENCE MAP:
{reference_map}
{previous_rule}

EXACT FOUR SHOTS:
{shots}

CHARACTER IDENTITY LOCK:
{profiles}
Preserve face, apparent age, hair, body proportions, wardrobe and handed props
across all four shots. No face swap, twin, duplicate, morph, wardrobe exchange,
extra person or identity drift. Jian Ci and Su Wang must never resemble one
another. Only Jian Ci may ever have red irises.

SCENE AND PROP LOCK. Location: {clip['scene']}. Match the board's cold blue-black
low-saturation suspense lighting, rain-dark surfaces, fine ink linework,
controlled high contrast and restrained 2D motion. Keep architecture, furniture,
evidence seals, tools, clothing and prop placement coherent. Camera language is
cinematic crime direction: motivated wide/medium/macro progression, stable
screen direction, subtle parallax, one restrained push at most, no frantic
camera, no glossy 3D, no photoreal live action, no chibi, no bright fantasy glow.

FORENSIC REALISM. Use gloves and sealed evidence when required. Do not turn
medical supplies, anesthetic, stress reactions or Jian Ci's vampire perception
into proof of guilt. No gore, blood spray, torture, surgery spectacle, loose
body parts or sensational corpse movement.

AUDIO LOCK. Generate synchronized native Mandarin audio with clear natural
adult Chinese voices, subtle location ambience and sparse low suspense music.
Speak only the following exact Chinese words, at a brisk but intelligible pace,
without overlap. Do not speak English and do not invent any line:
{audio}
Make every specified line audible. Keep dialogue centered and louder than
ambience. Do not generate visible subtitles; deterministic Chinese/English
subtitles and the persistent top title will be added in post.

STRICT NEGATIVE: wrong name, 周屿, English speech, missing dialogue, silent
track, unreadable mumbling, extra dialogue, generated text, captions, credits,
logo, watermark, collage, split screen, repeated close-up, skipped shot, bright
palette, comedy distortion, identity drift, inconsistent location, inconsistent
prop, supernatural proof, fangs, aura, beam, gore.
""".strip()


def upload_reference(client: SegmindClient, path: Path) -> str:
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
    urls: list[str] = []
    output = result.get("output", result) if isinstance(result, dict) else result
    collect_urls(output, urls)
    urls = list(dict.fromkeys(urls))
    if not urls:
        raise RuntimeError("Segmind completed without a downloadable output URL")
    for url in urls:
        response = requests.get(url, timeout=300)
        response.raise_for_status()
        if looks_like_video(
            response.content,
            response.headers.get("content-type", ""),
            url,
        ):
            target.write_bytes(response.content)
            return url
    raise RuntimeError(f"Segmind output contained no video URL: {urls}")


def probe_and_verify(
    video_path: Path,
    clip_id: str,
    speech_model: WhisperModel,
    expected_dialogue: list[dict[str, Any]],
) -> dict[str, Any]:
    if video_path.stat().st_size < 200_000:
        raise RuntimeError(f"Clip {clip_id} is unexpectedly small")
    probe_result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(video_path),
        ]
    )
    probe = json.loads(probe_result.stdout)
    streams = probe.get("streams", [])
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if not video_streams:
        raise RuntimeError(f"Clip {clip_id} has no video stream")
    if not audio_streams:
        raise RuntimeError(f"Clip {clip_id} has no audio stream")
    duration = float(probe.get("format", {}).get("duration") or 0)
    if not 4.3 <= duration <= 5.8:
        raise RuntimeError(f"Clip {clip_id} duration is invalid: {duration}")
    audio_duration = float(audio_streams[0].get("duration") or duration)
    if audio_duration < 4.0:
        raise RuntimeError(
            f"Clip {clip_id} audio stream is too short: {audio_duration}"
        )

    loudness = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(video_path),
            "-vn",
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    loudness_text = loudness.stderr
    match = re.search(r"max_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB", loudness_text)
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
    speech_segments = [
        {
            "start": float(segment.start),
            "end": float(segment.end),
            "text": segment.text.strip(),
        }
        for segment in segment_iterator
        if segment.text.strip()
    ]
    transcript = "".join(segment["text"] for segment in speech_segments)
    speech_seconds = sum(
        max(0.0, segment["end"] - segment["start"])
        for segment in speech_segments
    )
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", transcript))
    speech_audit = {
        "clip_id": clip_id,
        "language_forced": "zh",
        "reported_language": getattr(speech_info, "language", None),
        "language_probability": getattr(speech_info, "language_probability", None),
        "transcript": transcript,
        "cjk_character_count": cjk_count,
        "detected_speech_seconds": speech_seconds,
        "segments": speech_segments,
        "expected_dialogue": [line["zh"] for line in expected_dialogue],
        "purpose": "Fail-fast detection of missing Mandarin speech; not a word-perfect transcript.",
    }
    write_json(AUDIT_DIR / f"clip_{clip_id}_speech_check.json", speech_audit)
    if speech_seconds < 0.40 or cjk_count < 2:
        raise RuntimeError(
            f"Clip {clip_id} has an audio track but no verifiable Mandarin speech"
        )

    write_json(AUDIT_DIR / f"clip_{clip_id}_ffprobe.json", probe)
    (AUDIT_DIR / f"clip_{clip_id}_loudness.txt").write_text(
        loudness_text,
        encoding="utf-8",
    )
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


def make_proof(video_path: Path, clip_id: str) -> Path:
    last_frame = LAST_FRAME_DIR / f"clip_{clip_id}_last.jpg"
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-sseof",
            "-0.15",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(last_frame),
        ]
    )
    contact = PROOF_DIR / f"clip_{clip_id}_contact.jpg"
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-vf",
            "fps=0.8,scale=427:240:force_original_aspect_ratio=decrease,"
            "pad=427:240:(ow-iw)/2:(oh-ih)/2:black,tile=2x2:padding=4:margin=4",
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(contact),
        ]
    )
    return last_frame


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


def main() -> None:
    if not os.environ.get("SEGMIND_API_KEY"):
        raise RuntimeError("SEGMIND_API_KEY is missing; no paid request made")

    plan = load_and_validate_plan()
    identity_paths = prepare_references(plan)
    speech_model = WhisperModel(
        "tiny",
        device="cpu",
        compute_type="int8",
        download_root=os.environ.get("WHISPER_CACHE_DIR", "whisper_cache"),
    )
    client = SegmindClient()
    completed: list[dict[str, Any]] = []
    previous_last_frame: Path | None = None

    manifest_path = AUDIT_DIR / "generation_manifest.json"
    manifest: dict[str, Any] = {
        "episode": plan["episode"],
        "model": plan["model"],
        "started_at": utc_now(),
        "planned_clips": 12,
        "completed_clips": 0,
        "request_count": 0,
        "automatic_retries": 0,
        "estimated_usd_per_clip": plan["estimated_usd_per_clip"],
        "estimated_usd_total": plan["estimated_usd_total"],
        "actual_provider_cost_usd": None,
        "status": "running",
        "clips": completed,
    }
    write_json(manifest_path, manifest)

    try:
        for clip in plan["clips"]:
            clip_id = clip["id"]
            continuity_frame = (
                previous_last_frame
                if clip["use_previous_last_frame"]
                and previous_last_frame is not None
                else None
            )
            reference_specs = build_reference_list(
                clip,
                identity_paths,
                continuity_frame,
            )
            prompt = build_prompt(clip, reference_specs)
            prompt_path = AUDIT_DIR / f"clip_{clip_id}_prompt.txt"
            prompt_path.write_text(prompt, encoding="utf-8")

            request_audit: dict[str, Any] = {
                "clip_id": clip_id,
                "model": "seedance-2.0-mini",
                "duration": 5,
                "resolution": "480p",
                "aspect_ratio": "16:9",
                "generate_audio": True,
                "bitrate_mode": "high",
                "seed": clip["seed"],
                "reference_files": [str(path) for _, path in reference_specs],
                "reference_labels": [label for label, _ in reference_specs],
                "request_count": 0,
                "automatic_retries": 0,
                "estimated_usd": plan["estimated_usd_per_clip"],
                "actual_provider_cost_usd": None,
                "status": "uploading_references",
                "started_at": utc_now(),
            }
            request_path = AUDIT_DIR / f"clip_{clip_id}_request.json"
            write_json(request_path, request_audit)

            reference_urls = [
                upload_reference(client, path) for _, path in reference_specs
            ]
            request_audit["status"] = "submitting_once"
            request_audit["request_count"] = 1
            write_json(request_path, request_audit)
            manifest["request_count"] += 1
            write_json(manifest_path, manifest)

            # This is the only paid submission statement in the script. The loop
            # reaches it once for each clip and stops immediately on any failure.
            job = client.submit_async(
                "seedance-2.0-mini",
                prompt=prompt,
                reference_images=reference_urls,
                duration=5,
                resolution="480p",
                aspect_ratio="16:9",
                generate_audio=True,
                bitrate_mode="high",
                return_last_frame=True,
                seed=clip["seed"],
            )
            request_audit["request_id"] = job.request_id
            request_audit["status"] = "processing"
            write_json(request_path, request_audit)
            print(f"Clip {clip_id}: Segmind request {job.request_id}", flush=True)

            result = job.wait(timeout=1800, interval=5)
            result_path = AUDIT_DIR / f"clip_{clip_id}_result.json"
            write_json(result_path, result)
            actual_cost = extract_cost(result)
            request_audit["actual_provider_cost_usd"] = actual_cost

            video_path = RAW_DIR / f"S1E02_clip_{clip_id}_raw.mp4"
            output_url = download_video(result, video_path)
            request_audit["output_url"] = output_url
            technical_qc = probe_and_verify(
                video_path,
                clip_id,
                speech_model,
                clip["dialogue"],
            )
            previous_last_frame = make_proof(video_path, clip_id)

            request_audit["status"] = "completed"
            request_audit["completed_at"] = utc_now()
            request_audit["technical_qc"] = technical_qc
            request_audit["video_sha256"] = sha256(video_path)
            request_audit["last_frame_sha256"] = sha256(previous_last_frame)
            write_json(request_path, request_audit)

            completed.append(request_audit)
            manifest["completed_clips"] = len(completed)
            known_costs = [
                item["actual_provider_cost_usd"]
                for item in completed
                if item["actual_provider_cost_usd"] is not None
            ]
            manifest["actual_provider_cost_usd"] = (
                round(sum(known_costs), 8)
                if len(known_costs) == len(completed)
                else None
            )
            write_json(manifest_path, manifest)
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["failed_at"] = utc_now()
        manifest["error"] = str(exc)
        write_json(manifest_path, manifest)
        raise

    manifest["status"] = "completed"
    manifest["completed_at"] = utc_now()
    write_json(manifest_path, manifest)
    print("All twelve five-second clips completed exactly once.", flush=True)


if __name__ == "__main__":
    main()
