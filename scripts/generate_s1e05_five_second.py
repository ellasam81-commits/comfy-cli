#!/usr/bin/env python3
"""Generate locked S01E05 five-second clips once each, with no retry path."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from base64 import b64decode
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image, ImageOps


ROOT = Path.cwd()
SOURCE = ROOT / "references" / "s1e05"
PLAN_PATH = SOURCE / "five_second_plan.json"
OUTPUT = ROOT / os.environ.get("GENERATION_OUTPUT_DIR", "output/s1e05-gate")
RUNTIME, RAW, AUDIT, PROOF, LAST = [OUTPUT / item for item in ("runtime_refs", "raw", "audit", "proof", "last_frames")]
S1E03_REFS = ROOT / "references" / "s1e03" / "source_refs"
JIAN_IDENTITY = S1E03_REFS / "jian_ci_identity.jpg"
CHARACTER_CHART = S1E03_REFS / "character_chart_highres.jpeg"
SHEN_MI_IDENTITY = SOURCE / "identity_refs" / "shen_mi_deceased.jpg"
IDENTITY_CROPS = {
    "lin_qian": (208, 245, 408, 661),
    "zhou_qiao": (411, 245, 613, 661),
    "xu_wei": (616, 245, 819, 661),
    "han_che": (821, 245, 1019, 661),
}


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def sha(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def shell(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def image_ok(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < 10_000 or path.stat().st_size > 30 * 1024 * 1024:
        raise RuntimeError(f"Invalid reference: {path}")
    with Image.open(path) as image:
        width, height = image.size
        image.verify()
    if width < 200 or height < 200:
        raise RuntimeError(f"Reference too small: {path}")


def decode_panel(clip_id: str, index: int) -> Path:
    """Decode a compact, committed storyboard panel before upload to Segmind.

    Only the three finished panel crops are kept in the remote render branch.
    This keeps the workflow self-contained without substituting or regenerating a
    storyboard at execution time.
    """
    encoded = SOURCE / "panels" / f"clip_{clip_id}_shot_{index}.jpg.b64"
    target = RUNTIME / f"clip_{clip_id}_shot_{index}.jpg"
    if not encoded.is_file():
        raise RuntimeError(f"Missing locked storyboard panel: {encoded}")
    try:
        target.write_bytes(b64decode(encoded.read_text(encoding="ascii"), validate=True))
    except Exception as exc:
        raise RuntimeError(f"Invalid locked storyboard panel: {encoded}") from exc
    image_ok(target)
    return target


def identity(name: str) -> Path:
    """Create stable identity crops from the already-versioned S1E03 character chart."""
    if name == "jian_ci":
        image_ok(JIAN_IDENTITY)
        return JIAN_IDENTITY
    if name == "shen_mi":
        image_ok(SHEN_MI_IDENTITY)
        return SHEN_MI_IDENTITY
    if name not in IDENTITY_CROPS:
        raise RuntimeError(f"Unknown character identity: {name}")
    target = RUNTIME / f"identity_{name}.jpg"
    if not target.exists():
        image_ok(CHARACTER_CHART)
        with Image.open(CHARACTER_CHART) as chart:
            crop = chart.convert("RGB").crop(IDENTITY_CROPS[name])
            ImageOps.fit(crop, (320, 480), Image.Resampling.LANCZOS).save(target, quality=94)
    image_ok(target)
    return target


def initial_frame(panels: list[Path]) -> Path:
    url = os.environ.get("PREVIOUS_VIDEO_URL")
    if url:
        import requests

        video = RUNTIME / "previous_clip.mp4"
        response = requests.get(url, timeout=300)
        response.raise_for_status()
        video.write_bytes(response.content)
        if video.stat().st_size < 200_000:
            raise RuntimeError("Previous accepted video is invalid; no paid request made")
        target = RUNTIME / "previous_clip_last.jpg"
        shell(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "4.70", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(target)])
        image_ok(target)
        return target
    # The one-shot opening gate has no previous clip URL yet. Its first locked
    # storyboard panel is the continuity authority; later clips use the prior
    # accepted rendered last frame through PREVIOUS_VIDEO_URL.
    return panels[0]


def load_plan() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    locked = {
        "episode": "S01E05", "model": "seedance-2.0-mini", "duration_seconds_per_clip": 5,
        "clip_count": 12, "shots_per_clip": 3, "resolution": "480p", "aspect_ratio": "16:9",
    }
    for key, expected in locked.items():
        if plan.get(key) != expected:
            raise RuntimeError(f"Plan lock failed: {key}")
    clips = plan.get("clips")
    if not isinstance(clips, list) or [item.get("id") for item in clips] != [f"{i:02d}" for i in range(1, 13)]:
        raise RuntimeError("Plan must contain clips 01 through 12 in order")
    selected = os.environ.get("ONLY_CLIP_ID")
    selected_many = os.environ.get("ONLY_CLIP_IDS")
    if selected and selected_many:
        raise RuntimeError("Set ONLY_CLIP_ID or ONLY_CLIP_IDS, never both")
    if selected:
        clips = [item for item in clips if item.get("id") == selected]
        if len(clips) != 1:
            raise RuntimeError("ONLY_CLIP_ID must name exactly one locked clip")
    if selected_many:
        wanted = [value.strip() for value in selected_many.split(",") if value.strip()]
        if not wanted or wanted != sorted(set(wanted)) or any(not re.fullmatch(r"(?:0[1-9]|1[0-2])", value) for value in wanted):
            raise RuntimeError("ONLY_CLIP_IDS must be a unique ascending comma-separated clip list")
        clips = [item for item in clips if item.get("id") in wanted]
        if [item.get("id") for item in clips] != wanted:
            raise RuntimeError("ONLY_CLIP_IDS must name locked clips exactly")
    for clip in clips:
        if len(clip.get("shots", [])) != 3 or not clip.get("dialogue"):
            raise RuntimeError(f"Clip {clip.get('id')} is not a three-shot spoken clip")
        for line in clip["dialogue"]:
            start = float(line.get("start", 0.20))
            end = float(line.get("end", 4.55))
            if not 0 <= start < end <= 5:
                raise RuntimeError(f"Invalid dialogue timing in clip {clip['id']}")
    for path in [PLAN_PATH, JIAN_IDENTITY, CHARACTER_CHART, SHEN_MI_IDENTITY]:
        image_ok(path) if path.suffix.lower() in {".jpg", ".jpeg", ".png"} else None
    return plan, clips


def prepare(clip: dict[str, Any]) -> tuple[list[Path], list[Path]]:
    panels = [decode_panel(clip["id"], index) for index in range(1, 4)]
    identities = [identity(name) for name in clip["characters"]]
    for path in identities:
        image_ok(path)
    if "jian_ci" in clip["characters"] and identities[clip["characters"].index("jian_ci")] != JIAN_IDENTITY:
        raise RuntimeError("Jian Ci's no-glasses identity authority is missing")
    return panels, identities


def build_prompt(plan: dict[str, Any], clip: dict[str, Any]) -> str:
    shots = "\n".join(f"{index + 1}. {value}" for index, value in enumerate(clip["shots"]))
    speech = "\n".join(
        f"{float(line.get('start', 0.20)):.2f}-{float(line.get('end', 4.55)):.2f} {line['speaker']}: {line['zh']}"
        for line in clip["dialogue"]
    )
    profiles = "\n".join(plan["character_lock"].split(". "))
    identity_order = "\n".join(
        f"Identity reference {index + 4}: {name}."
        for index, name in enumerate(clip["characters"])
    )
    return f"""ORIGINAL SERIES PRODUCTION LOCK. Render exactly one clean five-second 16:9 animated clip for 《吸血法医·剑刺》S01E05《血是谁的》, clip {clip['id']} of 12. Original dark forensic manga-noir only; never imitate a named artist, studio, franchise or copyrighted character.

REFERENCE ORDER IS LOCKED. References 1-3 are the three storyboard shot authorities. They define composition, character positions, action and handed props. Following images are identity authorities only:
{identity_order}
The final image is the previous accepted continuity frame; it controls opening light and screen direction only. Never show a board, grid, panel, collage, title, subtitle, logo, watermark, UI, readable label or generated text.

RENDER EXACTLY THREE FULL-SCREEN CINEMATIC SHOTS:
{shots}

CHARACTER LOCK. {profiles}
CRITICAL: Jian Ci / 剑刺 NEVER wears glasses. Only Zhou Qiao / 周峤 wears silver-rim glasses and a hearing device. Preserve faces, hair, costume, age, body scale, scene geography and props. No face swap, duplicate person, wardrobe drift, extra crowd or distorted hands.

VISUAL / FORENSIC LOCK. {clip['scene']}. Cold blue-black rain-dark 2D manga cinema: clean fine ink linework, restrained cel shading, cinematic light falloff, controlled contrast, stable camera axis, subtle motivated camera movement, natural blink and breath. It must never become a static concept poster, live action, photoreal, 3D or chibi. Evidence is gloved, sealed and procedurally handled. DNA, door access and medical history are only investigative directions, never a legal conclusion by themselves. No early declaration that Tao Wen is guilty. Jian Ci's vampire physiology never proves a case.

MANDARIN AUDIO LOCK. Generate synchronized clear native Mandarin audio with restrained room tone and a low subtle industrial pulse. Speak only the exact Chinese line(s) below, clearly above ambience, without overlap, English, invented speech or silence:
{speech}
Do not generate visible subtitles. The persistent header and clear Chinese/English subtitles are burned in after all clip and audio QC.

STRICT NEGATIVE: {plan['global_negative']}"""


def upload(client: Any, path: Path) -> str:
    result = client.files.upload(path)
    urls = result.get("file_urls") if isinstance(result, dict) else None
    if not urls or not isinstance(urls[0], str):
        raise RuntimeError(f"Reference upload failed: {path}")
    return urls[0]


def find_urls(data: Any, out: list[str]) -> None:
    if isinstance(data, str) and data.startswith(("https://", "http://")):
        out.append(data)
    elif isinstance(data, dict):
        for value in data.values():
            find_urls(value, out)
    elif isinstance(data, list):
        for value in data:
            find_urls(value, out)


def fetch_video(result: Any, target: Path) -> str:
    import requests

    candidates: list[str] = []
    find_urls(result.get("output", result) if isinstance(result, dict) else result, candidates)
    for url in dict.fromkeys(candidates):
        response = requests.get(url, timeout=300)
        response.raise_for_status()
        data = response.content
        if data[4:8] == b"ftyp" or "video/" in response.headers.get("content-type", "").lower() or Path(urlparse(url).path).suffix.lower() in {".mp4", ".mov", ".webm"}:
            target.write_bytes(data)
            return url
    raise RuntimeError("Provider returned no video")


def verify(video: Path, clip: dict[str, Any], model: Any) -> dict[str, Any]:
    probe = json.loads(shell(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)]).stdout)
    streams = probe.get("streams", [])
    visual = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
    duration = float(probe.get("format", {}).get("duration") or 0)
    if video.stat().st_size < 200_000 or not visual or not audio or not 4.3 <= duration <= 5.8:
        raise RuntimeError(f"Clip {clip['id']} technical video/audio QC failed")
    loud = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vn", "-af", "volumedetect", "-f", "null", "-"], check=False, capture_output=True, text=True)
    level = re.search(r"max_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB", loud.stderr)
    if not level or level.group(1) == "-inf" or float(level.group(1)) < -55:
        raise RuntimeError(f"Clip {clip['id']} audio silent")
    iterator, info = model.transcribe(str(video), language="zh", task="transcribe", beam_size=1, vad_filter=True, condition_on_previous_text=False)
    speech = [{"start": float(item.start), "end": float(item.end), "text": item.text.strip()} for item in iterator if item.text.strip()]
    transcript = "".join(item["text"] for item in speech)
    if sum(item["end"] - item["start"] for item in speech) < 0.4 or len(re.findall(r"[\u3400-\u9fff]", transcript)) < 2:
        raise RuntimeError(f"Clip {clip['id']} Mandarin ASR QC failed")
    dump(AUDIT / f"clip_{clip['id']}_ffprobe.json", probe)
    (AUDIT / f"clip_{clip['id']}_loudness.txt").write_text(loud.stderr, encoding="utf-8")
    dump(AUDIT / f"clip_{clip['id']}_speech.json", {"language": getattr(info, "language", None), "transcript": transcript, "expected": [line["zh"] for line in clip["dialogue"]]})
    return {"duration": duration, "width": visual[0].get("width"), "height": visual[0].get("height"), "audio_codec": audio[0].get("codec_name"), "max_volume_db": float(level.group(1)), "asr": transcript}


def make_proof(video: Path, clip_id: str) -> Path:
    last = LAST / f"clip_{clip_id}_continuity.jpg"
    contact = PROOF / f"clip_{clip_id}_three_shot_contact.jpg"
    shell(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "4.70", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(last)])
    shell(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-vf", "fps=0.6,scale=427:240:force_original_aspect_ratio=decrease,pad=427:240:(ow-iw)/2:(oh-ih)/2:black,tile=3x1:padding=4:margin=4", "-frames:v", "1", "-q:v", "2", str(contact)])
    return last


def main() -> None:
    for path in (RUNTIME, RAW, AUDIT, PROOF, LAST):
        path.mkdir(parents=True, exist_ok=True)
    plan, clips = load_plan()
    if not os.environ.get("SEGMIND_API_KEY"):
        raise RuntimeError("SEGMIND_API_KEY is missing; no paid request made")
    from faster_whisper import WhisperModel
    from segmind import SegmindClient

    model = WhisperModel("tiny", device="cpu", compute_type="int8", download_root=os.environ.get("WHISPER_CACHE_DIR", "whisper_cache"))
    client = SegmindClient()
    if clips[0]["id"] != "01" and not os.environ.get("PREVIOUS_VIDEO_URL"):
        raise RuntimeError("A later S01E05 clip batch needs PREVIOUS_VIDEO_URL; no paid request made")
    previous: Path | None = None
    manifest: dict[str, Any] = {"episode": "S01E05", "clips": [], "request_count": 0, "automatic_retries": 0, "status": "running", "started_at": stamp(), "plan_sha256": sha(PLAN_PATH)}
    manifest_path = AUDIT / "generation_manifest.json"
    dump(manifest_path, manifest)
    try:
        for clip in clips:
            panels, identities = prepare(clip)
            if previous is None:
                previous = initial_frame(panels)
            refs = [*panels, *identities, previous]
            if len(refs) > 9:
                raise RuntimeError(f"Too many references for clip {clip['id']}")
            prompt = build_prompt(plan, clip)
            (AUDIT / f"clip_{clip['id']}_prompt.txt").write_text(prompt, encoding="utf-8")
            record: dict[str, Any] = {"clip_id": clip["id"], "status": "submitting_once", "automatic_retries": 0, "references": [str(item) for item in refs], "started_at": stamp()}
            dump(AUDIT / f"clip_{clip['id']}_request.json", record)
            urls = [upload(client, ref) for ref in refs]
            # This is the only paid submission for this clip. No retry branch exists.
            job = client.submit_async("seedance-2.0-mini", prompt=prompt, reference_images=urls, duration=5, resolution="480p", aspect_ratio="16:9", generate_audio=True, bitrate_mode="high", return_last_frame=True, seed=20260850 + int(clip["id"]))
            record.update({"request_id": job.request_id, "status": "processing"})
            manifest["request_count"] += 1
            dump(AUDIT / f"clip_{clip['id']}_request.json", record)
            dump(manifest_path, manifest)
            result = job.wait(timeout=1800, interval=5)
            dump(AUDIT / f"clip_{clip['id']}_result.json", result)
            video = RAW / f"S1E05_clip_{clip['id']}_raw.mp4"
            record["output_url"] = fetch_video(result, video)
            record["technical_qc"] = verify(video, clip, model)
            previous = make_proof(video, clip["id"])
            record.update({"status": "completed", "completed_at": stamp(), "video_sha256": sha(video), "continuity_sha256": sha(previous)})
            manifest["clips"].append(record)
            dump(AUDIT / f"clip_{clip['id']}_request.json", record)
            dump(manifest_path, manifest)
        manifest.update({"status": "completed", "completed_at": stamp()})
        dump(manifest_path, manifest)
    except Exception as exc:
        manifest.update({"status": "failed", "failed_at": stamp(), "error": f"{type(exc).__name__}: {exc}"})
        dump(manifest_path, manifest)
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
