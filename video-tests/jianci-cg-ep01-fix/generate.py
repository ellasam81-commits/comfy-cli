import importlib.util,json,os,re,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('shared',ROOT.parent/'jianci-transition'/'run_test.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
def main():
 cfg=json.loads((ROOT/'episode.json').read_text());assert len(cfg['clips'])==3
 if os.environ.get('JIANCI_CG_EP01_FIX_EXECUTE')!='1': print('Validated six 10-second clips, 480P, estimate USD3; no API calls.');return
 if os.environ.get('GITHUB_RUN_ATTEMPT','1')!='1':raise RuntimeError('No automatic rerun allowed')
 out=Path('output/jianci-cg-ep01-fix');out.mkdir(parents=True,exist_ok=True)
 if (out/'report.json').exists():raise RuntimeError('Existing report: no duplicate submissions')
 # Save current public provider specification for parameter/pricing review; does not expose credentials.
 with urllib.request.urlopen('https://www.segmind.com/models/wan3.0-video/llms.txt',timeout=60) as r: docs=r.read().decode()
 (out/'wan3-docs.txt').write_text(docs)
 if not all(x in docs for x in ['reference_images','480P','duration']):raise RuntimeError('Provider schema changed; review before submitting')
 gate=s.Gateway(os.environ.get('SEGMIND_API_KEY'));gate.request('/v1/get-user-credits')
 base='https://raw.githubusercontent.com/'+os.environ['GITHUB_REPOSITORY']+'/'+'698539ce99a22d2758834005a916026042c889a8/video-tests/jianci-cg-ep01/'
 report={'episode':1,'version':'CG v1 targeted repair; clips01,04,06; attempt2 final','model':'wan3.0-video','estimated_usd':1.5,'actual_billing':'provider history','clips':[]};s.save_report(out,report)
 pending=[]
 for clip in cfg['clips']:
  row={'id':clip['id'],'state':'SUBMITTING'};report['clips'].append(row);s.save_report(out,report)
  try:
   result=gate.request('/v2/wan3.0-video',{'prompt':clip['prompt'],'reference_images':[base+'cast.jpg',base+'room.jpg',base+'jianci-approved.jpg'],'duration':10,'resolution':'480P','aspect_ratio':'16:9','audio':True,'prompt_extend':False,'enable_thinking':True,'seed':910602,'negative_prompt':'stairs, staircase, split screen, contact sheet, labels, text, captions, live action, flat 2D outlines, chibi, glowing eyes, exaggerated gore, repeated turning, repeated speech, additional dialogue, music, opaque black scene'})
   rid=result['request_id'];assert re.fullmatch('[A-Za-z0-9_-]+',rid)
   row.update(state='QUEUED',request_id=rid);pending.append(row);print('Accepted clip',clip['id'],rid,flush=True)
  except Exception as exc:
   row.update(state='SUBMISSION_UNKNOWN_OR_FAILED',error_type=type(exc).__name__);s.save_report(out,report);break
  s.save_report(out,report)
 deadline=time.monotonic()+1800
 while pending and time.monotonic()<deadline:
  for row in list(pending):
   try:
    path='/v2/requests/'+row['request_id'];status=gate.request(path+'/status')['status'];row['state']=status
    if status=='FAILED':pending.remove(row)
    elif status=='COMPLETED':
     result=gate.request(path);row['media']=s.download_video(result,out/(row['id']+'-raw.mp4'));pending.remove(row);print('Downloaded',row['id'],flush=True)
   except Exception as exc:row['poll_error_type']=type(exc).__name__
   s.save_report(out,report)
  if pending:time.sleep(8)
 for row in pending:row['state']='TIMEOUT_RETAIN_REQUEST_ID'
 s.save_report(out,report)
 if sum('media' in x for x in report['clips'])!=3:raise SystemExit(2)
if __name__=='__main__':main()
