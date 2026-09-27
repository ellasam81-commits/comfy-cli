from pathlib import Path
from faster_whisper import WhisperModel
import json,sys,re
from difflib import SequenceMatcher
root=Path(__file__).parent;raw=Path(sys.argv[1]) if len(sys.argv)>1 else root/'raw'
model=WhisperModel('small',device='cpu',compute_type='int8',cpu_threads=4,download_root=str(root.parent/'two-fix/whisper'),local_files_only=True)
out={}
cfg=json.load(open(root/'episodes.json'));expected={c['id']:c['zh'] for e in cfg['episodes'] for c in e['clips']}
expected['07_01']='等一下我能救我能救'
def norm(x):return re.sub(r'[^\u4e00-\u9fff0-9]','',x)
for p in sorted(raw.glob('*-raw.mp4')):
 cid=p.stem.replace('-raw','')
 corrected=root/'corrected'/p.name
 if corrected.exists():p=corrected
 seg,info=model.transcribe(str(p),language='zh',beam_size=5,vad_filter=True,word_timestamps=True)
 ss=list(seg);out[p.stem.replace('-raw','')]={'text':''.join(s.text for s in ss),'segments':[{'start':s.start,'end':s.end,'text':s.text,'words':[{'start':w.start,'end':w.end,'word':w.word} for w in (s.words or [])]} for s in ss]}
 out[cid]['expected']=expected.get(cid,'');out[cid]['similarity']=round(SequenceMatcher(None,norm(out[cid]['text']),norm(expected.get(cid,''))).ratio(),3)
 print(p.name,out[p.stem.replace('-raw','')]['text'],flush=True)
 (raw/'transcripts.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
