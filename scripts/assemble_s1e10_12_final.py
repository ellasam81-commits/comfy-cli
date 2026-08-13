#!/usr/bin/env python3
"""Assemble verified S01E10-12 clips with header and voice-synchronous bilingual subtitles."""
from __future__ import annotations

import json
import os
import subprocess
import argparse
from pathlib import Path


ROOT = Path.cwd()
PLAN = ROOT / "references" / "s1e10-12" / "production_plan.json"
RAW_ROOT = ROOT / os.environ.get("GENERATION_OUTPUT_DIR", "output/s1e10-12-all")
OUT = ROOT / os.environ.get("FINAL_OUTPUT_DIR", "output/s1e10-12-final")
FONTS = ROOT / "references" / "fonts"
SYSTEM_CJK_FONTS = Path("/usr/share/fonts/opentype/noto")
WIDTH, HEIGHT = 864, 496


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def esc(value: str) -> str:
    return value.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def ass_time(seconds: float) -> str:
    centis = round(seconds * 100)
    hours, centis = divmod(centis, 360000)
    minutes, centis = divmod(centis, 6000)
    return f"{hours}:{minutes:02d}:{centis / 100:05.2f}"


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def playable_with_audio(path: Path, expected: float, label: str) -> None:
    if not path.is_file() or path.stat().st_size < 200_000:
        raise RuntimeError(f"{label} is missing or too small: {path}")
    actual = probe_duration(path)
    if abs(actual - expected) > 0.35:
        raise RuntimeError(f"{label} duration mismatch: expected {expected:.3f}s, got {actual:.3f}s")
    streams = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "default=nw=1:nk=1", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    if "video" not in streams or "audio" not in streams:
        raise RuntimeError(f"{label} must contain both video and audio")


def voice_cue(episode: str, clip: dict, duration: float) -> tuple[float, float]:
    source = RAW_ROOT / episode / "audit" / f"clip_{clip['id']}_speech.json"
    if not source.is_file():
        raise RuntimeError(f"Missing Mandarin ASR audit: {source}")
    data = json.loads(source.read_text(encoding="utf-8"))
    segments = [item for item in data.get("segments", []) if item.get("text")]
    if not segments:
        raise RuntimeError(f"No Mandarin voice boundary found for {episode} clip {clip['id']}")
    start = max(0.0, min(float(segments[0]["start"]), duration - 0.08))
    end = min(duration, max(float(segments[-1]["end"]), start + 0.12))
    return start, end


def font_dir() -> Path:
    if (FONTS / "NotoSansCJKsc-Regular.otf").is_file():
        return FONTS
    if (SYSTEM_CJK_FONTS / "NotoSansCJK-Regular.ttc").is_file():
        return SYSTEM_CJK_FONTS
    raise RuntimeError("Missing Noto Sans CJK font; no unreadable Chinese subtitles may be burned")


def assemble_episode(plan: dict, episode: dict, fonts: Path) -> Path:
    code = episode["episode"]
    work = OUT / code
    normalized = work / "normalized"
    work.mkdir(parents=True, exist_ok=True)
    normalized.mkdir(parents=True, exist_ok=True)
    durations: list[float] = []
    for clip in episode["clips"]:
        source = RAW_ROOT / code / "raw" / f"{code}_clip_{clip['id']}_raw.mp4"
        if not source.is_file():
            raise RuntimeError(f"Missing verified raw clip: {source}")
        clip_duration = probe_duration(source)
        if not 4.3 <= clip_duration <= 5.8:
            raise RuntimeError(f"Unexpected clip duration: {source} ({clip_duration:.3f}s)")
        durations.append(clip_duration)
        target = normalized / f"{clip['id']}.mp4"
        pending = normalized / f"{clip['id']}.pending.mp4"
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
            "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih):black,setsar=1",
            "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(pending),
        ])
        playable_with_audio(pending, clip_duration, f"Normalized {code} clip {clip['id']}")
        pending.replace(target)

    total = sum(durations)
    ass_lines = [
        "[Script Info]", f"Title: {code} {episode['title_en']}", "ScriptType: v4.00+", f"PlayResX: {WIDTH}", f"PlayResY: {HEIGHT}", "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        "Style: Header,Noto Sans CJK SC,17,&H00F6F8FA,&H000000FF,&H80000000,&H80000000,1,0,0,0,100,100,0,0,1,1.2,1,8,18,18,12,1",
        "Style: Chinese,Noto Sans CJK SC,23,&H00FFFFFF,&H000000FF,&H90000000,&H90000000,1,0,0,0,100,100,0,0,1,1.8,1,2,28,28,48,1",
        "Style: English,Noto Sans,14,&H00F0F4F8,&H000000FF,&H90000000,&H90000000,0,0,0,0,100,100,0,0,1,1.3,1,2,28,28,24,1",
        "", "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    header = f"《{plan['series_title_zh']}》｜{code}《{episode['title_zh']}》｜制作：{plan['maker_zh']}"
    ass_lines.append(f"Dialogue: 0,0:00:00.00,{ass_time(total)},Header,,0,0,0,,{esc(header)}")
    offset = 0.0
    for clip, clip_duration in zip(episode["clips"], durations):
        start, end = voice_cue(code, clip, clip_duration)
        line = clip["dialogue"][0]
        ass_lines.append(f"Dialogue: 1,{ass_time(offset + start)},{ass_time(offset + end)},Chinese,,0,0,0,,{esc(line['zh'])}")
        ass_lines.append(f"Dialogue: 2,{ass_time(offset + start)},{ass_time(offset + end)},English,,0,0,0,,{esc(line['en'])}")
        offset += clip_duration
    ass = work / f"{code}_bilingual.ass"
    ass.write_text("\n".join(ass_lines) + "\n", encoding="utf-8")

    concat = work / "concat.txt"
    concat.write_text("\n".join(f"file '{(normalized / f'{clip['id']}.mp4').as_posix()}'" for clip in episode["clips"]) + "\n", encoding="utf-8")
    joined = work / f"{code}_joined.mp4"
    pending_joined = work / f"{code}_joined.pending.mp4"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", "-movflags", "+faststart", str(pending_joined)])
    playable_with_audio(pending_joined, total, f"Joined {code}")
    pending_joined.replace(joined)
    final = work / f"{code}_{episode['title_en'].replace(' ', '')}_Final.mp4"
    pending_final = work / f"{final.stem}.pending.mp4"
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(joined), "-vf", f"ass={ass}:fontsdir={fonts}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(pending_final),
    ])
    playable_with_audio(pending_final, total, f"Final {code}")
    pending_final.replace(final)
    return final


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--episode", choices=["S01E10", "S01E11", "S01E12"])
    args = parser.parse_args()
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    expected = ["S01E10", "S01E11", "S01E12"]
    if [episode.get("episode") for episode in plan.get("episodes", [])] != expected:
        raise RuntimeError("Assembly plan episode order is locked")
    OUT.mkdir(parents=True, exist_ok=True)
    fonts = font_dir()
    episodes = [episode for episode in plan["episodes"] if args.episode is None or episode["episode"] == args.episode]
    finals = [assemble_episode(plan, episode, fonts) for episode in episodes]
    package = OUT / (f"{args.episode}_NoWaterDrowning_Final.zip" if args.episode else "S01E10_S01E12_NoWaterDrowning_Final.zip")
    pending = OUT / f"{package.stem}.pending.zip"
    run(["zip", "-j", "-9", str(pending), *(str(item) for item in finals)])
    pending.replace(package)
    print(json.dumps({"finals": [str(item) for item in finals], "zip": str(package)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
