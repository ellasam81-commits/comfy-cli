from pathlib import Path
import subprocess
p=Path('/workspace/scratch/6651942d1ae0')
src=p/'剑刺_第13集_你看见了_结尾衔接修正版.mp4'
out=p/'剑刺_第13集_你看见了_照片节奏修正版.mp4'
# Remove two seconds from the silent photo hold; maintain continuous camera motion.
f="[0:v]split=3[x][y][p];[x]trim=end=79.5,setpts=PTS-STARTPTS[a];[y]trim=start=81.5,setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0[base];[p]trim=start=77.7:end=77.733333,setpts=PTS-STARTPTS,crop=1280:490:0:120,zoompan=z='1+0.0007*on':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=124:s=1280x490:fps=30,setpts=PTS+77.9/TB[photo];[base][photo]overlay=0:120:enable='gte(t,77.9)*lt(t,82.033333)'[v];[0:a]asplit[c][d];[c]atrim=end=79.5,asetpts=PTS-STARTPTS,afade=t=out:st=79.475:d=0.025[e];[d]atrim=start=81.5,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.025[g];[e][g]concat=n=2:v=0:a=1[au]"
subprocess.run(['ffmpeg','-v','error','-y','-i',str(src),'-filter_complex',f,'-map','[v]','-map','[au]','-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-t','85.9','-movflags','+faststart',str(out)],check=True)
print(out)
