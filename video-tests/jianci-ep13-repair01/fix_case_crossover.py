from pathlib import Path
import subprocess
p=Path('/workspace/scratch/6651942d1ae0')
src=p/'剑刺_第13集_你看见了_连续性修正版.mp4'
out=p/'剑刺_第13集_你看见了_串案修正版.mp4'
f="[0:v]split[base][detail];[detail]trim=start=40:end=42.5,setpts=(PTS-STARTPTS)*2.4+40/TB,crop=1280:490:0:120[insert];[base][insert]overlay=0:120:enable='gte(t,40)*lt(t,46)'[v]"
subprocess.run(['ffmpeg','-v','error','-y','-i',str(src),'-filter_complex',f,'-map','[v]','-map','0:a:0','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','copy','-t','90','-movflags','+faststart',str(out)],check=True)
print(out)
