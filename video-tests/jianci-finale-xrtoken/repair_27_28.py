import base64, json, os, re, subprocess, time, urllib.request, urllib.parse, urllib.error
from pathlib import Path

ROOT = Path(__file__).parent
CFG = json.loads((ROOT / "episodes.json").read_text(encoding="utf-8"))
EP = int(os.environ["EPISODE"])
assert EP in (27,28)
EPDATA = CFG["episodes"][str(EP)]
TITLE = CFG["titles"][str(EP)]
OUT = Path(f"output/jianci-finale-repair/ep{EP}")
HOST = "https://api.xrtoken.ai"
MODEL = CFG["model"]
RES = CFG["resolution"]
RATIO = CFG["ratio"]
SEED = CFG["seed"]

EXISTING = {
    27: {
        "01":"0a263141-c341-4e43-bcfa-5868c72aa4fc",
        "02":"bf406aae-fcd3-45da-85af-6e5b221d655a",
        "03":"9414afdd-7550-44b5-b34e-154142b25f8e",
        "04":"877c8d27-8bcf-43e7-b5ce-e789205a88e0",
    },
    28: {
        "01":"2f7cc6d9-8dc4-4032-8afd-ace8ec00ca12",
    }
}

SAFE_PROMPTS = {
    (27,"05"): "12 seconds. Cinematic detailed hand-drawn 2D anime, cool blue-gray archive room, restrained psychological horror, realistic adult proportions. ABSOLUTELY NO injured person, NO corpse, NO medical reenactment, NO blood, NO wound, NO photograph, NO readable generated text, NO subtitles, NO logos, NO music. Only Han and Jian are visible. Han stands LEFT under a cold desk lamp holding a plain photocopy angled AWAY from camera so its surface is visually blank. Jian stands RIGHT three steps away, hands empty. Camera stays medium-close on their faces and the page-turn gesture only. At 0.45s Han ON CAMERA says exactly in calm Mandarin: “无名男性。严重失血。次日生命体征恢复。” At 6.70s Jian ON CAMERA asks exactly: “下一页呢？” Han turns ONE plain page, still no readable text. At 8.55s Han ON CAMERA says exactly: “死亡确认。” End on Jian's controlled face, no supernatural effect, no red eyes, no fangs. Only the speaking person's mouth moves. No extra people or dialogue.",
    (28,"02"): "12 seconds. Cinematic detailed hand-drawn 2D anime, cool blue-gray evidence-review room, realistic adult proportions, restrained suspense. NO body, NO corpse photo, NO clothing on a person, NO violence, NO gore, NO readable generated text, NO subtitles, NO logos, NO music. Only Lin and Han are visible. Lin stands LEFT beside a steel desk and holds a PLAIN opaque evidence sleeve; Han stands RIGHT and places a second PLAIN opaque sleeve beside it. The objects remain abstract and blank, used only as neutral evidence props. At 0.45s Lin ON CAMERA says exactly: “当年的衣服没有身份标签，身上也没证件。” At 6.20s Han ON CAMERA says exactly: “还有一张寄存票。没人领。” Keep both calm and procedural. Only speaker mouth moves. No extra people, no invented visuals of a victim.",
    (28,"03"): "12 seconds. Cinematic detailed hand-drawn 2D anime, cold archive desk under one lamp, restrained mystery, realistic adult proportions. NO corpse, NO morgue, NO body drawer, NO cremation imagery, NO burial imagery, NO gore, NO readable generated text, NO music. Xu stands LEFT with a plain copied record folder; Han stands RIGHT. Camera stays on their faces and Xu turning ONE blank-looking page. At 0.45s Xu ON CAMERA says exactly: “之后没有火化记录，也没有埋葬编号。” At 6.20s Han ON CAMERA says exactly: “只剩一句：转移前，遗体不在原位。” After the line, hold one second on the closed folder. No paranormal motion, no extra people.",
    (28,"04"): "12 seconds. Cinematic detailed hand-drawn 2D anime, cool blue-gray records corridor, restrained psychological tension, realistic adult proportions. NO corpse, NO morgue drawer, NO flashback, NO ghost, NO blood, NO injury, NO supernatural effect, NO text, NO music. Lin stands LEFT, Jian stands RIGHT in black turtleneck and dark gray jacket. They do not move closer. At 0.45s Lin ON CAMERA says exactly: “尸体不见了？” At 2.15s Jian ON CAMERA says exactly: “可能不是尸体。” At 4.35s Lin ON CAMERA says exactly: “这是记忆，还是推断？” At 7.20s Jian ON CAMERA says exactly: “现在只是推断。” Jian remains calm and explicitly uncertain. Only speaker mouth moves; no extra people.",
    (28,"05"): "12 seconds. Cinematic detailed hand-drawn 2D anime, clean forensic evidence room, cold blue-gray light, restrained suspense, realistic adult proportions. NO body, NO injury, NO blood, NO scalp imagery, NO gore, NO readable generated text, NO music. Xu stands LEFT holding a tiny SEALED transparent secondary evidence container containing only a few loose dark hair strands, clearly detached evidence with no human remains shown. Jian stands RIGHT behind a floor boundary, hands empty, never touches it. At 0.45s Xu ON CAMERA says exactly: “旧物里还有一小束头发，封存记录完整。” At 7.40s Jian ON CAMERA says exactly: “这个可以不是记忆。” End close on the sealed container only. No extra dialogue or people."
}

def run(cmd): subprocess.run(cmd, check=True)
def probe(p):
    return json.loads(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration:stream=codec_type,width,height","-of","json",str(p)]))
def api(path, body=None):
    key=os.environ["XRTOKEN"].strip(); assert key
    data=None if body is None else json.dumps(body,ensure_ascii=False).encode()
    req=urllib.request.Request(HOST+path,data=data,headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=90) as f:return json.load(f)
def dl(url,p):
    assert urllib.parse.urlparse(url).scheme=="https"
    with urllib.request.urlopen(url,timeout=180) as f:p.write_bytes(f.read())
def task_video(tid,p):
    r=api("/v1/videos/generations/"+urllib.parse.quote(tid,safe="")); assert r.get("status")=="succeeded",(tid,r.get("status"))
    url=r.get("video_url") or (r.get("content") or {}).get("video_url"); assert url; dl(url,p)
def frame_data(src,sec,crop=None):
    jpg=OUT/(src.stem+"-ref.jpg")
    cmd=["ffmpeg","-v","error","-y","-ss",str(sec),"-i",str(src),"-frames:v","1"]
    if crop:cmd += ["-vf","crop="+crop]
    run(cmd+[str(jpg)])
    data="data:image/jpeg;base64,"+base64.b64encode(jpg.read_bytes()).decode(); jpg.unlink(missing_ok=True); return data
def ref_image(name):
    ref=CFG["known_refs"][name]; tmp=OUT/("ref-"+name+".mp4"); task_video(ref["task_id"],tmp); d=frame_data(tmp,ref["seconds"],ref.get("crop")); tmp.unlink(missing_ok=True); return d
def submit(clip,refs):
    content=[{"type":"text","text":SAFE_PROMPTS[(EP,clip["id"])]}]
    for name in clip["refs"]:content.append({"type":"image_url","image_url":{"url":refs[name]},"role":"reference_image"})
    r=api("/v1/videos/generations",{"model":MODEL,"content":content,"duration":12,"resolution":RES,"ratio":RATIO,"generate_audio":True,"watermark":False,"prompt_extend":False,"seed":SEED})
    tid=r.get("id") or (r.get("data") or {}).get("id"); assert isinstance(tid,str)
    deadline=time.monotonic()+2400
    while time.monotonic()<deadline:
        q=api("/v1/videos/generations/"+urllib.parse.quote(tid,safe="")); st=q.get("status")
        if st=="succeeded":
            url=q.get("video_url") or (q.get("content") or {}).get("video_url"); assert url; return tid,url
        if st in ("failed","cancelled","expired"):raise RuntimeError(f"{clip['id']} {st}: {q.get('error','')}")
        time.sleep(12)
    raise TimeoutError(tid)
def srt_time(sec):
    ms=int(round(sec*1000)); h,ms=divmod(ms,3600000); m,ms=divmod(ms,60000); s,ms=divmod(ms,1000); return f"{h:02}:{m:02}:{s:02},{ms:03}"
def make_srt():
    names={"jian":"剑刺","lin":"林浅","zhou":"周峤","xu":"许未","han":"韩彻"}; cues=[(0.05,1.85,f"《吸血法医·剑刺》第{EP}集《{TITLE['zh']}》\nJian Ci · Episode {EP} — {TITLE['en']}")]
    for i,c in enumerate(EPDATA):
        prompt=SAFE_PROMPTS.get((EP,c["id"]),c["prompt"]); times=[float(x) for x in re.findall(r"At ([0-9.]+)s",prompt)]
        assert len(times)==len(c["lines"]),(c["id"],times,c["lines"])
        for j,(line,st) in enumerate(zip(c["lines"],times)):
            sp,zh,en=line; end=(times[j+1]-0.18 if j+1<len(times) else min(11.3,st+max(1.5,min(4.5,len(zh)/4+0.6))))
            cues.append((i*12+st,i*12+end,f"{names[sp]}：{zh}\n{en}"))
    p=OUT/f"EP{EP:02d}_bilingual.srt"
    with p.open("w",encoding="utf-8") as f:
        for n,(a,b,t) in enumerate(cues,1):f.write(f"{n}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n\n")
    return p
def finish(raws,report):
    lst=OUT/"concat.txt"; lst.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in raws))
    joined=OUT/f"EP{EP:02d}_joined.mp4"; run(["ffmpeg","-v","error","-y","-f","concat","-safe","0","-i",str(lst),"-c:v","libx264","-preset","veryfast","-crf","20","-c:a","aac","-b:a","160k","-movflags","+faststart",str(joined)])
    srt=make_srt(); esc=str(srt.resolve()).replace(":","\\:").replace("'","\\'")
    out=OUT/f"剑刺_第{EP}集_{TITLE['zh']}_中英字幕_BGM.mp4"; dur=float(probe(joined)["format"]["duration"])
    fc=f"[0:v]subtitles='{esc}':force_style='FontName=Noto Sans CJK SC,FontSize=18,Outline=2,MarginV=26'[v];[0:a]volume=1.0[a0];[1:a]volume=0.010,lowpass=f=95[a1];[2:a]volume=0.004,lowpass=f=650[a2];[a0][a1][a2]amix=inputs=3:duration=first:normalize=0[a]"
    run(["ffmpeg","-v","error","-y","-i",str(joined),"-f","lavfi","-t",str(dur),"-i","sine=frequency=49:sample_rate=48000","-f","lavfi","-t",str(dur),"-i","anoisesrc=color=brown:amplitude=0.02:sample_rate=48000","-filter_complex",fc,"-map","[v]","-map","[a]","-c:v","libx264","-preset","veryfast","-crf","20","-c:a","aac","-b:a","160k","-movflags","+faststart",str(out)])
    m=probe(out); types=[s.get("codec_type") for s in m["streams"]]; assert "video" in types and "audio" in types; assert 56<float(m["format"]["duration"])<64
    for i,t in enumerate([2,14,26,38,50],1):run(["ffmpeg","-v","error","-y","-ss",str(t),"-i",str(out),"-frames:v","1",str(OUT/f"proof-{i:02d}.jpg")])
    report.update(final=out.name,srt=srt.name,technical_qc={"has_video":True,"has_audio":True,"proof_frames":5}); (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))

def main():
    assert os.environ.get("JIANCI_EXECUTE")=="1"; assert os.environ.get("GITHUB_RUN_ATTEMPT","1")=="1"
    OUT.mkdir(parents=True,exist_ok=True)
    refs={n:ref_image(n) for n in CFG["known_refs"]}
    report={"episode":EP,"repair":True,"clips":[]}; raws=[]
    for c in EPDATA:
        dest=OUT/f"{c['id']}-raw.mp4"
        if c["id"] in EXISTING[EP]:
            tid=EXISTING[EP][c["id"]]; task_video(tid,dest); report["clips"].append({"id":c["id"],"source":"reused-success","task_id":tid})
        else:
            tid,url=submit(c,refs); dl(url,dest); report["clips"].append({"id":c["id"],"source":"targeted-regeneration","task_id":tid})
        m=probe(dest); types=[s.get("codec_type") for s in m["streams"]]; assert "video" in types and "audio" in types
        raws.append(dest); (OUT/"progress.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    finish(raws,report); print(f"EP{EP} TARGETED REPAIR READY")
if __name__=="__main__":main()
