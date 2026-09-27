from pathlib import Path
from faster_whisper import WhisperModel
import json,sys
root=Path(__file__).parent;raw=Path(sys.argv[1]) if len(sys.argv)>1 else root/'raw'
model=WhisperModel('small',device='cpu',compute_type='int8',cpu_threads=4,download_root=str(root.parent/'two-fix/whisper'),local_files_only=True)
out={}
for p in sorted(raw.glob('*-raw.mp4')):
 seg,info=model.transcribe(str(p),language='zh',beam_size=5,vad_filter=True,word_timestamps=True)
 ss=list(seg);out[p.stem.replace('-raw','')]={'text':''.join(s.text for s in ss),'segments':[{'start':s.start,'end':s.end,'text':s.text} for s in ss]}
 print(p.name,out[p.stem.replace('-raw','')]['text'],flush=True)
 (raw/'transcripts.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
