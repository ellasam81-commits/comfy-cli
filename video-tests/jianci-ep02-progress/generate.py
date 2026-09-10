import importlib.util,json,os,re,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('shared',ROOT.parent/'jianci-transition/run_test.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)

import urllib.error

def diagnose(gate,out):
 old={'episode': 2, 'model': 'wan3.0-video', 'estimate_usd': 3, 'clips': [{'id': '01', 'state': 'FAILED', 'request_id': 'f2967d4cb5687290074c109f5a105ae0'}, {'id': '02', 'state': 'FAILED', 'request_id': 'd49f784e8c5ec03f242cd4c0fb989dd7'}, {'id': '03', 'state': 'FAILED', 'request_id': '887ec96294dafb7f0bffdb1a4c68a016'}, {'id': '04', 'state': 'FAILED', 'request_id': '4fd7150672e023cf440cc90ccbd8e641'}, {'id': '05', 'state': 'FAILED', 'request_id': '520e013636588a202747e721de50879a'}, {'id': '06', 'state': 'FAILED', 'request_id': '501979d545b11033aead8e9755743ed2'}]}
 evidence=[]
 for row in old['clips']:
  url=s.API+'/v2/requests/'+row['request_id']+'/status'
  req=urllib.request.Request(url,headers={'x-api-key':gate.key,'Content-Type':'application/json'})
  try:
   with gate.opener.open(req,timeout=60) as response:
    code=response.status;body=response.read(16000).decode('utf-8','replace')
  except urllib.error.HTTPError as e:code=e.code;body=e.read(16000).decode('utf-8','replace')
  safe=body.replace(gate.key,'[REDACTED]')
  evidence.append({'id':row['id'],'http':code,'body':safe})
 (out/'diagnosis.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
 print('Prior request diagnostic:',json.dumps(evidence[0],ensure_ascii=False),flush=True)
 # Only recover a confirmed incompatible-input-mode validation failure.
 text=' '.join(x['body'].lower() for x in evidence)
 conflict=('image' in text and ('reference' in text or 'first' in text) and any(k in text for k in ['cannot','mutually','either','not support','not allowed','exclusive','only one']))
 if not all(x['http']==422 or 'failed' in x['body'].lower() for x in evidence) or not conflict:
  print('Unrecognized failure; no new paid submissions.',flush=True);raise SystemExit(2)
 print('Confirmed incompatible image/reference mode; one recovery per failed clip, references only.',flush=True)

def main():
 cfg=json.loads((ROOT/'episode.json').read_text());assert len(cfg['clips'])==6 and cfg['episode']==2
 if os.environ.get('JIANCI_EP02_PROGRESS_EXECUTE')!='1':print('6 x10 seconds, USD3 base estimate; no API calls');return
 if os.environ.get('GITHUB_RUN_ATTEMPT','1')!='1':raise RuntimeError('No duplicate paid rerun')
 out=Path('output/jianci-ep02-progress');out.mkdir(parents=True,exist_ok=True)
 if (out/'report.json').exists():raise RuntimeError('Existing report, refusing paid resubmission')
 with urllib.request.urlopen('https://www.segmind.com/models/wan3.0-video/llms.txt',timeout=60) as r:docs=r.read().decode()
 (out/'wan3-docs.txt').write_text(docs)
 assert all(k in docs for k in ['480P','reference_images','image','duration'])
 gate=s.Gateway(os.environ.get('SEGMIND_API_KEY'));gate.request('/v1/get-user-credits');diagnose(gate,out)
 base='https://raw.githubusercontent.com/'+os.environ['GITHUB_REPOSITORY']+'/'+os.environ['GITHUB_SHA']+'/video-tests/jianci-ep02-progress/'
 report={'episode':2,'model':'wan3.0-video','estimate_usd':3,'mode':'single recovery after diagnosed input conflict','clips':[]};s.save_report(out,report);pending=[]
 starts=['opening.jpg','scene-02.jpg','scene-03.jpg','scene-03.jpg','scene-05.jpg','scene-06.jpg']
 refs=[['scene-01.jpg'],['scene-02.jpg'],['scene-02.jpg'],['scene-04.jpg'],['scene-05.jpg'],['scene-06.jpg']]
 for i,c in enumerate(cfg['clips']):
  row={'id':c['id'],'state':'SUBMITTING'};report['clips'].append(row);s.save_report(out,report)
  try:
   payload={'prompt':c['prompt'],'reference_images':[base+x for x in dict.fromkeys([starts[i]]+refs[i])],'duration':10,'resolution':'480P','aspect_ratio':'16:9','audio':True,'watermark':False,'prompt_extend':False,'enable_thinking':True,'seed':906101,'negative_prompt':'photorealism, live action, CGI, subtitles, text, writing, split-screen, extra limbs, stairs inside apartment, teleportation, disappearing person, repeated gestures, repeated lines, gore, zombie, mask on detective, office'}
   res=gate.request('/v2/wan3.0-video',payload);rid=res['request_id'];assert re.fullmatch('[A-Za-z0-9_-]+',rid);row.update(state='QUEUED',request_id=rid);pending.append(row);print('Accepted',c['id'],flush=True)
  except Exception as e:row.update(state='SUBMISSION_UNKNOWN_OR_FAILED',error=type(e).__name__);s.save_report(out,report);break
  s.save_report(out,report)
 deadline=time.monotonic()+1800
 while pending and time.monotonic()<deadline:
  for row in list(pending):
   try:
    path='/v2/requests/'+row['request_id'];row['state']=gate.request(path+'/status')['status']
    if row['state']=='FAILED':pending.remove(row)
    elif row['state']=='COMPLETED':row['media']=s.download_video(gate.request(path),out/(row['id']+'-raw.mp4'));pending.remove(row);print('Downloaded',row['id'],flush=True)
   except Exception as e:row['last_poll_error']=type(e).__name__
   s.save_report(out,report)
  if pending:time.sleep(8)
 for row in pending:row['state']='TIMEOUT_RETAIN_REQUEST_ID'
 s.save_report(out,report)
 if sum('media' in c for c in report['clips'])!=6:raise SystemExit(2)
if __name__=='__main__':main()
