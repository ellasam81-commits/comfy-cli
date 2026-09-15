import base64, json, os, re, subprocess, time, urllib.request, urllib.parse, urllib.error
from pathlib import Path

HOST='https://api.xrtoken.ai'
OUT=Path('output/jianci-ep27-single-lin')
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
    assert os.environ.get('GITHUB_RUN_ATTEMPT','1')=='1'
    lin=get_video('75c2593e-12b3-4c09-836f-da13c4dd8f0d','lin-reference.mp4')
    lin_img=frame_data(lin,1,'300:320:130:0')
    prompt='''6 seconds. Detailed cinematic hand-drawn 2D ANIME, cool blue-gray police archive office. EXACTLY ONE visible adult: LIN QIAN, adult WOMAN with chin-length straight BLACK BOB, NAVY POLICE UNIFORM over plain dark shirt. Reference is FACE IDENTITY ONLY. Absolutely NO white coat, NO lab coat, NO second woman, NO man, NO glasses, NO silhouettes or faces in background, NO portraits on walls. Medium close-up, one stable camera, Lin centered. She holds one plain paper below chest level; document has NO visible writing. At 0.30 seconds Lin ON CAMERA speaks exactly in Mandarin, calmly and clearly: “这张死亡确认，是那个无名男性。” Finish the whole sentence by 4.30 seconds. Mouth follows only those audible words, then closes. Natural small eye movements, serious expression, no smile. No other dialogue, no subtitles, no captions, no music, no generated text, no scene change, no dissolves, no extra limbs. Single continuous shot with this same uniform and person.'''
    content=[{'type':'text','text':prompt},{'type':'image_url','image_url':{'url':lin_img},'role':'reference_image'}]
    r=api('/v1/videos/generations',{'model':'wan3.0-video','content':content,'duration':6,'resolution':'480P','ratio':'16:9','generate_audio':True,'watermark':False,'prompt_extend':False,'seed':906181})
    tid=r.get('id') or (r.get('data') or {}).get('id')
    assert isinstance(tid,str) and re.fullmatch(r'[A-Za-z0-9_.:-]+',tid)
    report={'task_id':tid,'state':r.get('status','queued'),'purpose':'EP27 final duplicated-Lin shot only','cost_guard':'single 6s targeted repair'}
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    deadline=time.monotonic()+2400
    while time.monotonic()<deadline:
        q=api('/v1/videos/generations/'+urllib.parse.quote(tid,safe=''))
        report['state']=q.get('status')
        (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if report['state']=='succeeded':
            url=q.get('video_url') or (q.get('content') or {}).get('video_url')
            assert url
            download(url,OUT/'lin-raw.mp4')
            subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','json',str(OUT/'lin-raw.mp4')],check=True,stdout=open(OUT/'ffprobe.json','wb'))
            print('EP27_SINGLE_LIN_READY',tid,flush=True)
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
