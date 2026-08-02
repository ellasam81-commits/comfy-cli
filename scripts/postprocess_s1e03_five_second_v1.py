#!/usr/bin/env python3
"""Post-process the twelve approved S1E03 five-second Seedance clips.

This script performs no paid generation.  It discovers clip 01 in the gate
artifact and clips 02-12 in the remainder artifact, normalizes every clip,
applies the two deterministic picture fixes, builds one clean 60-second
master, creates a global bilingual ASS file, mixes an optional low suspense
drone, normalizes the complete programme to EBU R128, and renders the final
delivery plus machine-readable QC and a contact sheet.

Run from any directory.  Static validation does not require generated clips::

    python scripts/postprocess_s1e03_five_second_v1.py --prepare-only

Render after downloading both artifacts::

    python scripts/postprocess_s1e03_five_second_v1.py \
      --gate-dir gate_input \
      --remainder-dir remainder_input \
      --out-dir output/s1e03-final-v1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shlex
import shutil
import subprocess
import sys
import wave
from array import array
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "references" / "s1e03"
PLAN_PATH = SOURCE_DIR / "five_second_v1_plan.json"

EPISODE = "S1E03"
CLIP_IDS = [f"{number:02d}" for number in range(1, 13)]
WIDTH = 1280
HEIGHT = 720
FPS = 24
FRAMES_PER_CLIP = 120
SAMPLES_PER_CLIP = 240_000
TOTAL_FRAMES = 1_440
SAMPLE_RATE = 48_000
CHANNELS = 2
TOTAL_SAMPLES = 2_880_000
PROGRAM_SECONDS = 60

TARGET_I = -16.0
TARGET_LRA = 7.0
TARGET_TP = -2.0
DEFAULT_DRONE_GAIN_DB = -36.0

CLIP01_ACCEPTED_RAW_SHA256 = (
    "718f7c311028f610d4d6de3d52b6cc63ca403a9de84814ad853a0a427dc623fb"
)
CLIP01_EYE_REPAIR_START_FRAME = 8
CLIP01_EYE_REPAIR_END_FRAME = 12  # exclusive; repaired frames are 8 through 11
CLIP01_BLACK_EYE_SOURCE_FRAME = 12
CLIP01_REPAIR_START_FRAME = 30
CLIP01_REPAIR_END_FRAME = 54  # exclusive; repaired frames are 30 through 53
CLIP01_FREEZE_SOURCE_FRAME = 54
CLIP01_MATCH_SSIM_MIN = 0.990
CLIP01_DISTINCT_SSIM_MAX = 0.980
CLIP07_REPLACEMENT_FRAMES = 29
CLIP12_BODY_FRAMES = 115
CLIP12_BLACK_FRAMES = 5


def validate_clip01_repair_lock() -> dict[str, Any]:
    """Validate the accepted-gate repair independently of the story plan."""
    if len(CLIP01_ACCEPTED_RAW_SHA256) != 64 or not re.fullmatch(
        r"[0-9a-f]{64}", CLIP01_ACCEPTED_RAW_SHA256
    ):
        raise RuntimeError("Clip01 accepted-gate SHA-256 lock is malformed")
    if (
        CLIP01_EYE_REPAIR_START_FRAME != 8
        or CLIP01_EYE_REPAIR_END_FRAME != 12
        or CLIP01_BLACK_EYE_SOURCE_FRAME != 12
        or CLIP01_REPAIR_START_FRAME != 30
        or CLIP01_REPAIR_END_FRAME != 54
        or CLIP01_FREEZE_SOURCE_FRAME != 54
    ):
        raise RuntimeError("Clip01 split-screen repair frame lock changed")
    if not (
        0 < CLIP01_EYE_REPAIR_START_FRAME
        < CLIP01_EYE_REPAIR_END_FRAME
        == CLIP01_BLACK_EYE_SOURCE_FRAME
        < CLIP01_REPAIR_START_FRAME
        < CLIP01_REPAIR_END_FRAME
        == CLIP01_FREEZE_SOURCE_FRAME
        < FRAMES_PER_CLIP
    ):
        raise RuntimeError("Clip01 split-screen repair frame lock is internally invalid")
    if not (
        0.98 <= CLIP01_MATCH_SSIM_MIN <= 1.0
        and 0.0 < CLIP01_DISTINCT_SSIM_MAX < CLIP01_MATCH_SSIM_MIN
    ):
        raise RuntimeError("Clip01 repair SSIM thresholds are internally invalid")
    return {
        "accepted_raw_sha256": CLIP01_ACCEPTED_RAW_SHA256,
        "preserved_red_to_black_transition_frame": CLIP01_EYE_REPAIR_START_FRAME - 1,
        "black_eye_replaced_frames": [
            CLIP01_EYE_REPAIR_START_FRAME,
            CLIP01_EYE_REPAIR_END_FRAME - 1,
        ],
        "black_eye_freeze_source_frame": CLIP01_BLACK_EYE_SOURCE_FRAME,
        "first_unmodified_black_eye_frame": CLIP01_EYE_REPAIR_END_FRAME,
        "black_eye_replacement_frame_count": CLIP01_EYE_REPAIR_END_FRAME
        - CLIP01_EYE_REPAIR_START_FRAME,
        "preserved_jian_ci_frame": CLIP01_REPAIR_START_FRAME - 1,
        "replaced_frames": [CLIP01_REPAIR_START_FRAME, CLIP01_REPAIR_END_FRAME - 1],
        "fullscreen_su_wang_freeze_source_frame": CLIP01_FREEZE_SOURCE_FRAME,
        "first_unmodified_fullscreen_su_wang_frame": CLIP01_REPAIR_END_FRAME,
        "replacement_frame_count": CLIP01_REPAIR_END_FRAME
        - CLIP01_REPAIR_START_FRAME,
        "preservation_ssim_min": CLIP01_MATCH_SSIM_MIN,
        "jian_vs_su_wang_ssim_max": CLIP01_DISTINCT_SSIM_MAX,
        "plan_independent": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the deterministic S1E03 12x5-second final master."
    )
    parser.add_argument(
        "--gate-dir",
        type=Path,
        help="Downloaded gate artifact directory containing clip 01 (searched recursively).",
    )
    parser.add_argument(
        "--remainder-dir",
        type=Path,
        help="Downloaded remainder artifact directory containing clips 02-12 (searched recursively).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "output" / "s1e03-final-v1",
        help="Delivery directory (default: output/s1e03-final-v1).",
    )
    parser.add_argument(
        "--fonts-dir",
        type=Path,
        help="Optional directory containing a Simplified-Chinese Noto/Source Han Sans font.",
    )
    parser.add_argument(
        "--no-drone",
        action="store_true",
        help="Do not synthesize or mix the original low suspense drone.",
    )
    parser.add_argument(
        "--drone-gain-db",
        type=float,
        default=DEFAULT_DRONE_GAIN_DB,
        help="Drone gain before dialogue-keyed ducking; allowed range -60..-30 dB.",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Validate the plan, deterministic overlays, tools and fonts without clip inputs.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def command_text(command: Iterable[str]) -> str:
    return shlex.join(str(item) for item in command)


def run_command(
    command: list[str],
    *,
    capture: bool = False,
    quiet: bool = False,
) -> subprocess.CompletedProcess[str]:
    if not quiet:
        print(f"+ {command_text(command)}", flush=True)
    result = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if result.returncode:
        detail = ""
        if capture:
            combined = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
            detail = f"\n{combined[-8000:]}" if combined else ""
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: "
            f"{command_text(command)}{detail}"
        )
    return result


def require_executable(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise RuntimeError(f"Required executable is missing: {name}")
    return executable


def safe_source_path(relative: str) -> Path:
    candidate = (SOURCE_DIR / relative).resolve()
    source_root = SOURCE_DIR.resolve()
    if candidate != source_root and source_root not in candidate.parents:
        raise RuntimeError(f"Source reference escapes references/s1e03: {relative}")
    if not candidate.is_file():
        raise RuntimeError(f"Required source reference is missing: {relative}")
    return candidate


def load_and_validate_plan() -> dict[str, Any]:
    if not PLAN_PATH.is_file():
        raise RuntimeError(f"S1E03 plan is missing: {PLAN_PATH}")
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    required = {
        "schema_version": 3,
        "episode": EPISODE,
        "duration_seconds_per_clip": 5,
        "clip_count": 12,
        "shots_per_clip": 3,
        "generate_audio": True,
    }
    for key, expected in required.items():
        if plan.get(key) != expected:
            raise RuntimeError(
                f"Invalid plan value for {key}: expected {expected!r}, got {plan.get(key)!r}"
            )

    clips = plan.get("clips")
    if not isinstance(clips, list) or [clip.get("id") for clip in clips] != CLIP_IDS:
        raise RuntimeError("Plan must contain clips 01 through 12 exactly once and in order")

    expected_header = (
        f"《{plan['series_title_zh']}》｜{plan['episode']}"
        f"《{plan['episode_title_zh']}》｜制作：{plan['maker_zh']}"
    )
    if plan.get("persistent_header") != expected_header:
        raise RuntimeError(
            "Persistent header does not match the locked series, episode, title and maker"
        )

    for clip in clips:
        dialogue = clip.get("dialogue")
        if not isinstance(dialogue, list) or not dialogue:
            raise RuntimeError(f"Clip {clip['id']} contains no locked dialogue")
        for line in dialogue:
            start = float(line["start"])
            end = float(line["end"])
            if not 0.0 <= start < end <= 5.0:
                raise RuntimeError(f"Invalid dialogue timing in clip {clip['id']}: {line}")
            for field in ("speaker_zh", "speaker_en", "zh", "en"):
                if not str(line.get(field, "")).strip():
                    raise RuntimeError(f"Missing {field} in clip {clip['id']} dialogue")

    source_hashes = plan.get("source_sha256")
    if not isinstance(source_hashes, dict) or not source_hashes:
        raise RuntimeError("Plan contains no locked source hashes")
    for relative, expected_digest in source_hashes.items():
        source = safe_source_path(relative)
        actual_digest = sha256(source)
        if actual_digest != expected_digest:
            raise RuntimeError(
                f"Locked S1E03 source hash changed for {relative}: "
                f"expected {expected_digest}, got {actual_digest}"
            )

    clip07 = clips[6]
    replacement = clip07.get("postprocess")
    locked_replacement = "source_refs/container07_exact.png"
    if not isinstance(replacement, dict):
        raise RuntimeError("Clip 07 deterministic replacement is missing from the plan")
    if replacement.get("replace_first_shot_with") != locked_replacement:
        raise RuntimeError("Clip 07 replacement path changed")
    if float(replacement.get("start", -1)) != 0.0 or float(replacement.get("end", -1)) != 1.2:
        raise RuntimeError("Clip 07 replacement interval must remain 0.00-1.20 seconds")
    container_image = safe_source_path(locked_replacement)
    expected_container_hash = plan.get("source_sha256", {}).get(locked_replacement)
    actual_container_hash = sha256(container_image)
    if not expected_container_hash or actual_container_hash != expected_container_hash:
        raise RuntimeError(
            f"Container-07 source hash mismatch: expected {expected_container_hash}, "
            f"got {actual_container_hash}"
        )

    clip12 = clips[11]
    clock_overlay = clip12.get("postprocess")
    if not isinstance(clock_overlay, dict):
        raise RuntimeError("Clip 12 deterministic 10:54 overlay is missing from the plan")
    if clock_overlay.get("add_exact_time_card") != "10:54":
        raise RuntimeError("Clip 12 deterministic time card must remain 10:54")
    if (
        float(clock_overlay.get("start", -1)) != 2.45
        or float(clock_overlay.get("end", -1)) != 4.80
        or clock_overlay.get("clock_face_must_be_covered_if_incorrect") is not True
    ):
        raise RuntimeError("Clip 12 10:54 overlay policy or timing changed")
    if not any("4.80-5.00 hard cut to black" in shot for shot in clip12.get("shots", [])):
        raise RuntimeError("Clip 12 no longer contains the locked 4.80-5.00 black cut")

    return plan


def available_font_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in {".ttf", ".otf", ".ttc"}
    )


def looks_like_cjk_font(path: Path) -> bool:
    compact = re.sub(r"[^a-z0-9]", "", path.name.lower())
    return (
        ("notosans" in compact and ("sc" in compact or "cjk" in compact))
        or "sourcehansans" in compact
    )


def choose_font_file(files: list[Path]) -> Path:
    cjk = [path for path in files if looks_like_cjk_font(path)]
    if not cjk:
        raise RuntimeError(
            "No Simplified-Chinese Noto/Source Han Sans font found. Install "
            "fonts-noto-cjk or pass --fonts-dir."
        )
    preference = (
        "NotoSansSC-Regular.ttf",
        "NotoSansCJKsc-Regular.otf",
        "NotoSansCJK-Regular.ttc",
        "SourceHanSansSC-Regular.otf",
    )
    by_name = {path.name: path for path in cjk}
    for name in preference:
        if name in by_name:
            return by_name[name]
    regular = [path for path in cjk if "regular" in path.name.lower()]
    return regular[0] if regular else cjk[0]


def font_family_from_file(path: Path) -> str:
    scanner = shutil.which("fc-scan")
    if scanner:
        result = subprocess.run(
            [scanner, "--format=%{family[0]}\\n", str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
        families = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        for family in families:
            if re.search(r"(?:CJK\s+SC|Sans\s+SC|Hans|Simplified)", family, re.I):
                return family
        if families:
            return families[0]
    compact = path.name.lower()
    if "cjk" in compact:
        return "Noto Sans CJK SC"
    if "sourcehan" in compact:
        return "Source Han Sans SC"
    return "Noto Sans SC"


def resolve_font_bundle(explicit: Path | None) -> tuple[list[Path], str, Path]:
    candidates: list[Path] = []
    if explicit:
        candidates.append(explicit.expanduser().resolve())
    candidates.extend(
        [
            ROOT / "fonts",
            ROOT / "assets" / "fonts",
            ROOT.parent
            / "comfy-cli-s1e01"
            / "deliverables"
            / "s1e02_five_second_v3"
            / "fonts",
            Path("/usr/share/fonts/opentype/noto"),
            Path("/usr/share/fonts/truetype/noto"),
            Path("/usr/local/share/fonts"),
        ]
    )
    errors: list[str] = []
    for directory in candidates:
        files = available_font_files(directory)
        if not files:
            continue
        try:
            selected = choose_font_file(files)
        except RuntimeError as exc:
            errors.append(f"{directory}: {exc}")
            continue
        cjk_files = [path for path in files if looks_like_cjk_font(path)]
        family = font_family_from_file(selected)
        return cjk_files, family, directory
    detail = "\n".join(errors)
    raise RuntimeError(
        "No usable CJK font bundle found. Install fonts-noto-cjk or pass --fonts-dir."
        + (f"\n{detail}" if detail else "")
    )


def copy_font_bundle(files: list[Path], destination: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for source in files:
        target = destination / source.name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        copied.append(target)
    return copied


def ass_centiseconds(seconds: float | Decimal) -> int:
    value = Decimal(str(seconds)) * Decimal(100)
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def ass_time(seconds: float | Decimal) -> str:
    total = ass_centiseconds(seconds)
    hours, remainder = divmod(total, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    secs, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def ass_text(value: str) -> str:
    return (
        str(value)
        .replace("\\", "／")
        .replace("{", "｛")
        .replace("}", "｝")
        .replace("\r\n", "\\N")
        .replace("\n", "\\N")
    )


def ass_event(
    layer: int,
    start: float,
    end: float,
    style: str,
    name: str,
    text: str,
) -> str:
    return (
        f"Dialogue: {layer},{ass_time(start)},{ass_time(end)},{style},"
        f"{ass_text(name)},0,0,0,,{ass_text(text)}"
    )


def build_ass(plan: dict[str, Any], font_family: str) -> str:
    if "," in font_family:
        raise RuntimeError(f"ASS font family contains an unsupported comma: {font_family}")
    header = plan["persistent_header"]
    lines = [
        "[Script Info]",
        f"Title: {EPISODE} {plan['episode_title_zh']}",
        "ScriptType: v4.00+",
        f"PlayResX: {WIDTH}",
        f"PlayResY: {HEIGHT}",
        "ScaledBorderAndShadow: yes",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding"
        ),
        (
            f"Style: Top,{font_family},28,&H00F8F8F8,&H00F8F8F8,&H00000000,"
            "&H78000000,-1,0,0,0,100,100,0,0,3,2,0,8,28,28,18,1"
        ),
        (
            f"Style: ZH,{font_family},36,&H00F8F3E8,&H00F8F3E8,&H00000000,"
            "&H70000000,-1,0,0,0,100,100,0,0,3,2.5,0,2,34,34,56,1"
        ),
        (
            f"Style: EN,{font_family},23,&H00FFFFFF,&H00FFFFFF,&H00000000,"
            "&H70000000,0,0,0,0,100,100,0,0,3,2,0,2,44,44,18,1"
        ),
        (
            f"Style: Card,{font_family},44,&H00F8F3E8,&H00F8F3E8,&H00000000,"
            "&H85000000,-1,0,0,0,100,100,1,0,3,2.5,0,5,40,40,0,1"
        ),
        (
            f"Style: ClockMask,{font_family},1,&H0010161E,&H0010161E,&H0010161E,"
            "&H0010161E,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1"
        ),
        (
            f"Style: Clock,{font_family},48,&H00F8F3E8,&H00F8F3E8,&H00000000,"
            "&H00000000,-1,0,0,0,100,100,2,0,1,2.5,0,5,0,0,0,1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ass_event(3, 0.0, 60.0, "Top", "", header),
        ass_event(2, 10.10, 11.25, "Card", "", "第三天\nDAY 3"),
    ]

    for clip in plan["clips"]:
        clip_offset = (int(clip["id"]) - 1) * 5.0
        for dialogue in clip["dialogue"]:
            start = clip_offset + float(dialogue["start"])
            end = clip_offset + float(dialogue["end"])
            zh = f"{dialogue['speaker_zh']}：{dialogue['zh']}"
            en = f"{dialogue['speaker_en']}: {dialogue['en']}"
            lines.append(
                ass_event(1, start, end, "ZH", dialogue["speaker_zh"], zh)
            )
            lines.append(
                ass_event(1, start, end, "EN", dialogue["speaker_en"], en)
            )

    # Clip 12's plan owns the exact post-only time evidence.  This stays
    # independent of whatever unreadable markings the generator attempted.
    clock = plan["clips"][11]["postprocess"]
    clock_offset = 55.0
    clock_start = clock_offset + float(clock["start"])
    clock_end = clock_offset + float(clock["end"])
    # The accepted third panel fixes the wall clock in the upper-left evidence
    # region.  An opaque board-region card therefore both hides any generated
    # contradictory hands/digits and supplies the exact verified time.  The
    # separately rendered proof frame remains mandatory visual QA.
    lines.append(
        f"Dialogue: 2,{ass_time(clock_start)},{ass_time(clock_end)},ClockMask,,"
        "0,0,0,,{\\an7\\pos(32,64)\\p1}m 0 0 l 300 0 300 166 0 166{\\p0}"
    )
    lines.append(
        f"Dialogue: 3,{ass_time(clock_start)},{ass_time(clock_end)},Clock,,"
        f"0,0,0,,{{\\an5\\pos(182,147)}}{ass_text(str(clock['add_exact_time_card']))}"
    )
    return "\n".join(lines) + "\n"


def validate_ass(ass: str, plan: dict[str, Any]) -> None:
    if plan["persistent_header"] not in ass:
        raise RuntimeError("Generated ASS lost the persistent header")
    if "Dialogue: 3,0:00:00.00,0:01:00.00,Top" not in ass:
        raise RuntimeError("Persistent header is not locked to the complete 60-second programme")
    if "第三天\\NDAY 3" not in ass:
        raise RuntimeError("Third Day card is missing")
    if "0:00:57.45,0:00:59.80,Clock" not in ass or "10:54" not in ass:
        raise RuntimeError("Clip 12 deterministic 10:54 evidence overlay is missing")
    if "ClockMask" not in ass or "m 0 0 l 300 0 300 166 0 166" not in ass:
        raise RuntimeError("Clip 12 deterministic clock-face mask is missing")
    expected_dialogue_events = sum(len(clip["dialogue"]) for clip in plan["clips"]) * 2
    actual_dialogue_events = sum(
        1 for line in ass.splitlines() if ",ZH," in line or ",EN," in line
    )
    if actual_dialogue_events != expected_dialogue_events:
        raise RuntimeError(
            f"ASS dialogue count mismatch: {actual_dialogue_events} != {expected_dialogue_events}"
        )


def validate_tools() -> dict[str, str]:
    ffmpeg = require_executable("ffmpeg")
    ffprobe = require_executable("ffprobe")
    filters = run_command(
        [ffmpeg, "-hide_banner", "-filters"], capture=True, quiet=True
    ).stdout
    for required_filter in (
        "ass",
        "fps",
        "loudnorm",
        "sidechaincompress",
        "ssim",
        "tile",
    ):
        if not re.search(rf"\b{re.escape(required_filter)}\b", filters):
            raise RuntimeError(f"ffmpeg is missing required filter: {required_filter}")
    encoders = run_command(
        [ffmpeg, "-hide_banner", "-encoders"], capture=True, quiet=True
    ).stdout
    for encoder in ("libx264", "aac", "pcm_s16le"):
        if not re.search(rf"\b{re.escape(encoder)}\b", encoders):
            raise RuntimeError(f"ffmpeg is missing required encoder: {encoder}")
    return {"ffmpeg": ffmpeg, "ffprobe": ffprobe}


def prepare_only(args: argparse.Namespace) -> None:
    plan = load_and_validate_plan()
    clip01_lock = validate_clip01_repair_lock()
    tools = validate_tools()
    font_files, font_family, font_directory = resolve_font_bundle(args.fonts_dir)
    ass = build_ass(plan, font_family)
    validate_ass(ass, plan)
    if not -60.0 <= args.drone_gain_db <= -30.0:
        raise RuntimeError("--drone-gain-db must remain between -60 and -30 dB")
    report = {
        "status": "static_validation_ok",
        "paid_generation_requests": 0,
        "plan": str(PLAN_PATH),
        "plan_sha256": sha256(PLAN_PATH),
        "container07_sha256": sha256(
            safe_source_path("source_refs/container07_exact.png")
        ),
        "clip_ids": CLIP_IDS,
        "clip01_plan_independent_repairs": clip01_lock,
        "clip07_replacement_frames": CLIP07_REPLACEMENT_FRAMES,
        "clip12_black_frames": CLIP12_BLACK_FRAMES,
        "ass_sha256": sha256_text(ass),
        "persistent_header": plan["persistent_header"],
        "font_family": font_family,
        "font_source_directory": str(font_directory),
        "font_files": [str(path) for path in font_files],
        "tools": tools,
        "drone_default_enabled": not args.no_drone,
        "drone_gain_db": args.drone_gain_db,
        "note": "Static validation only; no input clips read and no paid request made.",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def recursive_exact_file(directory: Path, filename: str) -> Path:
    root = directory.expanduser().resolve()
    if not root.is_dir():
        raise RuntimeError(f"Artifact directory does not exist: {root}")
    matches = sorted(
        path.resolve()
        for path in root.rglob("*")
        if path.is_file() and path.name.lower() == filename.lower()
    )
    if not matches:
        raise RuntimeError(f"Could not find {filename} below {root}")
    if len(matches) > 1:
        listed = "\n".join(str(path) for path in matches)
        raise RuntimeError(f"Ambiguous raw clip {filename}; found multiple files:\n{listed}")
    return matches[0]


def discover_raw_clips(gate_dir: Path, remainder_dir: Path) -> dict[str, Path]:
    clips: dict[str, Path] = {}
    for clip_id in CLIP_IDS:
        search_root = gate_dir if clip_id == "01" else remainder_dir
        clips[clip_id] = recursive_exact_file(
            search_root, f"S1E03_clip_{clip_id}_raw.mp4"
        )
    if len({path.resolve() for path in clips.values()}) != 12:
        raise RuntimeError("The twelve discovered raw clips are not twelve distinct files")
    return clips


def probe_media(path: Path, *, count_frames: bool = False) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
    ]
    if count_frames:
        command.insert(3, "-count_frames")
    command.append(str(path))
    result = run_command(command, capture=True, quiet=True)
    return json.loads(result.stdout)


def first_stream(probe: dict[str, Any], stream_type: str) -> dict[str, Any]:
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == stream_type:
            return stream
    raise RuntimeError(f"Probe contains no {stream_type} stream")


def parse_fraction(value: str | None) -> Fraction:
    if not value or value == "0/0":
        return Fraction(0, 1)
    return Fraction(value)


def duration_from_probe(probe: dict[str, Any]) -> float:
    value = probe.get("format", {}).get("duration")
    return float(value or 0.0)


def max_volume_db(path: Path) -> float:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-map",
            "0:a:0",
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
    if result.returncode:
        raise RuntimeError(f"Could not measure source audio: {path}\n{result.stderr[-4000:]}")
    match = re.search(r"max_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB", result.stderr)
    if not match or match.group(1) == "-inf":
        raise RuntimeError(f"Raw clip has silent audio: {path}")
    return float(match.group(1))


def validate_raw_clip(
    clip_id: str,
    path: Path,
    *,
    required_audio_seconds: float,
) -> dict[str, Any]:
    if path.stat().st_size < 100_000:
        raise RuntimeError(f"Raw clip {clip_id} is unexpectedly small: {path}")
    probe = probe_media(path)
    video = first_stream(probe, "video")
    audio = first_stream(probe, "audio")
    duration = duration_from_probe(probe)
    if not 4.3 <= duration <= 5.8:
        raise RuntimeError(f"Raw clip {clip_id} duration is invalid: {duration:.3f}s")
    # Count decoded 48 kHz sample frames instead of trusting only container
    # metadata.  Some MP4s omit per-stream duration even when the video track
    # is longer than a truncated audio track.
    decoded_source_samples = decoded_audio_samples(path)
    audio_duration = decoded_source_samples / SAMPLE_RATE
    if audio_duration + 0.02 < required_audio_seconds:
        raise RuntimeError(
            f"Raw clip {clip_id} audio is too short to preserve the planned dialogue: "
            f"{audio_duration:.3f}s < {required_audio_seconds:.3f}s"
        )
    peak = max_volume_db(path)
    if peak < -55.0:
        raise RuntimeError(
            f"Raw clip {clip_id} audio is too quiet to preserve dialogue: {peak:.1f} dB"
        )
    return {
        "clip_id": clip_id,
        "path": str(path),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
        "duration_seconds": duration,
        "video_codec": video.get("codec_name"),
        "width": video.get("width"),
        "height": video.get("height"),
        "source_frame_rate": video.get("avg_frame_rate"),
        "audio_codec": audio.get("codec_name"),
        "audio_sample_rate": audio.get("sample_rate"),
        "audio_channels": audio.get("channels"),
        "audio_duration_seconds": audio_duration,
        "decoded_source_audio_samples_at_48000": decoded_source_samples,
        "required_audio_through_seconds": required_audio_seconds,
        "max_volume_db": peak,
    }


def decoded_audio_samples(path: Path) -> int:
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-ac",
        str(CHANNELS),
        "-ar",
        str(SAMPLE_RATE),
        "-f",
        "s16le",
        "pipe:1",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.stdout is None or process.stderr is None:
        raise RuntimeError("Could not open ffmpeg audio-count pipes")
    byte_count = 0
    while True:
        chunk = process.stdout.read(1024 * 1024)
        if not chunk:
            break
        byte_count += len(chunk)
    stderr = process.stderr.read().decode("utf-8", errors="replace")
    return_code = process.wait()
    if return_code:
        raise RuntimeError(f"Audio decode failed for {path}:\n{stderr[-4000:]}")
    bytes_per_sample_frame = CHANNELS * 2
    if byte_count % bytes_per_sample_frame:
        raise RuntimeError(f"Decoded audio byte count is not sample-aligned: {path}")
    return byte_count // bytes_per_sample_frame


def decoded_audio_sha256(path: Path) -> str:
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-ac",
        str(CHANNELS),
        "-ar",
        str(SAMPLE_RATE),
        "-f",
        "s16le",
        "pipe:1",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.stdout is None or process.stderr is None:
        raise RuntimeError("Could not open ffmpeg audio-hash pipes")
    digest = hashlib.sha256()
    while True:
        chunk = process.stdout.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    stderr = process.stderr.read().decode("utf-8", errors="replace")
    return_code = process.wait()
    if return_code:
        raise RuntimeError(f"Audio decode failed for {path}:\n{stderr[-4000:]}")
    return digest.hexdigest()


def normalized_summary(path: Path, expected_frames: int, expected_samples: int) -> dict[str, Any]:
    probe = probe_media(path, count_frames=True)
    video = first_stream(probe, "video")
    audio = first_stream(probe, "audio")
    frames = int(video.get("nb_read_frames") or video.get("nb_frames") or 0)
    samples = decoded_audio_samples(path)
    frame_rate = parse_fraction(video.get("avg_frame_rate"))
    checks = {
        "width": int(video.get("width") or 0) == WIDTH,
        "height": int(video.get("height") or 0) == HEIGHT,
        "frame_rate": frame_rate == Fraction(FPS, 1),
        "frame_count": frames == expected_frames,
        "audio_sample_rate": int(audio.get("sample_rate") or 0) == SAMPLE_RATE,
        "audio_channels": int(audio.get("channels") or 0) == CHANNELS,
        "decoded_audio_samples": samples == expected_samples,
    }
    if not all(checks.values()):
        raise RuntimeError(f"Normalized media failed QC: {path}\n{json.dumps(checks, indent=2)}")
    return {
        "path": str(path),
        "sha256": sha256(path),
        "duration_seconds": duration_from_probe(probe),
        "width": video.get("width"),
        "height": video.get("height"),
        "frame_rate": str(frame_rate),
        "frame_count": frames,
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "audio_sample_rate": int(audio.get("sample_rate") or 0),
        "audio_channels": int(audio.get("channels") or 0),
        "decoded_audio_samples": samples,
        "checks": checks,
    }


def x264_intermediate_options() -> list[str]:
    return [
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "12",
        "-profile:v",
        "high",
        "-level:v",
        "4.0",
        "-pix_fmt",
        "yuv420p",
        "-colorspace",
        "bt709",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-color_range",
        "tv",
        "-x264-params",
        "keyint=120:min-keyint=120:scenecut=0",
    ]


def normalize_clip(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    video_filter = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"fps={FPS}:start_time=0,tpad=stop_mode=clone:stop_duration=5,"
        f"trim=end_frame={FRAMES_PER_CLIP},setpts=N/({FPS}*TB),setsar=1,format=yuv420p"
    )
    audio_filter = (
        f"aresample={SAMPLE_RATE}:async=1:first_pts=0,"
        f"aformat=sample_fmts=s16:sample_rates={SAMPLE_RATE}:channel_layouts=stereo,"
        f"apad=pad_dur=5,atrim=end_sample={SAMPLES_PER_CLIP},asetpts=N/SR/TB"
    )
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0",
        "-vf",
        video_filter,
        "-af",
        audio_filter,
        "-frames:v",
        str(FRAMES_PER_CLIP),
        "-fps_mode",
        "cfr",
        *x264_intermediate_options(),
        "-c:a",
        "pcm_s16le",
        "-ar",
        str(SAMPLE_RATE),
        "-ac",
        str(CHANNELS),
        "-map_metadata",
        "-1",
        str(destination),
    ]
    run_command(command)


def patch_clip01_accepted_gate(base: Path, destination: Path) -> None:
    """Apply both accepted-gate picture-only repairs to Clip01.

    Frames 0-7 remain untouched; black-eye frame 12 supplies output frames
    8-11 and the original stream resumes at frame 12.  Frames 12-29 then remain
    untouched; full-screen Su Wang frame 54 supplies output frames 30-53 and
    the original stream resumes at frame 54.  Both joins share their freeze
    source with the first resumed frame.  The complete normalized PCM audio is
    stream-copied without retiming.
    """
    eye_replacement_count = (
        CLIP01_EYE_REPAIR_END_FRAME - CLIP01_EYE_REPAIR_START_FRAME
    )
    replacement_count = CLIP01_REPAIR_END_FRAME - CLIP01_REPAIR_START_FRAME
    filter_complex = (
        "[0:v:0]split=5[eyeheadsrc][eyefreezesrc][midsrc][gridsrc][tailsrc];"
        f"[eyeheadsrc]trim=end_frame={CLIP01_EYE_REPAIR_START_FRAME},"
        f"setpts=N/({FPS}*TB),format=yuv420p[eyehead];"
        f"[eyefreezesrc]trim=start_frame={CLIP01_BLACK_EYE_SOURCE_FRAME}:"
        f"end_frame={CLIP01_BLACK_EYE_SOURCE_FRAME + 1},setpts=N/({FPS}*TB),"
        f"tpad=stop_mode=clone:stop_duration=1,trim=end_frame={eye_replacement_count},"
        f"setpts=N/({FPS}*TB),format=yuv420p[eyefreeze];"
        f"[midsrc]trim=start_frame={CLIP01_EYE_REPAIR_END_FRAME}:"
        f"end_frame={CLIP01_REPAIR_START_FRAME},setpts=N/({FPS}*TB),"
        "format=yuv420p[mid];"
        f"[gridsrc]trim=start_frame={CLIP01_FREEZE_SOURCE_FRAME}:"
        f"end_frame={CLIP01_FREEZE_SOURCE_FRAME + 1},setpts=N/({FPS}*TB),"
        f"tpad=stop_mode=clone:stop_duration=1,trim=end_frame={replacement_count},"
        f"setpts=N/({FPS}*TB),format=yuv420p[gridfreeze];"
        f"[tailsrc]trim=start_frame={CLIP01_REPAIR_END_FRAME}:"
        f"end_frame={FRAMES_PER_CLIP},setpts=N/({FPS}*TB),format=yuv420p[tail];"
        f"[eyehead][eyefreeze][mid][gridfreeze][tail]concat=n=5:v=1:a=0,fps={FPS},"
        f"trim=end_frame={FRAMES_PER_CLIP},setpts=N/({FPS}*TB),format=yuv420p[v]"
    )
    run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-i",
            str(base),
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "0:a:0",
            "-frames:v",
            str(FRAMES_PER_CLIP),
            "-fps_mode",
            "cfr",
            *x264_intermediate_options(),
            "-c:a",
            "copy",
            "-map_metadata",
            "-1",
            str(destination),
        ]
    )


def patch_clip07(base: Path, image: Path, destination: Path) -> None:
    filter_complex = (
        f"[1:v:0]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={FPS},"
        f"trim=end_frame={CLIP07_REPLACEMENT_FRAMES},"
        f"setpts=N/({FPS}*TB),format=yuv420p[head];"
        f"[0:v:0]trim=start_frame={CLIP07_REPLACEMENT_FRAMES}:end_frame={FRAMES_PER_CLIP},"
        f"setpts=N/({FPS}*TB),setsar=1,format=yuv420p[tail];"
        f"[head][tail]concat=n=2:v=1:a=0,fps={FPS},"
        f"trim=end_frame={FRAMES_PER_CLIP},setpts=N/({FPS}*TB),format=yuv420p[v]"
    )
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-i",
        str(base),
        "-loop",
        "1",
        "-framerate",
        str(FPS),
        "-i",
        str(image),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "0:a:0",
        "-frames:v",
        str(FRAMES_PER_CLIP),
        "-fps_mode",
        "cfr",
        *x264_intermediate_options(),
        "-c:a",
        "copy",
        "-map_metadata",
        "-1",
        str(destination),
    ]
    run_command(command)


def patch_clip12_black(base: Path, destination: Path) -> None:
    black_duration = CLIP12_BLACK_FRAMES / FPS
    filter_complex = (
        f"[0:v:0]trim=end_frame={CLIP12_BODY_FRAMES},"
        f"setpts=N/({FPS}*TB),format=yuv420p[body];"
        f"[1:v:0]trim=end_frame={CLIP12_BLACK_FRAMES},"
        f"setpts=N/({FPS}*TB),format=yuv420p[black];"
        f"[body][black]concat=n=2:v=1:a=0,fps={FPS},"
        f"trim=end_frame={FRAMES_PER_CLIP},setpts=N/({FPS}*TB),format=yuv420p[v]"
    )
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-i",
        str(base),
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s={WIDTH}x{HEIGHT}:r={FPS}:d={black_duration:.9f}",
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "0:a:0",
        "-frames:v",
        str(FRAMES_PER_CLIP),
        "-fps_mode",
        "cfr",
        *x264_intermediate_options(),
        "-c:a",
        "copy",
        "-map_metadata",
        "-1",
        str(destination),
    ]
    run_command(command)


def measure_ssim(
    first: Path,
    second: Path,
    *,
    first_filter: str,
    second_filter: str,
) -> float:
    filter_complex = (
        f"[0:v:0]{first_filter},setpts=N/({FPS}*TB)[first];"
        f"[1:v:0]{second_filter},setpts=N/({FPS}*TB)[second];"
        "[first][second]ssim"
    )
    result = run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(first),
            "-i",
            str(second),
            "-filter_complex",
            filter_complex,
            "-an",
            "-f",
            "null",
            "-",
        ],
        capture=True,
        quiet=True,
    )
    matches = re.findall(r"All:([0-9]+(?:\.[0-9]+)?)", result.stderr)
    if not matches:
        raise RuntimeError(f"Could not parse SSIM result:\n{result.stderr[-4000:]}")
    return float(matches[-1])


def clip01_repair_metrics(repaired: Path, normalized_base: Path) -> dict[str, Any]:
    eye_replacement_count = (
        CLIP01_EYE_REPAIR_END_FRAME - CLIP01_EYE_REPAIR_START_FRAME
    )
    replacement_count = CLIP01_REPAIR_END_FRAME - CLIP01_REPAIR_START_FRAME
    preserved_frame7 = measure_ssim(
        repaired,
        normalized_base,
        first_filter="trim=start_frame=7:end_frame=8",
        second_filter="trim=start_frame=7:end_frame=8",
    )
    black_eye_freeze8_11 = measure_ssim(
        repaired,
        normalized_base,
        first_filter=(
            f"trim=start_frame={CLIP01_EYE_REPAIR_START_FRAME}:"
            f"end_frame={CLIP01_EYE_REPAIR_END_FRAME}"
        ),
        second_filter=(
            f"trim=start_frame={CLIP01_BLACK_EYE_SOURCE_FRAME}:"
            f"end_frame={CLIP01_BLACK_EYE_SOURCE_FRAME + 1},setpts=N/({FPS}*TB),"
            f"tpad=stop_mode=clone:stop_duration=1,trim=end_frame={eye_replacement_count}"
        ),
    )
    resumed_frame12 = measure_ssim(
        repaired,
        normalized_base,
        first_filter="trim=start_frame=12:end_frame=13",
        second_filter="trim=start_frame=12:end_frame=13",
    )
    transition_frame7_vs_black_frame12 = measure_ssim(
        repaired,
        normalized_base,
        first_filter="trim=start_frame=7:end_frame=8",
        second_filter="trim=start_frame=12:end_frame=13",
    )
    preserved_frame29 = measure_ssim(
        repaired,
        normalized_base,
        first_filter="trim=start_frame=29:end_frame=30",
        second_filter="trim=start_frame=29:end_frame=30",
    )
    freeze_to_fullscreen54 = measure_ssim(
        repaired,
        normalized_base,
        first_filter=(
            f"trim=start_frame={CLIP01_REPAIR_START_FRAME}:"
            f"end_frame={CLIP01_REPAIR_END_FRAME}"
        ),
        second_filter=(
            f"trim=start_frame={CLIP01_FREEZE_SOURCE_FRAME}:"
            f"end_frame={CLIP01_FREEZE_SOURCE_FRAME + 1},setpts=N/({FPS}*TB),"
            f"tpad=stop_mode=clone:stop_duration=1,trim=end_frame={replacement_count}"
        ),
    )
    resumed_frame54 = measure_ssim(
        repaired,
        normalized_base,
        first_filter="trim=start_frame=54:end_frame=55",
        second_filter="trim=start_frame=54:end_frame=55",
    )
    jian_frame29_vs_su_wang_frame54 = measure_ssim(
        repaired,
        normalized_base,
        first_filter="trim=start_frame=29:end_frame=30",
        second_filter="trim=start_frame=54:end_frame=55",
    )
    base_audio_pcm_sha256 = decoded_audio_sha256(normalized_base)
    repaired_audio_pcm_sha256 = decoded_audio_sha256(repaired)
    checks = {
        "frame7_red_to_black_transition_preserved": (
            preserved_frame7 >= CLIP01_MATCH_SSIM_MIN
        ),
        "frames8_11_match_black_eye_frame12": (
            black_eye_freeze8_11 >= CLIP01_MATCH_SSIM_MIN
        ),
        "frame12_resumes_on_same_black_eye_frame": (
            resumed_frame12 >= CLIP01_MATCH_SSIM_MIN
        ),
        "frame7_transition_is_distinct_from_black_eye_frame12": (
            transition_frame7_vs_black_frame12 <= CLIP01_DISTINCT_SSIM_MAX
        ),
        "frame29_preserved": preserved_frame29 >= CLIP01_MATCH_SSIM_MIN,
        "frames30_53_match_fullscreen_frame54": (
            freeze_to_fullscreen54 >= CLIP01_MATCH_SSIM_MIN
        ),
        "frame54_resumes_on_same_fullscreen_frame": (
            resumed_frame54 >= CLIP01_MATCH_SSIM_MIN
        ),
        "frame29_jian_is_distinct_from_frame54_su_wang": (
            jian_frame29_vs_su_wang_frame54 <= CLIP01_DISTINCT_SSIM_MAX
        ),
        "normalized_audio_is_bit_exact_after_repair": (
            base_audio_pcm_sha256 == repaired_audio_pcm_sha256
        ),
    }
    return {
        "preserved_frame7_ssim": preserved_frame7,
        "frames8_11_to_black_eye_frame12_ssim": black_eye_freeze8_11,
        "resumed_frame12_to_source_frame12_ssim": resumed_frame12,
        "frame7_to_frame12_ssim": transition_frame7_vs_black_frame12,
        "preserved_frame29_ssim": preserved_frame29,
        "frames30_53_to_fullscreen_frame54_ssim": freeze_to_fullscreen54,
        "resumed_frame54_to_source_frame54_ssim": resumed_frame54,
        "frame29_to_frame54_ssim": jian_frame29_vs_su_wang_frame54,
        "base_audio_pcm_sha256": base_audio_pcm_sha256,
        "repaired_audio_pcm_sha256": repaired_audio_pcm_sha256,
        "match_ssim_min": CLIP01_MATCH_SSIM_MIN,
        "distinct_ssim_max": CLIP01_DISTINCT_SSIM_MAX,
        "checks": checks,
    }


def ffconcat_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "\\\\").replace("'", "'\\''")


def concatenate_clips(clips: list[Path], list_path: Path, destination: Path) -> None:
    list_path.parent.mkdir(parents=True, exist_ok=True)
    list_path.write_text(
        "".join(f"file '{ffconcat_path(path)}'\n" for path in clips),
        encoding="utf-8",
    )
    run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-c",
            "copy",
            "-map_metadata",
            "-1",
            str(destination),
        ]
    )


def synthesize_drone(path: Path) -> None:
    """Write a deterministic original low-frequency stereo suspense texture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    total_frames = SAMPLE_RATE * PROGRAM_SECONDS
    chunk_frames = 4_800
    with wave.open(str(path), "wb") as output:
        output.setnchannels(CHANNELS)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        for first in range(0, total_frames, chunk_frames):
            payload = array("h")
            last = min(total_frames, first + chunk_frames)
            for index in range(first, last):
                t = index / SAMPLE_RATE
                fade_in = min(1.0, t / 2.0)
                fade_out = min(1.0, (PROGRAM_SECONDS - t) / 2.0)
                envelope = max(0.0, min(fade_in, fade_out))
                lfo = 0.70 + 0.20 * math.sin(2.0 * math.pi * 0.071 * t)
                pulse = 0.82 + 0.18 * math.sin(2.0 * math.pi * 0.113 * t + 0.7)
                left = envelope * (
                    0.50 * lfo * math.sin(2.0 * math.pi * 43.0 * t)
                    + 0.19 * pulse * math.sin(2.0 * math.pi * 64.5 * t + 0.35)
                    + 0.08 * math.sin(2.0 * math.pi * 86.0 * t + 1.10)
                )
                right = envelope * (
                    0.49 * lfo * math.sin(2.0 * math.pi * 43.15 * t + 0.08)
                    + 0.18 * pulse * math.sin(2.0 * math.pi * 64.3 * t + 0.52)
                    + 0.08 * math.sin(2.0 * math.pi * 86.3 * t + 1.28)
                )
                payload.append(max(-32767, min(32767, round(left * 32767))))
                payload.append(max(-32767, min(32767, round(right * 32767))))
            if sys.byteorder == "big":
                payload.byteswap()
            output.writeframesraw(payload.tobytes())


def build_mixed_program_audio(
    clean_master: Path,
    destination: Path,
    *,
    drone_path: Path | None,
    drone_gain_db: float,
) -> None:
    base_audio = (
        f"aresample={SAMPLE_RATE}:async=1:first_pts=0,"
        f"aformat=sample_fmts=s16:sample_rates={SAMPLE_RATE}:channel_layouts=stereo,"
        f"apad=pad_dur=60,atrim=end_sample={TOTAL_SAMPLES},asetpts=N/SR/TB"
    )
    if drone_path is None:
        run_command(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "warning",
                "-y",
                "-i",
                str(clean_master),
                "-map",
                "0:a:0",
                "-af",
                base_audio,
                "-c:a",
                "pcm_s16le",
                "-ar",
                str(SAMPLE_RATE),
                "-ac",
                str(CHANNELS),
                str(destination),
            ]
        )
        return

    gain = 10.0 ** (drone_gain_db / 20.0)
    filter_complex = (
        f"[0:a:0]{base_audio},asplit=2[program][key];"
        f"[1:a:0]aresample={SAMPLE_RATE},atrim=end_sample={TOTAL_SAMPLES},"
        f"asetpts=N/SR/TB,volume={gain:.9f}[drone];"
        "[drone][key]sidechaincompress=threshold=0.020:ratio=8:attack=20:"
        "release=500:makeup=1[ducked];"
        "[program][ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
        f"alimiter=limit=0.97,aresample={SAMPLE_RATE},apad=pad_dur=60,"
        f"atrim=end_sample={TOTAL_SAMPLES},asetpts=N/SR/TB[a]"
    )
    run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-i",
            str(clean_master),
            "-i",
            str(drone_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "[a]",
            "-c:a",
            "pcm_s16le",
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            str(CHANNELS),
            str(destination),
        ]
    )


def parse_loudnorm_json(stderr: str) -> dict[str, Any]:
    matches = re.findall(r"\{\s*\"input_i\".*?\}", stderr, flags=re.DOTALL)
    if not matches:
        raise RuntimeError(f"Could not parse ffmpeg loudnorm JSON:\n{stderr[-5000:]}")
    return json.loads(matches[-1])


def analyze_loudness(path: Path) -> dict[str, Any]:
    result = run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-af",
            f"loudnorm=I={TARGET_I}:LRA={TARGET_LRA}:TP={TARGET_TP}:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture=True,
        quiet=True,
    )
    return parse_loudnorm_json(result.stderr)


def normalized_program_audio(
    mixed_audio: Path, destination: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    measured = analyze_loudness(mixed_audio)
    required = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    for key in required:
        if str(measured.get(key, "")).lower() in {"", "-inf", "inf", "nan"}:
            raise RuntimeError(f"Invalid loudnorm measurement {key}: {measured.get(key)!r}")
    second_pass = (
        f"loudnorm=I={TARGET_I}:LRA={TARGET_LRA}:TP={TARGET_TP}:"
        f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:"
        f"measured_thresh={measured['input_thresh']}:offset={measured['target_offset']}:"
        "linear=true:print_format=json,"
        f"aresample={SAMPLE_RATE},aformat=sample_fmts=s16:sample_rates={SAMPLE_RATE}:"
        f"channel_layouts=stereo,apad=pad_dur=60,atrim=end_sample={TOTAL_SAMPLES},"
        "asetpts=N/SR/TB"
    )
    result = run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-y",
            "-i",
            str(mixed_audio),
            "-map",
            "0:a:0",
            "-af",
            second_pass,
            "-c:a",
            "pcm_s16le",
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            str(CHANNELS),
            str(destination),
        ],
        capture=True,
    )
    rendered = parse_loudnorm_json(result.stderr)
    samples = decoded_audio_samples(destination)
    if samples != TOTAL_SAMPLES:
        raise RuntimeError(
            f"Normalized programme audio is not exactly {TOTAL_SAMPLES} samples: {samples}"
        )
    return measured, rendered


def escape_filter_path(path: Path) -> str:
    value = str(path.resolve())
    return (
        value.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(",", "\\,")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def render_final(
    clean_master: Path,
    normalized_audio: Path,
    ass_path: Path,
    fonts_dir: Path,
    destination: Path,
    title: str,
) -> None:
    ass_filter = (
        f"ass=filename='{escape_filter_path(ass_path)}':"
        f"fontsdir='{escape_filter_path(fonts_dir)}'"
    )
    video_filter = (
        f"fps={FPS},trim=end_frame={TOTAL_FRAMES},setpts=N/({FPS}*TB),"
        f"{ass_filter},format=yuv420p"
    )
    run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-i",
            str(clean_master),
            "-i",
            str(normalized_audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-vf",
            video_filter,
            "-frames:v",
            str(TOTAL_FRAMES),
            "-fps_mode",
            "cfr",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "16",
            "-profile:v",
            "high",
            "-level:v",
            "4.0",
            "-pix_fmt",
            "yuv420p",
            "-colorspace",
            "bt709",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-color_range",
            "tv",
            "-video_track_timescale",
            "12288",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            str(CHANNELS),
            "-map_metadata",
            "-1",
            "-metadata",
            f"title={title}",
            "-movflags",
            "+faststart",
            str(destination),
        ]
    )


def render_contact_sheet(final_video: Path, destination: Path) -> None:
    # The special selections intentionally show the post-only Day 3 card,
    # Container-07 label and 10:54 clock rather than generic midpoints.
    frame_indices = [60, 180, 254, 420, 540, 660, 732, 900, 1020, 1140, 1260, 1392]
    expression = "+".join(f"eq(n,{frame})" for frame in frame_indices)
    video_filter = (
        f"select='{expression}',scale=320:180:flags=lanczos,"
        "tile=4x3:padding=4:margin=4:color=black"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-i",
            str(final_video),
            "-vf",
            video_filter,
            "-frames:v",
            "1",
            "-update",
            "1",
            "-q:v",
            "2",
            str(destination),
        ]
    )


def render_clip01_repair_proof(repaired_clip: Path, destination: Path) -> None:
    frame_indices = [29, 30, 41, 53, 54]
    expression = "+".join(f"eq(n,{frame})" for frame in frame_indices)
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-i",
            str(repaired_clip),
            "-vf",
            (
                f"select='{expression}',scale=256:144:flags=lanczos,"
                "tile=5x1:padding=4:margin=4:color=black"
            ),
            "-frames:v",
            "1",
            "-update",
            "1",
            "-q:v",
            "2",
            str(destination),
        ]
    )


def render_clip01_eye_repair_proof(repaired_clip: Path, destination: Path) -> None:
    frame_indices = [7, 8, 10, 11, 12]
    expression = "+".join(f"eq(n,{frame})" for frame in frame_indices)
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-y",
            "-i",
            str(repaired_clip),
            "-vf",
            (
                f"select='{expression}',scale=256:144:flags=lanczos,"
                "tile=5x1:padding=4:margin=4:color=black"
            ),
            "-frames:v",
            "1",
            "-update",
            "1",
            "-q:v",
            "2",
            str(destination),
        ]
    )


def render_proof_frame(final_video: Path, second: float, destination: Path) -> None:
    run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{second:.6f}",
            "-i",
            str(final_video),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(destination),
        ]
    )


def silence_intervals(path: Path) -> list[dict[str, float | None]]:
    result = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-af",
            "silencedetect=noise=-48dB:d=0.6",
            "-f",
            "null",
            "-",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(f"silencedetect failed:\n{result.stderr[-4000:]}")
    starts = [float(value) for value in re.findall(r"silence_start:\s*([0-9.]+)", result.stderr)]
    ends = [float(value) for value in re.findall(r"silence_end:\s*([0-9.]+)", result.stderr)]
    records: list[dict[str, float | None]] = []
    for index, start in enumerate(starts):
        end = ends[index] if index < len(ends) else None
        records.append(
            {
                "start": start,
                "end": end,
                "duration": (end - start) if end is not None else None,
            }
        )
    return records


def verify_full_decode(path: Path) -> None:
    run_command(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
        capture=True,
        quiet=True,
    )


def final_qc(
    final_video: Path,
    *,
    plan: dict[str, Any],
    ass_path: Path,
    font_family: str,
    font_files: list[Path],
    raw_records: list[dict[str, Any]],
    normalized_records: list[dict[str, Any]],
    clean_record: dict[str, Any],
    first_pass_loudness: dict[str, Any],
    drone_enabled: bool,
    drone_gain_db: float,
    container_path: Path,
    output_paths: dict[str, Path],
) -> dict[str, Any]:
    probe = probe_media(final_video, count_frames=True)
    video = first_stream(probe, "video")
    audio = first_stream(probe, "audio")
    frame_count = int(video.get("nb_read_frames") or video.get("nb_frames") or 0)
    frame_rate = parse_fraction(video.get("avg_frame_rate"))
    duration = duration_from_probe(probe)
    decoded_samples = decoded_audio_samples(final_video)
    loudness = analyze_loudness(final_video)
    integrated = float(loudness["input_i"])
    true_peak = float(loudness["input_tp"])
    clip01_raw = next(record for record in raw_records if record["clip_id"] == "01")
    clip01_normalized = next(
        record for record in normalized_records if record["clip_id"] == "01"
    )
    clip01_metrics = clip01_normalized["clip01_repair_metrics"]
    clip01_metric_checks = clip01_metrics["checks"]
    clip01_lock = validate_clip01_repair_lock()
    checks = {
        "duration_60_seconds": abs(duration - PROGRAM_SECONDS) <= 0.02,
        "resolution_1280x720": (
            int(video.get("width") or 0) == WIDTH
            and int(video.get("height") or 0) == HEIGHT
        ),
        "constant_24_fps": frame_rate == Fraction(FPS, 1),
        "exact_1440_video_frames": frame_count == TOTAL_FRAMES,
        "audio_aac": audio.get("codec_name") == "aac",
        "audio_48000_hz": int(audio.get("sample_rate") or 0) == SAMPLE_RATE,
        "audio_stereo": int(audio.get("channels") or 0) == CHANNELS,
        "decoded_audio_near_2880000_samples": abs(decoded_samples - TOTAL_SAMPLES) <= 1_024,
        "integrated_loudness_minus16_plusminus0_5": -16.5 <= integrated <= -15.5,
        "true_peak_at_or_below_minus1_5": true_peak <= -1.5,
        "clip01_is_exact_accepted_gate": (
            clip01_raw["sha256"] == CLIP01_ACCEPTED_RAW_SHA256
        ),
        "clip01_plan_independent_frame_lock": (
            clip01_lock["black_eye_replaced_frames"] == [8, 11]
            and clip01_lock["black_eye_freeze_source_frame"] == 12
            and clip01_lock["replaced_frames"] == [30, 53]
            and clip01_lock["fullscreen_su_wang_freeze_source_frame"] == 54
        ),
        "clip01_frame7_red_to_black_transition_preserved": bool(
            clip01_metric_checks["frame7_red_to_black_transition_preserved"]
        ),
        "clip01_frames8_11_are_black_eye_frame12": bool(
            clip01_metric_checks["frames8_11_match_black_eye_frame12"]
        ),
        "clip01_frame12_has_no_composition_jump": bool(
            clip01_metric_checks["frame12_resumes_on_same_black_eye_frame"]
        ),
        "clip01_frame7_transition_distinct_from_frame12_black_eye": bool(
            clip01_metric_checks["frame7_transition_is_distinct_from_black_eye_frame12"]
        ),
        "clip01_frame29_preserved_from_accepted_gate": bool(
            clip01_metric_checks["frame29_preserved"]
        ),
        "clip01_frames30_53_are_fullscreen_frame54": bool(
            clip01_metric_checks["frames30_53_match_fullscreen_frame54"]
        ),
        "clip01_frame54_has_no_composition_jump": bool(
            clip01_metric_checks["frame54_resumes_on_same_fullscreen_frame"]
        ),
        "clip01_frame29_jian_distinct_from_frame54_su_wang": bool(
            clip01_metric_checks["frame29_jian_is_distinct_from_frame54_su_wang"]
        ),
        "clip01_audio_bit_exact_after_picture_only_repair": bool(
            clip01_metric_checks["normalized_audio_is_bit_exact_after_repair"]
        ),
        "clip01_repair_proof_exists": output_paths["clip01_repair_proof"].is_file(),
        "clip01_eye_repair_proof_exists": output_paths[
            "clip01_eye_repair_proof"
        ].is_file(),
        "clip07_exact_source_hash": sha256(container_path)
        == plan["source_sha256"]["source_refs/container07_exact.png"],
        "clip07_replacement_is_29_frames": CLIP07_REPLACEMENT_FRAMES == 29,
        "clip12_black_is_5_frames": CLIP12_BLACK_FRAMES == 5,
        "no_normalized_clip_below_minus38_lufs": all(
            float(record["pre_global_loudness"]["input_i"]) >= -38.0
            for record in normalized_records
        ),
    }
    verify_full_decode(final_video)
    qc = {
        "status": "passed" if all(checks.values()) else "failed",
        "created_at": utc_now(),
        "episode": EPISODE,
        "plan_path": str(PLAN_PATH),
        "plan_sha256": sha256(PLAN_PATH),
        "final_video": {
            "path": str(final_video),
            "sha256": sha256(final_video),
            "size_bytes": final_video.stat().st_size,
            "duration_seconds": duration,
            "width": video.get("width"),
            "height": video.get("height"),
            "frame_rate": str(frame_rate),
            "frame_count": frame_count,
            "video_codec": video.get("codec_name"),
            "pixel_format": video.get("pix_fmt"),
            "audio_codec": audio.get("codec_name"),
            "audio_sample_rate": int(audio.get("sample_rate") or 0),
            "audio_channels": int(audio.get("channels") or 0),
            "decoded_audio_samples": decoded_samples,
        },
        "audio_loudness": {
            "target_i_lufs": TARGET_I,
            "target_lra_lu": TARGET_LRA,
            "target_tp_dbtp": TARGET_TP,
            "first_pass_measurement": first_pass_loudness,
            "final_measurement": loudness,
            "silence_intervals_below_minus48db_over_0_6s": silence_intervals(final_video),
            "drone_enabled": drone_enabled,
            "drone_gain_db_before_dialogue_ducking": drone_gain_db if drone_enabled else None,
            "drone_sidechain_ducked_by_program_audio": drone_enabled,
        },
        "subtitles": {
            "path": str(ass_path),
            "sha256": sha256(ass_path),
            "persistent_header": plan["persistent_header"],
            "header_start_seconds": 0.0,
            "header_end_seconds": 60.0,
            "third_day_card": {"start": 10.10, "end": 11.25, "text": "第三天 / DAY 3"},
            "clock_10_54": {"start": 57.45, "end": 59.80, "text": "10:54"},
            "clock_face_mask": {
                "ass_region": {"x": 32, "y": 64, "width": 300, "height": 166},
                "basis": "locked clip12 third-panel upper-left clock composition",
                "proof_frame": str(output_paths["clock_10_54_proof"]),
            },
            "font_family": font_family,
            "font_files": [str(path) for path in font_files],
        },
        "deterministic_picture_repairs": {
            "clip01": {
                **clip01_lock,
                "repair_method": (
                    "freeze accepted normalized black-eye frame12 over frames8-11; "
                    "freeze accepted normalized full-screen frame54 over frames30-53"
                ),
                "audio": "complete normalized clip01 PCM retained by stream copy without retiming",
                "metrics": clip01_metrics,
                "proofs": {
                    "black_eye": {
                        "path": str(output_paths["clip01_eye_repair_proof"]),
                        "frame_order_left_to_right": [7, 8, 10, 11, 12],
                        "expected_content": [
                            "preserved red-to-black transition",
                            "black-eye source frame12 freeze",
                            "black-eye source frame12 freeze",
                            "black-eye source frame12 freeze",
                            "black-eye original frame12 resumes",
                        ],
                    },
                    "split_screen": {
                        "path": str(output_paths["clip01_repair_proof"]),
                        "frame_order_left_to_right": [29, 30, 41, 53, 54],
                        "expected_content": [
                            "Jian Ci",
                            "full-screen Su Wang holding photograph",
                            "full-screen Su Wang holding photograph",
                            "full-screen Su Wang holding photograph",
                            "full-screen Su Wang holding photograph; original motion resumes",
                        ],
                    },
                },
            },
            "clip07": {
                "source": str(container_path),
                "source_sha256": sha256(container_path),
                "replacement_frames": [0, 28],
                "replacement_duration_at_24fps": CLIP07_REPLACEMENT_FRAMES / FPS,
                "audio": "original normalized clip07 audio retained without timing change",
            },
            "clip12": {
                "body_frames": [0, 114],
                "black_frames": [115, 119],
                "black_duration_at_24fps": CLIP12_BLACK_FRAMES / FPS,
                "audio": "original normalized clip12 audio retained without timing change",
            },
        },
        "raw_inputs": raw_records,
        "normalized_clips": normalized_records,
        "clean_master": clean_record,
        "outputs": {key: str(path) for key, path in output_paths.items()},
        "checks": checks,
        "full_decode": "passed",
    }
    return qc


def main() -> None:
    args = parse_args()
    if args.prepare_only:
        prepare_only(args)
        return

    if args.gate_dir is None or args.remainder_dir is None:
        raise RuntimeError("--gate-dir and --remainder-dir are required unless --prepare-only is used")
    if not -60.0 <= args.drone_gain_db <= -30.0:
        raise RuntimeError("--drone-gain-db must remain between -60 and -30 dB")

    plan = load_and_validate_plan()
    validate_tools()
    font_sources, font_family, _ = resolve_font_bundle(args.fonts_dir)

    out_dir = args.out_dir.expanduser().resolve()
    work_dir = out_dir / "work"
    normalized_dir = work_dir / "normalized"
    audio_dir = work_dir / "audio"
    subtitles_dir = out_dir / "subtitles"
    audit_dir = out_dir / "audit"
    proof_dir = out_dir / "proof"
    fonts_dir = out_dir / "fonts"
    for directory in (
        normalized_dir,
        audio_dir,
        subtitles_dir,
        audit_dir,
        proof_dir,
        fonts_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    copied_fonts = copy_font_bundle(font_sources, fonts_dir)
    ass = build_ass(plan, font_family)
    validate_ass(ass, plan)
    ass_path = subtitles_dir / "S1E03_bilingual.ass"
    ass_path.write_text(ass, encoding="utf-8")

    raw_clips = discover_raw_clips(args.gate_dir, args.remainder_dir)
    raw_records = []
    for clip in plan["clips"]:
        clip_id = clip["id"]
        required_audio_seconds = max(float(line["end"]) for line in clip["dialogue"])
        raw_records.append(
            validate_raw_clip(
                clip_id,
                raw_clips[clip_id],
                required_audio_seconds=required_audio_seconds,
            )
        )
    actual_clip01_hash = sha256(raw_clips["01"])
    if actual_clip01_hash != CLIP01_ACCEPTED_RAW_SHA256:
        raise RuntimeError(
            "Clip01 is not the accepted gate covered by the plan-independent "
            f"split-screen repair lock: expected {CLIP01_ACCEPTED_RAW_SHA256}, "
            f"got {actual_clip01_hash}"
        )
    print("All twelve raw clips contain picture, non-silent audio and valid duration.")

    container_path = safe_source_path(
        plan["clips"][6]["postprocess"]["replace_first_shot_with"]
    )
    effective_clips: list[Path] = []
    normalized_records: list[dict[str, Any]] = []
    clip01_effective: Path | None = None
    for clip_id in CLIP_IDS:
        base = normalized_dir / f"S1E03_clip_{clip_id}_norm_base.mkv"
        normalize_clip(raw_clips[clip_id], base)
        effective = base
        if clip_id == "01":
            effective = normalized_dir / "S1E03_clip_01_norm_repaired.mkv"
            patch_clip01_accepted_gate(base, effective)
            clip01_effective = effective
        elif clip_id == "07":
            effective = normalized_dir / "S1E03_clip_07_norm_container07.mkv"
            patch_clip07(base, container_path, effective)
        elif clip_id == "12":
            effective = normalized_dir / "S1E03_clip_12_norm_black_end.mkv"
            patch_clip12_black(base, effective)
        summary = normalized_summary(effective, FRAMES_PER_CLIP, SAMPLES_PER_CLIP)
        if clip_id == "01":
            repair_metrics = clip01_repair_metrics(effective, base)
            if not all(repair_metrics["checks"].values()):
                failed = [
                    name for name, passed in repair_metrics["checks"].items() if not passed
                ]
                raise RuntimeError(
                    f"Clip01 deterministic split-screen repair failed: {', '.join(failed)}"
                )
            summary["clip01_repair_metrics"] = repair_metrics
        summary["pre_global_loudness"] = analyze_loudness(effective)
        summary["clip_id"] = clip_id
        summary["deterministic_patch"] = (
            "replace_red_eye_frames_8_11_with_black_eye_frame12_and_"
            "split_screen_frames_30_53_with_fullscreen_frame54"
            if clip_id == "01"
            else "container07_first_29_frames"
            if clip_id == "07"
            else "black_frames_115_to_119"
            if clip_id == "12"
            else None
        )
        normalized_records.append(summary)
        effective_clips.append(effective)

    if clip01_effective is None:
        raise RuntimeError("Clip01 deterministic repair was not applied")

    clean_master = work_dir / "S1E03_clean_master_60s.mkv"
    concat_list = work_dir / "concat_normalized.txt"
    concatenate_clips(effective_clips, concat_list, clean_master)
    clean_record = normalized_summary(clean_master, TOTAL_FRAMES, TOTAL_SAMPLES)

    drone_enabled = not args.no_drone
    drone_path: Path | None = None
    if drone_enabled:
        drone_path = audio_dir / "S1E03_original_suspense_drone.wav"
        synthesize_drone(drone_path)
        if decoded_audio_samples(drone_path) != TOTAL_SAMPLES:
            raise RuntimeError("Program-synthesized drone is not exactly 60 seconds")

    mixed_audio = audio_dir / "S1E03_program_mix_pre_loudnorm.wav"
    build_mixed_program_audio(
        clean_master,
        mixed_audio,
        drone_path=drone_path,
        drone_gain_db=args.drone_gain_db,
    )
    if decoded_audio_samples(mixed_audio) != TOTAL_SAMPLES:
        raise RuntimeError("Programme mix is not exactly 60 seconds")

    final_audio = audio_dir / "S1E03_program_mix_loudnorm.wav"
    first_pass_loudness, _ = normalized_program_audio(mixed_audio, final_audio)

    final_video = out_dir / "S1E03_醒不过来的人_FINAL_60s.mp4"
    render_final(
        clean_master,
        final_audio,
        ass_path,
        fonts_dir,
        final_video,
        plan["persistent_header"],
    )

    contact_sheet = proof_dir / "S1E03_contact_sheet_12x5s.jpg"
    render_contact_sheet(final_video, contact_sheet)
    clip01_eye_repair_proof = (
        proof_dir / "S1E03_clip01_eye_repair_frames_7_8_10_11_12.jpg"
    )
    clip01_repair_proof = proof_dir / "S1E03_clip01_repair_frames_29_30_41_53_54.jpg"
    container_proof = proof_dir / "S1E03_clip07_container07_proof.jpg"
    clock_proof = proof_dir / "S1E03_clip12_10-54_proof.jpg"
    render_clip01_eye_repair_proof(clip01_effective, clip01_eye_repair_proof)
    render_clip01_repair_proof(clip01_effective, clip01_repair_proof)
    render_proof_frame(final_video, 30.50, container_proof)
    render_proof_frame(final_video, 58.00, clock_proof)

    qc_path = audit_dir / "S1E03_qc.json"
    outputs = {
        "final_mp4": final_video,
        "ass": ass_path,
        "qc_json": qc_path,
        "contact_sheet": contact_sheet,
        "clip01_eye_repair_proof": clip01_eye_repair_proof,
        "clip01_repair_proof": clip01_repair_proof,
        "container07_proof": container_proof,
        "clock_10_54_proof": clock_proof,
        "clean_master": clean_master,
        "normalized_audio": final_audio,
    }
    qc = final_qc(
        final_video,
        plan=plan,
        ass_path=ass_path,
        font_family=font_family,
        font_files=copied_fonts,
        raw_records=raw_records,
        normalized_records=normalized_records,
        clean_record=clean_record,
        first_pass_loudness=first_pass_loudness,
        drone_enabled=drone_enabled,
        drone_gain_db=args.drone_gain_db,
        container_path=container_path,
        output_paths=outputs,
    )
    write_json(qc_path, qc)
    if qc["status"] != "passed":
        failed = [name for name, passed in qc["checks"].items() if not passed]
        raise RuntimeError(f"Final S1E03 QC failed: {', '.join(failed)}; see {qc_path}")

    print(
        json.dumps(
            {
                "status": "completed",
                "final_mp4": str(final_video),
                "ass": str(ass_path),
                "qc_json": str(qc_path),
                "contact_sheet": str(contact_sheet),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
