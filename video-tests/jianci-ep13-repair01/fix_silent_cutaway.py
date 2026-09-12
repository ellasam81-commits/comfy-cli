"""Replace Episode 13's unvoiced extra cutaway at 67.9–70 seconds."""
from pathlib import Path
import subprocess
root=Path('/workspace/scratch/6651942d1ae0')
src=root/'剑刺_第13集_你看见了_第12集配乐风格版.mp4'
out=root/'剑刺_第13集_你看见了_口型修正版.mp4'
# Reuse a silent mother reaction from 63.1–64.5s (no caption or speech there).
# Extend its 42 frames to 63 frames. Keep the original audio stream untouched.
flt='[0:v]split=3[x][y][z];[x]trim=end=67.9,setpts=PTS-STARTPTS[a];[y]trim=start=63.1:end=64.5,setpts=1.5*(PTS-STARTPTS),fps=30,tpad=stop_mode=clone:stop_duration=0.1,trim=duration=2.1[b];[z]trim=start=70,setpts=PTS-STARTPTS[c];[a][b][c]concat=n=3:v=1:a=0[v]'
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(src),'-filter_complex',flt,'-map','[v]','-map','0:a:0','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','copy','-t','90','-movflags','+faststart',str(out)],check=True)
print(out)
