from pathlib import Path
import subprocess
p=Path('/tmp/ep14-work')
# Keep scarf inspection, replace invented paper/garbled-caption cutaway.
# Use only previously unused footage of the same mother quietly listening.
f="[0:v]trim=end=4.8,setpts=PTS-STARTPTS,crop=854:328:0:'48+80*min(t/2.5,1)',pad=854:480:0:48:black[a];[1:v]trim=start=8:end=9.9,setpts=(PTS-STARTPTS)*1.263157895,crop=854:328:0:48,pad=854:480:0:48:black,fps=30,tpad=stop_mode=clone:stop_duration=3,trim=duration=5.2[b];[a][b]concat=n=2:v=1:a=0[v]"
subprocess.run(['ffmpeg','-v','error','-y','-i',str(p/'raw/06-raw.mp4'),'-i',str(p/'raw/01-raw.mp4'),'-filter_complex',f,'-map','[v]','-map','0:a:0','-t','10','-c:v','libx264','-preset','fast','-crf','18','-c:a','copy',str(p/'edited/06-raw.mp4')],check=True)
