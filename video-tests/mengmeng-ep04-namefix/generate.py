"""Four episodes, bounded paid submissions, resumable artifacts, no blind reruns."""
import argparse,base64,hashlib,json,os,re,subprocess,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).parent;OUT=Path('output/mengmeng-ep02-05');HOST='https://api.xrtoken.ai'
def cmd(args):
 r=subprocess.run(args,capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stderr[-1500:])
 return r.stdout
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--batch',required=True);ap.add_argument('--execute',action='store_true');a=ap.parse_args()
 raw=(ROOT/'episodes.json').read_bytes();cfg=json.loads(raw);clips=[c for e in cfg['episodes'] for c in e['clips']];lookup={c['id']:c for c in clips};digest=hashlib.sha256(raw).hexdigest()
 assert len(clips)==48 and sum(c['duration'] for c in clips)==240
 assert all((ROOT/c['reference']).is_file() for c in clips)
 if not a.execute:print('Dry-run: 48 shots, 240 seconds, 20-second pilot, no paid retries');return
 if os.environ.get('GITHUB_RUN_ATTEMPT','1')!='1':raise RuntimeError('Refuse blind paid rerun')
 OUT.mkdir(parents=True,exist_ok=True);report_path=OUT/'report.json'
 if a.batch=='pilot':
  if report_path.exists():raise RuntimeError('Pilot report already exists')
  report={'config_sha256':digest,'max_paid_seconds':5,'clips':[]}
 else:
  report=json.loads(report_path.read_text());assert report['config_sha256']==digest
  assert all(any(r['id']==i and r.get('state')=='succeeded' for r in report['clips']) for i in cfg['pilot_ids'])
 key=os.environ['XRTOKEN'].strip();assert key
 def save():
  tmp=OUT/'report.tmp';tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2));tmp.replace(report_path)
 def request(path,body=None):
  headers={'Authorization':'Bearer '+key,'Accept':'application/json'};data=None
  if body is not None:headers['Content-Type']='application/json';data=json.dumps(body,ensure_ascii=False).encode()
  with urllib.request.urlopen(urllib.request.Request(HOST+path,headers=headers,data=data),timeout=120) as r:return json.load(r)
 def error(e):
  return {'type':type(e).__name__,'status':getattr(e,'code',None),'message':(e.read(1000).decode(errors='replace') if isinstance(e,urllib.error.HTTPError) else str(e))[:1000].replace(key,'[REDACTED]')}
 done={r['id'] for r in report['clips'] if r.get('state')=='succeeded'};existing={r['id'] for r in report['clips']}
 def depth(i):return 1+max([depth(c['id']) for c in clips if c.get('previous_frame')==i] or [0])
 if a.batch=='pilot':selected=[lookup[i] for i in cfg['pilot_ids']]
 else:
  ready=[c for c in clips if c['id'] not in existing and (not c.get('previous_frame') or c['previous_frame'] in done)]
  selected=sorted(ready,key=lambda c:(-depth(c['id']),c['shot'],c['episode']))[:6]
 if not selected:
  if len(done)!=48:raise RuntimeError('No ready clips but incomplete generation')
  print('All 48 already generated; no paid requests');return
 print('Batch',a.batch,'selected',[c['id'] for c in selected],flush=True);save();request('/v1/videos/generations?limit=1')
 rows=[];submission_ok=True
 for c in selected:
  row={'id':c['id'],'batch':a.batch,'state':'SUBMITTING','duration':5};report['clips'].append(row);save()
  ref=OUT/(c['previous_frame']+'-end.jpg') if c.get('previous_frame') else ROOT/c['reference']
  assert ref.is_file()
  payload={'model':cfg['model'],'duration':5,'resolution':'480P','ratio':'16:9','generate_audio':True,'watermark':False,'prompt_extend':False,'seed':927990,'content':[{'type':'text','text':c['prompt']},{'type':'image_url','image_url':{'url':'data:image/jpeg;base64,'+base64.b64encode(ref.read_bytes()).decode()},'role':'reference_image'}]}
  try:
   data=request('/v1/videos/generations',payload);task=data.get('id') or data.get('data',{}).get('id')
   if not isinstance(task,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]+',task):raise RuntimeError('Missing task id; do not resubmit')
   row.update(task_id=task,state=data.get('status','queued'));rows.append(row);save();print('Accepted',c['id'],task,flush=True)
  except Exception as e:
   row.update(state='SUBMISSION_UNKNOWN_OR_FAILED',error=error(e));submission_ok=False;save();break
 pending=list(rows);deadline=time.monotonic()+2100
 while pending and time.monotonic()<deadline:
  for row in list(pending):
   try:
    data=request('/v1/videos/generations/'+row['task_id']);row['state']=data.get('status','unknown')
    if row['state']=='succeeded':
     content=data.get('content') or {};url=data.get('video_url') or content.get('video_url');assert url.startswith('https://')
     dst=OUT/(row['id']+'-raw.mp4')
     with urllib.request.urlopen(url,timeout=180) as r:dst.write_bytes(r.read())
     info=json.loads(cmd(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(dst)]))
     row.update(file=dst.name,video_url=url,actual_duration=float(info['format']['duration']),has_audio=any(s['codec_type']=='audio' for s in info['streams']))
     for at,label in [(.7,'a'),(2.5,'b'),(4.65,'end')]:cmd(['ffmpeg','-y','-v','error','-ss',str(at),'-i',str(dst),'-frames:v','1',str(OUT/(row['id']+'-'+label+'.jpg'))])
     pending.remove(row);print('Downloaded',row['id'],'audio',row['has_audio'],flush=True)
    elif row['state'] in {'failed','cancelled','expired'}:
     row['error']=str(data.get('error',''))[:1000].replace(key,'[REDACTED]');pending.remove(row)
   except Exception as e:row['last_poll_error']=error(e)
   save()
  if pending:time.sleep(15)
 save()
 if not submission_ok or any(not r.get('file') or not r.get('has_audio') for r in rows):raise SystemExit(2)
 print('Batch complete',a.batch,'total succeeded',sum(r.get('state')=='succeeded' for r in report['clips']),flush=True)
if __name__=='__main__':main()
