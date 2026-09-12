from pathlib import Path
import subprocess
p=Path('/workspace/scratch/6651942d1ae0')
src=p/'剑刺_第13集_你看见了_串案修正版.mp4'
out=p/'剑刺_第13集_你看见了_转场修正版.mp4'
# Cover the crop jump and generated dissolve with a clean case-file insert.
# Original voice timing, captions and all previous repairs are preserved.
f="[1:v]trim=start=7:end=9,setpts=PTS-STARTPTS+34.9/TB,crop=854:328:0:74,scale=1280:490:flags=lanczos,fps=30[insert];[0:v][insert]overlay=0:120:enable='gte(t,34.9)*lt(t,36.9)'[v]"
subprocess.run(['ffmpeg','-v','error','-y','-i',str(src),'-i','/tmp/ep13-work/raw/03-raw.mp4','-filter_complex',f,'-map','[v]','-map','0:a:0','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','copy','-t','90','-movflags','+faststart',str(out)],check=True)
print(out)
