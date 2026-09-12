"""Episode 13 score in Episode 12's low-register suspense style, not an extracted track."""
from pathlib import Path
import wave, subprocess
import numpy as np
P=Path('/tmp/ep13-bgm12');ROOT=Path('/workspace/scratch/6651942d1ae0')
video=ROOT/'剑刺_第13集_你看见了_第一段修正版.mp4'
voice=Path('/tmp/ep13-work/assembled.mp4')
out=ROOT/'剑刺_第13集_你看见了_第12集配乐风格版.mp4'
sr=48000;t=np.arange(sr*90,dtype=float)/sr;s=np.zeros_like(t)
# Reference analysis: Episode 12's added energy lies chiefly below 500 Hz,
# with strong components near 43, 73, 110, 147 and 220 Hz. Use a warm D-minor bed.
for hz,amp,phase in [(43.654,.018,.8),(73.416,.032,0),(110,.019,1.1),(146.832,.013,2),(174.614,.009,.4),(220,.010,1.5)]:
 swell=.7+.3*np.sin(2*np.pi*.045*t+phase)**2
 s+=amp*swell*np.sin(2*np.pi*hz*t+.045*np.sin(2*np.pi*.14*t+phase))
# Muted felt-like notes: soft attack, quick high-harmonic decay, no metallic shimmer.
notes=[(0,293.665),(8,220),(20,293.665),(28,261.626),(36,220),(45,174.614),(53,220),(61,293.665),(70,220),(76,311.127),(84,293.665)]
for start,hz in notes:
 u=np.maximum(t-start,0);attack=(t>=start)*(1-np.exp(-u*14))
 s+=.027*attack*(np.exp(-u/2.8)*np.sin(2*np.pi*hz*u)+.16*np.exp(-u/.8)*np.sin(2*np.pi*2*hz*u))
s*=10**(-25.5/20)/np.sqrt(np.mean(s*s))
env=np.minimum(t/1.6,1)*np.clip((90-t)/1.8,0,1)
env[(t>=15)&(t<20)]*=.16
env*=np.where((t>=59)&(t<59.6),(59.6-t)/.6,1)
env[(t>=59.6)&(t<60.25)]=0
env*=np.where((t>=60.25)&(t<61.3),(t-60.25)/1.05,1)
s*=np.clip(env,0,1)
with wave.open(str(P/'score-ep12-style.wav'),'wb') as w:
 w.setnchannels(2);w.setsampwidth(2);w.setframerate(sr)
 w.writeframes((np.clip(np.column_stack([s,s*.97]),-1,1)*32767).astype('<i2').tobytes())
flt='[1:a]asplit=2[voice][sc];[2:a][sc]sidechaincompress=threshold=0.05:ratio=3:attack=25:release=500[bg];[voice][bg]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:level=0[a]'
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(video),'-i',str(voice),'-i',str(P/'score-ep12-style.wav'),'-filter_complex',flt,'-map','0:v:0','-map','[a]','-c:v','copy','-c:a','aac','-b:a','192k','-t','90','-movflags','+faststart',str(out)],check=True)
print(out)
