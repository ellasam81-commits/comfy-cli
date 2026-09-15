import base64, json, os, re, subprocess, time, urllib.request, urllib.parse, urllib.error
from pathlib import Path

HOST='https://api.xrtoken.ai'
OUT=Path('output/jianci-finale-e28-repair')
OUT.mkdir(parents=True, exist_ok=True)
KEY=os.environ['XRTOKEN'].strip()
assert KEY

def api(path, body=None):
    data=None if body is None else json.dumps(body,ensure_ascii=False).encode('utf-8')
    req=urllib.request.Request(HOST+path,data=data,headers={'Authorization':'Bearer '+KEY,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=90) as f:
        return json.load(f)

def download(url,path):
    assert urllib.parse.urlparse(url).scheme=='https'
    with urllib.request.urlopen(url,timeout=180) as f:path.write_bytes(f.read())

def get_video(task_id,name):
    r=api('/v1/videos/generations/'+urllib.parse.quote(task_id,safe=''))
    assert r.get('status')=='succeeded',f'reference task not ready: {task_id}'
    url=r.get('video_url') or (r.get('content') or {}).get('video_url')
    assert url
    p=OUT/name
    download(url,p)
    return p

def frame_data(src,seconds,crop=None):
    jpg=OUT/(src.stem+'-ref.jpg')
    cmd=['ffmpeg','-v','error','-y','-ss',str(seconds),'-i',str(src),'-frames:v','1']
    if crop: cmd+=['-vf','crop='+crop]
    subprocess.run(cmd+[str(jpg)],check=True)
    data='data:image/jpeg;base64,'+base64.b64encode(jpg.read_bytes()).decode('ascii')
    jpg.unlink(missing_ok=True)
    return data

def main():
    assert os.environ.get('JIANCI_EXECUTE')=='1'
    # Continue directly from the successful new EP28 clip 04; this anchors Jian's locked outfit.
    prev=get_video('48bb52a8-f706-4751-b74f-984ec5a26366','04-reference.mp4')
    xu=get_video('a8f8000e-6ef7-4714-aa1f-fb1a51f6c90c','xu-reference.mp4')
    prev_img=frame_data(prev,6)
    xu_img=frame_data(xu,1,'360:300:250:0')
    prompt='''12 seconds. Cinematic detailed hand-drawn 2D anime, cool blue-gray forensic suspense lighting, realistic adult proportions, restrained tension. This is a NON-GRAPHIC archival evidence scene. NO corpse, NO body, NO blood, NO wound, NO morgue drawer, NO fire, NO gore. Continue immediately from reference image 1. PRESENT-DAY JIAN CI MUST keep exactly the same face, black tousled short hair, BLACK TURTLENECK and DARK CHARCOAL-GRAY CIVILIAN JACKET from reference image 1 for the entire clip. He is suspended from forensic duty: NO white coat, NO forensic coat, NO scrubs, NO ID badge, NO gloves, NO police uniform. Jian stays two meters behind the evidence line, hands empty, and NEVER touches the evidence. Xu is the only person wearing a WHITE LAB COAT, over a green shirt, brown ponytail, and gloves, matching reference image 2. Xu stands at the evidence bench and lifts a sealed transparent archival specimen sleeve from a plain evidence box. Inside the sleeve is only a tiny dark fiber-like strand, abstract and non-graphic. No readable labels or generated text. At 0.45s Xu ON CAMERA says exactly in natural Mandarin: “这个可以不是记忆。” At 3.40s Jian ON CAMERA asks exactly: “能查吗？” At 5.10s Xu ON CAMERA says exactly: “先查来源和污染。” Then use a slow close-up on the sealed sleeve under cold light, followed by Jian's restrained reaction in the SAME locked outfit. Only the speaker's mouth moves. No invented dialogue, no morphing, no teleporting, no costume change, no subtitles, no music.'''
    content=[{'type':'text','text':prompt},{'type':'image_url','image_url':{'url':prev_img},'role':'reference_image'},{'type':'image_url','image_url':{'url':xu_img},'role':'reference_image'}]
    r=api('/v1/videos/generations',{'model':'wan3.0-video','content':content,'duration':12,'resolution':'480P','ratio':'16:9','generate_audio':True,'watermark':False,'prompt_extend':False,'seed':906181})
    tid=r.get('id') or (r.get('data') or {}).get('id')
    assert isinstance(tid,str) and re.fullmatch(r'[A-Za-z0-9_.:-]+',tid)
    report={'task_id':tid,'state':r.get('status','queued'),'purpose':'EP28 clip05 only','cost_guard':'single 12s targeted repair'}
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    deadline=time.monotonic()+2400
    while time.monotonic()<deadline:
        q=api('/v1/videos/generations/'+urllib.parse.quote(tid,safe=''))
        report['state']=q.get('status')
        (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if report['state']=='succeeded':
            url=q.get('video_url') or (q.get('content') or {}).get('video_url')
            assert url
            download(url,OUT/'05-raw.mp4')
            subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','json',str(OUT/'05-raw.mp4')],check=True,stdout=open(OUT/'ffprobe.json','wb'))
            print('EP28_CLIP05_READY',tid,flush=True)
            return
        if report['state'] in ('failed','cancelled','expired'):
            report['error']=str(q.get('error',''))[:1200]
            (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            raise SystemExit(2)
        time.sleep(12)
    report['state']='TIMEOUT_RETAIN_TASK_ID'
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    raise SystemExit(3)

if __name__=='__main__': main()
