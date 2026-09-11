import importlib.util,json,os,re,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('shared',ROOT.parent/'jianci-transition/run_test.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)

def main():
 cfg=json.loads((ROOT/'episode.json').read_text());assert len(cfg['clips'])==6 and cfg['episode']==6
 if os.environ.get('JIANCI_EP06_EXECUTE')!='1':print('6 x10 seconds, USD3 base estimate; no API calls');return
 if os.environ.get('GITHUB_RUN_ATTEMPT','1')!='1':raise RuntimeError('No duplicate paid rerun')
 out=Path('output/jianci-ep06-evidence');out.mkdir(parents=True,exist_ok=True)
 if (out/'report.json').exists():raise RuntimeError('Existing report, refusing paid resubmission')
 with urllib.request.urlopen('https://www.segmind.com/models/wan3.0-video/llms.txt',timeout=60) as r:docs=r.read().decode()
 (out/'wan3-docs.txt').write_text(docs)
 assert all(k in docs for k in ['480P','reference_images','image','duration'])
 gate=s.Gateway(os.environ.get('SEGMIND_API_KEY'));gate.request('/v1/get-user-credits')
 base='https://raw.githubusercontent.com/'+os.environ['GITHUB_REPOSITORY']+'/'+'865bba9f85c3c0506b22831a13ebf26efa51dd89/video-tests/jianci-ep03-evidence/'
 report={'episode':6,'model':'wan3.0-video','estimate_usd':3,'mode':'six new episode6 scenes','clips':[]};s.save_report(out,report);pending=[]
 starts=['scene-01.jpg','scene-05.jpg','scene-01.jpg','scene-01.jpg','scene-05.jpg','scene-01.jpg']
 refs=[[],[],[],['scene-05.jpg'],['scene-05.jpg'],[]]
 for c in cfg['clips']:
  i=int(c['id'])-1
  row={'id':c['id'],'state':'SUBMITTING'};report['clips'].append(row);s.save_report(out,report)
  try:
   payload={'prompt':c['prompt'],'reference_images':[base+x for x in dict.fromkeys([starts[i]]+refs[i])],'duration':10,'resolution':'480P','aspect_ratio':'16:9','audio':True,'watermark':False,'prompt_extend':False,'enable_thinking':True,'seed':906121,'negative_prompt':'photorealism, live action, CGI, subtitles, text, writing, split-screen, extra limbs, stairs inside apartment, teleportation, disappearing person, repeated gestures, repeated lines, gore, zombie, mask on detective'}
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

