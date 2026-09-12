from pathlib import Path
import subprocess
p=Path('/workspace/scratch/6651942d1ae0')
src=p/'剑刺_第13集_你看见了_去重复修正版.mp4'
out=p/'剑刺_第13集_你看见了_照片一致修正版.mp4'
# Use the exact photograph introduced by the mother, not a new generated portrait.
# A single photograph can hold with a gentle camera push; no live action is looped.
f="[0:v]split[base][photo];[photo]trim=start=77.7:end=77.733333,setpts=PTS-STARTPTS,crop=1280:490:0:120,zoompan=z='1+0.0007*on':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=163:s=1280x490:fps=30,setpts=PTS+77.9/TB[insert];[base][insert]overlay=0:120:enable='gte(t,77.9)*lt(t,83.333333)'[v]"
subprocess.run(['ffmpeg','-v','error','-y','-i',str(src),'-filter_complex',f,'-map','[v]','-map','0:a:0','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','copy','-t','87.9','-movflags','+faststart',str(out)],check=True)
print(out)
