from pathlib import Path
import json,subprocess
from faster_whisper import WhisperModel
p=Path('qa');m=WhisperModel('medium',device='cpu',compute_type='int8');rows=[]
for clip,a,b in [('02',0,5.45),('02',4.5,10),('03',0,6),('05',0,4),('06',5,9)]:
 out=p/f'{clip}-{a}.wav';subprocess.run(['ffmpeg','-v','error','-y','-ss',str(a),'-to',str(b),'-i',str(p/'raw'/f'{clip}-raw.mp4'),'-ar','16000','-ac','1',str(out)],check=True)
 segs,_=m.transcribe(str(out),language='zh',beam_size=5,word_timestamps=True,condition_on_previous_text=False,vad_filter=False)
 rows.append({'clip':clip,'offset':a,'segments':[{'start':s.start+a,'end':s.end+a,'text':s.text,'words':[{'start':w.start+a,'end':w.end+a,'word':w.word} for w in s.words or []]} for s in segs]})
(p/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
