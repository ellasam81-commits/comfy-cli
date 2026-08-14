#!/usr/bin/env python3
"""Generate locked S01E13 clips exactly once each, with no retry path."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import generate_s1e10_12_five_second as base


ROOT = Path.cwd()
PLAN_PATH = ROOT / "references" / "s1e13" / "production_plan.json"
BOARDS = ROOT / "references" / "s1e13_storyboard_refs_compressed"

VOICE_LOCK = {
    "剑刺": "low, restrained adult Mandarin male voice",
    "林浅": "steady mid-low adult Mandarin female investigator voice",
    "周峤": "precise measured young adult Mandarin male voice",
    "许未": "clear, firm adult Mandarin female forensic voice",
    "韩彻": "calm authoritative mature Mandarin male voice",
    "旁白": "quiet, grounded Mandarin narrator voice",
}
IDENTITY_NAMES = {"jian_ci", "lin_qian", "zhou_qiao", "xu_wei", "han_che"}


def load_plan() -> dict[str, Any]:
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    lock = {
        "model": "seedance-2.0-mini",
        "resolution": "480p",
        "aspect_ratio": "16:9",
        "duration_seconds_per_clip": 5,
        "clips_per_episode": 12,
        "shots_per_clip": 3,
        "generate_audio": True,
        "automatic_retries": 0,
    }
    for key, expected in lock.items():
        if plan.get(key) != expected:
            raise RuntimeError(f"S01E13 production lock failed: {key}")
    episodes = plan.get("episodes")
    if not isinstance(episodes, list) or [item.get("episode") for item in episodes] != ["S01E13"]:
        raise RuntimeError("S01E13 plan must contain only S01E13")
    clips = episodes[0].get("clips")
    if not isinstance(clips, list) or [item.get("id") for item in clips] != [f"{value:02d}" for value in range(1, 13)]:
        raise RuntimeError("S01E13 must contain clips 01 through 12 in order")
    for clip in clips:
        if len(clip.get("shots", [])) != 3 or len(clip.get("dialogue", [])) != 1:
            raise RuntimeError(f"S01E13 clip {clip.get('id')} must have exactly three shots and one approved voice cue")
        cue = clip["dialogue"][0]
        if cue.get("speaker") not in VOICE_LOCK or not 0 <= float(cue.get("start", -1)) < float(cue.get("end", -1)) <= 5:
            raise RuntimeError(f"Invalid S01E13 voice cue in clip {clip['id']}")
        if any(name not in IDENTITY_NAMES for name in clip.get("characters", [])):
            raise RuntimeError(f"Unknown or unlocked S01E13 identity in clip {clip['id']}")
        board = BOARDS / f"S01E13_{clip['id']}_board.jpg"
        base.image_ok(board)
    for required in (base.JIAN, base.CHART, base.E09_PANEL_1, base.E09_PANEL_12):
        if not required.is_file():
            raise RuntimeError(f"Required locked source is missing: {required}")
    base.image_ok(base.JIAN)
    base.image_ok(base.CHART)
    base.locked_b64_image_ok(base.E09_PANEL_1)
    base.locked_b64_image_ok(base.E09_PANEL_12)
    return plan


def storyboard_board(episode: str, clip_id: str, runtime: Path) -> Path:
    if episode != "S01E13":
        raise RuntimeError(f"Storyboard authority is only locked for S01E13, not {episode}")
    board = BOARDS / f"S01E13_{clip_id}_board.jpg"
    base.image_ok(board)
    return board


def build_prompt(plan: dict[str, Any], episode: dict[str, Any], clip: dict[str, Any], reference_names: list[str], has_board: bool) -> str:
    if not has_board:
        raise RuntimeError(f"S01E13 clip {clip['id']} is missing its locked storyboard")
    shots = "\n".join(f"{index + 1}. {item}" for index, item in enumerate(clip["shots"]))
    cue = clip["dialogue"][0]
    names = ", ".join(reference_names)
    return f"""ORIGINAL SERIES PRODUCTION LOCK. Render exactly one clean five-second 16:9 animated clip for 《吸血法医·剑刺》{episode['episode']}《{episode['title_zh']}》, case《{episode['case_zh']}》, clip {clip['id']} of 12. Original dark forensic manga-noir only; never imitate a named artist, studio, franchise or copyrighted character.

REFERENCE ORDER IS LOCKED. References 1 and 2 are accepted visual-style and cinematic-lighting authorities. The following images are fixed identity authorities for {names}. The next image is the locked storyboard authority for this exact clip: preserve its cast, wardrobe, props, location, framing and three-shot order, but render a full-screen moving scene rather than a board. The final image is the previous accepted continuity frame; control only opening light, screen direction and scene geography. Never render a board, grid, panel, split-screen, title, subtitle, logo, watermark, readable UI, readable report or generated text.

RENDER EXACTLY THREE FULL-SCREEN CINEMATIC SHOTS IN THE GIVEN TIMING:
{shots}

CHARACTER LOCK. {plan['character_lock']}
CRITICAL: Jian Ci never wears glasses. Only Zhou Qiao wears silver-rim glasses and a hearing device. Preserve faces, hair, age, clothing, body scale, props and screen direction. Never duplicate a character, introduce an extra character, change wardrobe or give anyone a weapon.

VISUAL / STORY LOCK. {plan['visual_lock']} {plan['case_continuity']} {episode['continuity']} Current clip scene: {clip['scene']}. Each 1.66-second shot has one motivated action and one dominant emotion. Evidence is always gloved, photographed, sealed and separate. Jian Ci's blood hunger is a private danger only: it never solves this case and he never harms any person.

MANDARIN AUDIO LOCK. Generate synchronized clear native Mandarin audio with restrained room tone and a subtle low industrial suspense pulse. Use this fixed voice quality: {VOICE_LOCK[cue['speaker']]}. Speak only this exact Chinese line during {float(cue['start']):.2f}-{float(cue['end']):.2f}, with no overlap, English, singing, invented dialogue or silence: {cue['speaker']}：“{cue['zh']}”
Do not generate visible subtitles. The permanent title header and clear Chinese/English subtitles are burned in only after technical and Mandarin-speech QC.

STRICT NEGATIVE: {plan['global_negative']}"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--episode", choices=["S01E13"], default="S01E13")
    parser.add_argument("--previous-frame", type=Path)
    args = parser.parse_args()
    base.PLAN_PATH = PLAN_PATH
    base.OUT = ROOT / os.environ.get("GENERATION_OUTPUT_DIR", "output/s1e13-all")
    base.load_plan = load_plan
    base.storyboard_board = storyboard_board
    base.build_prompt = build_prompt
    try:
        if args.preflight:
            if args.previous_frame is not None:
                raise RuntimeError("--previous-frame is not needed during preflight")
            base.preflight(args.episode)
        else:
            if args.previous_frame is None:
                raise RuntimeError("S01E13 requires the accepted S01E12 final continuity frame")
            base.generate(args.episode, None, args.previous_frame)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
