#!/usr/bin/env python3
"""One authorised targeted repair for E5 clips 10-11 and E6 clips 10-12."""
from __future__ import annotations
import base64, hashlib, json, os, re, shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from PIL import Image

ROOT = Path.cwd()
OUT = ROOT / "output" / "s1e05-s1e06-targeted-repair"
PRIOR = ROOT / "prior_results"
RAW = OUT / "raw"
AUDIT = OUT / "audit"
PROOF = OUT / "proof"
RUNTIME = OUT / "runtime"
PLANS = {
    "S01E05": ROOT / "references" / "s1e05_rework" / "five_second_plan.json",
    "S01E06": ROOT / "references" / "s1e06_rework" / "five_second_plan.json",
}
TARGETS = [("S01E05", "10"), ("S01E05", "11"), ("S01E06", "10"), ("S01E06", "11"), ("S01E06", "12")]
FINAL_NAMES = {
    "S01E05": "S1E05_TheMissingFortyOneMinutes_TargetedRepair_Final.mp4",
    "S01E06": "S1E06_TestimonyWithoutAWound_TargetedRepair_Final.mp4",
}

def now(): return datetime.now(timezone.utc).isoformat()
def dump(path: Path, value: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
def run(args, capture=False): return subprocess.run(args, check=True, text=True, capture_output=capture)
def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""): h.update(chunk)
    return h.hexdigest()
def probe(path): return json.loads(run(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(path)],True).stdout)
def image_ok(path):
    if not path.is_file() or path.stat().st_size < 5000: raise RuntimeError(f"invalid image {path}")
    with Image.open(path) as im:
        if min(im.size) < 150: raise RuntimeError(f"small image {path}")
        im.verify()
def video_ok(path):
    data=probe(path); streams=data.get("streams",[]); dur=float(data.get("format",{}).get("duration") or 0)
    vs=[x for x in streams if x.get("codec_type")=="video"]; aus=[x for x in streams if x.get("codec_type")=="audio"]
    if path.stat().st_size < 200000 or not vs or not aus or not 4.3 <= dur <= 5.8: raise RuntimeError(f"technical A/V QC failed: {path}")
    out=subprocess.run(["ffmpeg","-hide_banner","-nostats","-i",str(path),"-vn","-af","volumedetect","-f","null","-"],capture_output=True,text=True).stderr
    match=re.search(r"max_volume:\s*(-?inf|-?\d+(?:\.\d+)?)\s*dB",out)
    if not match or match.group(1)=="-inf" or float(match.group(1)) < -55: raise RuntimeError(f"silent output: {path}")
    return {"duration":dur,"width":vs[0].get("width"),"height":vs[0].get("height"),"audio":aus[0].get("codec_name"),"max_volume_db":float(match.group(1))}
def frame(src, out):
    out.parent.mkdir(parents=True,exist_ok=True)
    run(["ffmpeg","-hide_banner","-loglevel","error","-y","-sseof","-0.16","-i",str(src),"-frames:v","1","-q:v","2",str(out)])
    image_ok(out); return out
def recursive(name):
    hits=list(PRIOR.rglob(name))
    if not hits: raise RuntimeError(f"missing prior artifact {name}")
    return hits[0]
def prepare_prior():
    source=recursive("raw")
    shutil.copytree(source,RAW,dirs_exist_ok=True)
    for ep in ("S01E05","S01E06"):
        for n in range(1,13):
            if (ep,n) in (("S01E06",11),("S01E06",12)): continue
            if not (RAW/f"{ep}_clip_{n:02d}_raw.mp4").is_file(): raise RuntimeError(f"missing {ep} clip {n:02d}")
    return {
        "lin_qian": recursive("identity_lin_qian.jpg"),
        "jian_ci": recursive("identity_jian_ci.jpg") if list(PRIOR.rglob("identity_jian_ci.jpg")) else ROOT / "references" / "s1e03" / "source_refs" / "jian_ci_identity.jpg",
        "zhou_qiao": recursive("identity_zhou_qiao.jpg"),
        "chen_mo": recursive("chen_mo_e4_identity.jpg"),
    }
def cheng_identity():
    # The provider rejected the first small portrait (228px narrow side) before rendering.
    # This normalized 576px portrait keeps the exact approved identity but is safely sized.
    source=ROOT / "references" / "s1e05_rework" / "identity" / "cheng_yue_identity_v2.jpg.b64"
    target=RUNTIME / "cheng_yue_identity_v2.jpg"
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(base64.b64decode(source.read_text(encoding="ascii")))
    image_ok(target); return target
def style(ep, cid):
    source=recursive(f"style_{cid}.jpg")
    target=RUNTIME/f"{ep}_style_{cid}.jpg"; shutil.copy2(source,target); image_ok(target); return target
def upload(client,path):
    result=client.files.upload(path); urls=result.get("file_urls") if isinstance(result,dict) else None
    if not urls or not isinstance(urls[0],str): raise RuntimeError(f"could not upload reference {path}")
    return urls[0]
def all_urls(value,out):
    if isinstance(value,str) and value.startswith(("https://","http://")): out.append(value)
    elif isinstance(value,dict):
        for x in value.values(): all_urls(x,out)
    elif isinstance(value,list):
        for x in value: all_urls(x,out)
def fetch(result,destination):
    import requests
    urls=[]; all_urls(result.get("output",result) if isinstance(result,dict) else result,urls)
    for url in dict.fromkeys(urls):
        response=requests.get(url,timeout=300); response.raise_for_status()
        if len(response.content)>200000 and (response.content[4:8]==b"ftyp" or "video" in response.headers.get("content-type","").lower()):
            destination.write_bytes(response.content); return url
    raise RuntimeError("Segmind returned no downloadable video")
def clip(plan,cid): return next(x for x in plan["clips"] if x["id"]==cid)
def prompt(plan,c,cast):
    shots="\n".join(f"{i+1}. {s}" for i,s in enumerate(c["shots"]))
    lines="\n".join(f"{x['start']:.2f}-{x['end']:.2f} {x['speaker']}: {x['zh']}" for x in c["dialogue"])
    return f"""ORIGINAL SERIES TARGETED REPAIR. Render exactly one 5-second, full-screen, 16:9 animated clip for 《吸血法医·剑刺》 {plan['episode']}《{plan['episode_title_zh']}》 clip {c['id']}. The first reference locks the series 2D forensic-noir look; named identity references lock only those people; the final reference locks the exact opening composition. Never display any reference as a panel, grid or split screen.
Exactly three continuous cinematic shots:\n{shots}
Scene: {c['scene']}
Cast lock: {cast}. No person other than this cast may be visible. Cheng Yue is the navy-uniformed ordinary cold-chain supervisor in his reference image; he has no glasses and is never Zhou Qiao. Lin Qian has a short black bob and navy investigator uniform. Jian Ci is in a white forensic coat, black gloves, no glasses. Chen Mo's neck stays fully intact. Maintain screen direction, room geography, clothing, hands, evidence separation and restrained acting.
Mandarin audio: clear, synchronised, natural adult Mandarin dialogue with only low room tone, no music. Speak only these exact lines at these times; no English, no invented speech, no silence:\n{lines}
Visual lock: dark blue-black and iron-gray 2D manga/anime forensic noir, cinematic lighting, controlled camera movement, clear faces and eyes. Never live action, 3D, chibi, comic page, collage, on-image title, watermark, generated subtitle, readable report, duplicate person, wrong cast, face swap, gore, fangs, glowing eyes, supernatural evidence."""
def ass_time(seconds):
    cs=round(seconds*100); h,cs=divmod(cs,360000); m,cs=divmod(cs,6000)
    return f"{h}:{m:02d}:{cs/100:05.2f}"
def esc(s): return s.replace("\\",r"\\").replace("{",r"\\{").replace("}",r"\\}").replace("\n",r"\\N")
def assemble(plan):
    ep=plan["episode"]; stage=OUT/"final"/ep; normal=stage/"normal"; normal.mkdir(parents=True,exist_ok=True)
    files=[]
    for n in range(1,13):
        source=RAW/f"{ep}_clip_{n:02d}_raw.mp4"; dest=normal/f"{n:02d}.mp4"
        run(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(source),"-vf","scale=864:496:force_original_aspect_ratio=decrease,pad=864:496:(ow-iw)/2:(oh-ih)/2:black,fps=24","-c:v","libx264","-preset","medium","-crf","18","-c:a","aac","-ar","48000","-ac","2","-b:a","160k",str(dest)])
        files.append(dest)
    concat=stage/"concat.txt"; concat.write_text("".join(f"file '{x.resolve()}'\n" for x in files),encoding="utf-8")
    joined=stage/"joined.mp4"; run(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","concat","-safe","0","-i",str(concat),"-c","copy",str(joined)])
    ass=stage/"subtitles.ass"; rows=["[Script Info]","ScriptType: v4.00+","PlayResX: 864","PlayResY: 496","ScaledBorderAndShadow: yes","","[V4+ Styles]","Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding","Style: Header,Noto Sans CJK SC,19,&H00FFFFFF,&H000000FF,&H00101010,&H90000000,1,0,0,0,100,100,0,0,1,1.5,0,8,18,18,13,1","Style: CN,Noto Sans CJK SC,21,&H00FFFFFF,&H000000FF,&H00101010,&H80000000,1,0,0,0,100,100,0,0,1,2.1,0.6,2,32,32,34,1","Style: EN,DejaVu Sans,13,&H00F4F4F4,&H000000FF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,1.4,0.5,2,32,32,14,1","","[Events]","Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"]
    rows.append(f"Dialogue: 0,0:00:00.00,{ass_time(60)},Header,,0,0,0,,{esc(plan['persistent_header'])}")
    for index,c in enumerate(plan["clips"]):
        for line in c["dialogue"]:
            start=index*5+float(line["start"]); end=index*5+float(line["end"])
            rows.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},CN,,0,0,0,,{esc(line['zh'])}")
            rows.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},EN,,0,0,0,,{esc(line['en'])}")
    ass.write_text("\n".join(rows)+"\n",encoding="utf-8")
    out=stage/FINAL_NAMES[ep]
    run(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",str(joined),"-vf",f"subtitles={ass}:fontsdir=/usr/share/fonts/opentype/noto","-c:v","libx264","-preset","slow","-crf","17","-c:a","aac","-ar","48000","-ac","2","-b:a","160k","-movflags","+faststart",str(out)])
    data=probe(out); dur=float(data.get("format",{}).get("duration") or 0)
    if not 58<=dur<=63 or not any(x.get("codec_type")=="audio" for x in data.get("streams",[])): raise RuntimeError(f"final QC failed {ep}")
    return out
def main():
    if not os.environ.get("SEGMIND_API_KEY"): raise RuntimeError("SEGMIND_API_KEY missing; no provider request made")
    for p in (RAW,AUDIT,PROOF,RUNTIME): p.mkdir(parents=True,exist_ok=True)
    plans={ep:json.loads(path.read_text(encoding="utf-8")) for ep,path in PLANS.items()}
    ids=prepare_prior(); ids["cheng_yue"]=cheng_identity()
    from segmind import SegmindClient
    client=SegmindClient(); master={"status":"running","automatic_retries":0,"request_count":0,"targets":[f"{a}_{b}" for a,b in TARGETS],"started_at":now()}
    previous={"S01E05":frame(RAW/"S01E05_clip_09_raw.mp4",RUNTIME/"e5_09_last.jpg"),"S01E06":frame(RAW/"S01E06_clip_09_raw.mp4",RUNTIME/"e6_09_last.jpg")}
    try:
        for ep,cid in TARGETS:
            c=clip(plans[ep],cid)
            if ep=="S01E05": cast=[ids["lin_qian"],ids["cheng_yue"]]
            elif cid=="10": cast=[ids["cheng_yue"],ids["lin_qian"]]
            elif cid=="11": cast=[ids["chen_mo"],ids["jian_ci"],ids["lin_qian"]]
            else: cast=[ids["lin_qian"],ids["jian_ci"],ids["zhou_qiao"]]
            refs=[style(ep,cid),*cast,previous[ep]]
            record={"episode":ep,"clip":cid,"status":"submitting_once","automatic_retries":0,"reference_count":len(refs),"started_at":now()}; dump(AUDIT/f"{ep}_{cid}_request.json",record)
            job=client.submit_async("seedance-2.0-mini",prompt=prompt(plans[ep],c,", ".join(c["characters"])),reference_images=[upload(client,x) for x in refs],duration=5,resolution="480p",aspect_ratio="16:9",generate_audio=True,bitrate_mode="high",return_last_frame=True,seed=202608610+int(ep[-2:])*100+int(cid))
            master["request_count"]+=1; record["request_id"]=job.request_id; record["status"]="processing"; dump(AUDIT/f"{ep}_{cid}_request.json",record)
            result=job.wait(timeout=1800,interval=5); dump(AUDIT/f"{ep}_{cid}_result.json",result)
            dest=RAW/f"{ep}_clip_{cid}_raw.mp4"; record["output_url"]=fetch(result,dest); record["technical_qc"]=video_ok(dest); record["sha256"]=sha(dest); record["status"]="completed"; record["completed_at"]=now(); dump(AUDIT/f"{ep}_{cid}_request.json",record)
            previous[ep]=frame(dest,PROOF/f"{ep}_{cid}_last.jpg"); dump(AUDIT/"master_manifest.json",master)
        master["finals"]={ep:str(assemble(plan)) for ep,plan in plans.items()}; master["status"]="completed"; master["completed_at"]=now(); dump(AUDIT/"master_manifest.json",master)
    except Exception as exc:
        master["status"]="stopped_after_single_submission_failure"; master["error"]=str(exc); dump(AUDIT/"master_manifest.json",master); raise
if __name__=="__main__": main()
