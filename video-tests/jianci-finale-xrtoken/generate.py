import base64, json, os, re, subprocess, time, urllib.request, urllib.parse, urllib.error
from pathlib import Path

ROOT = Path(__file__).parent
CFG = json.loads((ROOT / "episodes.json").read_text(encoding="utf-8"))
EP = int(os.environ["EPISODE"])
MODEL = CFG["model"]
RESOLUTION = CFG["resolution"]
RATIO = CFG["ratio"]
SEED = int(CFG["seed"])
EPDATA = CFG["episodes"][str(EP)]
TITLE = CFG["titles"][str(EP)]
GLOBAL_PROMPT = CFG.get("global_prompt", "")
OUT = Path(f"output/jianci-finale-xrtoken/ep{EP}")
HOST = "https://api.xrtoken.ai"

def run(cmd):
    subprocess.run(cmd, check=True)

def probe(path):
    raw = subprocess.check_output([
        "ffprobe","-v","error","-show_entries",
        "format=duration:stream=index,codec_type,codec_name,width,height",
        "-of","json",str(path)
    ])
    return json.loads(raw)

def api(path, body=None):
    key = os.environ["XRTOKEN"].strip()
    assert key
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        HOST + path,
        data=data,
        headers={"Authorization":"Bearer " + key,"Content-Type":"application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as f:
        return json.load(f)

def safe_error(e):
    key = os.environ.get("XRTOKEN","")
    if isinstance(e, urllib.error.HTTPError):
        try:
            msg = e.read(1600).decode(errors="replace")
        except Exception:
            msg = str(e)
        return (str(e.code) + " " + msg).replace(key, "[REDACTED]")
    return (type(e).__name__ + ": " + str(e)).replace(key, "[REDACTED]")

def download(url, path):
    assert urllib.parse.urlparse(url).scheme == "https"
    with urllib.request.urlopen(url, timeout=180) as f:
        path.write_bytes(f.read())

def frame_data_url(src, sec, crop=None):
    jpg = OUT / (src.stem + f"-{str(sec).replace('.','_')}.jpg")
    cmd = ["ffmpeg","-v","error","-y","-ss",str(sec),"-i",str(src),"-frames:v","1"]
    if crop:
        cmd += ["-vf","crop=" + crop]
    run(cmd + [str(jpg)])
    meta = probe(jpg)
    vs = [s for s in meta["streams"] if s.get("codec_type") == "video"]
    assert vs
    assert min(vs[0].get("width",0), vs[0].get("height",0)) >= 240
    data = "data:image/jpeg;base64," + base64.b64encode(jpg.read_bytes()).decode("ascii")
    jpg.unlink(missing_ok=True)
    return data

def get_known_ref(task_id, sec, crop, name):
    tmp = OUT / f"ref-{name}.mp4"
    r = api("/v1/videos/generations/" + urllib.parse.quote(task_id, safe=""))
    assert r.get("status") == "succeeded", f"Reference {name} unavailable"
    url = r.get("video_url") or (r.get("content") or {}).get("video_url")
    assert url
    download(url, tmp)
    data = frame_data_url(tmp, sec, crop)
    tmp.unlink(missing_ok=True)
    return data

def srt_time(sec):
    ms = max(0, int(round(sec * 1000)))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def build_srt():
    cues = []
    cues.append((0.05,1.85,f"《吸血法医·剑刺》第{EP}集《{TITLE['zh']}》\nJian Ci · Episode {EP} — {TITLE['en']}"))
    names = {"jian":"剑刺","lin":"林浅","zhou":"周峤","xu":"许未","han":"韩彻","woman":"女声"}
    for idx, clip in enumerate(EPDATA):
        offset = idx * 12.0
        times = [float(x) for x in re.findall(r"At ([0-9.]+)s", clip["prompt"])]
        lines = clip["lines"]
        assert len(times) == len(lines), (idx, times, lines)
        for j, ((speaker, zh, en), st) in enumerate(zip(lines, times)):
            if j + 1 < len(times):
                end = max(st + 1.0, times[j+1] - 0.18)
            else:
                reading = max(1.5, min(4.8, len(zh) / 4.0 + 0.6))
                end = min(11.35, st + reading)
            cues.append((offset+st, offset+end, f"{names[speaker]}：{zh}\n{en}"))
    srt = OUT / f"EP{EP:02d}_bilingual.srt"
    with srt.open("w", encoding="utf-8") as f:
        for n,(a,b,text) in enumerate(cues,1):
            f.write(f"{n}\n{srt_time(a)} --> {srt_time(b)}\n{text}\n\n")
    return srt

def concat_and_finish(raws, report):
    listfile = OUT / "concat.txt"
    listfile.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in raws), encoding="utf-8")
    joined = OUT / f"EP{EP:02d}_joined.mp4"
    run([
        "ffmpeg","-v","error","-y","-f","concat","-safe","0","-i",str(listfile),
        "-c:v","libx264","-preset","veryfast","-crf","20",
        "-c:a","aac","-b:a","160k","-movflags","+faststart",str(joined)
    ])
    srt = build_srt()
    final_ascii = OUT / f"EP{EP:02d}_final_CN-EN_BGM.mp4"
    duration = float(probe(joined)["format"]["duration"])
    escaped_srt = str(srt.resolve()).replace("\\","/").replace(":","\\:").replace("'","\\'")
    fc = (
        f"[0:v]subtitles='{escaped_srt}':force_style='FontName=Noto Sans CJK SC,FontSize=18,"
        "Outline=2,Shadow=0,MarginV=26'[v];"
        "[0:a]volume=1.0[a0];"
        "[1:a]volume=0.010,lowpass=f=95[a1];"
        "[2:a]volume=0.004,lowpass=f=650[a2];"
        "[a0][a1][a2]amix=inputs=3:duration=first:normalize=0[a]"
    )
    run([
        "ffmpeg","-v","error","-y",
        "-i",str(joined),
        "-f","lavfi","-t",f"{duration:.3f}","-i","sine=frequency=49:sample_rate=48000",
        "-f","lavfi","-t",f"{duration:.3f}","-i","anoisesrc=color=brown:amplitude=0.02:sample_rate=48000",
        "-filter_complex",fc,
        "-map","[v]","-map","[a]",
        "-c:v","libx264","-preset","veryfast","-crf","20",
        "-c:a","aac","-b:a","160k","-movflags","+faststart",str(final_ascii)
    ])
    final_cn = OUT / f"剑刺_第{EP}集_{TITLE['zh']}_中英字幕_BGM.mp4"
    final_cn.write_bytes(final_ascii.read_bytes())
    for i,t in enumerate([2,14,26,38,50],1):
        jpg = OUT / f"proof-{i:02d}.jpg"
        run(["ffmpeg","-v","error","-y","-ss",str(t),"-i",str(final_ascii),"-frames:v","1",str(jpg)])
    meta = probe(final_ascii)
    types = [s.get("codec_type") for s in meta["streams"]]
    assert "video" in types and "audio" in types
    fdur = float(meta["format"]["duration"])
    assert 56 <= fdur <= 64, fdur
    report["final"] = final_cn.name
    report["final_duration"] = fdur
    report["srt"] = srt.name
    report["technical_qc"] = {"has_video":True,"has_audio":True,"proof_frames":5}
    (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")

def main():
    assert EP in range(25,31)
    assert os.environ.get("JIANCI_EXECUTE") == "1"
    assert os.environ.get("GITHUB_RUN_ATTEMPT","1") == "1", "Refuse duplicate paid workflow rerun"
    assert RESOLUTION == "480P"
    assert len(EPDATA) == 5 and sum(int(c["duration"]) for c in EPDATA) == 60
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT/"report.json").exists():
        raise RuntimeError("Existing report found; refusing duplicate paid generation")

    refs = {}
    for name, ref in CFG["known_refs"].items():
        refs[name] = get_known_ref(ref["task_id"],ref["seconds"],ref.get("crop"),name)

    report = {
        "episode":EP,"title":TITLE,"model":MODEL,"resolution":RESOLUTION,
        "estimate_usd":round(60*float(CFG["estimate_usd_per_second"]),4),"clips":[]
    }
    raws = []

    for clip in EPDATA:
        row = {"id":clip["id"],"duration":clip["duration"],"state":"SUBMITTING"}
        report["clips"].append(row)
        (OUT/"progress.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        full_prompt = (GLOBAL_PROMPT + " " + clip["prompt"]).strip()
        content = [{"type":"text","text":full_prompt}]
        for name in clip["refs"]:
            content.append({"type":"image_url","image_url":{"url":refs[name]},"role":"reference_image"})
        try:
            r = api("/v1/videos/generations",{
                "model":MODEL,"content":content,"duration":int(clip["duration"]),
                "resolution":RESOLUTION,"ratio":RATIO,"generate_audio":True,
                "watermark":False,"prompt_extend":False,"seed":SEED
            })
            tid = r.get("id") or (r.get("data") or {}).get("id")
            assert isinstance(tid,str) and re.fullmatch(r"[A-Za-z0-9_.:-]+",tid)
            row["task_id"] = tid
            row["state"] = r.get("status","queued")
        except Exception as e:
            row["state"] = "SUBMISSION_UNKNOWN_OR_FAILED"
            row["error"] = safe_error(e)
            (OUT/"progress.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
            raise

        deadline = time.monotonic()+2400
        while time.monotonic() < deadline:
            try:
                q = api("/v1/videos/generations/"+urllib.parse.quote(tid,safe=""))
                row["state"] = q.get("status")
                if row["state"] == "succeeded":
                    url = q.get("video_url") or (q.get("content") or {}).get("video_url")
                    assert url
                    dest = OUT / f"{clip['id']}-raw.mp4"
                    download(url,dest)
                    m = probe(dest)
                    stypes = [s.get("codec_type") for s in m["streams"]]
                    if "video" not in stypes or "audio" not in stypes:
                        row["state"] = "TECHNICAL_QC_FAILED"
                        row["error"] = "Missing video or audio stream; do not auto-retry"
                        break
                    row["file"] = dest.name
                    row["state"] = "succeeded"
                    raws.append(dest)
                    break
                if row["state"] in ("failed","cancelled","expired"):
                    row["error"] = re.sub(r"https?://[^\s\"']+","[URL REDACTED]",str(q.get("error",""))[:1200])
                    break
            except Exception as e:
                row["poll_error"] = safe_error(e)
            (OUT/"progress.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
            time.sleep(12)
        else:
            row["state"] = "TIMEOUT_RETAIN_TASK_ID"

        (OUT/"progress.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        if row["state"] != "succeeded":
            raise SystemExit(2)

    assert len(raws) == 5
    concat_and_finish(raws, report)
    print(f"EP{EP} READY",flush=True)

if __name__ == "__main__":
    main()
