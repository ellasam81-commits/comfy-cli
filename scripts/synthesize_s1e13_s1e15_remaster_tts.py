#!/usr/bin/env python3
"""Create one fixed Mandarin TTS take per remaster clip, with no retry path."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path.cwd()
PLAN_PATH = ROOT / "references" / "s1e13-s1e15-remaster" / "production_plan.json"
E13 = ROOT / "accepted" / "s1e13" / "s1e13-all" / "S01E13" / "raw"
E14 = ROOT / "accepted" / "s1e14" / "s1e14-all" / "S01E14" / "raw"
E15 = ROOT / os.environ.get("GENERATION_OUTPUT_DIR", "output/s1e13-s1e15-remaster") / "S01E15" / "raw"
OUT = ROOT / os.environ.get("TTS_OUTPUT_DIR", "output/s1e13-s1e15-remaster-tts")

REFERENCE_SEGMENTS = {
    "林浅": [("S01E13", "01", 0.25, 3.8), ("S01E13", "06", 0.25, 3.8), ("S01E14", "01", 0.25, 3.8)],
    "剑刺": [("S01E13", "02", 0.25, 3.9), ("S01E13", "09", 0.25, 3.9), ("S01E14", "09", 0.25, 3.9)],
    "许未": [("S01E13", "03", 0.25, 4.0), ("S01E13", "04", 0.25, 4.0), ("S01E14", "02", 0.25, 4.0)],
    "周峤": [("S01E13", "05", 0.25, 4.0), ("S01E13", "08", 0.25, 4.0), ("S01E14", "04", 0.25, 4.0)],
    "韩彻": [("S01E14", "11", 0.25, 3.95), ("S01E14", "11", 0.25, 3.95), ("S01E14", "11", 0.25, 3.95)],
}


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def plan() -> dict[str, Any]:
    data = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    runtime = data.get("runtime", {})
    if runtime.get("tts_requests") != 12 or runtime.get("automatic_retries") != 0:
        raise RuntimeError("Remaster TTS count or retry lock is invalid")
    episodes = data.get("episodes")
    if not isinstance(episodes, list) or [item.get("code") for item in episodes] != ["S01E13", "S01E14", "S01E15"]:
        raise RuntimeError("Remaster episodes must remain S01E13–S01E15 in order")
    if sum(len(item.get("clips", [])) for item in episodes) != 36:
        raise RuntimeError("Remaster requires exactly 36 TTS clips")
    for episode in episodes:
        if [item.get("id") for item in episode["clips"]] != [f"{index:02d}" for index in range(1, 13)]:
            raise RuntimeError(f"{episode.get('code')} must retain clips 01–12")
        for clip in episode["clips"]:
            if clip.get("speaker") not in data["voice_lock"] or not clip.get("zh") or not clip.get("en"):
                raise RuntimeError(f"Invalid TTS line in {episode['code']} clip {clip.get('id')}")
            if not 0.0 <= float(clip.get("start", -1)) < float(clip.get("end", 6)) <= 5.0:
                raise RuntimeError(f"Invalid TTS timing in {episode['code']} clip {clip['id']}")
    return data


def raw_path(episode: str, clip: str) -> Path:
    root = {"S01E13": E13, "S01E14": E14, "S01E15": E15}[episode]
    result = root / f"{episode}_clip_{clip}_raw.mp4"
    if not result.is_file() or result.stat().st_size < 200_000:
        raise RuntimeError(f"Missing accepted visual source: {result}")
    return result


def build_reference(destination: Path, segments: list[tuple[str, str, float, float]]) -> None:
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for episode, clip, _, _ in segments:
        command.extend(["-i", str(raw_path(episode, clip))])
    filters, tags = [], []
    for index, (_, _, start, end) in enumerate(segments):
        tag = f"a{index}"
        filters.append(f"[{index}:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,aresample=32000,aformat=channel_layouts=mono[{tag}]")
        tags.append(f"[{tag}]")
    filters.append(f"{''.join(tags)}concat=n={len(tags)}:v=0:a=1[voice]")
    command.extend(["-filter_complex", ";".join(filters), "-map", "[voice]", "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "32000", "-ac", "1", str(destination)])
    run(command)
    if not destination.is_file() or destination.stat().st_size < 70_000:
        raise RuntimeError(f"Could not build voice reference: {destination}")


def probe_audio(path: Path) -> dict[str, Any]:
    data = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]).stdout)
    audio = [item for item in data.get("streams", []) if item.get("codec_type") == "audio"]
    return {
        "file": path.name, "codec": audio[0].get("codec_name") if len(audio) == 1 else None,
        "sample_rate": audio[0].get("sample_rate") if len(audio) == 1 else None,
        "channels": audio[0].get("channels") if len(audio) == 1 else None,
        "duration": float(data.get("format", {}).get("duration") or 0), "streams": len(audio), "bytes": path.stat().st_size,
    }


def ensure_mp3_reference(path: Path) -> dict[str, Any]:
    details = probe_audio(path)
    if not (details["codec"] == "mp3" and str(details["sample_rate"]) == "32000" and str(details["channels"]) == "1" and 8.0 <= details["duration"] <= 25.0):
        raise RuntimeError(f"Voice reference preflight failed: {details}")
    return details


def find_urls(value: Any, found: list[str]) -> None:
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        found.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            find_urls(item, found)
    elif isinstance(value, list):
        for item in value:
            find_urls(item, found)


def download_audio(result: Any, target: Path) -> str:
    import requests

    candidates: list[str] = []
    find_urls(result, candidates)
    for url in dict.fromkeys(candidates):
        response = requests.get(url, timeout=300)
        response.raise_for_status()
        kind = response.headers.get("content-type", "").lower()
        suffix = Path(urlparse(url).path).suffix.lower()
        if kind.startswith("audio/") or response.content[:4] in {b"RIFF", b"OggS"} or response.content[:3] == b"ID3" or suffix in {".wav", ".mp3", ".m4a", ".aac"}:
            target.write_bytes(response.content)
            return url
    raise RuntimeError("Seed Audio returned no downloadable audio")


def atempo_chain(factor: float) -> str:
    values: list[float] = []
    remaining = factor
    while remaining > 2.0:
        values.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        values.append(0.5)
        remaining /= 0.5
    values.append(remaining)
    return ",".join(f"atempo={value:.6f}" for value in values if abs(value - 1.0) > 0.0001)


def make_clip_audio(source: Path, target: Path, start: float, end: float) -> dict[str, Any]:
    details = probe_audio(source)
    if details["streams"] != 1 or not 0.35 <= details["duration"] <= 12.0:
        raise RuntimeError(f"TTS source technical QC failed: {details}")
    desired = end - start
    tempo = max(0.5, min(2.0, details["duration"] / desired))
    tempo_filter = atempo_chain(tempo)
    voice = f"[1:a]aresample=48000{',' + tempo_filter if tempo_filter else ''},atrim=duration={desired:.3f},asetpts=PTS-STARTPTS,adelay={round(start * 1000)}[voice]"
    filters = ";".join([
        "[0:a]volume=0.006[room]", voice,
        "[room][voice]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[mix]",
    ])
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-t", "5", "-i",
        "anoisesrc=color=brown:sample_rate=48000:amplitude=0.5", "-i", str(source),
        "-filter_complex", filters, "-map", "[mix]", "-t", "5", "-c:a", "aac", "-b:a", "192k", str(target),
    ])
    final = probe_audio(target)
    if final["streams"] != 1 or not 4.85 <= final["duration"] <= 5.15:
        raise RuntimeError(f"Timed dialogue output QC failed: {final}")
    final["source_duration"] = details["duration"]
    final["tempo"] = tempo
    return final


def preflight() -> None:
    data = plan()
    for speaker, segments in REFERENCE_SEGMENTS.items():
        if speaker not in data["voice_lock"]:
            raise RuntimeError(f"Reference mapping has an unrecognised speaker: {speaker}")
        for episode, clip, _, _ in segments:
            raw_path(episode, clip)
    print("Remaster TTS preflight passed: five source voices, thirty-six one-line fixed-TTS slots, no retry path.")


def synthesize() -> None:
    preflight()
    if not os.environ.get("SEGMIND_API_KEY"):
        raise RuntimeError("SEGMIND_API_KEY is missing; no TTS request made")
    from faster_whisper import WhisperModel
    from segmind import SegmindClient

    data = plan()
    OUT.mkdir(parents=True, exist_ok=True)
    refs = OUT / "references"
    takes = OUT / "takes"
    final_audio = OUT / "timed"
    refs.mkdir(exist_ok=True); takes.mkdir(exist_ok=True); final_audio.mkdir(exist_ok=True)
    manifest: dict[str, Any] = {
        "model": "seed-audio-1.0", "status": "preparing", "automatic_retries": 0,
        "reference_uploads": {}, "tts_requests_submitted": 0, "tts_request_limit": 36,
        "clips": [], "started_at": stamp(),
        "note": "closest-match synthetic voice references; no persistent source voice ID is claimed",
    }
    manifest_path = OUT / "manifest.json"
    dump(manifest_path, manifest)
    client = SegmindClient()
    urls: dict[str, str] = {}
    for speaker, segments in REFERENCE_SEGMENTS.items():
        reference = refs / f"{speaker}_reference.mp3"
        build_reference(reference, segments)
        manifest["reference_uploads"][speaker] = ensure_mp3_reference(reference)
        resolver = getattr(client.files, "_get_content_type", None)
        if not callable(resolver) or not str(resolver(reference)).startswith("audio/"):
            raise RuntimeError(f"Installed Segmind SDK rejected MP3 reference before upload: {reference}")
        uploaded = client.files.upload(reference)
        file_urls = uploaded.get("file_urls") if isinstance(uploaded, dict) else None
        if not isinstance(file_urls, list) or len(file_urls) != 1 or not isinstance(file_urls[0], str) or not file_urls[0].startswith("https://"):
            raise RuntimeError(f"Voice reference upload failed for {speaker}: {uploaded!r}")
        urls[speaker] = file_urls[0]
        manifest["reference_uploads"][speaker]["url"] = urls[speaker]
        dump(manifest_path, manifest)
    manifest["status"] = "synthesizing"
    dump(manifest_path, manifest)
    model = WhisperModel("tiny", device="cpu", compute_type="int8", download_root=os.environ.get("WHISPER_CACHE_DIR", "whisper_cache"))
    try:
        for episode in data["episodes"]:
            for clip in episode["clips"]:
                speaker = clip["speaker"]
                reference_speaker = speaker if speaker in urls else "韩彻"
                record = {"episode": episode["code"], "clip_id": clip["id"], "speaker": speaker, "reference_speaker": reference_speaker, "text": clip["zh"], "request_count": 1, "automatic_retries": 0, "status": "submitting_once"}
                manifest["clips"].append(record)
                dump(manifest_path, manifest)
                prompt = "\n".join([
                    "Original-series audio-only Mandarin dialogue replacement.",
                    f"Use @Audio1 only as {speaker}; match the reference timbre, age, restraint and cadence.",
                    "Speak only the quoted Chinese line once. Do not speak the name label, directions, English, title, narration, music or effects.",
                    f"\"{clip['zh']}\"",
                ])
                job = client.submit_async("seed-audio-1.0", text_prompt=prompt, reference_audio_urls=[urls[reference_speaker]], format="wav", sample_rate=48000, speech_rate=0, loudness_rate=0, pitch_rate=0)
                record["request_id"] = job.request_id
                record["status"] = "processing"
                manifest["tts_requests_submitted"] += 1
                dump(manifest_path, manifest)
                result = job.wait(timeout=600, interval=2)
                raw = takes / f"{episode['code']}_clip_{clip['id']}_{speaker}.wav"
                record["output_url"] = download_audio(result, raw)
                iterator, info = model.transcribe(str(raw), language="zh", task="transcribe", beam_size=1, vad_filter=True, condition_on_previous_text=False)
                transcript = "".join(item.text.strip() for item in iterator if item.text.strip())
                if len(re.findall(r"[\u3400-\u9fff]", transcript)) < 2:
                    raise RuntimeError(f"TTS ASR QC failed for {episode['code']} clip {clip['id']}")
                timed = final_audio / f"{episode['code']}_clip_{clip['id']}_dialogue.m4a"
                record["timed_audio_qc"] = make_clip_audio(raw, timed, float(clip["start"]), float(clip["end"]))
                record["asr"] = transcript
                record["asr_language"] = getattr(info, "language", None)
                record["status"] = "completed"
                dump(manifest_path, manifest)
        manifest["status"] = "completed"
        manifest["completed_at"] = stamp()
        dump(manifest_path, manifest)
    except Exception as exc:
        manifest["status"] = "failed"; manifest["error"] = f"{type(exc).__name__}: {exc}"; manifest["failed_at"] = stamp()
        dump(manifest_path, manifest)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.preflight:
        preflight()
    elif args.verify:
        data = plan(); manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("status") != "completed" or manifest.get("tts_requests_submitted") != 36 or len(manifest.get("clips", [])) != 36:
            raise RuntimeError("TTS manifest does not prove thirty-six completed one-shot dialogue takes")
        for episode in data["episodes"]:
            for clip in episode["clips"]:
                path = OUT / "timed" / f"{episode['code']}_clip_{clip['id']}_dialogue.m4a"
                probe_audio(path)
        print("Remaster TTS completion verified: 36 fixed dialogue takes, one request each, no retry path.")
    else:
        synthesize()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
