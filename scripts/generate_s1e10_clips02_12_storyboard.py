#!/usr/bin/env python3
"""Generate S01E10 clips 02-12 once each from their locked three-shot boards.

This deliberately has no retry loop.  Each clip has exactly one Seedance request,
then the original video is checked for duration, audio, and Mandarin speech before
the permanent header and bilingual subtitles are burned in.
"""
from __future__ import annotations

import os
import argparse
from pathlib import Path

from PIL import Image, ImageOps

import generate_s1e10_12_five_second as base


ROOT = Path.cwd()
OUT = ROOT / os.environ.get("GENERATION_OUTPUT_DIR", "output/s1e10-clips02-12")
REFS = ROOT / "references/s1e10-12/storyboard_video_refs"
RAW = ROOT / "references/s1e10-12/storyboard_raw"
PREVIOUS_B64 = REFS / "S01E10_01_continuity.jpg.b64"
START_CLIP = int(os.environ.get("S01E10_START_CLIP", "2"))
END_CLIP = int(os.environ.get("S01E10_END_CLIP", "12"))
CONTINUITY_B64 = Path(os.environ.get("S01E10_CONTINUITY_B64", str(PREVIOUS_B64)))
END_CONTINUITY_B64_VALUE = os.environ.get("S01E10_END_CONTINUITY_B64", "")
END_CONTINUITY_B64 = Path(END_CONTINUITY_B64_VALUE) if END_CONTINUITY_B64_VALUE else None
SEED_OFFSET = int(os.environ.get("S01E10_SEED_OFFSET", "0"))
RECURRING = {"jian_ci", "lin_qian", "zhou_qiao", "xu_wei", "han_che", "tang_yun"}


def ass_time(value: float) -> str:
    h = int(value // 3600)
    m = int((value % 3600) // 60)
    s = value % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def provider_image_ok(path: Path) -> None:
    """Check both our asset and Seedance's 300-pixel minimum before submission."""
    base.image_ok(path)
    with Image.open(path) as image:
        width, height = image.size
    if width < 300 or height < 300:
        raise RuntimeError(f"Provider reference too small: {path} is {width}x{height}; minimum is 300px")


def storyboard_refs(clip_id: str, runtime: Path) -> list[Path]:
    runtime.mkdir(parents=True, exist_ok=True)
    encoded = [REFS / f"S01E10_{clip_id}_shot_{index}.jpg.b64" for index in range(1, 4)]
    if all(item.is_file() for item in encoded):
        result = [
            base.decode_b64(item, runtime / f"storyboard_{clip_id}_shot_{index}.jpg")
            for index, item in enumerate(encoded, 1)
        ]
    else:
        # Local-only fallback. The workflow requires the committed 320x540 refs.
        source_path = RAW / f"S01E10_{clip_id}.png"
        if not source_path.is_file():
            missing = ", ".join(item.name for item in encoded)
            raise RuntimeError(f"Missing locked storyboard references: {missing}")
        with Image.open(source_path) as source:
            source = source.convert("RGB")
            third = source.width // 3
            result = []
            for index in range(3):
                panel = source.crop((index * third, 0, (index + 1) * third if index < 2 else source.width, source.height))
                panel = ImageOps.fit(panel, (320, 540), Image.Resampling.LANCZOS)
                target = runtime / f"storyboard_{clip_id}_shot_{index + 1}.jpg"
                panel.save(target, quality=95)
                result.append(target)
    for item in result:
        provider_image_ok(item)
    return result


def write_ass(path: Path, episode: dict, clip: dict) -> None:
    cue = clip["dialogue"][0]
    name = cue["speaker"]
    line = cue["zh"].replace("\n", " ")
    english = cue["en"].replace("\n", " ")
    title = f"《吸血法医·剑刺》｜{episode['episode']}《{episode['title_zh']}》｜制作：林爱丽"
    path.write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 854\nPlayResY: 480\n\n"
        "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
        "Style: Header,Noto Sans CJK SC,18,&H00DED8C9,&H000000FF,&H00101724,&H80101724,0,0,0,0,100,100,0,0,1,1.4,0,8,18,18,13,1\n"
        "Style: Zh,Noto Sans CJK SC,22,&H00FFFFFF,&H000000FF,&H00101724,&H80101724,1,0,0,0,100,100,0,0,1,2.2,0,2,20,20,88,1\n"
        "Style: En,Arial,14,&H00E9E9E9,&H000000FF,&H00101724,&H80101724,0,0,0,0,100,100,0,0,1,1.8,0,2,20,20,48,1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
        f"Dialogue: 0,0:00:00.00,0:00:05.00,Header,,0,0,0,,{title}\n"
        f"Dialogue: 0,{ass_time(float(cue['start']))},{ass_time(float(cue['end']))},Zh,,0,0,0,,{{\\c&H00FFBB73&}}{name}：{{\\c&H00FFFFFF&}}{line}\n"
        f"Dialogue: 0,{ass_time(float(cue['start']))},{ass_time(float(cue['end']))},En,,0,0,0,,{english}\n",
        encoding="utf-8",
    )


def storyboard_prompt(plan: dict, episode: dict, clip: dict, names: list[str], has_end_continuity: bool = False) -> str:
    prompt = base.build_prompt(plan, episode, clip, names)
    old = (
        f"References 1 and 2 are visual-style and cinematic-lighting authorities from the accepted series. "
        f"The following images are fixed identity authorities for {', '.join(names)}; "
        "the final image is the previous accepted continuity frame, controlling only the opening light, screen direction and scene geography."
    )
    new = (
        "References 1 and 2 are accepted-series visual-style and cinematic-lighting authorities. "
        "References 3, 4 and 5 are the locked storyboard visuals for shots 1, 2 and 3 respectively: reproduce their shot order, composition, subjects, props, costume and action, but never render a triptych or text. "
        "The next reference images are fixed character-identity authorities. The final image controls only the opening light, screen direction and scene geography from the immediately previous accepted clip."
    )
    if has_end_continuity:
        new = (
            "References 1 and 2 are accepted-series visual-style and cinematic-lighting authorities. "
            "References 3, 4 and 5 are the locked storyboard visuals for shots 1, 2 and 3 respectively: reproduce their shot order, composition, subjects, props, costume and action, but never render a triptych or text. "
            "The next reference images are fixed character-identity authorities. The final two reference images are continuity authorities only: the first controls the opening frame, light and screen direction from the immediately previous accepted clip; the final image controls the intended handoff. Begin from the prior evidence-route geography, then finish with a calm visual handoff toward the hydrotherapy-pool floor-plan briefing; do not copy or generate any text from either continuity image."
        )
    if old not in prompt:
        raise RuntimeError(f"Could not lock storyboard-reference ordering for S01E10 clip {clip['id']}")
    return prompt.replace(old, new)


def make_final_contact(final: Path, folders: dict[str, Path], clip_id: str) -> None:
    """Keep subtitle-bearing proof frames separate from the text-free continuity frame."""
    contact = folders["proof"] / f"clip_{clip_id}_final_three_shot_contact.jpg"
    base.shell([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(final),
        "-vf", "fps=0.6,scale=427:240:force_original_aspect_ratio=decrease,pad=427:240:(ow-iw)/2:(oh-ih)/2:black,tile=3x1:padding=4:margin=4",
        "-frames:v", "1", "-q:v", "2", str(contact),
    ])
    base.image_ok(contact)


def selected_clips(episode: dict) -> list[dict]:
    if not (2 <= START_CLIP <= END_CLIP <= 12):
        raise RuntimeError("S01E10 clip range must be within 02 through 12")
    clips = [clip for clip in episode["clips"] if START_CLIP <= int(clip["id"]) <= END_CLIP]
    expected = [f"{item:02d}" for item in range(START_CLIP, END_CLIP + 1)]
    if episode["episode"] != "S01E10" or [clip["id"] for clip in clips] != expected:
        raise RuntimeError(f"This runner is locked to S01E10 clips {expected[0]} through {expected[-1]}")
    return clips


def preflight() -> None:
    plan = base.load_plan()
    episode = plan["episodes"][0]
    clips = selected_clips(episode)
    preflight_dir = OUT / "preflight_refs"
    for clip in clips:
        for index in range(1, 4):
            encoded = REFS / f"S01E10_{clip['id']}_shot_{index}.jpg.b64"
            decoded = base.decode_b64(encoded, preflight_dir / f"S01E10_{clip['id']}_shot_{index}.jpg")
            provider_image_ok(decoded)
    if not CONTINUITY_B64.is_file():
        raise RuntimeError(f"Missing proof continuity reference: {CONTINUITY_B64}")
    provider_image_ok(base.decode_b64(CONTINUITY_B64, preflight_dir / "S01E10_recovery_continuity.jpg"))
    if END_CONTINUITY_B64 is not None:
        if not END_CONTINUITY_B64.is_file():
            raise RuntimeError(f"Missing end continuity reference: {END_CONTINUITY_B64}")
        provider_image_ok(base.decode_b64(END_CONTINUITY_B64, preflight_dir / "S01E10_end_continuity.jpg"))
    print(f"Preflight passed: S01E10 clips {START_CLIP:02d}-{END_CLIP:02d}, one request per clip, storyboard refs ≥300px, audio/subtitle QC, no retries.")


def main() -> None:
    plan = base.load_plan()
    episode = plan["episodes"][0]
    clips = selected_clips(episode)
    if not os.environ.get("SEGMIND_API_KEY"):
        raise RuntimeError("SEGMIND_API_KEY is missing; no paid request made")

    from faster_whisper import WhisperModel
    from segmind import SegmindClient

    folders = base.episode_dirs("S01E10")
    style_dir = OUT / "shared_runtime_refs"
    styles = [
        base.decode_b64(base.E09_PANEL_1, style_dir / "s1e09_style_rain_laptop.jpg"),
        base.decode_b64(base.E09_PANEL_12, style_dir / "s1e09_style_blue_drive.jpg"),
    ]
    previous = base.decode_b64(CONTINUITY_B64, folders["runtime_refs"] / f"S01E10_clip_{START_CLIP - 1:02d}_accepted_continuity.jpg")
    provider_image_ok(previous)
    end_continuity = None
    if END_CONTINUITY_B64 is not None:
        end_continuity = base.decode_b64(END_CONTINUITY_B64, folders["runtime_refs"] / f"S01E10_clip_{END_CLIP + 1:02d}_opening_continuity.jpg")
        provider_image_ok(end_continuity)
    whisper = WhisperModel("tiny", device="cpu", compute_type="int8", download_root=os.environ.get("WHISPER_CACHE_DIR", "whisper_cache"))
    client = SegmindClient()
    manifest_path = OUT / "generation_manifest.json"
    manifest = {
        "episode": "S01E10", "clips": [], "request_count": 0, "automatic_retries": 0,
        "status": "running", "started_at": base.stamp(), "range": f"{START_CLIP:02d}-{END_CLIP:02d}",
        "continuity_source": str(CONTINUITY_B64),
        "end_continuity_source": str(END_CONTINUITY_B64) if END_CONTINUITY_B64 is not None else None,
        "seed_offset": SEED_OFFSET,
    }
    base.dump(manifest_path, manifest)
    try:
        for request_number, clip in enumerate(clips, 1):
            boards = storyboard_refs(clip["id"], folders["runtime_refs"])
            names = [name for name in clip["characters"] if name in RECURRING]
            identities = [base.identity(name, folders["runtime_refs"]) for name in names]
            refs = [*styles, *boards, *identities, previous]
            if end_continuity is not None:
                refs.append(end_continuity)
            if len(refs) > 9:
                raise RuntimeError(f"Too many locked references for S01E10 clip {clip['id']}")
            for image in refs:
                provider_image_ok(image)
            prompt = storyboard_prompt(plan, episode, clip, names, end_continuity is not None)
            prompt_path = folders["audit"] / f"clip_{clip['id']}_prompt.txt"
            prompt_path.write_text(prompt, encoding="utf-8")
            record = {
                "episode": "S01E10", "clip_id": clip["id"], "status": "submitting_once",
                "request_count": 1, "automatic_retries": 0, "references": [str(item) for item in refs], "started_at": base.stamp(),
            }
            record_path = folders["audit"] / f"clip_{clip['id']}_request.json"
            base.dump(record_path, record)
            urls = [base.upload(client, image) for image in refs]
            # The sole paid attempt for this clip. There is intentionally no retry branch.
            job = client.submit_async(
                "seedance-2.0-mini", prompt=prompt, reference_images=urls, duration=5,
                resolution="480p", aspect_ratio="16:9", generate_audio=True, bitrate_mode="high",
                return_last_frame=True, seed=202608112 + int(clip["id"]) - 1 + SEED_OFFSET,
            )
            record.update({"request_id": job.request_id, "status": "processing"})
            manifest["request_count"] += 1
            base.dump(record_path, record)
            base.dump(manifest_path, manifest)
            result = job.wait(timeout=1800, interval=5)
            base.dump(folders["audit"] / f"clip_{clip['id']}_result.json", result)
            raw = folders["raw"] / f"S01E10_clip_{clip['id']}_raw.mp4"
            record["provider_output_url"] = base.fetch_video(result, raw)
            record["technical_qc"] = base.verify(raw, clip, whisper, folders)
            previous = base.make_proof(raw, folders, clip["id"])
            ass = OUT / f"S01E10_clip_{clip['id']}.ass"
            write_ass(ass, episode, clip)
            final = OUT / f"S01E10_clip_{clip['id']}_final.mp4"
            base.shell([
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw),
                "-vf", f"subtitles={ass}:fontsdir=/usr/share/fonts/opentype/noto",
                "-c:a", "copy", "-movflags", "+faststart", str(final),
            ])
            make_final_contact(final, folders, clip["id"])
            record.update({
                "status": "completed", "completed_at": base.stamp(), "raw_sha256": base.sha(raw),
                "final": str(final), "final_sha256": base.sha(final), "continuity_sha256": base.sha(previous),
            })
            manifest["clips"].append(record)
            base.dump(record_path, record)
            base.dump(manifest_path, manifest)
        manifest.update({"status": "completed", "completed_at": base.stamp()})
        base.dump(manifest_path, manifest)
    except Exception as exc:
        manifest.update({"status": "failed", "failed_at": base.stamp(), "error": f"{type(exc).__name__}: {exc}"})
        base.dump(manifest_path, manifest)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    if args.preflight:
        preflight()
    else:
        main()
