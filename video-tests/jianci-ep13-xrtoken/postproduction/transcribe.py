import json
from pathlib import Path
from faster_whisper import WhisperModel
p=Path('/tmp/ep13-work/raw')
m=WhisperModel('small',device='cpu',compute_type='int8',cpu_threads=4)
results=[]
for f in sorted(p.glob('*-raw.mp4')):
 segs,info=m.transcribe(str(f),language='zh',beam_size=5,word_timestamps=True,vad_filter=True,initial_prompt='检刺 林浅 韩彻 梁川 顾晴 罗茵 周峤 赵成 祁芸')
 row={'file':f.name,'segments':[{'start':s.start,'end':s.end,'text':s.text,'words':[{'start':w.start,'end':w.end,'word':w.word} for w in (s.words or [])]} for s in segs]}
 results.append(row)
 print(f.name,[(s['start'],s['end'],s['text']) for s in row['segments']],flush=True)
 (p/'transcription.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
