import os,json,time,base64,subprocess,urllib.request,re,importlib.util
from pathlib import Path
assert os.environ.get('GITHUB_RUN_ATTEMPT','1')=='1','No automatic paid rerun'
out=Path('voice-output');out.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('shared','video-tests/jianci-transition/run_test.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
payload={'text':'用克制、低沉、自然的成年男声，说一句悬疑剧里的现场对白。语气警觉但不喊叫，在三秒左右说完。只读下面的台词，不读说明和角色名，不加音乐：林浅，先拍照，别碰它。','voice_1':'Charon','temperature':0.4}

g=s.Gateway(os.environ.get('SEGMIND_API_KEY'))
# Diagnose failed reference-voice service before selecting the non-cloning fallback.
req=urllib.request.Request('https://api.segmind.com/v2/requests/c8347f01a13e53ebbc07adae8cd15db8',headers={'x-api-key':os.environ['SEGMIND_API_KEY']})
try:
 with g.opener.open(req,timeout=30) as response:detail=response.read().decode()
except urllib.error.HTTPError as exc:detail=exc.read().decode()
safe=re.sub(r'data:[^" ]+','[reference omitted]',detail)
safe=re.sub(r'https?[^" ]+','[url omitted]',safe)
(out/'openvoice-failure-detail.txt').write_text(safe[:3000])
print(safe[:1000])
if any(w in detail.lower() for w in ['safety','moderation','policy','rai','content blocked']):raise RuntimeError('Safety-related failure; stopping')
if not any(w in detail.lower() for w in ['unavailable','invalid','unsupported','failed','error']):raise RuntimeError('Unresolved prior state; no new submission')
report={'model':'gemini-2.5-flash-tts','line':'林浅，先拍照，别碰它。','state':'SUBMITTING','reference':'Temporary preset Charon; no voice cloning, voice identity may differ','requests':1}
def save(): (out/'voice-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
save()
job=g.request('/v2/gemini-2.5-flash-tts',payload);rid=job['request_id'];assert re.fullmatch(r'[A-Za-z0-9_-]+',rid)
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
  report['duration']=float(probe['format']['duration']);report['actual_bill_verified']=False;save();break
 except Exception:continue
else:raise RuntimeError('No playable output audio')
from faster_whisper import WhisperModel
m=WhisperModel('medium',device='cpu',compute_type='int8',cpu_threads=4)
segments,info=m.transcribe(str(p),language='zh',beam_size=5,word_timestamps=True,vad_filter=False,condition_on_previous_text=False)
asr=[{'start':x.start,'end':x.end,'text':x.text,'words':[{'start':w.start,'end':w.end,'word':w.word} for w in x.words]} for x in segments]
(out/'transcription.json').write_text(json.dumps(asr,ensure_ascii=False,indent=2))
print(json.dumps({'duration':report['duration'],'asr':asr},ensure_ascii=False))
