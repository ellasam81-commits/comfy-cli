#!/usr/bin/env python3
"""One-pass S01E05–S01E06 rework generation. Each clip may be submitted once only."""
from __future__ import annotations
import argparse, hashlib, json, os, re, shutil, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from PIL import Image, ImageOps

ROOT = Path.cwd()
OUT = ROOT / "output" / "s1e05-s1e06-rework"
RUNTIME = OUT / "runtime_refs"
RAW = OUT / "raw"
AUDIT = OUT / "audit"
PROOF = OUT / "proof"
PLANS = [ROOT / "references" / "s1e05_rework" / "five_second_plan.json", ROOT / "references" / "s1e06_rework" / "five_second_plan.json"]
E4 = ROOT / "prior_e4"
BOARDS = ROOT / "references" / "s1e04" / "boards_hd_v2"
CHART = ROOT / "references" / "s1e03" / "source_refs" / "character_chart_highres.jpeg"
JIAN = ROOT / "references" / "s1e03" / "source_refs" / "jian_ci_identity.jpg"
EP_ARTIFACTS = {
    "S01E05": ("S1E05_TheMissingFortyOneMinutes_Final.mp4", "消失的四十一分钟"),
    "S01E06": ("S1E06_TestimonyWithoutAWound_Final.mp4", "没有伤口的证词"),
}
CROPS = {
    "lin_qian": (208,245,408,661),
    "zhou_qiao": (411,245,613,661),
    "xu_wei": (616,245,819,661),
    "han_che": (821,245,1019,661),
}

def now(): return datetime.now(timezone.utc).isoformat()
def dump(path: Path, value: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
def sha(path: Path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()
def run(cmd: list[str], capture=False):
    return subprocess.run(cmd, check=True, text=True, capture_output=capture)
def probe(path: Path):
    x=run(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(path)], True)
    return json.loads(x.stdout)
def image_ok(path: Path):
    if not path.is_file() or path.stat().st_size < 5000: raise RuntimeError(f"Missing/invalid image: {path}")
    with Image.open(path) as im:
        w,h=im.size; im.verify()
    if w<200 or h<150: raise RuntimeError(f"Reference too small: {path}")
def video_ok(path: Path):
    data=probe(path); streams=data.get("streams",[])
    dur=float(data.get("format",{}).get("duration") or 0)
    v=[s for s in streams if s.get("codec_type")=="video"]
    a=[s for s in streams if s.get("codec_type")=="audio"]
    if path.stat().st_size<200000 or not v or not a or not 4.3<=dur<=5.8: raise RuntimeError(f"Technical A/V QC failed: {path}")
    loud=subprocess.run(["ffmpeg","-hide_banner","-nostats","-i",str(path),"-vn","-af","volumedetect","-f","null","-"],capture_output=True,text=True).stderr
    m=re.search(r"max_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB",loud)
    if not m or m.group(1)=="-inf" or float(m.group(1))<-55: raise RuntimeError(f"Silent output: {path}")
    return {"duration":dur,"width":v[0].get("width"),"height":v[0].get("height"),"audio":a[0].get("codec_name"),"max_volume_db":float(m.group(1))}
def find_file(names: list[str]):
    for pat in names:
        hits=list(E4.rglob(pat))
        if hits: return hits[0]
    raise RuntimeError("Required prior-episode artifact file is missing")
def frame(source: Path, second: float, target: Path):
    target.parent.mkdir(parents=True,exist_ok=True)
    run(["ffmpeg","-hide_banner","-loglevel","error","-y","-ss",str(second),"-i",str(source),"-frames:v","1","-q:v","2",str(target)])
    image_ok(target); return target
def make_prior_refs():
    clip1=find_file(["S1E04_clip_01*_raw.mp4","*clip_01*.mp4"])
    clip12=find_file(["S1E04_clip_12*_raw.mp4","*clip_12*.mp4"])
    chen=frame(clip1,2.1,RUNTIME/"chen_mo_e4_identity.jpg")
    end=frame(clip12,4.75,RUNTIME/"s1e04_last_frame.jpg")
    return chen,end
def crop_style(clip_no: int):
    board=BOARDS/f"board_{((clip_no-1)%11)+2:02d}.png"
    image_ok(board)
    q=(clip_no-1)%4
    x=480 if q%2 else 0; y=270 if q>=2 else 0
    target=RUNTIME/f"style_{clip_no:02d}.jpg"
    with Image.open(board) as im:
        ImageOps.fit(im.convert("RGB").crop((x,y,x+480,y+270)),(640,360),Image.Resampling.LANCZOS).save(target,quality=94)
    image_ok(target); return target
def identity(name: str, chen: Path):
    if name=="jian_ci": image_ok(JIAN); return JIAN
    if name=="chen_mo": return chen
    if name=="cheng_yue": return None
    if name not in CROPS: raise RuntimeError(f"Unknown identity key {name}")
    target=RUNTIME/f"identity_{name}.jpg"
    if not target.exists():
        image_ok(CHART)
        with Image.open(CHART) as im:
            ImageOps.fit(im.convert("RGB").crop(CROPS[name]),(320,480),Image.Resampling.LANCZOS).save(target,quality=94)
    image_ok(target); return target
def upload(client, path: Path):
    reply=client.files.upload(path)
    urls=reply.get("file_urls") if isinstance(reply,dict) else None
    if not urls or not isinstance(urls[0],str): raise RuntimeError(f"Reference upload failed: {path}")
    return urls[0]
def urls_from(x, out):
    if isinstance(x,str) and x.startswith(("http://","https://")): out.append(x)
    elif isinstance(x,dict):
        for v in x.values(): urls_from(v,out)
    elif isinstance(x,list):
        for v in x: urls_from(v,out)
def fetch(result: Any, dest: Path):
    import requests
    candidates=[]; urls_from(result.get("output",result) if isinstance(result,dict) else result,candidates)
    for url in dict.fromkeys(candidates):
        r=requests.get(url,timeout=300); r.raise_for_status()
        if len(r.content)>200000 and (r.content[4:8]==b"ftyp" or "video" in r.headers.get("content-type","").lower() or url.split("?")[0].endswith((".mp4",".mov"))):
            dest.write_bytes(r.content); return url
    raise RuntimeError("Segmind returned no downloadable video")
def last_frame(video: Path, ep: str, cid: str):
    out=PROOF/f"{ep}_{cid}_last.jpg"
    return frame(video,4.70,out)
def plan_ok(plan):
    if plan.get("model")!="seedance-2.0-mini" or plan.get("resolution")!="480p" or plan.get("aspect_ratio")!="16:9" or plan.get("clip_count")!=12: raise RuntimeError("Plan production lock failed")
    clips=plan.get("clips",[])
    if [x.get("id") for x in clips] != [f"{i:02d}" for i in range(1,13)]: raise RuntimeError("Plan clip IDs must be 01–12")
    for c in clips:
        if len(c.get("shots",[]))!=3 or not c.get("dialogue"): raise RuntimeError(f"Invalid locked clip {c.get('id')}")
        for d in c["dialogue"]:
            if not 0<=float(d["start"])<float(d["end"])<=5: raise RuntimeError("Invalid dialogue cue")
def prompt(plan, clip, refs):
    shot_text="\n".join(f"{i+1}. {x}" for i,x in enumerate(clip["shots"]))
    line_text="\n".join(f"{d['start']:.2f}-{d['end']:.2f} {d['speaker']}: {d['zh']}" for d in clip["dialogue"])
    cast=", ".join(clip["characters"])
    return f"""ORIGINAL SERIES PRODUCTION LOCK. Render exactly one 5-second full-screen 16:9 animated clip for 《吸血法医·剑刺》 {plan['episode']}《{plan['episode_title_zh']}》, clip {clip['id']} of 12. The first reference is a prior-episode visual-language reference only. The following identity images lock the named core cast. The final reference is the immediately previous accepted frame and locks opening light and screen direction. Do not show any reference as a board, collage, grid or split screen.
Exactly three continuous cinematic shots:
{shot_text}
Identity and continuity lock: {plan['character_lock']}
Scene lock: {clip['scene']}
Evidence and logic lock: {plan['continuity_lock']}
Cinematic lock: {plan['visual_lock']} Maintain one coherent room geography and camera axis. {cast} only; never replace, duplicate, merge, age-shift or swap anyone. Jian Ci never wears glasses. Only Zhou Qiao wears silver-rim glasses and a hearing device. Chen Mo's neck stays completely intact. Preserve the transport case's damaged RIGHT latch, the cart's RIGHT wheel notch, and the silver-gray LEFT glove whenever specified.
Mandarin audio lock: generate clear, synchronised natural adult Mandarin speech with restrained location sound, no music. Speak only the exact lines below at the timed cue; no English, no extra voice or word and no silence:
{line_text}
No visible captions: title header and crisp bilingual subtitles are burned in after verified audio. Vampire detail is allowed only where specified and is never evidence.
Negative: {plan['global_negative']}"""
def ass_time(s):
    cent=round(s*100); h,cent=divmod(cent,360000); m,cent=divmod(cent,6000)
    return f"{h}:{m:02d}:{cent/100:05.2f}"
def esc(s): return s.replace("\\",r"\\").replace("{",r"\\{").replace("}",r"\\}").replace("\n",r"\\N")
def assemble(plan, raw_paths):
    ep=plan["episode"]; final_name,title=EP_ARTIFACTS[ep]; stage=OUT/"final"/ep; norm=stage/"normal"
    norm.mkdir(parents=True,exist_ok=True); concat=[]
    for i,src in enumerate(raw_paths,1):
        dst=norm/f"{i:02d}.mp4"
        run(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(src),"-vf","scale=864:496:force_original_aspect_ratio=decrease,pad=864:496:(ow-iw)/2:(oh-ih)/2:black,fps=24","-c:v","libx264","-preset","medium","-crf","18","-c:a","aac","-ar","48000","-ac","2","-b:a","160k",str(dst)])
        concat.append(dst)
    listfile=stage/"concat.txt"; listfile.write_text("".join(f"file '{p.resolve()}'\n" for p in concat),encoding="utf-8")
    joined=stage/"joined.mp4"; run(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","concat","-safe","0","-i",str(listfile),"-c","copy",str(joined)])
    ass=stage/"bilingual.ass"
    rows=["[Script Info]","ScriptType: v4.00+","PlayResX: 864","PlayResY: 496","ScaledBorderAndShadow: yes","","[V4+ Styles]","Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding","Style: Header,Noto Sans CJK SC,19,&H00FFFFFF,&H000000FF,&H00101010,&H90000000,1,0,0,0,100,100,0,0,1,1.5,0,8,18,18,13,1","Style: CN,Noto Sans CJK SC,21,&H00FFFFFF,&H000000FF,&H00101010,&H80000000,1,0,0,0,100,100,0,0,1,2.1,0.6,2,32,32,34,1","Style: EN,DejaVu Sans,13,&H00F4F4F4,&H000000FF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,1.4,0.5,2,32,32,14,1","","[Events]","Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"]
    rows.append(f"Dialogue: 0,0:00:00.00,{ass_time(60)},Header,,0,0,0,,{esc(plan['persistent_header'])}")
    for idx,c in enumerate(plan["clips"]):
        base=idx*5
        for d in c["dialogue"]:
            rows.append(f"Dialogue: 0,{ass_time(base+float(d['start']))},{ass_time(base+float(d['end']))},CN,,0,0,0,,{esc(d['zh'])}")
            rows.append(f"Dialogue: 0,{ass_time(base+float(d['start']))},{ass_time(base+float(d['end']))},EN,,0,0,0,,{esc(d['en'])}")
    ass.write_text("\n".join(rows)+"\n",encoding="utf-8")
    final=stage/final_name
    run(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(joined),"-vf",f"subtitles={ass}:fontsdir=/usr/share/fonts/opentype/noto","-c:v","libx264","-preset","slow","-crf","17","-c:a","aac","-ar","48000","-ac","2","-b:a","160k","-movflags","+faststart",str(final)])
    data=probe(final); streams=data.get("streams",[]); dur=float(data.get("format",{}).get("duration") or 0)
    if not 58<=dur<=63 or not any(s.get("codec_type")=="audio" for s in streams): raise RuntimeError(f"Final assembly QC failed for {ep}")
    return final
def preflight():
    for p in PLANS:
        plan=json.loads(p.read_text(encoding="utf-8")); plan_ok(plan)
    for p in [CHART,JIAN,*BOARDS.glob("board_*.png")]: image_ok(p)
    make_prior_refs()
    print("PRE-FLIGHT PASSED; no provider request was made.")
def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--preflight",action="store_true"); args=parser.parse_args()
    for p in [RUNTIME,RAW,AUDIT,PROOF]: p.mkdir(parents=True,exist_ok=True)
    if args.preflight: preflight(); return
    if not os.environ.get("SEGMIND_API_KEY"): raise RuntimeError("SEGMIND_API_KEY missing; no paid request made")
    preflight()
    from segmind import SegmindClient
    client=SegmindClient(); chen,e4_end=make_prior_refs(); previous=e4_end
    master={"status":"running","automatic_retries":0,"request_count":0,"started_at":now(),"episodes":[]}
    try:
        for plan_path in PLANS:
            plan=json.loads(plan_path.read_text(encoding="utf-8")); ep=plan["episode"]; raw_paths=[]
            episode_log={"episode":ep,"clips":[],"status":"running"}
            for index,clip in enumerate(plan["clips"],1):
                style=crop_style(index); ids=[identity(n,chen) for n in clip["characters"]]; ids=[x for x in ids if x]
                refs=[style,*ids,previous]
                if len(refs)>6: raise RuntimeError("Too many references")
                record={"clip_id":clip["id"],"status":"submitting_once","automatic_retries":0,"started_at":now(),"reference_count":len(refs)}
                dump(AUDIT/f"{ep}_clip_{clip['id']}_request.json",record)
                urls=[upload(client,x) for x in refs]
                job=client.submit_async("seedance-2.0-mini",prompt=prompt(plan,clip,refs),reference_images=urls,duration=5,resolution="480p",aspect_ratio="16:9",generate_audio=True,bitrate_mode="high",return_last_frame=True,seed=202608500+int(ep[-2:])*100+index)
                master["request_count"]+=1; record["request_id"]=job.request_id; record["status"]="processing"; dump(AUDIT/f"{ep}_clip_{clip['id']}_request.json",record)
                result=job.wait(timeout=1800,interval=5); dump(AUDIT/f"{ep}_clip_{clip['id']}_result.json",result)
                dest=RAW/f"{ep}_clip_{clip['id']}_raw.mp4"; record["output_url"]=fetch(result,dest); record["technical_qc"]=video_ok(dest)
                previous=last_frame(dest,ep,clip["id"]); record["status"]="completed"; record["completed_at"]=now(); record["sha256"]=sha(dest); dump(AUDIT/f"{ep}_clip_{clip['id']}_request.json",record)
                raw_paths.append(dest); episode_log["clips"].append(record); dump(AUDIT/"master_manifest.json",master)
            final=assemble(plan,raw_paths); episode_log["status"]="completed"; episode_log["final"]=str(final); episode_log["final_sha256"]=sha(final); master["episodes"].append(episode_log); dump(AUDIT/"master_manifest.json",master)
        master["status"]="completed"; dump(AUDIT/"master_manifest.json",master)
    except Exception as exc:
        master["status"]="stopped_after_single_submission_failure"; master["error"]=str(exc); dump(AUDIT/"master_manifest.json",master); raise
if __name__=="__main__": main()
