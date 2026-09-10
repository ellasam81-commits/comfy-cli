import json
from pathlib import Path
from faster_whisper import WhisperModel
out=Path('output/jianci-anime-ep01-repair')
m=WhisperModel('medium',device='cpu',compute_type='int8',cpu_threads=4)
rows=[]
for p in sorted(out.glob('*-raw.mp4')):
 segs,info=m.transcribe(str(p),language='zh',beam_size=5,word_timestamps=True)
 segs=[s._asdict() for s in segs];rows.append({'clip':p.name,'segments':segs})
 print(p.name,' '.join(s['text'] for s in segs),flush=True)
(out/'transcription.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2,default=str))
