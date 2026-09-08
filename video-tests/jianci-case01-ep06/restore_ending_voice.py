import os,json,time,base64,subprocess,urllib.request,re,importlib.util
from pathlib import Path
assert os.environ.get('GITHUB_RUN_ATTEMPT','1')=='1','No automatic paid rerun'
out=Path('voice-output');out.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('shared','video-tests/jianci-transition/run_test.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
ref=subprocess.check_output(['ffmpeg','-v','error','-ss','0.9','-i','clips/07-raw.mp4','-t','3.6','-vn','-ac','1','-ar','24000','-af','highpass=f=70','-f','wav','-'])
payload={'text_prompt':'Use the same male voice identity and calm restrained delivery as @Audio1. This is an original fictional forensic doctor. Speak ONLY the following Mandarin Chinese line once, naturally in about 3 seconds: 林浅，先拍照，别碰它。 Clean dry close-miked spoken dialogue. No music, no sound effects, no introduction, no reference dialogue.','reference_audio_urls':['data:audio/wav;base64,'+base64.b64encode(ref).decode()],'format':'wav','sample_rate':48000}
g=s.Gateway(os.environ.get('SEGMIND_API_KEY'))
report={'model':'seed-audio-1.0','line':'林浅，先拍照，别碰它。','state':'SUBMITTING','reference':'AI-generated fictional doctor, episode 6 shot 07','requests':1}
def save(): (out/'voice-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
save()
job=g.request('/v2/seed-audio-1.0',payload);rid=job['request_id'];assert re.fullmatch(r'[A-Za-z0-9_-]+',rid)
report.update(request_id=rid,state='QUEUED');save()
for _ in range(120):
 state=g.request('/v2/requests/'+rid+'/status')['status'];report['state']=state;save()
 if state=='FAILED':raise RuntimeError('Audio generation failed; no retry')
 if state=='COMPLETED':break
 time.sleep(3)
else:raise RuntimeError('Timed out; retain request id, do not resubmit')
result=g.request('/v2/requests/'+rid)
def urls(x):
 if isinstance(x,str) and x.startswith('https://'):yield x
 elif isinstance(x,list):
  for y in x:yield from urls(y)
 elif isinstance(x,dict):
  for k,y in x.items():
   if k not in ['status_url','response_url']:yield from urls(y)
for url in urls(result.get('output',result)):
 try:
  with urllib.request.urlopen(url,timeout=90) as response:data=response.read(15*1024*1024)
  p=out/'voice.wav';p.write_bytes(data)
  probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(p)]))
  if not any(v['codec_type']=='audio' for v in probe['streams']):continue
  report['duration']=float(probe['format']['duration']);report['estimated_usd']=round(report['duration']*.003125,5);save();break
 except Exception:continue
else:raise RuntimeError('No playable output audio')
from faster_whisper import WhisperModel
m=WhisperModel('medium',device='cpu',compute_type='int8',cpu_threads=4)
segments,info=m.transcribe(str(p),language='zh',beam_size=5,word_timestamps=True,vad_filter=False,condition_on_previous_text=False)
asr=[{'start':x.start,'end':x.end,'text':x.text,'words':[{'start':w.start,'end':w.end,'word':w.word} for w in x.words]} for x in segments]
(out/'transcription.json').write_text(json.dumps(asr,ensure_ascii=False,indent=2))
print(json.dumps({'duration':report['duration'],'asr':asr},ensure_ascii=False))
