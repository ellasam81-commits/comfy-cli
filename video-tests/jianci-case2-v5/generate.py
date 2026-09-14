import base64,json,os,re,subprocess,time,urllib.request,urllib.parse,urllib.error
from pathlib import Path
ROOT=Path(__file__).parent
EP=int(os.environ.get('EPISODE','14'))
CFG=json.loads((ROOT/os.environ.get('CONFIG_FILE',f'episode{EP}.json')).read_text())
OUT=Path(f'output/jianci-case2-v5/ep{EP}'+os.environ.get('BATCH',''))
HOST='https://api.xrtoken.ai'
def main():
 assert CFG['resolution']=='480P' and sum(c['duration'] for c in CFG['clips'])<=CFG['max_output_seconds']
 assert len(set(c['id'] for c in CFG['clips']))==len(CFG['clips'])
 if os.environ.get('JIANCI_EXECUTE')!='1':
  print('DRY RUN',EP,len(CFG['clips']),CFG['max_output_seconds'],CFG['estimate_usd']);return
 assert os.environ.get('GITHUB_RUN_ATTEMPT','1')=='1','Refuse duplicate paid workflow rerun'
 key=os.environ['XRTOKEN'].strip();assert key
 OUT.mkdir(parents=True,exist_ok=True);assert not (OUT/'report.json').exists()
 report={'episode':EP,'estimate_usd':CFG['estimate_usd'],'clips':[]}
 def save():
  p=OUT/'report.tmp';p.write_text(json.dumps(report,ensure_ascii=False,indent=2));p.replace(OUT/'report.json')
 def api(path,body=None):
  data=None if body is None else json.dumps(body,ensure_ascii=False).encode()
  req=urllib.request.Request(HOST+path,data=data,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=90) as f:return json.load(f)
 def error(e):
  if isinstance(e,urllib.error.HTTPError):return str(e.code)+' '+e.read(1500).decode(errors='replace').replace(key,'[REDACTED]')
  return type(e).__name__
 def download(url,path):
  assert urllib.parse.urlparse(url).scheme=='https'
  with urllib.request.urlopen(url,timeout=120) as f:path.write_bytes(f.read())
 def getvideo(task,dest):
  r=api('/v1/videos/generations/'+urllib.parse.quote(task,safe=''));assert r.get('status')=='succeeded','Known reference not available'
  url=r.get('video_url') or (r.get('content') or {}).get('video_url');download(url,dest)
 def frame(src,t,crop=None):
  dst=src.with_suffix('.jpg');args=['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(src),'-frames:v','1']
  if crop:args+=['-vf','crop='+crop]
  subprocess.run(args+[str(dst)],check=True)
  return 'data:image/jpeg;base64,'+base64.b64encode(dst.read_bytes()).decode()
 refs={}
 for name,ref in CFG['known_refs'].items():
  if 'url' in ref:refs[name]=ref['url']
  else:
   dest=OUT/(name+'-reference.mp4');getvideo(ref['task_id'],dest);refs[name]=frame(dest,ref['seconds'],ref.get('crop'));dest.unlink();dest.with_suffix('.jpg').unlink()
 save()
 def submit(c):
  content=[{'type':'text','text':c['prompt']}]
  for ref in c['refs']:
   if ref.startswith('clip:'):im=frame(OUT/(ref[5:]+'-raw.mp4'),2)
   else:im=refs[ref]
   content.append({'type':'image_url','image_url':{'url':im},'role':'reference_image'})
  row={'id':c['id'],'state':'SUBMITTING','duration':c['duration']};report['clips'].append(row);save()
  try:
   r=api('/v1/videos/generations',{'model':CFG['model'],'content':content,'duration':c['duration'],'resolution':'480P','ratio':'16:9','generate_audio':True,'watermark':False,'prompt_extend':False,'seed':906181})
   tid=r.get('id') or (r.get('data') or {}).get('id');assert isinstance(tid,str) and re.fullmatch(r'[A-Za-z0-9_.:-]+',tid)
   row.update(task_id=tid,state=r.get('status','queued'));print('ACCEPTED',c['id'],tid,flush=True)
  except Exception as e:
   row.update(state='SUBMISSION_UNKNOWN_OR_FAILED',error=error(e));save();raise RuntimeError('Submission stopped; preserve ID state, never auto retry')
  save()
 def poll(rows):
  pending=list(rows);deadline=time.monotonic()+2100
  while pending and time.monotonic()<deadline:
   for row in list(pending):
    try:
     r=api('/v1/videos/generations/'+urllib.parse.quote(row['task_id'],safe=''));row['state']=r.get('status')
     if row['state']=='succeeded':
      url=r.get('video_url') or (r.get('content') or {}).get('video_url');dest=OUT/(row['id']+'-raw.mp4');download(url,dest);row['file']=dest.name;pending.remove(row);print('DOWNLOADED',row['id'],flush=True)
     elif row['state'] in ['failed','cancelled','expired']:
      row['error']=str(r.get('error',''))[:1500].replace(key,'[REDACTED]');pending.remove(row);print('FAILED',row['id'],flush=True)
    except Exception as e:row['poll_error']=error(e)
    save()
   if pending:time.sleep(12)
  for row in pending:row['state']='TIMEOUT_RETAIN_TASK_ID'
  save()
 initial=[c for c in CFG['clips'] if not any(r.startswith('clip:') for r in c['refs'])]
 follow=[c for c in CFG['clips'] if c not in initial]
 for c in initial:submit(c)
 poll(report['clips'])
 for c in follow:
  if all(not r.startswith('clip:') or (OUT/(r[5:]+'-raw.mp4')).exists() for r in c['refs']):submit(c)
  else:report['clips'].append({'id':c['id'],'state':'DEPENDENCY_FAILED_NOT_SUBMITTED'});save()
 new=[r for r in report['clips'] if r.get('task_id') and not r.get('file') and r.get('state') not in ['failed','cancelled','expired','TIMEOUT_RETAIN_TASK_ID']]
 if new:poll(new)
 if not all(r.get('file') for r in report['clips']):raise SystemExit(2)
 print('ALL_RAW_READY_REVIEW_REQUIRED',flush=True)
if __name__=='__main__':main()
