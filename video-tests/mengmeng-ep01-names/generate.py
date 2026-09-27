"""EP01 remake, scene-specific clean references and recoverable paid jobs."""
import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT=Path(__file__).parent
OUT=Path('output/mengmeng-ep01-names')
HOST='https://api.xrtoken.ai'

def command(args):
    r=subprocess.run(args,capture_output=True,text=True)
    if r.returncode:
        raise RuntimeError(r.stderr[-1500:])
    return r.stdout

def probe(path):
    return json.loads(command(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--phase',choices=['pilot','remaining'],required=True);ap.add_argument('--execute',action='store_true');args=ap.parse_args()
    raw=(ROOT/'episode.json').read_bytes();cfg=json.loads(raw);digest=hashlib.sha256(raw).hexdigest()
    assert len(cfg['clips'])==3 and sum(c['duration'] for c in cfg['clips'])==15
    assert cfg['model']=='wan3.0-video' and cfg['resolution']=='480P'
    assert all((ROOT/c['reference']).is_file() for c in cfg['clips'])
    if not args.execute:
        print('Dry run OK: 15 seconds total, three identity dialogue shots, no paid retries.');return
    if os.environ.get('GITHUB_RUN_ATTEMPT','1')!='1':raise RuntimeError('No blind paid workflow reruns.')
    OUT.mkdir(parents=True,exist_ok=True)
    if args.phase=='pilot':
        if (OUT/'report.json').exists():raise RuntimeError('Existing pilot report, refuse duplicate.')
        report={'revision':3,'config_sha256':digest,'model':cfg['model'],'max_paid_seconds':15,'clips':[]}
    else:
        report=json.loads((OUT/'report.json').read_text())
        if report['config_sha256']!=digest:raise RuntimeError('Config changed after pilot.')
        assert {x['id'] for x in report['clips']}=={'01','09'}
        assert all(x['state']=='succeeded' and (OUT/x['file']).is_file() for x in report['clips'])
    key=os.environ['XRTOKEN'].strip()
    if not key:raise RuntimeError('Missing XRTOKEN')
    def save():
        temp=OUT/'report.tmp';temp.write_text(json.dumps(report,ensure_ascii=False,indent=2));temp.replace(OUT/'report.json')
    def request(path,body=None):
        headers={'Authorization':'Bearer '+key,'Accept':'application/json'};data=None
        if body is not None:data=json.dumps(body,ensure_ascii=False).encode();headers['Content-Type']='application/json'
        with urllib.request.urlopen(urllib.request.Request(HOST+path,data=data,headers=headers),timeout=120) as r:return json.load(r)
    def err(exc):
        x={'type':type(exc).__name__}
        if isinstance(exc,urllib.error.HTTPError):x.update(http_status=exc.code,message=exc.read(1500).decode(errors='replace').replace(key,'[REDACTED]'))
        return x
    def reference(c):
        if c.get('previous_frame'):
            ref=OUT/(c['previous_frame']+'-end.jpg')
            if not ref.is_file():raise RuntimeError('Missing predecessor frame')
        else:ref=ROOT/c['reference']
        return 'data:image/jpeg;base64,'+base64.b64encode(ref.read_bytes()).decode()
    def submit(c):
        if any(x['id']==c['id'] for x in report['clips']):raise RuntimeError('Duplicate clip ID refused')
        ref=reference(c)
        row={'id':c['id'],'state':'SUBMITTING','duration':5};report['clips'].append(row);save()
        body={'model':cfg['model'],'content':[{'type':'text','text':c['prompt']},{'type':'image_url','image_url':{'url':ref},'role':'reference_image'}],'duration':5,'resolution':'480P','ratio':'16:9','generate_audio':True,'watermark':False,'prompt_extend':False,'seed':927307}
        try:
            data=request('/v1/videos/generations',body);task=data.get('id') or data.get('data',{}).get('id')
            if not isinstance(task,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]+',task):raise RuntimeError('No task ID; do not resubmit')
            row.update(task_id=task,state=data.get('status','queued'));save();print('Accepted',c['id'],task,flush=True);return row
        except Exception as exc:
            row.update(state='SUBMISSION_UNKNOWN_OR_FAILED',error=err(exc));save();print(json.dumps(row,ensure_ascii=False),flush=True);return None
    def poll(rows):
        pending=list(rows);deadline=time.monotonic()+2100
        while pending and time.monotonic()<deadline:
            for row in list(pending):
                try:
                    data=request('/v1/videos/generations/'+urllib.parse.quote(row['task_id'],safe=''));row['state']=data.get('status','unknown')
                    if row['state']=='succeeded':
                        content=data.get('content') or {};url=data.get('video_url') or (content.get('video_url') if isinstance(content,dict) else None)
                        if not url or urllib.parse.urlparse(url).scheme!='https':raise RuntimeError('Missing HTTPS result')
                        row['video_url']=url;dest=OUT/(row['id']+'-raw.mp4')
                        with urllib.request.urlopen(url,timeout=180) as media:dest.write_bytes(media.read())
                        row['file']=dest.name
                        info=probe(dest);row['actual_duration']=float(info['format']['duration']);row['has_audio']=any(s['codec_type']=='audio' for s in info['streams'])
                        for at,label in [(.7,'a'),(2.5,'b'),(4.65,'end')]:command(['ffmpeg','-v','error','-y','-ss',str(at),'-i',str(dest),'-frames:v','1',str(OUT/(row['id']+'-'+label+'.jpg'))])
                        pending.remove(row);print('Downloaded',row['id'],'duration',row['actual_duration'],'audio',row['has_audio'],flush=True)
                    elif row['state'] in {'failed','cancelled','expired'}:
                        row['error']=str(data.get('error',''))[:1500].replace(key,'[REDACTED]');pending.remove(row);print('Failed',row['id'],row['error'],flush=True)
                except Exception as exc:row['last_poll_error']=err(exc)
                save()
            if pending:time.sleep(15)
        save();return all(x.get('file') and x.get('has_audio') for x in rows)
    save()
    try:request('/v1/videos/generations?limit=1')
    except Exception as exc:report['preflight_error']=err(exc);save();raise SystemExit(2)
    batches=[['01','02b','03']]
    for batch in batches:
        accepted=[];ok=True
        for id in batch:
            row=submit(next(c for c in cfg['clips'] if c['id']==id))
            if row is None:ok=False;break
            accepted.append(row)
        done=poll(accepted)
        if not ok or not done:raise SystemExit(2)
    report['phase_completed']=args.phase;save();print('Phase complete:',args.phase,flush=True)

if __name__=='__main__':main()
