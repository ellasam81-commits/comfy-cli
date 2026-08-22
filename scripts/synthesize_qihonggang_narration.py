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
GATE = ROOT / "references" / "qihonggang-fanedit" / "run-narration-gate-v1.txt"
EXPECTED_GATE = (
    "AUTHOR-APPROVED: QIHONGGANG FAN EDIT NARRATION V1; "
    "ONE GEMINI 3.1 FLASH TTS REQUEST; PRESET CHARON MANDARIN MALE; "
    "TEXT ONLY; NO REFERENCE AUDIO UPLOAD; NO VIDEO GENERATION; "
    "NO AUTOMATIC RETRIES; NO RERUNS"
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

    styled_text = "\n\n[long pause]\n\n".join(LINES)
    styled_text = (
        "[deep voice] [mature] [calm] [restrained] [slow pace] "
        "[cinematic narration] [compassionate] " + styled_text
    )
    manifest = {
        "model": "gemini-3.1-flash-tts",
        "voice": "Charon",
        "temperature": 0.35,
        "request_limit": 1,
        "requests_submitted": 0,
        "automatic_retries": 0,
        "video_requests": 0,
        "reference_audio_uploads": 0,
        "lines": LINES,
        "status": "submitting_once",
    }
    write_json(OUT / "manifest.json", manifest)
    client = SegmindClient()
    job = client.submit_async(
        "gemini-3.1-flash-tts",
        text=styled_text,
        voice_1="Charon",
        temperature=0.35,
    )
    manifest["requests_submitted"] = 1
    manifest["request_id"] = job.request_id
    manifest["status"] = "processing"
    write_json(OUT / "manifest.json", manifest)
    result = job.wait(timeout=600, interval=1.0)
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
    qc = {
        "file": final.name,
        "duration_seconds": duration,
        "audio_streams": len(streams),
        "codec": streams[0].get("codec_name"),
        "sample_rate": streams[0].get("sample_rate"),
        "script_chinese_characters": len(re.findall(r"[\u3400-\u9fff]", "".join(LINES))),
        "requests_submitted": 1,
        "automatic_retries": 0,
        "video_requests": 0,
        "reference_audio_uploads": 0,
    }
    write_json(OUT / "audio_qc.json", qc)
    manifest["status"] = "completed"
    manifest["audio_qc"] = qc
    write_json(OUT / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
