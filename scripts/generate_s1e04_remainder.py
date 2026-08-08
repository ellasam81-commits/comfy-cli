#!/usr/bin/env python3
"""Generate S1E04 clips 02-12 once each after the accepted clip-01 gate."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

ROOT = Path.cwd()
PLAN = ROOT / "references/s1e04/five_second_plan.json"
STORY_LOCK = ROOT / "references/s1e04/current_story_lock.json"
BOARDS = ROOT / "references/s1e04/boards_hd_v2"
OUT = ROOT / os.environ.get("GENERATION_OUTPUT_DIR", "output/s1e04-remainder")
RUNTIME, RAW, AUDIT, PROOF, LAST = [OUT / item for item in ("runtime_refs", "raw", "audit", "proof", "last_frames")]
GATE_ARTIFACT_ID = "8885633802"

PROFILES = {
    "jian_ci": "Jian Ci / 剑刺: tall slim pale Chinese male vampire forensic doctor, sharp angular face, layered side-part black hair, white forensic coat over black high-neck shirt, black gloves, no glasses.",
    "lin_qian": "Lin Qian / 林浅: adult Chinese female police investigator, chin-length straight black bob, fitted dark-navy field uniform and black gloves.",
    "zhou_qiao": "Zhou Qiao / 周峤: young Chinese male technical officer, messy black hair, silver-rim glasses, small hearing device, dark technical jacket.",
    "xu_wei": "Xu Wei / 许未: adult Chinese female forensic analyst, brown high ponytail, olive forensic coverall, black examination gloves.",
    "han_che": "Han Che / 韩彻: mature Chinese male commander, broad square weathered face, short dark-gray hair, dark command jacket.",
    "chen_mo": "Chen Mo / 陈沫: living Chinese woman around thirty, shoulder-length rain-wet black hair, deep-brown long coat over ivory blouse, black trousers. Neck skin remains completely intact; blood exists only on the outer blouse collar."
}
CHART_BOXES = {"lin_qian":(208,245,408,661), "zhou_qiao":(411,245,613,661), "xu_wei":(616,245,819,661), "han_che":(821,245,1019,661)}

def shell(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=True, text=True)

def stamp() -> str: return datetime.now(timezone.utc).isoformat()

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""): h.update(b)
    return h.hexdigest()

def dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

def crop(board: Image.Image, index: int) -> Image.Image:
    row, col = divmod(index - 1, 2)
    box = (round(col * board.width / 2) + 3, round(row * board.height / 2) + 3, round((col + 1) * board.width / 2) - 3, round((row + 1) * board.height / 2) - 3)
    image = board.crop(box).convert("RGB")
    image = ImageEnhance.Contrast(image).enhance(1.08).filter(ImageFilter.UnsharpMask(radius=1, percent=120, threshold=2))
    return ImageOps.fit(image, (640, 360), Image.Resampling.LANCZOS)

def identity(images: list[Image.Image], target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", (960,720), (3,7,12))
    for i, image in enumerate(images[:2]): canvas.paste(ImageOps.fit(image.convert("RGB"),(480,720),Image.Resampling.LANCZOS),(i*480,0))
    canvas.save(target, quality=97)
    return target

def image_ok(path: Path) -> None:
    with Image.open(path) as im:
        w,h = im.size; im.verify()
    if w < 300 or h < 250 or path.stat().st_size > 30 * 1024 * 1024: raise RuntimeError(f"Invalid reference {path}")

def initial_frame() -> Path:
    token = os.environ.get("GITHUB_TOKEN")
    if not token: raise RuntimeError("GITHUB_TOKEN is missing; no paid request made")
    archive = OUT / "clip01_gate.zip"
    shell(["curl","--fail","--silent","--show-error","--location","-H",f"Authorization: Bearer {token}",f"https://api.github.com/repos/ellasam81-commits/comfy-cli/actions/artifacts/{GATE_ARTIFACT_ID}/zip","--output",str(archive)])
    shell(["unzip","-o",str(archive),"-d",str(OUT / "clip01_gate")])
    raw = OUT / "clip01_gate/raw/S1E04_clip_01_raw.mp4"
    if not raw.is_file(): raise RuntimeError("Accepted clip-01 raw video missing from gate artifact")
    frame = RUNTIME / "clip01_accepted_last.jpg"
    shell(["ffmpeg","-hide_banner","-loglevel","error","-y","-ss","4.70","-i",str(raw),"-frames:v","1","-q:v","2",str(frame)])
    image_ok(frame)
    return frame

def prepare(plan: dict[str,Any]) -> tuple[dict[str,Path],dict[str,list[Path]],Path]:
    for d in (RUNTIME,RAW,AUDIT,PROOF,LAST): d.mkdir(parents=True,exist_ok=True)
    charts = ROOT / "references/s1e03/source_refs/character_chart_highres.jpeg"
    jian = ROOT / "references/s1e03/source_refs/jian_ci_identity.jpg"
    if not charts.is_file() or not jian.is_file(): raise RuntimeError("Locked S1E03 character references are missing")
    identities = {"jian_ci":jian}
    chart = Image.open(charts).convert("RGB")
    for name,box in CHART_BOXES.items(): identities[name] = identity([chart.crop(box)],RUNTIME/f"identity_{name}.jpg")
    board06 = Image.open(BOARDS / "board_06.png").convert("RGB")
    identities["chen_mo"] = identity([crop(board06,1),crop(board06,3)],RUNTIME/"identity_chen_mo.jpg")
    panels:dict[str,list[Path]]={}
    for clip in plan["clips"][1:]:
        cid = clip["id"]; board_path = BOARDS / f"board_{cid}.png"
        if not board_path.is_file(): raise RuntimeError(f"Missing pre-cropped board {cid}")
        board = Image.open(board_path).convert("RGB")
        panels[cid]=[]
        for i in range(1,5):
            target=RUNTIME/f"clip_{cid}_shot_{i}.jpg"; crop(board,i).save(target,quality=97); panels[cid].append(target)
    for path in [*identities.values(),*(x for group in panels.values() for x in group)]: image_ok(path)
    first = initial_frame()
    dump(AUDIT/"preflight.json",{"status":"prepared_without_paid_request","created_at":stamp(),"plan_sha256":sha(PLAN),"clips":[c["id"] for c in plan["clips"][1:]],"initial_frame_sha256":sha(first)})
    return identities,panels,first

def build_prompt(plan:dict[str,Any], clip:dict[str,Any], refs:list[Path]) -> str:
    lines="\n".join(f"{float(x['start']):.2f}-{float(x['end']):.2f} {x['speaker']}: {x['zh']}" for x in clip["dialogue"])
    shots="\n".join(f"{i+1}. {text}" for i,text in enumerate(clip["shots"]))
    profiles="\n".join(PROFILES[x] for x in clip["characters"])
    return f"""ORIGINAL SERIES PRODUCTION LOCK. Animate exactly one clean five-second 16:9 clip for {plan['series_title_zh']} S1E04《{plan['episode_title_zh']}》, clip {clip['id']} of 12. Original dark forensic manga-noir only; never imitate a named artist, studio, franchise or copyrighted character.

ABSOLUTE STORYBOARD RULE. References 1-4 are storyboard composition and action authorities. Render exactly three distinct full-screen cinematic shots in the exact timing below; merge adjacent reference actions into one continuous camera shot where directed. Reference images after them are identity authorities; the final image is the prior accepted continuity frame, controlling only opening position, lighting and screen direction. Never show a board, grid, panel, split screen, collage, title, subtitle, logo, watermark, UI or readable label.

EXACT THREE SHOTS:\n{shots}

IDENTITY LOCK:\n{profiles}
Preserve face, hair, age, clothing, body scale, handed props and scene geography. No face swap, duplicate, extra person or wardrobe drift. Chen Mo is always alive and has an intact neck. Only Jian Ci may show the expressly requested restrained vampire hint; it is never proof.

LOOK / FORENSICS. {clip['scene']}. Exact supplied storyboard mood: cold blue-black low-saturation rain-dark 2D manga cinema, clean fine ink linework and restrained cel shading, controlled contrast, stable screen direction, one clear motivated move or action in each 1.67-second shot, restrained parallax, natural blink and breath. Never use thick painterly key-art texture, frozen poses or a concept-art poster look. Use gloves, seals and chain of custody. {plan['continuity_lock']}

AUDIO LOCK. Generate synchronized clear native Mandarin audio, restrained room ambience, no music. Speak only the exact Chinese lines below, without overlap or invented speech; do not speak English:\n{lines}
Do not generate visible subtitles. The persistent title header and clear Chinese/English subtitles are added deterministically after all video and audio QC.

STRICT NEGATIVE: {plan['global_negative']}"""

def upload(client:Any,path:Path)->str:
    result=client.files.upload(path); urls=result.get("file_urls") if isinstance(result,dict) else None
    if not urls or not isinstance(urls[0],str): raise RuntimeError(f"Reference upload failed: {path}")
    return urls[0]

def find_urls(data:Any,out:list[str])->None:
    if isinstance(data,str) and data.startswith(("https://","http://")): out.append(data)
    elif isinstance(data,dict):
        for v in data.values(): find_urls(v,out)
    elif isinstance(data,list):
        for v in data: find_urls(v,out)

def fetch_video(result:Any,target:Path)->str:
    import requests
    candidates:list[str]=[]; find_urls(result.get("output",result) if isinstance(result,dict) else result,candidates)
    for url in dict.fromkeys(candidates):
        res=requests.get(url,timeout=300); res.raise_for_status(); data=res.content
        if data[4:8]==b"ftyp" or "video/" in res.headers.get("content-type","").lower() or Path(urlparse(url).path).suffix.lower() in {".mp4",".mov",".webm"}:
            target.write_bytes(data); return url
    raise RuntimeError("Provider returned no video")

def verify(video:Path,cid:str,lines:list[dict[str,Any]],model:Any)->dict[str,Any]:
    probe=json.loads(shell(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(video)]).stdout)
    streams=probe.get("streams",[]); vs=[x for x in streams if x.get("codec_type")=="video"]; au=[x for x in streams if x.get("codec_type")=="audio"]
    duration=float(probe.get("format",{}).get("duration") or 0)
    if video.stat().st_size<200000 or not vs or not au or not 4.3<=duration<=5.8: raise RuntimeError(f"Clip {cid} technical video/audio QC failed")
    loud=subprocess.run(["ffmpeg","-hide_banner","-nostats","-i",str(video),"-vn","-af","volumedetect","-f","null","-"],check=False,capture_output=True,text=True)
    volume=re.search(r"max_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB",loud.stderr)
    if not volume or volume.group(1)=="-inf" or float(volume.group(1))<-55: raise RuntimeError(f"Clip {cid} audio silent")
    iterator,info=model.transcribe(str(video),language="zh",task="transcribe",beam_size=1,vad_filter=True,condition_on_previous_text=False)
    seg=[{"start":float(x.start),"end":float(x.end),"text":x.text.strip()} for x in iterator if x.text.strip()]
    transcript="".join(x["text"] for x in seg); seconds=sum(x["end"]-x["start"] for x in seg)
    dump(AUDIT/f"clip_{cid}_speech.json",{"language":getattr(info,"language",None),"transcript":transcript,"speech_seconds":seconds,"expected":[x["zh"] for x in lines]})
    if seconds<.4 or len(re.findall(r"[\u3400-\u9fff]",transcript))<2: raise RuntimeError(f"Clip {cid} Mandarin ASR QC failed")
    dump(AUDIT/f"clip_{cid}_ffprobe.json",probe); (AUDIT/f"clip_{cid}_loudness.txt").write_text(loud.stderr,encoding="utf-8")
    return {"duration":duration,"width":vs[0].get("width"),"height":vs[0].get("height"),"audio_codec":au[0].get("codec_name"),"max_volume_db":float(volume.group(1)),"asr":transcript}

def make_proof(video:Path,cid:str)->Path:
    last=LAST/f"clip_{cid}_continuity.jpg"; contact=PROOF/f"clip_{cid}_three_shot_contact.jpg"
    shell(["ffmpeg","-hide_banner","-loglevel","error","-y","-ss","4.70","-i",str(video),"-frames:v","1","-q:v","2",str(last)])
    shell(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(video),"-vf","fps=0.6,scale=427:240:force_original_aspect_ratio=decrease,pad=427:240:(ow-iw)/2:(oh-ih)/2:black,tile=3x1:padding=4:margin=4","-frames:v","1","-q:v","2",str(contact)])
    return last

def main()->None:
    if not STORY_LOCK.is_file():
        raise RuntimeError("Current S1E04 story lock is missing; no paid request made")
    story_lock = json.loads(STORY_LOCK.read_text(encoding="utf-8"))
    if story_lock.get("case_title_zh") != "十点十三分的伤口" or story_lock.get("status") != "ready_for_paid_generation":
        raise RuntimeError("S1E04 remainder is blocked: story lock is not the user-approved earlier version; no paid request made")
    plan=json.loads(PLAN.read_text(encoding="utf-8"))
    if plan.get("episode")!="S1E04" or plan.get("model")!="seedance-2.0-mini" or plan.get("clip_count")!=12 or plan.get("shots_per_clip")!=3 or plan.get("automatic_retries")!=0: raise RuntimeError("S1E04 plan lock invalid")
    clips=plan.get("clips",[])[1:]
    if [c.get("id") for c in clips] != [f"{x:02d}" for x in range(2,13)]: raise RuntimeError("Remainder must be clips 02-12 only")
    if any(len(c.get("shots", [])) != 3 for c in clips): raise RuntimeError("Each remainder clip must contain exactly three shots")
    identities,panels,previous=prepare(plan)
    if not os.environ.get("SEGMIND_API_KEY"): raise RuntimeError("SEGMIND_API_KEY is missing; no paid request made")
    from faster_whisper import WhisperModel
    from segmind import SegmindClient
    model=WhisperModel("tiny",device="cpu",compute_type="int8",download_root=os.environ.get("WHISPER_CACHE_DIR","whisper_cache")); client=SegmindClient()
    manifest={"episode":"S1E04","stage":"remainder","planned_clip_ids":[x["id"] for x in clips],"request_count":0,"automatic_retries":0,"status":"running","started_at":stamp(),"initial_frame_sha256":sha(previous),"clips":[]}; manifest_path=AUDIT/"generation_manifest.json"; dump(manifest_path,manifest)
    try:
        for clip in clips:
            cid=clip["id"]; refs=[*panels[cid],*(identities[name] for name in clip["characters"]),previous]
            if len(refs)>9: raise RuntimeError(f"Too many references for {cid}")
            for ref in refs: image_ok(ref)
            text=build_prompt(plan,clip,refs); (AUDIT/f"clip_{cid}_prompt.txt").write_text(text,encoding="utf-8")
            record={"clip_id":cid,"request_count":1,"automatic_retries":0,"status":"submitting_once","references":[str(x) for x in refs],"started_at":stamp()}; dump(AUDIT/f"clip_{cid}_request.json",record)
            urls=[upload(client,x) for x in refs]
            # Sole paid request for this clip; no retry path exists.
            # The locked legacy plan predates per-clip seed fields. Use a deterministic
            # non-repeating fallback so the first paid request cannot fail on a missing key.
            seed = int(clip.get("seed", 20260804 + int(cid)))
            job=client.submit_async("seedance-2.0-mini",prompt=text,reference_images=urls,duration=5,resolution="480p",aspect_ratio="16:9",generate_audio=True,bitrate_mode="high",return_last_frame=True,seed=seed)
            record["request_id"]=job.request_id; record["status"]="processing"; dump(AUDIT/f"clip_{cid}_request.json",record); manifest["request_count"]+=1; dump(manifest_path,manifest)
            result=job.wait(timeout=1800,interval=5); dump(AUDIT/f"clip_{cid}_result.json",result)
            video=RAW/f"S1E04_clip_{cid}_raw.mp4"; record["output_url"]=fetch_video(result,video); record["technical_qc"]=verify(video,cid,clip["dialogue"],model); previous=make_proof(video,cid)
            record.update({"status":"completed","completed_at":stamp(),"video_sha256":sha(video),"continuity_sha256":sha(previous)}); dump(AUDIT/f"clip_{cid}_request.json",record); manifest["clips"].append(record); dump(manifest_path,manifest)
        manifest.update({"status":"completed","completed_at":stamp()}); dump(manifest_path,manifest)
    except Exception as e:
        manifest.update({"status":"failed","failed_at":stamp(),"error":f"{type(e).__name__}: {e}"}); dump(manifest_path,manifest); raise

if __name__=="__main__":
    try: main()
    except Exception as e: print(f"ERROR: {type(e).__name__}: {e}",file=sys.stderr); raise
