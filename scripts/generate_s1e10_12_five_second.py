#!/usr/bin/env python3
"""Generate the locked S01E10-12 clips once each, with no retry path."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from base64 import b64decode
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image, ImageOps


ROOT = Path.cwd()
PLAN_PATH = ROOT / "references" / "s1e10-12" / "production_plan.json"
SOURCE = PLAN_PATH.parent
OUT = ROOT / os.environ.get("GENERATION_OUTPUT_DIR", "output/s1e10-12-all")
S1E03 = ROOT / "references" / "s1e03" / "source_refs"
JIAN = S1E03 / "jian_ci_identity.jpg"
CHART = S1E03 / "character_chart_highres.jpeg"
TANG = SOURCE / "identity_refs" / "tang_yun.jpg"
E09_PANEL_1 = ROOT / "references" / "s1e09" / "panels" / "clip_01_shot_1.jpg.b64"
E09_PANEL_12 = ROOT / "references" / "s1e09" / "panels" / "clip_12_shot_4.jpg.b64"
S1E11_BOARDS = SOURCE / "s1e11_storyboard_refs"

IDENTITY_CROPS = {
    "lin_qian": (208, 245, 408, 661),
    "zhou_qiao": (411, 245, 613, 661),
    "xu_wei": (616, 245, 819, 661),
    "han_che": (821, 245, 1019, 661),
}

VOICE_LOCK = {
    "剑刺": "low, restrained adult Mandarin male voice",
    "林浅": "steady mid-low adult Mandarin female investigator voice",
    "周峤": "precise measured young adult Mandarin male voice",
    "许未": "clear, firm adult Mandarin female forensic voice",
    "韩彻": "calm authoritative mature Mandarin male voice",
    "唐筠": "tired, controlled adult Mandarin female voice",
    "方阿姨": "gentle elderly Mandarin female voice, clear and unforced",
    "旁白": "quiet, grounded Mandarin narrator voice",
}


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def sha(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def shell(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def image_ok(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < 5_000 or path.stat().st_size > 30 * 1024 * 1024:
        raise RuntimeError(f"Invalid reference: {path}")
    with Image.open(path) as image:
        width, height = image.size
        image.verify()
    if width < 200 or height < 200:
        raise RuntimeError(f"Reference too small: {path}")


def decode_b64(source: Path, target: Path) -> Path:
    if not source.is_file():
        raise RuntimeError(f"Missing locked reference: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_bytes(b64decode(source.read_text(encoding="ascii"), validate=True))
    except Exception as exc:
        raise RuntimeError(f"Invalid locked base64 reference: {source}") from exc
    image_ok(target)
    return target


def locked_b64_image_ok(source: Path) -> None:
    """Validate every board during preflight, before any paid request can start."""
    if not source.is_file():
        raise RuntimeError(f"Missing locked reference: {source}")
    try:
        data = b64decode(source.read_text(encoding="ascii"), validate=True)
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
            image.verify()
    except Exception as exc:
        raise RuntimeError(f"Invalid locked base64 reference: {source}") from exc
    if not 5_000 <= len(data) <= 30 * 1024 * 1024 or width < 200 or height < 200:
        raise RuntimeError(f"Invalid locked reference dimensions: {source}")


def episode_dirs(code: str) -> dict[str, Path]:
    root = OUT / code
    result = {name: root / name for name in ("runtime_refs", "raw", "audit", "proof", "last_frames")}
    for directory in result.values():
        directory.mkdir(parents=True, exist_ok=True)
    return result


def identity(name: str, runtime: Path) -> Path:
    if name == "jian_ci":
        image_ok(JIAN)
        return JIAN
    if name == "tang_yun":
        image_ok(TANG)
        return TANG
    if name not in IDENTITY_CROPS:
        raise RuntimeError(f"No fixed identity asset is needed or known for {name}")
    target = runtime / f"identity_{name}.jpg"
    if not target.exists():
        image_ok(CHART)
        with Image.open(CHART) as chart:
            crop = chart.convert("RGB").crop(IDENTITY_CROPS[name])
            ImageOps.fit(crop, (320, 480), Image.Resampling.LANCZOS).save(target, quality=95)
    image_ok(target)
    return target


def storyboard_board(episode: str, clip_id: str, runtime: Path) -> Path | None:
    """Decode S01E11's locked board for that exact five-second clip."""
    if episode != "S01E11":
        return None
    source = S1E11_BOARDS / f"S01E11_{clip_id}_board.jpg.b64"
    target = runtime / f"S01E11_{clip_id}_board.jpg"
    return decode_b64(source, target)


def find_urls(data: Any, results: list[str]) -> None:
    if isinstance(data, str) and data.startswith(("http://", "https://")):
        results.append(data)
    elif isinstance(data, dict):
        for value in data.values():
            find_urls(value, results)
    elif isinstance(data, list):
        for value in data:
            find_urls(value, results)


def upload(client: Any, path: Path) -> str:
    response = client.files.upload(path)
    urls = response.get("file_urls") if isinstance(response, dict) else None
    if not urls or not isinstance(urls[0], str):
        raise RuntimeError(f"Reference upload failed: {path}")
    return urls[0]


def fetch_video(result: Any, target: Path) -> str:
    import requests

    candidates: list[str] = []
    find_urls(result.get("output", result) if isinstance(result, dict) else result, candidates)
    for url in dict.fromkeys(candidates):
        response = requests.get(url, timeout=300)
        response.raise_for_status()
        data = response.content
        suffix = Path(urlparse(url).path).suffix.lower()
        content_type = response.headers.get("content-type", "").lower()
        if data[4:8] == b"ftyp" or "video/" in content_type or suffix in {".mp4", ".mov", ".webm"}:
            target.write_bytes(data)
            return url
    raise RuntimeError("Provider returned no video")


def make_proof(video: Path, folders: dict[str, Path], clip_id: str) -> Path:
    last = folders["last_frames"] / f"clip_{clip_id}_continuity.jpg"
    contact = folders["proof"] / f"clip_{clip_id}_three_shot_contact.jpg"
    shell(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "4.70", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(last)])
    shell([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video),
        "-vf", "fps=0.6,scale=427:240:force_original_aspect_ratio=decrease,pad=427:240:(ow-iw)/2:(oh-ih)/2:black,tile=3x1:padding=4:margin=4",
        "-frames:v", "1", "-q:v", "2", str(contact),
    ])
    image_ok(last)
    image_ok(contact)
    return last


def verify(video: Path, clip: dict[str, Any], model: Any, folders: dict[str, Path]) -> dict[str, Any]:
    probe = json.loads(shell(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)]).stdout)
    streams = probe.get("streams", [])
    visual = [item for item in streams if item.get("codec_type") == "video"]
    audio = [item for item in streams if item.get("codec_type") == "audio"]
    duration = float(probe.get("format", {}).get("duration") or 0)
    if video.stat().st_size < 200_000 or not visual or not audio or not 4.3 <= duration <= 5.8:
        raise RuntimeError(f"Clip {clip['id']} technical video/audio QC failed")
    loud = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vn", "-af", "volumedetect", "-f", "null", "-"],
        check=False, capture_output=True, text=True,
    )
    level = re.search(r"max_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB", loud.stderr)
    if not level or level.group(1) == "-inf" or float(level.group(1)) < -55:
        raise RuntimeError(f"Clip {clip['id']} is silent")
    iterator, info = model.transcribe(
        str(video), language="zh", task="transcribe", beam_size=1, vad_filter=True, condition_on_previous_text=False
    )
    segments = [
        {"start": float(item.start), "end": float(item.end), "text": item.text.strip()}
        for item in iterator if item.text.strip()
    ]
    transcript = "".join(item["text"] for item in segments)
    speech_seconds = sum(item["end"] - item["start"] for item in segments)
    if speech_seconds < 0.40 or len(re.findall(r"[\u3400-\u9fff]", transcript)) < 2:
        raise RuntimeError(f"Clip {clip['id']} Mandarin ASR QC failed")
    dump(folders["audit"] / f"clip_{clip['id']}_ffprobe.json", probe)
    (folders["audit"] / f"clip_{clip['id']}_loudness.txt").write_text(loud.stderr, encoding="utf-8")
    dump(
        folders["audit"] / f"clip_{clip['id']}_speech.json",
        {
            "language": getattr(info, "language", None),
            "segments": segments,
            "transcript": transcript,
            "expected": [line["zh"] for line in clip["dialogue"]],
        },
    )
    return {
        "duration": duration,
        "width": visual[0].get("width"),
        "height": visual[0].get("height"),
        "audio_codec": audio[0].get("codec_name"),
        "max_volume_db": float(level.group(1)),
        "asr": transcript,
        "speech_segments": segments,
    }


def load_plan() -> dict[str, Any]:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    lock = {
        "model": "seedance-2.0-mini", "resolution": "480p", "aspect_ratio": "16:9",
        "duration_seconds_per_clip": 5, "clips_per_episode": 12, "shots_per_clip": 3, "automatic_retries": 0,
    }
    for key, expected in lock.items():
        if plan.get(key) != expected:
            raise RuntimeError(f"Production lock failed: {key}")
    episodes = plan.get("episodes")
    expected_episodes = ["S01E10", "S01E11", "S01E12"]
    if not isinstance(episodes, list) or [item.get("episode") for item in episodes] != expected_episodes:
        raise RuntimeError("Plan must retain S01E10, S01E11 and S01E12 in order")
    for episode in episodes:
        clips = episode.get("clips")
        if not isinstance(clips, list) or [item.get("id") for item in clips] != [f"{value:02d}" for value in range(1, 13)]:
            raise RuntimeError(f"{episode['episode']} must contain clips 01 through 12 in order")
        for clip in clips:
            if len(clip.get("shots", [])) != 3 or len(clip.get("dialogue", [])) != 1:
                raise RuntimeError(f"{episode['episode']} clip {clip.get('id')} must have exactly three shots and one approved voice cue")
            cue = clip["dialogue"][0]
            if cue["speaker"] not in VOICE_LOCK or not 0 <= float(cue["start"]) < float(cue["end"]) <= 5:
                raise RuntimeError(f"Invalid voice cue in {episode['episode']} clip {clip['id']}")
    for required in (JIAN, CHART, TANG, E09_PANEL_1, E09_PANEL_12):
        if not required.is_file():
            raise RuntimeError(f"Required locked source is missing: {required}")
    image_ok(JIAN)
    image_ok(CHART)
    image_ok(TANG)
    for clip_id in (f"{value:02d}" for value in range(1, 13)):
        locked_b64_image_ok(S1E11_BOARDS / f"S01E11_{clip_id}_board.jpg.b64")
    return plan


def build_prompt(plan: dict[str, Any], episode: dict[str, Any], clip: dict[str, Any], reference_names: list[str], has_board: bool) -> str:
    shots = "\n".join(f"{index + 1}. {item}" for index, item in enumerate(clip["shots"]))
    cue = clip["dialogue"][0]
    names = ", ".join(reference_names) if reference_names else "no additional recurring character"
    return f"""ORIGINAL SERIES PRODUCTION LOCK. Render exactly one clean five-second 16:9 animated clip for 《吸血法医·剑刺》{episode['episode']}《{episode['title_zh']}》, case《{episode['case_zh']}》, clip {clip['id']} of 12. Original dark forensic manga-noir only; never imitate a named artist, studio, franchise or copyrighted character.

REFERENCE ORDER IS LOCKED. References 1 and 2 are visual-style and cinematic-lighting authorities from the accepted series. The following images are fixed identity authorities for {names}.{" The next image is the locked S01E11 storyboard authority for this exact clip: preserve its cast, wardrobe, props, location, framing and the three-shot order, but render a full-screen moving scene rather than a board." if has_board else ""} The final image is the previous accepted continuity frame, controlling only the opening light, screen direction and scene geography. Never render a board, grid, panel, split-screen, title, subtitle, logo, watermark, readable UI, readable report or generated text.

RENDER EXACTLY THREE FULL-SCREEN CINEMATIC SHOTS IN THE GIVEN TIMING:
{shots}

CHARACTER LOCK. {plan['character_lock']}
CRITICAL: Jian Ci never wears glasses. Only Zhou Qiao wears silver-rim glasses and a hearing device. Preserve faces, hair, age, clothing, body scale, props and screen direction. Never duplicate a character, introduce an extra character, change wardrobe, give someone a weapon, or make Tang Yun look like a melodramatic villain.

VISUAL / STORY LOCK. {plan['visual_lock']} {plan['case_continuity']} {episode['continuity']} Current clip scene: {clip['scene']}. Each 1.66-second shot has only one motivated action and one dominant emotion. Evidence handling is always gloved, photographed, sealed and separate. Drowning is a conclusion built from multiple independent findings, never a single magic test. Jian Ci's hunger is a private danger only; it never solves a case and never harms any person.

MANDARIN AUDIO LOCK. Generate synchronized clear native Mandarin audio with restrained room tone and a subtle low industrial suspense pulse. Use the fixed voice quality: {VOICE_LOCK[cue['speaker']]}. Speak only this exact Chinese line during {float(cue['start']):.2f}-{float(cue['end']):.2f}, with no overlap, English, singing, invented dialogue or silence: {cue['speaker']}：“{cue['zh']}”
Do not generate visible subtitles. The permanent title header and clear Chinese/English subtitles will be burned in after technical and speech QC.

STRICT NEGATIVE: {plan['global_negative']}"""


def selected_episodes(plan: dict[str, Any], episode_code: str | None) -> list[dict[str, Any]]:
    episodes = plan["episodes"]
    if episode_code is None:
        return episodes
    selected = [episode for episode in episodes if episode["episode"] == episode_code]
    if len(selected) != 1:
        raise RuntimeError(f"Unknown locked episode: {episode_code}")
    return selected


def preflight(episode_code: str | None = None) -> None:
    plan = load_plan()
    episodes = selected_episodes(plan, episode_code)
    print(f"Preflight passed: {[episode['episode'] for episode in episodes]}, {len(episodes) * 12} ordered clips, three shots per clip, 480p Seedance 2 mini, audio + bilingual subtitle QA, no automatic retries.")


def generate(episode_code: str | None = None) -> None:
    plan = load_plan()
    episodes = selected_episodes(plan, episode_code)
    if not os.environ.get("SEGMIND_API_KEY"):
        raise RuntimeError("SEGMIND_API_KEY is missing; no paid request made")
    from faster_whisper import WhisperModel
    from segmind import SegmindClient

    model = WhisperModel("tiny", device="cpu", compute_type="int8", download_root=os.environ.get("WHISPER_CACHE_DIR", "whisper_cache"))
    client = SegmindClient()
    style_runtime = OUT / "shared_runtime_refs"
    style_one = decode_b64(E09_PANEL_1, style_runtime / "s1e09_style_rain_laptop.jpg")
    style_two = decode_b64(E09_PANEL_12, style_runtime / "s1e09_style_blue_drive.jpg")
    previous: Path = style_two
    manifest: dict[str, Any] = {
        "episodes": [item["episode"] for item in episodes], "request_count": 0,
        "automatic_retries": 0, "status": "running", "started_at": stamp(), "plan_sha256": sha(PLAN_PATH), "clips": [],
    }
    manifest_path = OUT / "generation_manifest.json"
    dump(manifest_path, manifest)
    request_index = 0
    try:
        for episode in episodes:
            folders = episode_dirs(episode["episode"])
            for clip in episode["clips"]:
                request_index += 1
                ids = [
                    identity(name, folders["runtime_refs"])
                    for name in clip["characters"]
                    if name in {"jian_ci", "lin_qian", "zhou_qiao", "xu_wei", "han_che", "tang_yun"}
                ]
                names = [name for name in clip["characters"] if name in {"jian_ci", "lin_qian", "zhou_qiao", "xu_wei", "han_che", "tang_yun"}]
                board = storyboard_board(episode["episode"], clip["id"], folders["runtime_refs"])
                refs = [style_one, style_two, *ids, *([board] if board else []), previous]
                if len(refs) > 9:
                    raise RuntimeError(f"Too many references for {episode['episode']} clip {clip['id']}")
                for path in refs:
                    image_ok(path)
                prompt = build_prompt(plan, episode, clip, names, board is not None)
                prompt_file = folders["audit"] / f"clip_{clip['id']}_prompt.txt"
                prompt_file.write_text(prompt, encoding="utf-8")
                record: dict[str, Any] = {
                    "episode": episode["episode"], "clip_id": clip["id"], "status": "submitting_once", "request_count": 1,
                    "automatic_retries": 0, "references": [str(item) for item in refs], "started_at": stamp(),
                }
                dump(folders["audit"] / f"clip_{clip['id']}_request.json", record)
                urls = [upload(client, path) for path in refs]
                # The only paid request for this clip. There is deliberately no retry branch.
                job = client.submit_async(
                    "seedance-2.0-mini", prompt=prompt, reference_images=urls, duration=5, resolution="480p",
                    aspect_ratio="16:9", generate_audio=True, bitrate_mode="high", return_last_frame=True, seed=202608100 + request_index,
                )
                record.update({"request_id": job.request_id, "status": "processing"})
                manifest["request_count"] += 1
                dump(folders["audit"] / f"clip_{clip['id']}_request.json", record)
                dump(manifest_path, manifest)
                result = job.wait(timeout=1800, interval=5)
                dump(folders["audit"] / f"clip_{clip['id']}_result.json", result)
                video = folders["raw"] / f"{episode['episode']}_clip_{clip['id']}_raw.mp4"
                record["output_url"] = fetch_video(result, video)
                record["technical_qc"] = verify(video, clip, model, folders)
                previous = make_proof(video, folders, clip["id"])
                record.update({"status": "completed", "completed_at": stamp(), "video_sha256": sha(video), "continuity_sha256": sha(previous)})
                manifest["clips"].append(record)
                dump(folders["audit"] / f"clip_{clip['id']}_request.json", record)
                dump(manifest_path, manifest)
        manifest.update({"status": "completed", "completed_at": stamp()})
        dump(manifest_path, manifest)
    except Exception as exc:
        manifest.update({"status": "failed", "failed_at": stamp(), "error": f"{type(exc).__name__}: {exc}"})
        dump(manifest_path, manifest)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--episode", choices=["S01E10", "S01E11", "S01E12"])
    args = parser.parse_args()
    try:
        if args.preflight:
            preflight(args.episode)
        else:
            generate(args.episode)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
