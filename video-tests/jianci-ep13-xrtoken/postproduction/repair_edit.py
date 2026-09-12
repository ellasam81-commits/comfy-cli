from pathlib import Path
import subprocess,json
P=Path('/tmp/ep13-work');R=P/'raw';Q=P/'edited';Q.mkdir(exist_ok=True)
def run(a):subprocess.run(a,check=True)
# Reaction insert from the user's already supplied Episode 12, edited locally only.
# Liang's generated question becomes offscreen; no incorrect Han speaking shot remains.
old='/workspace/scratch/6651942d1ae0/剑刺_第12集_别让我靠近他_原声预览.mp4'
flt="[0:v]trim=start=57.8:end=60,setpts=(PTS-STARTPTS)*2.155,crop=554:212:300:86,scale=854:328,pad=854:480:0:74:black,fps=30,tpad=stop_mode=clone:stop_duration=0.2,trim=duration=4.74[a];[1:v]trim=start=4.74:end=10,setpts=PTS-STARTPTS,crop=400:154:40:115,scale=854:328,pad=854:480:0:74:black,fps=30[b];[a][b]concat=n=2:v=1:a=0[v];[1:a]volume=0:enable='between(t,3.95,4.72)'[au]"
run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',old,'-i',str(R/'01-raw.mp4'),'-filter_complex',flt,'-map','[v]','-map','[au]','-t','10','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac',str(Q/'01-raw.mp4')])
flt="[0:v]trim=start=0:end=5,setpts=PTS-STARTPTS[a];[0:v]trim=start=5:end=10,setpts=PTS-STARTPTS,crop=500:192:0:162,scale=854:328,pad=854:480:0:74:black[b];[a][b]concat=n=2:v=1:a=0[v]"
run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(R/'04-raw.mp4'),'-filter_complex',flt,'-map','[v]','-map','0:a','-t','10','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac',str(Q/'04-raw.mp4')])
t={'01-0':[.8,3.5],'01-1':[4.73,8.15],'02-0':[0,3.8],'04-0':[.65,4.7],'04-1':[5,9.4],'05-0':[0,4.1],'05-1':[5.15,9],'06-0':[0,4.95],'06-1':[5.15,8.8],'07-0':[.2,3.0],'07-1':[4.65,7.1]}
(P/'timings.json').write_text(json.dumps(t,indent=2))
# Remove an unrequested cutaway to bystanders from the private promise/nod beat.
flt="[0:v]trim=start=0:end=3.533333,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=1.5,trim=duration=5[a];[0:v]trim=start=6.566667:end=10,setpts=(PTS-STARTPTS)*1.456311,fps=30,tpad=stop_mode=clone:stop_duration=0.1,trim=duration=5[b];[a][b]concat=n=2:v=1:a=0[v]"
run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(R/'02-raw.mp4'),'-filter_complex',flt,'-map','[v]','-map','0:a','-t','10','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac',str(Q/'02-raw.mp4')])
