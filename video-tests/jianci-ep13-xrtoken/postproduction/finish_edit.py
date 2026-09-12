from pathlib import Path
import subprocess,json
p=Path('/tmp/ep13-work')
flt="[0:v]trim=start=0:end=1.433333,setpts=(PTS-STARTPTS)*3.790698,fps=30,tpad=stop_mode=clone:stop_duration=0.2,trim=duration=5.433333[a];[0:v]trim=start=5.433333:end=7.733333,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=2.3,trim=duration=4.566667[b];[a][b]concat=n=2:v=1:a=0[v]"
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(p/'raw/09-raw.mp4'),'-filter_complex',flt,'-map','[v]','-map','0:a','-t','10','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac',str(p/'edited/09-raw.mp4')],check=True)
f=p/'timings.json';t=json.loads(f.read_text());t.update({'03-0':[.05,3.85],'03-1':[4.7,8.5],'08-0':[.25,4.5],'08-1':[5.05,8.25],'09-1':[5.43,8.0]});f.write_text(json.dumps(t,indent=2))
