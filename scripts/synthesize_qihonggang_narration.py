#!/usr/bin/env python3
"""Generate one fixed Mandarin narration take for the Qi Honggang fan edit."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import requests
from segmind import SegmindClient


ROOT = Path.cwd()
OUT = ROOT / os.environ.get("OUTPUT_DIR", "output/qihonggang-fanedit-narration-v1")
ACCEPTED = ROOT / "accepted" / "s1e14"
GATE = ROOT / "references" / "qihonggang-fanedit" / "run-narration-gate-v1.txt"
EXPECTED_GATE = (
    "AUTHOR-APPROVED: QIHONGGANG FAN EDIT NARRATION V1; "
    "ONE SEED AUDIO 1.0 TTS REQUEST; MATURE LOW MANDARIN MALE; "
    "SYNTHETIC REFERENCE ONLY; NO VIDEO GENERATION; NO AUTOMATIC RETRIES; NO RERUNS"
)

LINES = [
    "亓宏刚为什么总怕自己晚一步？因为过去，他已经失去过一次。",
    "所以，他不是害怕犯错，而是再也承受不起——来不及。",
    "他不是传统影视里那个永远冷硬、靠外形压人的警察。他会冲动，会近乎疯狂地大喊，也会不顾一切地往前冲。",
    "但他有爆发，却不靠爆发压人。情绪冲到最高点，他仍知道自己为什么出发。",
    "看见复杂，仍守住底线。",
]


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def find_raw() -> Path:
    exact = list(ACCEPTED.rglob("S01E14_clip_11_raw.mp4"))
    candidates = exact or list(ACCEPTED.rglob("*S01E14*clip_11*raw*.mp4"))
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one accepted S01E14 clip 11 source, found: {candidates}")
    return candidates[0]


def build_reference(source: Path, destination: Path) -> None:
    filters = []
    tags = []
    for index in range(3):
        tag = f"r{index}"
        filters.append(
            f"[{index}:a]atrim=start=0.25:end=3.95,asetpts=PTS-STARTPTS,"
            f"aresample=32000,aformat=channel_layouts=mono[{tag}]"
        )
        tags.append(f"[{tag}]")
    filters.append(f"{''.join(tags)}concat=n=3:v=0:a=1[voice]")
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source), "-i", str(source), "-i", str(source),
        "-filter_complex", ";".join(filters), "-map", "[voice]",
        "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "32000", "-ac", "1",
        str(destination),
    ])
    if not destination.is_file() or destination.stat().st_size < 70_000:
        raise RuntimeError("Synthetic reference extraction failed")


def find_urls(value: object, found: list[str]) -> None:
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        found.append(value)
    elif isinstance(value, list):
        for item in value:
            find_urls(item, found)
    elif isinstance(value, dict):
        for item in value.values():
            find_urls(item, found)


def download_audio(result: object, destination: Path) -> str:
    urls: list[str] = []
    find_urls(result, urls)
    for url in dict.fromkeys(urls):
        response = requests.get(url, timeout=300)
        response.raise_for_status()
        kind = response.headers.get("content-type", "").lower()
        suffix = Path(urlparse(url).path).suffix.lower()
        data = response.content
        if (
            kind.startswith("audio/")
            or data[:4] in {b"RIFF", b"OggS"}
            or data[:3] == b"ID3"
            or suffix in {".wav", ".mp3", ".m4a", ".aac", ".ogg"}
        ):
            destination.write_bytes(data)
            return url
    raise RuntimeError("Segmind returned no downloadable narration audio")


def main() -> None:
    if not os.environ.get("SEGMIND_API_KEY"):
        raise RuntimeError("SEGMIND_API_KEY is missing; no paid request made")
    if not GATE.is_file() or GATE.read_text(encoding="utf-8").strip() != EXPECTED_GATE:
        raise RuntimeError("Narration approval gate is absent or invalid")
    OUT.mkdir(parents=True, exist_ok=True)
    source = find_raw()
    reference = OUT / "mature_male_synthetic_reference.mp3"
    build_reference(source, reference)

    client = SegmindClient()
    resolver = getattr(client.files, "_get_content_type", None)
    if not callable(resolver) or not str(resolver(reference)).startswith("audio/"):
        raise RuntimeError("Segmind SDK rejected the synthetic reference before upload")
    uploaded = client.files.upload(reference)
    file_urls = uploaded.get("file_urls") if isinstance(uploaded, dict) else None
    if not isinstance(file_urls, list) or len(file_urls) != 1:
        raise RuntimeError(f"Reference upload returned an unexpected payload: {uploaded!r}")

    prompt = "\n".join([
        "Mandarin cinematic narration for a restrained police-character fan edit.",
        "Use @Audio1 only as a synthetic timbre reference. Deliver a mature, low male voice: calm, grounded, compassionate, and controlled, never promotional or exaggerated.",
        "Speak only the five quoted Chinese paragraphs below, exactly once and in order. Leave 0.8 to 1.1 seconds of clean silence between paragraphs.",
        "Do not speak instructions, numbering, labels, English, titles, music, sound effects, or any extra words.",
        "Do not imitate a real actor or interview voice. Keep the narration clearly separate from the preserved interview audio.",
        *[f'“{line}”' for line in LINES],
    ])
    manifest = {
        "model": "seed-audio-1.0",
        "request_limit": 1,
        "requests_submitted": 0,
        "automatic_retries": 0,
        "video_requests": 0,
        "lines": LINES,
        "status": "submitting_once",
        "reference_note": "accepted synthetic fictional-character audio; not a real-person clone",
    }
    write_json(OUT / "manifest.json", manifest)
    job = client.submit_async(
        "seed-audio-1.0",
        text_prompt=prompt,
        reference_audio_urls=[file_urls[0]],
        format="wav",
        sample_rate=48000,
        speech_rate=0,
        loudness_rate=0,
        pitch_rate=-1,
    )
    manifest["requests_submitted"] = 1
    manifest["request_id"] = job.request_id
    manifest["status"] = "processing"
    write_json(OUT / "manifest.json", manifest)
    result = job.wait(timeout=600, interval=2)
    write_json(OUT / "result.json", result)
    final = OUT / "qihonggang_mature_male_narration_v1.wav"
    download_audio(result, final)

    probe = json.loads(run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(final)
    ]).stdout)
    streams = [item for item in probe.get("streams", []) if item.get("codec_type") == "audio"]
    duration = float(probe.get("format", {}).get("duration") or 0)
    if len(streams) != 1 or not 18.0 <= duration <= 45.0 or final.stat().st_size < 30_000:
        raise RuntimeError(f"Narration technical QC failed: streams={len(streams)} duration={duration}")
    transcript_chars = len(re.findall(r"[\u3400-\u9fff]", "".join(LINES)))
    qc = {
        "file": final.name,
        "duration_seconds": duration,
        "audio_streams": len(streams),
        "codec": streams[0].get("codec_name"),
        "sample_rate": streams[0].get("sample_rate"),
        "script_chinese_characters": transcript_chars,
        "requests_submitted": 1,
        "automatic_retries": 0,
        "video_requests": 0,
    }
    write_json(OUT / "audio_qc.json", qc)
    manifest["status"] = "completed"
    manifest["audio_qc"] = qc
    write_json(OUT / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
