#!/usr/bin/env python3
"""Generate only S1E02 clip 12 once with Seedance 2 Mini.

The paid request is deliberately isolated: one clip, one submit statement,
zero automatic retries, and no episode merge. The output is a review artifact.
"""

from __future__ import annotations

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

from PIL import Image, ImageOps


ROOT = Path.cwd()
SOURCE_DIR = ROOT / "references" / "s1e02"
PLAN_PATH = SOURCE_DIR / "clip12_identity_v4_plan.json"
SUBTITLE_PATH = SOURCE_DIR / "clip12_identity_v4_subtitles.ass"
RAW_DIR = ROOT / "raw"
REVIEW_DIR = ROOT / "review"
AUDIT_DIR = ROOT / "audit"
PROOF_DIR = ROOT / "proof"


PROMPT = r"""
ORIGINAL SERIES PRODUCTION LOCK. Generate only one five-second 16:9 review clip
for the user's original dark forensic manga-noir series 《吸血法医·剑刺》,
S1E02《会说话的骨头》, clip 12 of 12. Use only the supplied original
storyboard and character references. Do not imitate any named artist, studio,
franchise, actor or copyrighted character.

REFERENCE AUTHORITY, IN THIS EXACT ORDER:
1. Reference image 1 is the exact four-shot storyboard order and composition
   authority only, read top-left, top-right, bottom-left, bottom-right. Its low
   resolution, faces, eyes and clothing are not identity authority.
2. Reference image 2 is the primary face, hair and white-coat identity authority
   for Jian Ci / 检刺.
3. Reference image 3 is the full-body costume, scale and same-location authority
   for Jian Ci / 检刺.
4. Reference image 4 is the sole face, build and civilian wardrobe identity
   authority for Su Wang / 苏望.

ABSOLUTE SHOT ORDER. Render four distinct full-screen shots with clean hard cuts
at about 1.15, 2.00 and 4.20 seconds. Every shot fills the complete 16:9 frame.
Never show a grid, contact sheet, split screen, panel border, storyboard page,
UI, prompt, logo, watermark, title, credits or generated subtitle.

0.00-1.15 — SHOT 1. Jian Ci alone in the cold dark interrogation suite, same
camera composition as storyboard panel 1: tight restrained three-quarter
close-up, very pale angular narrow face, layered side-part black hair, white
knee-length forensic coat over black high-neck shirt, black gloves, NO GLASSES,
both irises ordinary dark brown-black. Lin Qian is heard offscreen only and is
not visible. Jian listens without moving his lips.

1.15-2.00 — SHOT 2. Hard cut to Su Wang alone at the same metal interrogation
table, same camera composition as storyboard panel 2. He is a visibly different
and younger Chinese man: warmer skin, broader squarer face, wider jaw and eyes,
shorter blunt black hair, charcoal-gray civilian button shirt with rolled
sleeves, bare hands clasped on the table. NO white coat, NO gloves, NO badge,
NO red eyes. He does not resemble Jian Ci.

2.00-4.20 — SHOT 3. Hard cut back to Jian Ci alone, same composition as
storyboard panel 3, leaning slightly toward Su Wang across the unseen table.
White forensic coat, black high-neck shirt, black gloves, NO GLASSES, ordinary
dark eyes for this entire shot. Jian asks the question onscreen with restrained,
precise lip sync. Su Wang answers offscreen; do not cut to him and do not make
Jian mouth Su Wang's answer.

4.20-5.00 — SHOT 4. Hard cut to the exact same Jian Ci identity in the extreme
eye close-up of storyboard panel 4. Only now, for the final approximately 0.8
seconds, both irises quietly shift to restrained deep burgundy. No glow beam,
no aura, no fangs, no glasses, no face change and no supernatural spectacle.

IDENTITY LOCK. Only one man is visible in any shot. Jian Ci and Su Wang are two
different people and must never share, blend, swap or morph faces, hair,
wardrobe, body proportions or hands. Lin Qian remains offscreen for the entire
clip. No twins, duplicates, extra people, background faces, mirror people or
face drift. Only Jian Ci may show burgundy irises, and only after 4.20 seconds.

SCENE AND PROP LOCK. All four shots belong to one coherent interrogation suite
at night: the same rain-dark window, blue-black walls, brushed metal table,
single overhead pool of cold light and restrained background practicals. Keep
architecture, table edge, chair position, wardrobe and screen direction stable.
No laboratory cutaway, no street, no daylight and no changing room. Match the
storyboard's very dark, low-saturation suspense mood, fine 2D manga ink lines,
controlled cel shading, natural anatomy and subtle limited animation. Cinematic
forensic-crime direction, stable camera, shallow parallax, no glossy 3D, no
photoreal live action, no chibi and no comedy distortion.

MANDARIN AUDIO LOCK. Generate clear synchronized native Mandarin audio with
three distinct natural adult Chinese voices, quiet rain-room ambience and very
low sparse suspense music. Dialogue must be centered and louder than ambience.
Speak only these exact Chinese lines at these times, briskly but intelligibly,
without overlap, without English and without any invented words:
0.10-1.05 林浅（女声，画外）：“采购记录也吻合。”
2.05-3.20 检刺（男声，画内）：“苏望，你想让谁醒来？”
3.30-4.12 苏望（年轻男声，画外）：“我只想让他醒来。”
Do not generate visible text; deterministic Chinese-English subtitles and the
persistent series header will be added in post.

STRICT NEGATIVE: silent audio, missing Mandarin, English speech, wrong speaker,
extra dialogue, wrong person, same male face, face swap, morph, glasses, red eyes
before 4.20, red eyes on Su Wang, woman visible, extra person, wardrobe exchange,
white coat on Su Wang, bare hands on Jian, changing location, bright palette,
fantasy glow, fangs, gore, generated text, captions, credits, logo, watermark,
collage, split screen, repeated panel, skipped shot, reordered shot.
""".strip()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def validate_image(path: Path, expected_size: tuple[int, int]) -> None:
    with Image.open(path) as image:
        actual_size = image.size
        image.verify()
    if actual_size != expected_size:
        raise RuntimeError(
            f"Locked reference dimensions changed: {path} is {actual_size}, "
            f"expected {expected_size}"
        )
    width, height = actual_size
    if not (300 <= width <= 6000 and 300 <= height <= 6000):
        raise RuntimeError(f"Reference is outside Segmind side limits: {path}")
    if not 0.4 <= width / height <= 2.5:
        raise RuntimeError(f"Reference is outside Segmind aspect limits: {path}")
    if path.stat().st_size >= 30 * 1024 * 1024:
        raise RuntimeError(f"Reference exceeds Segmind size limit: {path}")


def load_and_validate_plan() -> tuple[dict[str, Any], list[Path]]:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    required = {
        "episode": "S1E02",
        "clip_id": "12",
        "model": "seedance-2.0-mini",
        "duration_seconds": 5,
        "resolution": "480p",
        "aspect_ratio": "16:9",
        "generate_audio": True,
        "automatic_retries": 0,
        "seed": 20260825,
        "review_only": True,
        "merge_after_generation": False,
    }
    for key, expected in required.items():
        if plan.get(key) != expected:
            raise RuntimeError(f"Invalid locked plan value {key}: {plan.get(key)!r}")
    references = plan.get("references")
    if not isinstance(references, list) or len(references) != 4:
        raise RuntimeError("Clip 12 must use exactly four isolated image references")
    paths: list[Path] = []
    for item in references:
        path = SOURCE_DIR / item["file"]
        validate_image(path, (int(item["width"]), int(item["height"])))
        actual_digest = sha256(path)
        if actual_digest != item["sha256"]:
            raise RuntimeError(f"Locked reference hash changed: {path}")
        paths.append(path)
    if len(plan.get("shots", [])) != 4 or len(plan.get("dialogue", [])) != 3:
        raise RuntimeError("The locked plan must contain four shots and three lines")
    for line in plan["dialogue"]:
        if not 0 <= float(line["start"]) < float(line["end"]) <= 5:
            raise RuntimeError("Dialogue timing is outside the five-second clip")
    if not SUBTITLE_PATH.is_file():
        raise RuntimeError("Locked deterministic subtitle file is missing")
    return plan, paths


def upload_reference(client: Any, path: Path) -> str:
    response = client.files.upload(path)
    urls = response.get("file_urls") if isinstance(response, dict) else None
    if not urls or not isinstance(urls[0], str):
        raise RuntimeError(f"Segmind returned no file URL for {path}: {response}")
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
    for url in dict.fromkeys(urls):
        response = requests.get(url, timeout=300)
        response.raise_for_status()
        if looks_like_video(response.content, response.headers.get("content-type", ""), url):
            target.write_bytes(response.content)
            return url
    raise RuntimeError(f"Segmind completed without a downloadable video: {urls}")


def probe_video(path: Path, require_mandarin: bool) -> dict[str, Any]:
    if path.stat().st_size < 150_000:
        raise RuntimeError(f"Video is unexpectedly small: {path.stat().st_size} bytes")
    probe = json.loads(
        run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ]
        ).stdout
    )
    streams = probe.get("streams", [])
    videos = [stream for stream in streams if stream.get("codec_type") == "video"]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if not videos or not audios:
        raise RuntimeError("Clip 12 must contain both video and audio streams")
    duration = float(probe.get("format", {}).get("duration") or 0)
    if not 4.3 <= duration <= 5.8:
        raise RuntimeError(f"Clip 12 duration is invalid: {duration}")
    audio_duration = float(audios[0].get("duration") or duration)
    if audio_duration < 4.0:
        raise RuntimeError(f"Clip 12 audio stream is too short: {audio_duration}")
    run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"])
    loudness = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
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
    match = re.search(
        r"max_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB", loudness.stderr
    )
    if not match or match.group(1) == "-inf" or float(match.group(1)) < -55:
        raise RuntimeError("Clip 12 audio track is silent or effectively inaudible")
    result: dict[str, Any] = {
        "duration": duration,
        "size_bytes": path.stat().st_size,
        "video_codec": videos[0].get("codec_name"),
        "width": videos[0].get("width"),
        "height": videos[0].get("height"),
        "audio_codec": audios[0].get("codec_name"),
        "audio_channels": audios[0].get("channels"),
        "audio_duration": audio_duration,
        "max_volume_db": float(match.group(1)),
        "ffprobe": probe,
        "loudness_log": loudness.stderr,
    }
    if require_mandarin:
        from faster_whisper import WhisperModel

        model = WhisperModel(
            "tiny",
            device="cpu",
            compute_type="int8",
            download_root=os.environ.get("WHISPER_CACHE_DIR", "whisper_cache"),
        )
        segments, info = model.transcribe(
            str(path),
            language="zh",
            task="transcribe",
            beam_size=1,
            temperature=0,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 250},
            condition_on_previous_text=False,
        )
        rows = [
            {"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
            for s in segments
            if s.text.strip()
        ]
        transcript = "".join(row["text"] for row in rows)
        speech_seconds = sum(max(0.0, row["end"] - row["start"]) for row in rows)
        cjk_count = len(re.findall(r"[\u3400-\u9fff]", transcript))
        result["speech_check"] = {
            "language_forced": "zh",
            "reported_language": getattr(info, "language", None),
            "transcript": transcript,
            "cjk_character_count": cjk_count,
            "detected_speech_seconds": speech_seconds,
            "segments": rows,
        }
        if speech_seconds < 0.40 or cjk_count < 2:
            raise RuntimeError("Audio exists but Mandarin speech could not be verified")
    return result


def make_review(raw_path: Path, review_path: Path) -> None:
    font_dir = Path("/usr/share/fonts/opentype/noto")
    ass_filter = f"ass={SUBTITLE_PATH}"
    if font_dir.is_dir():
        ass_filter += f":fontsdir={font_dir}"
    video_filter = (
        "scale=1280:720:force_original_aspect_ratio=decrease,"
        "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black," + ass_filter
    )
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(raw_path),
            "-vf",
            video_filter,
            "-af",
            "loudnorm=I=-16:LRA=7:TP=-1.5",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "16",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(review_path),
        ]
    )


def make_proofs(video_path: Path) -> list[Path]:
    times = (0.60, 1.55, 2.80, 4.60)
    frames: list[Path] = []
    for index, timestamp in enumerate(times, start=1):
        target = PROOF_DIR / f"clip12_frame_{index}_{timestamp:.2f}s.jpg"
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{timestamp:.2f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(target),
            ]
        )
        frames.append(target)
    canvas = Image.new("RGB", (1280, 720), (4, 8, 13))
    for index, path in enumerate(frames):
        with Image.open(path).convert("RGB") as image:
            tile = ImageOps.fit(image, (640, 360), Image.Resampling.LANCZOS)
            canvas.paste(tile, ((index % 2) * 640, (index // 2) * 360))
    contact = PROOF_DIR / "S1E02_clip12_identity_v4_contact.jpg"
    canvas.save(contact, quality=95)
    return frames + [contact]


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


def prepare_only() -> None:
    plan, paths = load_and_validate_plan()
    print(
        json.dumps(
            {
                "status": "prepared",
                "episode": plan["episode"],
                "clip_id": plan["clip_id"],
                "request_count": 0,
                "automatic_retries": 0,
                "reference_count": len(paths),
                "reference_sha256": {str(path): sha256(path) for path in paths},
                "prompt_sha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    plan, reference_paths = load_and_validate_plan()
    if not os.environ.get("SEGMIND_API_KEY"):
        raise RuntimeError("SEGMIND_API_KEY is missing; no paid request made")
    for directory in (RAW_DIR, REVIEW_DIR, AUDIT_DIR, PROOF_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    manifest_path = AUDIT_DIR / "clip12_identity_v4_manifest.json"
    request_path = AUDIT_DIR / "clip12_identity_v4_request.json"
    manifest: dict[str, Any] = {
        "episode": "S1E02",
        "clip_id": "12",
        "model": "seedance-2.0-mini",
        "started_at": utc_now(),
        "planned_requests": 1,
        "request_count": 0,
        "automatic_retries": 0,
        "estimated_usd": plan["estimated_usd"],
        "actual_provider_cost_usd": None,
        "review_only": True,
        "merged": False,
        "status": "uploading_references",
    }
    write_json(manifest_path, manifest)
    (AUDIT_DIR / "clip12_identity_v4_prompt.txt").write_text(PROMPT, encoding="utf-8")
    request: dict[str, Any] = {
        "model": "seedance-2.0-mini",
        "duration": 5,
        "resolution": "480p",
        "aspect_ratio": "16:9",
        "generate_audio": True,
        "bitrate_mode": "high",
        "return_last_frame": True,
        "seed": 20260825,
        "automatic_retries": 0,
        "request_count": 0,
        "reference_files": [str(path) for path in reference_paths],
        "reference_sha256": {str(path): sha256(path) for path in reference_paths},
        "prompt_sha256": hashlib.sha256(PROMPT.encode("utf-8")).hexdigest(),
        "status": "uploading_references",
        "started_at": utc_now(),
    }
    write_json(request_path, request)
    try:
        from segmind import SegmindClient

        client = SegmindClient()
        reference_urls = [upload_reference(client, path) for path in reference_paths]
        request["status"] = "submitting_once"
        request["request_count"] = 1
        manifest["request_count"] = 1
        manifest["status"] = "submitting_once"
        write_json(request_path, request)
        write_json(manifest_path, manifest)

        # The script contains exactly one paid submission statement and no loop.
        job = client.submit_async(
            "seedance-2.0-mini",
            prompt=PROMPT,
            reference_images=reference_urls,
            duration=5,
            resolution="480p",
            aspect_ratio="16:9",
            generate_audio=True,
            bitrate_mode="high",
            return_last_frame=True,
            seed=20260825,
        )
        request["request_id"] = job.request_id
        request["status"] = "processing"
        manifest["request_id"] = job.request_id
        manifest["status"] = "processing"
        write_json(request_path, request)
        write_json(manifest_path, manifest)
        print(f"S1E02 clip 12: Segmind request {job.request_id}", flush=True)

        result = job.wait(timeout=1800, interval=5)
        write_json(AUDIT_DIR / "clip12_identity_v4_result.json", result)
        actual_cost = extract_cost(result)
        raw_path = RAW_DIR / "S1E02_clip_12_identity_v4_RAW.mp4"
        output_url = download_video(result, raw_path)
        raw_qc = probe_video(raw_path, require_mandarin=True)
        review_path = REVIEW_DIR / "S1E02_clip_12_identity_v4_REVIEW.mp4"
        make_review(raw_path, review_path)
        review_qc = probe_video(review_path, require_mandarin=False)
        proof_paths = make_proofs(review_path)

        request.update(
            {
                "status": "completed",
                "completed_at": utc_now(),
                "output_url": output_url,
                "actual_provider_cost_usd": actual_cost,
                "raw_video": str(raw_path),
                "raw_video_sha256": sha256(raw_path),
                "review_video": str(review_path),
                "review_video_sha256": sha256(review_path),
                "proof_files": [str(path) for path in proof_paths],
                "raw_qc": raw_qc,
                "review_qc": review_qc,
            }
        )
        manifest.update(
            {
                "status": "completed",
                "completed_at": utc_now(),
                "actual_provider_cost_usd": actual_cost,
                "raw_video_sha256": sha256(raw_path),
                "review_video_sha256": sha256(review_path),
            }
        )
        write_json(request_path, request)
        write_json(manifest_path, manifest)
        print("S1E02 clip 12 completed exactly once; no merge performed.", flush=True)
    except Exception as exc:
        request["status"] = "failed"
        request["failed_at"] = utc_now()
        request["error"] = str(exc)
        manifest["status"] = "failed"
        manifest["failed_at"] = utc_now()
        manifest["error"] = str(exc)
        write_json(request_path, request)
        write_json(manifest_path, manifest)
        raise


if __name__ == "__main__":
    if "--prepare-only" in sys.argv:
        prepare_only()
    else:
        main()
