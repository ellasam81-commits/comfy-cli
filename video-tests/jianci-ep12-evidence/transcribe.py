from pathlib import Path
import json,subprocess
from faster_whisper import WhisperModel
p=Path('output/jianci-ep12-evidence');m=WhisperModel('medium',device='cpu',compute_type='int8');rows=[]
for f in sorted(p.glob('*-raw.mp4')):
 segs,info=m.transcribe(str(f),language='zh',beam_size=5,word_timestamps=True,condition_on_previous_text=False)
 rows.append({'clip':f.name,'segments':[{'start':s.start,'end':s.end,'text':s.text,'words':[{'start':w.start,'end':w.end,'word':w.word,'probability':w.probability} for w in s.words or []]} for s in segs]})
(p/'transcription.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))


openings=[]
for f in sorted(p.glob('*-raw.mp4')):
 wav=p/(f.stem+'-opening.wav');subprocess.run(['ffmpeg','-v','error','-y','-i',str(f),'-t','1.45','-ar','16000','-ac','1',str(wav)],check=True)
 segs,_=m.transcribe(str(wav),language='zh',beam_size=5,word_timestamps=True,condition_on_previous_text=False,vad_filter=False)
 openings.append({'clip':f.name,'segments':[{'start':s.start,'end':s.end,'text':s.text} for s in segs]})
(p/'opening-check.json').write_text(json.dumps(openings,ensure_ascii=False,indent=2))
