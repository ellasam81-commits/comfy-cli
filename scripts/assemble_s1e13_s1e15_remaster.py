#!/usr/bin/env python3
"""Package the S01E13–15 clear remaster with fixed audio and bilingual subtitles."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path.cwd()
PLAN_PATH = ROOT / "references" / "s1e13-s1e15-remaster" / "production_plan.json"
E13 = ROOT / "accepted" / "s1e13" / "s1e13-all" / "S01E13" / "raw"
E14 = ROOT / "accepted" / "s1e14" / "s1e14-all" / "S01E14" / "raw"
E15 = ROOT / os.environ.get("GENERATION_OUTPUT_DIR", "output/s1e13-s1e15-remaster") / "S01E15" / "raw"
TTS = ROOT / os.environ.get("TTS_OUTPUT_DIR", "output/s1e13-s1e15-remaster-tts")
OUT = ROOT / os.environ.get("FINAL_OUTPUT_DIR", "output/s1e13-s1e15-remaster-final")
FONTS = Path("/usr/share/fonts/opentype/noto")
WIDTH, HEIGHT = 864, 496


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def duration(path: Path) -> float:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def audio_video(path: Path, label: str, expected: float | None = None) -> None:
    if not path.is_file() or path.stat().st_size < 80_000:
        raise RuntimeError(f"Missing {label}: {path}")
    streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "default=nw=1:nk=1", str(path)], check=True, capture_output=True, text=True).stdout.splitlines()
    if "video" not in streams or "audio" not in streams:
        raise RuntimeError(f"{label} must contain video and audio")
    if expected is not None and abs(duration(path) - expected) > 0.18:
        raise RuntimeError(f"{label} must be {expected:.2f}s, got {duration(path):.2f}s")


def audio_only(path: Path, label: str) -> None:
    if not path.is_file() or path.stat().st_size < 10_000:
        raise RuntimeError(f"Missing {label}: {path}")
    streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "default=nw=1:nk=1", str(path)], check=True, capture_output=True, text=True).stdout.splitlines()
    if streams.count("audio") != 1 or not 4.85 <= duration(path) <= 5.15:
        raise RuntimeError(f"{label} must be a five-second mono dialogue track")


def esc(value: str) -> str:
    return value.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def ass_time(seconds: float) -> str:
    cents = round(seconds * 100)
    hours, cents = divmod(cents, 360000)
    mins, cents = divmod(cents, 6000)
    return f"{hours}:{mins:02d}:{cents / 100:05.2f}"


def raw(episode: str, clip_id: str) -> Path:
    root = {"S01E13": E13, "S01E14": E14, "S01E15": E15}[episode]
    result = root / f"{episode}_clip_{clip_id}_raw.mp4"
    if not result.is_file() or result.stat().st_size < 200_000:
        raise RuntimeError(f"Missing raw visual for {episode} clip {clip_id}: {result}")
    return result


def data() -> dict:
    value = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    if [item.get("code") for item in value.get("episodes", [])] != ["S01E13", "S01E14", "S01E15"]:
        raise RuntimeError("Assembly requires the three locked remaster episodes")
    return value


def verify_tts(source: dict) -> None:
    manifest = json.loads((TTS / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "completed" or manifest.get("tts_requests_submitted") != 36 or len(manifest.get("clips", [])) != 36:
        raise RuntimeError("Fixed-TTS manifest does not prove thirty-six single takes")
    for episode in source["episodes"]:
        for clip in episode["clips"]:
            audio_only(TTS / "timed" / f"{episode['code']}_clip_{clip['id']}_dialogue.m4a", f"{episode['code']} clip {clip['id']} dialogue")


def assemble(source: dict, episode: dict) -> Path:
    code = episode["code"]
    work = OUT / code
    normalized = work / "normalized"
    work.mkdir(parents=True, exist_ok=True); normalized.mkdir(exist_ok=True)
    for clip in episode["clips"]:
        source_video = raw(code, clip["id"])
        audio = TTS / "timed" / f"{code}_clip_{clip['id']}_dialogue.m4a"
        target = normalized / f"{clip['id']}.mp4"
        pending = normalized / f"{clip['id']}.pending.mp4"
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source_video), "-i", str(audio),
            "-map", "0:v:0", "-map", "1:a:0", "-t", "5", "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih):black,setsar=1",
            "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(pending),
        ])
        audio_video(pending, f"Normalized {code} clip {clip['id']}", 5.0)
        pending.replace(target)
    concat = work / "concat.txt"
    concat.write_text("\n".join("file '" + (normalized / f"{clip['id']}.mp4").as_posix() + "'" for clip in episode["clips"]) + "\n", encoding="utf-8")
    joined = work / f"{code}_joined.mp4"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", "-movflags", "+faststart", str(joined)])
    audio_video(joined, f"Joined {code}", 60.0)
    ass = work / f"{code}_bilingual.ass"
    lines = [
        "[Script Info]", f"Title: {code} Clear Remaster", "ScriptType: v4.00+", f"PlayResX: {WIDTH}", f"PlayResY: {HEIGHT}", "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]", "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        "Style: Header,Noto Sans CJK SC,17,&H00F6F8FA,&H000000FF,&H80000000,&H80000000,1,0,0,0,100,100,0,0,1,1.2,1,8,18,18,12,1",
        "Style: Chinese,Noto Sans CJK SC,23,&H00FFFFFF,&H000000FF,&H90000000,&H90000000,1,0,0,0,100,100,0,0,1,1.8,1,2,28,28,48,1",
        "Style: English,Noto Sans,14,&H00F0F4F8,&H000000FF,&H90000000,&H90000000,0,0,0,0,100,100,0,0,1,1.3,1,2,28,28,24,1", "",
        "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    header = f"《{source['series']}》｜{code}《{episode['title_zh']}》｜制作：{source['author']}"
    lines.append(f"Dialogue: 0,0:00:00.00,0:01:00.00,Header,,0,0,0,,{esc(header)}")
    for index, clip in enumerate(episode["clips"]):
        offset = index * 5.0
        start, end = offset + float(clip["start"]), offset + float(clip["end"])
        lines.append(f"Dialogue: 1,{ass_time(start)},{ass_time(end)},Chinese,,0,0,0,,{esc(clip['speaker'] + '：' + clip['zh'])}")
        lines.append(f"Dialogue: 2,{ass_time(start)},{ass_time(end)},English,,0,0,0,,{esc(clip['en'])}")
    ass.write_text("\n".join(lines) + "\n", encoding="utf-8")
    final = work / f"{code}_{episode['title_en'].replace(' ', '')}_ClearRemaster.mp4"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(joined), "-vf", f"ass={ass}:fontsdir={FONTS}", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(final)])
    audio_video(final, f"Final {code}", 60.0)
    return final


def main() -> None:
    if not FONTS.is_dir():
        raise RuntimeError("Noto CJK font is required for readable Chinese subtitles")
    source = data(); verify_tts(source); OUT.mkdir(parents=True, exist_ok=True)
    finals = [assemble(source, episode) for episode in source["episodes"]]
    report = OUT / "remaster_qc.json"
    report.write_text(json.dumps({"episodes": [str(path) for path in finals], "video_requests": 12, "tts_requests": 36, "auto_retries": 0, "clear_story": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    package = OUT / "S01E13_S01E15_TheDrained_ClearRemaster.zip"
    run(["zip", "-j", "-9", str(package), *(str(item) for item in finals), str(report)])
    print(json.dumps({"finals": [str(path) for path in finals], "zip": str(package)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
