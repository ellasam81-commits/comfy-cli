#!/usr/bin/env python3
"""Generate only the new S01E15 visuals once each; dialogue is added later."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import generate_s1e10_12_five_second as base


ROOT = Path.cwd()
PLAN_PATH = ROOT / "references" / "s1e13-s1e15-remaster" / "production_plan.json"
BOARDS = ROOT / "references" / "s1e15" / "storyboard_refs"
OUT = ROOT / os.environ.get("GENERATION_OUTPUT_DIR", "output/s1e13-s1e15-remaster")

DISPLAY_NAMES = {
    "jian_ci": "Jian Ci", "lin_qian": "Lin Qian", "xu_wei": "Xu Wei",
    "zhou_qiao": "Zhou Qiao", "han_che": "Han Che", "luo_chuan": "Luo Chuan",
}
KNOWN_IDENTITIES = {"jian_ci", "lin_qian", "xu_wei", "zhou_qiao", "han_che"}
MODEL_FORBIDDEN = {
    "blood", "needle", "puncture", "wound", "injury", "syringe", "plasma", "medical",
    "clinical", "skin", "neck", "arm", "body close-up", "gore", "vampire", "bite",
    "subtitle", "caption", "report", "readable", "text", "ui",
}


def raw_plan() -> dict[str, Any]:
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))


def board(clip_id: str) -> Path:
    path = BOARDS / f"S01E15_{clip_id}_board.jpg"
    base.image_ok(path)
    from PIL import Image
    with Image.open(path) as image:
        if image.format != "JPEG" or image.size != (1280, 720):
            raise RuntimeError(f"S01E15 board must be a 1280x720 JPEG: {path}")
    return path


def load_plan() -> dict[str, Any]:
    raw = raw_plan()
    runtime = raw.get("runtime", {})
    expected = {
        "resolution": "480p", "aspect_ratio": "16:9", "seconds_per_clip": 5,
        "clips_per_episode": 12, "video_requests": 12, "tts_requests": 12,
        "automatic_retries": 0,
    }
    for key, value in expected.items():
        if runtime.get(key) != value:
            raise RuntimeError(f"Remaster runtime lock failed: {key}")
    episode = next((item for item in raw.get("episodes", []) if item.get("code") == "S01E15"), None)
    if not episode or episode.get("source") != "new_s01e15_video_generation":
        raise RuntimeError("S01E15 remaster source lock is invalid")
    clips = episode.get("clips")
    expected_ids = [f"{value:02d}" for value in range(1, 13)]
    if not isinstance(clips, list) or [item.get("id") for item in clips] != expected_ids:
        raise RuntimeError("S01E15 must retain clips 01 through 12 in order")
    adapted: list[dict[str, Any]] = []
    for clip in clips:
        board(clip["id"])
        if not isinstance(clip.get("visual"), str) or not isinstance(clip.get("characters"), list):
            raise RuntimeError(f"S01E15 clip {clip['id']} visual lock is invalid")
        if clip.get("speaker") not in raw.get("voice_lock", {}):
            raise RuntimeError(f"S01E15 clip {clip['id']} speaker is invalid")
        if not 0.0 <= float(clip.get("start", -1)) < float(clip.get("end", 6)) <= 5.0:
            raise RuntimeError(f"S01E15 clip {clip['id']} dialogue timing is invalid")
        adapted.append({
            "id": clip["id"], "characters": clip["characters"], "scene": clip["visual"],
            "shots": [clip["visual"]],
            "dialogue": [{"speaker": clip["speaker"], "zh": clip["zh"], "en": clip["en"], "start": clip["start"], "end": clip["end"]}],
        })
    return {
        "series_title_zh": raw["series"], "maker_zh": raw["author"],
        "model": "seedance-2.0-mini", "resolution": "480p", "aspect_ratio": "16:9",
        "duration_seconds_per_clip": 5, "clips_per_episode": 12, "shots_per_clip": 1,
        "generate_audio": True, "automatic_retries": 0,
        "episodes": [{
            "episode": "S01E15", "title_zh": episode["title_zh"], "title_en": episode["title_en"],
            "case_zh": raw["case"]["title_zh"], "case_en": raw["case"]["title_en"],
            "continuity": "Begins at the accepted old-warehouse ending of S01E14.", "clips": adapted,
        }],
    }


def storyboard_board(episode: str, clip_id: str, _runtime: Path) -> Path:
    if episode != "S01E15":
        raise RuntimeError(f"Unexpected episode for S01E15 visual generation: {episode}")
    return board(clip_id)


def build_prompt(_plan: dict[str, Any], _episode: dict[str, Any], clip: dict[str, Any], reference_names: list[str], has_board: bool) -> str:
    if not has_board:
        raise RuntimeError(f"Locked S01E15 storyboard missing for clip {clip['id']}")
    names = ", ".join(DISPLAY_NAMES[name] for name in reference_names) or "the stated cast"
    prompt = f"""Original 2D cinematic investigation noir in blue-black and steel-grey. Create one clean five-second full-screen moving 16:9 sequence, never a board, grid or split screen. References control only established faces, wardrobe, colour, geography and blocking for {names}. This clip's board controls the composition; render an animated scene, not the board. Show exactly the stated cast once, fully clothed, with black gloves when handling a prop. Jian Ci never wears glasses. Only Zhou Qiao wears silver-rim glasses and a hearing device. Every prop is blank, unmarked and opaque. No lettering, digits, labels, symbols, screen graphics, signs, logos or watermarks.

ACTION IN ORDER:
{clip['scene']}

Use quiet room tone and a restrained low industrial pulse only. Do not create spoken words. No live action, three-dimensional rendering, chibi, comedy, fighting or weapons. Do not add characters, actions, props or information beyond the stated action."""
    lowered = prompt.lower()
    found = sorted(word for word in MODEL_FORBIDDEN if re.search(rf"\b{re.escape(word)}\b", lowered))
    if found:
        raise RuntimeError(f"Unsafe or text-seeking vocabulary leaked into provider prompt for clip {clip['id']}: {found}")
    return prompt


def verify(video: Path, clip: dict[str, Any], _model: Any, folders: dict[str, Path]) -> dict[str, Any]:
    """Visual source needs technical sound only; exact spoken audio is added in post."""
    probe = json.loads(base.shell(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video)]).stdout)
    streams = probe.get("streams", [])
    visual = [item for item in streams if item.get("codec_type") == "video"]
    audio = [item for item in streams if item.get("codec_type") == "audio"]
    duration = float(probe.get("format", {}).get("duration") or 0)
    if video.stat().st_size < 200_000 or not visual or not audio or not 4.3 <= duration <= 5.8:
        raise RuntimeError(f"S01E15 clip {clip['id']} failed five-second technical QC")
    base.dump(folders["audit"] / f"clip_{clip['id']}_ffprobe.json", probe)
    return {
        "duration": duration, "width": visual[0].get("width"), "height": visual[0].get("height"),
        "audio_codec": audio[0].get("codec_name"), "speech_is_postproduction": True,
    }


def verify_complete() -> None:
    plan = load_plan()
    manifest_path = OUT / "generation_manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("Missing S01E15 generation manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    clips = manifest.get("clips", [])
    if manifest.get("status") != "completed" or manifest.get("request_count") != 12 or manifest.get("automatic_retries") != 0:
        raise RuntimeError("S01E15 does not prove one completed video request per clip")
    if [item.get("clip_id") for item in clips] != [item["id"] for item in plan["episodes"][0]["clips"]]:
        raise RuntimeError("S01E15 manifest clip sequence is incomplete")
    for clip in clips:
        if clip.get("request_count") != 1 or clip.get("automatic_retries") != 0 or clip.get("status") != "completed":
            raise RuntimeError(f"S01E15 clip {clip.get('clip_id')} lacks single-request proof")
    print("S01E15 visual completion verified: twelve distinct five-second clips, no retry path.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--verify-complete", action="store_true")
    parser.add_argument("--previous-frame", type=Path)
    args = parser.parse_args()
    if args.preflight and args.verify_complete:
        raise RuntimeError("Choose one validation action")
    base.PLAN_PATH = PLAN_PATH
    base.OUT = OUT
    base.load_plan = load_plan
    base.storyboard_board = storyboard_board
    base.build_prompt = build_prompt
    base.verify = verify
    try:
        if args.preflight:
            load_plan()
            print("S01E15 preflight passed: twelve locked 1280x720 JPEG boards, one request per clip, dialogue deferred to fixed TTS.")
        elif args.verify_complete:
            verify_complete()
        else:
            if args.previous_frame is None:
                raise RuntimeError("S01E15 needs the accepted S01E14 final continuity frame")
            base.generate("S01E15", None, args.previous_frame)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
