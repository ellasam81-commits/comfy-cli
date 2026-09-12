"""Make Episode 13's suspense score audible on phone speakers; copy video unchanged."""
from pathlib import Path
import wave, subprocess
import numpy as np
P=Path('/tmp/ep13-bgm')
ROOT=Path('/workspace/scratch/6651942d1ae0')
source=ROOT/'剑刺_第13集_你看见了_第一段修正版.mp4'
voice=Path('/tmp/ep13-work/assembled.mp4')
output=ROOT/'剑刺_第13集_你看见了_BGM加强版.mp4'
sr=48000;t=np.arange(sr*90,dtype=np.float64)/sr
# Audible midrange harmonics supplement the bass rather than relying on sub-bass.
s=np.zeros_like(t)
for hz,amp,phase in [(55,.018,0),(110,.020,.5),(220,.030,1),(233.08,.012,2),(440,.009,.3),(466.16,.006,2.2)]:
    swell=.62+.38*np.sin(2*np.pi*.085*t+phase)**2
    vibrato=.11*np.sin(2*np.pi*.22*t+phase)
    s+=amp*swell*np.sin(2*np.pi*hz*t+vibrato)
for onset,hz in [(0,293.66),(9,220),(20,293.66),(29,261.63),(39,220),(49,293.66),(61,311.13),(70,293.66),(76,311.13),(84,220)]:
    u=np.maximum(t-onset,0)
    env=(t>=onset)*(1-np.exp(-u*8))*np.exp(-u/3.0)
    s+=.034*env*(np.sin(2*np.pi*hz*u)+.3*np.sin(2*np.pi*hz*2.004*u))
# Gradually increase tension in the mother's account without loud jump scares.
s*=1+.17*np.clip((t-60)/20,0,1)
s*=10**(-23/20)/np.sqrt(np.mean(s*s))
env=np.minimum(t/1.5,1)*np.clip((90-t)/1.3,0,1)
env[(t>=15)&(t<20)]*=.22
# Smooth silence at the old/new case boundary.
env*=np.where((t>=59)&(t<59.6),(59.6-t)/.6,1)
env[(t>=59.6)&(t<60.25)]=0
env*=np.where((t>=60.25)&(t<61),(t-60.25)/.75,1)
s*=np.clip(env,0,1)
stereo=np.column_stack((s,s*.96))
with wave.open(str(P/'score-strong.wav'),'wb') as w:
    w.setnchannels(2);w.setsampwidth(2);w.setframerate(sr)
    w.writeframes((np.clip(stereo,-1,1)*32767).astype('<i2').tobytes())
flt='[1:a]asplit=2[voice][sc];[2:a][sc]sidechaincompress=threshold=0.05:ratio=3:attack=20:release=450[bg];[voice][bg]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95:level=0[a]'
subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(source),'-i',str(voice),'-i',str(P/'score-strong.wav'),'-filter_complex',flt,'-map','0:v:0','-map','[a]','-c:v','copy','-c:a','aac','-b:a','192k','-t','90','-movflags','+faststart',str(output)],check=True)
print(output)
