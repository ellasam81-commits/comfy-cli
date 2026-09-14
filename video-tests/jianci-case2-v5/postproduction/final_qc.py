import json,subprocess,sys,math
from pathlib import Path
import cv2,numpy as np
from PIL import Image,ImageDraw
P=Path('/tmp/jianci-production');eps=[int(x) for x in sys.argv[1:]] or [14,15,16,17,18]
for ep in eps:
 f=next((P/'final').glob(f'剑刺_第{ep}集_*.mp4'));E=P/f'edit/ep{ep}';Q=P/f'final-qa/ep{ep}';Q.mkdir(parents=True,exist_ok=True)
 probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(f)]));decode=subprocess.run(['ffmpeg','-v','error','-i',str(f),'-f','null','-'],capture_output=True,text=True)
 timeline=json.loads((E/'timeline.json').read_text());cap=cv2.VideoCapture(str(f));dur=float(probe['format']['duration']);samples=[]
 for i,s in enumerate(timeline):
  for t in [s['start']+.1,(s['start']+s['end'])/2,s['end']-.1]:samples.append((max(0,min(dur-.1,t)),f'cut{i}'))
 # Each sheet is small enough to inspect at readable size.
 for page in range(math.ceil(len(samples)/12)):
  im=Image.new('RGB',(1280,4*265),(22,22,22));dr=ImageDraw.Draw(im)
  for k,(t,label) in enumerate(samples[page*12:page*12+12]):
   cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,a=cap.read()
   if ok:im.paste(Image.fromarray(cv2.cvtColor(a,cv2.COLOR_BGR2RGB)).resize((426,240)),((k%3)*426,(k//3)*265));dr.text(((k%3)*426+3,(k//3)*265+242),f'{label} {t:.2f}s',fill='white')
  im.save(Q/f'boundary-{page+1}.jpg',quality=90)
 cap.release()
 # Check dialogue signal in each scheduled line, before background music.
 cut=E/'cut.mp4';wav=Q/'dialogue.wav';subprocess.run(['ffmpeg','-v','error','-y','-i',str(cut),'-vn','-ac','1','-ar','16000','-f','f32le',str(Q/'audio.f32')],check=True)
 audio=np.fromfile(Q/'audio.f32',dtype='<f4');plan=json.loads((E/'edit.json').read_text());cursor=0;levels=[]
 for s in plan['segments']:
  for r,cn,en,a,b in s.get('lines',[]):
   z=audio[int((cursor+a)*16000):int((cursor+b)*16000)];db=float(20*np.log10(max(1e-9,np.sqrt(np.mean(z*z))))) if len(z) else -180
   levels.append(dict(text=cn,start=cursor+a,end=cursor+b,rms_dbfs=round(db,1)))
  cursor+=s['duration']
 result={'episode':ep,'duration':dur,'decode_errors':decode.stderr,'decode_exit':decode.returncode,'av_streams':[x['codec_type'] for x in probe['streams']],'audio_video_duration_difference':abs(float(probe['streams'][0].get('duration',dur))-float(probe['streams'][1].get('duration',dur))),'dialogue_levels':levels,'silent_expected_lines':[x for x in levels if x['rms_dbfs']<-38],'scope':'All frames decoded; boundary and dense source-frame visual review plus ASR-based dialogue timing. Not continuous human audiovisual playback or phoneme-level lip-sync certification.'}
 (Q/'checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));(Q/'audio.f32').unlink()
 print(ep,round(dur,2),'decode',decode.returncode,'silent-lines',len(result['silent_expected_lines']),flush=True)
