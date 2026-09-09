import os,json,time,urllib.request,urllib.error,re
from pathlib import Path
out=Path("output/door-test");out.mkdir(parents=True,exist_ok=True)
report={"model":"wan3.0-video","duration":10,"resolution":"480P","estimated_usd":0.5,"attempt":1,"state":"PREPARING"}
def save():
 (out/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
save()
if os.environ.get("GITHUB_RUN_ATTEMPT","1")!="1": raise SystemExit("No automatic rerun allowed")
key=os.environ.get("SEGMIND_API_KEY")
if not key: raise SystemExit("Missing existing SEGMIND_API_KEY")
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kw): raise RuntimeError("Authenticated redirect refused")
opener=urllib.request.build_opener(NoRedirect)
def api(path,data=None):
 req=urllib.request.Request("https://api.segmind.com"+path,data=None if data is None else json.dumps(data).encode(),headers={"x-api-key":key,"Content-Type":"application/json"})
 with opener.open(req,timeout=70) as r:return json.load(r)
base="https://raw.githubusercontent.com/"+os.environ["GITHUB_REPOSITORY"]+"/"+os.environ["GITHUB_SHA"]+"/"
payload={"prompt":"""Make a 10-second cinematic hand-drawn 2D anime suspense sequence. Reference video 1 is a simple blocking animation: follow its single door opening, world layout, forward walking route and action continuity across the cut at five seconds. Transform the block figure into the adult male forensic doctor Jian Ci from image 1, with the same black hair, pale face, white coat and black high-neck shirt. Image 1 is appearance and painted anime style only: do not copy its seated pose, office layout or female character. Only one man appears.
Space: one modest full-size single-level modern room, one normal wooden entrance door, left hinge when seen from the corridor, opens inward once, level floor, table at back right. The preview's cutaway walls are a visibility aid; render an intact believable room, not a dollhouse.
Shot 1 (0-5s): steady elevated three-quarter view near the corridor, see his hand and entire doorway. Jian Ci reaches the handle once and gently pushes the door inward to approximately 95 degrees; releases it, then begins stepping across the unobstructed threshold. Door remains open. No repeated opening.
Shot 2 (5-10s): cut slightly closer from the same side, preserve the exact ongoing step, door hinge, open angle, table position and walking direction. He continues into the same room, takes two measured steps, then stops before the back-right table without touching it. Never restart the entrance or turn back.
Restrained dark blue-gray cinematic lighting, soft warm practical accent, readable hands and face, detailed painted anime linework, real human proportions and natural walking. Replace all block geometry with finished anime environment and human anatomy. Sound: handle click, one soft hinge creak, continuous measured footsteps and low room ambience only. No dialogue or music. No text, captions, watermarks, stairs, extra doors, split screen, morphs, additional people or live action.""",
"reference_images":[base+"video-tests/jianci-transition/modern.png"],
"reference_videos":[base+"video-tests/jianci-previz/door-reference.mp4"],
"resolution":"480P","duration":10,"aspect_ratio":"16:9","audio":True,"prompt_extend":False,"enable_thinking":True,"seed":20260909,
"negative_prompt":"stairs, staircase, repeated opening, double head turn, teleportation, block character, dollhouse, extra person, subtitles, text, split screen, live action, 3D cartoon"}
(out/"payload.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2))
try:
 api("/v1/get-user-credits")
 report["state"]="SUBMITTING";save()
 result=api("/v2/wan3.0-video",payload)
 rid=result.get("request_id","")
 if not re.fullmatch(r"[A-Za-z0-9_-]+",rid):raise RuntimeError("Submission returned no request ID")
 report.update(state="QUEUED",request_id=rid);save();print("Accepted request",rid,flush=True)
 deadline=time.monotonic()+1500
 while time.monotonic()<deadline:
  try: st=api("/v2/requests/"+rid+"/status").get("status","UNKNOWN")
  except urllib.error.HTTPError as e:
   if e.code==422:
    report.update(state="FAILED",status_http=422);save();break
   raise
  report["state"]=st;save()
  if st=="FAILED":break
  if st=="COMPLETED":
   result=api("/v2/requests/"+rid)
   (out/"result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
   def urls(v):
    if isinstance(v,str) and v.startswith("https://"):yield v
    elif isinstance(v,list):
     for child in v:yield from urls(child)
    elif isinstance(v,dict):
     for k in ["output","video","video_url","url","output_url","data"]:
      if k in v:yield from urls(v[k])
   for u in urls(result):
    with urllib.request.urlopen(u,timeout=120) as r: data=r.read(100*1024*1024)
    if b"ftyp" in data[:48]:
     (out/"wan3-door-test.mp4").write_bytes(data);report["downloaded"]=True;save();break
   break
  time.sleep(10)
 else:report["state"]="TIMEOUT_RETAIN_REQUEST_ID";save()
except urllib.error.HTTPError as e:
 report["http_error"]=e.code
 report["error_detail"]=e.read(1200).decode(errors="replace").replace(key,"[REDACTED]")
 if report["state"]=="SUBMITTING":report["state"]="SUBMISSION_FAILED_OR_UNKNOWN"
 save()
except Exception as e:
 report["error_type"]=type(e).__name__;save()
print(json.dumps(report,ensure_ascii=False),flush=True)
