from pathlib import Path
from PIL import Image,ImageDraw
from faster_whisper import WhisperModel
import json,subprocess,sys
ROOT=Path('/workspace/scratch/b4c0488cda29/output/mengmeng-ep02-05');ROOT.mkdir(exist_ok=True,parents=True)
dst=ROOT/'transcripts.json';known=json.loads(dst.read_text()) if dst.exists() else {}
todo=[p for p in sorted(ROOT.glob('*-raw.mp4')) if p.stem[:-4] not in known]
if todo:
 model=WhisperModel('small',device='cpu',compute_type='int8',cpu_threads=4,download_root='/workspace/scratch/b4c0488cda29/names-source/whisper')
 for p in todo:
  i=p.stem[:-4]
  segs,info=model.transcribe(str(p),language='zh',beam_size=5,vad_filter=False,condition_on_previous_text=False,word_timestamps=True)
  known[i]=[{'start':s.start,'end':s.end,'text':s.text,'words':[{'start':w.start,'end':w.end,'text':w.word} for w in s.words]} for s in segs]
  dst.write_text(json.dumps(known,ensure_ascii=False,indent=2));print(i,json.dumps(known[i],ensure_ascii=False),flush=True)
for ep in range(2,6):
 available=[i for i in range(1,13) if (ROOT/f'{ep:02}_{i:02}-b.jpg').exists()]
 if not available:continue
 for page in range((len(available)+3)//4):
  canvas=Image.new('RGB',(1281,1040),'#101820');d=ImageDraw.Draw(canvas)
  for row,n in enumerate(available[page*4:page*4+4]):
   for col,label in enumerate(['a','b','end']):
    im=Image.open(ROOT/f'{ep:02}_{n:02}-{label}.jpg').convert('RGB').resize((427,240));canvas.paste(im,(col*427,row*260+20));d.text((col*427+5,row*260+4),f'{ep:02}_{n:02} {label}',fill='white')
  canvas.save(ROOT/f'ep{ep:02}-review-{page+1}.jpg',quality=90)
print('Known clips',len(known),flush=True)
