from pathlib import Path
import subprocess,os
P=Path(__file__).resolve().parent;R=P/'raw';O=P/'corrected';O.mkdir(exist_ok=True)
# Prop inserts avoid showing a moving mouth during removal of spoken directions.
# Boundaries verified by word-level transcription.
for cid,end,crop in [('08_01',3.05,'crop=600:250:90:230'),('09_01',2.92,'crop=330:186:45:294'),('10_01',2.56,'crop=560:190:20:290')]:
 filt=f'[0:v]split=2[i][w];[i]trim=duration={end},setpts=PTS-STARTPTS,{crop},scale=854:480,setsar=1,fps=24[a];[w]trim=start={end}:end=5,setpts=PTS-STARTPTS,scale=854:480,setsar=1,fps=24[b];[a][b]concat=n=2:v=1:a=0[v];[0:a]volume=0:enable=\'lt(t,{end})\',afade=t=in:st={end}:d=0.02,apad,atrim=duration=5[au]'
 subprocess.run(['ffmpeg','-y','-v','error','-i',str(R/(cid+'-raw.mp4')),'-filter_complex',filt,'-map','[v]','-map','[au]','-t','5','-c:v','libx264','-threads','2','-preset','fast','-crf','17','-c:a','aac','-b:a','192k',str(O/(cid+'-pending.mp4'))],check=True)
 os.replace(O/(cid+'-pending.mp4'),O/(cid+'-raw.mp4'))
 print('Removed spoken setup and inserted relevant prop close-up:',cid,flush=True)
