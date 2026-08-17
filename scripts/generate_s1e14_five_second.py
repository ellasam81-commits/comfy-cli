#!/usr/bin/env python3
"""Generate the locked S01E14 clips exactly once each, without retrying."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import generate_s1e10_12_five_second as base


ROOT = Path.cwd()
SOURCE_PLAN = ROOT / "references" / "s1e14" / "production_plan.json"
BOARDS = ROOT / "references" / "s1e14" / "storyboard_refs"

VOICE_LOCK = {
    "剑刺": "low, restrained adult Mandarin male voice",
    "林浅": "steady mid-low adult Mandarin female investigator voice",
    "周峤": "precise, measured young adult Mandarin male voice",
    "许未": "clear, firm adult Mandarin female analyst voice",
    "韩彻": "calm, authoritative mature Mandarin male voice",
}

IDENTITIES = {"jian_ci", "lin_qian", "zhou_qiao", "xu_wei", "han_che"}
DISPLAY_NAMES = {
    "jian_ci": "Jian Ci",
    "lin_qian": "Lin Qian",
    "zhou_qiao": "Zhou Qiao",
    "xu_wei": "Xu Wei",
    "han_che": "Han Che",
}

# This runtime adapter is deliberately separate from the uploaded production plan.
# It preserves the approved dialogue while supplying the metadata the shared
# one-shot runner needs.  Visual wording below is intentionally platform-safe.
CLIPS: list[dict[str, Any]] = [
    {
        "id": "01", "characters": ["lin_qian", "xu_wei"], "speaker": "林浅",
        "zh": "剑刺，准备销毁的那份样本，去向断了。", "en": "Jian Ci, the sample marked for disposal has lost its destination.", "start": 0.28, "end": 3.55,
        "shots": [
            "0.00-1.66 Lin Qian in a navy field uniform studies a shut brushed-steel archive cabinet in a blue-black corridor; one rectangular recess is empty.",
            "1.66-3.33 Xu Wei in an olive coverall places three separately sealed blank square paper packets on a steel tray.",
            "3.33-5.00 Slow raking light reveals the same diagonal fold on all three packets; controlled concern.",
        ],
    },
    {
        "id": "02", "characters": ["xu_wei", "lin_qian"], "speaker": "林浅",
        "zh": "许未，这不是自己贴的。", "en": "Xu Wei, this was not applied by the person themselves.", "start": 0.30, "end": 3.55,
        "shots": [
            "0.00-1.66 Xu Wei uses a flat black archival tool to turn three sealed blank square packets in a medium tabletop shot.",
            "1.66-3.33 A narrow sweep of light reveals matching edge pressure.",
            "3.33-5.00 Lin Qian records the arrangement with an unbranded compact camera whose display stays out of frame, then returns each packet to a separate blank tray recess.",
        ],
    },
    {
        "id": "03", "characters": ["xu_wei", "lin_qian"], "speaker": "许未",
        "zh": "林浅，间隔像排好的班。", "en": "Lin Qian, the intervals look scheduled.", "start": 0.30, "end": 3.65,
        "shots": [
            "0.00-1.66 Four opaque cream-paper sleeves sit evenly spaced on a steel tray.",
            "1.66-3.33 Overhead cold light picks out an identical rhythm of tiny corner folds.",
            "3.33-5.00 Lin Qian slides the final sealed sleeve into a blank recess, completing an unnervingly orderly pattern.",
        ],
    },
    {
        "id": "04", "characters": ["zhou_qiao", "lin_qian"], "speaker": "周峤",
        "zh": "林浅，三站连成一条夜线。", "en": "Lin Qian, three stops form one night route.", "start": 0.30, "end": 3.70,
        "shots": [
            "0.00-1.66 Zhou Qiao, the only person with silver-rim glasses and a hearing device, leans over a raised physical city relief with no electronics.",
            "1.66-3.33 Three tiny anonymous blue beacon beads light in sequence.",
            "3.33-5.00 Their narrow glow ends at a bare rain-dark transport junction; Zhou looks up.",
        ],
    },
    {
        "id": "05", "characters": ["lin_qian"], "speaker": "林浅",
        "zh": "周峤，这里不像诊所。", "en": "Zhou Qiao, this does not look like a clinic.", "start": 0.30, "end": 3.65,
        "shots": [
            "0.00-1.66 Lin Qian enters a vacant temporary service room under cold light: plain white fabric dividers and aligned low stools.",
            "1.66-3.33 She opens a shallow chest containing blank colour tabs, closed paper rolls and empty foldover sleeves.",
            "3.33-5.00 A wide pullback shows empty chairs facing a locked unmarked rear door.",
        ],
    },
    {
        "id": "06", "characters": ["xu_wei"], "speaker": "许未",
        "zh": "林浅，合格是后来补的。", "en": "Lin Qian, the passing result was added later.", "start": 0.30, "end": 3.85,
        "shots": [
            "0.00-1.66 Xu Wei holds a sealed unprinted cream card beneath a desk lamp, black gloves visible.",
            "1.66-3.33 Oblique light shows two shallow blind-embossed layers with no glyphs.",
            "3.33-5.00 She places the card alone in a transparent unmarked sleeve and closes it, calm and certain.",
        ],
    },
    {
        "id": "07", "characters": ["lin_qian", "jian_ci"], "speaker": "林浅",
        "zh": "剑刺，签过字也不代表愿意。", "en": "Jian Ci, a signature does not mean consent.", "start": 0.30, "end": 3.70,
        "shots": [
            "0.00-1.66 Lin Qian separates a blank agreement envelope and small transit tokens on two distinct evidence mats.",
            "1.66-3.33 Jian Ci in a white coat remains at the clean boundary, fully composed and empty-handed.",
            "3.33-5.00 Lin Qian closes an unmarked sleeve and keeps the evidence groups apart.",
        ],
    },
    {
        "id": "08", "characters": ["zhou_qiao", "jian_ci"], "speaker": "周峤",
        "zh": "剑刺，今晚还有一趟车。", "en": "Jian Ci, there is one more vehicle run tonight.", "start": 0.30, "end": 3.70,
        "shots": [
            "0.00-1.66 Zhou Qiao places unmarked reservation tokens beside a physical route model.",
            "1.66-3.33 Only one blue route bead remains lit on the blank model.",
            "3.33-5.00 Jian Ci stays softly out of focus at the doorway while Zhou turns toward him.",
        ],
    },
    {
        "id": "09", "characters": ["jian_ci", "lin_qian"], "speaker": "剑刺",
        "zh": "林浅，冷柜交给你。", "en": "Lin Qian, the cold cabinet is yours.", "start": 0.32, "end": 3.60,
        "shots": [
            "0.00-1.66 Jian Ci stops a full step from a closed brushed-steel cold-storage cabinet in a dark corridor.",
            "1.66-3.33 A restrained red emergency-indicator reflection passes across the steel cabinet surface, grounded and brief.",
            "3.33-5.00 He withdraws as Lin Qian watches from the clean boundary; neither touches the cabinet.",
        ],
    },
    {
        "id": "10", "characters": ["lin_qian"], "speaker": "周峤",
        "zh": "林浅，它先换人再换地。", "en": "Lin Qian, it changes people before it changes places.", "start": 0.32, "end": 3.70,
        "shots": [
            "0.00-1.66 An unmarked grey transfer van crosses a rainy warehouse district.",
            "1.66-3.33 Lin Qian observes through a convex mirror, her face reflected in cool light; no screen is visible.",
            "3.33-5.00 A diagonal blank sealing strip flashes on the rear door as the van turns away.",
        ],
    },
    {
        "id": "11", "characters": ["han_che", "lin_qian", "jian_ci", "zhou_qiao"], "speaker": "韩彻",
        "zh": "林浅，先救人，再取证。", "en": "Lin Qian, save people first, then secure the evidence.", "start": 0.30, "end": 3.75,
        "shots": [
            "0.00-1.66 Han Che divides two action paths on an unmarked physical model in the command room.",
            "1.66-3.33 Lin Qian takes an empty sealed evidence case from the far edge of the table.",
            "3.33-5.00 Jian Ci and Zhou Qiao hold position without equipment in their hands; Han Che leads with calm urgency.",
        ],
    },
    {
        "id": "12", "characters": ["lin_qian", "jian_ci"], "speaker": "周峤",
        "zh": "林浅，车进旧仓库了。", "en": "Lin Qian, the van has entered the old warehouse.", "start": 0.30, "end": 3.75,
        "shots": [
            "0.00-1.66 An unmarked transfer van enters an old warehouse through rain.",
            "1.66-3.33 Only empty stools, white curtains and an opaque closed inner door are visible inside.",
            "3.33-5.00 Lin Qian gives a silent stop signal while Jian Ci watches the entrance from beside her.",
        ],
    },
]

MODEL_FORBIDDEN = (
    "blood", "needle", "puncture", "wound", "injury", "syringe", "plasma", "medical",
    "clinical", "skin", "neck", "arm", "body close-up", "gore", "vampire", "bite",
)


def source_plan() -> dict[str, Any]:
    return json.loads(SOURCE_PLAN.read_text(encoding="utf-8"))


def image_1280x720(path: Path) -> None:
    base.image_ok(path)
    from PIL import Image

    with Image.open(path) as image:
        if image.format != "JPEG" or image.size != (1280, 720):
            raise RuntimeError(f"S01E14 storyboard must be a 1280x720 JPEG: {path}")


def load_plan() -> dict[str, Any]:
    raw = source_plan()
    target = raw.get("runtime_target", {})
    expected = {
        "aspect_ratio": "16:9", "resolution": "480p", "duration_seconds": 60,
        "clips": 12, "seconds_per_clip": 5, "shots_per_clip": 3,
        "generate_audio": True, "automatic_retries": 0,
    }
    if raw.get("series") != "吸血法医·剑刺" or raw.get("season") != 1 or raw.get("episode") != 14:
        raise RuntimeError("S01E14 source plan identity is not locked")
    for key, value in expected.items():
        if target.get(key) != value:
            raise RuntimeError(f"S01E14 runtime lock failed: {key}")
    source_clips = raw.get("clips")
    if not isinstance(source_clips, list) or [item.get("id") for item in source_clips] != list(range(1, 13)):
        raise RuntimeError("S01E14 source plan must contain clips 01 through 12 in order")
    if len(CLIPS) != 12 or [clip["id"] for clip in CLIPS] != [f"{item:02d}" for item in range(1, 13)]:
        raise RuntimeError("S01E14 runtime adapter must retain every locked clip")
    for source, clip in zip(source_clips, CLIPS):
        board = BOARDS / f"S01E14_{clip['id']}_board.jpg"
        if source.get("board") != f"storyboard_refs/S01E14_{clip['id']}_board.jpg":
            raise RuntimeError(f"S01E14 storyboard path changed for clip {clip['id']}")
        image_1280x720(board)
        if source.get("audio") != f"{clip['speaker']}：{clip['zh']}":
            raise RuntimeError(f"S01E14 dialogue changed for clip {clip['id']}")
        if len(source.get("shots", [])) != 3 or len(clip["shots"]) != 3:
            raise RuntimeError(f"S01E14 clip {clip['id']} must have exactly three locked shots")
        if clip["speaker"] not in VOICE_LOCK or not 0 <= clip["start"] < clip["end"] <= 5:
            raise RuntimeError(f"S01E14 voice cue is invalid for clip {clip['id']}")
        if any(identity not in IDENTITIES for identity in clip["characters"]):
            raise RuntimeError(f"S01E14 identity lock is invalid for clip {clip['id']}")
    return {
        "series_title_zh": raw["series"], "maker_zh": raw["author"],
        "model": "seedance-2.0-mini", "resolution": "480p", "aspect_ratio": "16:9",
        "duration_seconds_per_clip": 5, "clips_per_episode": 12, "shots_per_clip": 3,
        "generate_audio": True, "automatic_retries": 0,
        "character_lock": "locked source identities", "visual_lock": "locked original noir investigation animation",
        "case_continuity": "the evidence trail continues safely", "global_negative": "not passed to the provider",
        "episodes": [{
            "episode": "S01E14", "title_zh": raw["title_zh"], "title_en": "Healed Evidence",
            "case_zh": raw["case_zh"], "case_en": "The Drained",
            "continuity": "Begins after the accepted S01E13 final continuity frame.",
            "clips": [{
                "id": clip["id"], "characters": clip["characters"], "scene": "safe locked investigation scene",
                "shots": clip["shots"],
                "dialogue": [{"speaker": clip["speaker"], "zh": clip["zh"], "en": clip["en"], "start": clip["start"], "end": clip["end"]}],
            } for clip in CLIPS],
        }],
    }


def storyboard_board(episode: str, clip_id: str, runtime: Path) -> Path:
    if episode != "S01E14":
        raise RuntimeError(f"Storyboard authority is only locked for S01E14, not {episode}")
    board = BOARDS / f"S01E14_{clip_id}_board.jpg"
    image_1280x720(board)
    return board


def build_prompt(plan: dict[str, Any], episode: dict[str, Any], clip: dict[str, Any], reference_names: list[str], has_board: bool) -> str:
    if not has_board:
        raise RuntimeError(f"Missing locked storyboard for S01E14 clip {clip['id']}")
    cue = clip["dialogue"][0]
    names = ", ".join(DISPLAY_NAMES[name] for name in reference_names)
    shots = "\n".join(f"{index + 1}. {value}" for index, value in enumerate(clip["shots"]))
    prompt = f"""ORIGINAL 2D cinematic investigation noir, blue-black and steel-grey palette. Render one clean five-second 16:9 full-screen moving sequence with exactly three shots in the stated order. References govern only the locked faces, wardrobe, palette, geography and blocking; render a scene, never a board. Reference order: accepted style and lighting frames, fixed identity images for {names}, this clip's locked storyboard, then the previous continuity frame. Show exactly the named locked cast, each once; all are fully clothed, and prop handling uses black gloves. Jian Ci never wears glasses. Only Zhou Qiao wears silver-rim glasses and a hearing device. Every prop is blank and unmarked: no letters, digits, labels, symbols, barcodes or interface graphics. No screens, phones, monitors, dashboards, vehicle plates, signs, captions, titles, logos or watermark. No live action, 3D, chibi, comedy or weapons. Do not infer any action beyond the three shots.

RENDER EXACTLY THREE FULL-SCREEN CINEMATIC SHOTS:
{shots}

AUDIO ONLY, never onscreen. Mandarin only; one speaker with a {VOICE_LOCK[cue['speaker']]}, from {cue['start']:.2f} to {cue['end']:.2f}. Speak exactly: “{cue['zh']}”. Quiet room tone and a restrained low industrial pulse; no other speech, singing, English or narration."""
    lowered = prompt.lower()
    found = [word for word in MODEL_FORBIDDEN if word in lowered]
    if found:
        raise RuntimeError(f"Unsafe vocabulary leaked into provider prompt for clip {clip['id']}: {found}")
    return prompt


def verify_complete() -> None:
    plan = load_plan()
    output = ROOT / os.environ.get("GENERATION_OUTPUT_DIR", "output/s1e14-all")
    manifest_path = output / "generation_manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("Missing S01E14 generation manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "completed" or manifest.get("request_count") != 12 or manifest.get("automatic_retries") != 0:
        raise RuntimeError("S01E14 manifest does not prove one completed request per clip")
    records = manifest.get("clips")
    if not isinstance(records, list) or [item.get("clip_id") for item in records] != [clip["id"] for clip in plan["episodes"][0]["clips"]]:
        raise RuntimeError("S01E14 manifest clip order is incomplete")
    for clip in plan["episodes"][0]["clips"]:
        record = next(item for item in records if item.get("clip_id") == clip["id"])
        video = output / "S01E14" / "raw" / f"S01E14_clip_{clip['id']}_raw.mp4"
        qc = record.get("technical_qc", {})
        if record.get("request_count") != 1 or record.get("automatic_retries") != 0 or not video.is_file():
            raise RuntimeError(f"S01E14 clip {clip['id']} does not prove a single completed request")
        dimensions = (int(qc.get("width") or 0), int(qc.get("height") or 0))
        if dimensions not in {(854, 480), (864, 496)} or not 4.3 <= float(qc.get("duration", 0)) <= 5.8:
            raise RuntimeError(f"S01E14 clip {clip['id']} does not meet 480p five-second QC")
        if not qc.get("audio_codec") or len(re.findall(r"[\u3400-\u9fff]", str(qc.get("asr", "")))) < 2:
            raise RuntimeError(f"S01E14 clip {clip['id']} does not meet Mandarin-audio QC")
    print("S01E14 completion verification passed: 12 distinct five-second 480p clips, audio present, no retry path.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--verify-complete", action="store_true")
    parser.add_argument("--episode", choices=["S01E14"], default="S01E14")
    parser.add_argument("--previous-frame", type=Path)
    args = parser.parse_args()
    if args.preflight and args.verify_complete:
        raise RuntimeError("Choose either --preflight or --verify-complete")
    base.PLAN_PATH = SOURCE_PLAN
    base.OUT = ROOT / os.environ.get("GENERATION_OUTPUT_DIR", "output/s1e14-all")
    base.load_plan = load_plan
    base.storyboard_board = storyboard_board
    base.build_prompt = build_prompt
    try:
        if args.preflight:
            if args.previous_frame is not None:
                raise RuntimeError("--previous-frame is not needed during preflight")
            base.preflight(args.episode)
        elif args.verify_complete:
            verify_complete()
        else:
            if args.previous_frame is None:
                raise RuntimeError("S01E14 requires the accepted S01E13 final continuity frame")
            base.generate(args.episode, None, args.previous_frame)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
