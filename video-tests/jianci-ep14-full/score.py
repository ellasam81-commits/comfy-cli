import numpy as np, wave
from pathlib import Path
P=Path('/tmp/ep14-full')
sr=24000;t=np.arange(sr*60)/sr;s=np.zeros_like(t)
for hz,amp,phase in [(43.654,.018,.8),(73.416,.032,0),(110,.019,1.1),(146.832,.013,2),(174.614,.009,.4),(220,.010,1.5)]:
 s+=amp*(.7+.3*np.sin(2*np.pi*.045*t+phase)**2)*np.sin(2*np.pi*hz*t+.045*np.sin(2*np.pi*.14*t+phase))
for start,hz in [(0,293.665),(9,220),(20,261.626),(30,220),(40,174.614),(50,293.665),(54,311.127)]:
 u=np.maximum(t-start,0);a=(t>=start)*(1-np.exp(-u*14))
 s+=.027*a*(np.exp(-u/2.8)*np.sin(2*np.pi*hz*u)+.16*np.exp(-u/.8)*np.sin(2*np.pi*2*hz*u))
s*=10**(-25.5/20)/np.sqrt(np.mean(s*s))
s*=np.minimum(t/1.2,1)*np.clip((60-t)/1.2,0,1)
with wave.open(str(P/'score.wav'),'wb') as w:
 w.setnchannels(2);w.setsampwidth(2);w.setframerate(sr);w.writeframes((np.clip(np.column_stack([s,s*.97]),-1,1)*32767).astype('<i2').tobytes())
