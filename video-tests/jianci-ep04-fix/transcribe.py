from pathlib import Path
import json,subprocess
from faster_whisper import WhisperModel
p=Path('output/jianci-ep04-fix');m=WhisperModel('medium',device='cpu',compute_type='int8');rows=[]
for name,start,duration in [('03-early',0,3.3),('03-all',0,10),('04-last',7.8,2.2)]:
 source='03' if name.startswith('03') else '04'
 subprocess.run(['ffmpeg','-v','error','-y','-ss',str(start),'-i',f'original-ep04/{source}-raw.mp4','-t',str(duration),'-vn',str(p/(name+'.wav'))],check=True)
for f in [p/'05-raw.mp4']+list(p.glob('*.wav')):
 segs,info=m.transcribe(str(f),language='zh',beam_size=5,word_timestamps=True,condition_on_previous_text=False)
 rows.append({'clip':f.name,'segments':[{'start':s.start,'end':s.end,'text':s.text,'words':[{'start':w.start,'end':w.end,'word':w.word,'probability':w.probability} for w in s.words or []]} for s in segs]})
(p/'transcription.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
