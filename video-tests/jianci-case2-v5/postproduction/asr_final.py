from pathlib import Path
import json
from faster_whisper import WhisperModel
p=Path('/tmp/jianci-production');m=WhisperModel('small',device='cpu',compute_type='int8',cpu_threads=4)
for ep in [15,17,18]:
 f=next((p/'final').glob(f'剑刺_第{ep}集_*.mp4'));seg,info=m.transcribe(str(f),language='zh',word_timestamps=True,vad_filter=True)
 a=[dict(start=s.start,end=s.end,text=s.text) for s in seg];(p/f'final-qa/ep{ep}/asr.json').write_text(json.dumps(a,ensure_ascii=False,indent=2));print(ep,a,flush=True)
