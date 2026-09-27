"""Bounded 300-second XRToken generation. Never retry a paid POST."""
import argparse,base64,hashlib,json,os,re,subprocess,threading,time,urllib.request,urllib.error
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parent; OUT=Path('output/mengmeng-ep06-10'); HOST='https://api.xrtoken.ai';LOCK=threading.RLock()
def cmd(args):
 r=subprocess.run(args,capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stderr[-1800:])
 return r.stdout

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['pilot','rest'],required=True);ap.add_argument('--execute',action='store_true');a=ap.parse_args()
 raw=(ROOT/'episodes.json').read_bytes();cfg=json.loads(raw);digest=hashlib.sha256(raw).hexdigest()
 assert len(cfg['episodes'])==5 and all(len(e['clips'])==12 for e in cfg['episodes'])
 assert all((ROOT/c['reference']).is_file() for e in cfg['episodes'] for c in e['clips'])
 if not a.execute: print('VALID: 60 shots, 300 paid seconds max, five pilot shots, no paid retries');return
 if os.getenv('GITHUB_RUN_ATTEMPT','1')!='1':raise RuntimeError('Refuse blind paid rerun')
 OUT.mkdir(parents=True,exist_ok=True);report_path=OUT/'report.json';key=os.environ['XRTOKEN'].strip();assert key
 if a.stage=='pilot':
  assert not report_path.exists();report={'config_sha256':digest,'max_paid_seconds':300,'clips':[]}
 else:
  report=json.loads(report_path.read_text());assert report['config_sha256']==digest
  assert all(any(r['id']==e['clips'][0]['id'] and r['state']=='succeeded' for r in report['clips']) for e in cfg['episodes'])
 def save():
  with LOCK:
   tmp=OUT/'report.tmp';tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2));tmp.replace(report_path)
 def request(path,body=None):
  headers={'Authorization':'Bearer '+key,'Accept':'application/json'};data=None
  if body is not None:headers['Content-Type']='application/json';data=json.dumps(body,ensure_ascii=False).encode()
  with urllib.request.urlopen(urllib.request.Request(HOST+path,headers=headers,data=data),timeout=120) as r:return json.load(r)
 def error(e):
  s=e.read(1000).decode(errors='replace') if isinstance(e,urllib.error.HTTPError) else str(e)
  return {'type':type(e).__name__,'status':getattr(e,'code',None),'message':s[:1000].replace(key,'[REDACTED]')}
 save();request('/v1/videos/generations?limit=1')
 def episode(e):
  clips=e['clips'][:1] if a.stage=='pilot' else e['clips'][1:]
  for c in clips:
   cid=c['id'];previous=f"{e['episode']:02}_{c['shot']-1:02}"
   with LOCK:
    assert not any(r['id']==cid for r in report['clips'])
    row={'id':cid,'state':'SUBMITTING','duration':5};report['clips'].append(row);save()
   ref=ROOT/c['reference'] if c['shot']==1 else OUT/(previous+'-end.jpg');assert ref.is_file()
   payload={'model':cfg['model'],'duration':5,'resolution':'480P','ratio':'16:9','generate_audio':True,'watermark':False,'prompt_extend':False,'seed':928600+e['episode']*100+c['shot'],'content':[{'type':'text','text':c['prompt']},{'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(ref.read_bytes()).decode()},'role':'reference_image'}]}
   try:
    data=request('/v1/videos/generations',payload);task=data.get('id') or data.get('data',{}).get('id')
    if not isinstance(task,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]+',task):raise RuntimeError('Missing task id. Do not resubmit.')
    with LOCK:row.update(task_id=task,state=data.get('status','queued'));save()
    print('Accepted',cid,task,flush=True)
   except Exception as ex:
    with LOCK:row.update(state='SUBMISSION_UNKNOWN_OR_FAILED',error=error(ex));save()
    raise
   deadline=time.monotonic()+2400
   while time.monotonic()<deadline:
    try:
     data=request('/v1/videos/generations/'+task);state=data.get('status','unknown')
     with LOCK:row['state']=state;save()
     if state=='succeeded':
      content=data.get('content') or {};url=data.get('video_url') or content.get('video_url');assert url and url.startswith('https://')
      dst=OUT/(cid+'-raw.mp4')
      with urllib.request.urlopen(url,timeout=180) as r:dst.write_bytes(r.read())
      info=json.loads(cmd(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(dst)]));duration=float(info['format']['duration'])
      assert any(s['codec_type']=='audio' for s in info['streams'])
      for at,label in [(.7,'a'),(2.5,'b'),(duration-.12,'end')]:cmd(['ffmpeg','-y','-v','error','-ss',str(at),'-i',str(dst),'-frames:v','1',str(OUT/(cid+'-'+label+'.jpg'))])
      with LOCK:row.update(file=dst.name,actual_duration=duration,has_audio=True);save()
      print('Downloaded',cid,'audio=True',flush=True);break
     if state in {'failed','cancelled','expired'}:
      with LOCK:row['error']=str(data.get('error',''))[:1000].replace(key,'[REDACTED]');save()
      raise RuntimeError('Provider terminal failure '+cid)
    except urllib.error.HTTPError as ex:
     with LOCK:row['last_poll_error']=error(ex);save()
    time.sleep(15)
   else:raise RuntimeError('Polling timeout '+cid+'; task recorded; do not resubmit')
  return e['episode']
 errors=[]
 with ThreadPoolExecutor(max_workers=5) as pool:
  futures=[pool.submit(episode,e) for e in cfg['episodes']]
  for f in as_completed(futures):
   try:print('Episode phase complete',f.result(),flush=True)
   except Exception as ex:errors.append(error(ex));print('Episode phase failed',error(ex),flush=True)
 save()
 if errors:raise SystemExit(2)
 print('PHASE COMPLETE',a.stage,flush=True)
if __name__=='__main__':main()
