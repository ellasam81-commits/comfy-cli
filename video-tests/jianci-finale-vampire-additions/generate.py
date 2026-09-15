import base64, json, os, re, subprocess, time, urllib.request, urllib.parse, urllib.error
from pathlib import Path

HOST='https://api.xrtoken.ai'
OUT=Path('output/jianci-finale-vampire-additions')
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


import concurrent.futures
BEATS=[{"ep":25,"zh":"铃一出现，牙就开始疼。先别拿近。","en":"Whenever that bell appears, my teeth ache. Keep it away.","prompt":"He looks toward the copper-bell photocopy held OFF SCREEN at lower left. At 0.5s his iris rims turn clearly dark red. He briefly parts his lips showing two short upper canine tips, then closes his mouth and moves one measured step back, hands empty at his sides. At 2.0s he says: “铃一出现，牙就开始疼。先别拿近。” Finish by 6.8s. Hold controlled red eyes, exhale, never move toward the unseen person."},{"ep":26,"zh":"不是这里有血，是记忆里的味道。","en":"There is no blood here. The scent is in my memory.","prompt":"After seeing the old bell photograph, he stops breathing for a moment and closes his eyes. He opens them with clearly red irises at 1.3s, looks toward Zhou OFF SCREEN LEFT, jaw tense, normal closed teeth. At 2.0s he says: “不是这里有血，是记忆里的味道。” Finish by 6.5s. Then his red irises gradually fade back to dark gray by 7.7s. He remains outside the archive threshold; no paper handling."},{"ep":27,"zh":"她把我藏起来时，我的牙也是这样。","en":"My teeth were like this when she hid me.","prompt":"After hearing the name Shen Anning, he grips his own sleeve below chest level. At 0.7s his irises redden clearly and his two upper canine tips become visible as he takes a slow breath. He holds himself still instead of approaching anyone. At 2s he quietly tells Lin OFF SCREEN LEFT: “她把我藏起来时，我的牙也是这样。” Finish by 6.8s. At end mouth closes, eyes remain red, hands release his own sleeve. No historical insert."},{"ep":28,"zh":"那次醒来以后，饥饿就一直跟着我。","en":"Since I woke that time, the hunger has never left me.","prompt":"After recalling waking in the metal drawer, he looks up toward Zhou OFF SCREEN LEFT. His red iris coloration is unmistakable; two small upper canine tips appear when his lips part, but no snarling. At 1.4s he explains: “那次醒来以后，饥饿就一直跟着我。” Finish by 6.5s. He swallows, looks down, clenches then relaxes an empty hand, keeping his body still. Cool archive wall only."},{"ep":29,"zh":"许医生，先别靠近。等我压下去。","en":"Doctor Xu, keep your distance. Let me get it under control.","prompt":"Medical consultation room outside lab evidence area. Jian is seated alone, clean empty hands on his own knees. Before a mouth swab is taken, his iris rims redden and two small upper canine tips briefly show at 0.8s. At 1.8s he warns Dr Xu OFF SCREEN LEFT: “许医生，先别靠近。等我压下去。” Finish by 5.7s. Close his mouth, take two slow controlled breaths, and return eyes to normal dark gray by 7.5s. No swab, no medical tools, no other hands enter this shot."},{"ep":30,"zh":"你们都看见了。我没好，只是能停下。","en":"You've all seen it. I'm not cured. I can stop myself now.","prompt":"In the night archive corridor, Jian looks toward Han and Zhou OFF SCREEN LEFT after earlier image is mentioned. His irises turn clearly red for 1 second and small upper canine tips briefly show; he consciously closes his mouth, loosens tense shoulders and steps back half a step. At 2s he says calmly: “你们都看见了。我没好，只是能停下。” Finish by 6.8s. Eyes return to normal dark gray before the end, hold wary expression. No text, no end card."}]
COMMON="8 seconds. Cinematic hand-drawn 2D ANIME, cool blue-gray police archive corridor, realistic adult proportions. Present-day JIAN CI adult male pale skin, short tousled black hair, BLACK TURTLENECK under DARK CHARCOAL-GRAY CASUAL JACKET, no glasses, no lab coat, no uniform, no gloves. Reference image locks his face only. EXACTLY ONE visible person, Jian alone in a medium close-up; all colleagues stay OFF CAMERA. No additional faces, portraits or reflections. One steady shot, no cuts, no costume or face changes. Non-graphic supernatural suspense: natural red iris coloration and small upper vampire canine tips, NOT a monster mouth, no wounds, no blood, no attack. Mandarin voice precisely follows the quoted sentence, no extra words, no captions, no written text, no music. "
def run_one(b, ref):
    ep=str(b['ep'])
    content=[{'type':'text','text':COMMON+b['prompt']},{'type':'image_url','image_url':{'url':ref},'role':'reference_image'}]
    r=api('/v1/videos/generations',{'model':'wan3.0-video','content':content,'duration':8,'resolution':'480P','ratio':'16:9','generate_audio':True,'watermark':False,'prompt_extend':False,'seed':906181+b['ep']})
    tid=r.get('id') or (r.get('data') or {}).get('id')
    assert isinstance(tid,str) and re.fullmatch(r'[A-Za-z0-9_.:-]+',tid)
    report={'episode':b['ep'],'task_id':tid,'state':r.get('status','queued'),'zh':b['zh'],'en':b['en'],'max_submissions':1}
    rp=OUT/(ep+'-report.json')
    rp.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    deadline=time.monotonic()+2400
    while time.monotonic()<deadline:
        q=api('/v1/videos/generations/'+urllib.parse.quote(tid,safe=''))
        report['state']=q.get('status')
        rp.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        if report['state']=='succeeded':
            download(q.get('video_url') or (q.get('content') or {}).get('video_url'),OUT/(ep+'-raw.mp4'))
            return
        if report['state'] in ('failed','cancelled','expired'):
            report['error']=str(q.get('error',''))[:1000]
            rp.write_text(json.dumps(report,ensure_ascii=False,indent=2))
            return
        time.sleep(12)
    report['state']='TIMEOUT_RETAIN_TASK_ID'
    rp.write_text(json.dumps(report,ensure_ascii=False,indent=2))

def main():
    assert os.environ.get('JIANCI_EXECUTE')=='1'
    assert os.environ.get('GITHUB_RUN_ATTEMPT','1')=='1'
    jian=get_video('266e6ebd-0a4d-408c-ae66-6b82077aa055','jian-reference.mp4')
    ref=frame_data(jian,2,'400:320:230:0')
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        jobs=[pool.submit(run_one,b,ref) for b in BEATS]
        for f in concurrent.futures.as_completed(jobs):f.result()
if __name__=='__main__':main()
