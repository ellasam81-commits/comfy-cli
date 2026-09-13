from pathlib import Path
import subprocess
p=Path('/workspace/scratch/6651942d1ae0')
src=p/'剑刺_第13集_你看见了_照片两秒版.mp4'
out=p/'剑刺_第13集_你看见了_母亲连续性修正版.mp4'
f="[0:v]split[base][lin];[lin]crop=680:260:600:160,scale=1280:490:flags=lanczos[detail];[base][detail]overlay=0:120:enable='gte(t,64.966667)*lt(t,67.9)'[v]"
subprocess.run(['ffmpeg','-v','error','-y','-i',str(src),'-filter_complex',f,'-map','[v]','-map','0:a:0','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','copy','-t','83.766667','-movflags','+faststart',str(out)],check=True)
print(out)
