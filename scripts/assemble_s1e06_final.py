#!/usr/bin/env python3
"""Assemble verified S01E06 clips with a header and voice-synchronous bilingual subtitles."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path.cwd()
PLAN = ROOT / "references/s1e06/five_second_plan.json"
RAW = ROOT / "output/s1e06-all/raw"
AUDIT = ROOT / "output/s1e06-all/audit"
OUT = ROOT / "output/s1e06-final"
NORMALIZED = OUT / "normalized"
FONTS = ROOT / "references/fonts"
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
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def duration(path: Path) -> float:
    value = probe_duration(path)
    if not 4.3 <= value <= 5.8:
        raise RuntimeError(f"Unexpected clip duration: {path} ({value:.3f}s)")
    return value


def playable_with_audio(path: Path, expected: float, label: str) -> None:
    """Reject a truncated normalization, concat, or final before it can be handed off."""
    if not path.is_file() or path.stat().st_size < 200_000:
        raise RuntimeError(f"{label} is missing or too small: {path}")
    actual = probe_duration(path)
    if abs(actual - expected) > 0.35:
        raise RuntimeError(f"{label} duration mismatch: expected {expected:.3f}s, got {actual:.3f}s")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "default=nw=1:nk=1", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    if "video" not in probe or "audio" not in probe:
        raise RuntimeError(f"{label} must contain both video and audio")


def voice_cues(clip: dict, clip_duration: float) -> list[dict]:
    """Use Whisper's measured voice boundaries, limited by the approved cue window.

    Each line is first checked against the planned timing window so subtitles never
    lead the intended speaker. A short line keeps its exact detected start/end;
    the two-line closing exchange requires two detected speech segments.
    """
    expected = clip["dialogue"]
    if not expected:
        return []
    source = AUDIT / f"clip_{clip['id']}_speech.json"
    if not source.is_file():
        raise RuntimeError(f"Missing Mandarin ASR audit: {source}")
    data = json.loads(source.read_text(encoding="utf-8"))
    segments = [item for item in data.get("segments", []) if item.get("text")]
    if len(expected) == 1:
        if not segments:
            raise RuntimeError(f"No Mandarin timing detected for clip {clip['id']}")
        start, end = float(segments[0]["start"]), float(segments[-1]["end"])
        line = expected[0]
        # Whisper can include a small trailing syllable; retain the actual audio
        # boundary but never show a subtitle outside the five-second clip.
        start = max(0.0, min(start, clip_duration - 0.08))
        end = min(clip_duration, max(end, start + 0.12))
        return [{"start": start, "end": end, "source": "whisper"}]
    if len(segments) < len(expected):
        raise RuntimeError(f"Clip {clip['id']} needs {len(expected)} separately detected Mandarin lines for subtitle sync")
    cues: list[dict] = []
    for line, segment in zip(expected, segments):
        start, end = float(segment["start"]), float(segment["end"])
        if not 0.0 <= start < end <= clip_duration:
            raise RuntimeError(f"Invalid ASR speech boundary for clip {clip['id']}")
        cues.append({"start": start, "end": end, "source": "whisper"})
    return cues


def main() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    clips = plan["clips"]
    if [clip["id"] for clip in clips] != [f"{value:02d}" for value in range(1, 13)]:
        raise RuntimeError("S01E06 plan must retain the 12 locked clips")
    if (FONTS / "NotoSansCJKsc-Regular.otf").is_file():
        font_dir = FONTS
    elif (SYSTEM_CJK_FONTS / "NotoSansCJK-Regular.ttc").is_file():
        font_dir = SYSTEM_CJK_FONTS
    else:
        raise RuntimeError("Missing Noto Sans CJK font; do not burn unreadable Chinese subtitles")
    OUT.mkdir(parents=True, exist_ok=True)
    NORMALIZED.mkdir(parents=True, exist_ok=True)

    durations: list[float] = []
    for clip in clips:
        source = RAW / f"S1E06_clip_{clip['id']}_raw.mp4"
        if not source.is_file():
            raise RuntimeError(f"Missing verified raw clip: {source}")
        durations.append(duration(source))
        normalized = NORMALIZED / f"{clip['id']}.mp4"
        try:
            playable_with_audio(normalized, durations[-1], f"Normalized clip {clip['id']}")
        except Exception:
            # Encode into a sibling temporary file and replace only after it is
            # independently playable. A partial ffmpeg write can never poison
            # the accepted 12-clip concat input.
            temporary = NORMALIZED / f"{clip['id']}.pending.mp4"
            run([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
                "-vf", f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih):black,setsar=1",
                "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(temporary),
            ])
            playable_with_audio(temporary, durations[-1], f"Pending normalized clip {clip['id']}")
            temporary.replace(normalized)

    offset = 0.0
    lines = [
        "[Script Info]", "Title: S01E06 The Killer Chosen by Numbers", "ScriptType: v4.00+", f"PlayResX: {WIDTH}", f"PlayResY: {HEIGHT}", "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        "Style: Header,Noto Sans CJK SC,17,&H00F6F8FA,&H000000FF,&H80000000,&H80000000,1,0,0,0,100,100,0,0,1,1.2,1,8,18,18,12,1",
        "Style: Chinese,Noto Sans CJK SC,23,&H00FFFFFF,&H000000FF,&H90000000,&H90000000,1,0,0,0,100,100,0,0,1,1.8,1,2,28,28,48,1",
        "Style: English,Noto Sans,14,&H00F0F4F8,&H000000FF,&H90000000,&H90000000,0,0,0,0,100,100,0,0,1,1.3,1,2,28,28,24,1",
        "", "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    total = sum(durations)
    header = "《吸血法医·剑刺》  S01E06《被数字选中的凶手》  |  林爱丽"
    lines.append(f"Dialogue: 0,0:00:00.00,{ass_time(total)},Header,,0,0,0,,{esc(header)}")
    for clip, clip_duration in zip(clips, durations):
        cue_list = voice_cues(clip, clip_duration)
        if len(cue_list) != len(clip["dialogue"]):
            raise RuntimeError(f"S01E06 voice-cue count must match dialogue count for clip {clip['id']}")
        for spoken, cue in zip(clip["dialogue"], cue_list):
            local_start, local_end = float(cue["start"]), float(cue["end"])
            if not 0 <= local_start < local_end <= clip_duration:
                raise RuntimeError(f"Invalid S01E06 voice cue for clip {clip['id']}: {cue}")
            start = offset + local_start
            end = offset + local_end
            lines.append(f"Dialogue: 1,{ass_time(start)},{ass_time(end)},Chinese,,0,0,0,,{esc(spoken['zh'])}")
            lines.append(f"Dialogue: 2,{ass_time(start)},{ass_time(end)},English,,0,0,0,,{esc(spoken['en'])}")
        offset += clip_duration
    ass = OUT / "S1E06_bilingual.ass"
    ass.write_text("\n".join(lines) + "\n", encoding="utf-8")

    concat = OUT / "concat.txt"
    concat.write_text("\n".join(f"file '{(NORMALIZED / f'{clip['id']}.mp4').as_posix()}'" for clip in clips) + "\n", encoding="utf-8")
    joined = OUT / "S1E06_TheKillerChosenByNumbers_joined.mp4"
    pending_joined = OUT / "S1E06_TheKillerChosenByNumbers_joined.pending.mp4"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", "-movflags", "+faststart", str(pending_joined)])
    playable_with_audio(pending_joined, total, "Joined S1E06")
    pending_joined.replace(joined)
    final = OUT / "S1E06_TheKillerChosenByNumbers_Final.mp4"
    pending_final = OUT / "S1E06_TheKillerChosenByNumbers_Final.pending.mp4"
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(joined), "-vf", f"ass={ass}:fontsdir={font_dir}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(pending_final),
    ])
    playable_with_audio(pending_final, total, "Final S1E06")
    pending_final.replace(final)
    run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height", "-of", "json", str(final)])
    package = OUT / "S1E06_TheKillerChosenByNumbers_Final.zip"
    pending_package = OUT / "S1E06_TheKillerChosenByNumbers_Final.pending.zip"
    run(["zip", "-j", "-9", str(pending_package), str(final)])
    pending_package.replace(package)


if __name__ == "__main__":
    main()
