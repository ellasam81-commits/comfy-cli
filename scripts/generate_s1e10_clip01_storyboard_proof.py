#!/usr/bin/env python3
"""One approved S01E10 clip-01 proof generated from its locked three-shot storyboard."""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

import generate_s1e10_12_five_second as base


ROOT = Path.cwd()
OUT = ROOT / os.environ.get("GENERATION_OUTPUT_DIR", "output/s1e10-proof")
STORY = ROOT / "references/s1e10-12/storyboard_raw/S01E10_01.png"
STORY_B64 = ROOT / "references/s1e10-12/storyboard_video_refs"


def ass_time(value: float) -> str:
    h = int(value // 3600)
    m = int((value % 3600) // 60)
    s = value % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def make_story_refs(runtime: Path) -> list[Path]:
    runtime.mkdir(parents=True, exist_ok=True)
    encoded = [STORY_B64 / f"S01E10_01_shot_{index}.jpg.b64" for index in range(1, 4)]
    if all(item.is_file() for item in encoded):
        return [base.decode_b64(item, runtime / f"storyboard_shot_{index}.jpg") for index, item in enumerate(encoded, 1)]
    if not STORY.is_file():
        raise RuntimeError(f"Missing locked storyboard visuals: {STORY_B64} or {STORY}")
    with Image.open(STORY) as source:
        source = source.convert("RGB")
        third = source.width // 3
        result: list[Path] = []
        for index in range(3):
            target = runtime / f"storyboard_shot_{index + 1}.jpg"
            crop = source.crop((index * third, 0, (index + 1) * third if index < 2 else source.width, source.height))
            crop.save(target, quality=95)
            base.image_ok(target)
            result.append(target)
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


def main() -> None:
    plan = base.load_plan()
    episode = plan["episodes"][0]
    clip = episode["clips"][0]
    if episode["episode"] != "S01E10" or clip["id"] != "01":
        raise RuntimeError("Proof must remain S01E10 clip 01")
    if not os.environ.get("SEGMIND_API_KEY"):
        raise RuntimeError("SEGMIND_API_KEY is missing; no paid request made")
    from faster_whisper import WhisperModel
    from segmind import SegmindClient

    folders = base.episode_dirs("S01E10")
    styles = [
        base.decode_b64(base.E09_PANEL_1, OUT / "shared_runtime_refs/s1e09_style_rain_laptop.jpg"),
        base.decode_b64(base.E09_PANEL_12, OUT / "shared_runtime_refs/s1e09_style_blue_drive.jpg"),
    ]
    boards = make_story_refs(folders["runtime_refs"])
    identities = [base.identity(name, folders["runtime_refs"]) for name in ("lin_qian", "jian_ci", "han_che")]
    refs = [*styles, *boards, *identities, styles[1]]
    if len(refs) != 9:
        raise RuntimeError("Proof reference lock must be exactly nine assets")
    for item in refs:
        base.image_ok(item)
    prompt = base.build_prompt(plan, episode, clip, ["lin_qian", "jian_ci", "han_che"])
    prompt = prompt.replace(
        "References 1 and 2 are visual-style and cinematic-lighting authorities from the accepted series. The following images are fixed identity authorities for lin_qian, jian_ci, han_che; the final image is the previous accepted continuity frame, controlling only the opening light, screen direction and scene geography.",
        "References 1 and 2 are accepted-series visual style and cinematic-lighting authorities. References 3, 4 and 5 are the locked storyboard visuals for shots 1, 2 and 3 respectively: reproduce their shot order, composition, subjects, props, costume and action, but never render a triptych or text. References 6, 7 and 8 are fixed identity authorities for Lin Qian, Jian Ci and Han Che. Reference 9 controls the opening rain-light and screen direction.",
    )
    prompt_file = folders["audit"] / "clip_01_prompt.txt"
    prompt_file.write_text(prompt, encoding="utf-8")
    manifest = {"episode": "S01E10", "clip": "01", "storyboard_sources": [str(item) for item in boards], "automatic_retries": 0, "request_count": 1, "status": "submitting_once"}
    base.dump(OUT / "proof_manifest.json", manifest)
    client = SegmindClient()
    urls = [base.upload(client, ref) for ref in refs]
    job = client.submit_async("seedance-2.0-mini", prompt=prompt, reference_images=urls, duration=5, resolution="480p", aspect_ratio="16:9", generate_audio=True, bitrate_mode="high", return_last_frame=True, seed=202608111)
    manifest.update({"request_id": job.request_id, "status": "processing"})
    base.dump(OUT / "proof_manifest.json", manifest)
    result = job.wait(timeout=1800, interval=5)
    raw = folders["raw"] / "S01E10_clip_01_storyboard_proof_raw.mp4"
    manifest["provider_output_url"] = base.fetch_video(result, raw)
    model = WhisperModel("tiny", device="cpu", compute_type="int8", download_root=os.environ.get("WHISPER_CACHE_DIR", "whisper_cache"))
    manifest["technical_qc"] = base.verify(raw, clip, model, folders)
    base.make_proof(raw, folders, "01_storyboard_proof")
    ass = OUT / "S01E10_clip_01_storyboard_proof.ass"
    write_ass(ass, episode, clip)
    final = OUT / "S01E10_clip_01_storyboard_proof_final.mp4"
    base.shell(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), "-vf", f"subtitles={ass}:fontsdir=/usr/share/fonts/opentype/noto", "-c:a", "copy", "-movflags", "+faststart", str(final)])
    manifest.update({"status": "completed", "final": str(final), "completed_at": base.stamp()})
    base.dump(OUT / "proof_manifest.json", manifest)


if __name__ == "__main__":
    main()
