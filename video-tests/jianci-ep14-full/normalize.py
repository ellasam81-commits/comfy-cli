from pathlib import Path
import subprocess
p=Path('/tmp/ep14-full')
for cid in ['01','02','03','04','05','06','07']:
 f=p/'edited'/f'{cid}-raw.mp4'
 if not f.exists():f=p/'raw'/f'{cid}-raw.mp4'
 out=p/f'{cid}-normalized.mp4'
 if not f.exists() or out.exists():continue
 subprocess.run(['ffmpeg','-v','error','-y','-i',str(f),'-t','10','-vf','crop=854:328:0:48,scale=1280:490,pad=1280:720:0:120:black,setsar=1,fps=30','-af','aresample=48000,apad','-c:v','libx264','-preset','fast','-crf','18','-c:a','aac','-ar','48000','-ac','2',str(out)],check=True)
 print('Normalized',cid,flush=True)
