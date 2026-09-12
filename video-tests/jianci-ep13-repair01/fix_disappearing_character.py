"""Replace the faulty 74.967–77.9s character fade with a hand-and-photo insert."""
from pathlib import Path
import subprocess
p=Path('/workspace/scratch/6651942d1ae0')
src=p/'剑刺_第13集_你看见了_口型修正版.mp4'
out=p/'剑刺_第13集_你看见了_连续性修正版.mp4'
# Only the picture window changes; preserve the existing captions and audio.
f="[0:v]split[base][detail];[detail]crop=640:246:640:330,scale=1280:490[insert];[base][insert]overlay=0:120:enable='gte(t,74.966667)*lt(t,77.9)'[v]"
subprocess.run(['ffmpeg','-v','error','-y','-i',str(src),'-filter_complex',f,'-map','[v]','-map','0:a:0','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','copy','-t','90','-movflags','+faststart',str(out)],check=True)
print(out)
