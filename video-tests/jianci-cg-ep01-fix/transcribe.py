import json
from pathlib import Path
from faster_whisper import WhisperModel
out=Path('output/jianci-cg-ep01-fix')
m=WhisperModel('medium',device='cpu',compute_type='int8',cpu_threads=4)
rows=[]
for p in sorted(out.glob('*-raw.mp4')):
 segs,info=m.transcribe(str(p),language='zh',beam_size=5,word_timestamps=True)
 segs=[s._asdict() for s in segs];rows.append({'clip':p.name,'segments':segs})
 print(p.name,' '.join(s['text'] for s in segs),flush=True)
(out/'transcription.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2,default=str))

original=[]
for p in sorted(Path('output/original-qa').glob('*-raw.mp4')):
 segs,info=m.transcribe(str(p),language='zh',beam_size=5,word_timestamps=True)
 segs=[s._asdict() for s in segs];original.append({'clip':p.name,'segments':segs})
 print('ORIGINAL',p.name,' '.join(s['text'] for s in segs),flush=True)
(out/'original-transcription.json').write_text(json.dumps(original,ensure_ascii=False,indent=2,default=str))
