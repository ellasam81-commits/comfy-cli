"""One authorized retry of seven faulty shots, with dependent pose references."""
import base64,importlib.util,json,os,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('base',R/'generate.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base);shared=base.shared

def ref(p,t,crop=None):
 args=['ffmpeg','-nostdin','-v','error','-ss',str(t),'-i',str(p),'-frames:v','1']
 if crop:args+=['-vf',crop]
 b=subprocess.check_output(args+['-f','image2pipe','-vcodec','mjpeg','-q:v','3','-'])
 return 'data:image/jpeg;base64,'+base64.b64encode(b).decode()

def inspect(p):
 x=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)]));d=float(x['format']['duration']);assert 4.8<=d<=5.3
 assert any(s['codec_type']=='audio' for s in x['streams'])
 return {'duration':d,'audio_track':True,'qa':'pending'}

def main():
 assert os.environ.get('JIANCI_EP06_RETRY_EXECUTE')=='1'
 assert os.environ['GITHUB_REPOSITORY']=='ellasam81-commits/comfy-cli'
 assert int(os.environ.get('GITHUB_RUN_ATTEMPT','1'))==1,'No duplicate paid retry'
 cfg=json.loads((R/'retry.json').read_text());clips={c['id']:c for c in cfg['clips']};assert set(clips)=={'01','03','06','08','09','10','12'}
 src=Path('.runtime/ep6');out=Path('output/jianci-episode06-retry');out.mkdir(parents=True,exist_ok=True);assert not (out/'report.json').exists()
 refs={'radio':[ref(src/'01-raw.mp4',2.5,'crop=240:240:100:230')],'scene':[ref(src/'03-raw.mp4',0,'crop=832:240:0:240')],'seated':[ref(src/'06-raw.mp4',2.5)],'wood':[ref(src/'12-raw.mp4',4.5,'crop=120:240:40:40,scale=240:480')]}
 identity=ref(src/'06-raw.mp4',2.5,'crop=280:280:300:0')
 shared.inspect_video=inspect;g=shared.Gateway(os.environ.get('SEGMIND_API_KEY'))
 report={'episode':6,'retry_ids':list(clips),'estimated_usd':1.75,'clips':[]};shared.save_report(out,report)
 for ids in [['01','03','06','08','12'],['09'],['10']]:
  if ids==['09']:refs['standing']=[ref(out/'08-raw.mp4',4.7),identity]
  if ids==['10']:refs['chair']=[ref(out/'09-raw.mp4',4.7),identity]
  pending=[]
  for k in ids:
   c=clips[k];row={'id':k,'state':'SUBMITTING'};report['clips'].append(row);shared.save_report(out,report)
   result=g.request('/v2/wan3.0-video',{'prompt':c['prompt'],'reference_images':refs[c['role']],'duration':5,'resolution':'480P','aspect_ratio':'16:9','audio':True,'watermark':False,'prompt_extend':False,'enable_thinking':True,'seed':908607,'negative_prompt':'stairs, railing, extra dialogue, subtitles, changing clothes, repeated standing, teleportation, live action, 3D'})
   row.update(state='QUEUED',request_id=result['request_id']);pending.append(row);shared.save_report(out,report);print('Accepted retry',k,flush=True)
  deadline=time.monotonic()+1200
  while pending and time.monotonic()<deadline:
   for row in list(pending):
    path='/v2/requests/'+row['request_id'];status=g.request(path+'/status')['status'];row['state']=status
    if status=='FAILED':pending.remove(row)
    elif status=='COMPLETED':
     row['media']=shared.download_video(g.request(path),out/(row['id']+'-raw.mp4'));pending.remove(row);print('Downloaded retry',row['id'],flush=True)
    shared.save_report(out,report)
   if pending:time.sleep(5)
  if pending or any(x['state']!='COMPLETED' for x in report['clips']):raise RuntimeError('Retry stage incomplete; no additional retry')
 print('Seven replacements generated; no second retry.',flush=True)
if __name__=='__main__':main()
