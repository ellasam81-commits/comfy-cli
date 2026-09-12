from pathlib import Path
import subprocess
p=Path('/workspace/scratch/6651942d1ae0')
src=p/'剑刺_第13集_你看见了_转场修正版.mp4'
out=p/'剑刺_第13集_你看见了_去重复修正版.mp4'
# Ripple-delete recycled waiting shot 67.9-70.0, including its pause.
# Keep all dialogue and baked captions aligned. Tiny audio fades prevent clicks.
f="[0:v]split[x][y];[x]trim=end=67.9,setpts=PTS-STARTPTS[a];[y]trim=start=70,setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0[v];[0:a]asplit[c][d];[c]atrim=end=67.9,asetpts=PTS-STARTPTS,afade=t=out:st=67.875:d=0.025[e];[d]atrim=start=70,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.025[g];[e][g]concat=n=2:v=0:a=1[au]"
subprocess.run(['ffmpeg','-v','error','-y','-i',str(src),'-filter_complex',f,'-map','[v]','-map','[au]','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-t','87.9','-movflags','+faststart',str(out)],check=True)
print(out)
