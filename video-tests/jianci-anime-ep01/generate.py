import importlib.util,json,os,re,time,urllib.request,subprocess
from pathlib import Path
ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('shared',ROOT.parent/'jianci-transition'/'run_test.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
def download(result,path):
 for u in s.output_urls(result):
  try:
   with urllib.request.urlopen(u,timeout=120) as r:data=r.read(70*1024*1024)
   if b'ftyp' not in data[:48]:continue
   path.write_bytes(data)
   info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))
   assert 4.5<float(info['format']['duration'])<5.6
   return {'duration':float(info['format']['duration']),'audio':any(x['codec_type']=='audio' for x in info['streams'])}
  except Exception:pass
 raise RuntimeError('No valid 5-second video found')
def main():
 cfg=json.loads((ROOT/'episode.json').read_text());assert len(cfg['clips'])==12
 if os.environ.get('JIANCI_ANIME_EP01_EXECUTE')!='1':print('12 x 5s, estimate USD3, no calls');return
 if os.environ.get('GITHUB_RUN_ATTEMPT','1')!='1':raise RuntimeError('No automatic rerun')
 out=Path('output/jianci-anime-ep01');out.mkdir(parents=True,exist_ok=True)
 if (out/'report.json').exists():raise RuntimeError('Existing request report')
 with urllib.request.urlopen('https://www.segmind.com/models/wan3.0-video/llms.txt',timeout=60) as r:docs=r.read().decode()
 (out/'wan3-docs.txt').write_text(docs)
 if not all(x in docs for x in ['480P','reference_images','duration']):raise RuntimeError('Review changed schema')
 gate=s.Gateway(os.environ.get('SEGMIND_API_KEY'));gate.request('/v1/get-user-credits')
 base='https://raw.githubusercontent.com/'+os.environ['GITHUB_REPOSITORY']+'/'+os.environ['GITHUB_SHA']+'/video-tests/jianci-anime-ep01/'
 report={'version':'2D anime remake v1','duration':60,'estimate_usd':3,'clips':[]};s.save_report(out,report);pending=[]
 for c in cfg['clips']:
  row={'id':c['id'],'state':'SUBMITTING'};report['clips'].append(row);s.save_report(out,report)
  try:
   result=gate.request('/v2/wan3.0-video',{'prompt':c['prompt'],'reference_images':[base+'cast.jpg',base+'room-body.jpg'],'duration':5,'resolution':'480P','aspect_ratio':'16:9','audio':True,'prompt_extend':False,'enable_thinking':True,'seed':911001,'negative_prompt':'3D CGI, photorealism, live action, stairs, subtitles, lettering, speech bubbles, split screen, labels, extra people, corpse moving, disappearing corpse, repeated head turns, repeated gestures, mask appearing on detective, laboratory, gore, camera shake'})
   rid=result['request_id'];assert re.fullmatch('[A-Za-z0-9_-]+',rid);row.update(state='QUEUED',request_id=rid);pending.append(row);print('Accepted',c['id'],rid,flush=True)
  except Exception as e:row.update(state='SUBMISSION_UNKNOWN_OR_FAILED',error=type(e).__name__);s.save_report(out,report);break
  s.save_report(out,report)
 deadline=time.monotonic()+1800
 while pending and time.monotonic()<deadline:
  for row in list(pending):
   try:
    path='/v2/requests/'+row['request_id'];state=gate.request(path+'/status')['status'];row['state']=state
    if state=='FAILED':pending.remove(row)
    elif state=='COMPLETED':row['media']=download(gate.request(path),out/(row['id']+'-raw.mp4'));pending.remove(row);print('Downloaded',row['id'],flush=True)
   except Exception as e:row['poll_error']=type(e).__name__
   s.save_report(out,report)
  if pending:time.sleep(8)
 for row in pending:row['state']='TIMEOUT_RETAIN_REQUEST_ID'
 s.save_report(out,report)
 if sum('media' in r for r in report['clips'])!=12:raise SystemExit(2)
if __name__=='__main__':main()
